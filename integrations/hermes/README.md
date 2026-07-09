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
  # aliases: []
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
| `mention_id` | str | *(absent)* | Discord mention snowflake (e.g. `"1496355876234199040"`).  Included in the payload so the classifier can detect direct @-mentions.  This is the **platform mention token** (the numeric snowflake), **not** the display name: a display name here makes the gate blind to real @-mentions — a direct `@<snowflake>` mention reads as "someone else" and PASSes (observed live 2026-07-08).  Display names belong in `aliases`.  Omit if not needed. |
| `aliases` | list or CSV | *(absent)* | Additional identities this one agent answers to beyond `agent_id`/`mention_id`: display names, nicknames, secondary handles ("Codex"), profile names ("Aether"), extra mention tokens.  Sent as `agent.aliases` so addressing recognizes the full bundle.  Deduped against `agent_id`/`mention_id`.  Can be overridden per channel in the map form (a bot may carry a different display identity per channel).  Not runtime-overridable — like `agent_id`/`mention_id`, identity must stay stable within a session. |
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
| `aliases` | global `aliases` |

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

---

## Runtime state overrides

### Design: config.yaml vs state.json

nunchi-gate uses a two-layer configuration model:

| Layer | File | Who writes | When applied |
|-------|------|------------|--------------|
| **Baseline** | `~/.hermes/config.yaml` | Operator (editor / deploy) | At Hermes startup; comment-preserving |
| **Overrides** | `~/.hermes/nunchi-gate.state.json` | `/nunchi` slash command, dashboard PUT `/state` | Hot; mtime-cached; no restart needed |

The `state.json` file is always layered **on top of** the static baseline.  Hermes
does not need to restart when the state file changes — the gate reads it on every
event with mtime-based caching (no re-read unless the file changes on disk).

**Who reads what:**
- `_gate_event` in `__init__.py` applies `state["global"]` overrides before the
  basic gate check, then calls `merge_effective` to apply `state["channels"][id]`
  overrides on top of the config.yaml per-channel merge.
- The `/nunchi` slash command and the dashboard PUT `/state` both write through
  `state.save_state` with `updated_by="slash"` or `"dashboard"` respectively.

**Effective config layering order (lowest → highest precedence):**

1. config.yaml global keys (baseline)
2. `state["global"]` runtime overrides
3. config.yaml `channels` map per-channel keys (if using the map form)
4. `state["channels"][<id>]` runtime per-channel overrides

### Security whitelist

The following keys can be set via state (slash command or dashboard):

```
enabled, senders, allow_from, verbosity, fail_open, model, pinned_rules_file
```

The following keys are **config.yaml-only** and cannot be changed at runtime:

| Key | Rationale |
|-----|-----------|
| `binary` | Would allow a chat message to redirect the subprocess executable. |
| `timeout_seconds` | Operator-controlled safety boundary. |
| `log_path` | Prevents redirecting receipts to an attacker-controlled path. |
| `agent_id` | Changing the bot identity at runtime would corrupt history parsing. |
| `mention_id` | Same: identity must stay stable within a session. |
| `aliases` | Same: the identity bundle is operator config, not chat-settable. (Per-channel values in config.yaml's map form are fine; runtime state is not.) |
| `state_path` | Prevents the state file from redirecting itself. |

`state.py`'s `filter_overridable()` enforces this whitelist at ingestion time.
Both the slash command and the dashboard API call through `filter_overridable`
before writing, so neither surface can accidentally or maliciously bypass it.

### Hot-adding channels without editing config.yaml

You can add a new channel to the gate without touching `config.yaml` or
restarting Hermes:

```
/nunchi enable 9999999999999999999
```

This writes `{"enabled": true}` into `state["channels"]["9999999999999999999"]`.
`merge_effective` detects that the config.yaml baseline returned `None` for this
channel but the state file has an explicit `enabled: true`, and gates the channel
using the global-patched baseline config as the foundation (plus any additional
per-channel state overrides).

To remove a hot-added channel: `/nunchi reset 9999999999999999999`

To list all currently active surfaces (baseline-listed + state-introduced):
`/nunchi status`

---

## /nunchi slash command

The `/nunchi` command lets operators inspect and modify the gate configuration
at runtime from any Discord channel.  Changes take effect immediately — the next
gate invocation reads the updated state file.

> **Note:** the handler has no implicit channel context.  Channel IDs must be
> given explicitly (e.g. `1518384310321811456`).  Use `global` to target the
> cross-channel override.

### Subcommands

#### `status`

```
/nunchi status
```

Prints a compact effective-config summary for every configured channel (baseline
+ state-introduced).  Each config value carries a provenance badge:
- *(no badge)* — from config.yaml baseline
- `[global-override]` — set via `state["global"]`
- `[channel-override]` — set via `state["channels"][id]`
- `[state-introduced]` — channel exists only because of a state entry

#### `enable` / `disable`

```
/nunchi enable  <channel-id | global>
/nunchi disable <channel-id | global>
```

Sets `enabled: true` or `enabled: false` in the state for the given channel or
globally.  `enable <channel-id>` works for channels that are not listed in
config.yaml — the channel becomes state-introduced.

#### `senders`

```
/nunchi senders <all | humans | allowlist> [channel-id | global]
```

Sets the sender policy override.  When no channel is given, sets the global
override.  Valid values: `all`, `humans`, `allowlist`.

#### `verbosity`

```
/nunchi verbosity <minimal | normal | debug> [channel-id | global]
```

Sets the log verbosity override.  When no channel is given, sets the global
override.  Valid values: `minimal`, `normal`, `debug`.

#### `reset`

```
/nunchi reset [channel-id | global]
```

- `reset` or `reset global` — clears **all** overrides (global + every channel).
- `reset <channel-id>` — clears overrides for that channel only; global and
  other channels are untouched.

### Error handling

All subcommands return a human-readable string.  Unknown subcommands and
malformed arguments return the usage text.  Internal errors return an
`error:` prefix line.  The handler never raises.

---

## Dashboard tab

The dashboard plugin adds a **Nunchi** tab to the Hermes web interface.
It requires the dashboard service to be running (`hermes dashboard`).

### Install

The plugin directory must be discoverable from `~/.hermes/plugins/`.  The
existing gate symlink already covers this:

```sh
# Already done during gate install:
ln -s "$(pwd)/integrations/hermes/nunchi-gate" ~/.hermes/plugins/nunchi-gate
```

The `dashboard/` subdirectory inside the symlinked plugin directory is
discovered automatically at startup.  **A dashboard service restart is
required** for the new tab to appear (the plugin is discovered at process
start, not hot-reloaded):

```sh
# Restart hermes with the dashboard flag
hermes dashboard
```

After restarting, the **Nunchi** tab should appear in the sidebar.

### Dashboard routes

| Route | Method | Description |
|-------|--------|-------------|
| `GET /api/plugins/nunchi/state` | GET | Returns `{baseline, overrides, effective, channel_names, available_channels, resolved_model}`.  `channel_names` maps IDs to human-readable names from `~/.hermes/channel_directory.json` (mtime-cached).  `available_channels` lists directory entries not yet configured (`{id, name}` objects).  `resolved_model` is `{value, source}` computed by the dashboard service process (see [Model resolution display](#model-resolution-display)). |
| `PUT /api/plugins/nunchi/state` | PUT | Apply overrides.  Body: `{"global": {...}, "channels": {"<id>": {...}}}`.  Whitelist-enforced. |
| `GET /api/plugins/nunchi/receipts?limit=N` | GET | Tail-parse the gate JSONL log (default 50, max 500).  Newest-first.  All JSONL fields returned as-is — no filtering. |

### UI features

The dashboard tab is built entirely from Hermes SDK components
(`Card`, `Button`, `Input`, `Label`, `Select`, `Badge`, `Tabs`, `Separator`)
and host CSS custom properties — zero hardcoded colours or fonts.

**Settings tab**

- **Channel display names** — channel names from `channel_directory.json` shown
  prominently above the raw snowflake ID (displayed in muted tertiary text).
- **Global Overrides card** — set `senders`, `verbosity`, and `model` globally,
  each with one-line help text and a provenance badge.
- **Per-channel cards** — editable `enabled`, `senders`, `verbosity`, `model`,
  and `pinned_rules` with provenance badges per field.
  - `senders = allowlist` reveals an `allow_from` textarea (comma or
    newline-separated names/IDs; stored as a list).
  - **Model field** — text input; helper shows the effective value with source
    (see [Model resolution display](#model-resolution-display));
    provenance badge shows whether the value is a channel override, global
    override, or inherited.
  - **Room governance (pinned rules)** — collapsible textarea per channel.
    Inline rules (`pinned_rules` state key) take precedence over
    `pinned_rules_file` when both are set; state-set `pinned_rules` overrides
    any file-based value at the gate call site.
- **Add channel** — a control at the bottom of the channel list that lets
  operators hot-add a new channel without editing config.yaml or restarting
  Hermes.  See [Adding channels from the dashboard](#adding-channels-from-the-dashboard).
- **Provenance badges** — amber **pending** while an edit is unsaved;
  cream **channel** for a channel-level override; secondary **global** for a
  global override; no badge for baseline values.
- **Save button** — disabled (dimmed, `not-allowed` cursor, tooltip) when no
  pending edits; amber **Unsaved changes** indicator when edits exist.
- **Reset All Overrides** — sends `{global:{}, channels:{}}` which replaces
  (clears) both sections via replace-on-empty semantics.
- **Refresh** — reloads state from the server.

**Receipts tab**

- **Polling controls** — pause/resume button, interval selector (2 s / 5 s /
  15 s / Off); selection persisted in `localStorage` under key `nunchi.poll`.
- **Visibility suspension** — polling is automatically suspended when the tab
  or window is hidden (`visibilitychange` listener); resumes on becoming visible.
- **Verdict legend** — four distinct entries:
  `PASS = suppressed (no message) · ACK = brief presence signal · ASK = one clarifying question · SPEAK = full turn`
  styled with host semantic colour tokens (PASS = destructive, SPEAK = success,
  ASK = warning, ACK = secondary).
- **Expandable receipt rows** — each row is a disclosure button (`aria-expanded`,
  keyboard accessible via Enter/Space).  Collapsed: summary line (timestamp,
  verdict chip, author, channel IDs, up to three reasons, confidence bar).
  Expanded: every field present in the receipt JSONL object, including the full
  reasons list, full confidence table, elapsed\_ms, classifier\_model, message\_id,
  channel (with resolved display name), action, silent, and full ts.  At debug
  verbosity, also shows the gate payload (trigger content, history entries,
  pinned\_rules presence) and the full directive, rendered as labeled rows.
  Fields absent from the receipt are silently omitted; a muted note
  "Message content is only recorded at debug verbosity" appears when debug
  fields are absent.
- **Confidence distribution** — when present, each receipt row renders the full
  confidence dict sorted highest-first (e.g. `SPEAK 0.70 · PASS 0.20 · ACK 0.05 · ASK 0.05`),
  with the winning verdict emphasised in bold.  A mini percentage bar below shows
  the top-verdict share using a host token colour.
- **Reasons** — up to three reasons joined with ` · ` in the collapsed summary;
  the full list is shown in the expanded detail panel.
- **Date-aware timestamps** — today's receipts show time only; older receipts
  show date and time.  The expanded panel also shows a full locale date-time.

### Adding channels from the dashboard

The Settings tab includes an **Add channel** control below the channel list.
It provides two ways to stage a new channel:

1. **Channel directory select** — when `~/.hermes/channel_directory.json`
   contains channels that are not already configured (either in `config.yaml`
   or in the current state overrides), they appear in a dropdown by display
   name (selecting pre-fills the ID field).
2. **Free-text ID input** — type any channel ID directly.  Accepted: any
   non-empty token without spaces.  Discord snowflakes (digits only) and
   other platform-specific formats are all accepted.

Clicking **Add** stages `channels.<id>.enabled = true` as a pending change,
which goes through the normal Save flow (pending badge appears, Save button
activates, server applies the change on Save).

> **Gateway allowlist caveat:** adding a channel here writes `enabled: true`
> into the gate's runtime state, but the channel must also be one the hermes
> gateway forwards to plugins (`allowed_channels` in the gateway config).  If
> the gateway never delivers messages from that channel, the gate never sees
> them regardless of this setting.

You can also add channels without the dashboard:

```
/nunchi enable <channel-id>   # from Discord chat
```

Or permanently, without needing a restart, via config.yaml:

```yaml
nunchi:
  channels:
    "<channel-id>":
      senders: all
```

### Model resolution display

The **model** field in the Global Overrides card and in each channel card shows
helper text `currently: <value> (from <source>)` where `<source>` is one of:

| Source | Meaning |
|--------|---------|
| `config` | Set explicitly in config.yaml or a state override |
| `env var` | Inherited from `NUNCHI_CLASSIFIER_MODEL` in the dashboard service process environment |
| `.env` | Found in `~/.hermes/.env` (the same file `_load_dotenv_into` injects into the subprocess at gate time) |
| *(absent)* | Not configured anywhere |

The resolution is computed by `resolve.py`'s `resolve_effective_model` helper
using the same lookup order the plugin applies at gate time:
`cfg["model"]` → `environ["NUNCHI_CLASSIFIER_MODEL"]` → `.env` file → `None`.

> **Caveat:** this resolution is computed by the dashboard service process.
> The gateway subprocess sees its own environment at gate time — which may
> differ if the dashboard service was started in a different shell or with
> different environment variables.  A tooltip on the helper text notes this.
> The gateway's environment is always authoritative at gate time.

**Overridable keys**

`pinned_rules` (inline governance text) is now in the security whitelist
alongside `enabled`, `senders`, `allow_from`, `verbosity`, `fail_open`,
`model`, and `pinned_rules_file`.  `binary`, `timeout_seconds`, `log_path`,
`agent_id`, `mention_id`, `aliases`, and `state_path` remain config.yaml-only.

**pinned_rules precedence**

When `pinned_rules` is set via state (dashboard or slash command), it takes
precedence over `pinned_rules_file` in the gate payload.  The gate calls
`cfg.get("pinned_rules")` before falling back to `pinned_rules_file`, so any
state-merged `pinned_rules` value is applied first.  To revert to file-based
rules, clear the `pinned_rules` state key (send `null` or leave the textarea
empty and save).

### Manual verification steps

After installing and restarting the dashboard:

1. Open the Hermes dashboard in a browser.
2. Check the sidebar for a **Nunchi** tab (Shield icon).
3. The tab should load without errors; the **Channels** section shows channels
   from config.yaml (or an empty state if none are configured).
4. Toggle `enabled` on a channel, click **Save**, and verify the state file
   was updated: `cat ~/.hermes/nunchi-gate.state.json`.
5. Send a message in the gated channel and check the **Receipts** panel updates
   within 5 seconds.
6. Click **Reset All Overrides** and confirm the state file is cleared.
7. Run `/nunchi status` in Discord; the output should reflect the cleared state.

#### New behaviours introduced in UX audit round

**B1 — Reset All is no longer a no-op**
Click **Reset All Overrides** while overrides exist and confirm
`cat ~/.hermes/nunchi-gate.state.json` contains neither a `"global"` nor a
`"channels"` key afterwards.  Previously, sending `{global:{}, channels:{}}`
was a no-op merge; it now replaces (clears) each section.

**B2 — Null-deletion and redundant-override pruning**
Set `senders` to a non-baseline value on a channel and save.  Open
`state.json` and confirm the key is stored.  Now set `senders` back to the
baseline value (e.g. `"all"` if that is the config.yaml default) and save
again.  Confirm `senders` is gone from `state.json` — the dashboard sends
`null` as the deletion signal, and the server prunes the now-redundant
override.

**M1 — Success messages auto-dismiss**
After clicking **Save** or **Reset All Overrides** successfully, the status
message ("Saved." / "All overrides cleared.") should disappear automatically
after 4 seconds.  Error messages ("Save failed: …") must persist until the
next action.

**M2 — Pending badges**
Change a field on a channel (do not click Save).  The field's provenance
badge should change to amber **pending** immediately.  After saving, the badge
should revert to **channel-override** (purple) or disappear if the server
pruned the override.

**M3 — Save button disabled when idle**
On first load (no pending edits), the **Save** button should be visually
dimmed, have `cursor: not-allowed`, and show a tooltip "No unsaved changes".
After editing any field the amber **Unsaved changes** indicator should appear
beside Save and the button should become active.  After a successful save both
the indicator and the dimmed state should reset.

**mn1 — Effective view is whitelist-filtered**
`GET /api/plugins/nunchi/state` → inspect `effective["<channel-id>"]`.  Keys
such as `binary`, `timeout_seconds`, `log_path`, `agent_id`, `mention_id`,
and `state_path` must not appear; only `OVERRIDABLE_KEYS` values are returned.

**mn2 — Receipts show date for non-today entries**
In the receipts panel, a receipt whose `ts` timestamp is from a previous day
should display a date prefix (e.g. `7/1/2026 3:04:05 PM`) while today's
receipts show time only (e.g. `3:04:05 PM`).

**mn3 — Up to three reasons shown**
A receipt entry with multiple `reasons` strings should display up to three of
them joined with ` · ` (e.g. `No direct address · Topic resolved · Low signal`).

**p1 — PASS verdict labelled as suppressed**
Receipts panel: a `PASS` verdict should display as **PASS (suppressed)**.  A
one-line legend `PASS = suppressed · SPEAK = full turn · ACK/ASK = brief turn`
should appear directly under the "Gate Receipts" heading.

**p2 — Legacy channel_ids form works in provenance**
Configure channels as a flat YAML list (`channel_ids: ["123", "456"]`).  The
state-introduced badge logic should recognise these channels as baseline
channels (not show them as `[state-introduced]`).

---

#### New behaviours introduced in verification-audit round

**VA-1 — Version banner when backend is outdated**
`GET /api/plugins/nunchi/state` now returns `"api_version": "2"`.  If the
response lacks `api_version` or its numeric value is below `2`, a prominent
amber banner appears at the top of the Nunchi tab:
> ⚠️ The dashboard service is running an outdated nunchi backend — restart the
> hermes dashboard service to activate current features.

To test: temporarily rename `plugin_api.py`'s `PLUGIN_API_VERSION` to `"1"` and
reload the dashboard.  The banner should appear.  Restore to `"2"` and confirm
the banner disappears on the next load.

**VA-2 — Honest save contract (applied/rejected echo)**
`PUT /api/plugins/nunchi/state` now responds with:
```json
{"ok": true, "applied_state": {"global": {...}, "channels": {...}}, "rejected_keys": [...]}
```
If `rejected_keys` is non-empty, the dashboard shows a **persistent** error:
> Server did not accept: \<field names\> — the dashboard service may be running an
> older plugin version

To test: send a PUT body containing a non-overridable key (e.g.
`{"global": {"binary": "/evil"}}`) directly via `curl`.  Confirm `rejected_keys`
contains `"binary"` in the response.

**VA-3 — Per-channel Clear overrides button**
Each channel card with at least one stored override shows a small **Clear
overrides** button in the header.  Clicking it presents a confirm dialog; on
confirmation it sends `PUT /state` with `{"channels": {"<id>": {}}}` which
wipes that channel's overrides without affecting other channels or global
overrides.  Confirm `state.json` no longer contains the cleared channel's entry.

**VA-4 — allow_from does not mangle input while typing**
Open a channel card with `senders: allowlist`.  Type a comma-separated list
such as `alice, bob` into the `allow_from` field.  The cursor should not jump
and the text should not be re-ordered mid-keystroke.  Parsing into an array
only occurs on blur (clicking away from the field) or on Save.

**VA-5 — Global "(inherit)" removes override**
In the **Global Overrides** card, select `(inherit)` for `senders` or
`verbosity`.  The provenance badge should turn amber **pending**.  After saving,
the global override key should be absent from `state.json` (not present as an
empty value).

**VA-6 — Per-channel selects have "(inherit)" option**
Each channel card's `senders`, `verbosity`, and `enabled` selects include
`(inherit)` as the first option.  Selecting it removes the channel-level
override for that key on the next Save (server prunes the null deletion signal).

**VA-7 — allow_from cleared when senders changes from allowlist**
Set `senders: allowlist` and populate `allow_from`, then save.  Confirm both
keys appear in `state.json`.  Change `senders` to `humans` and save.  Confirm
`allow_from` is gone from `state.json` — the dashboard sends `allow_from: null`
alongside the senders change.

**VA-8 — Effective model displayed as helper text**
In both the **Global Overrides** card and each channel card, the model field
shows helper text `currently: <effective model>` reflecting the value that
would actually be used (from override, global, baseline, or "(from env)").

**VA-9 — Verbosity options carry short meanings**
The verbosity selects in the global and channel cards now read:
`minimal — verdict & action only`, `normal — + reasons & confidences`,
`debug — + full payload`.

**VA-10 — Channel-ID pill is readable on all themes**
The snowflake ID shown below the channel display name now has an explicit
translucent background and padding, ensuring it is legible regardless of the
host dashboard theme (was invisible at ~1:1 contrast on light themes).
