# Quickstart: Classifier Verdict Test Suite

**Feature**: 003-classifier-test-suite

This is the runnable, copy-paste integration doc the spec promises. If any command here does not work after `/speckit-implement` completes, that is a Constitution VIII violation — please file an issue.

> **Reconciliation 2026-06-13**: spec 002 merged to `main`; the classifier under test is now the provider-backed product classifier. Changes in this file: invocation corrected to the direct-path `python3 specs/003-classifier-test-suite/contracts/runner.py` form (the earlier `python -m specs.003-classifier-test-suite…` form is not importable — dashes are invalid in Python module paths); run instructions split into the offline deterministic path vs. the live provider evidence run; self-tests run via stdlib `unittest` (no pytest — the repo forbids third-party deps); `a132ccc` expectations retimed as the historical baseline.

## Run the suite — offline deterministic path

The classifier on `main` is provider-backed (spec 002). For a deterministic, offline run, inject a pinned classifier decision via `TURNAWARE_CLASSIFIER_TEST_RESULT`. The subprocess adapter inherits the environment, so the injected decision reaches the `turnaware` CLI:

```bash
# from repo root
pip install -e .                                          # one-time, installs the `turnaware` CLI
export TURNAWARE_CLASSIFIER_TEST_RESULT='{"verdict":"SPEAK","confidences":{"PASS":0.05,"ACK":0.05,"ASK":0.05,"SPEAK":0.8},"context_checked":[],"reasons":["pinned test verdict"]}'
python3 specs/003-classifier-test-suite/contracts/runner.py
```

(`context_checked` must be `[]` here: the core validates checked references
against each envelope, and the empty list is the only subset valid for every
fixture simultaneously. The winner confidence sits below the 0.85 FR-008
baseline so declared-invariant fixtures are judged on their verdict.)

Exit code is `0` if every fixture passed; `1` if any fixture failed or any adapter-level error occurred. Under a single pinned verdict, fixtures whose expected set does not contain that verdict report `fail` by design — a healthy pinned run shows zero `error` records and exit `1`.

This path is fully deterministic — byte-identical JSONL across repeated runs with `--deterministic-time` (FR-015 as re-scoped). Because every fixture receives the same pinned decision here, this run exercises the runner, loader, report, and contract plumbing; per-fixture verdict judgment is what the live run below measures. (The `unittest` self-tests pin per-fixture decisions instead.)

## Run the suite — live provider evidence run

To measure the actual product classifier, unset the test injection and provide the provider environment before running (the subprocess adapter inherits it):

```bash
unset TURNAWARE_CLASSIFIER_TEST_RESULT
export TURNAWARE_CLASSIFIER_MODEL="<provider-model-id>"   # e.g. an OpenRouter model id
export OPENROUTER_API_KEY="<key>"                         # or TURNAWARE_CLASSIFIER_API_KEY
python3 specs/003-classifier-test-suite/contracts/runner.py --format jsonl > evidence-run.jsonl
```

Live runs are **evidence runs**: the fixture set, report schema, and exit-code semantics are stable, but verdicts may vary run-to-run (temperature is pinned to 0, which reduces but does not eliminate variance, and provider/model updates can shift behaviour). Capture the JSONL as honestly timestamped evidence under `evidence/` (see `evidence/README.md`); never claim the live classifier passes a fixture without a captured run.

## Historical baseline (`a132ccc`)

The suite's first captured run was against the historical deterministic substring classifier at smoke commit `a132ccc`: exit code `1` with 13 failures, including the two false-verdict cases from FR-001 / FR-002, the four Discord-suppressor fixtures from FR-021 (no suppressor concept in that classifier — see research.md R5), and the bracketed-persona and vocative-greeting fixtures from FR-018 failing on the ASK fallthrough mechanism. Baselines (FR-003) passed. That run is preserved at `evidence/a132ccc-baseline.jsonl` and is the regression proof that the suite detects those failure classes; the current evaluation target is `main`'s product classifier.

## Get just the JSONL output for CI

```bash
python3 specs/003-classifier-test-suite/contracts/runner.py --format jsonl > results.jsonl
```

Each line is a `fixture-result` object; the last line is a `summary` object. See `data-model.md` for the schema.

## Filter to one source pool

```bash
python3 specs/003-classifier-test-suite/contracts/runner.py --source discord     # FR-019
python3 specs/003-classifier-test-suite/contracts/runner.py --source multica
python3 specs/003-classifier-test-suite/contracts/runner.py --source contract
```

Filtering does not change the pass/fail status of any included fixture; the unfiltered run and the unioned filtered runs report the same per-fixture outcomes.

## List fixtures without running them

```bash
python3 specs/003-classifier-test-suite/contracts/runner.py --list
```

Prints the index (id, source, evidence, expected verdict, FR refs) one per line.

## Add a fixture (under 5 minutes — SC-004)

1. Copy an existing fixture-pair as a template:

   ```bash
   cd specs/003-classifier-test-suite/contracts/fixtures/discord
   cp d-vocative-greeting-first-bot.json d-my-new-case.json
   cp d-vocative-greeting-first-bot.meta.json d-my-new-case.meta.json
   ```

2. Edit `d-my-new-case.json` — replace `trigger.content`, `trigger.id`, `request_id`, and any `context` items. Keep `source_shape` accurate. The envelope is a `turnaware admit --input` request; `turnaware admit --input d-my-new-case.json` should run end-to-end (with `TURNAWARE_CLASSIFIER_TEST_RESULT` or the provider environment set, per the run sections above).

3. Edit `d-my-new-case.meta.json` — set `id`, `title`, `expected.verdict`, `failure_mode`, `invariant`, `rationale`, `fr_refs`, `sc_refs`. If the case came from runtime evidence, set `evidence: "runtime"` and `runtime_source`; if it came from code reading, set `evidence: "predicted"` and `predicted_basis`.

4. Run the suite (with the offline injection or live provider environment from
   the run sections above). Your fixture appears in the report with no runner
   code changes.

   ```bash
   python3 specs/003-classifier-test-suite/contracts/runner.py --source discord
   ```

## Plug in a non-default adapter

The bundled subprocess adapter calls `turnaware admit --input <tmp>.json`. To test against an in-process candidate (imports `turnaware.core.evaluate` directly):

```bash
python3 specs/003-classifier-test-suite/contracts/runner.py --adapter in-process
```

To test against a CLI on a different path (e.g., a candidate build):

```bash
python3 specs/003-classifier-test-suite/contracts/runner.py --adapter subprocess --cmd /path/to/candidate-turnaware
```

To test a third-party / non-Python adapter, implement the `Adapter` protocol (see `contracts/adapters.py` `class Adapter(Protocol)`) and pass `--adapter custom:path/to/your_adapter.py:YourAdapter`.

## Run the runner's own self-tests

```bash
python3 -m unittest tests.test_003_runner -v
```

These exercise loader correctness, report shape, JSONL stream validity, the adapter contract, and the metadata-driven `mock_adapter_output` path that the verdict-surface contract fixtures rely on. They pin per-fixture classifier decisions via `TURNAWARE_CLASSIFIER_TEST_RESULT`, so they run offline and deterministically. They do NOT exercise live classifier judgment — that's what the evidence run does. The self-tests run in milliseconds; the actual suite runs in seconds on the deterministic path.

## Troubleshooting

- **`turnaware: command not found`** — run `pip install -e .` from repo root, or use `--adapter subprocess --cmd "$(python3 -c 'import sys; print(sys.executable)') -m turnaware"` to invoke the module directly.
- **`classifier provider model is required …` / `classifier provider API key is required …`** — the provider-backed classifier needs its environment. Either export `TURNAWARE_CLASSIFIER_TEST_RESULT` (offline deterministic path) or export `TURNAWARE_CLASSIFIER_MODEL` plus `OPENROUTER_API_KEY`/`TURNAWARE_CLASSIFIER_API_KEY` (live evidence run) before invoking the runner.
- **All fixtures report `error_kind: subprocess-crash`** — the adapter cannot find or execute the CLI, or the CLI is exiting on missing classifier environment. Verify directly with `turnaware admit --input tests/fixtures/pass.json` using the same environment.
- **Determinism check** — on the offline deterministic path, run twice with `--deterministic-time`; the JSONL output should be byte-identical (FR-015 as re-scoped). If not, file a bug. Live provider runs are NOT expected to be byte-identical — same command, same fixture set, same schema, honestly captured evidence.
