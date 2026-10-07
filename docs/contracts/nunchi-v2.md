# Nunchi V2 Contracts

**Owner**: Codex owns the shared portable contracts. Consumers use these
schemas rather than maintaining private variants.

**Status**: these six contracts are the implemented shared seam in the V2
candidate. Candidate source behavior does not by itself establish installed,
live, integrated, or released status.

**Field-level authority**: this repository-owned reference and
`docs/architecture/v2-selected-design.md` preserve the field inventory selected
from Aleph Vault at `c834e8c`; the external path is provenance, not a
contributor dependency. The program-canonical interface names and versions
(`I-010D`, `I-010F` at `@1`; `I-010A` at `@6`; `I-010E` at `@5`; `I-010C` at `@13`; `I-010B` at `@9`) are this
slice's vocabulary layered over that inventory. A document the selected design
declares valid that either validator rejects is a contract defect, never
resolved by narrowing the corpus.

**Machine-readable contracts** (JSON Schema Draft 2020-12):

| Interface | Version | Schema path |
|---|---|---|
| `I-010A AttentionRequestV2` | `@6` | [`schemas/v2/attention-request.schema.json`](../../schemas/v2/attention-request.schema.json) |
| `I-010B AttentionDecisionV2` | `@9` | [`schemas/v2/attention-decision.schema.json`](../../schemas/v2/attention-decision.schema.json) |
| `I-010C ParticipantWakeV2` | `@13` | [`schemas/v2/participant-wake.schema.json`](../../schemas/v2/participant-wake.schema.json) |
| `I-010D ContextContinuationV2` | `@1` | [`schemas/v2/context-continuation.schema.json`](../../schemas/v2/context-continuation.schema.json) |
| `I-010E AttentionReceiptV2` | `@5` | [`schemas/v2/attention-receipt.schema.json`](../../schemas/v2/attention-receipt.schema.json) |
| `I-010F PrivilegedActionAuthorizationV2` | `@1` | [`schemas/v2/privileged-action-authorization.schema.json`](../../schemas/v2/privileged-action-authorization.schema.json) |

### Privileged-action boundary

`I-010F PrivilegedActionAuthorizationV2@1` has a machine-readable schema,
deterministic flow validator, adversarial corpus, and an executable shared
coordinator. Platform hosts still own their trusted policy source,
authenticated approval seam, and native effect executors.

Only the request carries an explicit generation tag, `schema_version: 2`
(the design's own field; there is no separate `interface`/`version`
envelope pair on any of the five documents — that was an attempt-2 local
invention the selected design does not carry). A non-empty `request_id`
correlates the request, decision, wake, and receipt records for one
attention pass. All five contracts are closed: an unexpected property
rejects. V1 envelopes, reply-bearing fields, inferred-roster claims, and
`handled`/`open`/`owed`/permission ledger state reject everywhere; there is
no V1 translation bridge (FR-011).

## Attention contract flow

```text
observation  ->  AttentionRequestV2   (host assembles factual events)
             ->  AttentionDecisionV2  (ok | bypass | error)
             ->  ParticipantWakeV2    (WAKE | DEFER | ERROR_FALLBACK | PREATTENTION_BYPASS)
             ->  ContextContinuationV2 (optional host-mediated bounded expansion)
             ->  AttentionReceiptV2   (immutable staged telemetry, one record per stage)
```

These are lifecycle boundaries, not social state: no contract carries a
composed reply, an admission meta-answer, or a social permission ledger.

## I-010F PrivilegedActionAuthorizationV2@1

This contract is a closed host-facing union, always carrying a `schema_version:
1`, a non-secret `request_id`, and one exact `binding`:

- **`request`** records a unique action ID, participant, exact origin event,
  namespaced capability, bounded platform/room/continuity/participant/resource
  scope, transport-derived requester, and a digest of the operation. The raw
  operation remains host-only.
- **`decision`** records `ALLOW`, `DENY`, or `APPROVAL_REQUIRED`, the reason,
  trusted operator-policy provenance, evaluation/expiry/revocation/persistence
  facts, and either direct-policy or authenticated-approval provenance.
- **`approval_challenge`** is an expiring, exact-bound, host-only reference
  naming the allowed approvers. It carries no reusable approval secret.
- **`approval_completion`** names the exact authenticated approver and a fresh
  policy/revocation/expiry/persistence recheck. It must follow its originating
  approval-required decision and retain the challenge's policy provenance. A
  later authenticated-approval decision must name that exact completion, match
  its outcome and policy/expiry/revocation/persistence facts, and occur after
  that recheck.

`binding.action_digest` is a closed object: `algorithm` is exactly `sha256`,
`value` is exactly 64 lowercase hexadecimal characters, and
`canonicalization_profile` is exactly `nunchi.operation-json.v1`. A different
canonicalization algorithm requires a versioned contract change; an unknown
profile cannot authorize an operation.

The deterministic flow validator rejects a changed action, digest, origin,
requester, capability, scope, challenge, approver, policy provenance, expiry,
revocation, or persistence fact; stale revocation results; a decision reason
that contradicts its outcome; a completion that predates its
approval-required decision; and recheck policy drift. It also rejects multiple
initial policy decisions, duplicate decision IDs, multiple completions of one
challenge, and multiple decisions from one completion. An approval prompt is
valid only when approval is the sole missing authority: policy and revocation
must otherwise be current and the decision durable. Room text, reactions,
quotes, aliases, model assertions, copied decisions, and unknown fields cannot
become authorization facts because the union is closed.

This is deliberately not a bearer-capability format. Schema and corpus success
does not attest a native event, authenticate an approver, load a policy, retain
state across restart, or execute anything. `I-040B` must resolve the retained
canonical event, recheck all facts immediately before execution, persist the
new decision, and consume one allow at one effect-commit point. Unknown
persistence, restart, expiry, revocation, replay, capacity exhaustion, or any
binding mismatch means no effect.

Focused checks:

```sh
python3 -m unittest tests.v2.contract.test_privileged_action_authorization
uv run --offline --isolated --no-project --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'
```

## I-010A AttentionRequestV2@7

A truthful attention request represents:

- **Exact self binding** — `self.participant_id` plus one exact
  `self.actor_id`, transport- or host-attested (FR-002). Optional
  `self.names`/`role`/`description` are flat loose descriptors that never
  establish authorship; an alias collision with another observed actor is
  representable without becoming an identity claim. `self.actor_id` must
  resolve to a key in `actors` (runtime-adapter-only; rejection R8).
- **Room facts** — `room.platform`, `room.id`, `room.continuity_scope_id`,
  optional `room.name` and `room.kind` (`group`/`direct`/`unknown`).
- **The actor map** — `actors` is an object keyed by opaque actor ID (not
  an array), value `{display_name?, kind?}`; the observed/referenced cast
  only, never an inferred full roster. Every typed event's actor reference
  must resolve to a key here too (runtime-adapter-only; rejection R8) — a
  reference absent from the map is a dangling opaque string.
- **The typed event union** — array order is authoritative. Every event
  carries `id` and `type`; `message` events add `author_id`, optional
  `timestamp`, `text`, optional `reply_to_event_id`/`thread_root_event_id`,
  `mentioned_actor_ids`, and `mentions_room`; `reaction` events add
  `author_id`, `target_event_id`, `reaction`, and `operation`
  (`add`/`remove`); `membership` events add `scope`
  (`{kind: room/thread/space/unknown, id}`), `subject_actor_id`, optional
  `caused_by_actor_id`, and `change` (`join`/`leave`) (FR-003, FR-014).
- **One included trigger** — `trigger_event_id` must name an event in
  `events` (runtime-adapter-only rule; see the partition below).
- **Honest coverage** — `has_more_before`/`has_more_after` (boolean or
  `null` when unknowable), `has_gaps`, `truncated_by` (subset of
  `events`/`bytes`/`age`), `continuity` (`restart-safe`/`session-only`/
  `unknown`), `has_restart_gap`, optional `max_events`/`max_bytes`/
  `max_age_seconds` budgets (each a positive integer, S15), and optional
  per-event-type `event_visibility`. `session-only` continuity and unknown
  visibility are never upgraded by inference.
- **Relational byte closure** — when `coverage.max_bytes` is present, the
  canonical `actors` plus `events` context must fit that budget; actor IDs and
  actor metadata are not free side channels. The stdlib runtime enforces this
  relation for both attention requests and participant wakes.
- **Optional continuation capability** — the wire document MAY carry the
  full `continuation` object (`handle_id`, exact `bound_to`
  `{participant_id, room_id, continuity_scope_id, trigger_event_id}`,
  `can_fetch_before`/`can_fetch_after`/`can_fetch_around_event`,
  `max_events_per_fetch`/`max_bytes_per_fetch`, optional `expires_at`) —
  the selected design's own example embeds it, so the schema does not
  forbid it (FR-014). The classifier-facing host-secret exclusion (FR-004)
  is enforced where the classifier is actually invoked: the runtime path
  that constructs the model-facing projection redacts `continuation` down
  to coverage plus expansion-capability booleans before that call. This is
  a runtime-adapter-only behavior, not a schema constraint.
- **The room's pace (@2, #94 step 6)** — optional `pace`, computed when the
  snapshot is built: `now`; `window_messages` and `own_messages` (the
  participant's share of the window's messages); and, when the timestamps
  allow, `judged_seconds_ago`, `quiet_before_seconds` (since the previous
  message by anyone), `author_run_messages` and `author_run_seconds` (the
  judged message's author's unbroken run of messages ending at it; other
  people's messages break a run, reactions and joins do not), and
  `own_last_seconds_ago`. All are whole non-negative numbers;
  `own_messages` never exceeds `window_messages` (runtime-adapter-only).
  They are facts, never verdicts. The host's clock is injectable, so a
  replay can place each moment at its own time.
- **Why it is judged without a new message (@3, #94 step 6)** — optional
  `occasion`. Absent, the trigger is judged because it just arrived (or, on
  replay, as it arrived). `pause` means an earlier judgment of the same
  trigger read it as a moment to wait on, and the room stayed quiet since,
  so it is judged again as it stands now. `pace.judged_seconds_ago` then
  says how long the quiet has lasted. Since @4, `outcome` means an action
  the participant proposed was approved and has finished since its turn
  about it ended (Zoe, #90 decision 2 on #94). The trigger is the message
  the action was proposed about, or the newest retained event once that
  message has left the window. The participant gets a turn to tell the
  room itself, whatever the judgment reads (I-010B@7 `outcome-turn`).
- **The participant's memory (@5, #94 step 6)** — optional `memory`, the
  same facts and shape as the I-010C wake's `memory`, built for the same
  trigger: the participant's own recent moves and the threads. The judgment
  reads the message as the participant would, with what it said it would do,
  after that has left the window. The reference host builds it for every
  judgment, including recalled ones; it is absent while the memory is
  empty. The attention prompt explains it only to a judgment that carries
  it. The reference typed route does not pass it to its model yet. Since @7
  it shares I-010C@14's memory: a `message` own move may lack `event_id`.
- **Messages that arrived while the participant was busy (@6, #94 step 6;
  Zoe, 2026-10-06)** — optional `unattended_event_ids`: 1 to 3 messages by
  others, in `events` and newest first, that arrived while the participant
  was busy with its previous turn and got no turn of their own. The trigger
  is the newest message that arrived meanwhile, and the judgment reads these
  with it as one moment, the way a person catching up reads the newest
  message and glances back. Never the trigger; membership, authorship and
  order are runtime-adapter-only. The attention prompt explains them, and
  I-010B@8 asks one more question, only on a request that has them.

## I-010B AttentionDecisionV2@9

A tagged host-facing union on `status`:

- **`status: ok`** — carries `classifier_disposition`,
  `effective_disposition`, the closed `routing_audit` (below), the
  required sibling `reasons` audit field (an array of audit strings,
  possibly empty, that never enters the participant turn and is never a
  member of the routing-audit object), `evidence_event_ids`, `classifier`
  (`{name, provider?, model?}`), the required typed `answers` behind the
  judgment (@5, below), the optional
  `attention_advice` reading of the room (an array of at most 4
  `{note, evidence_event_ids}` items with notes of at most 400 characters,
  allowed on every pair since @4). The declared
  classifier/effective pairs validate,
  each mapped onto its applied valve (FR-006):

  | Transition | Applied valve | `override_cause` |
  |---|---|---|
  | `WAKE -> WAKE` | `none` | `none` |
  | `DEFER -> DEFER` | `classifier-defer` | `none` |
  | `SUPPRESS -> DEFER` | `margin-defer` or `policy-defer` | `margin` (margin valve); `suppression-disabled`, `recoverability-unproven`, or `outcome-turn` (@7) (policy valve) |
  | `SUPPRESS -> SUPPRESS` | `none` | `none` |

  Until @3, only `WAKE -> WAKE` could carry `attention_advice`. Zoe,
  2026-10-05 (#94): the reading reaches the participant on every turn it
  takes, so @4 allows it on every pair. A malformed item is dropped by the
  engine on its own and never fails the judgment.

  Classifier-DEFER and margin-DEFER stay separately auditable (S08); a
  widened suppression preserves its exact valve and override cause (S05).
  Every other pairing must be reported on the error branch — malformed
  evidence never supports suppression (S09).
- **`routing_audit` (the closed FR-005 audit set)** — a closed object
  recording the applied `valve` (`none`, `classifier-defer`,
  `margin-defer`, or `policy-defer`), the
  `override_cause` (`none`, `margin`, `suppression-disabled`,
  `recoverability-unproven`, or, since @7, `outcome-turn`), the
  `margin_status` (`active` or `retired`, recorded on every ok decision),
  the `effective_margin`, and the trusted `margin_source`. The
  cross-field rules are part of the contract: a margin counts as
  **applied** exactly when the valve is `margin-defer` — the
  `effective_margin` (a finite number in `[0, 1]`, inclusive of the exact
  boundary — `@2` amendment A2, c834e8c "a transition margin, when active,
  is a finite number within `[0,1]`"; the accepted `@1` shape wrongly
  excluded exactly `0`) is then required and is
  forbidden on every other valve, the override cause must be `margin`,
  and the margin status must be `active` (a retired margin cannot apply);
  the trusted `margin_source` may appear only on that margin-applied
  decision (optional there); valves `none`/`classifier-defer` pair with
  override cause `none`; and `policy-defer` pairs with a trusted policy
  cause.
- **`outcome-turn` (@7, #94 step 6)** — on a request whose `occasion` is
  `outcome`, a SUPPRESS judgment widens to DEFER through
  `policy-defer` with this cause, ahead of every other valve: the
  participant reports what its approved action did, so the turn always
  reaches it, with the reading as advice. Only such a request may use it,
  and on such a request every widening uses it (runtime-adapter-only).
- **Nunchi's own nod, removed in @9 (#94 step 7).** `@3` added the ACK
  disposition, the `ACK -> ACK` and `ACK -> DEFER` transitions, the
  `capability-defer` valve with the `ack-disabled` and `ack-unsupported`
  causes, and the `ack` authority audit, so Nunchi could react for the
  participant. Every visible move is now the participant's own (Zoe,
  2026-10-05), so `@9` removes all of them: a judgment whose most likely
  move is a "mhm" is `DEFER`, and the participant takes the turn. This is a
  breaking closed-union change; a `@9` consumer never receives ACK.
- **`answers` (@5)** — required on `status: ok` (Zoe, 2026-10-05, #94
  step 4). The model answers fixed typed questions about the judged
  message, and the core decides from them. Step 1: `conversation`, the
  probability that it is conversation a participant like this one could take
  part in; only a value below 0.5 selects `SUPPRESS`, and the margin valve
  widens a near call to `DEFER`. Step 2: `addressee` (`participant`, `room`,
  `someone_else`, `nobody`), `answered` and the optional `answered_by`
  pointer to the supplied message that answered it, `mid_thought`,
  `adds_something`, and `move` (`speak`, `mhm`, `wait`, `stay_quiet`): the
  most likely move selects `WAKE` for speak, and `DEFER` for a mhm (since
  @9; `ACK` before), wait, and stay quiet,
  with ties going to the move that pays more attention. Since @6 (#94 step
  5) step 2 also asks `asks`, whether the judged message asks someone in the
  room for something, and the optional `responds_to` pointer to the earlier
  supplied message it answers or responds to, the participant's own
  included; the participant's memory builds its threads from these. Yes/no
  answers are finite numbers in `[0, 1]`; a choice names exactly its
  options, each in `[0, 1]`, normalized by the core to sum to 1.
  `answered_by` and `responds_to` must name a supplied event
  (runtime-adapter-only); the core drops a pointer that does not, or that
  names the judged message, on its own. Since @8 (#94 step 6), a request
  with `unattended_event_ids` adds the optional `calls_for_participant`
  pointer: which of those messages still calls for the participant, asked of
  it or of the room and not yet answered. It must name one of the request's
  unattended messages (runtime-adapter-only); the core drops it otherwise.
  Step 1 never suppresses a judgment that names one, and the reading names
  it first, on both routes. The V1-era
  `legacy_verdict_confidences` vector that `answers` replaces is no longer
  allowed. A chat model answers the questions as one JSON object; a typed
  decision model answers them natively; both produce the same `answers`.
- **`status: bypass`** — exactly `cause: "preattention-disabled"` and
  `request_id`, nothing else. The full FR-005 exclusion set applies
  identically everywhere: no classifier/effective disposition, classifier
  audit, reasons, evidence, legacy confidence vector, routing audit, or
  advice. Bypass is non-social and fabricates no model judgment.
- **`status: error`** — the operational branch: the complete error object is
  `{code, detail}`, both required (FR-005, FR-014). `code` is the authority's
  open string — not a locally narrowed enum; example values in use include
  `malformed-model-output`, `invalid-transition`,
  `invalid-legacy-confidence`, `provider-failure`, and `runtime-failure`, but
  any non-empty string is schema-valid. `request_id` is optional on both the
  pre-validation and post-validation branches (a pre-validation error may
  occur before a request ID is assignable); an optional `classifier` audit is
  present only when the error occurred after classifier invocation.

## I-010C ParticipantWakeV2@14

The normal-turn input materializes `self`, `room`, `actors`, `events`,
`trigger_event_id`, `coverage`, and optional `continuation` directly —
the same field shapes as `AttentionRequestV2` — not a wrapped
`observation` reference or classifier projection (FR-014). A separate
`attention` object carries the explicit `source` (`WAKE`, `DEFER`,
`ERROR_FALLBACK`, or the non-social `PREATTENTION_BYPASS`; `ACK` until @13)
and, when
`source` is `WAKE` or `DEFER` (since @3), the model's reading of the room:
optional `advice` (an array of `{note, evidence_event_ids}`), optional
`evidence_event_ids`, and optional `judged_through_event_id`, the newest
event the reading saw, which must name an event in the wake and appears
only with a reading. The host keeps each reading item whose citations are
still in the fresh wake and drops the rest one by one. `ERROR_FALLBACK` and
`PREATTENTION_BYPASS` have no model judgment, so those wakes carry no
reading. There is no
separate participant "budgets" field — the wake's own `coverage` (computed
when the packet was materialized for the participant) carries the
independent participant event/byte budget (S15). The contract contains no
admission meta-question and no composed reply.

Since @4 (#94 step 5) a wake may carry `memory`: `own_moves`, the
participant's own recent moves in the room, oldest first. Each move is one
closed shape: a `message` (`event_id`, `text`), a `reply` or `reaction`
(`event_id`, `about_event_id`, and `text` or `reaction`), or a `silence`
(`about_event_id`, `at`); messages, replies and reactions may carry `at`, and
`text` is at most 280 characters. Visible moves come from the room's
retained history; the host records a silence when a turn ends without an
action. The pointers may name messages that have left the wake's window.
Memory is facts with pointers, never a verdict, an obligation, or a work
queue, and old moves fade: the reference host keeps the newest 8 visible
moves and the latest 3 silences within a day, and a silence goes once its
message is no longer retained.

Since @5 (#94 step 5) `memory` may also carry `threads`, and carries
`own_moves`, `threads`, or both, each a non-empty array when present. A
thread starts at a message by someone else that attention judged to ask for
something (`asks` and `conversation` at least 0.5), or at one of the
participant's own messages that someone responded to. It carries
`event_id`, `author_id`, `text` (at most 280 characters), optional `at`,
`addressed_to` (one of the `addressee` options, only on others' asks), and
`responses`: at most 4 `{event_id, author_id, text}` items for the first later
messages by others that reply to it on the platform, that attention judged to
respond to it (`responds_to`), or that attention named as having answered it
(`answered_by`), with what each said (at most 280 characters): a response is
not always an answer. An empty `responses` array means none has yet; it is a
fact, not a request to answer. The reference host keeps the judgments of the
newest 64 messages and shows the newest 6 threads within a day, leaves the
message the turn is about out of the threads and their responses (its reading
describes it), and forgets the judgments on restart. A message observed but
never judged starts no thread. Since #94 step 6, messages that arrive while the
participant is mid-turn are judged: the newest gets the next opportunity, and
up to 3 that it replaced are judged for the memory alone just before it.

Since @6 (#94 step 5) any own move may carry `why`: the participant's own
reason at the time, in its own words, a non-empty string of at most 200
characters. It comes from the action the participant returned (silence
included) and is never posted. The reference host keeps it with a silence
directly, and joins it to a visible move once the room shows that move with
the same kind, target and words; a move the room never shows keeps its reason
to itself. A restart forgets the reasons.

Since @7 (#90, #94 step 5) an own move may be a `proposal`: one of the
participant's privileged proposals and what became of it. It carries
`proposal_id`, `about_event_id` (the message that prompted it), `capability`,
`status` (`awaiting_approval`, `done`, `failed`, `unknown`, `denied`,
`expired`, `withdrawn`, or `cancelled`), and `at`, and nothing about the
operation itself. It sits after the message it was about. The reference host
shows the newest 3, from the authorization coordinator.

Since @8 (#94 step 6) a wake may carry `pace`, the same facts as the attention
request's, computed for the fresh view the turn is built from.

Since @9 (#94 step 6) a wake may carry `occasion`, copied from the attention
request it follows: `pause` means the turn comes from a look again after the
room stayed quiet, not from a new message. Since @10 it may also be
`outcome`: an action the participant proposed was approved and has finished,
and its `proposal` own move says how it ended. Nunchi never reports the
outcome in the room; the participant does, if it still helps.

Since @11 (#94 step 6) an own move about a message (`reply`, `reaction`,
`silence`, `proposal`) may carry `about_author_id` and `about_text`, together:
who wrote that message and what it said, at most 280 characters, while the
message is retained and is someone else's. A person remembers what they
replied to, so the move still makes sense once the message has left the
window; attention's request (I-010A@5) carries the same memory.

Since @12 (#94 step 6; Zoe, 2026-10-06) the wake may carry
`unattended_event_ids`, copied from the attention request (I-010A@6) for
those still in the fresh view: messages by others that arrived while the
participant was busy with its previous turn and got no turn of their own,
newest first. The turn reads them with its trigger as one moment, and a
reply may target any of them.

Since @14 (#94 step 9d) a `message` own move may lack `event_id`. The harness
posted that message itself (`HarnessDelivery`), and the room has not shown it
back: some harnesses hide their agent's own messages from plugins. The
reference host remembers it by its text and time, just after the message the
turn was about, until the room shows a message by the participant with the
same words after that one; then the room's copy stands. Like a silence, it
goes once the message it followed is no longer retained, and a restart
forgets it. Attention's request (I-010A@7) carries the same memory.

## I-010D ContextContinuationV2@1

The continuation capability itself lives on `I-010A`/`I-010C`'s
`continuation` field; this interface covers only the fetch request/page
pair that capability authorizes — a `oneOf` over two bare shapes with no
`interface`/`version`/`kind` envelope (FR-014):

- **Fetch request** — `request_id`, `handle_id`, `direction`
  (`before`/`after`/`around`), `anchor_event_id` (defaults to the trigger
  for `before`/`after`, required for `around`), optional opaque `cursor`,
  and positive `max_events`/`max_bytes`.
- **Fetch page** — `request_id`, `handle_id`, `room_id`,
  `continuity_scope_id`, `direction`, `anchor_event_id`, the actor map,
  ordered typed `events` (same union as the request), returned
  `coverage`, and optional opaque `next_cursor` (absent means the binding
  is exhausted).

Since 2026-10-05 (#94 step 3) the participant's own turn no longer fetches
through this interface: it reads the live room through the host's view
(see `docs/platform-v2.md`, "The participant's view of the room"), and the
continuation capability serves the attention request's availability flags.

Handles, cursors, and fetch credentials are host-only and forbidden from
the classifier projection; the classifier sees coverage and expansion
capability booleans only (FR-004/FR-009). A fetch request carries no
inline binding fields — the host's actual call context is compared
independently against the issuing continuation capability's exact
`bound_to` at fetch time (rejection R10); a known, unexpired handle alone
does not establish correct binding or bounded authorization — see the
runtime-adapter-only rules below.

## I-010E AttentionReceiptV2@5

Immutable, append-only stage records correlated by `request_id`, in the
canonical order `observation -> attention -> participant-host ->
transport` (FR-010). Each record names its `stage`, its `writer`, and a
  stage-shaped `body` carrying the selected telemetry (FR-014). Classifier
  receipts preserve the same exact transition, valve, and override-cause
  matrix as `AttentionDecisionV2`:

| Stage | Owning writer | Body |
|---|---|---|
| `observation` | `observation-provider` | `schema_version` (must be `2`), `trigger_event_id`, `continuity_scope_id`, `event_count`, `byte_count` (canonical actor-map plus event bytes), `coverage`, `included_event_ids` |
| `attention` | `attention-engine` | classifier outcome (`classifier_disposition`, `effective_disposition`, `classifier`, `evidence_event_ids`, `routing_audit`, required `policy_provenance`, plus, on a legacy ACK record only, `ack: {reaction, policy_provenance, permissions_revision}`) or operational error (`error: {code, detail}`, both required, plus `wake_action`/`policy_provenance` present together exactly when an explicit operator override to the shared `WAKE` default applied) or bypass (`classifier_not_invoked: true`, `cause: "preattention-disabled"`, `policy_provenance`) — three mutually exclusive shapes |
| `participant-host` | `participant-host` | `wake_source`, `packet_event_count`, `packet_byte_count` (canonical actor-map plus event bytes), `delivered_event_ids`, `expansion_calls`, `invoked`, `outcome` (`sent`/`silent`/`unknown`) |
| `transport` | `transport` | `delivery: sent/failed/unknown/unavailable`, optional `detail` |

**`@2` amendment A1** (`evidence/v2/attention/dependency-010-post-acceptance-blocker.md`,
discovered during slice 030 planning after slice 010's `@1` acceptance): the
selected design at `c834e8c` requires the effective policy and its source to
be inspectable in receipts, and an operator's explicit `NO_WAKE` override to
the shared `WAKE` error-handling default to be separately receipted as
operational failure policy, never as a social disposition. `@1` gave
`policy_provenance` only to the trusted-bypass body and gave the error body
no way to distinguish an operator override from an ordinary failure; `@2`
adds the classifier-outcome body's required `policy_provenance` and the
error body's conditional `wake_action`/`policy_provenance` pair. `@1`
consumers must migrate to `@2` before consuming attention-stage receipts;
`margin_source` on `routing_audit` remains scoped to the margin-defer valve
and does not serve as general policy provenance.

`@3` adds ACK dispositions, ACK participant-host source, and the ACK-only
authority audit. An ACK host record has `invoked: false`; the following
transport record alone reports whether the one reaction was sent, failed,
unknown, or unavailable. `@2` consumers must upgrade before receiving ACK
receipts. `@4` (#94 step 6) lets the attention stage record the I-010B@7
`outcome-turn` widening. `@5` (#94 step 7) removes Nunchi's own nod: no new
record carries an ACK disposition, ACK widening, `ack` audit, or ACK
participant-host source. A record written before `@5` with those facts still
validates, read-only, so an older journal loads.

The stage-to-writer binding is part of the public per-record contract
(FR-010): each stage names its single directly observing owner per the
closed map above, and a record attributing one stage to another stage's
owner — for example `stage: "observation"` written by `transport` — is
invalid as a single document in both validators, independent of the
stream-level checks below.

A prefix-partial receipt — for example a contributed stream awaiting its
transport stage, or a participant-silence outcome ending at
`participant-host` — is valid-in-progress. Each owner appends only its own
stage, never mutates a prior record, and never fills a future stage.
Participant silence (S07) stays distinct from model suppression (which ends
the stream at `attention`) and from non-invocation; the observed outcome is
`sent`/`silent`/`unknown`, never a handled/owed social state. A bypass
attention record marks `classifier_not_invoked: true` and carries its
trusted `cause`/`policy_provenance`.

The participant-host outcome does not substitute for the transport result.
`silent` means the delegated participant returned no action. `sent` is valid
only when the host can attest an irreversible handoff to the separately owned
transport boundary. `unknown` means an action exists but that handoff is not
yet truthfully established. The shared runtime persists `unknown` before any
native effect and lets the following transport record exclusively settle
`sent`/`failed`/`unknown`/`unavailable`; a deadline crossed during host-receipt
persistence therefore makes zero native calls and never leaves a false
participant-host `sent`.

## Validation model (FR-012)

The runtime package stays dependency-free: shipped runtime validation is
explicit Python-stdlib code. JSON Schema Draft 2020-12 is the portable test
oracle through dev/test-only `jsonschema==4.26.0`, and one shared
conformance corpus exercises both validators:

- **Corpus**: `evals/v2/contract/attention-request/`,
  `evals/v2/contract/attention-decision/`, and
  `evals/v2/contract/downstream/`, each holding `cases.jsonl` and its
  authoritative per-class `expected-counts.json` (updated in the same
  change as any corpus edit; counts are asserted loudly, and the on-disk
  corpus directory inventory is asserted closed at load time). The corpus
  also carries the FR-014 authority-conformance class: named cases drawn
  verbatim or field-complete from the selected design at `c834e8c`,
  schema-expressible and counted as their own manifest-tracked subset —
  never a fourth oracle-treatment class (CHK099).
- **Runner**: the `tests/v2/contract/` suite. The stdlib
  runtime-validation adapter lives in
  `tests/v2/contract/schema_helpers.py`.
- **The sole complete dual-validator run** is the exact offline command:

  ```sh
  uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'
  ```

  `--offline` fails rather than accessing the network, and any `jsonschema`
  version other than the pin is treated as an absent oracle. Under the
  repository baseline (`python3 -m unittest`) the stdlib adapter still runs
  the full corpus and must pass; oracle-side checks are skipped with an
  explicit counted skip (`baseline-oracle-absence`), kept separate from the
  per-class oracle skips (`oracle-class-skip`) below. No silent skips.

The corpus is partitioned by expressiveness with a fixed per-class oracle
treatment:

| Partition class | Validators | Oracle treatment |
|---|---|---|
| `schema-expressible` (incl. the authority-conformance subset) | both | identical expected result |
| `id-uniqueness` | runtime adapter | expected-valid (document-shaped) |
| `timestamp-order` | runtime adapter | expected-valid (document-shaped) |
| `advice-citation` | runtime adapter | expected-valid (document-shaped) |
| `trigger-membership` | runtime adapter | expected-valid (document-shaped) |
| `actor-reference-integrity` | runtime adapter | expected-valid (document-shaped) |
| `binding-expiry` | runtime adapter | class-skipped (behavioral) |
| `receipt-sequence` | runtime adapter | class-skipped (behavioral) |

Document-shaped relational classes are oracle-expected-valid because each
document is schema-valid in isolation; behavioral/sequence classes are
oracle-class-skipped because there is no single document to validate.
Per-class counts are asserted so neither partition can silently shrink.

## Runtime-adapter-only semantic rules

These rules are part of the `@1` contracts but live outside the schemas;
every runtime consumer must enforce them in its stdlib adapter:

1. **Cross-item ID uniqueness** (FR-003/FR-009): event IDs are unique
   within one request and continuity scope; a duplicate rejects. A
   continuation page whose event IDs collide with its originating request
   rejects at fetch time under the exact merge-identity rule.
2. **Timestamp-versus-order agreement** (FR-003): the event array order is
   authoritative; parseable timestamps must not contradict it
   (non-decreasing). An omitted or unparseable timestamp is exempt as an
   unknown platform fact — the authority represents unknown timestamp by
   omission, not `null` (rejection R7).
3. **Cross-document advice citations** (FR-013): every advice
   `evidence_event_ids` entry — on a decision's `attention_advice` items or
   a wake's `attention.advice` items/`attention.evidence_event_ids` — must
   name an event supplied in the correlated request (for a wake, its own
   materialized events); a citation of a nonexistent event rejects.
4. **Trigger membership** (FR-003): `trigger_event_id` must name an event
   present in `events`.
5. **Actor-map reference integrity** (FR-002/FR-003, rejection R8/R9):
   `self.actor_id` and every typed event's actor reference — message/
   reaction `author_id`, message `mentioned_actor_ids`, membership
   `subject_actor_id` and optional `caused_by_actor_id` — must resolve to a
   key present in `actors`; a reference absent from the actor map is a
   dangling opaque string, not a valid binding, and rejects. One shared
   validator enforces this identically on `AttentionRequestV2` and
   `ParticipantWakeV2`, which materialize the identical `self`/`actors`/
   `events` field shapes — not a partial, per-schema reimplementation.
6. **Fetch-time binding/expiry state** (FR-004/FR-009, rejection R10): a
   fetch validates only if its `handle_id` was issued for the continuity
   scope and is unexpired at fetch time; its issued capability's exact
   `bound_to` (`participant_id`, `room_id`, `continuity_scope_id`,
   `trigger_event_id`) matches the host's actual call context; the
   requested `direction` is authorized by that capability's
   `can_fetch_before`/`can_fetch_after`/`can_fetch_around_event` flag; the
   requested `max_events`/`max_bytes` do not exceed the capability's issued
   `max_events_per_fetch`/`max_bytes_per_fetch` caps; and any cursor was
   minted under that same handle. Expired handles, an exact-binding
   mismatch, an unauthorized direction, a cap overrun, and cross-handle
   cursor reuse all reject as binding-validation failures. The fetch
   request itself carries no inline binding fields (FR-014) — the host call
   context is compared against the capability's `bound_to` independently;
   a known, unexpired handle alone does not establish correct binding or
   bounded authorization.
7. **Receipt-stage sequence rules** (FR-010): one request ID per stream,
   canonical stage order as a prefix, each stage appended at most once,
   and stream-level writer ownership. These are the multi-record checks;
   the per-record stage-to-writer binding itself is schema-expressible
   and enforced by both validators on every single record, in addition.

## Examples

The selected design's own example attention request, which validates
verbatim (FR-014, `REQ-AUTH-001` in the authority-conformance corpus):

```json
{
  "schema_version": 2,
  "request_id": "discord:room:152:event:203",
  "self": {"participant_id": "vigil", "actor_id": "discord:user:149", "names": ["Vigil", "Codex"], "role": "participant"},
  "room": {"platform": "discord", "id": "152", "continuity_scope_id": "discord:channel:152", "name": "nunchi-room", "kind": "group"},
  "actors": {
    "discord:user:149": {"display_name": "Vigil", "kind": "bot"},
    "discord:user:42": {"display_name": "Zoe", "kind": "human"}
  },
  "events": [
    {"id": "discord:message:201", "type": "message", "author_id": "discord:user:42", "timestamp": "2026-07-11T12:00:00Z", "text": "Could you review the latest flow?", "mentioned_actor_ids": [], "mentions_room": false},
    {"id": "discord:message:203", "type": "message", "author_id": "discord:user:42", "timestamp": "2026-07-11T12:01:00Z", "text": "Vigil, especially the participant wake.", "reply_to_event_id": "discord:message:201", "thread_root_event_id": "discord:message:201", "mentioned_actor_ids": ["discord:user:149"], "mentions_room": false}
  ],
  "trigger_event_id": "discord:message:203",
  "coverage": {"max_events": 2, "max_bytes": 4096, "max_age_seconds": 86400, "has_more_before": true, "has_more_after": false, "has_gaps": false, "truncated_by": ["events"], "continuity": "restart-safe", "has_restart_gap": false},
  "continuation": {
    "handle_id": "ctx:discord:152:203",
    "bound_to": {"participant_id": "vigil", "room_id": "152", "continuity_scope_id": "discord:channel:152", "trigger_event_id": "discord:message:203"},
    "can_fetch_before": true, "can_fetch_after": false, "can_fetch_around_event": true,
    "max_events_per_fetch": 20, "max_bytes_per_fetch": 32768
  }
}
```

A governed suppression (`status: ok`, `SUPPRESS -> SUPPRESS`; step 1 found
the judged message is not conversation):

```json
{
  "status": "ok",
  "request_id": "req-0100",
  "classifier_disposition": "SUPPRESS",
  "effective_disposition": "SUPPRESS",
  "routing_audit": {"valve": "none", "override_cause": "none", "margin_status": "active"},
  "reasons": ["conversation 0.05", "addressee nobody 1.00", "move stay_quiet 0.90"],
  "evidence_event_ids": ["e1"],
  "classifier": {"name": "nunchi-classifier"},
  "answers": {
    "conversation": 0.05,
    "addressee": {"participant": 0.0, "room": 0.0, "someone_else": 0.0, "nobody": 1.0},
    "answered": 0.0,
    "mid_thought": 0.0,
    "adds_something": 0.0,
    "move": {"speak": 0.0, "mhm": 0.0, "wait": 0.1, "stay_quiet": 0.9}
  }
}
```

A margin-widened deferral (`SUPPRESS -> DEFER`; the margin applied, so the
routing audit records its effective width):

```json
{
  "status": "ok",
  "request_id": "req-0102",
  "classifier_disposition": "SUPPRESS",
  "effective_disposition": "DEFER",
  "routing_audit": {"valve": "margin-defer", "override_cause": "margin", "margin_status": "active", "effective_margin": 0.12},
  "reasons": ["conversation 0.47", "addressee nobody 0.60", "move stay_quiet 0.70"],
  "evidence_event_ids": ["e1"],
  "classifier": {"name": "nunchi-classifier"},
  "answers": {
    "conversation": 0.47,
    "addressee": {"participant": 0.1, "room": 0.2, "someone_else": 0.1, "nobody": 0.6},
    "answered": 0.1,
    "mid_thought": 0.1,
    "adds_something": 0.2,
    "move": {"speak": 0.1, "mhm": 0.05, "wait": 0.15, "stay_quiet": 0.7}
  }
}
```

A non-social preattention bypass:

```json
{
  "status": "bypass",
  "request_id": "req-0101",
  "cause": "preattention-disabled"
}
```

A participant-silence receipt record (the S07 stream ends at this stage):

```json
{
  "request_id": "req-0100",
  "stage": "participant-host",
  "writer": "participant-host",
  "body": {
    "wake_source": "WAKE",
    "packet_event_count": 3,
    "packet_byte_count": 512,
    "delivered_event_ids": ["e1", "e2", "e3"],
    "expansion_calls": 0,
    "invoked": true,
    "outcome": "silent"
  }
}
```

## Versioning and change control

`@1` is the first V2 execution version. A breaking edit requires a version
bump and re-verification of every consumer. `I-010B@5` replaced the
`legacy_verdict_confidences` vector, fixed for `@1` through `@4` (FR-007),
with the required typed `answers`, and `@6` made `asks` a required answer; margin retirement still flips only the
reported `margin_status`, never the schema. Each runtime must pass its adapter against the same contract corpus
before integration.
Evidence for the contract runs lives at
`evidence/v2/contract/attention-request.jsonl`,
`evidence/v2/contract/attention-decision.jsonl`,
`evidence/v2/contract/downstream.jsonl`,
`evidence/v2/contract/privileged-action-authorization.jsonl`, and the scene
manifest
`evidence/v2/contract/README.md`.
