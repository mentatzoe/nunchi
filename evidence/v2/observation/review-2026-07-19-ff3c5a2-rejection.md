# Slice 020 immutable review rejection — `ff3c5a2`

**Received**: 2026-07-19
**Verdict**: **REJECT**
**Candidate**: `ff3c5a2e71bb05cdba644c3a95f5346ef82987bb`
**Tree**: `f7d44c1c41e7533c5376b781e68e89e379a04e9f`
**Parent**: `1ac2ffe6836a9a674a9129364413d2c370082757`
**Phase base**: `5e2380af3c9abda63ff55c61f3ef16491cd1776c`
**Range diff SHA256**: `369f85d90aaa31e6e86d3edddf989eb17794d0df2cc0df410fe61834472a2aa4`
**Independent review artifact**:
`/Users/zmll/.hermes/cache/delegation/subagent-summary-0-20260719_121547_032150.txt`

The reviewer used a clean detached clone and did not retarget when the live branch
advanced. The verdict applies only to the exact candidate above.

## Blocking findings

1. **HIGH — mutable fetch request bypassed direction authority.** `fetch()`
   validated a caller-owned dictionary and reread it after validation. A gated
   mutation from authorized `before` to forbidden `after` served events `e4,e5`.
2. **HIGH — ingestion validated before copying.** A gated mutation after
   `_check_event()` committed an event whose `type` had never passed validation.
3. **HIGH — scanner fixture marker was a broad bypass.** Any source/evidence line
   carrying `slice020-secret-fixture` skipped all matchers.
4. **MEDIUM — active cursor capacity was checked after O(retention) work.** An
   over-limit fresh fetch visited all 256 retained events before rejecting.
5. **MEDIUM — preparation evidence was stale.** The exact candidate had 147
   focused tests, 1396 full tests, and 1357 scanned additions rather than the
   committed 146/1395/1307 receipt.
6. **MEDIUM — task-manifest completion ignored checkbox state.** T103 was open,
   but `--task-manifest` printed it under `Completed task IDs`; candidate
   validation trusted the normalized graph rather than literal committed checks.

## Passing controls

The reviewer independently confirmed exact closed host binding, exclusive expiry
with state reclamation, origin-overlap rejection before state mutation, hard
snapshot bytes, shared-lock atomicity, one-shot and hard-limit concurrency,
retention/reingestion generation rejection, zero cursor-replay deque visits,
copy isolation of returned documents, truthful retention gaps, corrected packet
provenance, and fail-closed planning/acceptance language.

## Disposition

- Finding 3 is superseded by pushed commits `0134cea` and `707f3e7`, which remove
  the marker exemption entirely and construct scanner fixtures dynamically.
- Findings 1, 2, 4, and 6 are current remediation work and require deterministic
  RED/GREEN evidence plus a new immutable review.
- Finding 5 can close only on the next exact immutable candidate receipt.

This rejection does not authorize candidate attempt 2, handoff, acceptance,
integration, release, deployment, promotion, or cutover.
