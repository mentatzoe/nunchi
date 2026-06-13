# Implementation Plan: Classifier Verdict Test Suite

**Branch**: `003-classifier-test-suite` | **Date**: 2026-05-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-classifier-test-suite/spec.md` (clarified 2026-05-25; expanded with Discord-pilot human-conversation cases the same day)

## Summary

Build a deterministic, offline test suite that exercises the TurnAware admission classifier against two evidence pools: the TUR-8/9/10 Multica-shape smoke fixtures distilled in the TUR-12 corpus, and the pilot-bot Discord session log human-conversation shapes. The suite consumes a candidate classifier through a pluggable adapter (subprocess against `turnaware admit --input` by default; an in-process adapter imports `turnaware.core.evaluate` directly), runs each JSON fixture through the adapter, and emits per-fixture pass/fail in human-readable text plus a JSON Lines machine-readable stream. The runner exits non-zero on any failure. The suite is vendored under `specs/003-classifier-test-suite/contracts/` and is invoked by a single command from repo root. No new runtime dependency outside the existing `pyproject.toml`.

### Reconciliation 2026-06-13

Spec 002 merged to `main` (`c78dcb4`); the classifier under test is now the provider-backed product classifier (`src/turnaware/classifiers.py`), and `a132ccc` is the suite's historical baseline (`evidence/a132ccc-baseline.jsonl`). Changes in this file: self-test harness retimed from `pytest` to stdlib `unittest` (`python3 -m unittest`; the repo forbids third-party test dependencies); offline/determinism constraints scoped to the deterministic path per FR-015 as re-scoped in spec.md (live provider runs are evidence runs via `TURNAWARE_CLASSIFIER_MODEL` + API key; deterministic runs use `TURNAWARE_CLASSIFIER_TEST_RESULT` injection or the mock adapter); source-tree sketch updated for `classifiers.py`; R5 retimed to the historical baseline. Fixture expected verdicts are semantic ground truth and were not changed.

## Technical Context

**Language/Version**: Python 3.11 (matches `pyproject.toml` `requires-python = ">=3.11"`; matches the existing `turnaware` package).

**Primary Dependencies**: Stdlib only (`json`, `subprocess`, `pathlib`, `argparse`, `dataclasses`, `sys`). No third-party runtime dependency. Stdlib `unittest` (run via `python3 -m unittest`, per the repo's no-third-party-deps rule) is the harness for the suite's own self-tests.

**Storage**: Filesystem-only. Fixtures live as `*.json` files under `specs/003-classifier-test-suite/contracts/fixtures/`. No DB.

**Testing**: stdlib `unittest` for runner self-tests (per `tests/` convention; `python3 -m unittest tests.test_003_runner`). The suite itself is *exercised* by running the runner against the public CLI; that exercise is what FR-001 / FR-002 / SC-001 verified against the historical `a132ccc` baseline (`evidence/a132ccc-baseline.jsonl`); the current candidate is `main`'s provider-backed product classifier, measured by captured evidence runs.

**Target Platform**: macOS and Linux (developer-laptop / CI). No Windows-specific paths; uses `pathlib.Path` and POSIX subprocess.

**Project Type**: CLI / library hybrid (the runner is a CLI; the fixture loader and adapter are importable so future tooling can reuse them).

**Performance Goals**: Whole suite under 5 seconds on a standard developer laptop (SC-005). Per-fixture median budget therefore ≲50ms with 50–100 fixtures. Subprocess fork dominates per-fixture cost; bench during implementation.

**Constraints**: No remote fetch of fixtures or runner inputs (FR-017). The deterministic path (mock adapter, or subprocess adapter with `TURNAWARE_CLASSIFIER_TEST_RESULT` injection) runs offline — no network, no LLM — and is deterministic across runs and OSes (FR-009 / FR-015 as re-scoped); live provider runs are evidence runs with a stable schema but no byte-identical-verdict guarantee. Single-command invocation from repo root (FR-011). Exit non-zero on any failure (FR-011). Output JSONL + human-readable text covering identical field set (FR-012 / FR-013).

**Scale/Scope**: ~20–30 fixtures at v1 (10–12 Multica-shape from TUR-12 corpus, 13–15 Discord-shape from FR-018 enumeration, 4 named-suppressor fixtures from FR-021, 1 verdict-surface contract from FR-020, baselines). Extensibility budget: under 5 minutes per added fixture (SC-004).

## Constitution Check

Walked the eight Core Principles against this plan; result: PASS, no violations to track.

- **I. Admission, Not Composition** — PASS. The suite tests verdict admission only. It does not draft reply prose, does not prescribe wording, does not introduce new verdicts. The verdict-surface contract test (FR-020) reinforces this principle by failing classifiers that try to compose a transport string instead of returning a typed verdict.
- **II. Hard-Stop PASS Is Load-Bearing** — PASS. FR-020 + SC-011 directly encode this principle as a contract assertion: PASS-as-string sentinel variants (the actual pilot-bot leak) are explicitly rejected as contract failures distinct from verdict miscategorizations. The suite is one of the mechanisms the constitution requires to keep "a successful PASS MUST NOT emit a room message" enforceable.
- **III. CLI-First, Modular Core** — PASS. The pluggable adapter (FR-022) consumes the existing `turnaware admit --input` CLI today (the subprocess adapter is the default) and is explicitly designed to also consume an in-process callable core tomorrow (the principle's "stable in-process evaluation boundary"). No "CLI containing all decision logic" is created here — the runner is a thin transport over the adapter.
- **IV. Vertical, Independently Testable Slices** — PASS. The suite ships an end-to-end runnable artifact (`python3 specs/003-classifier-test-suite/contracts/runner.py`, the single command documented in quickstart.md) that exercises real fixtures against the real public CLI. Not schemas-only, not docs-only; the slice does the product job of "tell me whether this candidate gets the verdicts right" today.
- **V. Test-First Contract and Fixture Discipline** — PASS. The suite IS the contract/fixture discipline for TUR-11's classifier completion. All four verdicts (PASS, ACK, ASK, SPEAK) are covered (FR-003 baselines + FR-001 / FR-002 false-case fixtures). Contract tests cover output schema (FR-020), PASS suppression semantics (FR-020 + SC-011), `context_checked` truthfulness (FR-007), and adapter failure behaviour for invalid input (FR-022). The deterministic CI path is the subprocess adapter against the public CLI with `TURNAWARE_CLASSIFIER_TEST_RESULT` injection (or the mock adapter) — no stochastic provider in the merge gate; live provider judgment is captured as review-time evidence.
- **VI. Adapter Tier Honesty and Consumer Boundaries** — PASS. FR-022 explicitly names the adapter as a tier-aware boundary; subprocess adapter is the "wrapper/gateway" tier today; a future in-process adapter would be the "pre-input hook" or "agent-invoked tool" tier. The suite's own honesty about which adapter ran is surfaced in the JSONL output's per-fixture record so a downstream consumer can tell which tier was exercised.
- **VII. Context Truth and Room Inference** — PASS. FR-007 is the explicit test of `context_checked` truthfulness against actual consultation. The Discord-shape suppressor fixtures (FR-021) exercise room inference (the gate inferring "the room" from peer messages) without baking a "hardcoded surface taxonomy" — they assert outcomes against the `before-you-respond.md` policy, which itself comes from supplied context, not a hidden product contract.
- **VIII. Documentation Is Product** — PASS. The runner publishes a `quickstart.md` (Phase 1 below) that is runnable verbatim. FR-012 makes the human-readable output self-explanatory ("a human reader MUST NOT need to open the source comment or smoke threads to interpret a failing line"). No marketing/positioning copy ships with this slice; the README updates planned at polish stage will state the suite's scope and link the spec.

**Gate decision**: PASS — proceed to Phase 0. No violations to track in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/003-classifier-test-suite/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output: runner + fixtures + adapter
│   ├── runner.py            # CLI entry point + orchestration
│   ├── adapters.py          # SubprocessAdapter (default); InProcessAdapter (stub)
│   ├── loader.py            # fixture discovery + JSON parsing + validation
│   ├── report.py            # JSONL + human-readable rendering
│   ├── invariants.py        # the structural-invariant assertions (FR-005..FR-008, FR-020)
│   ├── fixtures/
│   │   ├── multica/         # FR-001..FR-008 fixtures (TUR-8/9/10 + corpus)
│   │   ├── discord/         # FR-018 + FR-021 fixtures (pilot-bot session)
│   │   └── contract/        # FR-020 verdict-surface contract fixture(s)
│   ├── index.json           # fixture registry: id -> path -> expected + metadata
│   └── README.md            # links spec, names entry command, lists fixture classes
├── tasks.md             # /speckit-tasks output (Phase 2; produced separately)
└── checklists/
    └── requirements.md  # spec quality checklist (already validated 2x)
```

### Source Code (repository root)

```text
src/
└── turnaware/                # existing package; NOT modified by this slice
    ├── cli.py
    ├── classifiers.py        # provider-backed product classifier (landed with spec 002)
    ├── core.py
    ├── errors.py
    ├── models.py
    ├── schema.py
    └── __init__.py

tests/
├── test_cli.py                       # existing
├── test_core.py                      # existing
├── test_schema.py                    # existing
├── test_003_runner.py                # NEW: stdlib-unittest self-tests exercising the runner's own behaviour
│                                     #      (loader correctness, report shape, adapter contract)
└── fixtures/                         # existing per-verdict baselines used by test_core/test_cli;
                                      # the suite's fixtures live under specs/003-*/contracts/fixtures/
                                      # so they're co-located with the spec, not mixed with unit tests.
```

**Structure Decision**: The runner and fixtures are vendored under the spec directory (`specs/003-classifier-test-suite/contracts/`) per FR-017 and per SpecKit convention for contract artifacts. The runner is invokable via `python -m` from repo root; a thin wrapper script may be added in `bin/` at polish stage if Zoe wants a shorter invocation. The runner's own self-tests live in `tests/test_003_runner.py` so they're picked up by `python3 -m unittest` discovery alongside the existing tests. No modifications to `src/turnaware/` in this slice — the classifier under test is consumed via the adapter, not patched.

## Complexity Tracking

No Constitution Check violations to justify. This section intentionally empty.

## Phase 0 outline (executed during /speckit-plan)

See `research.md` for the resolved decisions. Topics covered:

- **R1**: How to invoke the public CLI from the runner reliably across macOS/Linux (subprocess concerns, signal handling, stdout/stderr separation).
- **R2**: How to express "predicted, not runtime-observed" in fixture metadata so the runner can surface the distinction (FR-004 / SC-008).
- **R3**: How to express the verdict-surface contract fixture (FR-020 / SC-011) without coupling the suite to a Python type system — the contract must hold for a future Rust/Go/Node adapter too.
- **R4**: Fixture id naming convention (raised as low-impact in clarify; resolved here so the index.json is consistent).
- **R5**: How the four named Discord suppressors (FR-021) are exercised against the *historical* `a132ccc` `turnaware.core.evaluate`, which had no Discord-suppressor concept — these fixtures fail on that baseline (confirmed in `evidence/a132ccc-baseline.jsonl`), and the failure-mode column documents why. Whether `main`'s product classifier honours the suppressors is answered by captured evidence runs, not assumed.

## Phase 1 outline (executed during /speckit-plan)

See `data-model.md`, `contracts/README.md`, and `quickstart.md` for the artifacts.

- **Data model**: documents the fixture envelope schema (extending the public `turnaware admit` request shape with `source_shape` and per-item `timestamp`), the runner result schema (JSONL line + summary), the adapter interface, and the per-fixture index entry shape.
- **Contracts**: the `contracts/` directory carries the runner + adapter + fixture index + per-source fixture trees. The contract is "given a fixture JSON, the adapter MUST produce a typed verdict and the runner MUST report pass/fail with the metadata in FR-012."
- **Quickstart**: a short, runnable doc showing how to run the suite against the bundled subprocess adapter, how to add a fixture, and how to plug in a non-default adapter. Lives at `specs/003-classifier-test-suite/quickstart.md`.

**Agent context update**: The CLAUDE.md SPECKIT block in this worktree points at this plan after Phase 1 completes (per the speckit-plan skill step 3.3).

## Re-check Constitution Check post-Phase 1

Phase 1 introduces no new architecture, only the concrete file layout. The eight gates above still PASS. No new violations.

## Re-check Constitution Check post-implementation (T045, 2026-06-13)

Implementation complete (37 fixtures, invariant dispatch wired into the
runner, 18 self-tests in `tests/test_003_runner.py`, post-002 reconciliation
applied). The eight gates re-checked against the shipped code: PASS, no new
violations. Notes: the suite still composes no reply prose (I); the FR-020
sentinel-leak contract path is exercised by both fixtures and self-tests
(II); the runner consumes the public CLI via the subprocess adapter and the
in-process callable via `InProcessAdapter` with no decision logic of its own
(III); the deterministic self-test path satisfies test-first discipline while
live provider judgment is captured as timestamped evidence rather than
asserted (V, VIII).
