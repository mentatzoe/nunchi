# Shared Nunchi V2 foundation

This document is the platform-consumer and operator handoff for the shared
foundation introduced for issues #55, #56, and #40. It describes candidate
source behavior. It does not establish installed platform acceptance, live
validation, release readiness, or V2 completion.

## Shared interfaces

The changed portable interfaces are:

| Interface | Version | Change |
|---|---:|---|
| `I-010B AttentionDecisionV2` | `@3` | first-class `ACK`, ACK audit, and safe ACK-to-DEFER widening |
| `I-010C ParticipantWakeV2` | `@2` | advice-free `ACK` wake/effect source |
| `I-010E AttentionReceiptV2` | `@3` | ACK disposition, authority audit, and ACK host source |
| `I-030A AttentionEngineV2` | `@2` | shared ACK selection and capability/policy widening |
| `I-040A ParticipantTurnHostV2` | `@2` | one core-owned participant protocol and durable ACK commit path |

Every Nunchi-owned participant runs `nunchi.participant-turn` version `1` from
`src/nunchi/participant_model.py`. Core owns its prompt, request, action schema,
parser, bounded expansion state, and authority binding. The request binds the
exact request, participant, actor, platform, room, continuity scope, trigger,
opportunity generation, lifecycle, deadline, and permission revision. A model
result must copy that protocol and binding exactly around one action. Unknown
versions, changed bindings, invisible origins/targets, exceeded permissions,
and excess expansion reject before an effect.

Codex and Claude Code now supply only their isolated native model invocation,
session continuity, cancellation, and result extraction. Reference platform
transports supply authenticated capability facts and native effects. They do
not own a prompt, parser, expansion policy, social decision, or participant
turn protocol. Hermes remains a native-host integration: it consumes the
shared attention and opportunity interfaces around its stock participant and
must widen unsupported ACK to DEFER until it exposes the required native
capability and effect boundary.

## Core outcomes

- `SUPPRESS` ends at attention. There is no participant or native call.
- `ACK` adds the configured reaction (default `👂`) to the exact trigger and
  does not run the full participant.
- `WAKE` runs one normal participant turn through the shared protocol.
- `DEFER` runs that same normal participant path without fabricated advice.
- Disabled ACK or absent/unauthenticated native reaction capability converts
  `ACK` to `DEFER`, with the exact policy or capability cause in receipts.

An ACK decision records its reaction, trusted policy provenance, and native
permission revision. Immediately before dispatch the host rechecks those
facts. It durably reserves an ACK key bound to participant, actor, platform,
room, continuity scope, target message, reaction, and operation. Request,
generation, lifecycle, deadline, and permission revision remain in the durable
reservation audit. A restart, replay, concurrent opportunity, cancellation, or
lost acknowledgement cannot emit a second reaction. Uncertain effects remain
`unknown`; they are never retried as if definitely absent.

## Operator flow

One installed wheel provides guided setup, automatic integrity pins,
diagnostics, a bundled dashboard, and profile-scoped service supervision:

```sh
nunchi setup \
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

nunchi config show --profile vigil
nunchi diagnose --profile vigil
nunchi dashboard --profile vigil
```

Setup writes private profile/config directories and commits the validated
operator schema plus its SHA-256 integrity pin as one atomic envelope. Readers
and writers share the same profile lock, so they cannot observe a config/digest
split. Operators do not hand-write JSON or calculate hashes. The operator
configuration names credential environment variables; it does not contain or
return credential values.

The CLI and `/api/v1/operator` dashboard endpoint return the same validated
schema and snapshot: identity, rooms, models, attention policy, ACK policy,
services, platform capabilities, compatibility, credential presence, health,
warnings, and recent receipts. Dashboard writes require the current revision
through `If-Match`; stale writes reject. The dashboard is loopback-only and
applies no-store, framing, content-type, and content-security protections.

Services are declared in the same profile schema and controlled with:

```sh
nunchi service start room --profile vigil
nunchi service status room --profile vigil
nunchi service logs room --profile vigil
nunchi service stop room --profile vigil
nunchi service restart room --profile vigil
nunchi service reset room --profile vigil
nunchi service install room --profile vigil
```

Per-service control is serialized. The supervisor uses a private environment,
enforces `never`, `on-failure`, or `always` restart policy, rejects duplicate
supervisors, waits for worker readiness, reports child/restart state, and
installs and activates launchd or systemd user definitions without overriding
the worker's restart policy. Persistent install resolves declared environment
sources into a private owner-only state file; credential values are absent from
the generated unit and dashboard, and reinstall refreshes them after rotation.
Reset removes ephemeral supervisor state only; ACK and receipt journals survive.
Profile uninstall stops and deactivates its services before removing only the
named profile. Package install metadata supports verified upgrade, rollback,
and an explicit state-purge boundary.

## Compatibility and remaining work

| Surface | Shared behavior available | Remaining platform work |
|---|---|---|
| Generic channel / Discord | full shared protocol; Discord MCP measures exact bot, room, roles, and permission overwrites before ACK | platform-specific live validation and acceptance |
| Matrix | shared protocol; exact `whoami` and room power-level measurement before add-reaction ACK | platform-specific live validation and acceptance |
| Telegram | shared protocol; unsupported ACK widens to DEFER | native ACK support only if a future verified adapter supplies it |
| Codex | shared protocol and operator schema | platform-specific live/release gates outside this foundation |
| Claude Code | shared protocol and operator schema | issue #39 live and supported-surface proof |
| Hermes | shared attention/opportunity seam; unsupported ACK widens to DEFER | issues #38, #42, and #44 platform closure |

Issue #41 remains the combined acceptance gate. Security assurance, release
work, final acceptance, and platform-specific live proof remain separate. This
foundation must not be described as merged, platform-accepted, released, or
V2-complete merely because its source and deterministic tests pass.

## Verification

```sh
python3 -m unittest
uv run --offline --isolated --no-project --with 'jsonschema==4.26.0' \
  python -m unittest discover -s tests/v2/contract -p 'test_*.py'
python3 -m evals.verdict_suite.runner --list
python3 -m evals.verdict_suite.runner
```

Clean-package verification must build a wheel, install it into a new virtual
environment without the checkout on `PYTHONPATH`, run both probes, exercise
guided setup/diagnostics, and import the dashboard and service worker from
`site-packages`. Source, installed, live, integration, and release claims stay
separate.
