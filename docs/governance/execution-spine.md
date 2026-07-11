# Nunchi V2 execution spine

This document explains how Nunchi uses SpecKit after the V2 governance reset.
It is ordinary repository documentation; the executable planning state itself
lives in the disposable SpecKit control plane.

## Authority

The source-of-truth order is:

1. Zoe-selected Aleph Vault Nunchi decisions and technical design, selected in
   PR 67 at `bdd1ebb` and contract-clarified in PR 68 at `c834e8c`.
2. `.specify/memory/constitution.md`.
3. `AGENTS.md` and `CLAUDE.md`.
4. `specs/001-nunchi-v2-program/` and its independently owned slices.
5. Ordinary-path implementation, tests, evaluations, evidence, and product
   documentation for what is currently built and proven.

The Vault design owns the selected target. The repository's ordinary artifacts
own current implementation truth. SpecKit owns execution planning only.

## Two goals

- Goal 1 establishes this spine, relocates product assets, and plans the V2
  program. It does not implement V2 behavior.
- Goal 2 is separately commissioned. It implements the atomic V2 cutover and
  closes adapter/harness parity with committed evidence.

Creating or completing a task file is not Goal 2 authorization. After Zoe sets
Goal 2, the program owner records the external grant at
`evidence/governance/v2-goal-2-authorization.md` before checking any product
task. The record names the objective, authorizer, authority source, date, and
starting commit. It documents authorization; it cannot grant it. In the
record's absence, the governance checker rejects checked Goal 2 tasks; after a
valid record exists, it permits truthful task progress without relaxing any
workflow or acceptance gate. This is governance activation evidence, not a
conversation ledger, runtime permission registry, classifier input, or receipt.

Create the record only after the external goal is set, using this exact shape:

```markdown
# Nunchi V2 Goal 2 Authorization

**Program**: `001-nunchi-v2-program`

**Status**: AUTHORIZED

**Authorized by**: Zoe

**Authorized on**: YYYY-MM-DD

**Starting commit**: `<full-40-character-sha>`

**Objective**: <the separately commissioned Goal 2 objective>

**Authority source**: <the user-set goal/thread reference>

This record documents external authorization; it does not grant it.
```

## Pinned installation

The generated version pin is `.specify/init-options.json`:

```json
"speckit_version": "0.12.11"
```

`.specify/speckit-lock.json` additionally records that upstream tag
`v0.12.11` resolved to commit
`e802a7dd52a6eceba9403cbbf40e60dced043238`. Install the immutable commit:

```sh
uv tool install specify-cli --force \
  --from 'git+https://github.com/github/spec-kit.git@e802a7dd52a6eceba9403cbbf40e60dced043238'
specify --version
```

Initialize from a truly clean control plane:

```sh
specify init --here --force --integration codex --script sh
specify integration install claude --script sh
specify integration use codex
```

Codex and Claude are both installed; Codex is the default. The optional git and
agent-context extensions are intentionally absent so generated tooling does not
own commits, branches, `AGENTS.md`, or `CLAUDE.md`.

After an upstream refresh, restore or reapply Nunchi's constitution, customized
templates, workflows, and program artifacts from reviewable VCS changes before
planning. Do not preserve an old `.specify/` tree across a major reset.

## Control-plane boundary

Managed paths:

- `.specify/`
- `specs/`
- `.agents/skills/speckit-*`
- `.claude/skills/speckit-*`

Allowed content is limited to tool state, constitution, planning specs and
plans, planning research, requirement-quality checklists, task lists, ownership,
dependencies, and workflows. Product code, schemas/contracts, tests, fixtures,
evaluation runners/corpora, evidence, runtime assets, and product docs belong in
normal repository directories.

The standard SpecKit plan skill normally creates `data-model.md`, `contracts/`,
and `quickstart.md` under a feature. Nunchi forbids those outputs. Plans record
interface summaries and ordinary target paths; Goal 2 writes actual contracts to
`schemas/`, tests to `tests/`, evals to `evals/`, evidence to `evidence/`, and
documentation to `docs/`.

Run the mechanical boundary and version check with:

```sh
python3 scripts/check_governance.py --check-cli
```

With `--check-cli`, validation checks both `specify --version` and uv's PEP 610
installation metadata, including the exact resolved Git commit. A same-version
tool installed from another source or commit therefore fails the gate.

CI runs the same repository-boundary checks without requiring a globally
installed SpecKit CLI.

## Workflows

Inspect the planning-only workflow:

```sh
specify workflow info nunchi-plan
```

It runs specification, review, clarification, planning, plan review,
requirements checklist, task generation, analysis, and a planning-exit gate. It
has no implementation step.

Inspect the full slice workflow:

```sh
specify workflow info speckit
```

The full workflow adds an explicit Goal 2 authorization gate before
implementation, then convergence, documentation freshness, and integration
handoff. Reject the authorization gate unless Zoe has set Goal 2 and the slice
owner, dependencies, interfaces, acceptance scenes, and evidence requirements
are ready, and the external authorization record above is valid.

## Documentation freshness

Every implementation plan contains an exact documentation-impact matrix. It
must review `README.md` and each relevant ordinary-path document, then assign:

- `UPDATE` when the candidate must change and validate the document;
- `NO_IMPACT` only with exact reviewed paths and concrete rationale in ordinary
  handoff evidence; or
- `HANDOFF` only for shared or integrator-owned wording, with the exact claim
  delta and accepting owner.

Name each known affected file. Generic directory rows and wildcards are invalid
when the plan can identify the actual documents.

The workflow's `documentation-freshness` gate runs after convergence and before
integration handoff. It reviews the exact candidate rather than trusting a task
checkbox. Links, Mermaid, examples, commands, install/version claims, and
machine-checkable truthfulness tests are validated when relevant. Intermediate
V2 slices update their component docs and hand global current-state deltas to
`v2-integrator`; slice `110` updates `README.md` and affected cross-surface docs
as part of the atomic cutover.

`scripts/check_governance.py` mechanically enforces the required sections,
README disposition, owned-doc update, tasks, checklist coverage, and workflow
order. It cannot infer whether prose is socially or technically truthful; that
remains the exact-candidate review gate, strengthened by focused truthfulness
tests for claims that can be compared to code.

## Ownership model

The umbrella program defines stable owner lanes. A future runtime or human may
occupy a lane, but two lanes never co-own a slice and reviewers never acquire
ownership by editing it. A lane handoff is explicit and records the outgoing and
incoming owner.

Each slice plan names:

- one accountable owner lane;
- upstream and downstream slice IDs;
- consumed and produced interfaces;
- isolated worktree/branch and integration order;
- acceptance scenes;
- deterministic and live evidence targets;
- the exact handoff packet required by the final integrator.

The program structure and selected product lifecycle are also available as
renderable Mermaid component, class, sequence, state, and execution-wave views
in [`../architecture/v2-selected-design.md`](../architecture/v2-selected-design.md).

## Reinitialization safety

The control plane is safe to delete when:

1. `python3 scripts/check_governance.py` passes;
2. no build, test, eval, docs, package, release, or runtime command references a
   managed path;
3. `python3 -m unittest` and ordinary eval smoke commands still run with the
   managed paths absent.

In a disposable copy where the control plane has deliberately been removed,
run the product baseline as:

```sh
NUNCHI_SKIP_GOVERNANCE_TESTS=1 python3 -m unittest
python3 -m evals.verdict_suite.runner --list
```

Only `tests/test_governance.py` is skipped by that explicit environment flag;
the pre-reset 968 product tests still execute. Never set the flag in CI or in a
normal checkout: CI first runs `scripts/check_governance.py`, and the complete
suite exercises the governance tests when `.specify/` is present.

Deletion loses planning state, not product truth. VCS preserves reviewed
planning history, and a fresh pinned init recreates the tooling surface.
