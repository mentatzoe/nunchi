# Nunchi Adapter Reference

This document is the full adapter reference for Nunchi. It covers every
supported surface, how to install and configure each adapter, and how to wire a
custom responder.

## Adapter index

| Adapter | Surface | Install weight | Status |
|---|---|---|---|
| `nunchi-channel` | Any (subprocess / in-process) | stdlib | stable |
| `nunchi-matrix` | Matrix (unencrypted rooms) | stdlib | beta\* |
| `nunchi-telegram` | Telegram | stdlib | beta\* |
| `nunchi-discord` | Discord | source install, `[discord]` extra | beta\* |
| Hermes plugin | Hermes gateway (Discord, Slack, …) | stdlib | beta |
| Claude Code hook | Claude Code PreToolUse | stdlib | beta |
| cc-connect preset | cc-connect (via `--format cc-connect`) | stdlib | stable |

\* *beta* for the Matrix, Telegram, and Discord adapters means: full offline
test coverage, but they have **not yet been run against a live
Matrix/Telegram/Discord server**. Expect first-run rough edges and please
report them.

The platform adapters (`nunchi-matrix`, `nunchi-telegram`, `nunchi-discord`)
landed after the published 0.2.0 PyPI release and are currently installable
from source only (see each adapter's install section below).

---

## nunchi-channel CLI

`nunchi-channel` is the transport-neutral CLI/subprocess adapter. It reads a
JSON payload (trigger, history, agent, optional pinned_rules and fail_policy)
from stdin or `--input` and writes a transport-neutral JSON directive to stdout:

```sh
echo '{"trigger":{"content":"vigil, rebase the branch","message_id":"m-1"},
       "history":[],"agent":{"id":"dalgos"},"fail_policy":"open"}' \
  | python3 -m nunchi.adapters
```

See `docs/integration.md` for the full in-process and subprocess integration
guide, including the cc-connect preset (`--format cc-connect`).

---

## Matrix adapter (reference)

`nunchi.adapters.matrix` is a reference integration that joins Matrix rooms as a
gated participant. One command, zero extra dependencies.

### One-command quickstart

```sh
pip install "git+https://github.com/mentatzoe/nunchi.git"

export NUNCHI_MATRIX_HOMESERVER="https://matrix.example.com"
export NUNCHI_MATRIX_TOKEN="<your-access-token>"
export NUNCHI_MATRIX_ROOMS="!room1:example.com,!room2:example.com"
export NUNCHI_CLASSIFIER_MODEL="openai/gpt-4o-mini"
export OPENROUTER_API_KEY="<your-key>"

nunchi-matrix
```

Use `--dry-run` to gate without sending, or `--once` to process one sync batch
and exit (useful for cron or testing).

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `NUNCHI_MATRIX_TOKEN` | yes | — | Matrix access token |
| `NUNCHI_MATRIX_HOMESERVER` | yes | — | Base URL of your homeserver |
| `NUNCHI_MATRIX_ROOMS` | yes | — | Comma-separated room IDs to watch |
| `NUNCHI_CLASSIFIER_MODEL` | yes | — | Model for the admission gate |
| `OPENROUTER_API_KEY` | yes | — | API key (gate + demo responder) |
| `NUNCHI_MATRIX_STATE` | no | `~/.nunchi/matrix-sync.json` | Since-token persistence |
| `NUNCHI_MATRIX_LOG` | no | `~/.nunchi/matrix-gate.jsonl` | JSONL receipt log |
| `NUNCHI_MATRIX_AGENT_ID` | no | `bot_<localpart>` | Agent identity label |
| `NUNCHI_MATRIX_PEER_BOTS` | no | `` | Comma-separated user IDs (or `@prefix*` globs) treated as `peer_bot` |
| `NUNCHI_MATRIX_HISTORY` | no | `20` | Recent messages fed to the gate as context |
| `NUNCHI_RESPONDER_MODEL` | no | `NUNCHI_CLASSIFIER_MODEL` | LLM for the built-in demo responder |
| `NUNCHI_CLASSIFIER_BASE_URL` | no | OpenRouter | OpenAI-compatible API base URL |

### Obtaining a Matrix access token

```sh
curl -XPOST 'https://YOUR_HOMESERVER/_matrix/client/v3/login' \
     -H 'Content-Type: application/json' \
     -d '{"type":"m.login.password",
          "identifier":{"type":"m.id.user","user":"@BOTUSER:HOMESERVER"},
          "password":"SECRET"}'
# Response includes "access_token"; export it as NUNCHI_MATRIX_TOKEN.
```

Or from Python:

```python
from nunchi.adapters.matrix import login
token = login("https://matrix.example.com", "@bot:example.com", "secret")
```

### Bridge note

One adapter covers Discord, Slack, Microsoft Teams, Telegram, and IRC via the
[Matrix bridge ecosystem](https://matrix.org/ecosystem/bridges/). Deploy
nunchi-matrix on your homeserver; the bridges handle protocol translation.

### Limitation: unencrypted rooms only

`nunchi-matrix` uses the Matrix Client-Server API directly without an E2EE
library. Rooms that use `m.room.encrypted` are detected and skipped with a
one-time warning per room. Use an unencrypted Matrix room or a bridge endpoint
that decrypts before delivering.

### Responder callback contract

The built-in demo responder is clearly labelled a demo — the adapter's product
is the gating loop. To wire a real agent, pass a callable:

```python
from nunchi.adapters.matrix import MatrixSyncLoop

def my_responder(trigger: dict, history: list[dict], gate_result) -> str | None:
    """
    trigger  — dict with content/author/author_kind/message_id/timestamp
    history  — list of the same shape, oldest first
    gate_result — ChannelGateResult (verdict/silent/run_shape/reasons/confidences)

    Return a string to post, or None to post nothing (receipt: responder-declined).
    """
    return f"[{gate_result.verdict}] I would respond here."

loop = MatrixSyncLoop(
    homeserver="https://matrix.example.com",
    token="tok_...",
    room_ids=["!room:example.com"],
    agent_id="my-agent",
    own_user_id="@my-agent:example.com",
    peer_bot_specs=["@other-bot:example.com"],
    history_len=10,
    state_path=...,
    log_path=...,
    responder=my_responder,
)
loop.run()
```

### Open Floor Protocol alignment

Nunchi verdicts map onto Open Floor Protocol floor semantics:

- `SPEAK` — taking the floor (producing a substantive participant turn)
- `PASS` — yielding the floor (posting nothing for this turn)
- `ACK` — brief acknowledgement without claiming the floor
- `ASK` — requesting clarification before proceeding

The adapter uses these names explicitly so future OFP compatibility is
vocabulary-aligned: a transport that implements OFP can map `gate_result.verdict`
to OFP floor-request/yield primitives without a translation layer.

---

## Telegram adapter

`nunchi.adapters.telegram` joins Telegram chats as a gated participant using the
Telegram Bot HTTP API over stdlib `urllib` (zero extra dependencies).

### Quickstart

1. **Create a bot**: message [@BotFather](https://t.me/BotFather) on Telegram,
   send `/newbot`, follow the prompts, and copy the token.

2. **Get the chat ID** of each group or DM you want the bot to watch. Add the
   bot to the group, then retrieve the chat ID with:
   ```sh
   curl "https://api.telegram.org/bot<TOKEN>/getUpdates"
   # Look for "chat":{"id":...} in the result
   ```

3. **Run**:

```sh
pip install "git+https://github.com/mentatzoe/nunchi.git"

export NUNCHI_TELEGRAM_TOKEN="<bot-token>"
export NUNCHI_TELEGRAM_CHATS="-1001234567890,-1009876543210"
export NUNCHI_CLASSIFIER_MODEL="openai/gpt-4o-mini"
export OPENROUTER_API_KEY="<your-key>"

nunchi-telegram
```

Use `--dry-run` to gate without sending, or `--once` to process one
`getUpdates` batch and exit.

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `NUNCHI_TELEGRAM_TOKEN` | yes | — | Bot token from BotFather |
| `NUNCHI_TELEGRAM_CHATS` | yes | — | Comma-separated chat IDs (integers; negative for groups) |
| `NUNCHI_CLASSIFIER_MODEL` | yes | — | Model for the admission gate |
| `OPENROUTER_API_KEY` | yes | — | API key (gate + demo responder) |
| `NUNCHI_TELEGRAM_STATE` | no | `~/.nunchi/telegram-sync.json` | Offset persistence |
| `NUNCHI_TELEGRAM_LOG` | no | `~/.nunchi/telegram-gate.jsonl` | JSONL receipt log |
| `NUNCHI_TELEGRAM_AGENT_ID` | no | `bot_<username>` | Agent identity label |
| `NUNCHI_TELEGRAM_HISTORY` | no | `20` | Recent messages fed to the gate |
| `NUNCHI_RESPONDER_MODEL` | no | `NUNCHI_CLASSIFIER_MODEL` | LLM for the demo responder |
| `NUNCHI_CLASSIFIER_BASE_URL` | no | OpenRouter | OpenAI-compatible API base URL |

### Author-kind mapping

| Sender | author_kind |
|---|---|
| Own bot | `self` — recorded in history but not gated |
| Any bot (`is_bot=true`) | `peer_bot` |
| Human user | `human` |

### Notes

- Text messages only; media, stickers, and polls are ignored.
- Rate-limit (HTTP 429) handling honours the `retry_after` field in Telegram's
  JSON response body before falling back to the `Retry-After` HTTP header.
- Permanent errors (4xx other than 429) abort immediately without retrying.

---

## Discord adapter

`nunchi.adapters.discord` joins Discord channels as a gated participant via
discord.py's event-driven client. This is an **optional extra** — discord.py is
not a default dependency.

### Install

The `[discord]` extra is not yet installable from PyPI — the published 0.2.0
release predates this adapter. Install from source:

```sh
pip install "nunchi[discord] @ git+https://github.com/mentatzoe/nunchi.git"
# or, from a checkout:
pip install ".[discord]"
```

### Quickstart

1. **Create an application** at the [Discord Developer Portal](https://discord.com/developers/applications).
2. Navigate to **Bot**, enable the **Message Content Intent** (required for
   reading message text).
3. Copy the bot token.
4. Generate an invite URL: **OAuth2 → URL Generator**. Required scopes: `bot`.
   Required bot permissions: `Read Messages/View Channels`, `Send Messages`,
   `Read Message History`.
5. Invite the bot to your server using the generated URL.
6. Get the channel IDs (enable **Developer Mode** in Discord settings → right-click
   a channel → **Copy Channel ID**).

```sh
export NUNCHI_DISCORD_TOKEN="<bot-token>"
export NUNCHI_DISCORD_CHANNELS="1234567890123456789,9876543210987654321"
export NUNCHI_CLASSIFIER_MODEL="openai/gpt-4o-mini"
export OPENROUTER_API_KEY="<your-key>"

nunchi-discord
```

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `NUNCHI_DISCORD_TOKEN` | yes | — | Bot token from the Developer Portal |
| `NUNCHI_DISCORD_CHANNELS` | yes | — | Comma-separated channel IDs to watch |
| `NUNCHI_CLASSIFIER_MODEL` | yes | — | Model for the admission gate |
| `OPENROUTER_API_KEY` | yes | — | API key (gate + demo responder) |
| `NUNCHI_DISCORD_PEER_BOTS` | no | `` | Comma-separated bot user IDs treated as gated peers |
| `NUNCHI_DISCORD_BOT_POLICY` | no | `all` | `all` — gate all bots; `allowlist` — gate only bots in `NUNCHI_DISCORD_PEER_BOTS` |
| `NUNCHI_DISCORD_MAX_EVENTS` | no | *(unlimited)* | Stop after N gated events (useful for bounded integration tests) |
| `NUNCHI_DISCORD_LOG` | no | `~/.nunchi/discord-gate.jsonl` | JSONL receipt log |
| `NUNCHI_DISCORD_AGENT_ID` | no | `bot_<username>` | Agent identity label |
| `NUNCHI_DISCORD_HISTORY` | no | `20` | Recent messages per channel for context |
| `NUNCHI_RESPONDER_MODEL` | no | `NUNCHI_CLASSIFIER_MODEL` | LLM for the demo responder |
| `NUNCHI_CLASSIFIER_BASE_URL` | no | OpenRouter | OpenAI-compatible API base URL |

### Bot policy

Unlike standard Discord bots that ignore all bot-authored messages, this
adapter can intentionally process bot messages as peer participants:

- `NUNCHI_DISCORD_BOT_POLICY=all` (default): all bot messages except own are
  processed with `author_kind=peer_bot`.
- `NUNCHI_DISCORD_BOT_POLICY=allowlist`: only bots whose user IDs appear in
  `NUNCHI_DISCORD_PEER_BOTS` are processed; all other bots are silently ignored.

The bot always skips its own messages (they are recorded in the channel history
but not gated).

### Notes

- Initial history is backfilled via `channel.history(limit=10)` on the first
  event per channel.
- discord.py is event-driven — there is no `--once` flag. Use
  `NUNCHI_DISCORD_MAX_EVENTS=N` for bounded test runs.
- The built-in demo responder uses synchronous `urllib` calls inside an async
  event handler, which briefly blocks the event loop. For production, supply
  your own async-compatible responder via the `NunchiDiscordClient` class.

---

## Hermes plugin (nunchi-gate)

The `nunchi-gate` Hermes plugin runs every incoming channel message through the
`nunchi-channel` CLI and suppresses the agent reply when nunchi returns a `PASS`
verdict.

Full setup and configuration: [`integrations/hermes/README.md`](../integrations/hermes/README.md)

---

## Claude Code hook

`nunchi_gate_hook.py` is a Claude Code **PreToolUse hook** that gates outbound
channel sends through the nunchi admission classifier before they reach the tool
layer.

Full setup and configuration: [`integrations/claude-code/README.md`](../integrations/claude-code/README.md)

---

## cc-connect preset

The `nunchi-channel` CLI includes a cc-connect preset that emits the
`CC_CONNECT_SILENT_PASS` sentinel on PASS:

```sh
echo '...' | nunchi-channel --format cc-connect
```

This is equivalent to `--silent-token CC_CONNECT_SILENT_PASS`. Any transport
can use `--silent-token <your-sentinel>` to hook into its own suppression
mechanism without any special status for cc-connect.
