# Slice 020 candidate-attempt-2 preparation review — rejection

**Date**: 2026-07-19
**Review object**: immutable candidate `f38a4fe4cf98fd4d63887e0baf735db7427298f6`
**Mode**: independent read-only code/security/convergence review
**Verdict**: REJECT

## Findings

- **CRITICAL — Snapshot byte limits are not hard.** `src/nunchi/observation.py:1015-1037` inserts the trigger before checking `max_bytes`, violating `.specify/memory/constitution.md:82-84`, `specs/020-v2-observation/spec.md:221-226`, and SC-002 at `:289-293`. The evaluator never asserts observed bytes are within the configured cap (`evals/v2/observation/run_scenes.py:113-139`), allowing `evidence/v2/observation/budget-sweep.jsonl:4` to claim PASS with `configured_max_bytes=1` and `receipt_byte_count=156`. Command evidence: direct pinned-tree probe returned `BYTE_CAP_PROBE 1 115 ['e1'] ['bytes']`.

- **CRITICAL — The Phase 17 static-scan completion claim is not reproducible.** Constitution VI requires every completion claim to cite a reproducible command (`.specify/memory/constitution.md:145-146`), but `evidence/v2/observation/handoff.md:951` records only “high-confidence static secret scan over the working diff,” without the command, matcher set, or exact diff basis, while T082 is marked complete at `specs/020-v2-observation/tasks.md:756-758`. `git show f38a4fe…:evidence/v2/observation/handoff.md | sed -n '937,954p'` confirms the omission. A separate conservative scan returned `STATIC_SECRET_SCAN_CLEAN`, but cannot verify the unspecified recorded scan.

- **HIGH — Continuation fetch does not enforce originating-request merge deduplication.** The accepted contract requires a page colliding with its originating request to reject at fetch time (`docs/contracts/nunchi-v2.md:299-302`), and T015 claims exact merge deduplication (`specs/020-v2-observation/tasks.md:172-173`). Yet `ContinuationProvider` receives no originating-request identity set and checks uniqueness only within the returned page (`src/nunchi/observation.py:1239-1256`, `:1488-1490`). Command evidence: an originating snapshot containing `['e3','e4','e5']` accepted a page containing `['e1','e2','e3','e4']`; `ORIGIN_MERGE_PROBE` reported overlap `['e3','e4']`.

## Review execution note

Focused continuation, attempt-6 corpus, and complete Observation tests reran clean in
the read-only environment. The reviewer's attempted full repository rerun failed
because that sandbox exposed no writable temporary directory; this is an
independent-review environment limitation, not a product-test failure. The owner
matrix on the immutable candidate remained 1,376 passing tests with 4 optional
integration skips.

This review is input to correction only. It does not accept the slice or authorize
integration, cutover, deployment, release, or promotion.
