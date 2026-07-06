# nunchi-gate-hook — Claude Code PreToolUse Integration

## What it does

`nunchi_gate_hook.py` is a Claude Code **PreToolUse hook** that gates outbound
channel sends through the nunchi admission classifier. When a Claude Code agent
tries to send a reply to a chat surface (Discord or similar) by invoking a
matching reply tool, the hook:

1. Parses the session transcript to identify the most recent inbound channel
   message for that chat channel.
2. Builds a `nunchi-channel` payload (trigger + history + agent identity).
3. Calls the `nunchi-channel` binary to obtain a verdict.
4. **On PASS** (silent=true): outputs a `deny` hookSpecificOutput, preventing
   the send. The model receives a clear instruction to stay silent.
5. **On any other verdict** (ACK, ASK, SPEAK): outputs an `allow`
   hookSpecificOutput, letting the send proceed.

This converts voluntary instruction-following into a hard gate enforced at the
tooling layer, with a receipt log for every decision.

## What it does NOT enforce

Agent-initiated sends (no inbound channel message in the transcript for that
`chat_id`) are not gated — the hook allows them through silently and logs the
action as `allow-untriggered`. Gating initiations requires out-of-band context
that the transcript alone cannot provide.

## Hook output contract

The hook always exits 0. It writes JSON to stdout or nothing at all.

**Allow** (non-PASS verdict, non-matching tool, untriggered send):
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow"
  }
}
```

**Deny** (PASS verdict, or fail-closed gate error):
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "nunchi gate: PASS — <first reason>. Do not send this message; stay silent this turn and end your reply without further send attempts."
  }
}
```

Non-matching tools produce no stdout output (Claude Code applies normal
permission flow). The hook never exits 2; gate errors are handled by the
fail policy, not by blocking via exit code.

## settings.json configuration

Add this to your project or user `settings.json` to register the hook for
the Discord reply tool. Adjust the matcher and command path to match your
deployment.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "mcp__plugin_discord_discord__reply",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/integrations/claude-code/nunchi_gate_hook.py",
            "timeout": 35
          }
        ]
      }
    ]
  }
}
```

To gate all reply tools (not just Discord), use a broader matcher:
```json
"matcher": ".*__reply$"
```

The `matcher` field is matched against `tool_name`. The hook also checks that
`tool_input` contains both `chat_id` and `text` before acting; other tools
that happen to match the pattern but lack those fields are passed through.

**Note:** Hook configuration changes take effect immediately for new tool
calls, but an active Claude Code session must be restarted (or the session
reloaded) for changes to `settings.json` to be picked up by the running
process.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `NUNCHI_HOOK_TOOL_PATTERN` | `__reply$` | Regex matched against `tool_name`. Must also have `chat_id` + `text` in `tool_input`. |
| `NUNCHI_HOOK_AGENT_ID` | `agent` | Agent identifier sent in the nunchi payload. |
| `NUNCHI_HOOK_MENTION_ID` | _(unset)_ | Optional @mention handle for the agent. |
| `NUNCHI_HOOK_PEER_BOTS` | _(empty)_ | Comma-separated usernames treated as `peer_bot` (all others are `human`). |
| `NUNCHI_HOOK_FAIL_POLICY` | `open` | Gate error handling: `open` → allow, `closed` → deny. |
| `NUNCHI_HOOK_TIMEOUT` | `30` | Timeout in seconds for the nunchi-channel subprocess. |
| `NUNCHI_HOOK_LOG` | `~/.claude/nunchi-gate-receipts.jsonl` | Path for per-call receipt log (JSONL). |
| `NUNCHI_CHANNEL_BIN` | `shutil.which("nunchi-channel")` | Path to the nunchi-channel binary. |

## Receipts log format

Each gated call appends one JSON line to `NUNCHI_HOOK_LOG`:

```json
{
  "ts": "2026-07-02T15:30:00+00:00",
  "session_id": "abc123",
  "chat_id": "1488717251212476569",
  "trigger_message_id": "1515760096783761541",
  "trigger_author": "decisionparalysis",
  "history_len": 3,
  "verdict": "PASS",
  "silent": true,
  "action": "deny-pass",
  "elapsed_ms": 42.1,
  "reasons": ["bot chatter ratio too high"]
}
```

`action` values:
- `allow-untriggered` — no inbound trigger found; send passed through unexamined
- `allow-<verdict>` — gate returned non-silent verdict (e.g. `allow-speak`)
- `deny-pass` — gate returned PASS/silent; send blocked
- `allow-gate-error` — gate failed, fail-open policy applied
- `deny-gate-error` — gate failed, fail-closed policy applied

## Requirements

- Python 3.11+ stdlib only; no third-party dependencies.
- `nunchi-channel` binary installed (via `pip install nunchi` or pointing
  `NUNCHI_CHANNEL_BIN` at the module: `python3 -m nunchi.adapters.channel`).
- A configured classifier environment for `nunchi-channel`
  (`NUNCHI_CLASSIFIER_MODEL` + `OPENROUTER_API_KEY` or equivalent).

---

# nunchi-prompt-gate — Claude Code UserPromptSubmit Integration

## What it does

`nunchi_prompt_gate.py` is a Claude Code **UserPromptSubmit hook** that gates
*inbound* channel messages **before they reach the LLM**.  When Claude Code
receives a submitted prompt that contains a `<channel ...>` tag (the format
used by Discord/channel transport adapters), the hook:

1. Parses the channel tag from the prompt to identify the sender, chat ID,
   and message body.
2. Parses the session transcript to build a history window of past events for
   that channel (inbound messages + agent self-sends).
3. Calls `nunchi-channel` with the trigger + history + agent identity.
4. **On PASS**: outputs `{"decision": "block", "reason": "..."}`, suppressing
   the prompt before any LLM inference runs.
5. **On SPEAK / ACK / ASK**: exits 0 with no output, allowing the prompt
   through normally.

Suppressing on PASS costs one lightweight gate call instead of a full
frontier-model turn.

## What it does NOT enforce

- **Operator prompts** (no `<channel>` tag) always pass through instantly —
  zero gate calls, no receipt.  The operator's own messages are never gated.
- **Outbound sends** are not gated here — that is handled separately by the
  PreToolUse hook (`nunchi_gate_hook.py`).  Both hooks are designed to run
  together; they complement each other.
- **Transport bot-deafness** (the Discord adapter ignoring messages from other
  bots by default) is a separate, upstream concern.  This hook operates on
  whatever prompts Claude Code already received; it does not filter at the
  transport layer.

## Inbound vs outbound gate summary

| Concern | Hook | Claude Code event |
|---|---|---|
| Channel message arrives (pre-LLM) | `nunchi_prompt_gate.py` | `UserPromptSubmit` |
| Agent tries to send a reply (pre-tool) | `nunchi_gate_hook.py` | `PreToolUse` |

## settings.json configuration

Add **both** hooks to your project or user `settings.json`.  The inbound hook
uses a `UserPromptSubmit` entry (no matcher needed — it self-selects on the
`<channel>` tag in the prompt):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/integrations/claude-code/nunchi_prompt_gate.py",
            "timeout": 35
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "mcp__plugin_discord_discord__reply",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/integrations/claude-code/nunchi_gate_hook.py",
            "timeout": 35
          }
        ]
      }
    ]
  }
}
```

Both hooks share the same `NUNCHI_CHANNEL_BIN`, `NUNCHI_HOOK_AGENT_ID`,
`NUNCHI_HOOK_LOG`, and other environment variables described below.

**Note:** Hook configuration changes take effect immediately for new events,
but an active Claude Code session must be restarted for changes to
`settings.json` to be picked up by the running process.

## Hook output contract

The hook always exits 0.  It writes JSON to stdout or nothing at all.

**Block** (PASS verdict):
```json
{"decision": "block", "reason": "nunchi gate: PASS — <first reason>."}
```

**Allow** (SPEAK / ACK / ASK verdict, non-channel prompt, or any gate error):
No stdout output; exit 0.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `NUNCHI_HOOK_AGENT_ID` | `agent` | Agent identifier in the nunchi payload. |
| `NUNCHI_HOOK_MENTION_ID` | _(unset)_ | Optional @mention handle for the agent. |
| `NUNCHI_HOOK_PEER_BOTS` | _(empty)_ | Comma-separated usernames treated as `peer_bot`. |
| `NUNCHI_HOOK_HISTORY_WINDOW` | `25` | Max transcript events included as history (most recent N). |
| `NUNCHI_HOOK_TOOL_PATTERN` | `__reply$` | Regex identifying outbound self-sends in the transcript. |
| `NUNCHI_HOOK_TIMEOUT` | `30` | Timeout in seconds for the nunchi-channel subprocess. |
| `NUNCHI_HOOK_LOG` | `~/.claude/nunchi-gate-receipts.jsonl` | Path for per-call receipt log (JSONL). |
| `NUNCHI_CHANNEL_BIN` | `shutil.which("nunchi-channel")` | Path to the nunchi-channel binary. |

Note: `NUNCHI_HOOK_HISTORY_WINDOW` defaults to **25** for the inbound hook
(vs. 10 for the outbound hook) because the inbound gate operates on the
entire prior transcript; larger context improves admission accuracy.

## Receipts log format

The inbound hook appends one JSON line per gate decision to the same
`NUNCHI_HOOK_LOG` file as the outbound hook.  The `"direction"` field
distinguishes the two:

```json
{
  "ts": "2026-07-06T12:00:00+00:00",
  "direction": "inbound",
  "session_id": "abc123",
  "chat_id": "1488717251212476569",
  "trigger_message_id": "1515760096783761541",
  "trigger_author": "decisionparalysis",
  "history_len": 12,
  "verdict": "PASS",
  "silent": true,
  "action": "block-pass",
  "elapsed_ms": 38.4,
  "reasons": ["conversation is still active"]
}
```

`action` values:
- `block-pass` — gate returned PASS; prompt blocked before LLM
- `allow-<verdict>` — gate returned non-PASS verdict (e.g. `allow-speak`)
- `allow-gate-error` — gate failed; fail-open applied (always for inbound)

The inbound hook is **permanently fail-open**: there is no `deny-gate-error`
action.  Gate failures on the inbound path always allow the prompt through,
ensuring a broken gate cannot silence the operator or wedge the session.
