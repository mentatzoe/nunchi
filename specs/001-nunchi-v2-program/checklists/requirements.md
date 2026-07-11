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
- [x] Separates Goal 1 planning from independently authorized Goal 2 implementation.
- [x] Excludes V1 bridges, mixed-version state, social ledgers/registries, deterministic social heuristics, and send-time social reclassification.
- [x] Distinguishes trusted preattention bypass from model WAKE/DEFER and operational ERROR without fabricating a classifier result.
- [x] Requires immutable singly attested observation, attention, participant-host, and transport receipt stages.
- [x] Keeps continuation authority host-only while allowing factual coverage and expansion-availability signals in classifier input.
- [x] Assigns live canary execution to dependent surface/integration owners without making the core handoff cyclic.
- [x] Requires final accepted atomic integration to merge to main and be reverified there, while keeping release/promotion separate.

## Verifiability

- [x] Every functional requirement is testable by artifact inspection or future ordinary-path evidence.
- [x] Success criteria are measurable and technology-independent where practical.
- [x] The core/CLI slice defines exact stdout, stderr, and exit behavior for every input and result class.
- [x] Aggregate evidence records carry canonical scene IDs and have explicit scene-to-record manifests.
- [x] Baseline and reinitialization-safety criteria are explicit.
- [x] No `[NEEDS CLARIFICATION]`, owner placeholder, unresolved dependency, or undefined final sink remains.

## Control-Plane Boundary

- [x] Product implementation targets only `src/` or `integrations/`.
- [x] Product schemas target only `schemas/`.
- [x] Tests, evals, evidence, and docs target ordinary repository paths.
- [x] The program explicitly forbids product workflow dependencies on managed paths.

## Notes

- Checklist complete. This validates requirement quality, not Goal 2 product
  completion or social correctness.
