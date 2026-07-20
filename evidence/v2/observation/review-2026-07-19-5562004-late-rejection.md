# Slice 020 late immutable review — `5562004` rejection

**Date received**: 2026-07-19
**Review object**: exact commit `55620049a4abd63672951ea2bd221558846fe1df`
**Tree**: `a33bbedaedd3cea328751e99f15bb1743609bd7e`
**Patch SHA-256**: `ce20d17d430e01f46e5afe79545d1377dc9de5e80e694724e75019f659874d36`
**Verdict**: REJECT

This report arrived after later Phase 18 planning and implementation work had
started. Its verdict remains pinned to `5562004`; each mechanism is separately
adjudicated against the current tree.

## HIGH findings

### 1. Originating-request merge deduplication is absent

`ContinuationProvider.issue()` retains no originating request/event identity,
and `fetch()` validates uniqueness only inside the returned page. A default
`before` fetch can return events already delivered in the originating snapshot.

- Contract: `docs/contracts/nunchi-v2.md:299-302`
- Pinned probe: origin IDs `['e3','e4','e5']`; page IDs `['e3','e4']`;
  overlap `['e3','e4']`; fetch accepted.
- Disposition: already bound by Phase 18 T085–T086.

### 2. Snapshot `max_bytes` is not a hard cap

The trigger is inserted before its size is checked. The implementation returns
an oversized snapshot with `truncated_by=['bytes']`; its test and evaluator
false-pass that result.

- Pinned probe: configured bytes `1`; accepted bytes `149`; within cap `False`.
- Disposition: already bound by Phase 18 T083–T084.

### 3. Cursor-chain transient work is quadratic

Every resumed page copies the remaining tuple suffix and materializes a complete
live-index list.

- Pinned operation counts: N=64 → 1,953 index lookups; N=128 → 8,001;
  N=256 → 32,385.
- Disposition: already bound by Phase 18 T091–T092.

### 4. One-shot cursor consumption is not atomic

Validation, page construction, incoming-token discard, and successor
registration are not protected by a shared lock/CAS. A barrier probe allowed two
workers to consume the same one-shot token and return the same `['e4']` page.
The same check-then-insert race applies to handle and cursor capacity.

- Disposition: already bound by Phase 18 T089–T090.

### 5. Continuation coverage hides known retention gaps

Every fetch page hard-codes `has_gaps: false`, including after bounded retention
has evicted known history.

- Pinned probe: provider evicted history; page `['e2','e3']`;
  `has_more_before=false`; `has_gaps=false`.
- Current dirty-tree reproduction: retained `['e2','e3','e4']` with
  `provider_evicted=true`; page `['e2','e3']`; `has_more_before=false`;
  `has_gaps=false`.
- Disposition: bound by Phase 18 late extension T095–T096.

## MEDIUM finding

### 6. Packet evidence contains a false append-only claim

`evidence/v2/observation/handoff.md` says its T036/T038 historical text was
never edited and remained exactly as originally recorded. Git-object history
shows multiple non-prefix changes to that packet. Lifecycle files
`slice-candidate.md` and `slice-handoff.md` are append-only; the broader packet
claim is not truthful.

- Disposition: append a correction; do not rewrite the historical statement
  again (T097).

## Independently verified controls at `5562004`

- Focused continuation: 51 tests, OK.
- Observation: 126 tests, OK.
- Scenes: 45 rows (9+7+22+4+3), 0 FAIL.
- Attempt-6 corpus: 202/202 accounted for, 0 mismatches.
- Full suite: 1,375 tests, OK, 4 skipped.
- Verdict fixtures: 60.
- Ruff/Bandit/static added-line scan/governance/diff check: clean.
- T001–T079 manifest:
  `ca4742489a32b6631a99b212c533be4bbbde44b79bf2c5749952d662eeaf5fd0`.
- Eight downstream lanes plus separate Slice 030 core-owner obligation present.

Reviewer side effects: none. The report is review input only. It is not slice
acceptance or integration, deployment, release, promotion, or cutover authority.
