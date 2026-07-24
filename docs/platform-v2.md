# V2 platform interface and conformance

This is the complete downstream interface for Hermes and Claude Code. Those
integrations are not implemented or armed by the shared-foundation candidate.

## Required owners

| Owner | Input | Output | Non-delegable responsibility |
|---|---|---|---|
| Transport | native delivery | canonical event or explicit gap/error | native identity, route, ordering, delivery semantics |
| Observation provider | canonical deliveries | bounded attention request and host-only continuation | exact self, actor closure, coverage truth, retention |
| Attention engine | request plus pinned participant profile | decision | exactly one participant-delegated social judgment |
| Scheduler | wake-eligible event anchors | active/newest-pending opportunity | cancellation, coalescing, restart invalidation |
| Participant host | current decision plus fresh snapshot | normal participant invocation | wake/silence, origin validation, single commit point |
| Authorization coordinator | privileged proposal plus trusted policy | deny, approval challenge, or exact effect | requester, scope, digest, approval, expiry, revocation, persistence, replay |
| Native output transport | committed ordinary action | sent/failed/unknown/unavailable | exact native result, no social reclassification |

## Inputs a platform integration must supply

1. Exact trusted `ParticipantBinding`: participant ID, native actor ID,
   platform, room, continuity scope, and optional descriptive metadata.
2. A pinned JSON `ParticipantProfile` with matching participant and actor IDs.
3. One delegated attention provider returning the closed judgment shape.
4. One normal participant implementation accepting `wake`, mediated `expand`,
   and cancellation.
5. One native transport returning `TransportResult`.
6. Stable private state paths for observations and receipts.
7. Optional pinned privileged-action policy and host-authenticated approval
   seam.

Room payloads are never trusted configuration.

## Shared Discord consumer contract

A consumer of the shared Discord transport must:

1. authenticate one exact participant/channel MCP session with a one-use HMAC;
2. verify `target_participant_id`, `room_id`, and the gateway-attested
   `transport_self_actor_id` against its pinned binding before retaining facts;
3. accept only the closed notification fields documented in
   `integrations/mcp-discord/README.md`;
4. cancel active and pending work before applying a targeted continuity gap;
5. submit ordinary live events through the asynchronous active/newest lane;
6. invoke output/history tools only from that authenticated session with a
   fresh exact-operation authorization;
7. correlate every JSON-RPC response to the exact request and report `sent`
   only after the tool payload attests the expected native room, effect, and
   new message or reaction identity. Empty, stale, mismatched, or malformed
   acknowledgements are `unknown`, never synthetic success.

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
Uncertainty returns `DEFER`. Only WAKE may include evidence-bound
`attention_advice`.

## Normal participant result

Return `None` for silence, or exactly one:

```json
{"kind":"message","origin_event_id":"discord:message:123","text":"..."}
{"kind":"reply","origin_event_id":"discord:message:123","target_event_id":"discord:message:120","text":"..."}
{"kind":"reaction","origin_event_id":"discord:message:123","target_event_id":"discord:message:120","reaction":"✅","operation":"add"}
{"kind":"privileged","origin_event_id":"discord:message:123","capability":"workspace.file.write","resource":{"kind":"workspace-file","id":"repo:README.md"},"operation":{"path":"README.md","content":"..."}}
```

The host rejects invisible origins or targets, malformed actions, stale
opportunities, deadline overruns, and unavailable native capabilities. The
participant cannot send directly.

## Continuation

The request may contain a bound expiring continuation capability. It remains
inside the host. The model sees only expansion availability booleans; the
normal participant receives a mediated function. Returned pages omit handles,
cursors, scope bindings, and expiry. Repeated requests use host-retained
cursors, never repeat already delivered events, and stop after three pages per
turn. Expired handles are pruned and a configured positive handle cap evicts
the oldest remaining authority, so retained continuation state is bounded as
well as expiring. Coverage may truthfully report evicted older facts without
offering an unfulfillable continuation. Restart discards all continuation
authority.

## Scheduling and recovery

Native live ingress retains and offers each event before returning to the
platform callback. One worker runs the active opportunity while later anchors
replace a single pending slot; after the active turn, only the newest retained
anchor becomes work. A host-wide deadline invalidates even a participant that
ignores cancellation. Gap, cancellation, restart, and corrupt persistence
cancel active and pending authority rather than promoting retained events.

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
- SUPPRESS, WAKE contribution, WAKE silence, classifier DEFER, margin DEFER,
  bypass, error fallback, and explicit NO_WAKE error;
- active-plus-newest-pending coalescing under real concurrency;
- cancellation ordered before and after the output commit point;
- restart/backfill without revived work or approval;
- exact-action authorization, mutation, expiry, revocation, approval,
  persistence failure, replay, and unknown result;
- clean installed-artifact probes and attributable real-platform evidence.

Passing schemas alone does not establish installed or live behavior.
