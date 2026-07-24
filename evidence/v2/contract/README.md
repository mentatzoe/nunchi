# Slice 010 contract evidence manifest (T018; A3 implementation complete, acceptance pending)

**Recorded on**: 2026-07-24 in the `v2-contract-owner` worktree. A3's
implementation is complete and independently reviewed; acceptance is pending.
This manifest does not establish an effective dependency or authorize an action.

**Amendment disposition**: A3 adds the
`privileged-action-authorization.jsonl` aggregate file for
`I-010F PrivilegedActionAuthorizationV2@1`. All four aggregate files were
regenerated against the completed implementation corpus so their validator
identities, expected results, and manifest counts describe one tree. This
leaves accepted A1/A2 history intact; it does not supersede their effective
commit until separate integrator acceptance.

**What changed (completed amendment A3 implementation)**: the new S18 corpus carries the
closed request/decision/challenge/completion union and rejects malformed digest
profiles, public operation or room/model authority fields, action/digest/
requester/capability substitution, missing or wrong challenge/approver,
challenge and decision replay, approval-recheck drift, expiry, policy mismatch,
revocation, and unknown persistence. Its runtime-only `binding-expiry` cases
prove supplied record correlation; they do not claim that an event, policy,
operator, persistence backend, or effect was actually trusted or executed.

**What changed (amendment A2, post-acceptance)**: fixing the gap found in
`evidence/v2/attention/dependency-010-amendment-A1-post-acceptance-zero-margin-blocker.md`
(slice 030 worktree), discovered during slice 030's re-planning analysis
after amendment A1's acceptance. The selected design at `c834e8c` says a
transition margin, when active, is a finite number within the inclusive
`[0,1]` domain. Accepted `@1`'s `routing_audit.effective_margin` used
`exclusiveMinimum: 0`, wrongly excluding exactly `0` — the sole outlier in
the schema file, since the sibling `confidence` `$def` used for
`legacy_verdict_confidences` was already correctly inclusive. `@2` changes
`exclusiveMinimum: 0` to `minimum: 0` (schema and stdlib adapter mirror);
no other field, valve, or cross-field rule changes.

**What changed (amendment A1, post-acceptance)**: fixing the gap found in
`evidence/v2/attention/dependency-010-post-acceptance-blocker.md`, discovered
by slice 030's planning analysis after slice 010's `@1` acceptance. The
selected design at `c834e8c` requires the effective policy and its source
to be inspectable in receipts, and an operator's explicit `NO_WAKE`
override to the shared `WAKE` error-handling default to be separately
receipted as operational failure policy. Accepted `@1` gave
`policy_provenance` only to the trusted-bypass attention body and gave the
error body no way to distinguish an operator override from an ordinary
failure; `margin_source` on `routing_audit` is scoped to the margin-defer
valve only and cannot serve as general policy provenance. `@2` adds the
classifier-outcome body's required `policy_provenance` and the error
body's conditional `wake_action`/`policy_provenance` pair (present together
exactly when an explicit operator override applied). This is a breaking
edit per FR-010/FR-014; `@1` consumers must migrate to `@2` before
consuming attention-stage receipts.

**Focused correction (A1-R1, first amendment candidate rejected)**: the
first A1 candidate (`959e4ac`) defined `wake_action` as
`enum: ["WAKE", "NO_WAKE"]`, which wrongly let a receipt assert an operator
override while naming the unchanged shared default. `evidence/v2/contract/review-2026-07-19-v2-integrator-amendment-A1.md`
rejected it (R7–R11 remained cleared and undisturbed). `wake_action` is now
`const: "NO_WAKE"`: `WAKE` is the shared default and is never itself a
receipted override.

Each aggregate JSONL evidence file holds two records per corpus case — one
per validator — and every record carries the five mandatory fields
(`scene_id`, `case_id`, `validator`, `expected`, `observed`). A record ID
below is the case's `case_id`; the two records for a case share it and are
distinguished by the `validator` field.

## Commands and results

The verified offline dual-validator command for the completed A3 implementation:

```sh
uv run --offline --isolated --no-project --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'
```

Result (2026-07-24): **215 tests, OK, 0 skipped** — every oracle-side check
ran; only the explicit per-class oracle skips applied inside the corpus runner
(counted below).

The SC-006 boundary and CLI verification:

```sh
python3 scripts/check_governance.py --check-cli
```

Result (2026-07-24): `governance boundary + CLI: OK (SpecKit 0.12.11)` — zero
product schemas, tests, fixtures, evaluation assets, evidence, or product
documentation under the SpecKit directories.

The full repository baseline (`python3 -m unittest`) passed on the completed
A3 implementation tree on 2026-07-24. Its oracle-absence skips now include all
four corpus suites; the exact handoff packet will record its complete command
output before separate acceptance review.

Evidence generation and shape verification:

```sh
uv run --offline --isolated --no-project --with 'jsonschema==4.26.0' python -m tests.v2.contract.schema_helpers --write-evidence
uv run --offline --isolated --no-project --with 'jsonschema==4.26.0' python -m tests.v2.contract.schema_helpers --verify-evidence
```

Result (2026-07-24): attention-request 98 records, attention-decision 134
records, downstream 184 records, privileged-action-authorization 52 records;
0 mismatched; all records carry the five mandatory fields.

## Observed per-class partition counts (cases; each case = 2 records)

| Partition class | attention-request | attention-decision | downstream | privileged-action-authorization | Total |
|---|---|---|---|---|---|
| `schema-expressible` | 36 | 65 | 57 | 12 | 170 |
| `id-uniqueness` | 2 | 0 | 2 | 0 | 4 |
| `timestamp-order` | 2 | 0 | 0 | 0 | 2 |
| `advice-citation` | 0 | 2 | 0 | 0 | 2 |
| `trigger-membership` | 2 | 0 | 0 | 0 | 2 |
| `actor-reference-integrity` | 7 | 0 | 2 | 0 | 9 |
| `binding-expiry` | 0 | 0 | 20 | 14 | 34 |
| `receipt-sequence` | 0 | 0 | 11 | 0 | 11 |
| **Total cases** | **49** | **67** | **92** | **26** | **234** |

These observed counts match each corpus's authoritative
`expected-counts.json` exactly (asserted loudly on every load). The
`schema-expressible` figures above include the FR-014 authority-conformance
class (20 cases total: 6 request, 6 decision, 8 downstream — enumerated
below), a named manifest-counted subset of `schema-expressible`, never a
fourth oracle-treatment class (CHK099/CHK115). `schema-expressible` widens
from 64 to 65 in the decision corpus this amendment (A2): 1 case
(`DEC-AUTH-006`, a margin-defer decision with `effective_margin: 0`,
valid).

## Both skip regimes (kept separately named and counted)

| Regime | When | Count |
|---|---|---|
| `oracle-class-skip` | Under the pinned command: the oracle skips the two behavioral classes by explicit class | 45 cases (34 `binding-expiry` + 11 `receipt-sequence`; 45 oracle-side records observe `oracle-class-skip`) |
| `baseline-oracle-absence` | Under `python3 -m unittest` (no pinned oracle): every oracle-side check for the six oracle-visible classes is skipped with an explicit count | 189 oracle-side checks (49 attention-request + 67 attention-decision + 61 downstream + 12 privileged-action-authorization), surfaced as 4 counted unittest skips |

## FR-014 authority-conformance class (CHK099/CHK110/CHK121; 20 cases)

Every case below is drawn verbatim or field-complete from the selected
design at `c834e8c` (`authority_source_commit: c834e8c` on each record
below), is schema-expressible (never a new partition class — CHK099), and
carries a `red_run_failing_count` measured against a specific rejected
pre-repair tree. The 14 cases carried forward from attempt 3 are measured
against the attempt-2 packet commit
`5383e9f3a5e9c20c08ab54395f4ff370128f03de`, unchanged from the attempt-3
manifest. The 5 cases new at attempt 4 (R7/R8 regression guards) are
measured against the rejected attempt-3 candidate commit
`7f9e81460d570e078c4bcbacb138f81c1b291455`; for these five, the authority
violation is a false *accept* under the rejected schema (the attempt-3
schema was too permissive), so a `red_run_failing_count` of `0` is itself
the defect — except DWN-AUTH-007, which is a false *reject* (an
authority-valid arbitrary error code, narrowed by attempt-3's closed enum)
in the original sense. The 1 case new this amendment (A2) is measured
against amendment A1's accepted decision commit
`30aba09f13a6752b4c24811da0d8ec772a9d9682` (the decision schema was
unchanged by A1, so this is also the pre-A2 tree): the accepted `@1`
schema's `exclusiveMinimum: 0` bound rejects the authority-valid boundary
value, another false *reject*.

| Case ID | Corpus | What it proves | `red_run_failing_count` |
|---|---|---|---|
| REQ-AUTH-001 | attention-request | the design's example attention request validates verbatim | 26 |
| REQ-AUTH-002 | attention-request | the typed reaction event union (add/remove operation) | 40 |
| REQ-AUTH-003 | attention-request | the typed membership event union (literal scope, subject/causal actor) | 36 |
| REQ-AUTH-004 | attention-request | the complete coverage field inventory incl. optional per-event-type visibility | 31 |
| REQ-AUTH-005 | attention-request | an explicit null timestamp rejects (unknown timestamp is representable only by omission) | 0 (attempt-3 schema wrongly accepted `null`) |
| REQ-AUTH-006 | attention-request | an empty-string actor-map key rejects | 0 (attempt-3 schema had no `propertyNames` constraint) |
| DEC-AUTH-001 | attention-decision | a valid WAKE records routing-audit margin status + full classifier audit | 1 |
| DEC-AUTH-002 | attention-decision | a valid WAKE without a legacy verdict confidence vector, margin retired | 1 |
| DEC-AUTH-003 | attention-decision | the error branch's request ID is optional on a pre-validation error | 1 |
| DEC-AUTH-004 | attention-decision | the error branch's request ID/classifier audit on a post-validation error | 1 |
| DEC-AUTH-005 | attention-decision | an error without `detail` rejects (the complete error object requires both `code` and `detail`) | 0 (attempt-3 schema made `detail` optional) |
| DEC-AUTH-006 | attention-decision | a margin-defer decision with `effective_margin` exactly `0` validates (inclusive `[0,1]` domain) | 1 (accepted `@1` schema's `exclusiveMinimum: 0` wrongly rejected the boundary) |
| DWN-AUTH-001 | downstream (context-continuation) | the directional anchored fetch (`around` + `anchor_event_id`) | 1 |
| DWN-AUTH-002 | downstream (context-continuation) | the identity-bearing page (room/continuity-scope identity, direction, anchor) | 1 |
| DWN-AUTH-003 | downstream (participant-wake) | the materialized wake packet, not a wrapped classifier projection | 6 |
| DWN-AUTH-004 | downstream (attention-receipt) | the observation-stage telemetry incl. `event_visibility` | 4 |
| DWN-AUTH-005 | downstream (attention-receipt) | the attention-stage telemetry (classifier identity, evidence, transition-valve) | 3 |
| DWN-AUTH-006 | downstream (attention-receipt) | the participant-host telemetry incl. `expansion_calls` | 4 |
| DWN-AUTH-007 | downstream (attention-receipt) | an attention-stage error carrying an arbitrary string code validates | 1 (attempt-3 schema's closed 5-value enum wrongly rejected it) |
| DWN-AUTH-008 | downstream (attention-receipt) | an attention-stage error without `detail` rejects | 0 (attempt-3 schema made `detail` optional) |

`red_run_failing_count` values for the 14 attempt-3-carried cases were
measured directly against `5383e9f3a5e9c20c08ab54395f4ff370128f03de`, as
recorded in the attempt-3 manifest. The 5 new values were measured directly
this attempt: the attempt-3 schemas were checked out at
`7f9e81460d570e078c4bcbacb138f81c1b291455` into an isolated scratch
directory and each document run through a Draft 2020-12 validator built
from those exact schema files (`iter_errors()` count).

## Scene-to-record manifest (all thirteen scene rows)

| Scene | JSONL file(s) | Record IDs |
|---|---|---|
| `S01` Exact self and alias collision | `attention-request.jsonl` | REQ-S01-001, REQ-S01-002, REQ-S01-101, REQ-S01-102, REQ-S01-103, REQ-S01-104, REQ-S01-105, REQ-AUTH-001, REQ-AUTH-006 |
| `S02` Native relations | `attention-request.jsonl` | REQ-S02-001, REQ-S02-101, REQ-S02-102, REQ-S02-103, REQ-S02-201, REQ-S02-202, REQ-S02-203, REQ-S02-204, REQ-AUTH-002, REQ-AUTH-003, REQ-S02-205, REQ-S02-206, REQ-S02-207, REQ-S02-208, REQ-S02-209, REQ-S02-210, REQ-S02-211 |
| `S03` Bounded context and tail | `attention-request.jsonl` | REQ-S03-001, REQ-S03-002, REQ-S03-003, REQ-S03-101, REQ-S03-102, REQ-S03-103, REQ-S03-104, REQ-S03-201, REQ-S03-202, REQ-AUTH-004, REQ-AUTH-005 |
| | `downstream.jsonl` | DWN-S03-001, DWN-S03-002, DWN-S03-003, DWN-S03-101, DWN-S03-102, DWN-S03-103, DWN-S03-104, DWN-S03-201, DWN-S03-202, DWN-S03-301, DWN-S03-302, DWN-S03-303, DWN-S03-305, DWN-AUTH-001, DWN-AUTH-002, DWN-S03-306, DWN-S03-307, DWN-S03-308, DWN-S03-309, DWN-S03-310, DWN-S03-311, DWN-S03-312, DWN-S03-313, DWN-S03-314, DWN-S03-315, DWN-S03-316, DWN-S03-317, DWN-S03-318, DWN-S03-319, DWN-S03-320, DWN-S03-321 |
| `S05` Governed suppression (conditional FR-007 rule) | `attention-decision.jsonl` | DEC-S05-001, DEC-S05-002, DEC-S05-003, DEC-S05-004, DEC-S05-005, DEC-S05-006, DEC-S05-101, DEC-S05-102, DEC-S05-103, DEC-S05-104, DEC-AUTH-002 |
| `S06` WAKE/bypass contribution | `downstream.jsonl` | DWN-S06-001, DWN-S06-002, DWN-S06-003, DWN-S06-101, DWN-S06-102, DWN-S06-104, DWN-S06-004, DWN-S06-005, DWN-S06-006, DWN-S06-007, DWN-S06-105, DWN-S06-106, DWN-S06-107, DWN-S06-108, DWN-S06-306, DWN-S06-301, DWN-S06-302, DWN-S06-303, DWN-S06-304, DWN-S06-305, DWN-S06-307, DWN-S06-308, DWN-S06-309, DWN-AUTH-003, DWN-AUTH-004, DWN-AUTH-005, DWN-AUTH-007, DWN-AUTH-008, DWN-S06-109, DWN-S06-110, DWN-S06-111, DWN-S06-112, DWN-S06-113, DWN-S06-114, DWN-S06-115 |
| `S07` Participant silence | `downstream.jsonl` | DWN-S07-001, DWN-S07-002, DWN-S07-003, DWN-S07-101, DWN-S07-102, DWN-S07-301, DWN-S07-302, DWN-AUTH-006 |
| `S08` Dual DEFER valves | `attention-decision.jsonl` | DEC-S08-001, DEC-S08-002, DEC-S08-003, DEC-S08-004, DEC-S08-101, DEC-S08-102, DEC-S08-103, DEC-S08-104, DEC-S08-105, DEC-S08-106, DEC-S08-107, DEC-AUTH-001, DEC-AUTH-006 |
| `S09` Operational error | `attention-decision.jsonl` | DEC-S09-001, DEC-S09-002, DEC-S09-003, DEC-S09-004, DEC-S09-101 through DEC-S09-122, DEC-S09-201, DEC-S09-202, DEC-AUTH-003, DEC-AUTH-004, DEC-AUTH-005 |
| `S15` Context budget | `attention-request.jsonl` | REQ-S15-001, REQ-S15-101, REQ-S15-102, REQ-S15-103 |
| | `downstream.jsonl` | DWN-S15-001, DWN-S15-101, DWN-S15-102, DWN-S15-103 |
| `S16` No registry or ledger | `attention-request.jsonl` | REQ-S16-101, REQ-S16-102, REQ-S16-103, REQ-S16-104, REQ-S16-105 |
| | `attention-decision.jsonl` | DEC-S16-101, DEC-S16-102, DEC-S16-103, DEC-S16-104 |
| | `downstream.jsonl` | DWN-S16-101, DWN-S16-102, DWN-S16-103, DWN-S16-104, DWN-S16-105, DWN-S16-106 |
| `010-Preattention-bypass` | `attention-decision.jsonl` | DEC-BYP-001, DEC-BYP-101, DEC-BYP-102, DEC-BYP-103, DEC-BYP-104, DEC-BYP-105, DEC-BYP-106, DEC-BYP-107 |
| | `downstream.jsonl` | DWN-BYP-001, DWN-BYP-002, DWN-BYP-101, DWN-BYP-103, DWN-BYP-104, DWN-BYP-301 |
| `010-V1` Breaking rejection | `attention-request.jsonl` | REQ-V1-101, REQ-V1-102, REQ-V1-103 |
| | `downstream.jsonl` | DWN-V1-101, DWN-V1-102 |
| `S18` Provenance-bound privileged action | `privileged-action-authorization.jsonl` | AUTH-S18-001, AUTH-S18-002, AUTH-S18-003, AUTH-S18-004, AUTH-S18-005, AUTH-S18-101, AUTH-S18-102, AUTH-S18-103, AUTH-S18-104, AUTH-S18-105, AUTH-S18-106, AUTH-S18-107, AUTH-S18-201, AUTH-S18-202, AUTH-S18-301, AUTH-S18-302, AUTH-S18-303, AUTH-S18-304, AUTH-S18-305, AUTH-S18-306, AUTH-S18-307, AUTH-S18-308, AUTH-S18-309, AUTH-S18-310, AUTH-S18-311, AUTH-S18-312 |

The `S09` row abbreviates the contiguous run DEC-S09-101 through
DEC-S09-122 (twenty-two consecutive IDs, all present); every other row
enumerates its record IDs exhaustively. All 234 case IDs above (212 named
plus the abbreviated S09 run) are exactly the cases present in the four
corpora; no evidence record is outside this manifest.
