# Slice 010 contract evidence manifest (T018)

**Recorded on**: 2026-07-17, in the implement step of bound run
`speckit-010-20260717T081350382670Z`, by cc-session-1
(`v2-contract-owner`).

Each aggregate JSONL evidence file holds two records per corpus case — one
per validator — and every record carries the five mandatory fields
(`scene_id`, `case_id`, `validator`, `expected`, `observed`). A record ID
below is the case's `case_id`; the two records for a case share it and are
distinguished by the `validator` field.

## Commands and results

The exact offline dual-validator command (the sole complete run):

```sh
uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'
```

Result (2026-07-17): `Ran 151 tests ... OK`, 0 skipped — every oracle-side
check ran; only the explicit per-class oracle skips applied inside the
corpus runner (counted below).

The boundary-only SC-006 verification, run with no flags:

```sh
python3 scripts/check_governance.py
```

Result (2026-07-17): `governance boundary: OK (SpecKit 0.12.11)` — zero
product schemas, tests, fixtures, evaluation assets, evidence, or product
documentation under the SpecKit directories.

Repository baseline for comparison (`python3 -m unittest`, full suite,
2026-07-17): 1208 tests, OK, 11 skipped — the 8 pre-existing V1 skips plus
the 3 counted `baseline-oracle-absence` skips (one per corpus suite).

Evidence generation and shape verification:

```sh
uv run --offline --with 'jsonschema==4.26.0' python -m tests.v2.contract.schema_helpers --write-evidence
uv run --offline --with 'jsonschema==4.26.0' python -m tests.v2.contract.schema_helpers --verify-evidence
```

Result (2026-07-17): attention-request 72 records, attention-decision 94
records, downstream 122 records; 0 mismatched; all records carry the five
mandatory fields.

## Observed per-class partition counts (cases; each case = 2 records)

| Partition class | attention-request | attention-decision | downstream | Total |
|---|---|---|---|---|
| `schema-expressible` | 30 | 45 | 43 | 118 |
| `id-uniqueness` | 2 | 0 | 2 | 4 |
| `timestamp-order` | 2 | 0 | 0 | 2 |
| `advice-citation` | 0 | 2 | 0 | 2 |
| `trigger-membership` | 2 | 0 | 0 | 2 |
| `binding-expiry` | 0 | 0 | 5 | 5 |
| `receipt-sequence` | 0 | 0 | 11 | 11 |
| **Total cases** | **36** | **47** | **61** | **144** |

These observed counts match each corpus's authoritative
`expected-counts.json` exactly (asserted loudly on every load).

## Both skip regimes (kept separately named and counted)

| Regime | When | Count |
|---|---|---|
| `oracle-class-skip` | Under the pinned command: the oracle skips the two behavioral classes by explicit class | 16 cases (5 `binding-expiry` + 11 `receipt-sequence`, all in the downstream corpus; 16 oracle-side records observe `oracle-class-skip`) |
| `baseline-oracle-absence` | Under `python3 -m unittest` (no pinned oracle): every oracle-side check for the five oracle-visible classes is skipped with an explicit count | 128 oracle-side checks (36 attention-request + 47 attention-decision + 45 downstream), surfaced as 3 counted unittest skips |

## Scene-to-record manifest (all twelve scene rows)

| Scene | JSONL file(s) | Record IDs |
|---|---|---|
| `S01` Exact self and alias collision | `attention-request.jsonl` | REQ-S01-001, REQ-S01-002, REQ-S01-101, REQ-S01-102, REQ-S01-103, REQ-S01-104, REQ-S01-105 |
| `S02` Native relations | `attention-request.jsonl` | REQ-S02-001, REQ-S02-101, REQ-S02-102, REQ-S02-103, REQ-S02-201, REQ-S02-202, REQ-S02-203, REQ-S02-204 |
| `S03` Bounded context and tail | `attention-request.jsonl` | REQ-S03-001, REQ-S03-002, REQ-S03-003, REQ-S03-101, REQ-S03-102, REQ-S03-103, REQ-S03-104, REQ-S03-201, REQ-S03-202 |
| | `downstream.jsonl` | DWN-S03-001, DWN-S03-002, DWN-S03-003, DWN-S03-101, DWN-S03-102, DWN-S03-103, DWN-S03-104, DWN-S03-201, DWN-S03-202, DWN-S03-301, DWN-S03-302, DWN-S03-303, DWN-S03-304, DWN-S03-305 |
| `S05` Governed suppression | `attention-decision.jsonl` | DEC-S05-001, DEC-S05-002, DEC-S05-101, DEC-S05-102, DEC-S05-103 |
| `S06` WAKE/bypass contribution | `downstream.jsonl` | DWN-S06-001, DWN-S06-002, DWN-S06-003, DWN-S06-004, DWN-S06-005, DWN-S06-006, DWN-S06-007, DWN-S06-101, DWN-S06-102, DWN-S06-104, DWN-S06-105, DWN-S06-106, DWN-S06-107, DWN-S06-108, DWN-S06-301, DWN-S06-302, DWN-S06-303, DWN-S06-304, DWN-S06-305, DWN-S06-306, DWN-S06-307, DWN-S06-308 |
| `S07` Participant silence | `downstream.jsonl` | DWN-S07-001, DWN-S07-002, DWN-S07-003, DWN-S07-101, DWN-S07-102, DWN-S07-301, DWN-S07-302 |
| `S08` Dual DEFER valves | `attention-decision.jsonl` | DEC-S08-001, DEC-S08-002, DEC-S08-003, DEC-S08-101, DEC-S08-102 |
| `S09` Operational error | `attention-decision.jsonl` | DEC-S09-001, DEC-S09-002, DEC-S09-003, DEC-S09-004, DEC-S09-101 through DEC-S09-120, DEC-S09-201, DEC-S09-202 |
| `S15` Context budget | `attention-request.jsonl` | REQ-S15-001, REQ-S15-101, REQ-S15-102, REQ-S15-103 |
| | `downstream.jsonl` | DWN-S15-001, DWN-S15-101, DWN-S15-102, DWN-S15-103 |
| `S16` No registry or ledger | `attention-request.jsonl` | REQ-S16-101, REQ-S16-102, REQ-S16-103, REQ-S16-104, REQ-S16-105 |
| | `attention-decision.jsonl` | DEC-S16-101, DEC-S16-102, DEC-S16-103, DEC-S16-104 |
| | `downstream.jsonl` | DWN-S16-101, DWN-S16-102, DWN-S16-103, DWN-S16-104, DWN-S16-105, DWN-S16-106 |
| `010-Preattention-bypass` | `attention-decision.jsonl` | DEC-BYP-001, DEC-BYP-101, DEC-BYP-102, DEC-BYP-103, DEC-BYP-104, DEC-BYP-105, DEC-BYP-106 |
| | `downstream.jsonl` | DWN-BYP-001, DWN-BYP-002, DWN-BYP-101, DWN-BYP-103, DWN-BYP-104, DWN-BYP-301 |
| `010-V1` Breaking rejection | `attention-request.jsonl` | REQ-V1-101, REQ-V1-102, REQ-V1-103 |
| | `downstream.jsonl` | DWN-V1-101, DWN-V1-102 |

The `S09` row abbreviates the contiguous run DEC-S09-101 through
DEC-S09-120 (twenty consecutive IDs, all present); every other row
enumerates its record IDs exhaustively. All 144 case IDs above are exactly
the cases present in the three corpora; no evidence record is outside this
manifest.
