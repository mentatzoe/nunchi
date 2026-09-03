# V2 platform interface and conformance

This is the current downstream interface for Hermes and Claude Code, and for
reference platform integrations. Both platform implementations consume the
shared owners but have not completed installed and live acceptance.
First-class ACK and the normal participant-turn protocol are now shared
interfaces; platform code does not redefine them.

## Required owners

| Owner | Input | Output | Non-delegable responsibility |
|---|---|---|---|
| Transport | native delivery | canonical event or explicit gap/error | native identity, route, ordering, delivery semantics |
| Observation provider | canonical deliveries | bounded attention request and host-only continuation | exact self, actor closure, coverage truth, retention |
| Attention engine | request plus pinned participant profile | decision | exactly one participant-delegated social judgment |
| ACK coordinator | ACK decision plus current authenticated reaction capability | one exact reaction or no effect | policy/capability widening, exact binding, durable replay suppression |
| Scheduler | wake-eligible event anchors | active/newest-pending opportunity | cancellation, coalescing, restart invalidation |
| Participant host | current decision plus fresh snapshot | normal participant invocation | wake/silence, origin validation, single commit point |
| Authorization coordinator | privileged proposal plus trusted policy | deny, approval challenge, or exact effect | requester, scope, digest, approval, expiry, revocation, persistence, replay |
| Native output transport | committed ordinary action | sent/failed/unknown/unavailable | exact native result, no social reclassification |

## Inputs a platform integration must supply

1. Exact trusted `ParticipantBinding`: participant ID, native actor ID,
   platform, room, continuity scope, and optional descriptive metadata.
2. A pinned JSON `ParticipantProfile` with matching participant and actor IDs.
3. One delegated attention provider returning the closed judgment shape.
4. For a Nunchi-owned participant, one isolated native model invocation that
   receives the core prompt/request/schema and returns the model result without
   interpreting it. Native-host integrations instead expose their admitted
   normal participant hook.
5. One native transport returning `TransportResult`, plus current
   authenticated reaction capability facts.
6. Stable private state paths for observations and receipts.
7. Optional pinned privileged-action policy and host-authenticated approval
   seam.

Room payloads are never trusted configuration.

The shared reference-adapter runtime can host either the pinned
OpenAI-compatible participant model or the Codex participant backend. Discord,
Matrix, and Telegram continue to own and authenticate their native ingress and
output. Generic JSONL ingress requires an exact HMAC-authenticated source and
payload envelope; raw channel-shaped prompt text is not an event. Both
backends use the same observation, attention, ACK, scheduling,
participant-host, authorization, transport, and receipt owners.

The shared runtime always owns the attention prompt, attention model selection,
judgment schema, policy, scheduling, and wake facts. For Nunchi-owned
participants it also owns the normal-turn prompt and action schema. A platform
plugin must not copy or rewrite those shared product behaviors.

### Host-owned participant pipelines

Hermes owns the participant execution pipeline. Its Nunchi integration uses
the shared observation, attention, opportunity preparation, scheduler, wake
builder, and participant-receipt formation as a gate around that pipeline:

1. Nunchi decides before Hermes starts visible processing.
2. `SUPPRESS` stops there.
3. An admitted turn receives the shared bounded wake facts through Hermes's
   context hook.
4. Hermes runs its participant prompt, main model, memory, reactions,
   cancellation, delivery, and platform adapter behind Nunchi's guards.
5. Nunchi observes completion and writes only the lifecycle facts exposed by
   Hermes.

For configured Nunchi rooms, Hermes tools are blocked because Hermes 0.19.0
does not expose a safe final authority boundary after approval. Auto-title is
also disabled because it can outlive the turn. Native typing, Discord voice
input, `/thread`, detached participant commands, and handoff into configured
rooms are disabled for the same lifecycle reason. Stock reactions run only
after the participant invocation begins. Because the current Hermes seam does
not attest the shared native ACK capability, a model ACK widens to DEFER and
runs the normal participant path. These are open product gaps: the current
Hermes source is not a complete V2 lifecycle.

The plugin requires Hermes 0.19.0 or newer. It checks the host capability
contract and installs its compatibility shim transactionally on every
activation. A changed required interface fails closed until Nunchi evolves its
shim; a new package version alone is not an incompatibility.

This is the intended Hermes participant implementation for the contract. The
plugin must not recreate shared Nunchi behavior with a second attention model
call, copied prompt, copied model selection, copied opportunity lifecycle, or
direct send path.

## Shared Discord consumer contract

A consumer of the shared Discord transport must:

1. authenticate one exact participant/channel MCP session with a one-use HMAC;
2. verify `target_participant_id`, `room_id`, and the gateway-attested
   `transport_self_actor_id` against its pinned binding before retaining facts;
3. accept only the closed notification fields documented in
   `integrations/mcp-discord/README.md`;
4. cancel active and pending work before applying a targeted continuity gap;
5. submit ordinary live events through the asynchronous active/newest lane;
6. measure current reaction permission through the authenticated
   `reaction_capability` tool and accept only its exact native room/self
   binding; unavailable, denied, or malformed facts widen ACK to DEFER;
7. invoke output/history tools only from that authenticated session with a
   fresh exact-operation authorization;
8. correlate every JSON-RPC response to the exact request and report `sent`
   only after the tool payload attests the expected native room, exact
   authenticated self, submitted content, reply target or non-reply effect,
   and new message or reaction identity. Empty, stale, cross-bot,
   wrong-content, wrong-reply, mismatched, or malformed acknowledgements are
   `unknown`, never synthetic success.

The server configuration maps participant IDs directly to numeric room arrays.
There is no participant/room cross product and no unauthenticated broadcast.
The delivery journal is per route, so one failed consumer cannot be hidden by
another consumer's success.

## Attention judgment returned by the delegated model

```json
{
  "disposition": "SUPPRESS",
  "reasons": ["not relevant to this participant"],
  "evidence_event_ids": ["discord:message:123"],
  "legacy_verdict_confidences": {
    "PASS": 0.91,
    "ACK": 0.03,
    "ASK": 0.02,
    "SPEAK": 0.04
  }
}
```

The confidence vector is margin evidence, not a V1 lifecycle verdict.
Uncertainty returns `DEFER`. `ACK` selects the core-configured lightweight
reaction. Only WAKE may include evidence-bound `attention_advice`.

## Normal participant result

Every Nunchi-owned participant receives `nunchi.participant-turn` version 1.
The model returns one closed envelope, copying the request's exact `protocol`
and `binding` objects:

```json
{
  "protocol": {"name": "nunchi.participant-turn", "version": 1},
  "binding": {
    "request_id": "...",
    "participant_id": "...",
    "actor_id": "...",
    "platform": "...",
    "room_id": "...",
    "continuity_scope_id": "...",
    "trigger_event_id": "...",
    "opportunity_generation": 7,
    "lifecycle_id": "...",
    "deadline_id": "...",
    "permissions_revision": "..."
  },
  "action": {"kind":"message","origin_event_id":"discord:message:123","text":"..."}
}
```

The `action` is exactly one `silence`, bounded `expand`, `message`, `reply`,
`reaction`, or privileged proposal shape allowed by the supplied schema. The
host rejects unknown versions, changed bindings, invisible origins or targets,
malformed actions, stale opportunities, deadline overruns, and unavailable
native capabilities. The participant cannot send directly.

## Continuation

The request may contain a bound expiring continuation capability. It remains
inside the host. The model sees only expansion availability booleans; the
normal participant receives a mediated function. Returned pages omit handles,
cursors, scope bindings, and expiry. Repeated requests use host-retained
cursors, never repeat already delivered events, and stop after three pages per
turn. Expired handles are pruned. A configured positive handle cap evicts the
oldest remaining authority only when reserving capacity for a newly issued
handle; fetching never revokes a known unexpired handle as a capacity side
effect. The wake refresh does not mint a second discarded capability.
Continuation state is therefore bounded as well as expiring. Coverage may
truthfully report evicted older facts without offering an unfulfillable
continuation. Restart discards all continuation authority.

Retention, snapshot, continuation-page, observation-receipt, and participant
packet byte counts cover the canonical `actors` plus `events` context. Actor
IDs and display metadata cannot escape an event budget; if the required
trigger closure and its actor closure do not fit, snapshot construction fails
explicitly without a model call.

## Scheduling and recovery

Native live ingress retains and offers each event before returning to the
platform callback. One worker runs the active opportunity while later anchors
replace a single pending slot; after the active turn, only the newest retained
anchor becomes work. One host-wide deadline begins before attention and spans
provider waiting, the participant, expansion, authorization, and native
transport acknowledgement. It invalidates even a participant or transport
that ignores cancellation; a late transport result remains `unknown` and
cannot revive work. Before an effect, the host persists a participant-host
`unknown` handoff; the transport stage alone settles actual delivery. A receipt
write that consumes the deadline therefore makes zero native calls.
Cancellation and expiry are rechecked after every blocking authorization
boundary, and canceled or expired challenges are absent from the operator
surface. Gap, cancellation, restart, and corrupt persistence cancel active and
pending authority rather than promoting retained events.

An unknown privileged effect remains consumed. If the target provides
idempotency, a fresh policy check may retry the same logical operation only
with the original deterministic idempotency key. Otherwise, a new
authenticated approval must display the exact operation, origin observation,
and duplicate-effect risk before one retry. A confirmed retry closes the
unknown state; ordinary replay remains denied.

## Runnable conformance

From the exact candidate:

```sh
uv run --offline --isolated --no-project --with 'jsonschema==4.26.0' \
  python -m unittest discover -s tests/v2/contract -p 'test_*.py'
python3 -m unittest \
  tests.v2.test_shared_foundation \
  tests.v2.test_surfaces \
  tests.v2.test_runtime_hardening
python3 -m evals.verdict_suite.runner
```

A downstream platform candidate must reuse these shared owners or provide a
thin wrapper whose injected attention, participant, transport, persistence,
and cancellation seams pass the same tests. Its platform-specific suite must
add:

- authenticated native self and wrong-route cases;
- native message, reaction, membership, reply, and explicit absence mapping;
- SUPPRESS, supported ACK with no participant, disabled/unsupported ACK
  widening to DEFER, WAKE contribution, WAKE silence, classifier DEFER, margin
  DEFER, bypass, error fallback, and explicit NO_WAKE error;
- ACK exact binding, restart replay, cancellation, permission change, and
  concurrent duplicate suppression;
- active-plus-newest-pending coalescing under real concurrency;
- cancellation ordered before and after the output commit point;
- restart/backfill without revived work or approval;
- exact-action authorization, mutation, expiry, revocation, approval,
  persistence failure, replay, and unknown result;
- clean installed-artifact probes and attributable real-platform evidence.

Passing schemas alone does not establish installed or live behavior.

See `docs/v2-shared-foundation.md` for exact interface versions, operator flow,
compatibility, and remaining platform work.
