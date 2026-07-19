# Independent rejection — `80c1de2`

**Target**: `80c1de2ed5941c1cc5d4e28ea3f13d84dc39b6d2`  
**Verdict**: REJECT  
**Review mode**: immutable Git-object reads and disposable detached probes; no
shared-worktree or lifecycle writes.  
**Authority**: review input only; not acceptance, handoff, integration,
deployment, release, promotion, or cutover authority.

## HIGH findings

### H1 — Caller mutation bypassed continuation direction authority

`fetch()` validated caller-owned request memory and then continued reading that
same mutable object. A barrier probe validated `before`, mutated it to an
unauthorized `after`, and served the `after` page. Closed later by Phase 24's
single private request/context copy at entry.

### H2 — Caller mutation defeated exact-document receipt authority

`build_observation_receipt()` compared caller memory with the pending private
copy, then reread caller memory while building the receipt. A barrier mutation
changed issued event bytes from 120 to 338; the receipt attested 338 and consumed
the original pending authority. Closed later by Phase 24 private-copy-only
validation/comparison/receipt construction.

### H3 — Shared governance manifest fabricated completion labels

The shared manifest normalizes checkbox state for graph identity and printed all
IDs under `Completed task IDs`, including literal unchecked gates. An attempted
shared-oracle modification was quarantined at `8f78ec5` because it exceeded
slice ownership. Phase 25 adds a separate slice-owned checker that reports
checked, explicitly superseded, and genuinely open IDs without changing the
shared oracle.

### H4 — Comparator erased expiry presence

`_normalized_continuation()` removed `expires_at` entirely, making expiring and
immortal authority equivalent. Phase 25 compares semantic
`expires_at_present` while keeping exact host-local clock values opaque.

### H5 — Undated retention eviction erased timestamp order

With retention two, `e1@00:00:10`, then undated `e2`, then undated `e3` evicted
`e1` and cleared the parseable watermark. `e4@00:00:05` was then accepted.
Phase 25 retains one constant-size provider/continuity-lifetime monotonic
parseable timestamp watermark independently of retained event membership.

### H6 — Missing relation targets claimed gap-free coverage

Missing reply/thread/reaction targets remained literal in events while
`coverage.has_gaps` was false. Phase 25 reports unavailable targets as gaps and
preserves exact `events`/`bytes`/`age` causes when a known retained target is
budget-excluded.

## Independent target receipts

The historical target itself passed:

- 42 focused tests;
- 166 Observation tests;
- 52 aggregate rows and 11 adversarial rows, all PASS;
- attempt-6 corpus 202/202 and framed digest
  `1ce18c9e9fc3b5aa820adcb1aad649c635fcb2ed64a7e644d4d5bba6aeb5d91f`;
- 1,415 repository tests with four optional skips;
- 60 verdict fixtures;
- Ruff, Bandit, exact scanner, governance, and diff checks.

Those green receipts did not override H1–H6. The exact eight downstream lanes
and separate slice-030 core-owner obligation were present; lifecycle remained
truthfully ACTIVE with no attempt-2 handoff claim.
