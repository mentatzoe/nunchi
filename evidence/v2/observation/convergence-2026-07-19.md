# Slice 020 convergence and plan-correction findings — 2026-07-19

**Slice**: `020-v2-observation`

**Source candidate commit**: `418432a50815fdc6875c13681cd18e64bdce32d7`

**Source workflow run**: `speckit-020-20260718T225136852105Z`

**Plan-correction workflow run**: `speckit-020-20260719T033702333611Z`

**Disposition**: append correction tasks while the slice remains `ACTIVE`; do not rewrite completed T001–T038 history.

## Phase 8 convergence findings

- **C020-01 — HIGH — reaction/membership documentation gap.** `docs/observation/v2.md` documents runnable `message` ingestion but does not equivalently document native `reaction` and `membership` event structure, literal relations, or honest-unavailability representation. Required task: T039.
- **C020-02 — HIGH — self-membership no-wake coverage gap.** The completed tests do not resolve whether a self-caused membership event is retained with `SELF_RETAINED_NO_WAKE` or whether the self check intentionally applies only to authored events. Required task: T040.
- **C020-03 — HIGH — event-visibility coverage gap.** The `event_visibility` coverage field exists in the provider but has no direct test/eval/evidence exercise. Required task: T041.
- **C020-04 — MEDIUM — inaccurate evidence claim.** The handoff calls the governance fixture repair a four-line addition while the committed diff contains nine insertions. Required task: T042.
- **C020-05 — MEDIUM — incomplete handoff recipients.** The handoff omits the declared `v2-wake-owner`, `v2-adapters-owner`, and `v2-security-owner` recipients. Required task: T043.
- **C020-06 — LOW — capability vocabulary too thin.** The reference-variant documentation does not explain how consumers should interpret `restart-safe`, `session-only`, `unknown`, and `known-gap`. Required task: T044.

## Phase 9 plan-correction findings

- **P020-01 — HIGH — nonexistent downstream owner lane.** Completed documentation and evidence name `v2-attention-owner`, but slice 030's declared accountable lane is `v2-core-owner`; no `v2-attention-owner` lane exists. Required tasks: T045/T046.
- **A020-F1 — HIGH — correction provenance missing.** Phase 8 and Phase 9 lacked a durable, severity-tagged correction source. This record plus the `Correction source` declarations in `tasks.md` resolves the finding.
- **A020-F2 — HIGH — inaccurate T046 locations and incomplete red gate.** The stray handoff occurrences are in `## Documentation dispositions (T028–T034)` → `### HANDOFF (accepting owner named per row...)` and `### Documentation dispositions, validation, and reviewer`; the downstream-obligations section contains none. T045 must gate both `docs/observation/v2.md` and `evidence/v2/observation/handoff.md` before T046 can be accepted.
- **A020-F3 — MEDIUM — advisory-only task ordering.** T045/T046 share files with T039/T044 and must have an explicit dependency rather than a concurrency caution.

## Verification boundary

This record is correction provenance only. It does not mark any appended task complete, establish convergence, create a candidate, accept a handoff, or authorize cutover/release/promotion. Each appended task remains unchecked until executed and verified inside a fresh bound slice-020 delivery run.

## Independent pre-review adjudication

**Review source**: `evidence/v2/observation/pre-review-2026-07-19-sr-critic.md`, produced by the read-only `sr-critic` Kanban worker against exact commit `418432a50815fdc6875c13681cd18e64bdce32d7`.

The reviewer re-ran the 84 observation tests, 28-row scene suite, full 1333-test repository suite, governance, and attempt-6 corpus conformance. Aleph independently reproduced the highest-severity new defect against the current branch before accepting it into the task graph.

- **H020-01 — HIGH — cross-direction cursor replay.** A cursor minted by a `before` fetch can be replayed under `after` for the same handle, returning an event already served on the first page (`['e4', 'e5']` followed by `['e3', 'e4']`). The cursor binding omits direction. Required tasks: T047–T048.
- **M020-01 — MEDIUM — stale completed-task SHA claim.** The handoff's T038-era full-manifest SHA claim became stale once convergence appended tasks. Historical activation prefix identity remains valid, but the current handoff needs an append-only supersession with the final full-manifest identity. Required task: T051.
- **M020-02 — MEDIUM — self-membership scope.** Accepted into existing T040. The selected design says “self-authored” events: membership events lack `author_id`, so `subject_actor_id == self` or `caused_by_actor_id == self` remains an ordinary observed fact. T040 must pin and test that author-attested scope explicitly.
- **M020-03 — MEDIUM — full-suite skip count mismatch.** Fresh runs return 1333 tests with 4 skips, while handoff evidence says 11 skips. Required task: T051.
- **M020-04 — MEDIUM — event-visibility propagation.** Accepted into strengthened T041: both snapshot and continuation-fetch coverage must propagate configured `event_visibility`, and evidence must record it.
- **L020-01 — LOW — around-fetch side coverage.** An `around` page may report both `has_more_before` and `has_more_after` as null even when truncated, preventing consumers from knowing which side has more context. Required tasks: T049–T050.

The review's remaining findings are already covered by T039, T042–T046. The accepted I-010E `@2` amendment is separately bound by `evidence/v2/observation/dependency-010-amendment-A1-acceptance.md`; current handoff evidence must append that version update before a candidate is proposed.
