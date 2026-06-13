# Phase 1 Data Model: Classifier Verdict Test Suite

**Feature**: 003-classifier-test-suite | **Date**: 2026-05-25

The suite has four data shapes: the **fixture envelope** (input to the adapter), the **fixture metadata** (sidecar describing what the fixture asserts), the **runner result** (per-fixture JSONL line plus a final summary line), and the **adapter response** (the structured object the adapter returns from a classifier call). All four are JSON-shaped; all four are validated by `loader.py` or `report.py` at the appropriate boundary.

## 1. Fixture envelope (`<fixture-id>.json`)

Extends the public `turnaware admit --input` request shape (see `src/turnaware/schema.py::validate_request`). The classifier under test consumes the envelope as-is; extra fields are silently ignored by the current schema validator. We add `source_shape` at top level and optional `timestamp` on context items.

```jsonc
{
  "request_id": "fixture-d-vocative-greeting-first-bot",
  "source_shape": "discord",                     // "multica" | "discord"; extension over public schema
  "trigger": {
    "id": "msg-pilot-1747104742818",
    "author": "zoe",
    "content": "Hi all, are you there?",
    "timestamp": "2026-05-13T00:32:22.818Z"      // optional, present for discord-shape
  },
  "context": [],                                  // first-bot variant: empty context
  "agent": { "id": "dalgos", "role": "participant" },
  "surface": { "type": "discord-channel" }
}
```

Multica-shape envelope (existing convention from `tests/fixtures/pass.json`):

```jsonc
{
  "request_id": "fixture-m-substring-trap-back-results",
  "source_shape": "multica",
  "trigger": {
    "id": "comment-c8a85931-dfdc-48ab-8121-bc3c4d072f54",
    "author": "tpm",
    "content": "Dalgos — owner of TUR-9. Please proceed and comment back with results."
  },
  "context": [],
  "agent": { "id": "turnaware-dalgos", "role": "developer" },
  "surface": { "type": "issue-thread" }
}
```

**Required fields**: `request_id`, `trigger.content`. **Recommended**: `trigger.id`, `trigger.author`, `source_shape`, `agent.id`, `surface.type`. **Allowed extensions**: any field not in `FORBIDDEN_REPLY_FIELDS` (see `src/turnaware/models.py`); the validator silently ignores unknowns.

## 2. Fixture metadata (`<fixture-id>.meta.json`)

Sidecar file alongside each envelope. Carries everything the runner needs to interpret pass/fail, surface the failure mode, and group by source/evidence. Kept out of the envelope so the envelope stays a clean classifier request.

```jsonc
{
  "id": "d-vocative-greeting-first-bot",
  "title": "Vocative greeting to a room with no prior peer response",
  "source_shape": "discord",                                   // FR-019
  "evidence": "runtime",                                       // "runtime" | "predicted"; FR-004 / R2
  "runtime_source": "pilot-bot/6dc3f5aa#2026-05-13T00:32:22.818Z",
  "expected": {
    "verdict": ["SPEAK", "ACK"],                               // single string or list of acceptable verdicts
    "surface_contract": null                                    // "typed-verdict" only for c-* fixtures; FR-020
  },
  "failure_mode": "no-keyword input lands on ASK fallthrough (FR-006)",
  "invariant": "FR-018: vocative greeting in empty-context room is admission-worthy",
  "rationale": "First bot to see a room greeting must SPEAK an introduction or ACK presence; ASK-by-fallthrough is wrong because the operator did not ask a question that needs clarification.",
  "fr_refs": ["FR-018", "FR-006"],                              // back-pointers for SC-003
  "sc_refs": ["SC-010"]
}
```

For predicted-evidence fixtures, `runtime_source` is replaced by `predicted_basis`:

```jsonc
{
  "id": "m-substring-trap-co-owner",
  "evidence": "predicted",
  "predicted_basis": "_classify_text SPEAK branch matches 'owner' inside 'co-owner' per TUR-12 corpus comment",
  // ...
}
```

For verdict-surface contract fixtures (FR-020), `expected.surface_contract` is set:

```jsonc
{
  "id": "c-verdict-surface-sentinel-leak-3-underscores",
  "evidence": "runtime",
  "runtime_source": "pilot-bot/6dc3f5aa#2026-05-13T01:00:14.598Z",
  "expected": {
    "verdict": "PASS",                          // what the underlying envelope would mean
    "surface_contract": "typed-verdict"         // assert adapter response shape, not just verdict
  },
  "mock_adapter_output": "__CC_CONNECT_SILENT_PASS___",       // raw string the adapter sees; --mock-adapter-output path
  "failure_mode": "PASS-as-string sentinel leak (SC-011)",
  // ...
}
```

## 3. Runner result — JSONL line per fixture

Emitted on stdout, one per line, in fixture-id alphabetical order. Followed by exactly one summary line.

```jsonc
{
  "kind": "fixture-result",
  "id": "d-vocative-greeting-first-bot",
  "source_shape": "discord",
  "evidence": "runtime",
  "expected_verdict": ["SPEAK", "ACK"],
  "observed_verdict": "ASK",
  "observed_confidence": 0.85,
  "status": "fail",                                            // "pass" | "fail" | "error"
  "failure_mode": "no-keyword input lands on ASK fallthrough (FR-006)",
  "invariant": "FR-018: vocative greeting in empty-context room is admission-worthy",
  "adapter": "subprocess:turnaware-admit",
  "duration_ms": 31.7,
  "fr_refs": ["FR-018", "FR-006"],
  "sc_refs": ["SC-010"]
}
```

Summary line (always the last line of the JSONL stream):

```jsonc
{
  "kind": "summary",
  "fixture_count": 28,
  "pass_count": 6,
  "fail_count": 22,
  "error_count": 0,                                            // adapter-level errors (subprocess crash, malformed output)
  "by_source_shape": { "multica": { "pass": 4, "fail": 8 }, "discord": { "pass": 2, "fail": 13 }, "contract": { "pass": 0, "fail": 1 } },
  "by_evidence": { "runtime": { "pass": 6, "fail": 16 }, "predicted": { "pass": 0, "fail": 6 } },
  "duration_ms": 4127.3,
  "adapter": "subprocess:turnaware-admit",
  "classifier_commit": "a132ccc0f904d98914dab3b555f6c116d7841ea1"   // populated when adapter can identify it; null otherwise
}
```

Exit code: `0` if `fail_count == 0 && error_count == 0`; `1` otherwise. (FR-011.)

## 4. Adapter response shape

The adapter returns one of two object types from each `classify(envelope)` call:

```python
# Success — adapter received and parsed classifier output
{
  "ok": True,
  "verdict": "PASS",                              # ∈ {PASS, ACK, ASK, SPEAK}; FR-020
  "confidences": {"PASS": 0.85, "ACK": 0.05, "ASK": 0.05, "SPEAK": 0.05},
  "context_checked": ["trigger-id", "ctx-1-id"],
  "raw_stdout": "{...}",                          # for the report's debug-mode appendix; not in the JSONL line
}

# Failure — adapter-level error (subprocess crash, malformed output, schema violation, sentinel leak)
{
  "ok": False,
  "error_kind": "sentinel-leak" | "subprocess-crash" | "malformed-output" | "schema-violation" | "timeout",
  "error_detail": "adapter received '__CC_CONNECT_SILENT_PASS___' as classifier output; expected typed verdict",
  "raw_stdout": "__CC_CONNECT_SILENT_PASS___",
  "returncode": 0,
  "stderr": "",
}
```

The runner's per-fixture logic:

1. Call `adapter.classify(envelope)`.
2. If the metadata's `expected.surface_contract == "typed-verdict"` AND the response is `ok=False` with `error_kind="sentinel-leak"` (and the mock-adapter-output matches one of the SC-011 strings), the fixture **passes**: it asserted the negative case correctly.
3. If the response is `ok=False` for any other reason, the fixture is reported with `status="error"` and `failure_mode` derived from `error_kind`. Adapter-level errors do not count as verdict miscategorizations.
4. If the response is `ok=True`, the runner compares `verdict` against `metadata.expected.verdict`. The expected can be a string or a list-of-strings; any element-match is a pass.

## 5. Index registry (`contracts/index.json`)

Generated by `loader.py` at runner start by scanning `contracts/fixtures/**/*.meta.json`. Persisted to disk so the runner can also serve as a discoverability surface (`runner.py --list` prints the index). The index is regenerated on every run; it is not authoritative — the per-fixture meta files are.

```jsonc
{
  "generated_at": "2026-05-25T...",
  "fixtures": [
    {
      "id": "d-vocative-greeting-first-bot",
      "envelope": "fixtures/discord/d-vocative-greeting-first-bot.json",
      "meta": "fixtures/discord/d-vocative-greeting-first-bot.meta.json",
      "source_shape": "discord",
      "evidence": "runtime",
      "expected_verdict": ["SPEAK", "ACK"],
      "fr_refs": ["FR-018", "FR-006"]
    }
    // ...
  ]
}
```

## State transitions

There are no fixture state transitions; fixtures are immutable assets. The runner is stateless across runs (no caching per R5). The adapter has no state — every `classify()` call is independent. This is deliberate (FR-015 determinism).

## Validation rules

- **Loader validation**: every `*.json` envelope under `fixtures/` MUST have a sibling `*.meta.json`. Mismatch is a loader error (suite exits non-zero before any fixture runs).
- **Metadata validation**: `expected.verdict` MUST be a string-in-VERDICTS or a non-empty list of such strings. `source_shape` MUST be `"multica" | "discord"`. `evidence` MUST be `"runtime" | "predicted"`. Violations are loader errors.
- **Envelope validation**: each envelope MUST be `turnaware/schema.py::validate_request`-compatible (test by parsing through it at load time, NOT by running it through the adapter). This catches malformed fixtures before the adapter pays subprocess cost.
- **Index regeneration consistency**: if the on-disk `index.json` exists and disagrees with the freshly-walked index, the runner overwrites it and prints a one-line stderr notice. The on-disk index is a cache for `--list`, not a source of truth.
