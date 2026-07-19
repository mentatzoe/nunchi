# Phase 27 final-page validity and deterministic relation priority

**Status**: ACTIVE — exact candidate freeze and T153 independent review pending
**Rejected predecessor**: `2b10abb0b9b7d4dff802e08b36030995263cf520`
**Decision**: `evidence/v2/observation/review-2026-07-19-phase26-hermes-2b10abb-rejection.md`

## RED

Two deterministic regressions reproduced both review findings:

```text
Ran 2 tests
FAILED (failures=2)
PHASE27_RED_EXIT=1
```

- the page received by `compare_pages()` contained invalid `next_cursor=null`;
- identical capped relation input selected reply or thread targets depending on `PYTHONHASHSEED`.

## GREEN

- `CAP-S13-008` represents cursor absence by removing the field;
- both fully mutated pages are validated immediately before comparison;
- trigger relation IDs preserve `_relation_closure_ids()` order;
- a separate set supplies membership/dedup without deciding selection order;
- cross-seed regression covers seeds 1–4.

```text
Ran 2 tests in 0.887s
OK
PHASE27_GREEN
```

## Complete matrix

| Gate | Result |
|---|---|
| Observation discovery | 189 tests, OK |
| aggregate scenes | 53 rows, 0 FAIL (9 identity; 7 budget; 24 continuation; 4 recoverability; 9 equivalence) |
| Phase 18/23/25/26/27 adversarial | 25 rows, 0 FAIL |
| corpus + executable docs | 19 tests, OK; corpus 202/202 and established digest |
| full repository | 1438 tests, OK; 4 optional-integration skips |
| verdict fixtures | 60 discovered |
| Ruff / Bandit / scanner regressions | clean |
| governance CLI / task manifest / literal task state | clean |
| working-tree and activation-range `git diff --check` | clean |
| generated reviewer checklist | absent |

T148–T152 are complete. T153 remains open for fresh independent review of the exact frozen successor. This receipt does not claim acceptance, convergence, handoff readiness, integration, deployment, release, promotion, or cutover authority.
