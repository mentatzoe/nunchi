# Specification Quality Checklist: Nunchi V2 Program

**Purpose**: Validate the umbrella specification before slice planning

**Created**: 2026-07-11

## Content Quality

- [x] Describes user and operator outcomes without embedding product implementation.
- [x] Distinguishes current V1 implementation truth from selected, unimplemented V2.
- [x] Uses social, human-shaped product language and avoids a mechanical social algorithm.
- [x] Contains no product schema, executable test, evaluation fixture, evidence, or product documentation.

## Requirement Completeness

- [x] Defines one umbrella and exactly eleven bounded slices.
- [x] Requires one stable accountable owner lane per slice.
- [x] Requires complete dependency and downstream-feed edges.
- [x] Requires named, versioned, singly owned interfaces.
- [x] Requires isolated integration strategy and explicit final handoff.
- [x] Requires common acceptance scenes and ordinary-path evidence.
- [x] Covers core, CLI, observation, participant wake, Discord transport, Hermes, Claude Code, Codex, and standalone adapters.
- [x] Covers blocking security/provenance and final parity/cutover ownership.
- [x] Separates program progress, external implementation authority, and independent slice progress.
- [x] Declares the dated 2026-07-11 reset baseline as program `READY`, authority `NOT_GRANTED`, and all slices `PLANNED` and dormant, while deriving live facts from declarations, immutable activation/acceptance evidence, and append-only candidate/handoff attempts.
- [x] Defines exact per-slice SpecKit binding, assigned participant/source, immutable activation evidence, dependencies, and readiness facts.
- [x] Requires the neutral authority record at `evidence/governance/v2-implementation-authorization.md` to enumerate every covered slice and document rather than grant Zoe's external authority.
- [x] Rejects a central mutable slice-state or assignment registry; lifecycle truth derives from slice declarations, immutable ordinary-path activation/acceptance records, and append-only candidate/handoff attempt streams.
- [x] Requires every dependent activation to map canonical IDs to ordered full SHAs and matching consumer-owned acceptance evidence, with `010` using `none` and slice `110` waiting for terminal acceptance of every upstream slice.
- [x] Excludes V1 bridges, mixed-version state, social ledgers/registries, deterministic social heuristics, and send-time social reclassification.
- [x] Distinguishes trusted preattention bypass from model WAKE/DEFER and operational ERROR without fabricating a classifier result.
- [x] Requires immutable singly attested observation, attention, participant-host, and transport receipt stages.
- [x] Keeps continuation authority host-only while allowing factual coverage and expansion-availability signals in classifier input.
- [x] Assigns live canary execution to dependent surface/integration owners without making the core handoff cyclic.
- [x] Requires final accepted atomic integration to merge to main and be reverified there, while keeping release/promotion separate.
- [x] Requires every implementation slice to review `README.md` and affected ordinary docs with exact `UPDATE`, evidence-backed `NO_IMPACT`, or owner-accepted `HANDOFF` dispositions before handoff.
- [x] Assigns global current-state documentation to slice `110` while requiring slices `010`–`100` to update owned guides and hand off exact claim deltas.
- [x] Rejects generic directory scope when known affected documentation files can be named.
- [x] Keeps every slice's implementation tasks dormant until the one valid complete authorization record enumerates exactly slices `010` through `110`, while still requiring the bound slice's independent readiness gate.
- [x] Makes slice `110` the only lane allowed to integrate and cut over the program.
- [x] Assigns slice-level acceptance of `010`–`100` to `v2-integrator` and `110` to Zoe, while requiring each dependent's own per-recipient upstream acceptance before readiness.
- [x] Names stable per-slice activation, candidate, handoff, and acceptance evidence plus slice `110` cutover-acceptance and post-merge-verification records without creating a central registry.
- [x] Requires rejection to append an attributable `REJECTED` decision, return the source slice to `ACTIVE`, preserve every attempt, and start a new bound run rather than resume the completed one; convergence-added tasks also require a new run, while only paused post-convergence fixes with an unchanged task graph resume.

## Verifiability

- [x] Every functional requirement is testable by artifact inspection or future ordinary-path evidence.
- [x] Success criteria are measurable and technology-independent where practical.
- [x] The core/CLI slice defines exact stdout, stderr, and exit behavior for every input and result class.
- [x] Aggregate evidence records carry canonical scene IDs and have explicit scene-to-record manifests.
- [x] Baseline and reinitialization-safety criteria are explicit.
- [x] Exact existing-slice selection is verifiable without relying on the umbrella default in `.specify/feature.json`.
- [x] No `[NEEDS CLARIFICATION]`, owner placeholder, unresolved dependency, or undefined final sink remains.
- [x] Documentation-freshness dispositions, validation, evidence, and review are measurable rather than generic polish tasks.

## Control-Plane Boundary

- [x] Product implementation targets only `src/` or `integrations/`.
- [x] Product schemas target only `schemas/`.
- [x] Tests, evals, evidence, and docs target ordinary repository paths.
- [x] The program explicitly forbids product workflow dependencies on managed paths.

## Notes

- Checklist complete. This validates requirement quality and the `READY`
  planning baseline, not implementation permission, slice readiness, V2 product
  completion, or social correctness.
