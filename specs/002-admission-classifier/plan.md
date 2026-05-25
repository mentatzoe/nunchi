# Implementation Plan: Admission Classifier Completion

**Branch**: `002-admission-classifier` | **Date**: 2026-05-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-admission-classifier/spec.md`

**Note**: This template was seeded by the `/speckit-plan` workflow and filled for the TUR-11 SpecKit redo. The prior 001 CLI/core work and TUR-12 adversarial observations are evidence inputs, not production branches to continue.

## Summary

Complete the next vertical TurnAware slice by replacing the current substring-only admission heuristic with a configurable provider-backed classifier boundary while preserving the existing admission-only CLI/core contract. The product/default classifier path is the actual admission classifier requested for TurnAware; Zoe explicitly rejected a selectable `deterministic` classifier path on 2026-05-25. Product results must expose classifier/provider/model identity in audit output, reject the known false ACK/PASS cases through deterministic provider-fixture evidence, keep legitimate PASS reachable only with corroborating inspected context, and remain verified through the public CLI and callable core.

## Technical Context

**Language/Version**: Python 3.11+ using the standard library

**Primary Dependencies**: Standard-library OpenAI-compatible provider client; product/default classifier path uses configured provider/model credentials. Offline CI evidence uses a deterministic fixture provider transport, not a public classifier path. Absence/unavailability must fail clearly with no silent local/deterministic fallback.

**Storage**: N/A; per-request evaluation with no persistence

**Testing**: `python -m unittest` plus public install/CLI smoke commands from quickstart

**Target Platform**: Local POSIX-like developer shell and CI runner with Python 3.11+

**Project Type**: Library plus CLI

**Performance Goals**: Deterministic provider-fixture set evaluates in under 2 seconds from process start on a typical developer machine; no network dependency for CI evidence

**Constraints**: Admission-only; no reply composition; verdict vocabulary remains PASS/ACK/ASK/SPEAK; `context_checked` only names inspected supplied material; invalid classifier/provider config fails clearly with no silent fallback; no selectable deterministic classifier; adapters, Discord/cc-connect integration, broad benchmarks, launch claims, and marketing copy are excluded

**Scale/Scope**: Single admission request per CLI invocation; product classifier covers supplied conversation/context envelopes, and deterministic provider-fixture corpus covers known false ACK/PASS cases plus representative PASS/ACK/ASK/SPEAK cases

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Admission, Not Composition | PASS | Classifier selection changes admission judgement only; reply prose remains forbidden. |
| II. Hard-Stop PASS Is Load-Bearing | PASS | PASS remains terminal for ordinary visible participation and must be backed by inspected completion evidence. |
| III. CLI-First, Modular Core | PASS | Existing `turnaware admit` and `src/turnaware/core.py` remain the shared boundary; classifier selection must be reachable from both. |
| IV. Vertical, Independently Testable Slices | PASS | Slice is end-to-end: input envelope + classifier config -> verdict + audit evidence through CLI/core. |
| V. Test-First Contract and Fixture Discipline | PASS | Plan requires deterministic provider fixtures for all verdicts, known false cases, invalid config, and context truth before implementation is accepted. |
| VI. Adapter Tier Honesty and Consumer Boundaries | PASS | No downstream adapter implementation or adapter launch claim is in scope. |
| VII. Context Truth and Room Inference | PASS | Classifier may reason over supplied context but `context_checked` must stay a subset of actually inspected trigger/context references. |
| VIII. Documentation Is Product | PASS | Quickstart evidence is limited to runnable CLI/core commands and public install checks. |

## Project Structure

### Documentation (this feature)

```text
specs/002-admission-classifier/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── admission-classifier.md
├── checklists/
│   ├── requirements.md
│   └── admission-classifier.md
└── tasks.md
```

### Source Code (repository root)

```text
pyproject.toml
README.md
src/
└── turnaware/
    ├── __init__.py
    ├── __main__.py
    ├── cli.py              # parse public classifier selection/config arguments
    ├── core.py             # callable evaluate boundary delegates to classifier registry
    ├── errors.py
    ├── models.py           # request/result models include classifier identity in result payload
    ├── schema.py           # validate request/result/config fields
    └── classifiers.py      # product classifier registry and provider boundary

tests/
├── fixtures/
│   ├── pass.json
│   ├── ack.json
│   ├── ask.json
│   ├── speak.json
│   ├── false_ack_comment_back.json
│   ├── false_pass_contradicted_done.json
│   └── invalid_classifier.json
├── test_cli.py
├── test_core.py
├── test_schema.py
└── test_classifiers.py
```

**Structure Decision**: Keep the existing single Python package. Add a small classifier module/registry instead of embedding selection logic in the CLI, so CLI and callable core remain contract-equivalent and future adapters can call the same evaluation boundary.

## Phase 0: Research Summary

Research decisions are captured in [research.md](./research.md). Key decisions: the product classifier path is the only supported classifier path; deterministic offline evidence is provided through a provider fixture, not a selectable classifier; classifier/provider/model identity is first-class audit/result evidence; unsupported classifier/provider configuration is a validation/runtime failure rather than fallback; contradiction handling must inspect supplied context before PASS; public install verification remains part of done.

## Phase 1: Design Summary

Design artifacts are captured in [data-model.md](./data-model.md), [contracts/admission-classifier.md](./contracts/admission-classifier.md), and [quickstart.md](./quickstart.md). The design adds `classifier`/`classifier_config` inputs and `classifier` audit output while preserving verdicts, confidences, reasons, request IDs, and checked-context semantics.

## Constitution Check - Post-Design

| Principle | Status | Notes |
|-----------|--------|-------|
| Admission, Not Composition | PASS | Contract explicitly forbids reply/draft/message/content fields in successful results. |
| Hard-Stop PASS | PASS | PASS fixtures require corroborating inspected completion context and no visible reply content. |
| CLI-First, Modular Core | PASS | CLI and core both call the same classifier registry and produce contract-equivalent payloads. |
| Vertical Slice | PASS | Tasks can be ordered by host selection, adversarial verdict evidence, then CLI/core compatibility. |
| Test-First Contract | PASS | Red tests must cover false ACK/PASS and invalid classifier config before implementation. |
| Adapter Honesty | PASS | Quickstart and contract exclude Discord/cc-connect/adapters and launch claims. |
| Context Truth | PASS | Data model defines inspected context references and contradiction evidence requirements. |
| Documentation Is Product | PASS | Quickstart commands are explicit verification evidence, not speculative usage. |

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
