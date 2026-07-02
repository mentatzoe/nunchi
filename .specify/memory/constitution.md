<!--
Sync Impact Report
Version change: template -> 1.0.0
Modified principles: all template placeholders replaced with Nunchi-specific principles
Added sections: Product Boundaries; SpecKit Workflow & Review Gates; Agent Execution Hygiene
Removed sections: placeholder Section 2 and Section 3 names/content
Templates requiring updates:
- ✅ .specify/templates/plan-template.md reviewed; generic Constitution Check gate already fits
- ✅ .specify/templates/spec-template.md reviewed; user-story vertical slicing model retained
- ✅ .specify/templates/tasks-template.md reviewed; independent-story tasking retained
- ✅ .specify/templates/commands/ absent in this Spec Kit install; installed agent skill command docs retained
- ✅ AGENTS.md and CLAUDE.md updated with Nunchi runtime guidance
Follow-up TODOs: none
-->

# Nunchi Constitution

## Core Principles

### I. Admission, Not Composition

Nunchi MUST decide admission for shared-surface triggers: whether the current
agent produces visible participation. The core verdict vocabulary is exactly
`PASS`, `ACK`, `ASK`, and `SPEAK` unless this constitution is amended. The core
MUST NOT draft reply prose, prescribe wording, or define speech-shape commands.
It MAY return evidence, confidence distribution, and context references so the
host agent or harness can decide what to say after admission is granted.

Rationale: the product exists to decide whether this agent enters the room, not
to become a second composer hidden upstream of the normal agent.

### II. Hard-Stop PASS Is Load-Bearing

A `PASS` verdict MUST be terminal for ordinary visible participation. A
successful PASS MUST NOT emit a room message, including sentinel strings,
acknowledgements, or explanatory text. Telemetry, traces, and audit records MAY
be written to non-conversational channels. Every integration MUST distinguish
"the gate ran and decided PASS" from "the gate did not run" or "the harness
swallowed the trigger before classification."

Rationale: a PASS that still speaks is not a pass. It is coordination noise with
a quieter costume.

### III. CLI-First, Modular Core

Every product capability MUST be reachable through the `nunchi` CLI and MUST
also live behind an internal callable core. A command-line wrapper that contains
all decision logic inline is not acceptable. The core MUST expose a stable
in-process evaluation boundary that tests and adapters can call without shelling
out. The CLI MUST support JSON input from stdin or file, JSON output on stdout,
errors on stderr, and documented exit-code semantics.

Rationale: the public product is a portable utility, not a script with a
costume. The CLI is the operator surface; the callable core is the adapter seam.

### IV. Vertical, Independently Testable Slices

SpecKit feature specs MUST be vertical user-story increments that can be tested
and demonstrated independently. Horizontal component specs are allowed only when
they support a previously shipped vertical path or when the spec declares a
non-user-facing maintenance purpose. The first product spec MUST prove an
end-to-end path from supplied conversation context to a verdict that a harness
can obey. A slice is not complete merely because schemas, docs, or internal
pieces exist.

Rationale: Nunchi's highest project risk is fake done. The first release
candidate must do the product job, not only prepare to do it later.

### V. Test-First Contract and Fixture Discipline

Any feature that changes verdict semantics, input envelope shape, provider
behavior, or adapter guarantees MUST define tests or fixtures before the
implementation is treated as complete. The test set MUST cover all four verdicts
where the feature can influence them. Contract tests MUST verify output schema,
PASS suppression semantics, `context_checked` truthfulness, and failure behavior
for invalid input. CI MUST have a deterministic provider path; a product claim
that depends only on a live stochastic provider is incomplete.

Rationale: the contract is the product surface. Tests are how the project keeps
agents from relabeling hopeful behavior as working behavior.

### VI. Adapter Tier Honesty and Consumer Boundaries

Nunchi MUST support invocation at the earliest reliable boundary a host
harness exposes: wrapper/gateway, pre-input hook, pre-model hook, agent-invoked
tool, or output-suppression fallback. Each adapter or handoff document MUST
state its capability tier and whether PASS is guaranteed to produce no visible
reply. The product team owns the CLI, callable core, schema, fixtures, and
handoff packet. It does not own every downstream adapter implementation.

Rationale: pre-LLM integration is valuable but not universal. Honest tiering
keeps the portable core from overfitting to one harness.

### VII. Context Truth and Room Inference

`context_checked` MUST describe context actually inspected by the gate. It MUST
NOT claim unavailable history, unqueried state, or inferred peer coverage as if
it had been checked. The classifier MAY infer what "the room" is from supplied
context, but it MUST NOT depend on a hardcoded surface taxonomy or predeclared
social rule list as the hidden product contract. Plans MUST preserve the guiding
heuristic: imagine a person entering this conversation and deciding whether to
participate.

Rationale: false context receipts are worse than uncertainty. The classifier's
judgment must stay auditable without turning human room sense into brittle
surface rules.

### VIII. Documentation Is Product

Quickstarts, examples, integration handoff documents, and README claims MUST be
backed by runnable commands, fixtures, or tests. Documentation MUST state when a
capability is implemented, planned, or intentionally out of scope. Marketing and
positioning copy MUST NOT lead implementation truth; no public claim may imply a
working adapter, provider, or release path that has not been verified.

Rationale: for a portable CLI utility, docs are how other harness owners decide
whether they can trust and integrate the tool.

## Product Boundaries

Nunchi is a portable pre-reply admission gate for unstructured multi-agent
collaboration on shared surfaces such as chats, meetings, repos, or issue
threads. It consumes supplied context and returns an auditable participation
verdict. The core contract is:

- `trigger`: the event or message being evaluated
- `verdict`: one of `PASS`, `ACK`, `ASK`, `SPEAK`
- `confidences`: per-verdict confidence distribution
- `context_checked`: specific context the gate inspected

The following are out of scope unless a future constitution amendment explicitly
moves them in:

- detecting coordination failure modes as the primary product job
- central orchestration, fixed speaking order, or manager-agent routing
- composing the final reply text
- requiring a literal pre-LLM hook in every harness
- building every downstream adapter before the core CLI is useful
- research/evaluation tracking for the peer-coordination experiment
- marketing, DevRel examples, or release claims before a runnable quickstart

## SpecKit Workflow & Review Gates

Nunchi uses Spec Kit as the governing development workflow. The constitution
MUST exist before product feature specs. Production features MUST use this gate
sequence unless the project owner explicitly approves a narrower spike:

1. `/speckit-constitution` for governance changes
2. `/speckit-specify` focused on what and why, not implementation stack
3. `/speckit-clarify` for high-impact ambiguity, one question at a time
4. `/speckit-plan` for technical plan and Constitution Check
5. `/speckit-checklist` for requirements quality before task generation
6. `/speckit-tasks` for dependency-ordered tasks by user story
7. `/speckit-analyze` before implementation; CRITICAL/HIGH findings block work
8. `/speckit-implement` or equivalent agent execution against the task file

Each bounded spec MUST have exactly one accountable owner from specify through
implementation or through a recorded handoff. Reviewers MAY challenge, red-team,
or inspect artifacts, but they do not silently co-own the same spec context.

The first product spec SHOULD be named `001-core-cli-mvp` or another clear
vertical equivalent. Its done bar MUST include a runnable CLI verdict path,
callable modular core, schema/fixture tests, and PASS suppression semantics.

## Agent Execution Hygiene

Agents working in this repository MUST use isolated git worktrees for non-trivial
branches after the initial bootstrap. The main checkout is reserved for main and
trivial authorized bootstrap changes. Worktrees belong under `.worktrees/<slug>`.

Agent-authored PRs MUST name:

- owning agent and runtime
- SpecKit feature directory
- issue or Multica card, when present
- verification commands and results
- whether the appropriate bot identity authored the commit

Codex runs that need high reasoning MUST pass `-c model_reasoning_effort=xhigh`.
Claude Code runs that need high reasoning MUST pass `--effort xhigh`. If an
agent runtime cannot expose the required effort setting, the issue or PR MUST
state that limitation before the work is treated as reviewed.

## Governance

This constitution supersedes README text, issue descriptions, agent prompts, and
ad hoc chat decisions when they conflict. A conflicting product request MUST
pause for explicit constitutional amendment or a documented exception.

Amendments require:

- a written rationale
- a semantic version bump
- a Sync Impact Report in this file
- review of affected templates, agent guidance, and active specs
- project owner approval or an explicit delegated approval path

Versioning policy:

- MAJOR for principle removals, product-boundary reversals, or backward
  incompatible governance changes
- MINOR for new principles, new required gates, or materially expanded scope
- PATCH for wording clarifications that do not change obligations

Compliance review is mandatory before implementation and before release claims.
Any unjustified constitution violation in a spec, plan, task file, PR, or release
artifact blocks the work until corrected or explicitly amended.

**Version**: 1.0.0 | **Ratified**: 2026-05-22 | **Last Amended**: 2026-05-22
