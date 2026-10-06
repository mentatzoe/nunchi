# Run the Claude Code participant live

This is the procedure for the first live run of the Claude Code gate and mod
in a real Discord room ([#39](https://github.com/mentatzoe/nunchi/issues/39)).
It assumes a Discord bot token, a logged-in Claude Code, an attention-model
endpoint, and a room. A clean run does not by itself make the status
**verified**; see [Filing the result](#filing-the-result).

How the integration works is in
[`integrations/claude-code/README.md`](../integrations/claude-code/README.md).

## What has never run against anything real

Watch these first; a first live run most likely fails here.

1. **A real model turn through the mod.** The real Claude Code CLI has been
   checked to load the mod in a headless stream-json session and attach to
   the gate socket before any prompt. Every turn after that has run only
   against a stub `claude` that speaks the same protocol.
2. **The stream-json turn protocol.** The gate writes a user message per wake,
   reads `result` messages as turn ends, and sends an `interrupt` control
   request on cancellation. These shapes come from the CLI's documented SDK
   protocol, not from a recorded live session.
3. **The runner's startup loop** against a real `nunchi-mcp-discord`.
4. **Your permission rules in a headless session.** A native tool that would
   ask for permission is denied there.

## 1. Claude Code

Install Claude Code 2.1.287 or later and log in as the OS user that will run
the gate. The dedicated session uses that user's normal Claude Code
configuration and login.

```sh
claude --version
claude auth status
```

Decide the session's working directory. Its `CLAUDE.md` and project settings
apply to the agent. Allow, in your Claude Code settings, the native tools the
agent should be able to use without a prompt.

## 2. Install the candidate

The wheel is the subject. A source checkout on `PYTHONPATH` is not evidence.

```sh
python3 -m build
python3 -m venv /tmp/nunchi-live
/tmp/nunchi-live/bin/python -m pip install --no-deps dist/nunchi-2.0.0-py3-none-any.whl
/tmp/nunchi-live/bin/python -m pip install 'mcp>=1.9,<2'
/tmp/nunchi-live/bin/nunchi probe
/tmp/nunchi-live/bin/nunchi-claude-code-room-runner --probe
```

Record `git rev-parse HEAD:src` as the candidate identity. The unconfigured
probe must print `"configured": false`, `"v1_fallback": false`, and the mod
version, and exit 0.

## 3. Discord identity and transport

The participant needs its own bot account. Enable the **message content** and
**server members** privileged intents, then invite it.

```sh
export NUNCHI_DISCORD_TOKEN=...
export NUNCHI_DISCORD_PARTICIPANT_ROUTES='{"vigil":["<channel id>"]}'
export NUNCHI_DISCORD_OUTPUT_HMAC_KEY=...             # >= 32 bytes
export NUNCHI_DISCORD_STATE_DIRECTORY=/srv/nunchi/discord-state   # 0700
/tmp/nunchi-live/bin/nunchi-mcp-discord
```

It listens on `http://127.0.0.1:3993/mcp` unless `NUNCHI_MCP_DISCORD_HOST` or
`NUNCHI_MCP_DISCORD_PORT` say otherwise. The routes key must equal
`participant_id`, and its channel id must equal `binding.room_id`.

The gate needs the same HMAC key under the name in `transport.output_key_env`.
The gate keeps that variable, and every `NUNCHI_*` variable, out of the
session's environment.

## 4. Profile and pinned configuration

Profile, exactly these five non-empty string fields:

```json
{
  "profile_id": "vigil-live-1",
  "participant_id": "vigil",
  "actor_id": "discord:actor:<bot user id>",
  "instructions": "You are Vigil...",
  "provenance": "trusted:operator/live-1"
}
```

Configuration:

```json
{
  "schema_version": 2,
  "binding": {
    "participant_id": "vigil",
    "actor_id": "discord:actor:<bot user id>",
    "platform": "discord",
    "room_id": "<channel id>",
    "continuity_scope_id": "discord:channel:<channel id>"
  },
  "profile": { "path": "/srv/nunchi/profile.json", "sha256": "<64 hex>" },
  "attention": {
    "policy": { "preattention_enabled": true },
    "model": {
      "kind": "openai-compatible",
      "base_url": "https://llm.example/v1",
      "model": "<attention model>",
      "api_key_env": "NUNCHI_ATTENTION_API_KEY"
    }
  },
  "limits": {},
  "state_directory": "/srv/nunchi/claude-code-state",
  "transport": {
    "url": "http://127.0.0.1:3993/mcp",
    "timeout_seconds": 30,
    "output_key_env": "NUNCHI_DISCORD_OUTPUT_KEY"
  },
  "claude_code": {
    "working_directory": "/srv/nunchi/vigil-workspace",
    "session_mode": "persistent",
    "timeout_seconds": 180
  }
}
```

The `claude_code` fields are listed in the integration README. Pin the bytes
with `--config-sha256` (or `NUNCHI_CLAUDE_CODE_CONFIG_SHA256`) and check the
configured probe. It must show `"claude_code_supported": true`, the
`mod_version`, the three room tools, and the deny rules for the state
directory.

## 5. Run

```sh
/tmp/nunchi-live/bin/nunchi-claude-code-room-runner \
  --config /srv/nunchi/config.json --config-sha256 <64 hex>
```

The gate registers with the transport and opens its socket. The Claude Code
session starts on the first wake. `Claude Code shared transport reconnect
after operational error` on stderr is the reconnect loop; each reconnect
declares a continuity gap and cancels in-flight work.

## 6. Scenes to capture

After each scene, capture the new lines of
`<state_directory>/claude-code-v2-receipts.jsonl` and the Discord message or
its absence. Receipt stages run `observation` → `attention` →
`participant-host` → `transport`.

| # | Scene | Trigger | Expect |
|---|---|---|---|
| 1 | SUPPRESS | ambient chatter not for the participant | attention `SUPPRESS`; no session turn; no message |
| 2 | WAKE, contribution | address it directly, within its brief | `room_send` called once; `transport` `sent`; a real message |
| 3 | WAKE, silence | an open moment not worth speaking into | a session turn; `participant-host` `silent`; **no** transport stage |
| 4 | reaction | a message better answered with a reaction | `room_react`; `transport` `sent` |
| 5 | ACK | a moment that only needs acknowledgement | ACK widens to DEFER by default: a session turn whose reading says a nod could fit; `room_react` if the agent nods |
| 6 | more context | a question about something said earlier | `room_context` before acting; the action names a fetched event |
| 7 | cancellation | restart the transport mid-turn | `interrupt` reaches the session; no late post |
| 7a | steering | while it works on a request that needs a tool (a file read, say), post another question to it | its next tool result carries the room update; it answers both or says why not; no second session turn is needed |
| 8 | restart | stop the gate, restart, follow up | the session resumes (`--resume`); a continuity gap is recorded first |
| 9 | secret refusal | ask it to post a value from `withhold_env` | the tool call is refused; nothing posted |
| 10 | privileged action | configure `authorization`, request a file write | journal entry; executor `sent` with digest; file inside the root |

Scene 3 matters most. Waking and then choosing silence is what separates this
from a bot that answers everything. Confirm that the transport stage is
absent, not merely that no message appeared.

Record for each scene:

- the receipt lines, verbatim;
- for anything delivered, the native Discord message id, and that it comes
  from the participant's own bot in the configured room;
- the wall-clock time;
- the installed identity and Claude Code version;
- the exact command line with configuration and profile digests.

## Failure modes

| Symptom | Meaning |
|---|---|
| `Claude Code 2.1.287 or later is required` | upgrade Claude Code, or set `claude_code.executable` |
| `the Nunchi mod did not bind this Claude Code turn; the mod never attached` | the mod did not load: mods disabled by policy, or the session was started with `--bare`, `--safe-mode` or `--tools ""` |
| `Claude Code exited ...` | the session died; its stderr tail follows. The next wake starts it again |
| a native tool is denied | your permission rules ask for that tool, and nobody can answer in a headless session |
| `output authorization key is absent or short in X` | `X` unset or under 32 bytes in the gate's environment |
| `profile and exact transport self differ` | profile identity does not match the binding |
| `authenticated Discord self differs from exact binding` | the token's actor is not `binding.actor_id` |
| transport result `unknown` | the acknowledgement was empty, stale, cross-bot, wrong-content, or malformed |

Uncertainty never becomes success. When `unknown` appears where `sent` was
expected, check what the acknowledgement said.

## Filing the result

Save the records under `evidence/v2/claude-code/` with the date, and update
[#39](https://github.com/mentatzoe/nunchi/issues/39). One clean run shows the
lifecycle plumbing, identity, authority, cancellation, receipts, and native
transport facts working together. It does not measure social quality; that is
behavioral evaluation ([#86](https://github.com/mentatzoe/nunchi/issues/86)).

Two rules:

1. Never accept a script's own success output as verification. Read the
   artifact back from git or from the installed location.
2. Measure recorded figures from a clean `git archive` of the committed head,
   not from a working tree mid-edit.
