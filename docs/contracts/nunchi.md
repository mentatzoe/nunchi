# Data contracts

**Current implementation, being redesigned.** This page explains the
data today's code accepts and produces. It does not make the library-owned
turn or sending path a requirement for the replacement design. Start that
review from the [agreed goal](../../AGENTS.md#architecture-goal-and-current-gap).

The JSON schemas define field shapes and limits. Runtime validators also
check relationships between records and current state. Unknown fields are
rejected. Use the shared definitions rather than maintaining private copies.

## Interface versions

These identifiers name implemented interfaces; they are separate from the
library's release number. `nunchi probe` reports installed revisions.

| Interface | Version | Definition |
|---|---|---|
| `I-010A AttentionRequestV2` | `@9` | [Attention request schema](../../schemas/v2/attention-request.schema.json) |
| `I-010B AttentionDecisionV2` | `@10` | [Attention decision schema](../../schemas/v2/attention-decision.schema.json) |
| `I-010C ParticipantWakeV2` | `@16` | [Participant context schema](../../schemas/v2/participant-wake.schema.json) |
| `I-010D ContextContinuationV2` | `@2` | [Context fetch schema](../../schemas/v2/context-continuation.schema.json) |
| `I-010E AttentionReceiptV2` | `@6` | [Receipt schema](../../schemas/v2/attention-receipt.schema.json) |
| `I-010F PrivilegedActionAuthorizationV2` | `@1` | [Authorization schema](../../schemas/v2/privileged-action-authorization.schema.json) |
| `I-030A AttentionEngineV2` | `@3` | [Attention engine](../../src/nunchi/attention.py) |
| `I-040A ParticipantTurnHostV2` | `@5` | [Current participant host](../../src/nunchi/participant.py) |
| `I-040D LocalTurnProtocolV2` | `@3` | [Current local turn protocol](../../src/nunchi/turn_server.py) |

The attention request has `schema_version: 2`. The attention documents do not
use an extra `interface`/`version` envelope. A nonempty `request_id` links the
request, decision, participant context and receipts for one attention pass.

## Attention request

An `AttentionRequestV2` describes what the participant can currently see:

| Field | Meaning |
|---|---|
| `self` | Participant ID and authenticated actor ID; optional names and descriptions do not establish identity |
| `room` | Platform, room ID and continuity scope, with optional room name and kind |
| `actors` | Metadata for observed or referenced actors, keyed by actor ID; not an inferred roster |
| `events` | Ordered messages, reactions and membership events |
| `trigger_event_id` | The included event being considered |
| `coverage` | What is retained, truncated, missing or unknown, with the applicable event, byte and age limits |
| `continuation` | Optional host-only permission to fetch more context |
| `pace`, `memory` | Optional timing facts and the participant's recorded conversation history |
| `occasion` | Optional `pause` or `outcome` when attention runs without a new message |
| `unattended_event_ids` | Up to three included messages that arrived while the participant was busy, newest first |

Event order is authoritative. Every actor reference must resolve in `actors`,
and the trigger must be present. Byte limits include the actor map as well as
events. If the required event and actor data do not fit, context construction
fails explicitly rather than silently omitting them.

Coverage distinguishes unknown facts from known absence. A continuity gap is
a point in the timeline. `coverage.gaps` reports gaps the current view reaches
and the participant has not yet been told about; it is not a lifetime flag.
The agreed gap behavior is described in the [behavior draft](../behavior.md).

A wire request may contain a continuation handle, binding and cursor. The
model-facing projection removes them and exposes only coverage and whether
expansion is available. A valid wire object is not automatically safe model
input.

## Attention decision

`AttentionDecisionV2` has three forms:

- **`ok`:** model answers, the original and effective dispositions, cited
  events, model identity and an audit of any policy adjustment.
- **`bypass`:** `request_id` and `cause: "preattention-disabled"`. It contains
  no fabricated model judgment, advice or classifier audit.
- **`error`:** a `{code, detail}` operational error. The code is a nonempty
  string, not a fixed enum. `request_id` may be absent if validation failed
  before one could be assigned. Classifier details appear only if it ran.

The model answers the two attention steps: whether this is conversation it
could join, then what is happening and which moves could fit. The answers
include `conversation`, `addressee`, `asks`, `answered`, `mid_thought` and
`move`, with optional message references. There is no usefulness or novelty
question. Chat and typed decision providers produce the same answer shape.

The existing engine derives a disposition from those answers. A low
`conversation` probability can select suppression, except when the reading
calls for participation; a likely `speak` selects wake. Other moves defer the
choice to the participant. The supported transitions are:

| Model disposition | Effective disposition | Recorded reason |
|---|---|---|
| `WAKE` | `WAKE` | No adjustment |
| `DEFER` | `DEFER` | Model deferred |
| `SUPPRESS` | `SUPPRESS` | No adjustment |
| `SUPPRESS` | `DEFER` | Uncertain margin, suppression disabled, recovery unproven, or an outcome turn |

`routing_audit.valve` identifies the rule that applied. `margin-defer`
requires an active margin and an `effective_margin` between 0 and 1;
other transitions cannot carry that value. Policy adjustments retain their
specific `override_cause`. An invalid transition is an error.

`attention_advice` contains up to four short notes with event citations. The
reading can accompany both wake and defer. Malformed notes and unknown
message pointers are dropped individually by the engine; malformed answers
fail the judgment. Audit `reasons` stay outside the participant's turn.

## Participant context

`ParticipantWakeV2` contains a fresh `self`, `room`, `actors`, `events`,
`trigger_event_id` and `coverage`, plus optional memory, pace and continuation.
Its `attention.source` is `WAKE`, `DEFER`, `ERROR_FALLBACK` or
`PREATTENTION_BYPASS`. Only model-judged wake/defer inputs carry advice.
Advice citations must still be present in the fresh view; stale items are
dropped. The context contains no composed reply or question asking the agent
to justify being admitted.

`memory` can record the participant's own moves, conversation threads and
privileged proposals. It records facts with message references, not reply
obligations. A move may carry the participant's private `why`, or point to
what prompted it with `about_event_id`, `about_author_id` and `about_text`.
Threads retain responses without treating every response as an answer.
Proposal memory exposes status, not the operation or approval credentials.

Memory limits and reconstruction are implemented in
[`memory.py`](../../src/nunchi/memory.py).
They are current implementation choices, not a complete context CRUD API.
Restart does not turn retained history into new work.

## More context

`ContextContinuationV2` describes a fetch request and its page:

- A request names `request_id`, `handle_id`, direction (`before`, `after` or
  `around`), an anchor, optional cursor, and event/byte limits. `around`
  requires an anchor; the other directions can default to the trigger.
- A page contains the same correlation and room information, ordered events,
  their actor map, coverage, and an optional next cursor.

The caller's actual participant, room, continuity scope and trigger must
match the issued handle. The direction must be allowed, limits must fit the
issued bounds, and a cursor must belong to that handle. A known, unexpired
handle alone is insufficient. Handles and cursors never enter model input.

The current turn implementation reads the live retained log through `RoomView`
instead. See [room context](../platform.md#room-context). These are distinct
interfaces; their future relationship belongs to the redesign.

## Receipts

`AttentionReceiptV2` records one stage of a request. Each stage writes its own
record; earlier records are not rewritten by a later stage.

| Stage | Writer | Main facts |
|---|---|---|
| `observation` | `observation-provider` | Included events, coverage and sizes |
| `attention` | `attention-engine` | Model result or bypass/error, policy and adjustments |
| `participant-host` | `participant-host` | Whether a participant ran, what it received, expansion and outcome |
| `transport` | `transport` | Delivery result: `sent`, `failed`, `unknown` or `unavailable` |

A receipt stream uses one request ID, follows that order, and contains each
stage at most once. A prefix is valid while work is incomplete or ends early.
A host's handoff is not proof of delivery; the transport records the native
result. An operator's `NO_WAKE` error policy is recorded as operational policy,
not as a social suppression judgment.

Older journals containing `ACK` remain readable. Current decisions, wakes and
new receipts do not use it.

## Privileged actions

`PrivilegedActionAuthorizationV2` represents a request, decision, approval
challenge or approval completion. Each record binds one participant and origin
event to an exact action, resource, scope and SHA-256 operation digest. The
raw operation stays with the host.

Validation rejects changed bindings, missing policy provenance, stale or
inconsistent approval, expired permission, replay and uncertain persistence.
Before dispatch, the coordinator rechecks current policy and authorization
and consumes permission for one effect. An approval message in room text is
not authenticated approval. The schema alone cannot establish identity,
current permission or successful execution.

See [privileged-action authorization](../security/privileged-action-authorization.md)
for the full policy and execution boundary.

## Validate the contracts

The shipped validators in [`v2_contracts.py`](../../src/nunchi/v2_contracts.py)
use the Python standard library. Tests also run JSON Schema validation with
`jsonschema==4.26.0`, against the same
[contract corpus](../../evals/v2/contract/). Expected case counts prevent a
fixture class from silently disappearing.

```sh
python3 -m pip install '.[test]'
python3 -m unittest discover -s tests/v2/contract -p 'test_*.py'
```

Both validators check schema-expressible rules. Runtime validation additionally
checks event uniqueness and ordering, actor references, trigger membership,
advice citations, continuation binding/expiry, and receipt sequences.
Relational cases can be valid JSON documents but invalid together. Stateful
cases cannot be decided by validating a single document. Missing schema-test
dependencies are reported as skips, not passes.

For `I-040A@5`, the existing participant host also rejects a reaction unless
it is exactly one emoji. The local turn protocol is `I-040D@3`. These runtime
interfaces are listed here because their revisions matter to consumers, even
though they do not have separate JSON Schema documents.
