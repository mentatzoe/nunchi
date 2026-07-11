# Nunchi Adapter Reference

This document is the full adapter reference for Nunchi. It covers every
supported surface, how to install and configure each adapter, and how to wire a
custom responder.

## Adapter index

| Adapter | Surface | Install weight | Status |
|---|---|---|---|
| `nunchi-channel` | Any (subprocess / in-process) | stdlib | stable |
| `nunchi-matrix` | Matrix (unencrypted rooms) | stdlib | code-only |
| `nunchi-telegram` | Telegram | stdlib | code-only |
| `nunchi-discord` | Discord | source install, `[discord]` extra | code-only |
| Hermes plugin | Hermes gateway (Discord, Slack, …) | stdlib | live-run; evidence owed |
| Claude Code gate | Claude Code UserPromptSubmit (one judgment, at wake) | stdlib | offline-tested; live evidence incomplete |
| Codex runner + hooks + config app | Codex CLI via shared Discord-MCP transport | stdlib + `[mcp-discord]` for transport/app | bounded live-smokes evidenced |
| cc-connect preset | cc-connect (via `--format cc-connect`) | stdlib | stable |

Status labels in this table are evidence tiers, not the release-alpha/beta
validation gates. `code-only` means implementation exists in the repo, but no
committed live-server evidence supports a readiness claim yet. `offline-tested`
means the relevant repo tests pass; it is not a live-readiness claim. `bounded
live-smokes evidenced` means committed live-room runs support the narrow
wake/outbound and two-turn persistent-session claims; it is not a sustained
operations claim. The configuration app has offline MCP protocol and responsive
interaction evidence plus a live read of the resulting session health state.

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
| `NUNCHI_MATRIX_ALIASES` | no | *(none)* | Comma-separated additional identities this agent answers to (display names, nicknames, secondary handles, mention tokens) → `agent.aliases`. A mention token is the platform's structured id, **not** the display name — names go here. |
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
| `NUNCHI_TELEGRAM_ALIASES` | no | *(none)* | Comma-separated additional identities this agent answers to (display names, nicknames, secondary handles, mention tokens) → `agent.aliases`. A mention token is the platform's structured id, **not** the display name — names go here. |
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
| `NUNCHI_DISCORD_ALIASES` | no | *(none)* | Comma-separated additional identities this agent answers to (display names, nicknames, secondary handles, mention snowflakes) → `agent.aliases`. A Discord mention token is the numeric **snowflake**, not the display name — names go here. |
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

## Claude Code hooks

One hook under `integrations/claude-code/` — `nunchi_prompt_gate.py`, a
`UserPromptSubmit` hook — makes nunchi's single judgment for a Claude Code
session that participates in a chat channel, at wake time:

| Gate decision | Effect |
|---|---|
| PASS (confident) | prompt blocked before any LLM inference runs |
| PASS (uncertain) | DEFER — the gate abstains; the agent wakes with the hesitation noted and its own model decides (silence stays a fine outcome) |
| SPEAK / ACK / ASK | admitted; an in-band note anchors the turn to the message it answers |

The hook self-selects on the `<channel ...>` tag that channel transports put
in the prompt, builds a per-channel history window from the session
transcript, and calls `nunchi-channel`. A confident PASS suppresses the
prompt for the cost of one lightweight gate call instead of a full
frontier-model turn. Operator prompts (no channel tag) always pass through
ungated, and the path is permanently fail-open — a broken gate cannot silence
the operator.

There is deliberately no send-time re-judgment: an earlier `PreToolUse` hook
re-judged composed replies against the newest transcript line and produced
false PASSes when peer messages landed mid-composition. It was retired
2026-07-10 (`tests/test_no_second_judgment.py` keeps it retired); once a turn
is admitted, the send rides on the agent's own judgment.

**Known transport gap: the official Discord plugin is bot-deaf.** The upstream
Claude Code Discord plugin (`anthropics/claude-plugins-official`) drops every
bot-authored message before its own access control runs
(`if (msg.author.bot) return`), so peer-agent messages never reach the session
and the inbound hook never sees them (upstream issues #1153/#1559, open). An
operator-carried patch — a one-guard delta that drops only self-messages and
lets the plugin's existing `gate()`/`allowFrom` access control authorize peer
bots — ships with apply instructions and a live verification recipe at
[`integrations/claude-code/transport-patch/`](../integrations/claude-code/transport-patch/README.md).

**Status:** the wake gate is merged and has been exercised against live Discord
channel traffic. The transport patch is a local operator step applied to your
own plugin checkout — the upstream fix is still pending, so peer-hearing is
not available out of the box.

Full setup and configuration: [`integrations/claude-code/README.md`](../integrations/claude-code/README.md)

---

## Codex runner + hooks + config app

The Codex integration has four Codex-side pieces in
[`integrations/codex/`](../integrations/codex/README.md):

- `nunchi-codex-room-runner` consumes the shared Discord-MCP transport's SSE
  notifications without polling, runs `nunchi-channel`, and wakes Codex only
  for `ACK`/`ASK`/`SPEAK`. Its first admitted wake creates a dedicated Codex
  room task and later wakes resume the persisted task. `PASS` writes a receipt
  and does not wake Codex. Events are not injected into an unrelated open
  desktop task. For
  configured channels, it backfills gate history on transport startup through
  the transport's `read_history` MCP tool; hot-added and watch-all channels
  backfill immediately before their first observed live event. Discord
  mention/reply metadata is retained for admission, including referenced self
  messages that the self-dropping transport would otherwise omit from live
  history.
- `nunchi-codex-prompt-gate` is a defense-in-depth `UserPromptSubmit` hook
  for channel-tagged prompts in interactive Codex sessions. It blocks `PASS`
  and fail-opens for operator or malformed prompts.
- `nunchi-codex-send-gate` is a `PreToolUse` hook for supported outbound
  `send_message` / `reply_message` MCP calls. It re-checks Nunchi immediately
  before the send tool runs; `PASS` denies the tool call. Matching sends with
  malformed or missing current runner-provided Nunchi room context are denied,
  as are repeated or concurrent sends for one admitted context and allows
  whose durable receipt cannot be locked and written.
- `nunchi-codex-config-app` serves a task-embedded MCP Apps panel for atomic
  hot global/per-channel presence overrides, channel add/disable, model and
  pinned-rule changes, persistent-session health/reset, and newest-first
  receipts. The runner and the wake gate read the same state on each
  event/invocation. Codex does not currently
  expose a documented persistent third-party dashboard-tab slot, so this is
  functional operator parity in a different container from Hermes.
- The repo-installable Codex plugin bundle at
  [`integrations/codex/nunchi-codex/`](../integrations/codex/nunchi-codex/)
  packages those hooks, a local streamable-HTTP MCP config for the shared
  `nunchi-discord` transport, and the local stdio configuration app.

Status is **bounded live-smokes evidenced**: unit tests cover the
runner, inbound hook, outbound send hook, hot state, configuration app protocol,
package entry points, config loading, history backfill, and plugin bundle shape,
while
[`evidence/codex/2026-07-09-vigil-live-smoke.md`](../evidence/codex/2026-07-09-vigil-live-smoke.md)
records one live-room wake and outbound hook allow, and
[`evidence/codex/2026-07-09-vigil-persistent-session.md`](../evidence/codex/2026-07-09-vigil-persistent-session.md)
records two admitted wakes on the same persisted Codex task plus one delivered
response. These remain bounded smokes, not sustained-operations evidence.
Sustained participation still requires the shared `nunchi-mcp-discord`
transport, credentials, installed/trusted Codex plugin hooks, and long-running
room runner.

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
