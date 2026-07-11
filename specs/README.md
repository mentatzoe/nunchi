# Nunchi SpecKit Control Plane

This tree is disposable planning state. It contains the V2 umbrella program and
independently owned implementation slices; it contains no product source,
schemas, tests, evaluations, fixtures, evidence, runtime assets, or product
documentation.

## Program

- `001-nunchi-v2-program` — umbrella authority, dependency graph, interface
  registry, common scenes, integration order, and final success contract;
  owner lane `v2-program-owner`.

## Slices

| Slice | Owner lane | Dependencies |
|---|---|---|
| `010-v2-contract` | `v2-contract-owner` | none |
| `020-v2-observation` | `v2-observation-owner` | `010` |
| `030-v2-core-attention` | `v2-core-owner` | `010` |
| `040-v2-participant-wake` | `v2-wake-owner` | `010`, `020`, `030` |
| `050-v2-discord-transport` | `v2-transport-owner` | `010`, `020` |
| `060-v2-hermes` | `v2-hermes-owner` | `010`, `020`, `030`, `040` |
| `070-v2-claude-code` | `v2-claude-owner` | `010`, `020`, `030`, `040`, `050` |
| `080-v2-codex` | `v2-codex-owner` | `010`, `020`, `030`, `040`, `050` |
| `090-v2-channel-adapters` | `v2-adapters-owner` | `010`, `020`, `030`, `040` |
| `100-v2-security-provenance` | `v2-security-owner` | `010`–`090` |
| `110-v2-parity-cutover` | `v2-integrator` | `010`–`100` |

The plans are not implementation authorization. Goal 2 begins only when Zoe
sets it explicitly. Ordinary repository truth remains under `src/`, `schemas/`,
`tests/`, `evals/`, `evidence/`, `integrations/`, `scripts/`, and `docs/`.
