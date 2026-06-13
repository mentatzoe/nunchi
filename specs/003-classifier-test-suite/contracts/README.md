# Contracts: Classifier Verdict Test Suite

This directory is the **vendored** test-suite artifact required by FR-017. Everything in here is checked into the repository, runs offline, and has no remote dependencies.

## Layout

```text
contracts/
├── README.md                   # this file
├── runner.py                   # CLI entry point + orchestration (FR-011, FR-013, FR-019)
├── adapters.py                 # Adapter protocol + SubprocessAdapter (default) + InProcessAdapter (stub)
├── loader.py                   # walks fixtures/, validates pairs, builds the in-memory index
├── report.py                   # JSONL + human-readable rendering (FR-012, FR-013)
├── invariants.py               # FR-005..FR-008 + FR-020 structural-invariant assertion helpers
└── fixtures/
    ├── multica/                # FR-001..FR-008 fixtures from TUR-12 corpus
    ├── discord/                # FR-018 + FR-021 fixtures from pilot-bot session
    └── contract/               # FR-020 verdict-surface fixtures
```

## Entry command

```bash
python3 specs/003-classifier-test-suite/contracts/runner.py
```

(Direct-path invocation — the directory name contains dashes, so a
`python -m` module form is not importable. The fixture index is built
in memory on every run; no `index.json` file is written.)

See `../quickstart.md` for the full set of invocations.

## Spec back-references

- `../spec.md` — functional requirements (FR-001..FR-022) and success criteria (SC-001..SC-011)
- `../plan.md` — implementation plan; constitution check
- `../research.md` — Phase 0 decisions (subprocess discipline, evidence metadata, contract-test mechanism, id convention, suppressor-fixture handling)
- `../data-model.md` — fixture envelope, fixture metadata, runner result, adapter response shapes
- `../tasks.md` — atomic implementation tasks (produced by `/speckit-tasks`)

## Adapter contract (FR-022)

Any adapter MUST implement:

```python
class Adapter(Protocol):
    name: str                                                  # e.g., "subprocess:turnaware-admit"
    def classify(self, envelope: dict) -> dict: ...
        # Returns either {"ok": True, "verdict": "...", "confidences": {...},
        #                 "context_checked": [...], "raw_stdout": "..."}
        # or {"ok": False, "error_kind": "...", "error_detail": "...", ...}
        # See ../data-model.md section 4 for full schemas.
```

A new adapter is plugged in via `--adapter custom:path/to/file.py:ClassName`.
