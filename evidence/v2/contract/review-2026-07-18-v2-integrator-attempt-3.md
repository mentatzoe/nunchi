# v2-integrator review — slice 010 attempt-3 candidate rejection

**Slice**: `010-v2-contract`

**Candidate commit**: `7f9e81460d570e078c4bcbacb138f81c1b291455`

**Handoff packet commit**: `6fa3996fd7cf92cd6157945245136a8c55cb69cc`

**Reviewed by**: v2-integrator

**Reviewed on**: 2026-07-18

**Decision**: REJECTED

## Decision basis

Attempt 3 fixes the large envelope and field-inventory divergence from attempt
2, makes the candidate identity single-valued, and reconciles task state. The
14 authority-conformance red-run counts are genuine and the complete packet
verification stack is green. The candidate still cannot be accepted because
direct comparison with the selected design and independent validator probes
found four uncovered contract/runtime defects.

### R7 — the operational-error contract still diverges from the selected response shape (CRITICAL)

The selected design at `c834e8c` defines the error member of
`AttentionResponse` as `error: { code: string, detail: string }`. Slice FR-005
likewise says the complete error object contains `code` and `detail`.

`schemas/v2/attention-decision.schema.json` instead requires only `code`, makes
`detail` optional, and narrows `code` from a string to five locally enumerated
values. `tests/v2/contract/schema_helpers.py` mirrors that same divergence in
`ERROR_KINDS` and `_validate_decision_error`; the attention-receipt error body
repeats it. `docs/contracts/nunchi-v2.md` then documents the local narrowing as
`detail?`.

Independent probes confirmed both wrong outcomes under both validators:

- `{status: error, error: {code: malformed-model-output}}` is accepted even
  though the authority requires `detail`;
- an error carrying an otherwise valid string code such as
  `transport-timeout` is rejected even though the authority declares `code`
  as `string`.

The four decision authority cases do not exercise either boundary, so their
green result does not establish the complete selected error shape.

The request/event schema carries a second direct type drift of the same kind:
the selected event union declares `timestamp?: string`, while the request
schema, stdlib adapter, corpus, and docs add `null` as a locally valid value.
Unknown timestamp remains representable by omission; `null` requires a higher-
authority contract amendment rather than a local extension.

### R8 — exact actor binding and referenced-cast integrity are not enforced (CRITICAL)

The selected design says `self.actor_id` points to the exact current-surface
account in `actors`, and that the actor map contains self, included-event
authors, structured mention targets, reaction actors, and membership actors.
The candidate validates none of those references.

This is not merely an uncovered hypothetical. The shared `_BASE_REQUEST` and
the ordinary attention-request corpus set `self.actor_id` to `discord:9001`
and cite that same ID as a structured mention target while omitting it from
`actors`. `test_valid_request_with_alias_collision_stays_valid` explicitly
asserts that the self actor is absent and then expects the document to validate.
Both the Draft 2020-12 schema and the stdlib adapter accept it. That turns the
supposed exact binding into a dangling opaque string and contradicts both the
selected `Self`/actor-map contract and the slice's own edge-case requirement
for missing referenced actors.

Cross-object membership is runtime-relational, but it is still a mandatory
adapter rule. The contract corpus needs explicit valid/invalid cases for self,
author, mention, reaction, subject, and causal-actor references; an empty actor
map key should also reject.

### R9 — the stdlib wake validator is not a faithful runtime mirror (HIGH)

`validate_participant_wake` duplicates only part of the shared `self` and
`room` validation. It checks required IDs but omits the schema's optional
`self.names`, `self.role`, `self.description`, `room.name`, and `room.kind`
types/enums. An independently constructed wake with `self.names = 7` and
`room.kind = "bogus"` produces two Draft 2020-12 errors and zero stdlib-adapter
errors.

The claimed dual-validator parity is therefore corpus-contingent: the current
cases simply do not reach the divergent fields. A downstream consumer using
the dependency-free adapter would accept documents rejected by the public
schema. Shared component validators should be reused rather than partially
reimplemented, and negative parity cases must cover every nested optional
field.

### R10 — fetch binding/capability enforcement was reduced below the selected contract (HIGH)

Removing attempt 2's inline `binding` object from `ContextFetch` is correct:
the selected fetch request has no such field. The resulting coverage reduction
is not sufficient, however. The selected continuation capability binds the
handle to participant, room, continuity scope, and trigger; authorizes
before/after/around independently; and carries per-fetch event/byte caps. The
selected design also says fetch limits are capped by both the request and
operator policy.

`validate_continuation_fetch` models issued state with only `handle_id`,
`expires_at`, and cursors. It neither retains/compares `bound_to` against the
host call context nor checks the requested direction or budgets against the
capability. A probe with an issued capability declaring
`can_fetch_after: false`, `max_events_per_fetch: 5`, and
`max_bytes_per_fetch: 100` accepts an `after` fetch requesting 20 events and
16384 bytes with zero adapter errors. Treating any known, unexpired handle as
"correct by construction" does not prove the exact binding or bounded
authorization the selected capability exists to carry.

The literal 1225-to-1222 test-count accounting is traceable: two obsolete
required-`attestation` tests and the obsolete inline-binding test explain the
net reduction. The first two removals are legitimate. The third should have
been replaced with host-context binding, direction-authorization, and cap-
overrun red cases rather than leaving those rules unimplemented.

## Verification performed

- At packet commit `6fa3996fd7cf92cd6157945245136a8c55cb69cc`:
  `python3 scripts/check_governance.py` — PASS,
  `governance boundary: OK (SpecKit 0.12.11)`.
- At the same packet commit: `python3 -m unittest` — PASS, 1222 tests,
  11 skipped.
- At the same packet commit:
  `uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'`
  — PASS, 164 tests, 0 skipped.
- `python3 -m evals.verdict_suite.runner --list` — PASS, 60 V1 fixtures
  discovered.
- `git diff --check` for attempt-2 packet to candidate and candidate to packet
  — PASS.
- The packet changes no product schemas, adapter, tests, corpora, or product
  docs after candidate commit `7f9e814`; its later changes are lifecycle,
  SpecKit, and handoff evidence only.
- Independent attempt-2 red-run reproduction used the exact five schemas from
  `5383e9f3a5e9c20c08ab54395f4ff370128f03de` with
  `jsonschema==4.26.0`. All 14 recorded top-level error counts matched exactly:
  request `26/40/36/31`, decision `1/1/1/1`, downstream `1/1/6/4/3/4`.
- Manual authority comparison and independent current-validator probes — FAIL
  as R7 through R10 describe.

## Required rework path

The source owner must return the slice declarations to `ACTIVE` while
preserving all three candidate/handoff attempts and rejection records. Per
Zoe's direction for this attempt, do not restart bound-workflow scaffolding
merely to perform the correction; follow the current owner-lane instruction.

The next correction must:

1. encode `error.code` as the authority's string and require string `detail`
   in the decision schema, receipt schema, stdlib adapter, corpus, docs, and
   authority cases; remove the local nullable event timestamp unless a higher-
   authority amendment explicitly adds it;
2. enforce actor-map key/reference integrity for self and every typed event
   reference, with an explicit runtime-relational corpus class and fixed counts;
3. make the stdlib wake validator validate every nested field the public schema
   validates and add negative oracle/adapter parity cases; and
4. retain the issued continuation's exact binding and capability facts at
   fetch time, compare the host call context, direction, and budgets, and add
   binding/direction/cap red cases to replace the removed local-shape check.

Then regenerate all three aggregate evidence files and the manifest, update
the slice-owned contract documentation, append a new exact candidate and
handoff packet, and present that new commit for a separate integrator review.
