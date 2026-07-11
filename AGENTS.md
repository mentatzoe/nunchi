# Nunchi Agent Guidelines

Nunchi is a portable pre-attention gate for turn-aware participants in shared
conversation.

## Authority order

Read these before substantive work, in this order:

1. Zoe-selected Aleph Vault Nunchi decisions and technical design, selected in
   PR 67 (`bdd1ebb`) and contract-clarified in PR 68 (`c834e8c`).
2. `.specify/memory/constitution.md`.
3. This file and `CLAUDE.md` for runtime-specific execution guidance.
4. `specs/001-nunchi-v2-program/` and the one owned slice being worked.
5. Ordinary-path source, schemas, tests, evals, evidence, and docs for what is
   currently implemented and proven.

Higher authority wins. SpecKit artifacts organize work; they do not redefine
the selected design or current implementation truth.

## Current goal boundary

Goal 1 rebuilds governance and the execution spine. It may relocate existing
assets and add governance tooling, but it MUST NOT implement V2 product
behavior. Goal 2 is commissioned separately for implementation, atomic cutover,
integration, and parity evidence.

The repository currently implements V1 (`PASS / ACK / ASK / SPEAK`). The
selected, unimplemented V2 target uses `SUPPRESS / WAKE / DEFER` plus separate
operational `ERROR`, followed by a normal participant act-or-silence turn.
Never describe the target as current behavior.

## SpecKit execution spine

- Required CLI version: exactly `0.12.11`.
- Installed integrations: Codex and Claude; Codex is the default.
- Planning-only workflow: `specify workflow info nunchi-plan`.
- Full slice workflow: `specify workflow info speckit`; its explicit Goal 2
  authorization gate is mandatory before `implement`.
- Each slice has one accountable owner lane. Reviewers do not silently co-own.
- Use isolated worktrees for non-trivial slice implementation.

SpecKit-managed paths are control plane only:

- `.specify/`
- `specs/`
- `.agents/skills/speckit-*`
- `.claude/skills/speckit-*`

They may contain tool configuration, constitution, specs, plans, planning
research, requirement-quality checklists, tasks, owners, dependencies, and
workflow state. They may never contain product source, machine-readable
contracts/schemas, executable tests, fixtures, eval runners/corpora, evidence,
runtime assets, or product documentation.

Product artifacts belong under `src/`, `schemas/`, `tests/`, `evals/`,
`evidence/`, `integrations/`, `scripts/`, and `docs/`. Build, test, eval, docs,
packaging, release, and runtime commands must not depend on managed paths.

The standard SpecKit plan command normally proposes `data-model.md`,
`contracts/`, and `quickstart.md` inside a feature directory. Nunchi's
constitution forbids those outputs. Record interface and validation planning in
`plan.md`; create actual schemas/contracts under `schemas/` and runnable guides
under `docs/` only during an authorized implementation goal.

## Documentation freshness

Documentation is a blocking part of every implementation slice. Each spec,
plan, and task graph must explicitly review `README.md` and every ordinary-path
document affected by behavior, interfaces, configuration/defaults,
installation, entry points, supported surfaces, security posture, evidence
grade, limitations, version/current state, diagrams, examples, or commands.

Use exactly one disposition per reviewed surface:

- `UPDATE`: land and validate the affected docs with the candidate.
- `NO_IMPACT`: list exact reviewed paths and concrete rationale in ordinary
  handoff evidence.
- `HANDOFF`: for shared/integrator-owned docs only, provide the exact required
  claim delta and accepting owner. It is not a no-impact finding.

Name exact affected files; a generic directory or wildcard is not a review when
the paths are already known. Goal 2 task checkboxes remain dormant until Zoe's
separately granted objective is recorded at
`evidence/governance/v2-goal-2-authorization.md`; that record documents
authority and never grants it.

Intermediate V2 slices update their owned component docs and hand global
current-state wording to `v2-integrator`; they must not claim partial V2 as
current. Slice `110` must update `README.md` and affected cross-surface docs as
part of the atomic cutover. No implementation may converge or hand off until
the documentation-freshness gate passes for the exact candidate.

## Product invariants

- Only a participant-shaped model may make a social suppression judgment.
- Deterministic code handles transport-proven non-events, never conversational
  meaning.
- Uncertainty wakes or defers.
- Trusted preattention bypass wakes directly with no fabricated model result.
- Exact self binding is separate from loose names and aliases.
- Context is bounded, structured, coverage-honest, and optionally expandable.
- Continuation authority is host-only; the classifier sees no opaque handle,
  binding, cursor, expiry, or fetch secret.
- Observation, attention, participant-host, and transport receipts are
  immutable, request-correlated, and singly attested by their owner.
- There is no social handled/open ledger, obligation queue, or inferred roster.
- Preattention is judged once; no send-time social reclassification.
- A woken participant contributes directly or sends nothing; no meta-answer.
- V2 must cut over atomically across all in-tree consumers and prove parity.

## Commands

```sh
python3 scripts/check_governance.py --check-cli
python3 -m unittest
python3 -m evals.verdict_suite.runner --list
```

The test suite is stdlib `unittest`, offline, and deterministic unless a command
explicitly performs a live provider evaluation. Current package/runtime details
remain in `CLAUDE.md`, `README.md`, and `docs/`.

## Definition of done

A slice is ready only when its spec, plan, tasks, owner, dependencies,
interfaces, integration strategy, acceptance scenes, and evidence requirements
agree; analysis has no CRITICAL/HIGH findings; and the governance boundary
passes. Product completion additionally requires ordinary-path implementation,
tests, evidence, installed-runtime provenance, accepted README/docs
dispositions and validation, and integrator handoff.
