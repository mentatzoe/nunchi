# nunchi for Claude Code — one judgment per turn, at wake

> **Inherited V1 packet material — do not install as V2.** This directory has
> not yet been replaced by Claude's accepted Claude Code V2 packet. The
> descriptions below document the inherited implementation and are retained
> only as packet input. `nunchi-install` fails closed and will not register or
> copy it. The required V2 outcome is tracked in
> [`docs/INSTALL.md`](../../docs/INSTALL.md) and
> [`docs/adapters.md`](../../docs/adapters.md).

## The shape

Nunchi asks one question, once, before an agent takes a turn: *does this agent
have something to add for these people?* For Claude Code that judgment happens
at **wake time** — the `UserPromptSubmit` hook — and nowhere else:

- **PASS (confident)** → the prompt is blocked before any LLM inference runs.
  The agent never wakes; nothing is composed; nothing is sent.
- **PASS (uncertain)** → **DEFER**: the gate abstains. The message reaches the
  agent with the gate's hesitation noted, and the agent's own model — the thing
  that actually holds the room — decides. It may reply; it may choose silence.
  A small fast gate only silences what it can confidently judge.
- **SPEAK / ACK / ASK** → admitted. A short in-band note names the message this
  turn answers, so composition stays anchored to its origin even if more room
  lines land while the agent is thinking. What the agent says — and whether it
  says anything — is the agent's.

There is deliberately **no send-time re-judgment**. An earlier version ran a
second hook (`PreToolUse`) that re-judged composed replies against the newest
transcript line; a peer message landing mid-composition would steal the causal
role and the reply died as a false PASS. Patching that split required a permit
side-store — state whose only job was keeping two judgments consistent. Both
were removed on 2026-07-10: one judgment, made once, carried in-band.
(`tests/test_no_second_judgment.py` enforces that this stays true.)

Once a turn is admitted, the send itself rides on the agent's judgment — the
same trust extended to any participant who has the floor.

## What it does

`nunchi_prompt_gate.py` is the single Claude Code hook. When a submitted prompt
contains a `<channel ...>` tag (the format used by Discord/channel transport
adapters), the hook:

1. Parses the channel tag: sender, chat ID, message body.
2. Parses the session transcript into a history window for that channel
   (inbound messages + agent self-sends).
3. Calls `nunchi-channel` with trigger + history + agent identity.
4. Emits one of the three decisions above.

Suppressing on a confident PASS costs one lightweight gate call instead of a
full frontier-model turn.

## What it does NOT do

- **Operator prompts** (no `<channel>` tag) always pass through instantly —
  zero gate calls, no receipt, no note. The operator is never gated.
- **No reply prose, ever.** Admission results carry no `message`/`reply`/
  `draft`/`content`; the in-band notes state admission facts (verdict, origin,
  hesitation) and explicitly leave the choice with the agent.
- **Transport bot-deafness** (the official Claude Code Discord plugin ignoring
  messages from other bots) is a separate, upstream concern. An
  operator-carried fix lives in [`transport-patch/`](transport-patch/README.md).

## Hook output contract

The hook always exits 0.

**Block** (confident PASS):
```json
{"decision": "block", "reason": "nunchi gate: PASS — <first reason>."}
```

**DEFER** (uncertain PASS) — the prompt goes through with the gate's hesitation
added to the turn's context:
```json
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "nunchi: the gate leaned PASS on this message but not confidently (confidences: {...}). It abstains rather than silence you. Read the room with your own judgment — replying and staying silent are both fine outcomes; if you stay silent, simply send nothing this turn."
  }
}
```

**Admit** (SPEAK / ACK / ASK) — the admission note travels with the turn:
```json
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "nunchi: admitted (SPEAK) — this turn answers message <id> from <author>. The gate judged only that a turn is open; what you say, and whether you say anything at all, is yours."
  }
}
```

**Operator prompt / any gate error**: no stdout; exit 0. The hook is
**permanently fail-open** — a broken gate must never silence the operator or
wedge the session.

## Historical V1 settings configuration (disabled)

One `UserPromptSubmit` entry (no matcher — the hook self-selects on the
`<channel>` tag). Prefer `nunchi-install`, which writes stable wrappers under
`~/.claude/hooks/` and prints this snippet:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/home/you/.claude/hooks/nunchi-user-prompt-submit.sh",
            "timeout": 35
          }
        ]
      }
    ]
  }
}
```

**Upgrading from the two-hook layout:** delete the old `PreToolUse` entry from
`settings.json` (exact file names in `docs/INSTALL.md`). `nunchi-install
upgrade` removes the retired hook files themselves (with backups) and
`nunchi-install verify` flags leftovers, but `settings.json` is operator-owned
— the installer never edits it.

**Note:** an active Claude Code session must be restarted for `settings.json`
changes to be picked up.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `NUNCHI_HOOK_AGENT_ID` | `agent` | Agent identifier in the nunchi payload. |
| `NUNCHI_HOOK_MENTION_ID` | _(unset)_ | Optional @mention handle. This is the **platform mention token** — on Discord the numeric snowflake — **not** the display name (a display name here makes the gate blind to real @-mentions; observed live 2026-07-08). Names belong in `NUNCHI_HOOK_ALIASES`. |
| `NUNCHI_HOOK_ALIASES` | _(unset)_ | Comma-separated additional identities this agent answers to → `agent.aliases`. |
| `NUNCHI_HOOK_PEER_BOTS` | _(empty)_ | Comma-separated usernames treated as `peer_bot` (all others `human`). |
| `NUNCHI_HOOK_HISTORY_WINDOW` | `25` | Max transcript events included as history (most recent N). Raise it for busy channels. |
| `NUNCHI_HOOK_TOOL_PATTERN` | `__reply$` | Regex identifying the agent's own outbound sends in the transcript (history only). |
| `NUNCHI_HOOK_TIMEOUT` | `30` | Timeout in seconds for the nunchi-channel subprocess. |
| `NUNCHI_HOOK_LOG` | `~/.claude/nunchi-gate-receipts.jsonl` | Per-call receipt log (JSONL). |
| `NUNCHI_CHANNEL_BIN` | `shutil.which("nunchi-channel")` | Path to the nunchi-channel binary. |
| `NUNCHI_DEFER` | _(on)_ | Kill switch. Set `off`/`0`/`false`/`no` to make every PASS block regardless of confidence. |
| `NUNCHI_DEFER_MARGIN` | `0.25` | A PASS is *uncertain* when the best alternative verdict is within this margin (inclusive). Values outside [0, 1] or non-finite fall back to the default. Placeholder pending calibration (see `DEFER_EVAL.md`). |

## Receipts log format

One JSON line per gate decision (telemetry only — receipts live outside the
conversation surface):

```json
{
  "ts": "2026-07-10T12:00:00+00:00",
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
- `block-pass` — confident PASS; prompt blocked before the LLM
- `defer-uncertain-pass` — uncertain PASS; gate abstained, turn handed to the
  agent's own judgment (these rows are the offline eval corpus — see
  `DEFER_EVAL.md`)
- `allow-<verdict>` — admitted (e.g. `allow-speak`)
- `allow-gate-error` — gate failed or returned a malformed directive; fail-open applied (always)
- `allow-envelope-error` — channel tag missing required attributes; passed through unjudged (no bound verdict exists to attach)

(`direction: inbound` is kept for continuity with logs written before the
send-time hook was retired.)

## Requirements

- Python 3.11+ stdlib only; no third-party dependencies.
- `nunchi-channel` binary installed (via `pip install nunchi` or pointing
  `NUNCHI_CHANNEL_BIN` at the module: `python3 -m nunchi.adapters.channel`).
- A configured classifier environment for `nunchi-channel`
  (`NUNCHI_CLASSIFIER_MODEL` + `OPENROUTER_API_KEY` or equivalent).

---

# transport-patch — hearing peer bots on the official Discord plugin

The hook gates what the session hears, but the official Claude Code Discord
plugin (`anthropics/claude-plugins-official`) drops every bot-authored message
before its own access control runs — peer agents are never delivered at all,
allowlisted or not (upstream issues #1153/#1559, open).

[`transport-patch/`](transport-patch/README.md) carries the operator-applied
patch (drop only self-messages; the plugin's existing `gate()`/`allowFrom`
access control remains the authorization layer), exact apply instructions,
and a live verification recipe for confirming a peer-bot message reaches the
session. Applying it is a local step on your own plugin checkout; the
upstream fix is pending.
