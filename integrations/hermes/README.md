# Hermes integration — Nunchi V2

`nunchi-v2` is a Hermes plugin packaged in the Nunchi wheel. It is not an admission gate. For every authorized event on an explicitly bound route it:

1. records the native event in the shared V2 observation provider;
2. applies the participant's own delegated attention once;
3. on WAKE, DEFER, bypass, or configured error-wake, invokes the ordinary participant turn;
4. accepts contribution, bounded context expansion, a privileged proposal, or silence;
5. dispatches ordinary output through Hermes' public route-bound delivery capability and privileged effects through the shared authorization coordinator.

Identity, gateway admission, configuration, scheduling, lifecycle, authorization, persistence, and effects remain host-owned. There is no V1 classifier, normal-agent fallback, compatibility config, or PASS/ACK/ASK/SPEAK gate path.

## Prerequisites

- Hermes Agent with the public async `gateway_message` and `gateway_session_cancel` plugin hooks, immutable event/route snapshots, route-bound delivery receipts, `ctx.llm.complete_structured`, and `ctx.dispatch_tool`. Nunchi does not use `pre_gateway_dispatch`, a raw `GatewayRunner`, private adapters, or session-store internals.
- The exact Nunchi wheel installed into the Python environment that runs `hermes`.
- A host-authorized Discord or Telegram route configured so every relevant room message reaches the gateway callback. Nunchi owns participant attention; leaving Hermes mention-only intake enabled would prevent observation rather than produce silence.

For Discord room observation, configure the bound channel/thread in Hermes' free-response set. If other participants are bots, configure Hermes to admit them (`DISCORD_ALLOW_BOTS=all`) and disable any inline-mention requirement for the bound room. Keep user/role/channel authorization restrictive.

For Telegram groups/topics, configure the group in `TELEGRAM_GROUP_ALLOWED_CHATS` (or the equivalent profile config) and use Hermes' observe-unmentioned mode for the bound surface. A topic's canonical Nunchi room ID is `CHAT_ID:topic:TOPIC_ID`; a non-topic chat uses `CHAT_ID`.

These are host admission settings, not Nunchi authority. Unauthorized events are never observed.

## Clean artifact installation

Build once, record the digest, then install that exact wheel into the Hermes runtime environment:

```bash
uv build --offline
WHEEL=dist/nunchi-2.0.0-py3-none-any.whl
shasum -a 256 "$WHEEL"

HERMES_PYTHON=/path/to/the/python-used-by-hermes
"$HERMES_PYTHON" -m pip install --no-deps --force-reinstall "$WHEEL"
hermes plugins list
hermes plugins enable nunchi-v2
```

`hermes plugins list` must report `nunchi-v2` from the installed `hermes_agent.plugins` entry point. A repository checkout on `PYTHONPATH`, a copied V1 user plugin, or an editable install is not clean-artifact evidence.

If a historical user plugin exists at `~/.hermes/plugins/nunchi-gate`, disable and remove it before enabling V2. Do not run V1 and V2 on the same route.

Keep each candidate room on Hermes' normal mention/command admission setting during installation. Install the exact Hermes core candidate and Nunchi wheel, generate and pin configuration, enable the plugin, restart Hermes, and require `/nunchi-v2 probe` to report `operational: true`, generation 2, and the expected digests and route binding. Only then enable unmentioned-message admission for that exact room. This ordering prevents a broken or undiscovered entry point from silently falling through to the normal Hermes agent.

## Generate pinned configuration

Put the participant instructions in an operator-owned file, then generate a private profile/config bundle:

```bash
nunchi-hermes-v2-config \
  --hermes-profile default \
  --platform discord \
  --room-id '1530625523334779001' \
  --actor-id '1496355876234199040' \
  --participant-id aleph \
  --profile-id aleph-default \
  --instructions-file "$HOME/.hermes/nunchi-v2/participant.md" \
  --output-dir "$HOME/.hermes/nunchi-v2/default" \
  --state-root "$HOME/.hermes/nunchi-v2/default/state" \
  --name Aleph
```

The command writes `0600` JSON files under a `0700` directory and prints their SHA-256 digests plus the exact profile-scoped environment keys. Suppression is disabled by default. It may be enabled only with `--enable-suppression --suppression-recovery-evidence PATH`, where the pinned JSON evidence identifies the matching platform and records `"later_hearing": "verified"`. For profile `default` they are:

```text
NUNCHI_HERMES_V2_CONFIG_DEFAULT=/absolute/path/hermes-v2-config.json
NUNCHI_HERMES_V2_CONFIG_SHA256_DEFAULT=<64 lowercase hex>
```

Set them in that Hermes profile's trusted environment, then restart Hermes. The unscoped names are accepted only as a single-profile compatibility spelling for profile `default`; non-default profiles require scoped names.

The config is closed and exact. It binds:

- Hermes profile;
- participant ID and exact native bot actor ID;
- platform, canonical room ID, and continuity scope;
- digest-pinned participant profile;
- participant-owned attention policy and total participant deadline;
- bounded observation/continuation/ingress limits;
- state root;
- optional digest-pinned authorization policy and fixed privileged capabilities.

Any byte change invalidates the configured digest. An enabled plugin that cannot verify its configuration still registers a profile-wide `gateway_message` safety hook and suppresses normal-agent dispatch; its probe reports `operational: false`. Room text cannot alter any binding or policy.

## Privileged effects

The participant may propose only a capability enabled by the pinned room config and matched by the pinned operator policy. The plugin exposes a fixed capability-to-Hermes-tool map:

- `hermes.cron.create` → `cronjob`, bounded create operations delivered only to the origin room and with script/no-agent/workdir overrides rejected;
- `hermes.task.delegate` → `delegate_task`;
- `workspace.file.write` → `write_file`, with an exact host-derived absolute-path resource;
- `workspace.file.patch` → single-file `patch` replace mode, with an exact host-derived absolute-path resource.

The participant cannot choose an arbitrary tool name or declare a resource that differs from the operation's host-derived target. Cron and delegation resources are derived from the participant/room binding. File targets are resolved by the host before policy matching. A mismatch fails before authorization or effect execution. The shared coordinator resolves the requester from the retained origin event, binds the exact operation digest and resource scope, reloads policy before effect commit, persists one-use consumption, rejects replay, and preserves unknown acknowledgement state.

Rules that are not direct-allow create a host-only approval challenge. Inspection and completion are accepted only in a host-authorized direct message from an exact actor ID listed in the pinned policy:

```text
nunchi-v2 approvals
nunchi-v2 approve APPROVAL_CHALLENGE_ID
```

These are post-authorization DM control messages, not slash commands or participant prompts. They are ignored as authority in rooms. Pending approvals are discarded on restart. Approval output is sent only through the route-bound authenticated DM capability.

## Operation and probe

```text
/nunchi-v2 probe
```

The probe reports generation 2, `v1_fallback: false`, Hermes profile, config digest, participant/profile binding, isolated state directory, and enabled capability names. It does not expose provider credentials, room conversation, or authorization operation contents.

The native adapter reports `sent` only with a positive acknowledgement and a non-empty native message ID. Rejection is `failed`; timeout, exception, malformed, or unattributable acknowledgement is `unknown`; unsupported reaction surfaces are `unavailable`. None of those states is rewritten as social success.

State is partitioned by Hermes profile, participant, platform, room, and continuity scope. Observation, receipts, and authorization journals are durable. Active/pending work, continuation handles, and pending approvals are invalidated on restart and never promoted from retained history.

## Platform verification

From the exact candidate:

```bash
python3 -m unittest tests.v2.test_hermes
python3 -m unittest \
  tests.v2.test_shared_foundation \
  tests.v2.test_surfaces \
  tests.v2.test_runtime_hardening \
  tests.v2.test_hermes
python3 -m evals.verdict_suite.runner
uv build --offline
```

Then install the built wheel into a fresh Hermes environment/home, verify entry-point discovery and `/nunchi-v2 probe`, restart, and run the live Discord and Telegram scenes required by `docs/platform-v2.md`. Record candidate SHA, wheel digest, Hermes version/commit, Hermes Python executable, profile/config/profile-policy digests, native event/output IDs, and exact command output. Evidence from a remediated predecessor is stale.

## Rollback

Rollback is an admission-first operation. Restore mention/command-only admission for every bound room and verify ordinary unmentioned room traffic no longer reaches the participant seam **before** disabling the plugin or replacing either artifact. Then stop Hermes, disable `nunchi-v2`, replace the exact Hermes/Nunchi artifacts as one deployment unit, and restart. Retain the V2 state directory for audit; never feed its journals into V1. Do not leave an observation-open room with the V2 entry point absent, disabled, or non-operational, because that would permit normal-agent fallthrough.
