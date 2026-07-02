# Evidence

This directory carries runtime artifacts produced by exercising the suite.

## Index

| Artifact | Captured | Classifier under test | What it proves |
|----------|----------|----------------------|----------------|
| `a132ccc-baseline.jsonl` | 2026-05-25 | historical deterministic substring classifier (`a132ccc`) | the suite detects the 13 known failure classes (HISTORICAL — frozen; that classifier no longer exists on `main`) |
| `perf-deterministic-2026-06-13.txt` | 2026-06-13 | n/a (pinned injection, plumbing only) | SC-005 wall-clock budget on the deterministic path at 37 fixtures |
| `unittest-2026-06-13.txt` | 2026-06-13 | n/a (offline self-tests) | runner/loader/report/invariant machinery green via stdlib `unittest` |
| `0437537-live.jsonl` | 2026-06-13 | `main` product classifier on `google/gemini-3.1-flash-lite` | live judgment evidence for the selected model: 33/37 pass, 0 errors |
| `model-selection-2026-06-13.md` + `bakeoff-2026-06-13/` | 2026-06-13 | 7 finalist models | the live bake-off that selected the model; per-model full-corpus JSONL runs |
| `53d9262-rulebook-baseline.jsonl` | 2026-07-02 | rulebook prompt at `53d9262` (last main before social core) on `google/gemini-3.1-flash-lite` | pre-change baseline: 33/37 pass, 0 errors |
| `58e6871-social-core-live.jsonl` | 2026-07-02 | social-core prompt at `58e6871` on `google/gemini-3.1-flash-lite` | post-change evidence: 32/37 pass, 0 errors; see `social-core-2026-07-02.md` |
| `social-core-2026-07-02.md` | 2026-07-02 | rulebook vs social core | run comparison, flicker set, stable-failure adjudication, and the case for rerunning the bake-off under the social prompt |

## a132ccc-baseline.jsonl (historical)

The complete suite output (JSONL form, deterministic time zeroed) against the
public `turnaware` CLI at the original worktree HEAD. The classifier code at
capture time was the `a132ccc` smoke commit unchanged — the worktree's commits
were SpecKit artifacts only. Spec 002 has since replaced that classifier; this
file is preserved as the frozen regression record and is NOT reproducible
against current `main` (by design — the failures it records were since fixed).
Note: captured at the 19-fixture MVP corpus; the corpus has since grown to 37.

### Summary at capture time (2026-05-25)

```
19 fixtures total
  6 PASS:
     - 4 Multica baselines (FR-003 per-verdict): PASS, ACK, ASK, SPEAK
     - 2 contract sentinel-leak rejections (FR-020 / SC-011)
 13 FAIL (broken down):
   Multica:
     - m-substring-trap-back-results        false ACK from "ack " ∈ "back "  (FR-001)
     - m-trigger-only-pass-fake-done        false PASS, trigger-first short-circuit  (FR-002)
     - m-trigger-only-pass-empty-context    PASS from bare claim with empty context  (FR-005)
     - m-no-keyword-negative-control        ASK fallthrough at 0.85  (FR-006)
   Discord:
     - d-bracketed-persona-podcast          ASK fallthrough on persona framing  (FR-018)
     - d-casual-pivot-stock-market          ASK fallthrough; embedded ask missed  (FR-018)
     - d-named-ask-dalgos-addressed         ASK fallthrough on direct-named ask  (FR-018)
     - d-vocative-greeting-first-bot        ASK fallthrough on vocative greeting  (FR-018)
     - d-vocative-greeting-second-bot       no Covered suppressor  (FR-021)
     - d-suppressor-covered                 no Covered suppressor  (FR-021)
     - d-suppressor-self-caused             no Self-caused suppressor  (FR-021)
     - d-suppressor-duplicate               no Duplicate suppressor  (FR-021)
     - d-suppressor-stale                   no Stale suppressor  (FR-021)
  0 ERROR (no adapter-level failures)
```

### How this satisfies the spec's success criteria

- **SC-001**: ≥2 failures on `a132ccc` — 13 observed, including FR-001 and FR-002.
- **SC-002**: independently reproducible — `python3 -m unittest tests.test_003_runner -k test_determinism_two_in_process_runs_byte_identical` passes; two consecutive deterministic-path runs are byte-identical with `--deterministic-time`.
- **SC-003**: every required fixture class covered — FR-001, FR-002, FR-003 (×4), FR-005, FR-006, FR-018 (subset of the 11 named cases shipped at MVP), FR-020 (×2), FR-021 (×4).
- **SC-005**: full suite executes in ~0.7s (subprocess adapter, real CLI) and ~0.0s (in-process adapter) — well under the 5s budget.
- **SC-008**: distinguishes runtime vs. predicted in both forms — `evidence` field carried in JSONL, `[runtime]` / `[predicted]` prefix in human-readable.
- **SC-009**: source filter is correct — `tests/test_003_runner.py::test_source_filter_union_equals_unfiltered_run` passes.
- **SC-010**: Discord-pilot-shape cases exercised — 9 Discord fixtures shipped at MVP (vocative ×2, persona, casual pivot, named ask, 4 suppressors); FR-018's full 11-case enumeration has 6 cases deferred to follow-up (mixed-address, operator-pivot, self-iteration ×2, peer-imperative, Discord-mention ×2, multi-step constraint) — tracked under tasks.md Phase 4.
- **SC-011**: sentinel-leak rejected and labelled as such — `error_kind: "sentinel-leak"` distinct from `error_kind: "schema-violation"`.

### MVP scope vs. full FR-018 enumeration

At MVP capture time the suite covered 5 of the 11 named Discord-shape cases
(FR-018) plus the 4 named-suppressor fixtures (FR-021). The remaining cases
(mixed-address ×2, operator topic-pivot, self-iteration ×2, peer-imperative,
Discord-mention ×2, multi-step constraint, named-ask unaddressed variant)
were authored on 2026-06-13 with zero runner changes — confirming the
extension-ergonomics claim. The corpus now stands at 37 fixtures (15 multica,
19 discord, 3 contract).

### Reproducing evidence against the current classifier

The historical baseline cannot be re-produced (its classifier is gone). To
capture fresh evidence against `main`'s product classifier, follow the "live
provider evidence run" section of `../quickstart.md` and save the JSONL here
as `<main-sha>-live.jsonl`. For deterministic plumbing evidence, use the
pinned-injection run from the same quickstart; it must report zero `error`
records and be byte-identical across consecutive `--deterministic-time` runs.
