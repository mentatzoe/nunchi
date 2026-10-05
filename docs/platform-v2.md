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

The shared runtime always owns the attention prompt, attention model selection,
judgment schema, policy, scheduling, and wake facts. For Nunchi-owned
participants it also owns the normal-turn prompt and action schema. A platform
plugin must not copy or rewrite those shared product behaviors.

### Agent-agnostic core seams

The shared core (`src/nunchi` outside `integrations/` and `adapters/`) names
no agent host, chat platform, or model vendor.
`tests/v2/test_agnostic_core.py` checks the top-level core modules for those
names. Host- and vendor-specific behavior enters through these seams:

- `attention_model_from_config(config, host_kinds=...)` builds the
  participant's attention model from trusted configuration. `kind` selects
  the implementation and defaults to `openai-compatible`, which requires an
  explicit `base_url` (there is no default endpoint), takes optional
  `temperature`, and passes provider-specific request fields through
  `extra_body`. An integration adds its own kinds as `host_kinds`, a mapping
  from kind name to factory. An unknown kind fails validation. No in-tree
  integration registers a kind yet.
- `HostTextAttentionModel(complete, ...)` is for hosts whose completion
  returns text only, with no JSON-schema mode and no report of the served
  model, such as a mod running attention on the user's own plan (not built
  yet). The host's
  `complete(system=..., prompt=..., timeout_seconds=...)` receives the same
  prompt and observation bytes as every other implementation.
  `decode_judgment_text` accepts the judgment object alone or in one Markdown
  code fence; anything else is a provider failure, never a guessed judgment.
- `HostStructuredAttentionModel(client, selection, is_denial=...,
  denied_detail=..., require_attestation=...)` wraps a host's
  `complete_structured` capability. `is_denial` recognises how that host
  signals a refused model; such errors become `HostAttentionPermissionError`
  carrying the integration's `denied_detail` repair text, and anything else
  is a provider failure. With `require_attestation` (the default) the host
  must report the provider and model it actually served. Hermes supplies its
  denial check and repair text from
  `src/nunchi/integrations/hermes_attention_trust.py`.
- An attention model's `provider` and `model_id` are opaque audit labels.
  `None` means the host does not report them, and the audit omits them.
- A participant that acts through tools inside its own agent loop uses the
  core tool-turn helpers in `nunchi.participant_model`.
  `participant_tool_roles(request)` lists the roles this turn's permissions
  allow (`send`, `react`, `propose`, `context`); `PARTICIPANT_TOOL_SPECS`
  holds each role's description and closed input schema;
  `participant_tool_turn_text(profile, request, tools=...)` renders the turn
  with the names the host registered; `participant_tool_action` turns one
  call into one bound action, checked against permissions and visible events;
  `participant_tool_expansion` turns a context call into expansion arguments.
  The host still commits the action through `ParticipantTurnHost`. The Claude
  Code gate is the first user
  ([`integrations/claude-code/README.md`](../integrations/claude-code/README.md)).

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

Configured-room tools use a durable invocation claim at the stock middleware
handoff. Hermes keeps its approvals and guards; Nunchi checks the opportunity
before dispatch, propagates cancellation through native thread interrupts,
and rechecks native approval waits on return. Invocation outcomes remain
unknown as effects, even when a tool returns text; claims are never retried
automatically after restart. Already-committed handlers that do not poll native
interrupts can continue after cancellation. This is cooperative cancellation,
not a sandbox or a zero-syscall guarantee. See
[`verification/2026-10-02-native-tools.md`](verification/2026-10-02-native-tools.md).

Auto-title is disabled because it can outlive the turn. Native typing, Discord voice
input, `/thread`, detached participant commands, and handoff into configured
rooms are disabled for the same lifecycle reason. A model ACK is not a
participant turn: when the authenticated adapter attests the configured
reaction, Nunchi adds that one reaction through the shipped adapter method
and the shared ACK journal. The effect is committed only while that
opportunity and deadline are still current, and journal waits stay off the
gateway loop. Unsupported or unknown permission still widens
ACK to DEFER and runs the normal participant path. These exclusions are not
a complete V2 lifecycle. See
[`verification/2026-10-02-hermes-ack.md`](verification/2026-10-02-hermes-ack.md)
and [`verification/2026-10-02-hermes-ack-repair.md`](verification/2026-10-02-hermes-ack-repair.md).

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
reaction. Every judgment may include evidence-bound `attention_advice`, the
model's reading of the room; it reaches the participant on WAKE and DEFER
turns.

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

The envelope may come alone or in one Markdown code fence. Text after the
closing fence is the model's own note, usually explaining a silence; it is
dropped and never posted. Any other text beside the envelope is a malformed
reply.

## The participant's view of the room

The gate's context and the participant's view are separate (Zoe, 2026-10-05,
#94 step 3). During its own turn the participant reads the room as it is now
through a host-mediated function: `before` (older messages), `after` (newer
than a message), `around`, or `new` (what others posted since the turn
began and it last looked). It reads the live retained log, never repeats an
event the participant has seen, and holds each page to the continuation
limits. It never fails the turn: nothing more, an evicted anchor, or the
per-turn limit of three history pages comes back as a page with a short
host-written `note`. Pages show messages only, never verdicts, and carry no
handles or cursors. Before the first message, reply, or reaction goes out,
the shared protocol and the Claude Code gate ask for `new` once; if others
posted meanwhile, the action is held, the participant is shown their
messages, and it sends, changes, or drops its action. Hermes does not offer
the view yet.

## Continuation

The attention request may contain a bound expiring continuation capability.
It remains inside the host. The attention model sees only expansion
availability booleans. Expired handles are pruned. A configured positive handle cap evicts the
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
surface. The turn deadline bounds only the publication of an approval
challenge; once published, it lives until its own expiry, an explicit cancel,
or restart. Gap, cancellation, restart, and corrupt persistence cancel active and
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
  tests.v2.test_runtime_hardening \
  tests.v2.test_agnostic_core \
  tests.v2.test_native_host_primitives
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
