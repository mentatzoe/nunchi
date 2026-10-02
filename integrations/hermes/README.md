# Hermes V2 integration

Nunchi installs as a normal Python package beside Hermes. It has no required
Hermes dependency and edits no Hermes source or installed distribution file.
It writes its own dashboard bridge and private configuration under Hermes's
user-data directory.

Current status: **landed, unverified**. Source and focused tests exist, but
installed-runtime and live-platform acceptance remain open. Earlier package
and live evidence belongs to a superseded implementation and does not verify
the landed code.

The current source accepts Hermes 0.19.0 or newer when its checked host
capability contract passes:

- A checked process-local wrapper runs observation and attention before
  Hermes starts typing, reactions, or participant work.
- Effective `SUPPRESS` returns there. `WAKE`, `DEFER`, bypass, and configured
  error-wake call Hermes's original handler exactly once.
- The integration calls Nunchi's shared observation, attention, opportunity,
  scheduling, wake, and participant-receipt code. It does not copy those
  product decisions into Hermes.
- Hermes's public `pre_llm_call` hook adds the shared bounded wake facts to the
  admitted turn without changing Hermes's system prompt or main model.
- Hermes keeps its participant prompt, main model, memory, reactions,
  cancellation, delivery, and platform adapter, subject to Nunchi's turn and
  effect guards.
- Generic Hermes tools are blocked on configured Nunchi rooms. Hermes 0.19.0
  exposes its tool hook before the handler performs approval and the native
  effect, so Nunchi cannot make the required final authority check there.
- Hermes auto-title is disabled on configured Nunchi rooms. Its background
  provider call and rename can otherwise run after the admitted turn ends.
- Hermes's stock processing reactions run only after participant invocation
  begins. A model ACK, when the authenticated adapter can add the configured
  reaction, is one native reaction on the exact trigger and does not run the
  participant. Unsupported or unknown permission widens that ACK to DEFER.
  Stock typing is disabled because Hermes 0.19.0 starts a
  background typing loop that can outlive the admitted opportunity.
- Discord voice input and native `/thread` are disabled on configured rooms.
  Hermes handoff cannot target a configured room. `/background`, `/goal`,
  `/queue`, `/retry`, and `/steer` are disabled because they create detached
  participant work. `/stop`, `/new`, `/reset`, and `/restart` remain available.
- The Discord patch extends Hermes's existing free-response set with exact
  configured Nunchi room IDs. It admits bot-authored messages through Hermes's
  existing checks only in those rooms and enables missed-message recovery only
  for those rooms. Mentions and profile-wide Discord settings are not required
  for Nunchi rooms.
- The Telegram patch retains each native update that Hermes combines into one
  text batch. Nunchi then processes those updates in order.
- Other Hermes platforms are not currently accepted. Adding one to a Nunchi
  config is rejected. Leave it unconfigured, or disable Nunchi, to use stock
  Hermes on that platform.
- Nunchi owns observation, attention, active/newest scheduling, wake facts,
  and lifecycle receipts. Hermes owns the admitted participant turn and its
  output.
- A Hermes version older than 0.19.0, or a runtime that does not satisfy the
  required host contract, refuses Nunchi activation with a repair message.
  The operator can update Nunchi's compatibility shim or run stock Hermes
  without the gate.

The wrappers change process behavior. They do not rewrite Hermes source,
checkout files, or installed distribution files.

## Install

Install Nunchi into the same environment as Hermes, enable its discovered
runtime plugin, then restart Hermes:

```sh
python -m pip install nunchi
hermes plugins enable nunchi
```

The package metadata exposes the `nunchi` entry point in the
`hermes_agent.plugins` group. When Hermes loads it, Nunchi installs its three
package-owned web bridge files into the selected profile and Hermes's
machine-level dashboard profile, because Hermes does not scan Python entry
points for dashboard assets. It also enables the entry point in that dashboard
profile unless the operator explicitly disabled it there. This changes only
Hermes user configuration and Nunchi-owned files; it does not change the
Hermes checkout or installed package. `nunchi-hermes-dashboard verify` checks
one bridge;
`nunchi-hermes-dashboard install` repairs it. These commands are repair and
verification tools; normal setup does not require running them.

A Hermes home or named profile may be a symlink to an existing directory,
including on another volume. The installer resolves that operator-selected
home once and keeps the dashboard inside it. Symlinks below the resolved home
(`plugins`, either Nunchi bridge directory, dashboard assets, or markers) are
still rejected, before migration or cleanup can modify their targets. Broken
profile links and symlink cycles require repairing the link or mounting the
target; the installer does not create a missing profile-link target.

## Configure

Enable the plugin and restart Hermes once. That first load installs the
**Nunchi** dashboard tab but does not activate the gate without a room config;
stock Hermes remains available. If the dashboard was already running before
that first load, restart the dashboard once so Hermes mounts the new tab and
API. Open the tab, select or enter a room, set the exact authenticated bot
actor ID, review the participant and attention settings, save, and restart
Hermes again. The plugin creates a private profile-scoped config and digest
under the selected profile's Hermes home:

```text
$HERMES_HOME/nunchi/profiles/<profile-and-hash>/
```

The machine dashboard passes its selected profile explicitly. Nunchi resolves
that profile without changing process-wide environment variables, and reads
only Nunchi's config pointers plus `DISCORD_ALLOW_BOTS` from the profile
`.env`. Hermes finds the same saved config on restart; no separate setup
command or environment variable is required.

For managed or manual configuration, use the same closed JSON shape:

```json
{
  "schema_version": 2,
  "hermes_profile": "default",
  "state_directory": "/absolute/private/path/nunchi-hermes-state",
  "rooms": [
    {
      "binding": {
        "participant_id": "agent",
        "actor_id": "discord:actor:123456789",
        "platform": "discord",
        "room_id": "987654321",
        "continuity_scope_id": "discord-room-987654321",
        "names": ["Agent"],
        "room_kind": "group",
        "provenance": "operator:hermes-default"
      },
      "profile": {
        "document": {
          "profile_id": "agent-default",
          "participant_id": "agent",
          "actor_id": "discord:actor:123456789",
          "instructions": "Judge whether this participant should take the turn.",
          "provenance": "operator:hermes-default"
        }
      },
      "attention": {
        "model": {
          "provider": "nous",
          "model": "deepseek/deepseek-v4-flash"
        },
        "policy": {
          "suppression_enabled": true,
          "suppression_recovery_verified": true
        }
      },
      "limits": {},
      "participant": {
        "timeout_seconds": 300,
        "max_expansions": 3
      }
    }
  ]
}
```

The config must be owned by the Hermes user and mode `0600`. An inline profile
is pinned by the outer config. A separate profile can instead use exact
`path`/`sha256` fields. Set `suppression_recovery_verified` to `true` only
after an attributable live restart and later-message recovery run has passed.
Until then, leave it `false`; Nunchi widens attempted suppression to `DEFER`.
The profile instructions describe the participant only to Nunchi's attention
model; they do not replace Hermes's system prompt. The attention provider and
model are required and intentionally separate from the participant's main
model. The dashboard defaults new rooms to
`nous` / `deepseek/deepseek-v4-flash`, the open-weight model selected for
Nunchi's lightweight operational attention route. Keep it explicit so the
participant model cannot silently replace it.

The dashboard's **Save & allow attention models** action configures the
profile's stock Hermes trust gate as part of setup: provider/model overrides
are allowed only for the providers and models selected across its rooms.
Saving again reconciles those allowlists (including removed routes). Runtime
attention never grants itself permission. Managed configurations can instead
allow only their selected routes directly in the Hermes profile:

```yaml
plugins:
  entries:
    nunchi:
      llm:
        allow_provider_override: true
        allow_model_override: true
        allowed_providers: [nous]
        allowed_models: [deepseek/deepseek-v4-flash]
```

Hermes retains the credentials. Nunchi supplies the selected provider and model
to Hermes's public plugin LLM API and verifies the returned attribution. A
present credential is not proof that the route has usable quota. Provider
failure is recorded and follows `attention.policy.error_action`; Nunchi never
silently falls back to the participant model for attention.

A host permission denial is recorded as `host-permission-denied`, with the
exact setting names and dashboard repair action rather than raw host exception
text. The dashboard shows saved-config trust readiness even if the Nunchi form
is unchanged, so Save can repair missing permissions. This readiness check is
not a provider/credential/quota check and does not prove the running gateway has
reloaded. The configured error policy still applies; an error-fallback wake is
not a successful classifier judgment.

Trust setup preserves unrelated configuration values and writes a private,
content-addressed `config.yaml.nunchi-backup-<sha256>` in that profile's Hermes
home before changing `config.yaml`. The active file is rewritten as JSON
(valid YAML); original YAML formatting and comments remain in the backup.
Unsupported non-JSON YAML values fail closed rather than being discarded.
A caught save failure restores the previous host bytes or absence; a concurrent
external edit is not overwritten. A process crash may leave the narrow grant
installed: repeat Save to reconcile it with the pinned room configuration.
For manual rollback, first stop editing the profile and review any intervening
changes, then restore the selected private backup together with the matching
pinned room config/digest. Never upload these backups: they may contain host
credentials. Restart remains an explicit operator action, not part of saving
or rollback. Host trust is checked per call, so a permission change can affect
attention immediately even before a gateway restart.

An explicit environment-managed config overrides the dashboard-created
profile config. For dashboard editing, put its digest in a private sidecar
file:

```sh
NUNCHI_HERMES_V2_CONFIG=/absolute/private/path/hermes-v2.json
NUNCHI_HERMES_V2_CONFIG_SHA256_FILE=/absolute/private/path/hermes-v2.json.sha256
```

For a named Hermes profile, use
`NUNCHI_HERMES_V2_CONFIG_<PROFILE>` and
`NUNCHI_HERMES_V2_CONFIG_SHA256_FILE_<PROFILE>`, with non-alphanumeric
characters replaced by `_`. An adjacent `<config>.sha256` file is also found
automatically. Both files must be private regular files owned by the Hermes
user. A literal `NUNCHI_HERMES_V2_CONFIG_SHA256` remains supported but is
read-only in the dashboard because the dashboard cannot update an environment
variable safely.

### Discord room behavior

A configured Discord room is a natural shared conversation:

- human and bot messages can reach Nunchi without mentioning the participant;
- direct group addresses such as “are you both listening?” can wake an included
  participant without naming or mentioning them;
- Hermes does not move those messages into an automatic thread;
- messages missed while Hermes restarts are recovered only from those rooms;
  and
- unconfigured rooms retain Hermes's normal admission, mention, and thread
  behavior.

Nunchi supplies this by wrapping Hermes's installed admission and
free-response and recovery methods in memory. It reuses the rest of the stock
Discord adapter. `DISCORD_ALLOW_BOTS`, `DISCORD_FREE_RESPONSE_CHANNELS`,
`DISCORD_NO_THREAD_CHANNELS`, and `DISCORD_MISSED_MESSAGE_BACKFILL` are not
required.

Current ingress is text-message only. Media messages are rejected because
Hermes 0.19.0 does not expose a complete V2 media mapping; reaction and
membership events are unavailable to this adapter. Reply relations carried by
normal text messages remain supported.

Hermes's `DISCORD_ALLOW_BOTS=mentions` or `all` remains a profile-wide fallback.
If set, it can admit bot messages outside Nunchi rooms under Hermes's normal
rules. The dashboard reports that state. Keep it `none` unless another Hermes
workflow needs the broader behavior.

## Dashboard

Open **Nunchi** in the Hermes dashboard to:

- configure supported Discord and Telegram rooms from Hermes's discovered
  channel list, with manual room IDs available when discovery is incomplete;
- confirm that no-mention conversation, room-scoped bot admission, and
  no-auto-thread behavior are active for configured Discord rooms;
- edit exact participant identity, attention identity context, the dedicated
  attention provider/model, attention policy, and gate deadline;
- use advanced JSON for the complete closed V2 configuration;
- inspect the newest V2 receipts for each configured room;
- save a new pinned config and restart Hermes to activate it.

Hermes authenticates the tab and its API. Saving uses the displayed revision
as an optimistic lock and validates the complete config before writing it. A
first save creates private config and digest files, with the digest written
last as the activation marker. Later saves use private atomic file
replacements. An interrupted first save that left only a valid config is shown
as recoverable setup; an orphan digest, stale edit, or invalid state fails
closed with a repair option. The running gateway is unchanged until the
operator requests restart; Hermes then invokes Nunchi's normal drain and
cancellation path.

Hermes continues to control platform credentials, allowlists, pairing, and all
unconfigured rooms. Nunchi changes Discord admission only for exact configured
room IDs.

This Hermes adapter currently supports Discord and Telegram only. Other Hermes
platforms remain stock Hermes behavior and cannot be added to a Nunchi config
until their identity, routing, and output seams are guarded and verified.

## Compatibility and repair

Nunchi requires Hermes 0.19.0 or newer and checks every wrapped host seam before
activation. Package versions are diagnostic evidence, not the compatibility
contract: a later Hermes release activates when host-contract V1 passes. An
actual interface mismatch fails closed, rolls back every process-local shim,
and names the incompatible seam. Update Nunchi's shim for the changed contract,
or run stock Hermes without the gate.

Two Discord gates run before Hermes's participant turn: bot admission and
auto-thread/free-response routing. A plugin that patches only the runner will
miss bot messages or receive a new thread ID instead of the configured room.
The Nunchi Discord shim covers both gates. The common gate itself is
platform-neutral. This remains a required compatibility check when adding
support for a new Hermes release.

The probe reports `complete_v2_lifecycle: false`,
`tool_execution: blocked-configured-routes`, and
`auto_title: disabled-configured-routes`. It also reports disabled stock
typing, Discord voice input, and detached participant commands. These features
must not be presented as supported Nunchi-room behavior until their gaps are
closed and reverified.

## Verify

In an authorized chat, run:

```text
/nunchi probe
```

The probe reports the installed Nunchi and Hermes versions, selected
compatibility mode, pinned configuration digest, and configured bindings. It
also reports that this Nunchi implementation writes no Hermes package files.
Only an external before/after hash comparison proves that Hermes bytes remained
unchanged during installation and use.

Source tests and a successful probe do not prove live platform behavior. Live
acceptance still requires attributable suppress, wake, defer, silence,
delivery, cancellation, restart, and later-message recovery runs on each
enabled platform. The landed implementation still needs exact
installed-runtime review and live-platform evidence.
