# Slice 040 participant-wake source freeze

**Review status**: SUCCESSOR FROZEN FOR INDEPENDENT RE-REVIEW

**Effective successor implementation commit**: `91e97bad7c50de70d3fd41805c206c9a5804a7ef`

**Pre-surface comparison commit**: `efa99ac`

**Audit-only base branch**: `codex/review-base-v2-040`

**Frozen review branch**: `codex/freeze-v2-040`

This packet projects the current effective slice-040-owned source and tests
from the integration candidate into a narrow GitHub diff. It does not rewrite
the integration candidate and is not a merge vehicle. Review approval or
rejection applies only to the exact frozen bytes listed in
`frozen-files.sha256`.

## Included surface

- `src/nunchi/participant.py`
- `src/nunchi/runtime.py`
- `src/nunchi/scheduling.py`
- `tests/v2/participant/`
- `docs/participant/v2.md`
- `evals/v2/participant/`

These are the ordinary implementation and test paths assigned to slice 040 by
`specs/040-v2-participant-wake/plan.md`. The test directory includes current
runtime and scheduling coverage because those tests exercise the participant
host boundary consumed by platform integrations.

## Successor closure

The successor closes every source-level objection recorded on the original
head: full decision/request/policy validation before suppression, bounded and
turn-scoped continuation, fact-bound action references, explicit turn
capabilities, truthful pre-transport host receipts, fail-closed receipt
persistence, atomic observation/scheduler order, and attention-receipt failure
before participant effect. Runtime and scheduling source are now manifest-
pinned with the tests that exercise them. The product guide and deterministic
scene catalog are included rather than claimed absent.

This audit PR still does not itself establish slice lifecycle acceptance or
live cross-platform parity; those remain separate governed decisions and must
not be inferred from source approval.

## Review requirements

1. Verify every listed SHA-256 and Git blob against effective source commit
   `adc8b645791e217eea5d4704a5fcb53be1e18e38` and confirm the PR does not move.
2. Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v
   tests.v2.participant.test_host tests.v2.participant.test_runtime
   tests.v2.participant.test_scheduling` (45 tests in the successor packet).
3. Adversarially inspect SUPPRESS, WAKE, DEFER, trusted bypass, operational
   error, direct act-or-silence, no send-time social reclassification,
   immutable receipt ownership, cancellation/timeout cleanup, request
   correlation, continuation bounds, and concurrent-turn scheduling.
4. Check cross-parameter identity, policy, room, session, and participant
   binding rather than accepting green happy-path tests as sufficient.
5. Return evidence-backed Critical/High/Medium findings with exact file:line
   references and reproduction results. Do not edit or merge this audit PR.

## Dependency and downstream note

Hermes and Claude Code already contain these source bytes in their ancestry.
Their work remains paused for new integration claims until this exact surface
is reviewed. A review result does not itself establish slice lifecycle
acceptance or installed-runtime parity.
