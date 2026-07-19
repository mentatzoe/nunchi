# Candidate attempts (append-only)

## Attempt 1 — CONVERGED

**Slice**: `020-v2-observation`

**Status**: CONVERGED

**Candidate commit**: `7b00bcaa4a2b8af12b6eb71bf6d8b098f4cfeba7`

**Tasks complete**: YES

**Completed task IDs**: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028, T029, T030, T031, T032, T033, T034, T035, T036, T037, T038, T039, T040, T041, T042, T043, T044, T045, T046, T047, T048, T049, T050, T051, T052, T053, T054

**Tasks SHA256**: b305267271aed22a83c98c3a95e8f967edfbe080115d9ee58d6a99eacaca4536

**Verification commands / results**: PASS — `PYTHONPATH=src python3 -m unittest discover -s tests/v2/observation -p 'test_*.py'` — 100 tests, OK; `PYTHONPATH=src python3 -m unittest tests.v2.observation.test_attempt6_corpus_conformance` — 5 tests, OK, all 202/202 upstream attempt-6 corpus cases accounted for; `PYTHONPATH=src python3 -m evals.v2.observation.run_scenes` — 5 suites, 32 rows, 0 FAIL; `PYTHONPATH=src python3 -m unittest` — 1349 tests, OK, 4 environment-dependent skips; `PYTHONPATH=src python3 -m evals.verdict_suite.runner --list` — 60 fixtures; governance boundary, CLI, task-manifest, and `git diff --check` — PASS. `/speckit-converge` appended no tasks and reported implementation, tests/evaluations, interfaces, evidence, documentation dispositions, and limitations aligned.

**Interface versions**: I-020A Observation Provider @1; consumed I-010A AttentionRequestV2@1, I-010D ContextContinuationV2@1, and accepted I-010E AttentionReceiptV2@2. The I-010E @2 amendment changes only the separately owned attention stage; `observationBody` and slice-020 implementation obligations are unchanged.

**Evidence paths**: `evidence/v2/observation/handoff.md`, `evidence/v2/observation/slice-activation.md`, `evidence/v2/observation/dependency-010-acceptance.md`, `evidence/v2/observation/dependency-010-amendment-A1-acceptance.md`, `evidence/v2/observation/identity-and-hygiene.jsonl`, `evidence/v2/observation/budget-sweep.jsonl`, `evidence/v2/observation/continuation.jsonl`, `evidence/v2/observation/s05-recoverability.jsonl`, `evidence/v2/observation/s13-equivalence.jsonl`, `evidence/v2/observation/convergence-2026-07-19.md`, `evidence/v2/observation/convergence-phase11-2026-07-19.md`, `evidence/v2/observation/pre-review-2026-07-19-sr-critic.md`

**Documentation freshness**: PASS — `docs/observation/v2.md` UPDATE landed and was validated; `docs/contracts/nunchi-v2.md` exact-path NO_IMPACT is evidence-backed; `README.md`, shared current-state docs, and eight downstream recipient deltas are explicit HANDOFF items naming their accepting owners.

**Known limitations**: this slice supplies transport-attested observation facts and bounded continuation only; it does not classify, route, invoke participants, guarantee transport persistence, or establish live-surface parity. Reference variants label continuity as `restart-safe`, `session-only`, `unknown`, or `known-gap`; downstream native-surface slices and the integrator own their live binding and final parity evidence. Full-suite skip counts vary with optional dependencies; the candidate has no test failures.

**Boundary**: this candidate does not authorize acceptance, integration, cutover, deployment, release, or promotion.

## Attempt 2 — CONVERGED

**Slice**: `020-v2-observation`

**Status**: CONVERGED

**Candidate commit**: `22a0a1ab9a996e82ec625ce73e301023889209e4`

**Candidate tree**: `ea186b389424f761a1cc5cbac8faac32f8c28484`

**Tasks complete**: YES

**Completed task IDs**: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027, T028, T029, T030, T031, T032, T033, T034, T035, T036, T037, T038, T039, T040, T041, T042, T043, T044, T045, T046, T047, T048, T049, T050, T051, T052, T053, T054, T055, T056, T057, T058, T059, T060, T061, T062, T063, T064, T065, T066, T067, T068, T069, T070, T071, T072, T073, T074, T075, T076, T077, T078, T079, T080, T081, T082, T083, T084, T085, T086, T087, T088, T089, T090, T091, T092, T093, T094, T095, T096, T097, T098, T099, T100, T101, T102, T103, T104, T105, T106, T107, T108, T109, T110, T111, T112, T113, T114, T115, T116, T117, T118, T119, T120, T121, T122, T123, T124, T125, T126, T127, T128, T129, T130, T131, T132, T133, T134, T135, T136, T137, T138, T139, T140

**Tasks SHA256**: 86e71d42acbeadc7759d70b64585dec5ae40798a1befc791a777821430a56a2a

**Verification commands / results**: PASS — Observation discovery 182 tests; aggregate scenes 53 rows and adversarial evidence 19 rows, zero FAIL; attempt-6 corpus 202/202 with framed digest `1ce18c9e9fc3b5aa820adcb1aad649c635fcb2ed64a7e644d4d5bba6aeb5d91f`; executable docs 13 tests; full repository 1,431 tests with four optional skips; 60 verdict fixtures; Ruff, production Bandit, scanner regressions, governance, literal task-state, reviewer-checklist absence, and diff checks clean; whole-slice scan CLEAN from `fc60858a3810e2f53d9574cce1eb9589bd19b55b` over 69 files, 10,249 additions, four matchers; independent Opus review APPROVE with no HIGH blocker.

**Interface versions**: I-020A ObservationProviderV2@1; consumed I-010A AttentionRequestV2@1, I-010D ContextContinuationV2@1, and accepted I-010E AttentionReceiptV2@2.

**Evidence paths**: evidence/v2/observation/handoff.md, evidence/v2/observation/slice-activation.md, evidence/v2/observation/dependency-010-acceptance.md, evidence/v2/observation/dependency-010-amendment-A1-acceptance.md, evidence/v2/observation/identity-and-hygiene.jsonl, evidence/v2/observation/budget-sweep.jsonl, evidence/v2/observation/continuation.jsonl, evidence/v2/observation/s05-recoverability.jsonl, evidence/v2/observation/s13-equivalence.jsonl, evidence/v2/observation/phase18-adversarial.jsonl, evidence/v2/observation/convergence-phase25-continuation-authority-2026-07-19.md, evidence/v2/observation/review-2026-07-19-80c1de2-late-rejection.md

**Known limitations**: this slice supplies transport-attested bounded observation and host-only continuation authority; it does not classify, route, invoke participants, guarantee transport persistence, establish downstream native-surface parity, accept itself, or authorize integration/cutover.

**Independent review**: APPROVE — `evidence/v2/observation/review-2026-07-19-phase25-opus-22a0a1a.md`; no HIGH correctness, resource, authority, evidence-integrity, or lifecycle blocker.

**Boundary**: candidate attempt 2 authorizes handoff review only. It does not
accept the slice or authorize integration, cutover, deployment, release, or
promotion.
