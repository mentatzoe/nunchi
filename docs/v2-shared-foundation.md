# Shared Nunchi V2 foundation

This document is the platform-consumer and operator guide for the shared
foundation introduced for issues #55, #56, and #40. That foundation merged in
PR [#67](https://github.com/mentatzoe/nunchi/pull/67) on 2026-08-02, and later
shared-core PRs (#88, #89, #90, #91) refined it. It is on `main` and is
**merged, unverified**: deterministic tests and clean-install probes pass, but
there is no installed operator-deployment or live proof since PR #67, no
platform acceptance, no release, and no V2 completion.

## Shared interfaces

The changed portable interfaces are:

| Interface | Version | Change |
|---|---:|---|
| `I-010A AttentionRequestV2` | `@6` | the room's pace at the snapshot: the current time, the quiet before the judged message, its author's run, and the participant's own share (@2); the `pause` occasion, a look again after the room stayed quiet (@3); the `outcome` occasion, a turn for an approved action that finished (@4); the participant's memory, the same as its turn's (@5); the messages that arrived while the participant was busy, read with the newest as one moment (@6) |
| `I-010B AttentionDecisionV2` | `@8` | first-class `ACK`, ACK audit, and safe ACK-to-DEFER widening (@3); the reading of the room on every judgment (@4); the model's typed answers in place of the legacy confidence vector (@5); the `asks` answer and the `responds_to` pointer (@6); the `outcome-turn` widening, so an outcome turn always reaches the participant (@7); the `calls_for_participant` pointer, which message that arrived while the participant was busy still calls for it (@8) |
| `I-010C ParticipantWakeV2` | `@12` | `ACK` wake/effect source without a reading (@2); the reading on `DEFER` wakes and `judged_through_event_id` (@3); the participant's own recent moves in `memory` (@4); the threads, who asked what and which messages responded, in `memory` (@5); the participant's own reason with each move (@6); its privileged proposals and what became of them (@7); the room's pace for the turn (@8); the `pause` occasion of a turn from a look again (@9); the `outcome` occasion of a turn for an approved action that finished (@10); who wrote the message each own move was about, and what it said (@11); the messages that arrived while the participant was busy (@12) |
| `I-010E AttentionReceiptV2` | `@4` | ACK disposition, authority audit, and ACK host source (@3); the `outcome-turn` widening (@4) |
| `I-030A AttentionEngineV2` | `@2` | shared ACK selection and capability/policy widening |
| `I-040A ParticipantTurnHostV2` | `@2` | one core-owned participant protocol and durable ACK commit path |

Every Nunchi-owned participant runs `nunchi.participant-turn` version `1` from
`src/nunchi/participant_model.py`. Core owns its prompt, request, action schema,
parser, bounded expansion state, and authority binding. The request binds the
exact request, participant, actor, platform, room, continuity scope, trigger,
opportunity generation, lifecycle, deadline, and permission revision. A model
result copies that protocol and the binding's `request_id` around one action;
the host fills in the rest of the binding, and any binding field the result
carries must match exactly. Unknown
versions, changed bindings, invisible origins/targets, and exceeded
permissions reject before an effect. Asking for room history never fails the
turn: past the limit the participant is told so once, and only asking again
fails it. Before its first post or reaction the protocol looks again for what
others posted meanwhile, once.

The Codex runner supplies only its isolated native model invocation, session
continuity, cancellation, and result extraction. The Claude Code gate supplies
its dedicated session and the mod that turns room tool calls into actions
through the core's tool-turn helpers. Reference platform transports supply authenticated
capability facts and native effects. They do not own a prompt, parser,
expansion policy, social decision, or participant turn protocol. Hermes
consumes the same attention decision. When its authenticated adapter attests
the configured reaction, it adds that one reaction and does not run the
participant. Unsupported or unknown permission still widens ACK to DEFER.

## Attention model selection

The participant's attention model is chosen by trusted configuration, not by
the core. `attention_model_from_config(config, host_kinds=...)` selects an
implementation by `kind`; the default `openai-compatible` kind needs an
explicit `base_url` (there is no vendor default endpoint) and passes any
provider-specific request fields through `extra_body`. An integration adds its
own kinds through `host_kinds`; the reference adapters, the Claude Code gate
and the Codex runner add `decisions-api`, a typed decision model that answers
the attention questions natively. `HostTextAttentionModel` serves hosts whose
completion returns plain text, such as a mod running attention on the user's
own plan (not built); `HostStructuredAttentionModel` serves hosts with structured
completion and takes the host's denial check (`is_denial`, `denied_detail`)
and whether the host must attest the served model (`require_attestation`).
The attention engine gives every kind the same core prompt and bounded
observation and validates every judgment the same way. Provider and model
names are opaque audit labels; a host-served kind may omit them. A guard test
(`tests/v2/test_agnostic_core.py`) keeps host, vendor, and chat-platform names
out of the shared core.

## Core outcomes

- `SUPPRESS` ends at attention. There is no participant or native call.
- `ACK` gives the participant a normal turn by default: the ACK policy is
  off, so it widens to `DEFER` and any "mhm" is the participant's own
  (Zoe, 2026-10-05). With `ack.enabled: true`, Nunchi instead adds the
  configured reaction (default `👂`) to the exact trigger and does not run
  the full participant.
- `WAKE` runs one normal participant turn through the shared protocol.
- `DEFER` runs that same normal participant path, with the model's reading
  of the room when the judgment gave one.
- Disabled ACK or absent/unauthenticated native reaction capability converts
  `ACK` to `DEFER`, with the exact policy or capability cause in receipts.

An ACK decision records its reaction, trusted policy provenance, and native
permission revision. Immediately before dispatch the host rechecks those
facts. Hermes consumes the same check again at native entry, before the
network await, and does not hold the scheduler lock across that await. It
durably reserves an ACK key bound to participant, actor, platform,
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
configuration may name credential environment variables (a host-served model
needs none); it does not contain or return credential values. A model entry
may carry a `kind`. A room may name any chat platform: the in-tree reference
adapters register their platforms' capabilities, and a room on an unregistered
platform is accepted with an `unregistered` status and a warning that its
capabilities, including reactions, are unknown until measured at runtime.

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
| Codex | shared protocol and operator schema; the merged runner is reduced to Discord with Codex tools disabled | draft PR #71; parity issues #59–#65; live proof |
| Claude Code | the per-room gate, dedicated session, and mod (issue #43) use the shared host and the core tool-turn helpers | Discord only; #57, #58, and live proof in #39 |
| Hermes | shared attention ACK when the authenticated adapter attests the configured reaction; otherwise ACK widens to DEFER | issues #38, #42, and #44 platform closure |

Issue #41 remains the combined acceptance gate. Security assurance, release
work, final acceptance, and platform-specific live proof remain separate. Being
merged does not make this foundation platform-accepted, released, or
V2-complete.

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
