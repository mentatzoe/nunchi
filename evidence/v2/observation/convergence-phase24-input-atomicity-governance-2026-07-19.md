# Slice 020 convergence — caller-memory atomicity, early limits, governance truth

**Date**: 2026-07-19
**Status**: local remediation GREEN; immutable review still BLOCKED
**Base**: `80c1de2ed5941c1cc5d4e28ea3f13d84dc39b6d2`
**Worktree**: `/tmp/nunchi-phase20-toctou`
**Correction source**:
`evidence/v2/observation/review-2026-07-19-ff3c5a2-rejection.md`

This lane was developed in isolation, then rebased onto settled Phase 23
permanent request-ID uniqueness. It changes only Observation caller-memory/
resource boundaries, the governance completion oracle, deterministic tests, and
new evidence. It makes no candidate or acceptance claim.

## RED

`tests/v2/observation/test_input_atomicity.py` reproduced four intended failures:

- an authorized `before` request mutated after validation served `after`;
- an event mutated after `_check_event()` committed an invalid type;
- uncopyable input did not fail at the complete-input boundary;
- an over-limit fresh fetch visited all 256 retained events before rejection.

Two governance RED tests proved that no checkbox-preserving manifest API existed
and no candidate completion validator rejected an open committed checkbox.

## GREEN implementation

- `ObservationProvider.ingest()` deep-copies the complete native input before
  reading or validating any nested field and converts copy failure to
  `ObservationInputError` before state mutation.
- `ContinuationProvider.fetch()` deep-copies request and host context once at
  entry, validates and uses only those copies, and converts copy failure to
  `ContinuationError` before cursor mutation.
- Fresh requests reject at active-cursor capacity before retained-deque copying
  or immutable-window construction.
- Governance preserves normalized task graph identity while tracking literal
  checked IDs separately. The read-only manifest prints only checked IDs. The
  effective/latest candidate used by handoff must have every committed task
  literally checked when declaring `Tasks complete: YES`; append-superseded
  historical attempts retain structural validation without becoming an
  unrepairable retroactive gate.

## Verification so far

| Check | Result |
|---|---|
| Observation discovery | 170 tests, OK |
| governance suite | 66 tests, OK |
| standard aggregate evidence | 52 rows, 0 FAIL (9/7/24/4/8) |
| Phase 18/24 adversarial evidence | 15 rows, 0 FAIL |
| Slice 020 manifest | 124 literal checks, 124 reported completed IDs; exact match |
| governance boundary + CLI | PASS, SpecKit 0.12.11 |
| full repository | 1421 tests, OK; 4 optional-integration skips |
| attempt-6 corpus | 6 tests, OK; 202/202 accounted for and exact digest GREEN |
| verdict discovery | 60 fixtures |
| Ruff over changed Python | clean |
| Bandit over `src/nunchi/observation.py` | clean, 0 findings |
| `git diff --check` | clean |

The complete repository/scanner matrix, immutable commit/push, exact receipt,
and fresh independent whole-slice review remain required.
