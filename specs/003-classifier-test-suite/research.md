# Phase 0 Research: Classifier Verdict Test Suite

**Feature**: 003-classifier-test-suite | **Date**: 2026-05-25

This document resolves the planning unknowns enumerated in `plan.md`. Each entry follows the Decision / Rationale / Alternatives format the speckit-plan skill prescribes.

## R1 — Public CLI invocation from the runner (subprocess discipline)

**Decision**: Use `subprocess.run(["turnaware", "admit", "--input", str(path)], capture_output=True, text=True, check=False, timeout=10.0)` from a `SubprocessAdapter` class. Resolve the `turnaware` executable by walking `shutil.which("turnaware")` first, then falling back to `sys.executable -m turnaware` for development checkouts where the script isn't installed. Capture stdout (parsed JSON), stderr (kept verbatim for failure messages), and the return code. A non-zero return code with non-JSON stdout is an adapter-level error (distinct from a verdict miscategorization, per FR-022).

**Rationale**: `subprocess.run` with `text=True` and explicit `timeout` is the deterministic, portable shape on macOS and Linux. `check=False` because the runner — not Python — owns the pass/fail interpretation; raising on non-zero would force the runner to wrap every call in `try/except`. The `shutil.which` → `sys.executable -m` fallback covers both "pipx-installed" and "dev checkout, editable install not done" cases, which were both seen during TUR-8/9/10 smoke. The 10s timeout is far beyond the 50ms target so it never fires in steady state but catches hangs.

**Alternatives considered**: `subprocess.check_output` — rejected because it raises on non-zero, hiding the adapter-level error from the runner. `os.popen` — rejected, returncode handling is awkward. Importing `turnaware.cli.main` and capturing stdout via `contextlib.redirect_stdout` — works in process and is faster, but it's the in-process adapter (R3 below), not the subprocess adapter; it's a different tier and ships as a separate adapter class.

## R2 — Predicted vs. runtime-observed in fixture metadata

**Decision**: Each fixture carries a top-level metadata key `evidence: "runtime"` or `evidence: "predicted"` in its companion metadata block (kept alongside the envelope, not inside it, so the envelope stays a clean `turnaware admit` request). Runtime fixtures additionally carry `runtime_source` (e.g., `tur-9#multica_speak_tur9.json@a132ccc` or `pilot-bot/6dc3f5aa#2026-05-13T00:32:22.818Z`); predicted fixtures carry `predicted_basis` (a one-line pointer to the code-reading hypothesis, e.g., `_classify_text PASS branch matches "resolved" inside "unresolved"`).

The runner surfaces `evidence` in both the JSONL stream (as a field) and the human-readable output (as a `[runtime]` / `[predicted]` prefix on each failing line). The summary block counts failing fixtures by evidence class so SC-008 ("a reviewer can count, without manual cross-reference, how many of the open failures are backed by runtime evidence") is directly satisfied.

**Rationale**: Keeping `evidence` out of the envelope itself is what lets the same JSON file pass straight through `turnaware admit --input` without modification (forward-compat with FR-009's "extra fields the classifier ignores MUST NOT cause validation failures" — verified against `turnaware/schema.py::validate_request` which silently ignores unknown keys, but we keep it out of the request body anyway for cleanliness).

**Alternatives considered**: Two parallel directory trees (`fixtures-runtime/`, `fixtures-predicted/`) — rejected, makes index.json walk awkward and obscures the per-fixture evidence call-out in the report. A boolean `is_runtime: true` — rejected, can't be extended to a future third category (e.g., "regression-from-PR-NNN") without renaming.

## R3 — Verdict-surface contract test for FR-020 without Python-type coupling

**Decision**: The verdict-surface contract fixture is a *paired* construct: a normal envelope (which `turnaware admit` consumes to produce an output) PLUS an adapter-level response-validation assertion that runs against the *output* — checking that the output JSON has a top-level `verdict` key whose value is `∈ {PASS, ACK, ASK, SPEAK}` (a JSON string, not a sentinel like `"__CC_CONNECT_SILENT_PASS___"` and not a missing field). The fixture's `expected` block carries an additional key `surface_contract: typed-verdict` which the runner interprets as "also assert the adapter response shape", in addition to whatever verdict-classification expectation is set. A second, paired fixture asserts the negative case: the runner feeds a *mocked* adapter output containing the literal sentinel string into the response-validation path and asserts that the validator rejects it as a contract failure distinct from a mis-verdict.

For the negative-side fixture, the runner exposes a `--mock-adapter-output <path>` CLI flag that injects raw JSON in place of the actual subprocess call; this is used only by contract fixtures, never by the verdict fixtures, and it's documented as such in `contracts/README.md`. This keeps the runner honest (no special hidden code paths for "contract" fixtures) and makes the contract-test mechanism portable to any future adapter (Rust / Go / Node) — that adapter just needs to also reject malformed-sentinel outputs as contract failures.

**Rationale**: This satisfies SC-011 ("failure message distinguishes 'sentinel-leak surface violation' from 'verdict miscategorization'") at the adapter response-validation layer where it belongs (per the clarify session). It also satisfies the principle that the contract must hold for non-Python adapters — by expressing the contract as "the adapter response JSON has a typed verdict field", not as "the adapter returns a Python enum", we keep the surface portable.

**Alternatives considered**: Asserting via `isinstance()` on the adapter's Python return type — rejected, couples the contract to one language. Adding a separate `contract_runner.py` for these fixtures — rejected, increases the API surface and creates a "contract tests are special" smell; the `--mock-adapter-output` flag is the minimum-surface alternative.

## R4 — Fixture id naming convention

**Decision**: Fixture ids are kebab-case, prefixed with the source pool and a short failure-class tag, then a human-readable suffix:

- Multica-shape: `m-substring-trap-back-results`, `m-trigger-only-pass-fake-done`, `m-baseline-pass-adapter-resolved`, …
- Discord-shape: `d-vocative-greeting-first-bot`, `d-vocative-greeting-second-bot`, `d-named-ask-dalgos-claudemd`, `d-bracketed-persona-podcast`, …
- Contract: `c-verdict-surface-typed`, `c-verdict-surface-sentinel-leak-3-underscores`, `c-verdict-surface-sentinel-leak-4-underscores`.

Ids are also the filename stem (e.g., `d-vocative-greeting-first-bot.json` + `d-vocative-greeting-first-bot.meta.json`). The `index.json` registry maps each id to its envelope path, metadata path, expected verdict (or set), failure-mode tag, source-shape, and evidence class.

**Rationale**: The prefix (`m-` / `d-` / `c-`) lets a reader visually parse the pool at a glance and matches the `--source` filter (FR-019). The failure-class tag (`substring-trap`, `trigger-only-pass`, `vocative-greeting`, `bracketed-persona`, `verdict-surface`, etc.) lets a reader group failures without parsing the full id. Kebab-case is filesystem-portable.

**Alternatives considered**: Numeric ids (`m-001`, `d-001`) — rejected, opaque in reports; you can't tell what `m-007` is without opening it. Full UUID — rejected, useless in human reports. Hash of envelope content — rejected, changes on every fixture edit, breaks SC-002's reproducibility-across-machines expectation.

## R5 — Discord-suppressor fixtures against the current `a132ccc` classifier

**Decision**: All four Discord-suppressor fixtures (FR-021: `Self-caused`, `Stale`, `Duplicate`, `Covered`) are expected to **fail** on the current `turnaware.core.evaluate` because the deterministic substring path has no suppressor concept — it only knows the four-keyword PASS/ACK/ASK/SPEAK branches. The failure mode column in the report for each of these fixtures reads:

- `Self-caused` fixture → expected PASS, observed ASK-by-fallthrough → failure mode: `no Self-caused suppressor; classifier ignored "trigger is receiving agent's own prior message" signal`
- `Stale` fixture → expected PASS, observed ASK-by-fallthrough → failure mode: `no Stale suppressor; classifier ignored "session closed" signal in context`
- `Duplicate` fixture → expected PASS, observed ASK-by-fallthrough → failure mode: `no Duplicate suppressor; classifier ignored receiving agent's own recent contributions`
- `Covered` fixture → expected PASS, observed ASK-by-fallthrough → failure mode: `no Covered suppressor; classifier ignored peer's prior coverage signal`

These failures are the suite doing its job — surfacing structural gaps in the classifier so a TUR-11 implementor can decide whether to add suppressors, change the verdict-default policy, or formally declare them out of scope.

**Rationale**: The suite's job is to encode the contract the verdict surface must meet for both Multica-shape and Discord-shape inputs. The current classifier was built for Multica-shape only; this is a known gap, not a bug discovered here. By making the fixtures explicit and the expected failure-mode explicit, the suite makes that gap visible without forcing a particular fix.

**Alternatives considered**: Marking the suppressor fixtures `skip` until suppressors exist — rejected, defeats the purpose of the suite. Tagging them `expected-fail` (so they don't count as failures) — rejected, hides the gap from CI. The chosen approach (real failures with documented mode) keeps SC-001's "at least two failures on `a132ccc`" honest while making the count larger and more informative.

## Cross-cutting decisions surfaced during research

- **No new third-party dependency.** Everything fits in stdlib. This keeps SC-005 (5-second budget) achievable and avoids polluting the `pyproject.toml` for a test-only artifact.
- **Sort fixture execution by id alphabetically.** SC-002's "two reviewers, identical output" requires deterministic order. Alphabetical id ordering is the simplest mechanism that requires no per-fixture priority field.
- **The runner does NOT cache adapter results across runs.** Even though caching would speed up "re-run after editing one fixture", caching introduces a deterministic-but-confusing-to-debug failure mode where stale results survive a classifier upgrade. The 5-second budget covers cold runs.
- **No parallel subprocess execution at v1.** The 5-second budget is achievable single-threaded for ~30 fixtures; introducing concurrency adds a non-determinism risk in stdout ordering. If a future suite grows past 100 fixtures we can revisit.
