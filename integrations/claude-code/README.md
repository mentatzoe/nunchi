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
