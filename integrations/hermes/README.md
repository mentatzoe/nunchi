# Hermes Integration: nunchi-gate

`nunchi-gate` is a [Hermes](https://github.com/example/hermes) gateway plugin
that runs every incoming channel message through the `nunchi-channel` CLI and
suppresses the agent reply when nunchi returns a `PASS` verdict (stay silent).
Verdicts `ACK`, `ASK`, and `SPEAK` allow the normal Hermes dispatch path to
continue.

---

## Host prerequisites

> **These must be satisfied before enabling the plugin.  The gate silently
> falls open (or closed, per `fail_open`) if they are not.**

### (a) `DISCORD_ALLOW_BOTS` in `~/.hermes/.env`

This environment variable controls two separate behaviours:

| Value | Effect |
|-------|--------|
| `none` (default) | Hermes drops peer-bot messages before they reach any plugin; the gate never sees peer traffic.  History backfill also excludes other bots' messages. |
| `mentions` | Peer-bot messages that @-mention the agent are forwarded to plugins and included in history backfill. |
| `all` | All peer-bot messages are forwarded and included in history backfill. |

Set `DISCORD_ALLOW_BOTS=mentions` or `DISCORD_ALLOW_BOTS=all` in
`~/.hermes/.env` if you want the gate to see and evaluate bot-originated
messages.

### (b) Discord bot permissions

The bot account requires the **Read Message History** permission in each
channel where history backfill is expected to work.  Without it,
`event.channel_context` will be empty and the gate will operate without
conversation history (verdict quality degrades).

### (c) Classifier API credentials

`nunchi-channel` calls an LLM classifier.  The following must be available —
either in the system environment or in `~/.hermes/.env` — unless the `model`
config key is set and the key is already exported:

| Variable | Required |
|----------|----------|
| `NUNCHI_CLASSIFIER_MODEL` | Yes (can be set via `model:` in config instead) |
| `OPENROUTER_API_KEY` or `NUNCHI_CLASSIFIER_API_KEY` | Yes |
| `NUNCHI_CLASSIFIER_BASE_URL` | No — defaults to OpenRouter |

---

## Install

Install by symlinking the plugin directory into Hermes' plugin search path.
From the repository root:

```sh
ln -s "$(pwd)/integrations/hermes/nunchi-gate" ~/.hermes/plugins/nunchi-gate
```

Then enable the plugin in `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - nunchi-gate
```

Restart (or reload) Hermes for the change to take effect.

---

## Configuration reference

All keys live under the `nunchi:` block in `~/.hermes/config.yaml`.

```yaml
nunchi:
  enabled: false            # (bool, default false) — set true to activate
  platforms: discord        # see below
  channels: ""              # see below — REQUIRED unless "*"
  agent_id: agent           # see below — operators MUST override this
  # mention_id: ""
  # binary: ""
  # model: ""
  # pinned_rules_file: ""
  timeout_seconds: 30
  fail_open: true
  bypass_commands: true
  log_path: ~/.hermes/logs/nunchi-gate.jsonl
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `false` | Gate is inactive unless explicitly set to `true`. |
| `platforms` | str or list | `"discord"` | Platform name(s) to gate.  Use `"*"` to gate all platforms regardless of name.  Comma-separated string or YAML list are both accepted. |
| `channels` | str or list | *(none)* | Chat / channel IDs to gate.  **Required unless `"*"`.** Without at least one channel ID (or `"*"`), the gate is a no-op for every event.  Comma-separated string or YAML list are both accepted. |
| `agent_id` | str | `"agent"` | The bot's display name as it appears in `[Name [bot]]` history lines.  **Operators must set this to the bot's actual display name** — the default `"agent"` is intentionally generic and will produce incorrect self/peer classification. |
| `mention_id` | str | *(absent)* | Discord mention snowflake (e.g. `"1496355876234199040"`).  Included in the payload so the classifier can detect direct @-mentions.  Omit if not needed. |
| `binary` | str | auto-detected | Path to the `nunchi-channel` executable.  Defaults to `shutil.which("nunchi-channel")` falling back to `/usr/local/bin/nunchi-channel`. |
| `model` | str | *(absent)* | When set, `NUNCHI_CLASSIFIER_MODEL=<model>` is exported into the subprocess environment, overriding any inherited value.  Useful for selecting a non-default classifier model without touching the system environment. |
| `pinned_rules_file` | str (path) | *(absent)* | Path to a text file whose contents are passed as `"pinned_rules"` in every payload.  The file is read lazily and cached by mtime, so edits take effect without restarting Hermes.  Tilde expansion is applied.  Ignored if the file is missing. |
| `timeout_seconds` | number | `30` | Subprocess timeout in seconds.  Values below 1 are clamped to 1. |
| `fail_open` | bool | `true` | When `true`, any classifier error allows the Hermes reply through.  Set to `false` for strict gating (errors suppress the reply). |
| `bypass_commands` | bool | `true` | When `true`, messages whose text starts with `/` bypass the gate entirely. |
| `log_path` | str (path) | `~/.hermes/logs/nunchi-gate.jsonl` | Append-only JSONL file recording every gated message.  Set to `""`, `"false"`, `"none"`, or `"off"` to disable logging. |

### Legacy config block

If `nunchi:` is absent but `turnaware:` is present, the plugin falls back to
reading `turnaware:` and emits a deprecation warning.  Rename the block to
migrate:

```yaml
# Before (deprecated)
turnaware:
  enabled: true
  ...

# After
nunchi:
  enabled: true
  ...
```

---

## Log format

One JSON object per line, appended to `log_path`.  Fields:

| Field | Type | Description |
|-------|------|-------------|
| `ts` | float | Unix timestamp of gate entry |
| `platform` | str | Platform name (e.g. `"discord"`) |
| `channel_ids` | list[str] | Sorted list of channel IDs from the event source |
| `message_id` | str\|null | Incoming message ID |
| `payload_keys` | list[str] | Top-level keys sent to nunchi-channel |
| `history_len` | int | Number of history entries included in the payload |
| `trigger_author` | str\|null | Author field extracted from the event |
| `trigger_author_kind` | str\|null | `"human"`, `"peer_bot"`, or absent |
| `elapsed_ms` | int | Time from gate entry to verdict, in milliseconds |
| `verdict` | str | Raw verdict string (`PASS`, `ACK`, `ASK`, `SPEAK`) |
| `silent` | bool\|null | The `silent` field from the nunchi-channel directive |
| `classifier_model` | str\|null | Model identifier reported by nunchi-channel |
| `reasons` | list[str] | Up to 3 reason strings from the classifier |
| `action` | str | `"skip"` (reply suppressed) or `"allow"` (reply proceeds) |
| `error` | str | *(error entries only)* Exception message (truncated to 500 chars) |
| `fail_open` | bool | *(error entries only)* The `fail_open` value at error time |

Example entry:

```json
{
  "action": "skip",
  "channel_ids": ["1518384310321811456"],
  "classifier_model": "google/gemini-flash-lite",
  "elapsed_ms": 412,
  "history_len": 4,
  "message_id": "1234567890123456789",
  "payload_keys": ["agent", "history", "trigger"],
  "platform": "discord",
  "reasons": ["No direct address", "Topic already resolved"],
  "silent": true,
  "trigger_author": "zoe",
  "trigger_author_kind": "human",
  "ts": 1751234567.123,
  "verdict": "PASS"
}
```
