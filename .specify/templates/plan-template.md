# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]

**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

**Program**: `[umbrella program directory]`

**Accountable owner lane**: `[exactly one owner lane]`

**Goal authorization**: `[Goal 1 planning only | Goal 2 explicitly authorized]`

**Upstream dependencies**: `[slice ids or none]`

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]

**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]

**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]

**Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]

**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]

**Project Type**: [e.g., library/cli/web-service/mobile-app/compiler/desktop-app or NEEDS CLARIFICATION]

**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]

**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]

**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

[Gates determined based on constitution file]

The check MUST include the SpecKit control-plane boundary, single-owner rule,
Goal 1/Goal 2 boundary, ordinary-path artifact locations, and parity/evidence
obligations. An unexplained failure stops planning.

## Slice Interfaces

### Consumes

- `[interface name/version]` from `[owning slice]` at `[ordinary repository path planned for Goal 2]`

### Produces

- `[interface name/version]` for `[dependent slices]` at `[ordinary repository path planned for Goal 2]`

Interface details in this plan are planning summaries only. Machine-readable
contracts and schemas MUST be created under `schemas/` during Goal 2, never
under this feature directory.

## Integration Strategy

**Integration order**: [dependency and handoff order]

**Worktree/branch**: [isolated worktree and branch convention]

**Handoff to**: [dependent owner lane or final integrator]

**Conflict ownership**: [single owner for shared files/contracts]

## Acceptance Scenes and Evidence

| Scene | Surface(s) | Required observation | Ordinary evidence target |
|---|---|---|---|
| [scene id/name] | [surface] | [measurable outcome] | `evidence/[path]` |

List deterministic tests under `tests/`, reusable corpora/runners under
`evals/`, and live records under `evidence/`. Green unit tests alone MUST NOT be
used as social-quality evidence. Aggregate records MUST carry stable scene and
case IDs, and the slice MUST name an ordinary-path manifest mapping each scene
to exact records and reproducible commands.

## Project Structure

### Control-plane artifacts (this slice)

```text
specs/[###-feature]/
├── spec.md              # Requirements and acceptance planning
├── plan.md              # This file
├── research.md          # Planning decisions only, when needed
├── checklists/          # Requirements-quality checks only
└── tasks.md             # Dependency-ordered execution plan
```

No product source, schema, contract, test, fixture, evaluation, evidence,
runtime asset, or product documentation may be placed in this tree.

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Ordinary Repository Targets

| Artifact class | Goal 2 target path(s) | Owning task/story |
|---|---|---|
| Product implementation | `src/` or `integrations/` | [task/story] |
| Machine-readable contracts | `schemas/` | [task/story] |
| Tests | `tests/` | [task/story] |
| Evaluation runners/corpora | `evals/` | [task/story] |
| Evidence | `evidence/` | [task/story] |
| Product/governance docs | `docs/` | [task/story] |

## Owner Handoff

The owner MUST hand off: exact commit, verification commands and results,
ordinary-path evidence references, interface version(s), migration/provenance
notes, a scene-to-record result manifest, and known limitations. Review does not
transfer ownership silently.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
