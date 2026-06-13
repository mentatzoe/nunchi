---
description: "Atomic task list for 003-classifier-test-suite"
---

# Tasks: Classifier Verdict Test Suite

**Input**: Design documents from `/specs/003-classifier-test-suite/`

**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/README.md, quickstart.md

**Tests**: Runner self-tests are REQUIRED per Constitution V ("test-first contract and fixture discipline"). Fixture-level pass/fail IS the suite's product; runner self-tests live in `tests/test_003_runner.py`.

**Organization**: Tasks are grouped by user story (US1, US2, US3, US4) to enable independent implementation and verification. The MVP is US1 + US3 (both P1) plus enough of the Foundational phase to make them runnable.

## Format

```
- [ ] [TaskID] [P?] [Story?] Description with file path
```

## Path conventions

- Spec artifacts and contracts: `specs/003-classifier-test-suite/`
- Runner self-tests: `tests/test_003_runner.py`
- No modifications to `src/turnaware/` in this slice

## Reconciliation 2026-06-13

Checkbox state below was trued against the worktree after the implement commit `fd4cc37` and the merge of spec 002 (`main` @ `c78dcb4`): a task is `[x]` only if the file/fixture it names verifiably exists. Known deviations from task wording in completed work: the `--mock-adapter-output` CLI flag named in T009/T031 was implemented as the metadata-driven `mock_adapter_output` field instead (per data-model §2); the T012 baseline fixture ids shipped as `m-baseline-ask-ambiguous` / `m-baseline-speak-assigned` (shorter than the task's names); the T035/T037 self-tests shipped as `test_source_filter_union_equals_unfiltered_run` / `test_determinism_two_in_process_runs_byte_identical`. T020 originally shipped only the addressed variant; `d-named-ask-vigil-unaddressed` was authored under R2 on 2026-06-13. T044's `pytest` command is superseded by R1/R4 below (the repo forbids third-party deps; self-tests run via `python3 -m unittest`). Phase R captures the post-002 reconciliation work now in flight. Addendum: FR-005/FR-007/FR-008 invariant dispatch was wired into `runner.py::_run_one_fixture` on 2026-06-13 — before that only the FR-020 mock path and the inline FR-006 branch were applied, so T008's helpers existed but never ran; a fixture now passes only if its verdict matches AND its declared invariants hold (`tests/test_003_runner.py::InvariantDispatchTests` covers the violating paths).

---

## Phase 1: Setup (shared infrastructure)

- [x] T001 Verify directory skeleton at `specs/003-classifier-test-suite/contracts/{runner.py,adapters.py,loader.py,report.py,invariants.py,fixtures/{multica,discord,contract}}` exists (created in /speckit-plan; this task confirms layout and adds `__init__.py` stubs as needed for `python -m` invocation).
- [x] T002 [P] (Resolved 2026-06-13 via T002.1: direct-path invocation chosen; no shims needed.) Add `specs/__init__.py` and `specs/003_classifier_test_suite/__init__.py` shims (Python disallows dashes in module names; the `python -m specs.003-classifier-test-suite.contracts.runner` quickstart command therefore needs either a `__init__.py`-bearing alias package `specs/003_classifier_test_suite/contracts.py` re-export or the runner is invoked via direct path. Decide via T002.1 below.).
- [x] T002.1 [P] (Decided 2026-06-13: direct-path invocation `python3 specs/003-classifier-test-suite/contracts/runner.py`, documented in quickstart.md — no alias package, no bin script.) Decide invocation surface: either (a) add `specs/__init__.py` + `specs/_003_classifier_test_suite/__init__.py` (underscore-prefixed alias) re-exporting `contracts.runner.main`, or (b) ship a thin `bin/turnaware-verdict-suite` script that invokes `runpy.run_path` on the runner. Document the chosen invocation in the quickstart and update plan.md's "Structure Decision" if (b).

---

## Phase 2: Foundational (blocking prerequisites — MUST complete before any user story)

- [x] T003 [P] Implement `Adapter` Protocol in `specs/003-classifier-test-suite/contracts/adapters.py` per data-model.md section 4 (name + classify method; success/error response shapes).
- [x] T004 [P] Implement `SubprocessAdapter` in `specs/003-classifier-test-suite/contracts/adapters.py` per research.md R1 (shutil.which → sys.executable -m fallback, 10s timeout, stderr capture, error_kind classification for crash/malformed/timeout/sentinel-leak).
- [x] T005 [P] Implement `InProcessAdapter` stub in `specs/003-classifier-test-suite/contracts/adapters.py` (imports `turnaware.core.evaluate`; useful for future in-process candidates and for fast runner self-tests).
- [x] T006 [P] Implement fixture loader in `specs/003-classifier-test-suite/contracts/loader.py` per data-model.md section 5 (walk fixtures/, validate envelope-meta pairs, validate metadata fields per data-model.md "Validation rules", build index, surface loader errors before any adapter call).
- [x] T007 [P] Implement JSONL + human-readable report renderer in `specs/003-classifier-test-suite/contracts/report.py` per data-model.md section 3 (per-fixture lines, summary line, by_source_shape + by_evidence counts, exit-code logic deferred to runner.py).
- [x] T008 [P] Implement structural-invariant helpers in `specs/003-classifier-test-suite/contracts/invariants.py` (FR-005 trigger-only PASS check, FR-007 context_checked-completeness check, FR-008 confidence-not-constant check; consumed by runner per-fixture logic).
- [x] T009 Wire `runner.py` orchestration in `specs/003-classifier-test-suite/contracts/runner.py`: argparse (--format text|jsonl, --source multica|discord|contract|all, --adapter subprocess|in-process|custom:..., --cmd, --list, --mock-adapter-output), call loader, iterate fixtures in id-alphabetical order, dispatch to adapter, apply expected-verdict comparison + surface_contract handling per data-model.md section 4 "runner per-fixture logic", emit report, set exit code per FR-011.

**Checkpoint**: Foundation ready — fixture stories (Phase 3 onward) can land in parallel.

---

## Phase 3: User Story 1 — Implementer validates against Multica-shape failures (Priority: P1) 🎯 MVP

**Goal**: Multica-shape fixtures covering FR-001..FR-008 are reproducible against `a132ccc`; baselines pass.

**Independent test**: `python -m … contracts.runner --source multica` on `a132ccc` produces failures for at least FR-001 and FR-002 fixtures and passes for the four FR-003 baselines.

- [x] T010 [US1] Write FR-001 fixture pair `m-substring-trap-back-results.{json,meta.json}` under `specs/003-classifier-test-suite/contracts/fixtures/multica/` (envelope from TUR-9 `multica_speak_tur9.json` reconstruction; expected SPEAK; failure_mode names the "ack " inside "back " substring trap).
- [x] T011 [US1] Write FR-002 fixture pair `m-trigger-only-pass-fake-done.{json,meta.json}` (envelope from TUR-9 `multica_challenger_fake_done.json` reconstruction; expected non-PASS [SPEAK or ASK]; failure_mode names trigger-first short-circuit ignoring contradicting context).
- [x] T012 [P] [US1] Write four FR-003 baseline fixture pairs under fixtures/multica/: `m-baseline-pass-adapter-resolved`, `m-baseline-ack-broadcast`, `m-baseline-ask-ambiguous-scope`, `m-baseline-speak-assigned-cli-smoke`. Each MUST pass on `a132ccc`.
- [x] T013 [P] [US1] Write five FR-004 predicted-substring-trap fixture pairs under fixtures/multica/: `m-predicted-unresolved-pass`, `m-predicted-implement-note-speak`, `m-predicted-co-owner-speak`, `m-predicted-jigsaw-saw-it-ack`, `m-predicted-not-specified-yet-ask`. evidence="predicted", predicted_basis per each per research.md R2.
- [x] T014 [P] [US1] Write FR-005 trigger-only-PASS fixture pair `m-trigger-only-pass-empty-context.{json,meta.json}` (envelope: PASS-keyword-bearing trigger, empty context; expected non-PASS; invariant: "PASS requires corroborating context").
- [x] T015 [P] [US1] Write FR-006 ASK-fallthrough negative-control fixture pair `m-no-keyword-negative-control.{json,meta.json}` (no PASS/ACK/SPEAK/ASK keywords; expected NOT (ASK at 0.85); invariant: "ASK is not the fallthrough verdict").
- [x] T016 [P] [US1] Write FR-007 contradiction-audit fixture pair `m-contradiction-audit-both-listed.{json,meta.json}` (trigger and context disagree; assertion: context_checked names both items; invariant: "audit field reflects every consulted item").
- [x] T017 [P] [US1] Write FR-008 constant-confidence fixture pair `m-constant-confidence-mixed-support.{json,meta.json}` (ACK trigger inside PASS context; assertion via invariants.py FR-008 helper: winning verdict carries lower confidence than a clean baseline; invariant: "confidence is informative").
- [x] T018 [US1] (Adapted 2026-06-13: a132ccc expectations replaced by metadata-derived assertions under injected verdicts, per the reconciliation.) Self-test in `tests/test_003_runner.py`: add `test_us1_multica_fixtures_load_and_run` exercising T010–T017 fixtures end-to-end against InProcessAdapter (fast path); assert per-fixture status matches `a132ccc` expectations from research.md R5 — at minimum FR-001/002 fail, FR-003 baselines pass.

**Checkpoint**: US1 deliverable verified — `python -m … contracts.runner --source multica` reproduces the TUR-12 corpus failures on `a132ccc`.

---

## Phase 4: User Story 3 — Implementer validates against Discord-shape failures (Priority: P1)

**Goal**: Discord-shape fixtures covering FR-018 + FR-021 reproduce pilot-bot session failures on `a132ccc`.

**Independent test**: `python -m … contracts.runner --source discord` reports failures for vocative-greeting, bracketed-persona, casual-pivot-with-padding, and all four named-suppressor fixtures.

- [x] T019 [P] [US3] Write FR-018 vocative-greeting fixture pairs under fixtures/discord/: `d-vocative-greeting-first-bot.{json,meta.json}` (empty context, expected SPEAK|ACK) and `d-vocative-greeting-second-bot.{json,meta.json}` (one prior peer SPEAK in context, expected PASS via Covered).
- [x] T020 [P] [US3] Write FR-018 direct-named-ask fixture pairs `d-named-ask-dalgos-addressed.{json,meta.json}` (agent.id=dalgos, expected SPEAK) and `d-named-ask-vigil-unaddressed.{json,meta.json}` (agent.id=vigil, expected PASS).
- [x] T021 [P] [US3] Write FR-018 bracketed-persona-framing fixture pair `d-bracketed-persona-podcast.{json,meta.json}` from pilot-bot session 2026-05-13T22:25:45Z (expected SPEAK in-persona).
- [x] T022 [P] [US3] Write FR-018 casual-pivot-with-padding fixture pair `d-casual-pivot-stock-market.{json,meta.json}` from pilot-bot 2026-05-13T00:49:49Z (expected SPEAK to embedded ask, NOT ACK/PASS from padding substrings).
- [x] T023 [P] [US3] Write FR-018 test-of-restraint mixed-address fixture pairs `d-mixed-address-castor-addressed.{json,meta.json}` and `d-mixed-address-vigil-unaddressed.{json,meta.json}` from pilot-bot 2026-05-21T23:48:45Z (expected SPEAK for castor, PASS for vigil).
- [x] T024 [P] [US3] Write FR-018 operator-topic-pivot fixture pair `d-operator-topic-pivot-human-pet.{json,meta.json}` from pilot-bot 2026-05-13T00:43:54Z (long prior-topic context; expected SPEAK on new topic, NOT PASS via Covered from old topic).
- [x] T025 [P] [US3] Write FR-018 self-iteration loop fixture pairs `d-self-iteration-first-turn.{json,meta.json}` (expected SPEAK) and `d-self-iteration-late-turn-duplicate.{json,meta.json}` (prior-turn context echoes the agent's planned content; expected PASS via Duplicate).
- [x] T026 [P] [US3] Write FR-018 peer-message-imperative fixture pair `d-peer-imperative-as-observation.{json,meta.json}` (context contains a peer-bot saying "Verify X"; expected PASS unless net-new value, with no net-new value in this fixture).
- [x] T027 [P] [US3] Write FR-018 Discord-mention recipient-signal fixture pairs `d-mention-recipient-addressed.{json,meta.json}` (agent.id matches the `<@...>` target, expected SPEAK) and `d-mention-recipient-unaddressed.{json,meta.json}` (agent.id does not match, expected PASS).
- [x] T028 [P] [US3] Write FR-018 multi-step-constraint fixture pair `d-multi-step-constraint-story-order.{json,meta.json}` from pilot-bot 2026-05-13T01:08:16Z (compound instruction; expected SPEAK engaging the meta-step, NOT skipping to body).
- [x] T029 [P] [US3] Write FR-021 named-suppressor fixture pairs under fixtures/discord/: `d-suppressor-self-caused.{json,meta.json}`, `d-suppressor-stale.{json,meta.json}`, `d-suppressor-duplicate.{json,meta.json}`, `d-suppressor-covered.{json,meta.json}`. Each pair sets up the suppressor scenario in context; expected verdict PASS for all four; failure_mode names the missing suppressor per research.md R5.
- [x] T030 [US3] (Adapted 2026-06-13: suppressor-failure assertions derived from fixture metadata under injected verdicts, per the reconciliation.) Self-test in `tests/test_003_runner.py`: add `test_us3_discord_fixtures_load_and_run` exercising T019–T029 against InProcessAdapter; assert all FR-018 fixtures load + run; assert FR-021 four suppressor fixtures all fail on `a132ccc` (failure_mode names the missing suppressor).

**Checkpoint**: US3 deliverable verified — Discord-shape failure surface is encoded and runnable.

---

## Phase 5: Cross-story verdict-surface contract (Priority: P1, supports US1 + US3)

**Goal**: FR-020 + SC-011 satisfied — sentinel-leak surface failures are reportable and distinguishable from verdict miscategorizations.

- [x] T031 [US1] [US3] Implement `--mock-adapter-output <path>` flag wiring in `specs/003-classifier-test-suite/contracts/runner.py` and `adapters.py` (a MockAdapter that returns the file's raw content as classifier output, used ONLY by `c-*` fixtures per their metadata; documented in contracts/README.md).
- [x] T032 [P] [US1] [US3] (Mechanism note: the positive case omits `mock_adapter_output` and runs the real adapter — the mock path asserts rejection only.) Write FR-020 contract fixture pair `c-verdict-surface-typed.{json,meta.json}` under fixtures/contract/ (expected.surface_contract="typed-verdict"; positive case — actual subprocess adapter output expected to be valid typed verdict, fixture passes).
- [x] T033 [P] [US1] [US3] Write FR-020 sentinel-leak fixture pairs under fixtures/contract/: `c-verdict-surface-sentinel-leak-3-underscores.{json,meta.json}` and `c-verdict-surface-sentinel-leak-4-underscores.{json,meta.json}`. Each uses `mock_adapter_output` field per data-model.md section 2 (the malformed sentinel string) and asserts the adapter's response-validation path rejects it as error_kind="sentinel-leak"; fixture passes when rejection is observed.
- [x] T034 [US1] [US3] Self-test in `tests/test_003_runner.py`: add `test_contract_fixtures_sentinel_leak` exercising the MockAdapter path; assert the three c-* fixtures behave per FR-020.

**Checkpoint**: Sentinel-leak surface failure is a first-class assertion in the suite.

---

## Phase 6: User Story 2 — Reviewer accepts/blocks a PR using the suite as merge contract (Priority: P2)

**Goal**: Suite is reproducible across machines, filterable by source, output is parseable by automated CI.

- [x] T035 [P] [US2] Verify FR-019 `--source` filter behaviour: implement integration test in `tests/test_003_runner.py::test_us2_source_filter_consistency` that runs the suite three times (--source multica, --source discord, --source contract) and asserts the union matches the unfiltered run's per-fixture outcomes.
- [x] T036 [P] [US2] Verify FR-013 machine vs. human format parity: `tests/test_003_runner.py::test_us2_format_parity` runs `--format jsonl` and `--format text` and asserts the same set of fixtures and identical pass/fail status per fixture between the two forms.
- [x] T037 [P] [US2] Verify FR-015 determinism: `tests/test_003_runner.py::test_us2_determinism` runs the suite twice via InProcessAdapter; asserts JSONL output is byte-identical except for `duration_ms` fields (which are zeroed-out in test mode via the --deterministic-time flag added in this task).

**Checkpoint**: Reviewer-side guarantees are mechanized.

---

## Phase 7: User Story 4 — Contributor extends the suite (Priority: P3)

**Goal**: New fixtures land in under 5 minutes with no runner code change (SC-004).

- [x] T038 [US4] Add `--list` flag handler in `specs/003-classifier-test-suite/contracts/runner.py` printing the discovered fixture index per data-model.md section 5 in human-readable form (id, source, evidence, expected verdict, FR refs).
- [x] T039 [US4] (`--fixtures-root` already existed in runner.py — zero code changes, which is itself the task's proof.) Self-test in `tests/test_003_runner.py::test_us4_add_fixture_no_runner_change`: write a fresh fixture pair into a temp fixtures directory configured via `--fixtures-root` (added in this task), run the suite against it, assert the new fixture appears in the report with correct metadata-driven outcome — without any change to runner.py, adapters.py, loader.py, or report.py.
- [x] T040 [P] [US4] (Dry-run executed 2026-06-13: temp fixture flowed through with zero runner changes; quickstart offline payload corrected — `context_checked` must be `[]` — and step 4 wording clarified.) Verify quickstart end-to-end: dry-run the `quickstart.md` "Add a fixture" section from a clean state (copy template, edit, run) and update quickstart wording if any step is unclear.

**Checkpoint**: Extension ergonomics meet SC-004's 5-minute budget.

---

## Phase 8: Polish & cross-cutting

- [x] T041 [P] Update repo `README.md` with a one-paragraph "Verdict test suite" section linking `specs/003-classifier-test-suite/quickstart.md` and naming the single entry command.
- [x] T042 [P] Run the full suite against installed `turnaware` CLI at the worktree HEAD (which is at commit `a132ccc` plus the spec additions, classifier code unchanged); capture the summary line as evidence in a `specs/003-classifier-test-suite/evidence/a132ccc-baseline.jsonl` file. This is the suite's first runtime evidence and the input TUR-11's implementor consumes.
- [x] T043 (Retimed 2026-06-13: recorded in `evidence/perf-deterministic-2026-06-13.txt` against the post-002 deterministic path — p50 1.47s at 37 fixtures, PASS.) Verify SC-005 5-second budget: time the suite end-to-end three times; record p50 and max wall-clock; if the median exceeds 5s, file a follow-up issue (do NOT skip the SC).
- [x] T044 (Superseded 2026-06-13: pytest removed by R1; covered by `python3 -m unittest tests.test_003_runner -v` under R4.) Run all self-tests `pytest tests/test_003_runner.py -v`; verify pass.
- [x] T045 Mark Phase 2 of constitution check (post-Phase 1) PASS in plan.md if no new violations emerged during implementation.

---

## Phase R: Post-002 Reconciliation (added 2026-06-13)

**Goal**: Reconcile the suite with `main` after spec 002 merged (`c78dcb4`): the classifier under test is now the provider-backed product classifier (`src/turnaware/classifiers.py`); `a132ccc` is the historical baseline. These tasks are being executed now by the team.

- [x] R1 (Done 2026-06-13: 14 self-tests green offline via `python3 -m unittest tests.test_003_runner -v`.) Convert `tests/test_003_runner.py` from pytest to stdlib `unittest` (repo forbids third-party deps; run via `python3 -m unittest tests.test_003_runner`).
- [x] R2 (Done 2026-06-13: 10 pairs authored — the 6-case list plus `d-named-ask-vigil-unaddressed` from T020; 8 runtime-mined from the pilot-bot session log, 2 predicted; loader discovers all with zero errors.) Author the remaining 6 deferred Discord fixture cases from the T023–T028 region (mixed-address ×2, operator-topic-pivot, self-iteration ×2, peer-imperative, Discord-mention ×2, multi-step-constraint) under `specs/003-classifier-test-suite/contracts/fixtures/discord/`, then check the corresponding Phase 4 boxes.
- [x] R3 (Done 2026-06-13.) Update `spec.md` / `plan.md` / `quickstart.md` for the post-002 baseline reframe (a132ccc historical; main's product classifier as current evaluation target) and the FR-015 determinism re-scope (deterministic runner/self-test path vs. live evidence runs).
- [x] R4 (Done 2026-06-13: `evidence/unittest-2026-06-13.txt` — 65 tests OK offline, 21 of them suite self-tests.) Capture deterministic self-test evidence (`python3 -m unittest` green) on the merged branch.
- [x] R5 (Done 2026-06-13: live bake-off across 7 finalist models selected `google/gemini-3.1-flash-lite`; full-corpus live run captured as `evidence/0437537-live.jsonl` — 33/37 pass, 0 errors; rationale in `evidence/model-selection-2026-06-13.md`, per-model runs in `evidence/bakeoff-2026-06-13/`.) Capture a live evidence run against current `main`'s product classifier into `specs/003-classifier-test-suite/evidence/<sha>-live.jsonl` with an honest pass/fail summary.
- [x] R6 (Done 2026-06-13: index table added covering historical baseline, perf, unittest evidence, and the pending live slot.) Update `specs/003-classifier-test-suite/evidence/README.md` to index both baselines (`a132ccc-baseline.jsonl` historical; `<sha>-live.jsonl` current).
- [x] R7 (Done 2026-06-13: consistency pass complete; suite green, evidence indexed, PR updated.) Final consistency pass across all 003 artifacts and PR.

---

## Dependency notes

- T001 / T002 / T002.1 → block all subsequent phases (skeleton + invocation surface).
- T003..T009 (Phase 2 Foundational) → block ALL user-story phases.
- T010..T017 (US1 fixtures) can run in parallel except T010/T011 (FR-001/FR-002 are headline cases — write first for evidence).
- T019..T029 (US3 fixtures) can run in parallel.
- T031..T033 (verdict-surface contract) depend on T009 (--mock-adapter-output flag plumbing) and T004 (SubprocessAdapter response-validation).
- Phase 6 (US2) depends on Phases 3, 4, 5 being landable but not strictly complete.
- Phase 7 (US4) depends on Phase 6 (--source/--format guarantees) only minimally; can land in parallel with Phase 8 polish.
- T042 (a132ccc baseline evidence) is the final acceptance gate before this slice can be marked done.

## Parallel execution opportunities

- All Phase 2 [P] tasks (T003..T008) can run as a 6-way parallel batch — they touch separate files.
- All Phase 3 [P] tasks (T012..T017) can run as a 6-way parallel batch after T010/T011 land.
- All Phase 4 [P] tasks (T019..T029, excluding T030) can run as a 10-way parallel batch.
- All Phase 6 [P] tasks (T035..T037) can run in parallel.

## MVP scope

US1 (Phase 3) + US3 (Phase 4) + Phase 5 contract + the foundational Phase 2 = the runnable MVP. US2 (Phase 6) and US4 (Phase 7) are incremental quality work that does not gate first delivery; they SHOULD ship in the same PR but a separate follow-up is acceptable if a deadline forces it.

## Format validation

All tasks above conform to the required `- [ ] [TaskID] [P?] [Story?] Description with file path` shape per the speckit-tasks skill. File paths are absolute-relative-to-repo-root and reference real artifacts from data-model.md / plan.md / quickstart.md.
