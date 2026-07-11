# Nunchi Claude Code Guidelines

Follow `AGENTS.md` and `.specify/memory/constitution.md`. The condensed rules
below are specific to Claude Code execution; they do not change the authority
order or product design.

## Grounding sequence

1. Read the selected Aleph Vault Nunchi technical design and decisions (PR 67
   at `bdd1ebb`, contract-clarified by PR 68 at `c834e8c`).
2. Read `.specify/memory/constitution.md`.
3. Read `AGENTS.md` and this file.
4. Read `specs/001-nunchi-v2-program/` and only the slice assigned to your owner
   lane.
5. Inspect ordinary-path implementation and evidence before making a current
   product claim.

Goal 1 is governance/planning only. Do not implement V2 until Zoe separately
sets Goal 2 and the full workflow's authorization gate is approved.

For V2 planning, preserve the explicit no-model preattention bypass, keep
continuation authority out of classifier input, and treat observation,
attention, participant-host, and transport receipts as immutable singly
attested stages. These are lifecycle boundaries, not social state.

## Runtime and tests

- Python 3.11+, standard-library runtime core; do not add a runtime dependency
  without an authorized slice and constitution check.
- Tests use stdlib `unittest`: `python3 -m unittest`.
- Governance check: `python3 scripts/check_governance.py --check-cli`.
- Verdict corpus smoke: `python3 -m evals.verdict_suite.runner --list`.
- Live classifier calls require `NUNCHI_CLASSIFIER_MODEL` and
  `OPENROUTER_API_KEY` or `NUNCHI_CLASSIFIER_API_KEY`; offline tests inject
  `NUNCHI_CLASSIFIER_TEST_RESULT` via `tests/provider_helpers.py`.
- CLI smoke from source:
  `PYTHONPATH=src python3 -m nunchi admit < tests/fixtures/speak.json`.

## SpecKit

SpecKit CLI is pinned to `0.12.11`; Claude and Codex integrations are installed,
with Codex as repository default. Claude uses `.claude/skills/speckit-*`.

Use `nunchi-plan` through analysis for planning. The customized `speckit`
workflow includes clarify, checklist, analysis, an explicit Goal 2 authorization
gate, implementation, convergence, a documentation-freshness gate, and
integration handoff.

SpecKit-managed directories are disposable control plane. Never place product
code, schemas/contracts, tests, fixtures, evals, evidence, runtime assets, or
product docs in `.specify/`, `specs/`, or a SpecKit skill directory. The standard
plan skill's `data-model.md`, `contracts/`, and `quickstart.md` outputs are
constitutionally disabled for Nunchi; summarize those needs in `plan.md` and
target ordinary repository paths.

## Ownership and handoff

Work only in the assigned slice and an isolated worktree for non-trivial
implementation. Do not change an upstream contract owned by another lane; file
or hand back the needed change. Handoff must include the exact commit, commands
and results, interface versions, ordinary evidence paths, runtime provenance,
documentation dispositions and validation, and known limitations. Every
implementation must review `README.md` plus affected ordinary docs using
`UPDATE`, evidence-backed `NO_IMPACT`, or an exact integrator-owned `HANDOFF`;
bare no-impact claims and generic directory scope block convergence. Do not
check a Goal 2 task until Zoe's external authorization is recorded at
`evidence/governance/v2-goal-2-authorization.md`; the record documents rather
than grants that authority.

When high reasoning is required, pass `--effort xhigh`. A green unit suite does
not establish social correctness; use the slice's replay and live acceptance
scenes before making parity or readiness claims.
