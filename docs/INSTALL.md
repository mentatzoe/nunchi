# Install and operate Nunchi V2

## Artifact installation

Build and install the exact candidate into a new environment:

```sh
python3 -m pip install build
python3 -m build
python3 -m venv /tmp/nunchi-v2-clean
/tmp/nunchi-v2-clean/bin/python -m pip install --no-deps \
  dist/nunchi-2.0.0-py3-none-any.whl
/tmp/nunchi-v2-clean/bin/nunchi probe
/tmp/nunchi-v2-clean/bin/nunchi-install probe
```

The wheel is the review subject. A source checkout on `PYTHONPATH` is not
installed-artifact evidence.

## Unified operator setup

Use the installed `nunchi` command for normal setup. It initializes private
operator roots and commits one validated shared-schema envelope with its
automatic integrity pin; no hand-written JSON, manual digest, separate
dashboard installation, or runner supervision is required.

```sh
/tmp/nunchi-v2-clean/bin/nunchi setup \
  --profile vigil \
  --participant-id vigil \
  --actor-id discord:bot:9 \
  --display-name Vigil \
  --instructions 'Contribute carefully.' \
  --platform discord \
  --room-id 42 \
  --room-name delivery \
  --continuity-scope-id discord:channel:42 \
  --attention-model provider/attention-model \
  --participant-model provider/participant-model

/tmp/nunchi-v2-clean/bin/nunchi config show --profile vigil
/tmp/nunchi-v2-clean/bin/nunchi diagnose --profile vigil
/tmp/nunchi-v2-clean/bin/nunchi dashboard --profile vigil
```

The operator configuration stores only credential environment-variable names.
Set those credentials outside the dashboard. A persistent-service install
resolves its declared environment sources into a private owner-only state file;
the generated launchd/systemd definition and dashboard never contain or return
the values. Re-run `nunchi service install` after rotating one of those values.
The dashboard and CLI expose the same
identity, rooms, models, attention/ACK policy, capabilities, compatibility,
health, services, and receipts. Dashboard mutations and service operations
require the current profile revision.

Declare supervised runners with repeated `--service NAME='COMMAND ...'` setup
arguments. Then use `nunchi service start|stop|restart|status|logs|reset`
or install and activate the generated launchd/systemd user definition with
`nunchi service install`. The worker, rather than the outer service manager,
enforces the configured restart policy. Profile reset preserves durable ACK
and receipt journals. `nunchi uninstall --profile NAME` stops its services,
deactivates installed definitions, and removes only that profile; package-level
state purge remains an explicit `nunchi-install uninstall --purge-state`
operation.

See [`v2-shared-foundation.md`](v2-shared-foundation.md) for the schema,
service, compatibility, and authority boundaries.

For Hermes, install the same wheel into Hermes's managed Python environment.
Package metadata lets Hermes discover the `nunchi` plugin without making
Hermes a Nunchi package dependency or changing Hermes source or installed
distribution files. The current source requires Hermes 0.19.0 or newer and
activates when its checked host capability contract passes. A changed required
interface fails closed until Nunchi evolves its package-owned compatibility
shim. The current adapter accepts configured Discord and Telegram rooms only.
Other platforms stay outside Nunchi and use stock Hermes behavior.
When Nunchi admits a configured turn, stock Hermes keeps its participant
prompt, main model, memory, post-invocation reactions, cancellation, delivery,
and platform adapter behind Nunchi's shared core and effect guards. Hermes's
current seam does not attest the shared native ACK capability, so model ACK
widens to DEFER. Hermes tools and
auto-title are disabled for that configured turn because Hermes 0.19.0 does
not expose safe final boundaries for them. Stock typing, Discord voice input,
native `/thread`, detached participant commands, and handoff into a configured
room are also disabled. `/stop`, `/new`, `/reset`, and `/restart` remain
available.

The source installs its package-owned dashboard bridge automatically in
Hermes's supported user-plugin directory. `nunchi-hermes-dashboard verify`
checks it, and `nunchi-hermes-dashboard install` repairs it when needed. See
[`../integrations/hermes/README.md`](../integrations/hermes/README.md) for the
pinned room/profile configuration, dashboard, `hermes plugins enable nunchi`,
and compatibility probe. First-time setup happens in the **Nunchi** dashboard
tab. The first enable/restart installs the tab, leaves Nunchi inactive, and
keeps stock Hermes available until setup is complete. Save a room in the tab,
then restart again to activate Nunchi. The plugin creates and later discovers
the private profile config itself; environment paths remain an optional
override. The separate dashboard command is a repair/check tool, not a setup
requirement.

The installed-host lane checks the released minimum and current Hermes source
on Discord and Telegram without permitting source or distribution changes.
Live first-save/restart proof remains pending. Do not reuse the superseded
`b6ee0c2` artifact or live record as proof of the current code.

Configured Discord rooms need no mentions or separate bot/thread environment
setup. The plugin extends Hermes's stock free-response path and admits
bot-authored messages only for exact configured Nunchi room IDs. A
profile-wide `DISCORD_ALLOW_BOTS` value is optional Hermes behavior, not a
Nunchi requirement; the dashboard warns when that broader fallback is active.
The plugin also enables Hermes's missed-message recovery only for configured
Nunchi rooms, so restart recovery needs no profile-wide Discord setting.

Initialize stable operator-owned directories:

```sh
nunchi-install init \
  --config-root "$NUNCHI_CONFIG_ROOT" \
  --state-root "$NUNCHI_STATE_ROOT"
nunchi-install verify --config-root "$NUNCHI_CONFIG_ROOT"
```

Both roots must be private to the operator (`0700`). Runtime journals and
markers are created `0600`. The installer has no repository discovery and no
Hermes or Claude Code artifact operations.

## Trusted configuration

Every configured adapter uses a JSON file whose exact bytes are pinned by
`--config-sha256` or `NUNCHI_ADAPTER_CONFIG_SHA256`. The Codex runner uses
`NUNCHI_CODEX_CONFIG_SHA256`; the Claude Code runner uses
`NUNCHI_CLAUDE_CODE_CONFIG_SHA256`. The profile entry contains its own exact
`path`/`sha256` pin.

Trusted configuration owns:

- exact participant, native self actor, platform, room, and continuity scope;
- participant profile and delegated attention model;
- attention suppression/recovery/margin/error policy;
- bounded retention, snapshot, age, continuation-page, continuation-handle,
  and expiry limits; every byte bound includes the referenced actor IDs and
  metadata as well as events;
- participant model, or fixed Codex or Claude Code model/session settings;
- Hermes keeps its own participant model and prompt, while Nunchi keeps the
  shared attention prompt, model selection, and lifecycle behavior;
- for Claude Code, the transport output-key variable name, which may not
  be one the participant turn can read;
- stable state directory and optional pinned privileged-action policy;
- native transport endpoint and credential environment-variable names.

Room text cannot supply or override any of these values.

## Shared Discord transport

Install `nunchi[mcp-discord]`, then set:

```text
NUNCHI_DISCORD_TOKEN
NUNCHI_DISCORD_PARTICIPANT_ROUTES
NUNCHI_DISCORD_OUTPUT_HMAC_KEY
NUNCHI_DISCORD_STATE_DIRECTORY
```

`NUNCHI_DISCORD_PARTICIPANT_ROUTES` is a closed JSON object such as
`{"codex":["123456789"]}`. It defines exact participant/room pairs, never a
participant-by-room cross product.

`NUNCHI_DISCORD_OUTPUT_HMAC_KEY` must be at least 32 bytes and shared only
between the host-owned participant runner and transport. Output/history tool
calls require a short-lived, exact-operation HMAC. Accepted nonces are fsynced
before native dispatch and remain replay-blocked across restart.

The transport requests message, reaction, membership, and message-content
gateway intents. Each MCP session must authenticate one exact route before it
can receive notifications or invoke tools. Notifications carry the
gateway-attested bot actor and exact target participant. The bounded queue
never replaces an accepted event. If an event or one participant delivery is
lost, a durable per-route audit is written; after restart, that route receives
an explicit continuity gap before any later event. Because gateway resume
credentials are intentionally process-local, every fresh shared or standalone
Discord process declares a source gap before it accepts post-start facts;
within-process resumable reconnects preserve their narrower attested
continuity.

Output success is target-attested. Message results must include a non-empty
native message identity for the exact room and authenticated bot and must echo
the exact submitted content plus the exact reply target or absence of one.
Reaction results must echo the exact room, target, operation, and reaction.
The Codex consumer independently rechecks those facts, JSON-RPC request
correlation, and the single MCP text result. Empty, stale, cross-bot,
wrong-content, wrong-reply, mismatched, or malformed acknowledgements are
recorded as unknown rather than sent.

`participant_timeout_seconds` is the host's total opportunity deadline despite
the compatibility name: observation packet construction, delegated attention,
the participant turn, expansion, privileged authorization, and native
transport acknowledgement all consume the same budget. A stage timeout may be
narrower, but no provider or network wait may extend the total deadline; a
late native result is recorded as `unknown` and cannot revive the opportunity.
Before any native effect, the shared host persists a participant-host
`unknown` handoff receipt. The separately owned transport stage alone may
later attest `sent`; if receipt persistence consumes the remaining deadline,
the host makes zero native calls and records a failed transport stage.

## Restart and recovery

Restart:

1. cancels active and pending conversation opportunities;
2. discards continuation handles and pending approvals;
3. retains bounded canonical observations as context only;
4. retains content-free replay reservations plus observation, receipt,
   authorization, output-nonce, and transport audits;
5. never promotes retained events into new wake work.

Corrupt or uncertain observation, receipt, authorization, nonce, session, or
continuity state fails closed. Operator recovery uses a new state directory or
an evidence-backed repair; the runtime never silently rewrites untrusted state.
Canonical delivery and event identities are fsynced to a content-free replay
reservation before mutable observation content. If the content or final audit
commit is uncertain, the event cannot wake again and coverage becomes unknown.

## Rollback

Stop V2 processes before changing artifacts. Rollback is an atomic deployment
choice: do not run V1 and V2 participants in one room/session. Retain the V2
state directory for audit, but do not feed V2 journals to a V1 runtime.
