# V2 platform interface and conformance

This is the current downstream interface for Hermes and Claude Code, and for
reference platform integrations. Both platform implementations consume the
shared owners but have not completed installed and live acceptance.
The normal participant-turn protocol is a shared interface; platform code
does not redefine it. Nunchi never reacts on the participant's behalf: a "mhm"
is the participant's own reaction in its own turn (#94 step 7).

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
  from kind name to factory. An unknown kind fails validation. The reference
  adapters, the Claude Code gate and the Codex runner register
  `decisions-api` (`src/nunchi/adapters/decisions_api.py`), a typed decision
  model behind OpenRouter's Decisions API (`model`, optional `url`,
  `api_key_env`).
- The OpenAI-compatible participant model (`OpenAICompatibleParticipant`,
  `nunchi.participant_model`) takes the same optional `extra_body`, for
  example a provider's reasoning setting. It, the OpenAI-compatible attention
  model and the `decisions-api` model keep the provider's last response as
  `last_response`, so an audit or evaluation can read the served model and
  its token usage.
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
  call into one bound action, checked against permissions and visible events
  (the wake's events, the messages its memory points at, and any page the
  participant read);
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
rooms are disabled for the same lifecycle reason. A judgment that leans to a
"mhm" runs the normal participant path like any `DEFER`; Nunchi no longer
adds its own reaction or probes reaction permission before attention (#94
step 7; the earlier nod is recorded in
[`verification/2026-10-02-hermes-ack.md`](verification/2026-10-02-hermes-ack.md)).
These exclusions are not a complete V2 lifecycle.

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
   binding; unavailable, denied, or malformed facts take the participant's
   reaction away, never its turn;
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

Steps 1 and 2 of reading the room are fixed typed questions about the judged
message (`src/nunchi/attention_questions.py`, Zoe, 2026-10-05, #94 step 4).
Step 1 asks whether it is conversation that a participant like this one
could take part in; a message addressed to someone else is still
conversation. Step 2 asks who it is addressed to, whether it asks someone
for something, whether it was already answered and by which message, which
earlier message it answers or responds to, whether its author is
mid-thought, whether the participant has something to add, and which kinds
of response could fit. The participant's memory builds its threads from the
asks and the pointers (#94 step 5). Since #94 step 6 the judgment also
carries that memory, the same facts the participant's turn gets, so it reads
a message as the participant would: a CI line it promised to report on
concerns it even when nobody addresses it and the promise has left the
window. A chat model reads it; a typed model is not given it yet, because it
made Jev hold back where it should speak (run 37). Step 1's "not
conversation" never suppresses a message the judgment's most likely move is
to speak to.

There are two routes, and both produce the same answers:

- **A chat model** answers all the questions as one JSON object, with up to
  three notes on the room in its own words:

  ```json
  {
    "conversation": 0.97,
    "addressee": {"participant": 0.05, "room": 0.1, "someone_else": 0.8, "nobody": 0.05},
    "asks": 0.9,
    "answered": 0.1,
    "answered_by": null,
    "responds_to": null,
    "mid_thought": 0.05,
    "adds_something": 0.7,
    "move": {"speak": 0.3, "mhm": 0.0, "wait": 0.6, "stay_quiet": 0.1},
    "notes": [{"note": "Zoe asked Castor, who has not answered yet.", "evidence_event_ids": ["discord:message:123"]}]
  }
  ```

  Every yes/no answer is a probability. One written as `true`/`false`,
  `"yes"`/`"no"`, or a `{"yes": p, "no": q}` split is read as the
  probability it states; anything else malformed fails the judgment.

- **A typed decision model** has an `answer(questions, state, timeout_seconds)`
  method. It receives the questions and the conversation as a state document
  (`attention_state`) and answers them natively, with probabilities. The
  engine prefers it whenever a model has it.

The core decides from the answers. A `conversation` below 0.5 selects
`SUPPRESS`, and the margin valve widens a near call to `DEFER`. Otherwise
the most likely move decides: `speak` wakes the participant, and `mhm`,
`wait` or `stay_quiet` defer to the participant with the reading; any "mhm"
is the participant's own reaction. Ties go to the move that pays more
attention. The participant then decides for itself. The decision records
the answers (`answers`), short audit strings, and every message they cite.

The reading of the room (`attention_advice`) is written from the answers.
It holds the model's own notes, or notes rendered from its answers when it
wrote none, and its last note is always the kinds of response that could
fit, with their probabilities. It reaches the participant on WAKE and DEFER
turns. A malformed answer fails the judgment and follows the error policy; a
malformed note or a pointer to an unknown message is dropped on its own.

## Normal participant result

Every Nunchi-owned participant receives `nunchi.participant-turn` version 1.
The model returns one closed envelope, copying the request's exact `protocol`
object and the `request_id` of its `binding`:

```json
{
  "protocol": {"name": "nunchi.participant-turn", "version": 1},
  "binding": {"request_id": "..."},
  "action": {"kind":"message","origin_event_id":"discord:message:123","text":"..."}
}
```

The request's binding also names the participant, actor, platform, room,
continuity scope, trigger, opportunity generation, lifecycle, deadline and
permission revision. The host fills in whichever of these the result leaves
out from the turn's own binding (#94 step 3). Any it carries must match
exactly, and an unknown field is refused. Models dropped or miscopied these
opaque IDs and lost their message; a result names its turn by `request_id`.

The `action` is exactly one `silence`, bounded `expand`, `message`, `reply`,
`reaction`, privileged proposal, or `withdraw` shape allowed by the supplied
schema. `withdraw` names the `proposal_id` of one of the participant's
proposals still awaiting approval, as its memory shows it. The
host rejects unknown versions, changed bindings, invisible origins or targets,
malformed actions, stale opportunities, deadline overruns, and unavailable
native capabilities. The participant cannot send directly.

Every action but `expand`, `silence` included, may carry `why`: one short
sentence in the participant's own words on why it chose the move (#94 step
5). The host strips it before anything is sent or proposed and keeps it in
the participant's memory, where later turns see it with the move
(`memory.own_moves[].why`, at most 200 characters). A malformed `why` is
dropped alone. The Claude Code participant acts through tools and has no
`why`: its dedicated session keeps its own reasons in its transcript.

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

Steering (#94 step 6; Zoe, 2026-10-06): a host that can reach a running turn
also tells the participant what others posted while it works, not only when it
is about to post. The view's host-only `news` direction reads like `new` but
never counts against the participant's own checks, and no action schema offers
it to a model. The Claude Code mod asks the gate after each tool call the main
session makes in a room turn, and a new message rides that tool's result as
context the model reads, never shown to the user. Each message is shown once,
becomes a valid origin or target, and no longer holds the first post. Codex
and the generic runtime do not steer yet.

The host keeps one `RoomView` per turn. Its `fork()` gives a fresh view of
the same turn, as if nothing had been read yet; the behavior suite uses it to
play a turn again without the reading, and the host never dispatches a forked
view's action.

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
anchor becomes work. The anchors it replaced are not lost: before the newest is
judged, the newest 3 of them are judged, oldest first, for the participant's
memory alone, so a question asked meanwhile starts a thread (#94 step 6).
They get no turn of their own, share one attention timeout, and a failed one
is skipped. The newest one's judgment then reads them with it as one moment
(Zoe, 2026-10-06): the request lists them newest first
(`unattended_event_ids`), attention says which, if any, still calls for the
participant (`calls_for_participant`), step 1 never hides that moment, the
reading names the message first, and the turn lists them too. One host-wide
deadline begins before attention and spans
provider waiting, the participant, expansion, authorization, and native
transport acknowledgement. It invalidates even a participant or transport
that ignores cancellation; a late transport result remains `unknown` and
cannot revive work.

Looking again (#94 step 6, `docs/behavior.md`): when a judgment's most
likely move is to wait, for the addressee or for the speaker to finish, the
pipeline arms one look again at that message. A new eligible message
disarms it, and so does a sent or unknown move by the participant about it.
If the room stays quiet for `look_again_seconds` (300 by default; 0 turns it
off), the delivery lane's timer judges the same message again with
`occasion: "pause"`, and the participant may get a turn that carries it. It
runs only when the lane is idle, so it never displaces a newer message, and
it happens once per quiet stretch: a look again never arms another. Hosts
that run through the async delivery lane (Claude Code, Codex, and the
generic runtime) look again; Hermes does not yet.

Outcome turns (#94 step 6; Zoe, #90 decision 2 on #94): when an operator's
approval settles a privileged action after the participant's turn about it
ended, the authorization coordinator tells its outcome listeners. The
delivery lane registers one when it starts, queues the outcome, and runs it
as soon as nothing else is running: a turn about the message the action was
proposed for (or the newest retained event once that message has left the
window), with `occasion: "outcome"` and the proposal's status in the
participant's memory. Attention's reading comes as advice; a SUPPRESS
judgment widens to DEFER (`outcome-turn`), and an attention error still
gives the turn. Nunchi never reports the outcome in the room. Cancel and
restart drop waiting outcomes; the next turn's memory still shows them.

Before an effect, the host persists a participant-host
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
- SUPPRESS, a mhm judgment deferring to the participant, WAKE contribution,
  WAKE silence, classifier DEFER, margin DEFER, bypass, error fallback, and
  explicit NO_WAKE error;
- the participant's own reaction only within the attested reaction
  capability;
- active-plus-newest-pending coalescing under real concurrency;
- cancellation ordered before and after the output commit point;
- restart/backfill without revived work or approval;
- exact-action authorization, mutation, expiry, revocation, approval,
  persistence failure, replay, and unknown result;
- clean installed-artifact probes and attributable real-platform evidence.

Passing schemas alone does not establish installed or live behavior.

See `docs/v2-shared-foundation.md` for exact interface versions, operator flow,
compatibility, and remaining platform work.
