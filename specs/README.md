# Nunchi SpecKit Control Plane

This tree is disposable planning state. It contains the V2 umbrella program and
independently owned implementation slices; it contains no product source,
schemas, tests, evaluations, fixtures, evidence, runtime assets, or product
documentation.

## Program

- `001-nunchi-v2-program` — umbrella authority, dependency graph, interface
  registry, common scenes, integration order, and final success contract;
  owner lane `v2-program-owner`.

The 2026-07-11 governance-reset baseline recorded the program as `READY`,
implementation authority as `NOT_GRANTED`, and every implementation slice as
`PLANNED` with its task graph dormant. Program readiness meant the control
plane was coherent; it was not product implementation permission. These values
are a dated snapshot, not a live registry.

## Slices

| Slice | State at reset baseline | Owner lane | Dependencies |
|---|---|---|---|
| `010-v2-contract` | `PLANNED` | `v2-contract-owner` | none |
| `020-v2-observation` | `PLANNED` | `v2-observation-owner` | `010` |
| `030-v2-core-attention` | `PLANNED` | `v2-core-owner` | `010` |
| `040-v2-participant-wake` | `PLANNED` | `v2-wake-owner` | `010`, `020`, `030` |
| `050-v2-discord-transport` | `PLANNED` | `v2-transport-owner` | `010`, `020` |
| `060-v2-hermes` | `PLANNED` | `v2-hermes-owner` | `010`, `020`, `030`, `040` |
| `070-v2-claude-code` | `PLANNED` | `v2-claude-owner` | `010`, `020`, `030`, `040`, `050` |
| `080-v2-codex` | `PLANNED` | `v2-codex-owner` | `010`, `020`, `030`, `040`, `050` |
| `090-v2-channel-adapters` | `PLANNED` | `v2-adapters-owner` | `010`, `020`, `030`, `040` |
| `100-v2-security-provenance` | `PLANNED` | `v2-security-owner` | `010`–`090` |
| `110-v2-parity-cutover` | `PLANNED` | `v2-integrator` | `010`–`100` |

This table is the reset baseline and is not updated as slices transition.
Resolve live program progress from `001-nunchi-v2-program/`, implementation
authority from the exact record at
`evidence/governance/v2-implementation-authorization.md`, and a slice's live
state and occupant from that bound slice's declarations plus immutable
activation/acceptance records and append-only candidate/handoff evidence.

The plans are not implementation authorization. Zoe's external grant is
documented at `evidence/governance/v2-implementation-authorization.md` and must
enumerate exactly all eleven slices `010` through `110`; a partial or
extra-scope record is invalid for every slice. The record documents but does
not grant authority. To plan or deliver one existing slice, use the bound
workflow runner, which verifies the pinned CLI, preflights the slice, sets its
process environment, resolves the integration, and pins those facts with the
slice input and workflow digest:

```sh
python3 scripts/run_slice_workflow.py run nunchi-plan \
  specs/030-v2-core-attention
# Or, after program authorization and slice readiness:
python3 scripts/run_slice_workflow.py run speckit \
  specs/030-v2-core-attention
python3 scripts/run_slice_workflow.py resume <run-id>
```

Replace the example with the bound existing slice. Both workflows use only that
slice and neither creates or replaces a feature. The runner's read-only
preflight allowlists the existing slices `010`–`110`, verifies their required
planning artifacts and exact resolver result, and does not modify
`.specify/feature.json`. Resume is only for a paused run with an unchanged task
graph. Convergence-added tasks or a rejected completed handoff require a new
bound delivery run for the same `ACTIVE` slice.
Implementation begins only after both the complete
program-authority gate and that slice's independent `READY` gate pass. Each
dependent owner separately accepts its required upstream handoffs before that
gate, recording ordered exact commits and matching per-consumer acceptance
references. Slice `110` requires every upstream slice to be `ACCEPTED`. At slice
level, `v2-integrator` accepts slices `010`–`100`; Zoe accepts slice `110`.

Zoe, or an assigner named in a durable Zoe delegation, assigns the program
owner and slice occupants. Declarations use `<participant identity>` —
`evidence/governance/assignments/<record>.md`; that non-symlink record contains
exactly one `Assignee`, `Lane`, `Assigned by`, ISO `Assigned on`, and durable
`Authority reference`. A non-Zoe assigner also requires `Delegated by: Zoe` and
a durable `Delegation reference`. Assignment may precede
implementation authority for planning but does not grant it or establish
`READY`. There is no central assignment registry.

Only slice `110` integrates accepted handoffs. After its workflow reaches
`HANDOFF_READY`, the integrator records Zoe's exact-candidate decision for the
slice and, on acceptance, the program owner records only the program cutover
copy. One atomic merge remains `CUTOVER_ACCEPTED` and verification-pending;
exact-main verification and final docs validation in a docs/evidence-only
follow-up establish `CUTOVER_VERIFIED`. Release and promotion remain separate.

Slice state follows `PLANNED -> READY -> ACTIVE -> CONVERGED -> HANDOFF_READY
-> ACCEPTED`. There is no central mutable status registry: state is derived
from the declared control-plane state and immutable ordinary-path activation,
acceptance, and append-only candidate/handoff evidence. A rejection appends its
decision, returns the same owner to `ACTIVE`, and preserves the prior attempt.
These governance records never become runtime
or conversational state, classifier input, a social ledger, or participant
memory. Ordinary repository truth remains under `src/`, `schemas/`, `tests/`,
`evals/`, `evidence/`, `integrations/`, `scripts/`, and `docs/`.
