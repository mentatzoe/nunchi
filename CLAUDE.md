# Nunchi Claude Code Guidelines

Follow `AGENTS.md` and `.specify/memory/constitution.md`. The condensed rules
below are specific to Claude Code execution; they do not change the authority
order or product design.

## Grounding sequence

1. Read `docs/architecture/v2-selected-design.md` and
   `docs/contracts/nunchi-v2.md`. These repository-owned references preserve
   the Zoe-selected Aleph Vault decisions from PR 67 (`bdd1ebb`) and PR 68
   (`c834e8c`); a Vault checkout is not required.
2. Read `.specify/memory/constitution.md`.
3. Read `AGENTS.md` and this file.
4. Read `specs/001-nunchi-v2-program/` and only the slice assigned to your owner
   lane.
5. Inspect ordinary-path implementation and evidence before making a current
   product claim.

The 2026-07-11 governance-reset baseline recorded the V2 program as `READY`,
implementation authority as `NOT_GRANTED`, and every slice as `PLANNED` and
dormant. Treat those values as a dated snapshot, not a live registry. Resolve
live program progress from `specs/001-nunchi-v2-program/`, authority from the
exact record at `evidence/governance/v2-implementation-authorization.md`, and
the bound slice's state and occupant from its declarations plus immutable
activation/acceptance records and append-only candidate/handoff attempt
streams. The planning-baseline amendment distinguishes `READY` from
`PLANNING`. Do not implement V2
unless the external grant recorded at
`evidence/governance/v2-implementation-authorization.md` enumerates exactly all
eleven slices and the bound slice independently satisfies its `READY` gate. A
partial authorization record is invalid for every slice. V1 remains the current
product until the atomic V2 merge is verified on `main` and program state is
`CUTOVER_VERIFIED`.

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

Both `nunchi-plan` and `speckit` operate on one existing slice. Invoke either
only through `scripts/run_slice_workflow.py`. It allowlists and preflights the
slice, sets `SPECIFY_FEATURE_DIRECTORY` inside the workflow process, pins the
slice input, integration manifest and installed skill bytes, workflow digest,
and initial task graph, and does not
modify `.specify/feature.json`.
`nunchi-plan` plans that bound slice through analysis and never creates or
replaces a feature. The customized `speckit` workflow continues with separate
implementation-authority and slice-readiness gates, implementation,
convergence, a documentation-freshness gate, and owner handoff. Only slice
`110` performs integration, and its atomic candidate still requires Zoe's
explicit `CUTOVER_ACCEPTED` decision before cutover.

Run the selected workflow with the exact bound directory, for example:

```sh
python3 scripts/run_slice_workflow.py run nunchi-plan \
  specs/030-v2-core-attention
python3 scripts/run_slice_workflow.py run speckit \
  specs/030-v2-core-attention
python3 scripts/run_slice_workflow.py resume <run-id>
```

Append `--integration claude` or `--integration codex` to an initial `run` when
the default is not appropriate. The runner pins the choice, manifest, and exact
installed skill bytes for every resume.

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
check an implementation task until the external grant is documented at
`evidence/governance/v2-implementation-authorization.md`, enumerates exactly
all slices `010` through `110`, and the bound slice is `READY`; the record
documents rather than grants that authority. A partial record authorizes no
slice.

Only Zoe, or an assigner named in a durable Zoe delegation, may assign the
`v2-program-owner` or a slice owner-lane occupant. Use `<participant identity>`
— `evidence/governance/assignments/<record>.md` in the declaration. That
non-symlink record must contain exactly one `Assignee`, `Lane`, `Assigned by`,
ISO `Assigned on`, and durable `Authority reference`; a non-Zoe assigner also
requires `Delegated by: Zoe` and a durable `Delegation reference`. Chat or
session memory alone is invalid. Assignment may
precede authority for planning, but it never grants implementation authority or
readiness. Record it in the program or bound slice and activation evidence,
never in a central assignment registry.

Slice state follows `PLANNED -> READY -> ACTIVE -> CONVERGED -> HANDOFF_READY
-> ACCEPTED`. It is derived from the slice declaration plus immutable
ordinary-path activation/acceptance records and append-only candidate/handoff
attempt streams—not a central mutable registry. Never expose this governance
lifecycle as runtime or conversational state, classifier input, a participant
registry, a social ledger, or memory.
At slice level, `v2-integrator` accepts slices `010`–`100`, while Zoe accepts
slice `110`. Each dependent owner must also accept its required upstream
handoffs independently before its own slice becomes `READY`; that dependency
decision is not the upstream slice's terminal acceptance.

Activation evidence maps each dependency to its exact full commit and matching
repo-relative per-consumer acceptance evidence; slice `110` requires every
upstream slice to be `ACCEPTED`. On handoff rejection, append `REJECTED` with
the exact candidate and durable decision, return the same slice owner to
`ACTIVE`, and start a new bound `run speckit` for the same slice; never resume
the completed delivery run. If convergence appends tasks, retain activation,
remain `ACTIVE`, and likewise start a new bound run. A paused post-convergence
gate may resume its run only for fixes that leave the task graph unchanged.
Append the later candidate/handoff attempts and never delete or rewrite an
earlier attempt.

After slice `110` reaches `HANDOFF_READY`, the slice workflow is complete and
the program tail begins. Zoe's durable decision for the exact candidate is
copied into `evidence/v2/parity/slice-acceptance.md` by the assigned integrator;
on acceptance, the assigned program owner copies it only into
`evidence/v2/parity/cutover-acceptance.md`. This establishes slice `ACCEPTED`
and program `CUTOVER_ACCEPTED`. The integrator may then perform the one atomic
merge, whose docs must still say verification and final current-state wording
are pending. Exact-main verification plus final documentation validation land
together in a docs/evidence-only follow-up at
`evidence/v2/parity/post-merge-verification.md`; only then is
`CUTOVER_VERIFIED` established. Release and promotion remain separate.

When high reasoning is required, pass `--effort xhigh`. A green unit suite does
not establish social correctness; use the slice's replay and live acceptance
scenes before making parity or readiness claims.
