# Independent pre-review: slice 020 observation at 418432a

Reviewer: sr-critic (read-only, scratch clone at
`/Users/zmll/.hermes/kanban/boards/nunchi-v2/workspaces/t_694140b1/scratch/nunchi-review`,
detached HEAD at `418432a`). Advisory only — no ACCEPTED/HANDOFF_READY decision.

## Verification re-run (scratch clone, safe, read-only)

- `git log --oneline -1 418432a` → `418432a feat(020): preserve observation implementation before convergence rework` (confirmed exact commit).
- `python3 scripts/check_governance.py --check-cli` → `governance boundary + CLI: OK (SpecKit 0.12.11)` (matches analysis-2026-07-18.md L43).
- `PYTHONPATH=src python3 -m unittest tests.v2.observation.test_attempt6_corpus_conformance -v` → 5 tests, OK (T037 reproduced: 202 cases, 100 consumed / 102 non-consumed, 0 mismatches, all 7 relational classes).
- `PYTHONPATH=src python3 -m unittest discover -s tests/v2/observation -p 'test_*.py'` → 84 tests, OK (matches handoff.md L95).
- `PYTHONPATH=src:. python3 -m unittest tests.v2.observation.test_docs` → 9 tests, OK (matches handoff.md L42).
- `PYTHONPATH=src:. python3 -m evals.v2.observation.run_scenes` → 5 suites, 28 rows, 0 FAIL (matches handoff.md L96).
- `python3 -m evals.verdict_suite.runner --list` → `60 fixture(s) discovered` (matches handoff.md L98).
- `PYTHONPATH=src python3 -m unittest` (full repo) → 1333 tests, OK, **4 skipped** (handoff.md L97/L319 claim **11 skipped** — see Medium M3 below).
- `python3 scripts/check_governance.py` → `governance boundary: OK (SpecKit 0.12.11)`.
- `python3 scripts/check_governance.py --task-manifest specs/020-v2-observation` → Initial/Completed SHA `1e4e45e9...` (T001–T044); activation record still pins `c261de...` for T001–T038 (prefix-check gate passes; see Medium M1).

## Findings (severity-ranked)

### HIGH H1 — Cross-direction cursor replay returns duplicate events (FR-009 gap, no test)

`ContinuationProvider.fetch` mints cursors as `{handle_id}:{next_index}` (src/nunchi/observation.py L1176) and `check_binding_expiry` only verifies the cursor was minted under the handle (L697-699), not that it matches the request's `direction`. A cursor minted by a `before` fetch can be replayed in an `after` fetch under the same handle, and the `after` request starts at that index reading forward, returning events already served by the `before` page. Per-page `check_id_uniqueness` (L1212) deduplicates only *within* a page, not across sequential pages of the same handle.

Reproduced in scratch clone:
```
page1 (direction=before, trigger e6): events=['e4','e5'], next_cursor='cont-...:2'
page2 (direction=after, cursor='cont-...:2'): events=['e3','e4']   # e4 already seen
```
FR-009 requires "deduplicate events only by continuity scope and event ID"; SC-003 requires fetch tests reject "cursor-replay" cases. The eval corpus (`evals/v2/observation/continuation/cases.jsonl` CONT-S03-004) only covers same-direction cursor replay, and `test_cross_handle_cursor_reuse_rejects` (test_budget_and_continuation.py L205) only covers cross-*handle* cursor reuse. No test or eval covers cross-*direction* cursor replay under the same handle. The cursor format should encode direction (or the validator should reject a direction mismatch), and a regression test should be added.

### MEDIUM M1 — Stale completed-task SHA256 claim in handoff.md (documentation freshness)

`evidence/v2/observation/handoff.md` L198 records `Tasks SHA256: c261de490e30e8e6c447dc5b204e463003f21cf38b69ca03c1895e58b00b6d31` and states it is "identical to the frozen Initial tasks SHA256". That was true when only T001–T038 existed, but the convergence phase has since appended T039–T044 (unchecked) to `specs/020-v2-observation/tasks.md`. The live `check_governance.py --task-manifest` now returns SHA `1e4e45e935d79c58100f11b70ee31e451fe18879c8f7e4066c9d62b014cc368c` for the full manifest. The activation record (slice-activation.md L39) correctly preserves the original `c261de...` for the T001–T038 prefix, and the governance prefix-check gate (check_governance.py L2136-2144) still passes because T001–T038 is an unchanged prefix. However, handoff.md L198's claim that the *completed* manifest SHA equals `c261de...` is now stale and inconsistent with the live CLI. Per the convergence contract, the candidate/handoff evidence should be updated (append-only) to reflect the appended T039–T044 and the resulting full-manifest SHA, or the T038-era record should be explicitly marked as superseded by the convergence rework.

### MEDIUM M2 — Self-membership events return `observed`, not `self-retained-no-wake` (FR-004 scope ambiguity, T040)

`ObservationProvider.ingest` self-check at src/nunchi/observation.py L883 is `SELF_RETAINED_NO_WAKE if event.get("author_id") == self.actor_id else OBSERVED`. Membership events have no `author_id` (they carry `subject_actor_id` and `caused_by_actor_id`), so a self-membership event always returns `OBSERVED`. Reproduced:
```
self-membership (subject_actor_id == self):  outcome='observed'        (not SELF_RETAINED_NO_WAKE)
self-membership (caused_by_actor_id == self): outcome='observed'        (not SELF_RETAINED_NO_WAKE)
self-message (author_id == self):            outcome='self-retained-no-wake'  (correct)
```
FR-004 says "retain-but-no-wake exact self events"; whether self-caused membership should be no-wake is an open scope question that T040 correctly flags. No test in `tests/v2/observation/test_provider.py` covers self-caused membership (the only membership test at L67 uses `discord:1001` as subject). This must be resolved (either the self-check is intentionally `author_id`-only and documented, or it should also cover membership `subject_actor_id`/`caused_by_actor_id`) before handoff.

### MEDIUM M3 — Full-suite skip count mismatch (11 vs 4)

`evidence/v2/observation/handoff.md` L97 states `PYTHONPATH=src python3 -m unittest` (repository baseline) → "1333 tests, OK, 11 skipped" and repeats "11 skipped" at L319. The activation baseline (analysis-2026-07-18.md L44, slice-activation.md L21) records "1,249 tests, 4 skipped". My fresh run in the scratch clone returns "1333 tests, OK, **4 skipped**". The test-count delta (1249→1333 = +84) is exactly the slice-020 contribution and matches, but the skip count (4 vs 11) does not. Either the handoff's "11 skipped" is a transcription error, or some skip source present at handoff time is no longer present at this commit. This is an evidence-claim defect (Constitution VI "Evidence Before Claims"); the recorded skip count should match a re-runnable command.

### MEDIUM M4 — `event_visibility` coverage field is untested and inconsistently propagated (FR-007, T041)

`event_visibility` is declared in the coverage schema (src/nunchi/observation.py L325, L345-351), accepted by `ObservationProvider.__init__` (L768, L783), and propagated to `snapshot()` coverage (L1009-1010), but:
- No test in `tests/v2/observation/` and no case in `evals/v2/observation/budgets/cases.jsonl` or `evals/v2/observation/continuation/cases.jsonl` exercises it.
- No evidence row in `evidence/v2/observation/budget-sweep.jsonl` records its outcomes.
- `ContinuationProvider.fetch` page coverage (L1196-1205) never propagates `self._provider.event_visibility` even when the provider has one, so a consumer reading a fetch page cannot see the visibility declaration that the snapshot would have included.

FR-007 requires coverage to "report configured limits, known pre/post-trigger omission, gaps, truncation causes, continuity, restart gaps, and event-kind visibility". T041 correctly flags this as partial. At minimum a test should assert `event_visibility` appears in snapshot coverage when set and is absent when not set, and the fetch-page coverage propagation should be made consistent (or the omission documented).

### LOW L1 — `tests/test_governance.py` diff-size claim contradicts actual diff (T042, Constitution VI)

`evidence/v2/observation/handoff.md` L313 states the `tests/test_governance.py` fix is "a four-line addition confined to that one helper". The actual diff at this commit is 9 insertions:
```
git diff --stat fc60858a..418432a -- tests/test_governance.py
 tests/test_governance.py | 9 +++++++++
```
The added block (L1534-1542) is a 9-line `if`/comment/`re.sub` block, not 4 lines. T042 correctly identifies this as a Constitution VI "Evidence Before Claims" contradiction. The handoff's "Known limitations" entry should be corrected to match the actual 9-insertion diff. (Note: the fix itself is legitimate shared test-infrastructure plumbing and is correctly flagged for `v2-integrator`/governance-tooling review rather than silently folded into the observation-slice diff.)

### LOW L2 — Docs lack reaction/membership ingestion examples (FR-003, T039)

`docs/observation/v2.md` §"Ingesting native events" only shows a `message`-event runnable example. `reaction` and `membership` events appear only in passing (L85 mentions `target_event_id` in the relation-closure description). T039 correctly flags this as partial: FR-003 requires "actor-targeted mention IDs and room-wide mention status MUST remain distinct, and unavailable facts MUST be represented honestly" for all three event kinds. `test_docs.py` asserts none of reaction/membership documentation presence. The reference provider and eval corpora do exercise these event kinds, but the user-facing guide should add runnable examples for `reaction` (with `target_event_id`/`operation`) and `membership` (with `scope`/`subject_actor_id`/`change`/`caused_by_actor_id`) alongside the message example.

### LOW L3 — Downstream recipients v2-wake-owner/v2-adapters-owner/v2-security-owner not named in handoff (T043)

`specs/020-v2-observation/spec.md` L47 declares `Feeds: 040, 050, 060, 070, 080, 090, 100, 110`. `evidence/v2/observation/handoff.md` §"Downstream comparator/recoverability/provenance obligations" (L265-280) names slices `050`, `060–090`, `040`, `110` by number but never names `v2-wake-owner` (040), `v2-adapters-owner` (090), or `v2-security-owner` (100) as explicit packet recipients. The assignment records exist (`evidence/governance/assignments/architect-v2-wake-owner-2026-07-16.md`, `mid-dev-v2-adapters-owner-2026-07-16.md`, `cc-session-blind-v2-security-owner-2026-07-16.md`) and `docs/architecture/v2-selected-design.md` confirms the owner-lane names (L331, L339, L343). T043 correctly flags this as partial; the Handoff Input Contract's "recipients" element should enumerate these three owners explicitly, not just their slice numbers.

### LOW L4 — Capability vocabulary listed but not explained (FR-011, T044)

`docs/observation/v2.md` L200-201 lists `restart-safe`, `session-only`, `unknown`, and `known-gap` but does not explain what each means or how a consumer should read a `known-gap` result. T044 correctly flags this as partial. The reference_provider.py docstrings explain each variant (L73-102), but the user-facing guide should lift that explanation into §"Reference variants and the comparator" so a downstream owner can interpret a `known-gap` coverage fact without reading the eval source.

### LOW L5 — `around`-fetch coverage reports `has_more_before`/`has_more_after` as null even on truncation

`ContinuationProvider.fetch` page coverage (src/nunchi/observation.py L1197-1198) sets `has_more_before`/`has_more_after` to `None` when `direction == "around"`, even when the page is truncated (`truncated_by: ["events"]`). The schema permits null (L332-333), so this validates, but a consumer cannot tell from these fields whether an `around` page was truncated on the before-side, after-side, or both. The handoff (L327-330) already discloses the `around` radius heuristic as a known limitation, but the `has_more_*` null-on-truncation behavior is an additional minor observability gap. Low severity.

## Amendment A1 (5e6fa37) — PROPOSED context, not accepted authority

Per the task instructions, amendment A1 commit `5e6fa37977df17259efd8217ab5589666ac717d1` is treated as PROPOSED compatibility context. I verified its claim that slice 020 cites `I-010E AttentionReceiptV2@1` (spec.md L254, plan.md, dependency-010-acceptance.md L11) — confirmed. A1's claim that `@2` changes only `attentionBody` and leaves `observationBody` byte-for-byte unchanged is **not independently verifiable at this commit** because `5e6fa37` is not in `418432a`'s ancestry (it is a same-date sibling commit). The `@1` schema at this commit (schemas/v2/attention-receipt.schema.json L12-28) shows `observationBody` with exactly the 7 fields the slice 020 implementation mirrors — no token field — consistent with FR-015. A1's recommendation that slice 020's owner "must record an explicit reacceptance/version-binding update to `@2` (spec/plan text only) before handoff, even though no implementation edit is owed" is a governance/contract-compatibility flag for the convergence rework to address, not a code defect in the slice 020 candidate at `418432a`.

## Scope ownership and selected-design consistency

- Owner lane `v2-observation-owner` assigned to Aleph (evidence/governance/assignments/aleph-v2-observation-owner-2026-07-16.md) — confirmed.
- Authority source cited as "Zoe-selected Aleph Vault design at `bdd1ebb`, contract-clarified in PR 68 at `c834e8c`" (spec.md L28) — these commits are not reachable from `418432a` in the scratch clone (predate the cloned ancestry window), so their content was not independently inspected in this review; their authority is accepted per the AGENTS.md authority order.
- File ownership: the diff touches only `src/nunchi/observation.py`, `tests/v2/observation/`, `evals/v2/observation/`, `evidence/v2/observation/`, `docs/observation/v2.md`, the slice's own SpecKit artifacts, and the one `tests/test_governance.py` fix (correctly flagged as out-of-lane shared infrastructure). No `schemas/v2/**`, `src/nunchi/core.py`, `src/nunchi/classifiers.py`, native transport, or `integrations/**` file is modified — consistent with plan §"Conflict ownership".
- Lifecycle: the commit message correctly states "Slice 020 remains ACTIVE; this commit does not claim CONVERGED, HANDOFF_READY, or ACCEPTED" — consistent with the tasks.md Phase 8 convergence rework (T039–T044 unchecked).

## Summary

The slice 020 implementation at `418432a` is substantively sound: the I-020A provider, continuation seam, observation-stage receipt, stdlib validation adapter, token-size proxy, reference variants, and attempt-6 corpus conformance all pass and match the spec/plan/FRs. The convergence findings T039–T044 are all valid and correctly scoped. The most substantive new finding (not already in T039–T044) is H1: a cross-direction cursor-replay gap that returns duplicate events across sequential fetch pages, violating FR-009's exact-event deduplication intent and uncovered by any test. The remaining findings are documentation-freshness and coverage gaps (M1–M4, L1–L5) that the convergence rework should close before handoff. Amendment A1 is a PROPOSED compatibility flag, not a code defect in this candidate.
