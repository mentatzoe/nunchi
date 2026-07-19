# Independent Phase 25 review — `22a0a1a`

**Verdict**: APPROVE
**Target**: `22a0a1ab9a996e82ec625ce73e301023889209e4`
**Tree**: `ea186b389424f761a1cc5cbac8faac32f8c28484`
**Reviewer**: independent Claude Opus, no-tools review of an exact Git-generated
packet containing the full implementation, comparator, task-state checker, and
complete Phase 25 diff.
**Boundary**: review input only; not acceptance, integration, deployment,
release, promotion, or cutover authority.

No HIGH correctness, resource, authority, evidence-integrity, or lifecycle
blocker was found.

## Verified mechanisms

### Provider-wide continuation state

`ContinuationProvider.__init__` installs or reads one
`provider._continuation_state`; every wrapper aliases the same capability,
cursor, sequence, and window dictionaries. All state transitions remain under
the provider-owned re-entrant lock. Mismatched limits reject at wrapper
construction, and concurrent issue/revoke/fetch operations therefore share one
global cap.

### Generated handle collisions

`issue()` retries a generated ID at most 16 times, accepts only an ID absent from
the shared capability registry, and raises `ContinuationError` after exhaustion.
Assignment occurs only after successful generation and validation, so no live
authority can be overwritten. Direct retry and exhaustion-preservation tests
cover both paths.

### Expiry comparison

The comparator drops exact `handle_id` and `expires_at` values but adds
`expires_at_present`. Host-local clock values remain opaque while immortal and
expiring authority remain semantically different. Unit and CAP-S13-009 evidence
cover this distinction.

### Relation-gap truth

Snapshot assembly marks a relation gap whenever a literal target is unavailable
or not selected. Missing targets add no invented truncation cause; known retained
targets rejected by event/byte/age budgets keep the exact cause emitted by
assembly. Reply, thread, reaction, and all three budget causes are covered.

### Lifetime timestamp order

The retention-time reset/recompute branch was removed. The provider's last
parseable timestamp is now only advanced by an accepted parseable event, whose
existing ordering gate requires it to be greater than or equal to the current
watermark. The scalar therefore survives source-event eviction and remains
constant-space and monotonic.

### Literal task state

The slice-owned checker is read-only, requires unique contiguous T001–T140 IDs,
reports checked/superseded/open sets separately, and fails on unexplained open
IDs or stale allowed-open IDs. It does not modify the shared normalized
governance oracle.

### Existing authority/state invariants

Phase 24 private-copy-at-entry behavior for fetch, ingest, and receipt remains
intact. Shared-state migration preserves one-shot cursor replacement,
`_discard_cursor`, retention generation checks, origin-overlap rejection, hard
resource bounds, and returned-document isolation.

### Lifecycle truth

The reviewed object remained `ACTIVE`, with T103/T140 open and explicit
statements that it was not `CONVERGED`, `HANDOFF_READY`, accepted, or authorized
for cutover. Closing those gates in a receipt-only successor is consistent with
the append-only lifecycle model.

## Exact-object receipts independently supplied to the review

- 182 Observation tests, OK;
- 53 aggregate rows, 0 FAIL;
- 19 adversarial rows, 0 FAIL;
- attempt-6 corpus 202/202, framed digest
  `1ce18c9e9fc3b5aa820adcb1aad649c635fcb2ed64a7e644d4d5bba6aeb5d91f`;
- 13 docs tests, OK;
- 1,431 repository tests, four optional skips;
- 60 fixtures;
- Ruff, Bandit, scanner regressions, governance, literal task-state, generated
  reviewer-checklist absence, and diff checks clean;
- normalized T001–T140 graph hash
  `86e71d42acbeadc7759d70b64585dec5ae40798a1befc791a777821430a56a2a`;
- whole-slice scan CLEAN from `fc60858a3810e2f53d9574cce1eb9589bd19b55b`
  to the target over 69 files, 10,249 additions, four matchers.

## Nonblocking nits

1. The Phase 25 handoff section preserves a mid-T139 literal-state receipt
   (`checked=132`, T139 open). The frozen reviewed object reproduces
   `checked=133`, with only T103/T140 open. The receipt-only successor annotates
   this expected freeze-order transition.
2. Plan prose names T083–T138 as the implementation-enforcement range while
   T139/T140 are process gates. This is descriptive and accurate by role.
3. The slice-namespaced task checker lives in shared `scripts/`; its explicit
   operator-supplied task path and clean governance result keep the ownership
   boundary visible.
