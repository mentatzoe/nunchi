# Nunchi V2 Contracts (I-010A–I-010E, version `@1`)

**Owner**: `v2-contract-owner` (slice `010`). Only this owner edits
`schemas/v2/**`; a dependent slice requests changes through an explicit
return handoff followed by re-analysis, never by editing a shared schema
directly.

**Status**: these five contracts are the shared seam consumed by the V2
program slices. V1 remains the current product until the atomic V2 merge is
verified on `main`; nothing in this document claims the V2 lifecycle is the
running product today.

**Machine-readable contracts** (JSON Schema Draft 2020-12):

| Interface | Version | Schema path |
|---|---|---|
| `I-010A AttentionRequestV2` | `@1` | [`schemas/v2/attention-request.schema.json`](../../schemas/v2/attention-request.schema.json) |
| `I-010B AttentionDecisionV2` | `@1` | [`schemas/v2/attention-decision.schema.json`](../../schemas/v2/attention-decision.schema.json) |
| `I-010C ParticipantWakeV2` | `@1` | [`schemas/v2/participant-wake.schema.json`](../../schemas/v2/participant-wake.schema.json) |
| `I-010D ContextContinuationV2` | `@1` | [`schemas/v2/context-continuation.schema.json`](../../schemas/v2/context-continuation.schema.json) |
| `I-010E AttentionReceiptV2` | `@1` | [`schemas/v2/attention-receipt.schema.json`](../../schemas/v2/attention-receipt.schema.json) |

Every document carries the envelope fields `interface` (the exact interface
name), `version` (the number `1`), and a non-empty `request_id` that
correlates the request, decision, wake, continuation, and receipt records
for one attention pass. All five contracts are closed: an unexpected
property rejects. V1 envelopes, reply-bearing fields, inferred-roster
claims, and `handled`/`open`/`owed`/permission ledger state reject
everywhere; there is no V1 translation bridge (FR-011).

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
  `self.actor_id` with `attestation` of `transport` or `host` (FR-002).
  Optional `self.loose` names/role/description never establish authorship;
  an alias collision with another observed actor is representable without
  becoming an identity claim.
- **Room and continuity scope** — `room.room_id` and
  `room.continuity_scope`.
- **Observed/referenced actors** — the observed cast only, never an
  inferred full roster.
- **Ordered native events** — array order is authoritative. Each event
  carries a stable `event_id`, `actor_id`, `kind`
  (`message`/`reply`/`reaction`/`membership`/`thread`), a timestamp that is
  a non-empty string or explicitly `null` (unknown), literal kind-keyed
  relation facts (`reply_to`, `reaction`, `membership` appear exactly on
  their own kind), actor-targeted `mentions`, and the separate boolean
  `mentions_room` (FR-003).
- **One included trigger** — `trigger_event_id` must name an event in
  `events` (runtime-adapter-only rule; see the partition below).
- **Honest coverage** — `truncated`, `gaps`, `visibility`, `continuity`,
  and `more_events` with explicit `unknown` members; `session-only`
  continuity and unknown visibility are never upgraded by inference.
- **Positive budgets** — independent `max_events` and `max_bytes`, each an
  integer `>= 1` (S15).
- **Expansion capability booleans only** — `expansion.available` is the
  entire classifier-visible continuation surface. The continuation handle,
  binding, cursor, expiry, and any other opaque fetch authority are
  host-only and reject inside a request (FR-004).

## I-010B AttentionDecisionV2@1

A tagged host-facing union on `status`:

- **`status: ok`** — carries `classifier_disposition`,
  `effective_disposition`, the closed `routing` audit (below), the
  required sibling `reasons` audit field (an array of audit strings,
  possibly empty, that never enters the participant turn and is never a
  member of the routing-audit object), `evidence_event_ids`,
  `classifier_audit` (model, optional `prompt_sha256`, optional
  `latency_ms`), the optional conditional `legacy_confidence` vector
  (FR-007, below), and optional WAKE-only `advice`. Exactly four
  classifier/effective pairs validate, each mapped onto its applied valve
  (FR-006):

  | Transition | Applied valve | `override_cause` | `advice` |
  |---|---|---|---|
  | `WAKE -> WAKE` | `none` | `none` | allowed (FR-013) |
  | `DEFER -> DEFER` | `classifier-defer` | `none` | forbidden |
  | `SUPPRESS -> DEFER` | `margin-defer` or `policy-defer` | `margin` (margin valve); `suppression-disabled` or `recoverability-unproven` (policy valve) | forbidden |
  | `SUPPRESS -> SUPPRESS` | `none` | `none` | forbidden |

  Classifier-DEFER and margin-DEFER stay separately auditable (S08); a
  widened suppression preserves its exact valve and override cause (S05).
  Every other pairing must be reported on the error branch — malformed
  evidence never supports suppression (S09).
- **`routing` (the closed FR-005 audit set)** — a closed object recording
  the applied `valve` (`none`, `classifier-defer`, `margin-defer`, or
  `policy-defer`), the `override_cause` (`none`, `margin`,
  `suppression-disabled`, or `recoverability-unproven`), the
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
- **`legacy_confidence` (FR-007, conditional)** — optional on
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
- **`status: bypass`** — exactly `cause: "preattention-disabled"` and the
  envelope, nothing else. The full FR-005 exclusion set applies
  identically everywhere: no classifier/effective disposition, classifier
  audit, reasons, evidence, legacy confidence vector, routing audit, or
  advice. Bypass is non-social and fabricates no model judgment.
- **`status: error`** — the operational branch: `error.kind` is one of
  `malformed-model-output`, `invalid-transition`,
  `invalid-legacy-confidence`, `provider-failure`, `runtime-failure`, with
  optional `detail`.

## I-010C ParticipantWakeV2@1

The normal-turn input: `source` (`WAKE`, `DEFER`, `ERROR_FALLBACK`, or the
non-social `PREATTENTION_BYPASS`), the embedded factual `observation`
(a complete `AttentionRequestV2` document), participant `budgets`, and
optional `advice`. Advice is valid only when `source` is `WAKE`; `DEFER`,
`ERROR_FALLBACK`, and `PREATTENTION_BYPASS` wakes are advice-free because
no classifier advice exists for those sources (FR-008/FR-013). The
contract contains no admission meta-question and no composed reply.

## I-010D ContextContinuationV2@1

Two document kinds under one interface:

- **`kind: fetch-request`** — `handle`, full `binding` (participant, room,
  continuity scope, trigger), `cursor` (opaque string or `null`),
  `expires_at`, and positive `budgets`.
- **`kind: fetch-page`** — `handle`, ordered native `events` (same event
  shape as the request), `cursor_next` (or `null`), and returned
  `coverage`.

Handles, bindings, cursors, expiry values, and fetch credentials are
host-only and forbidden from the classifier projection; the classifier sees
coverage and expansion capability booleans only (FR-004/FR-009). Binding
validation happens at fetch time — see the runtime-adapter-only rules
below.

## I-010E AttentionReceiptV2@1

Immutable, append-only stage records correlated by `request_id`, in the
canonical order `observation -> attention -> participant-host ->
transport` (FR-010). Each record names its `stage`, its `writer`, and a
stage-shaped `body`:

| Stage | Owning writer | Body |
|---|---|---|
| `observation` | `observation-provider` | `event_count`, `visibility` |
| `attention` | `attention-engine` | classifier outcome (`classifier_disposition`, `effective_disposition`, `policy_provenance`) or operational error (`error_kind`, `detail`) or bypass (`classifier_not_invoked: true`, `bypass_provenance`) — three mutually exclusive shapes |
| `participant-host` | `participant-host` | `outcome: contributed` (with `action_ref`) or `outcome: silence` |
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
the stream at `attention`) and from non-invocation. Unknown and unavailable
remain explicit outcomes; a bypass attention record marks
`classifier_not_invoked: true` and carries its trusted
`bypass_provenance` (`policy: "preattention-disabled"`, `attested_by`).

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
  corpus directory inventory is asserted closed at load time).
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
| `schema-expressible` | both | identical expected result |
| `id-uniqueness` | runtime adapter | expected-valid (document-shaped) |
| `timestamp-order` | runtime adapter | expected-valid (document-shaped) |
| `advice-citation` | runtime adapter | expected-valid (document-shaped) |
| `trigger-membership` | runtime adapter | expected-valid (document-shaped) |
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
   authoritative; non-null parseable timestamps must not contradict it
   (non-decreasing). An explicitly `null` or unparseable timestamp is
   exempt as an unknown platform fact.
3. **Cross-document advice citations** (FR-013): every
   `advice.evidence_event_ids` entry must name an event supplied in the
   request (for a wake packet, in its embedded observation); a citation of
   a nonexistent event rejects.
4. **Trigger membership** (FR-003): `trigger_event_id` must name an event
   present in `events`.
5. **Fetch-time binding/expiry state** (FR-004/FR-009): a fetch validates
   only if the handle was issued for the continuity scope, is unexpired at
   fetch time, the binding is identical to the issued binding, and any
   cursor was minted under the same handle/binding; expired handles and
   cross-binding cursor reuse reject as binding-validation failures.
6. **Receipt-stage sequence rules** (FR-010): one request ID per stream,
   canonical stage order as a prefix, each stage appended at most once,
   and stream-level writer ownership. These are the multi-record checks;
   the per-record stage-to-writer binding itself is schema-expressible
   and enforced by both validators on every single record, in addition.

## Examples

A minimal valid `AttentionRequestV2` document:

```json
{
  "interface": "AttentionRequestV2",
  "version": 1,
  "request_id": "req-0100",
  "self": {"participant_id": "vigil", "actor_id": "discord:9001", "attestation": "transport"},
  "room": {"room_id": "discord:room:42", "continuity_scope": "discord:room:42#2026-07"},
  "actors": [{"actor_id": "discord:1001", "relation": "observed"}],
  "events": [
    {
      "event_id": "e1",
      "actor_id": "discord:1001",
      "kind": "message",
      "timestamp": "2026-07-17T01:00:00Z",
      "content": "hey @Vigil can you take the deploy?",
      "mentions": ["discord:9001"],
      "mentions_room": false
    }
  ],
  "trigger_event_id": "e1",
  "coverage": {"truncated": false, "gaps": "none", "visibility": "complete", "continuity": "session-only", "more_events": "unknown"},
  "budgets": {"max_events": 50, "max_bytes": 65536},
  "expansion": {"available": false}
}
```

A governed suppression (`status: ok`, `SUPPRESS -> SUPPRESS`; the margin
is active, so the legacy vector is required per the conditional FR-007
rule):

```json
{
  "interface": "AttentionDecisionV2",
  "version": 1,
  "request_id": "req-0100",
  "status": "ok",
  "classifier_disposition": "SUPPRESS",
  "effective_disposition": "SUPPRESS",
  "routing": {"valve": "none", "override_cause": "none", "margin_status": "active"},
  "reasons": ["no direct address and no open question"],
  "evidence_event_ids": ["e1"],
  "classifier_audit": {"model": "openrouter/example-model"},
  "legacy_confidence": {"PASS": 0.8, "ACK": 0.1, "ASK": 0.05, "SPEAK": 0.05}
}
```

A margin-widened deferral (`SUPPRESS -> DEFER`; the margin applied, so the
routing audit records its effective width):

```json
{
  "interface": "AttentionDecisionV2",
  "version": 1,
  "request_id": "req-0102",
  "status": "ok",
  "classifier_disposition": "SUPPRESS",
  "effective_disposition": "DEFER",
  "routing": {"valve": "margin-defer", "override_cause": "margin", "margin_status": "active", "effective_margin": 0.12},
  "reasons": ["candidate suppression inside the protective margin"],
  "evidence_event_ids": ["e1"],
  "classifier_audit": {"model": "openrouter/example-model"},
  "legacy_confidence": {"PASS": 0.55, "ACK": 0.2, "ASK": 0.15, "SPEAK": 0.1}
}
```

A non-social preattention bypass:

```json
{
  "interface": "AttentionDecisionV2",
  "version": 1,
  "request_id": "req-0101",
  "status": "bypass",
  "cause": "preattention-disabled"
}
```

A participant-silence receipt record (the S07 stream ends at this stage):

```json
{
  "interface": "AttentionReceiptV2",
  "version": 1,
  "request_id": "req-0100",
  "stage": "participant-host",
  "writer": "participant-host",
  "body": {"outcome": "silence"}
}
```

## Versioning and change control

`@1` is the first V2 execution version. A breaking edit requires an
explicit owner handoff and dependent re-analysis and lands as `@2`; the
optional `legacy_confidence` field, its exact four-key shape, and its
conditional margin-active-suppression requirement are permanent for `@1`
(FR-007) — margin retirement flips only the reported `margin_status`,
never the schema. The slice 010 handoff packet names the exact contract
commit and corpus revision; each downstream runtime owner must pass its own
stdlib adapter over the identical corpus revision before its own handoff.
Evidence for the contract runs lives at
`evidence/v2/contract/attention-request.jsonl`,
`evidence/v2/contract/attention-decision.jsonl`,
`evidence/v2/contract/downstream.jsonl`, and the scene manifest
`evidence/v2/contract/README.md`.
