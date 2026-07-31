# Delivering Nunchi V2

This is the implementation entrypoint. The target is the product described in
`v2-completion-goal.md`, not a collection of completed planning artifacts.

## Current truth

Shared-foundation commit
`014546d2ec685341106b177bcf2f6e52e758e0a9` is the verified runnable V2
implementation. Its source, clean installed artifact, deterministic and
adversarial suites, real-room matrix, and exact-head non-author review passed.
It is **Integrated** only when that exact commit is reachable from the fetched
`integration/v2` head. Hermes and Claude Code remained outside the foundation's
scope; their owners consume the integrated interface but must separately
implement and prove their platform behavior.

Per-surface status at the target `integration/v2` head after this reconciliation
lands:

| Surface | Status | What is outstanding |
|---|---|---|
| Codex | Verified, Integrated | — |
| Hermes | Landed, unverified | source-boundary closure (#42), supported-surface parity (#44), and installed/live acceptance (#38) |
| Claude Code | Landed, unverified | live real-room and supported-surface closure (#39, #43); the combined exact head must be reverified |

Neither unverified platform may be described as done, live, or parity-ready
until its open gates pass.

Use five plain status terms:

- **Missing**: required product behavior is absent.
- **Implemented, unverified**: code exists but required tests or runtime proof
  have not passed.
- **Landed, unverified**: the exact code is present on `integration/v2`, but
  named verification gaps remain open in GitHub issues.
- **Verified**: the exact code passed its required source, deterministic,
  installed-runtime, and live checks.
- **Integrated**: the verified code is present on `integration/v2`.

Landing lets the product be assembled and tested as a whole. It is not
verification, support, release readiness, or completion. Nothing except the
completion rule below means done.

Current deferred gates are tracked in:

- [Hermes live-platform acceptance](https://github.com/mentatzoe/nunchi/issues/38);
- [Claude Code live and release acceptance](https://github.com/mentatzoe/nunchi/issues/39);
- [first-class ACK behavior](https://github.com/mentatzoe/nunchi/issues/40);
- [Hermes source boundaries](https://github.com/mentatzoe/nunchi/issues/42);
- [Hermes supported-surface parity](https://github.com/mentatzoe/nunchi/issues/44);
- [Claude participant identity and supported surface](https://github.com/mentatzoe/nunchi/issues/43);
- [combined V2 final acceptance](https://github.com/mentatzoe/nunchi/issues/41).

## Build order

```text
010 contract
  ├─ 020 observation
  └─ 030 attention core
       └─ 040 participant host, scheduling, and action guard
020 ──└─ 050 shared Discord transport
010–050 ── 060 Hermes / 070 Claude Code / 080 Codex / 090 reference adapters
010–090 ── 100 security assurance
010–100 ── 110 parity, packaging, live mixed-agent proof, and atomic cutover
```

`060` and `070` are platform-owned. All other implementation and integration
is Codex-owned. Claude owns security assurance, with non-author review for
Claude-authored code and the assurance candidate. Zoe owns product scope and
the final completion decision.

## Platform-owner handoff

Hermes and Claude Code owners start only from a fetched `integration/v2` that
contains the verified foundation:

```sh
git fetch origin integration/v2
git merge-base --is-ancestor \
  014546d2ec685341106b177bcf2f6e52e758e0a9 \
  origin/integration/v2
```

A nonzero result means the dependency is not integrated and platform work must
not consume a side branch as a substitute. Once the ancestry check passes:

1. Read `docs/platform-v2.md` for the complete shared-owner and platform seam.
2. Read `docs/contracts/nunchi-v2.md` for the portable closed contracts.
3. Run the shared suite under `tests/v2/contract` and the runtime commands in
   the platform document before adding native cases.
4. Implement only the platform-owned wrapper and native identity, transport,
   cancellation, persistence, and live-proof obligations. Do not fork social
   judgment or authority semantics into the integration.

## Working agreement

1. Fetch current `integration/v2` and create one ordinary implementation branch
   and isolated worktree.
2. Select the earliest missing product behavior whose dependencies are already
   integrated. Use the relevant `spec.md` and `plan.md` as reference, then
   verify their claims against the selected design and current source.
3. Implement the behavior, tests, evaluation hooks, installation/runtime
   changes, and affected product documentation together.
4. Open a normal PR against `integration/v2`. Describe observable outcomes,
   exact verification, limitations, and any remaining missing behavior.
5. Obtain an exact-head non-author code review proportionate to risk. Source
   approval does not claim installed or live success.
6. Close blocking code findings and required CI. Zoe may authorize landing
   before live, operational, or final-candidate proof is complete only when
   every omitted gate has a named GitHub issue and the status remains
   **Landed, unverified**.
7. After each landing, verify the combined `integration/v2` head. Downstream
   work consumes that combined head, not the old side branch.

If an upstream change affects a consumed interface, configuration, or runtime
behavior, block its consumers. Reuse requires an exact comparison plus
independent review; otherwise rebuild and reverify them.

## Review standard

Review the code and reproduce the behavior. Look specifically for hidden V1
paths, fail-open errors, identity or authorization confusion, stale
conversation revival, cancellation races, output escape paths, cross-room or
profile leakage, dishonest coverage, and installed-byte drift.

Evidence is useful only when it records a passing observable outcome against
the exact candidate. A packet, label, test file, or report does not pass merely
by existing.

## Completion

The project is complete only when every end condition in
`v2-completion-goal.md` is true for one frozen, installable candidate and Zoe
accepts that exact result. Until then, report what is missing without lifecycle
euphemisms.
