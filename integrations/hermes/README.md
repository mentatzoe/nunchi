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

> **Per-channel bot policy note:** if you use `senders: humans` or
> `senders: allowlist` *per channel* to restrict which senders are gated at
> the plugin level, you must still set `DISCORD_ALLOW_BOTS=all` globally so
> that bot messages reach the plugin at all.  The plugin then applies its own
> sender policy as a second filter.  Running `DISCORD_ALLOW_BOTS=all` globally
> and re-restricting per channel in the plugin is the sanctioned layering
> ("shim, not hack") — see [Sender policy](#sender-policy) below.

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
  # senders: all
  # allow_from: []
  # verbosity: normal
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
| `channels` | str, list, or map | *(none)* | Chat / channel IDs to gate.  See [Per-channel configuration](#per-channel-configuration) for the map form.  **Required unless `"*"`.** Without at least one channel ID (or `"*"`), the gate is a no-op for every event. |
| `agent_id` | str | `"agent"` | The bot's display name as it appears in `[Name [bot]]` history lines.  **Operators must set this to the bot's actual display name** — the default `"agent"` is intentionally generic and will produce incorrect self/peer classification. |
| `mention_id` | str | *(absent)* | Discord mention snowflake (e.g. `"1496355876234199040"`).  Included in the payload so the classifier can detect direct @-mentions.  Omit if not needed. |
| `binary` | str | auto-detected | Path to the `nunchi-channel` executable.  Defaults to `shutil.which("nunchi-channel")` falling back to `/usr/local/bin/nunchi-channel`. |
| `model` | str | *(absent)* | When set, `NUNCHI_CLASSIFIER_MODEL=<model>` is exported into the subprocess environment, overriding any inherited value.  Can be overridden per channel in the map form. |
| `senders` | str | `"all"` | Sender policy.  See [Sender policy](#sender-policy). |
| `allow_from` | list or CSV | *(absent)* | Required when `senders: allowlist`.  Values are matched case-insensitively against `user_name` and literally against `user_id`.  Can be overridden per channel in the map form. |
| `verbosity` | str | `"normal"` | Controls which fields appear in the gate log.  See [Verbosity levels](#verbosity-levels).  Can be overridden per channel in the map form. |
| `pinned_rules_file` | str (path) | *(absent)* | Path to a text file whose contents are passed as `"pinned_rules"` in every payload.  The file is read lazily and cached by mtime, so edits take effect without restarting Hermes.  Tilde expansion is applied.  Ignored if the file is missing.  Can be overridden per channel in the map form. |
| `timeout_seconds` | number | `30` | Subprocess timeout in seconds.  Values below 1 are clamped to 1. |
| `fail_open` | bool | `true` | When `true`, any classifier error allows the Hermes reply through.  Set to `false` for strict gating.  Can be overridden per channel in the map form. |
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

## Per-channel configuration

The `channels` key accepts three forms:

**Legacy CSV string** (unchanged from v1):
```yaml
channels: "1518384310321811456,2222222222222222222"
```

**Legacy YAML list** (unchanged from v1):
```yaml
channels:
  - "1518384310321811456"
  - "2222222222222222222"
```

Both legacy forms gate all listed channels using the global config defaults.

**Map form** (new): a dict mapping channel IDs to per-channel config overrides.

```yaml
channels:
  "1518384310321811456":
    senders: all
    verbosity: debug
    model: anthropic/claude-opus-4-5
  "9999999999999999999":
    senders: allowlist
    allow_from:
      - alice
      - "99"
    verbosity: normal
    fail_open: false
  "*":
    # wildcard — matches any channel not listed above
    verbosity: minimal
```

Per-channel keys that can be overridden in the map form:

| Key | Fallback |
|-----|---------|
| `enabled` | `true` for any listed channel |
| `senders` | global `senders` (default `"all"`) |
| `allow_from` | global `allow_from` |
| `verbosity` | global `verbosity` (default `"normal"`) |
| `model` | global `model` |
| `pinned_rules` | global `pinned_rules` |
| `pinned_rules_file` | global `pinned_rules_file` |
| `fail_open` | global `fail_open` (default `true`) |

All other keys (`binary`, `timeout_seconds`, `bypass_commands`, `log_path`,
`agent_id`, `mention_id`, `platforms`) are global-only and apply uniformly
across all channels.

**Matching precedence:** when the event carries multiple channel IDs
(`chat_id`, `parent_chat_id`, `thread_id`), the first exact match in the map
wins.  If no exact match is found, a `"*"` key is used as a wildcard.  If
neither matches, the event is not gated for that channel.

**`enabled: false`** in a per-channel entry opts the channel out of gating
entirely; no classifier call is made.

---

## Sender policy

The `senders` key controls which message senders reach the classifier.

| Value | Behaviour |
|-------|-----------|
| `all` (default) | Every message is gated and dispatched to the classifier — current behaviour, unchanged. |
| `humans` | Bot-authored messages (`is_bot: true`) are dropped without a classifier call.  A receipt entry with `action: "skip-sender-policy"` is written to the log. |
| `allowlist` | Only senders whose `user_name` (case-insensitive) or `user_id` (exact) appear in `allow_from` are gated and dispatched.  All other senders are dropped with `action: "skip-sender-policy"`. |

A sender-policy drop returns `{"action": "skip", "reason": "nunchi:sender-policy"}` to Hermes and writes a receipt log entry.  The `elapsed_ms` reflects wall-clock time to the drop decision, not a classifier round-trip.  No subprocess is ever spawned for a dropped message.

### Layering rationale

Hermes' `DISCORD_ALLOW_BOTS` environment variable is a coarse global gate: it
decides whether bot messages are forwarded to plugins at all.  The `senders`
key in nunchi-gate is a fine-grained, per-channel second filter applied after
Hermes has already delivered the message.

The recommended layering is:

1. Set `DISCORD_ALLOW_BOTS=all` in `~/.hermes/.env` (Hermes level) so every
   message reaches every plugin.
2. Use `senders: humans` or `senders: allowlist` per channel in the
   nunchi-gate config (plugin level) to restrict which senders get classified.

This approach — a permissive global setting plus a restrictive plugin filter —
keeps Hermes itself unopinionated about per-channel policy and makes the
per-channel rules visible in a single config file.  It is a shim, not a hack.

---

## Verbosity levels

The `verbosity` key controls which fields are written to the gate log.  Errors
always log all available fields regardless of verbosity level.

| Level | Fields |
|-------|--------|
| `minimal` | `ts`, `platform`, `channel_ids`, `message_id`, `verdict`, `silent`, `action`, `elapsed_ms` |
| `normal` *(default)* | Everything in `minimal`, plus: `trigger_author`, `trigger_author_kind`, `history_len`, `classifier_model`, `reasons` (up to 3), `confidences` (full dict from the directive, omitted when absent) |
| `debug` | Everything in `normal`, plus: `payload` (complete JSON sent to `nunchi-channel`) and `directive` (complete JSON returned) |

---

## Log format

One JSON object per line, appended to `log_path`.

### Normal dispatch entries

| Field | Verbosity | Type | Description |
|-------|-----------|------|-------------|
| `ts` | all | float | Unix timestamp of gate entry |
| `platform` | all | str | Platform name (e.g. `"discord"`) |
| `channel_ids` | all | list[str] | Sorted list of channel IDs from the event source |
| `message_id` | all | str\|null | Incoming message ID |
| `verdict` | all | str | Raw verdict string (`PASS`, `ACK`, `ASK`, `SPEAK`) |
| `silent` | all | bool\|null | The `silent` field from the nunchi-channel directive |
| `action` | all | str | `"skip"` (reply suppressed) or `"allow"` (reply proceeds) |
| `elapsed_ms` | all | int | Time from gate entry to verdict, in milliseconds |
| `trigger_author` | normal, debug | str\|null | Author field extracted from the event |
| `trigger_author_kind` | normal, debug | str\|null | `"human"`, `"peer_bot"`, or absent |
| `history_len` | normal, debug | int | Number of history entries included in the payload |
| `classifier_model` | normal, debug | str\|null | Model identifier reported by nunchi-channel |
| `reasons` | normal, debug | list[str] | Up to 3 reason strings from the classifier |
| `confidences` | normal, debug | dict\|absent | Full confidence scores dict from the directive (omitted when the directive does not include it) |
| `payload` | debug only | dict | Complete JSON payload sent to `nunchi-channel` |
| `directive` | debug only | dict | Complete JSON directive returned by `nunchi-channel` |
| `error` | error entries | str | Exception message (truncated to 500 chars) |
| `fail_open` | error entries | bool | The `fail_open` value at error time |

### Sender-policy drop entries

When a message is dropped by the sender policy (`senders: humans` or
`senders: allowlist`), a receipt entry is written with:

| Field | Description |
|-------|-------------|
| `ts` | Unix timestamp |
| `platform` | Platform name |
| `channel_ids` | Sorted list of channel IDs |
| `message_id` | Incoming message ID |
| `action` | `"skip-sender-policy"` |
| `elapsed_ms` | Wall-clock time to the drop decision |

No `verdict` or classifier fields are present in sender-policy drop entries.

Example normal entry (`verbosity: normal`):

```json
{
  "action": "skip",
  "channel_ids": ["1518384310321811456"],
  "classifier_model": "google/gemini-flash-lite",
  "confidences": {"ACK": 0.03, "ASK": 0.04, "PASS": 0.88, "SPEAK": 0.05},
  "elapsed_ms": 412,
  "history_len": 4,
  "message_id": "1234567890123456789",
  "platform": "discord",
  "reasons": ["No direct address", "Topic already resolved"],
  "silent": true,
  "trigger_author": "zoe",
  "trigger_author_kind": "human",
  "ts": 1751234567.123,
  "verdict": "PASS"
}
```

Example sender-policy drop entry:

```json
{
  "action": "skip-sender-policy",
  "channel_ids": ["9999999999999999999"],
  "elapsed_ms": 0,
  "message_id": "9876543210987654321",
  "platform": "discord",
  "ts": 1751234600.0
}
```
