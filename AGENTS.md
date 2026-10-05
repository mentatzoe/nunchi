# Nunchi contributor guidance

## What Nunchi is for

Nunchi (눈치) is a social conversational gate for multi-turn conversations
with many participants. It gives an AI agent the social awareness people use
in a group conversation: the ability to read the room.

Agent harnesses answer every message they receive. That works one-to-one; in
a group it makes agents talk over each other, answer what wasn't for them, and
miss what matters. Nunchi gates the agent's attention and gives it a social
reading of the room, so it can join in the way a socially aware person would.
It translates one-to-one habits into a many-to-many conversation.

The behavior is defined in [`docs/behavior.md`](docs/behavior.md). Every
change should make that behavior more true. Judge a design by the conversation
it produces, not by its mechanism. Zoe, 2026-10-04: rules from earlier
versions give way wherever they block this behavior
([#94](https://github.com/mentatzoe/nunchi/issues/94)).

Reading the room means:

- **Two steps, then the agent.** Step 1 asks whether this is conversation a
  participant like this one could take part in; it is conservative and never
  suppresses a message just because it was addressed to someone else. Step 2
  reads what is happening and recommends the kinds of response that could
  fit, with reasons. The agent then decides.
- **The participant judges for itself.** Only the participant's own delegated
  models, shaped by its identity, instructions, and the room, read the room
  for it. Deterministic code never decides relevance, resolution, or
  obligation.
- **Every visible move is the agent's own act**, including a "mhm". Nunchi
  never posts on the agent's behalf. (Today's ACK still does; #94.)
- **A conversation has memory, not a work queue.** Each participant keeps a
  memory of the conversation: who asked what, what was answered and by whom,
  its own moves and why. Every fact points to the messages it came from and
  none obliges a reply. There is no obligation queue or inferred roster.
- **Rhythm matters.** Pace, pauses, someone mid-thought, and the agent's own
  share of the conversation are part of reading the room.
- **Silence is a normal, correct outcome.** A woken participant contributes
  directly or says nothing. It never sends a meta-answer about its attention.
- **When unsure, pay attention.** Uncertainty wakes or defers. Wrongly
  suppressing something that mattered is the worst error.

Today's code does not yet behave this way in several places; the table at the
end of `docs/behavior.md` lists where. Treat each difference as a gap to close,
not as the intended behavior.
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
2. `docs/behavior.md` for the behavior Nunchi exists for. Where an older
   design, contract, or spec conflicts with it, the behavior wins.
3. `docs/architecture/v2-selected-design.md` for the selected design.
4. `docs/contracts/nunchi-v2.md` for the portable contract.
5. `docs/v2-completion-goal.md` for what a complete release must prove.
6. Source, schemas, tests, evaluations, evidence, and installed runtimes for
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
- Recommend the option that produces the more social conversation, not the
  smallest engineering change. Zoe, 2026-10-05: choosing the smallest change
  is how the code drifted from the behavior. Give the engineering cost next
  to the recommendation; between options that behave equally well, prefer
  the simpler one.
- Reviews say plainly what breaks, whether it prevents the goal, and a
  concrete repair that produces the intended behavior.
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
- Conversation memory records facts with pointers to messages and never
  obliges a reply. There is no obligation queue, inferred roster, or send-time
  social reclassification.
- A woken participant contributes directly or sends nothing.
- Privileged effects require current, provenance-bound authorization for the
  exact action immediately before dispatch.
- The shared core names no agent host, chat platform, or model vendor.
- No executable V1 path remains.

## Verification

```sh
python3 -m unittest
python3 -m evals.verdict_suite.runner --list
python3 -m evals.behavior.run --dry-run
```

Deterministic tests are offline and prove deterministic behavior only. Whether
an agent reads the room well is a behavioral question; it needs behavioral
evaluation across realistic multi-turn conversations
([#86](https://github.com/mentatzoe/nunchi/issues/86)). The scenes are in
`evals/behavior/`; the manual `behavior-eval` workflow runs them against real
models. Live provider and
platform runs need explicit credentials and must record the installed version,
identity, configuration, command, and complete result.
