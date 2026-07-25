# Nunchi contributor guidance

Nunchi is a portable pre-attention gate for turn-aware participants in shared
conversation. The objective is a coherent, secure, installable V2 product—not
completion of a planning process.

## Read first

1. `docs/v2-completion-goal.md` for the product outcome and end conditions.
2. `docs/architecture/v2-selected-design.md` for the selected design.
3. `docs/contracts/nunchi-v2.md` for the portable contract.
4. `docs/v2-delivery.md` for current ownership, dependency order, and delivery.
5. The relevant `specs/<slice>/spec.md` and `plan.md` as detailed reference.
6. Ordinary source, schemas, tests, evaluations, evidence, and installed
   runtimes for what actually exists and works.

The repository-owned design preserves Zoe's decisions from Aleph Vault PR 67
(`bdd1ebb`) and PR 68 (`c834e8c`); no Vault checkout or conversation history is
required. If documents disagree, the completion goal and selected design win.
Code and reproducible behavior determine implementation truth.

## Delivery rules

- Start V2 work from a clean checkout of current `integration/v2`, normally in
  an isolated worktree and ordinary implementation branch.
- Work on the earliest missing dependency. Do not start or reuse downstream or
  platform work until all required upstream behavior is implemented, tested,
  reviewed, and present on `integration/v2`.
- A changed upstream interface invalidates affected downstream work unless an
  exact comparison and independent review prove the consumed behavior and
  bytes unchanged.
- Implement product code, tests, evaluations, installation, and documentation
  in ordinary repository paths. Use normal commits and pull requests.
- Plans, labels, packets, reviews, documents, and evidence do not substitute
  for working behavior. Do not manufacture progress with governance work.
- A stale assignment, previous session owner, missing process artifact, pending
  review, or unfinished delegated task is not by itself a blocker. Resolve,
  reassign, replace, review, or integrate it as part of delivery. If one path
  is externally blocked, continue other unblocked product work. Stop only when
  no safe in-scope work remains because of a concrete external dependency;
  state that dependency and the remaining work plainly.
- Do not narrow supported behavior, redefine completion, or exclude a required
  surface without Zoe's explicit product decision. Ask Zoe only when a choice
  materially changes product behavior, supported surfaces, security
  boundaries, or requires an irreversible external action.
- “Unaccepted implementation” means unfinished. Say `missing`, `implemented
  but unverified`, `verified`, or `integrated` in status reports.
- Source review, installed-runtime verification, live evaluation, integration,
  and release are distinct claims. State exactly which one has passed.
- Preserve user changes and avoid destructive operations outside the exact
  requested scope.

## Ownership

Stable product identities survive session turnover:

| Work | Owner |
|---|---|
| Contract, observation, attention core, participant host, shared transport, Codex, reference adapters, integration, packaging, and product docs | Codex |
| Hermes integration | Aleph |
| Claude Code integration | Claude |
| Security assurance | Claude, with non-author review of Claude-authored code and the assurance candidate |
| Product scope and final completion decision | Zoe |

Platform owners receive a stable shared interface only after its upstream
implementation is integrated. The integrator remains accountable for the whole
product and may reject or replace inherited work.

## Product invariants

- Only the exact participant's delegated model may make a social suppression
  judgment.
- Deterministic code handles transport-proven non-events, lifecycle, and
  authority—not conversational meaning.
- Uncertainty wakes or defers.
- Trusted preattention bypass wakes directly without a fabricated model result.
- Exact self binding is separate from names, aliases, and roles.
- Context is bounded, structured, coverage-honest, and optionally expandable;
  continuation authority remains host-only.
- Observation, attention, participant-host, and transport receipts are
  immutable, request-correlated, and written only by their owning stage.
- There is no social handled/open ledger, obligation queue, inferred roster, or
  send-time social reclassification.
- A woken participant contributes directly or sends nothing.
- Privileged effects require current, provenance-bound authorization for the
  exact action immediately before dispatch.
- V2 cuts over atomically across every required in-tree surface; no executable
  V1 compatibility path remains.

## Verification

Use the smallest relevant tests while developing, then run:

```sh
python3 -m unittest
python3 -m evals.verdict_suite.runner --list
```

Deterministic tests are offline. Live provider and platform evaluations are
explicit, attributable runs. Green tests alone do not prove installed or live
behavior; the completion goal defines the final proof.
