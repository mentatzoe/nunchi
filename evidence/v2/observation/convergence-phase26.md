# Phase 26 independent-rejection remediation receipt

**Status**: ACTIVE — exact candidate freeze and independent review pending
**Rejected predecessor**: `22a0a1ab9a996e82ec625ce73e301023889209e4`
**Decision**: `evidence/v2/observation/review-2026-07-19-phase25-hermes-22a0a1a-rejection.md`

## RED

The direct barrier/wire regression set reproduced eleven failures:

```text
Ran 8 tests
FAILED (failures=11)
PHASE26_RED_EXIT=1
```

Mechanisms reproduced:

1. receipt byte count changed after post-comparison caller mutation;
2. receipt copy failure was not fail-closed;
3. nearby snapshot relation gaps were trigger-only;
4. continuation page relation gaps were absent for reply/thread/reaction;
5. event/byte-excluded page relation targets omitted gap truth;
6. session-only and partial restart loss stayed in evaluator side state.

## GREEN implementation

- `build_observation_receipt()` deep-copies caller input once at method entry and uses only that copy through validation, equality, byte computation, field projection, and atomic pending-state consumption.
- Snapshot relation closure/gap truth covers every returned event, not only the trigger.
- Continuation page gap truth covers every returned event and retains actual event/byte truncation causes.
- `ObservationProvider(has_restart_gap=...)` carries an explicit validated host fact; known restart loss sets both `has_restart_gap=true` and `has_gaps=true`, while unknown continuity remains null.
- S05 assertions now require wire coverage truth; `known_gap_event_ids` remains diagnostic only.
- S13 generated continuation fixtures are closed, schema-valid objects before comparison.
- Full activation-range whitespace hygiene was checked and repaired.

## Verification

| Gate | Result |
|---|---|
| focused Phase 26 | 21 tests, OK |
| Observation discovery | 187 tests, OK |
| aggregate scenes | 53 rows, 0 FAIL (9 identity; 7 budget; 24 continuation; 4 recoverability; 9 equivalence) |
| Phase 18/23/25/26 adversarial | 23 rows, 0 FAIL |
| corpus conformance | 6 tests, 202/202 accounted for, digest `1ce18c9e9fc3b5aa820adcb1aad649c635fcb2ed64a7e644d4d5bba6aeb5d91f` |
| executable docs | 13 tests, OK |
| full repository | 1436 tests, OK; 4 optional-integration skips |
| verdict fixtures | 60 discovered |
| Ruff / Bandit / scanner regressions | clean |
| governance CLI / task manifest | clean |
| `git diff --check` | clean |
| activation-range `git diff --check fc60858a...` | clean |
| generated reviewer checklist | absent |

T142–T147 are complete. T148 remains open for a fresh independent read-only review of the frozen successor. This receipt does not claim acceptance, convergence, handoff readiness, integration, deployment, release, promotion, or cutover authority.
