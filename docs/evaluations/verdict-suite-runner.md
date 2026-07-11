# Classifier Verdict Suite Runner

The repository-owned runner package is the **vendored** test-suite artifact
required by V1 FR-017. Everything is checked into the repository, runs offline,
and has no remote dependencies or SpecKit-path dependency.

## Layout

```text
evals/verdict_suite/
├── __init__.py                 # importable package
├── runner.py                   # CLI entry point + orchestration (FR-011, FR-013, FR-019)
├── adapters.py                 # Adapter protocol + SubprocessAdapter (default) + InProcessAdapter (stub)
├── loader.py                   # walks fixtures/, validates pairs, builds the in-memory index
├── report.py                   # JSONL + human-readable rendering (FR-012, FR-013)
├── invariants.py               # FR-005..FR-008 + FR-020 structural-invariant assertion helpers
└── fixtures/
    ├── multica/                # FR-001..FR-008 fixtures from TUR-12 corpus
    ├── discord/                # FR-018 + FR-021 fixtures from pilot-bot session
    ├── contract/               # FR-020 verdict-surface fixtures
    ├── injection/              # adversarial injection eval pack (i-*): gate
    │                           # steering, verdict spoofing, unicode/markdown
    │                           # smuggling, sentinel forgery, history injection
    ├── tool-chrome/            # peer-tool-chrome pool (t-*): peer-bot tool-use
    │                           # chrome (skill_view/search_files markers, todo
    │                           # lists, compaction notices) is not an invitation
    └── addressing/             # multi-identity addressing pool (a-*): one agent
                                # carrying several identities (id, mention
                                # snowflake, display name, secondary handles) via
                                # agent.aliases; a message targeting ANY of them
                                # is addressed to this agent, an alias in passing
                                # prose is not an address
```

## Entry command

```bash
python3 -m evals.verdict_suite.runner
```

(The fixture index is built in memory on every run; no `index.json` file is
written.)

See [`verdict-suite.md`](verdict-suite.md) for the full set of invocations.

## Product-contract back-references

- [`../contracts/verdict-suite-requirements-v1.md`](../contracts/verdict-suite-requirements-v1.md)
  — the stable FR-001..FR-022 and SC-001..SC-011 identifiers carried by fixture
  metadata.
- [`../contracts/verdict-suite-data-model-v1.md`](../contracts/verdict-suite-data-model-v1.md)
  — fixture envelope, metadata, runner result, and adapter response shapes.
- [`../../evidence/verdict-suite/README.md`](../../evidence/verdict-suite/README.md)
  — indexed historical and live run records.

## Adapter contract (FR-022)

Any adapter MUST implement:

```python
class Adapter(Protocol):
    name: str                                                  # e.g., "subprocess:turnaware-admit"
    def classify(self, envelope: dict) -> dict: ...
        # Returns either {"ok": True, "verdict": "...", "confidences": {...},
        #                 "context_checked": [...], "raw_stdout": "..."}
        # or {"ok": False, "error_kind": "...", "error_detail": "...", ...}
        # See docs/contracts/verdict-suite-data-model-v1.md section 4.
```

A new adapter is plugged in via `--adapter custom:path/to/file.py:ClassName`.
