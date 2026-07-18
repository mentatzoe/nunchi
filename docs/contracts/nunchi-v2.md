# Nunchi V2 Contracts (I-010A–I-010E, version `@1`)

**Owner**: `v2-contract-owner` (slice `010`). Only this owner edits
`schemas/v2/**`; a dependent slice requests changes through an explicit
return handoff followed by re-analysis, never by editing a shared schema
directly.

**Status**: these five contracts are the shared seam consumed by the V2
program slices. V1 remains the current product until the atomic V2 merge is
verified on `main`; nothing in this document claims the V2 lifecycle is the
running product today.

**Field-level authority**: the selected Aleph Vault design at `c834e8c`
(`projects/shared/nunchi/technical-design.md`) is the field-level naming and
shape authority for all five interfaces (FR-014); the program-canonical
interface names and versions (`I-010A`–`I-010E` at `@1`) are this slice's own
vocabulary layered over that same field inventory. A document the selected
design declares valid that either validator rejects is a contract defect,
never resolved by narrowing the corpus.

**Machine-readable contracts** (JSON Schema Draft 2020-12):

| Interface | Version | Schema path |
|---|---|---|
| `I-010A AttentionRequestV2` | `@1` | [`schemas/v2/attention-request.schema.json`](../../schemas/v2/attention-request.schema.json) |
| `I-010B AttentionDecisionV2` | `@1` | [`schemas/v2/attention-decision.schema.json`](../../schemas/v2/attention-decision.schema.json) |
| `I-010C ParticipantWakeV2` | `@1` | [`schemas/v2/participant-wake.schema.json`](../../schemas/v2/participant-wake.schema.json) |
| `I-010D ContextContinuationV2` | `@1` | [`schemas/v2/context-continuation.schema.json`](../../schemas/v2/context-continuation.schema.json) |
| `I-010E AttentionReceiptV2` | `@1` | [`schemas/v2/attention-receipt.schema.json`](../../schemas/v2/attention-receipt.schema.json) |

Only the request carries an explicit generation tag, `schema_version: 2`
(the design's own field; there is no separate `interface`/`version`
envelope pair on any of the five documents — that was an attempt-2 local
invention the selected design does not carry). A non-empty `request_id`
correlates the request, decision, wake, and receipt records for one
attention pass. All five contracts are closed: an unexpected property
rejects. V1 envelopes, reply-bearing fields, inferred-roster claims, and
`handled`/`open`/`owed`/permission ledger state reject everywhere; there is
no V1 translation bridge (FR-011).

## The lifecycle at a glance

```text
observation  ->  AttentionRequestV2   (host assembles factual events)
             ->  AttentionDecisionV2  (ok | bypass | error)
             ->  ParticipantWakeV2    (WAKE | DEFER | ERROR_FALLBACK | PREATTENTION_BYPASS)
             ->  ContextContinuationV2 (optional host-mediated bounded expansion)
             ->  AttentionReceiptV2   (immutable staged telemetry, one record per stage)
```

These are lifecycle boundaries, not social state: no contract carries a
composed reply, an admission meta-answer, or a social permission ledger.

## I-010A AttentionRequestV2@1

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

## I-010B AttentionDecisionV2@1

A tagged host-facing union on `status`:

- **`status: ok`** — carries `classifier_disposition`,
  `effective_disposition`, the closed `routing_audit` (below), the
  required sibling `reasons` audit field (an array of audit strings,
  possibly empty, that never enters the participant turn and is never a
  member of the routing-audit object), `evidence_event_ids`, `classifier`
  (`{name, provider?, model?}`), the optional conditional
  `legacy_verdict_confidences` vector (FR-007, below), and optional
  WAKE-only `attention_advice` (an array of `{note, evidence_event_ids}`,
  not a single object). Exactly four classifier/effective pairs validate,
  each mapped onto its applied valve (FR-006):

  | Transition | Applied valve | `override_cause` | `attention_advice` |
  |---|---|---|---|
  | `WAKE -> WAKE` | `none` | `none` | allowed (FR-013) |
  | `DEFER -> DEFER` | `classifier-defer` | `none` | forbidden |
  | `SUPPRESS -> DEFER` | `margin-defer` or `policy-defer` | `margin` (margin valve); `suppression-disabled` or `recoverability-unproven` (policy valve) | forbidden |
  | `SUPPRESS -> SUPPRESS` | `none` | `none` | forbidden |

  Classifier-DEFER and margin-DEFER stay separately auditable (S08); a
  widened suppression preserves its exact valve and override cause (S05).
  Every other pairing must be reported on the error branch — malformed
  evidence never supports suppression (S09).
- **`routing_audit` (the closed FR-005 audit set)** — a closed object
  recording the applied `valve` (`none`, `classifier-defer`,
  `margin-defer`, or `policy-defer`), the `override_cause` (`none`,
  `margin`, `suppression-disabled`, or `recoverability-unproven`), the
  `margin_status` (`active` or `retired`, recorded on every ok decision),
  the `effective_margin`, and the trusted `margin_source`. The
  cross-field rules are part of the contract: a margin counts as
  **applied** exactly when the valve is `margin-defer` — the
  `effective_margin` (a finite number in `(0, 1]`) is then required and is
  forbidden on every other valve, the override cause must be `margin`,
  and the margin status must be `active` (a retired margin cannot apply);
  the trusted `margin_source` may appear only on that margin-applied
  decision (optional there); valves `none`/`classifier-defer` pair with
  override cause `none`, and `policy-defer` pairs with
  `suppression-disabled` or `recoverability-unproven`.
- **`legacy_verdict_confidences` (FR-007, conditional)** — optional on
  `status: ok` and required exactly when the classifier disposition is
  `SUPPRESS` while the routing audit reports the margin `active`; a
  margin-active candidate suppression without a valid vector does not
  validate. A well-formed vector may accompany `WAKE`, `DEFER`, or a
  margin-retired `SUPPRESS` without invalidating them. When present:
  exactly the four keys `PASS`, `ACK`, `ASK`, `SPEAK`, each a finite
  number in `[0, 1]`. The optional field, its exact four-key shape, and
  this conditional requirement are fixed for the `@1` major version —
  margin retirement flips only the reported margin status under later
  evidence and is not a schema edit, while removing or reshaping the
  field is a breaking `@2` edit.
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

## I-010C ParticipantWakeV2@1

The normal-turn input materializes `self`, `room`, `actors`, `events`,
`trigger_event_id`, `coverage`, and optional `continuation` directly —
the same field shapes as `AttentionRequestV2` — not a wrapped
`observation` reference or classifier projection (FR-014). A separate
`attention` object carries the explicit `source` (`WAKE`, `DEFER`,
`ERROR_FALLBACK`, or the non-social `PREATTENTION_BYPASS`) and, only when
`source` is `WAKE`, optional `advice` (an array of `{note,
evidence_event_ids}`) and optional `evidence_event_ids`. `DEFER`,
`ERROR_FALLBACK`, and `PREATTENTION_BYPASS` wakes are advice-free because
no classifier advice exists for those sources (FR-008/FR-013). There is no
separate participant "budgets" field — the wake's own `coverage` (computed
when the packet was materialized for the participant) carries the
independent participant event/byte budget (S15). The contract contains no
admission meta-question and no composed reply.

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

Handles, cursors, and fetch credentials are host-only and forbidden from
the classifier projection; the classifier sees coverage and expansion
capability booleans only (FR-004/FR-009). A fetch request carries no
inline binding fields — a handle is permanently bound to its issuing
continuation capability, so a known, unexpired handle is by construction
the correct binding; binding/expiry validation happens at fetch time —
see the runtime-adapter-only rules below.

## I-010E AttentionReceiptV2@1

Immutable, append-only stage records correlated by `request_id`, in the
canonical order `observation -> attention -> participant-host ->
transport` (FR-010). Each record names its `stage`, its `writer`, and a
stage-shaped `body` carrying the selected telemetry (FR-014):

| Stage | Owning writer | Body |
|---|---|---|
| `observation` | `observation-provider` | `schema_version` (must be `2`), `trigger_event_id`, `continuity_scope_id`, `event_count`, `byte_count`, `coverage`, `included_event_ids` |
| `attention` | `attention-engine` | classifier outcome (`classifier_disposition`, `effective_disposition`, `classifier`, `evidence_event_ids`, `routing_audit`) or operational error (`error: {code, detail}`, both required) or bypass (`classifier_not_invoked: true`, `cause: "preattention-disabled"`, `policy_provenance`) — three mutually exclusive shapes |
| `participant-host` | `participant-host` | `wake_source`, `packet_event_count`, `packet_byte_count`, `delivered_event_ids`, `expansion_calls`, `invoked`, `outcome` (`sent`/`silent`/`unknown`) |
| `transport` | `transport` | `delivery: sent/failed/unknown/unavailable`, optional `detail` |

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

A governed suppression (`status: ok`, `SUPPRESS -> SUPPRESS`; the margin
is active, so the legacy vector is required per the conditional FR-007
rule):

```json
{
  "status": "ok",
  "request_id": "req-0100",
  "classifier_disposition": "SUPPRESS",
  "effective_disposition": "SUPPRESS",
  "routing_audit": {"valve": "none", "override_cause": "none", "margin_status": "active"},
  "reasons": ["no direct address and no open question"],
  "evidence_event_ids": ["e1"],
  "classifier": {"name": "nunchi-classifier"},
  "legacy_verdict_confidences": {"PASS": 0.8, "ACK": 0.1, "ASK": 0.05, "SPEAK": 0.05}
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
  "reasons": ["candidate suppression inside the protective margin"],
  "evidence_event_ids": ["e1"],
  "classifier": {"name": "nunchi-classifier"},
  "legacy_verdict_confidences": {"PASS": 0.55, "ACK": 0.2, "ASK": 0.15, "SPEAK": 0.1}
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

`@1` is the first V2 execution version. A breaking edit requires an
explicit owner handoff and dependent re-analysis and lands as `@2`; the
optional `legacy_verdict_confidences` field, its exact four-key shape, and
its conditional margin-active-suppression requirement are permanent for
`@1` (FR-007) — margin retirement flips only the reported `margin_status`,
never the schema. The slice 010 handoff packet names the exact contract
commit and corpus revision; each downstream runtime owner must pass its own
stdlib adapter over the identical corpus revision before its own handoff.
Evidence for the contract runs lives at
`evidence/v2/contract/attention-request.jsonl`,
`evidence/v2/contract/attention-decision.jsonl`,
`evidence/v2/contract/downstream.jsonl`, and the scene manifest
`evidence/v2/contract/README.md`.
