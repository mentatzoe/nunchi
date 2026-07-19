# Phase 25 convergence — continuation authority and relation-gap truth

**Date**: 2026-07-19
**Slice**: `020-v2-observation`
**Rejected review target**: `80c1de2ed5941c1cc5d4e28ea3f13d84dc39b6d2`
**Current settled head reproducing all four mechanisms**:
`564c9d55f0fa0b5a81c8a3507d2060e0fc836d69`
**Review source**: independent Codex read-only archive probes. The reviewer
completed probes but its provider blocked final report generation; no approval
verdict exists.
**Status**: ACTIVE / BLOCKED

## Current-object RED

```text
expiry_presence {'equivalent': True, 'unexplained': [], 'explained': []}
handle_collision {'same': True, 'live': 1, 'stored_trigger': 'e2'}
cross_wrapper_cap {'same_lock': True, 'total': 2}
missing_relation {'has_more_before': False, 'has_more_after': False,
                  'has_gaps': False, 'truncated_by': [], ...}
```

1. The comparator removes `expires_at` entirely, so capability expiry presence
   can differ while requests remain equivalent. Exact clock values are opaque;
   capability presence is semantic.
2. A generated continuation handle collision overwrites the first live
   capability and its trigger authority.
3. Two `ContinuationProvider` wrappers share the provider lock but own separate
   registries, so each admits `max_handles` and the provider-wide total exceeds
   the declared cap.
4. A trigger with a literal reply/thread/reaction relation to an unavailable
   event returns `has_gaps: false`, contradicting the acceptance scenario that
   required relation omissions remain literal and have honest gap/truncation
   coverage.

## Required correction

1. Compare continuation expiry presence while leaving exact clock values opaque.
2. Generate continuation handles with collision retry/fail-closed behavior; no
   generated ID may overwrite live authority.
3. Move continuation capability/cursor registries and limits into one
   provider-owned shared state. Additional wrappers over that provider must use
   identical limits or reject, and the cap applies globally across wrappers.
4. Mark relation-target absence as `has_gaps: true`; if a known retained target
   cannot fit due an actual event/byte/age cap, preserve the exact truncation
   cause already produced by assembly.
5. Add direct and concurrent wrapper regressions, rerun the complete matrix and
   exact scan, freeze a successor, and obtain fresh independent review.

## Lifecycle effect

T131 is superseded by T138. The active Hermes review of `80c1de2` and any later
report are stale for approval, though their findings remain review input. Phase
24 caller-memory/resource/governance fixes at `564c9d5` remain settled inputs.
The slice remains `ACTIVE`; nothing here establishes `CONVERGED`,
`HANDOFF_READY`, acceptance, integration, deployment, release, promotion, or
cutover authority.
