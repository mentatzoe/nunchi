# Delivering Nunchi V2

This is the implementation entrypoint. The target is the product described in
`v2-completion-goal.md`, not a collection of completed planning artifacts.

## Current truth

The runnable repository is still V1. V2 is incomplete until one reviewed
candidate satisfies the completion goal and cuts over atomically. Historical
branches, packets, approvals, and evidence may be reused only after their code
and behavior pass against the current upstream implementation.

Use four plain status terms:

- **Missing**: required product behavior is absent.
- **Implemented, unverified**: code exists but required tests or runtime proof
  have not passed.
- **Verified**: the exact code passed its required source, deterministic,
  installed-runtime, and live checks.
- **Integrated**: the verified code is present on `integration/v2`.

Nothing else means done.

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
5. Obtain an exact-head non-author review proportionate to risk. Source
   approval does not claim installed or live success.
6. Merge only after required checks and review pass. Then unblock direct
   consumers.

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
