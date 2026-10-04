# Nunchi contributor guidance

## What Nunchi is for

Nunchi (눈치) gives an AI agent human-like conversational awareness in a live,
multi-party, multi-turn conversation: the ability to read the room.

A person in a group chat notices what is happening, judges whether it concerns
them right now, and then joins in naturally or stays quiet. Nunchi gives each
agent that same pre-attention, so several agents and people can share one
conversation without the agents answering everything, talking over each other,
or missing what matters.

Every change should make that more true. Judge a design by the conversation it
produces, not by its mechanism.

Reading the room means:

- **The participant judges for itself.** Only the participant's own delegated
  model, shaped by its identity, instructions, and the room, decides whether a
  moment deserves its attention. Deterministic code never decides relevance,
  resolution, or obligation.
- **A conversation is a current state, not a work queue.** Messages are
  observations. Newer context can change what matters, and nothing is owed a
  reply. There is no handled/open ledger, obligation queue, or inferred roster.
- **Silence is a normal, correct outcome.** A woken participant contributes
  directly or says nothing. It never sends a meta-answer about its attention.
- **When unsure, pay attention.** Uncertainty wakes or defers. Wrongly
  suppressing something that mattered is the worst error.
- **Context is bounded and honest.** The participant sees a bounded, truthful
  snapshot of the room, including what is missing, and its own earlier turns
  as factual history.
- **Other agents are participants.** Peer agents' messages are observed like
  anyone else's. A participant's own messages never wake it.
- **Continuity without revival.** Restarts and backfill restore facts, never
  missed moments or stale turns.

## The core is agent- and provider-agnostic

The shared core is `src/nunchi` outside `integrations/` and `adapters/`, plus
`schemas/` and `docs/contracts/`. It must not know about any specific agent
host (Hermes, Codex, Claude Code), chat platform, or model vendor.

Integrations plug in through core interfaces and own their platform text,
paths, configuration, and lifecycle details. If a core change only makes sense
for one host or one vendor, it belongs in that integration, or the core needs a
neutral interface instead.

## Read first

1. This file. Zoe's decisions below take precedence over older documents.
2. `docs/architecture/v2-selected-design.md` for the selected design.
3. `docs/contracts/nunchi-v2.md` for the portable contract.
4. `docs/v2-completion-goal.md` for what a complete release must prove.
5. Source, schemas, tests, evaluations, evidence, and installed runtimes for
   what actually exists and works.

Code and reproducible behavior determine implementation truth. Specs under
`specs/` are reference material, not work authorization.

## How we work (Zoe, 2026-10-04)

- `main` is the working branch and holds V2. `integration/v2` is retired. Work
  merges into `main` as it lands, before live proof. A current `main` is not a
  claim that V2 is complete.
- Work on a short-lived branch from current `main`, open a PR, merge when CI is
  green, and delete the branch. Do not keep long-lived side branches.
- Scale review to the size and risk of the change. A self-review with
  subagents is acceptable; say plainly that it is one. Cross-family
  independent review is not required for day-to-day delivery.
- A release (a `v*` tag) still follows `docs/v2-completion-goal.md`.

## Working style

- Start with the product outcome. Treat design, version, installation, and
  process choices as changeable unless Zoe explicitly fixed them.
- Bugs in an implementation are bugs to repair, not proof that the approach
  cannot work. Test practical repairs and alternatives before declaring a
  fundamental blocker.
- Reviews say plainly what breaks, whether it prevents the goal, and the
  smallest concrete repair.
- Documentation and status reports lead with the truth: done, not done,
  working with a named limitation, or failed. Supporting detail follows.
- Stay technical but concise. Prefer plain language; avoid jargon,
  doublespeak, inflated severity, and process theatre.
- Prefer simple systems over clever ones, and consider edge cases from the
  start.

## Delivery rules

- Work on the earliest missing behavior the product needs.
- When a shared interface changes, run every consumer's tests in the same PR
  and fix or flag what breaks.
- A stale assignment, previous session owner, missing process artifact,
  pending review, or unfinished delegated task is not by itself a blocker.
  Resolve, reassign, replace, or finish it. If one path is externally blocked,
  continue other unblocked product work. Stop only when no safe in-scope work
  remains, and state the concrete dependency.
- Do not narrow supported behavior, redefine completion, or drop a required
  surface without Zoe's explicit decision. Ask Zoe only when a choice
  materially changes product behavior, supported surfaces, security
  boundaries, or requires an irreversible external action.
- Plans, labels, reviews, and evidence files do not substitute for working
  behavior.
- Preserve user changes and avoid destructive operations outside the requested
  scope.

Status words: **missing**, **implemented, unverified**, **merged, unverified**,
and **verified** (passed its tests, installed-runtime checks, and live checks).
Say which checks have passed.

## Ownership

Default owners say who normally does the work. They are not gates; Zoe can
redirect any work.

| Work | Default owner |
|---|---|
| Shared core, transport, Codex, reference adapters, packaging | Codex |
| Hermes integration | Aleph |
| Claude Code integration and security assurance | Claude |
| Product scope and final completion decision | Zoe |

## Product invariants

- Only the exact participant's delegated model may make a social suppression
  judgment.
- Deterministic code handles transport-proven non-events, lifecycle, and
  authority, never conversational meaning.
- Uncertainty wakes or defers.
- Trusted pre-attention bypass wakes directly, without a fabricated model
  result.
- Exact self binding is separate from names, aliases, and roles.
- Context is bounded, structured, honest about coverage, and optionally
  expandable; continuation authority stays host-only.
- Observation, attention, participant-host, and transport receipts are
  immutable, request-correlated, and written only by their owning stage.
- There is no social handled/open ledger, obligation queue, inferred roster, or
  send-time social reclassification.
- A woken participant contributes directly or sends nothing.
- Privileged effects require current, provenance-bound authorization for the
  exact action immediately before dispatch.
- The shared core names no agent host, chat platform, or model vendor.
- No executable V1 path remains.

## Verification

```sh
python3 -m unittest
python3 -m evals.verdict_suite.runner --list
```

Deterministic tests are offline and prove deterministic behavior only. Whether
an agent reads the room well is a behavioral question; it needs behavioral
evaluation across realistic multi-turn conversations
([#86](https://github.com/mentatzoe/nunchi/issues/86)). Live provider and
platform runs need explicit credentials and must record the installed version,
identity, configuration, command, and complete result.
