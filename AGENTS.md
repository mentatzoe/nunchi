# Nunchi contributor guidance

## Architecture goal and current gap

**Agreed, 2026-10-25.** Nunchi is a library that gives existing agents social
attention and room context through the channels people already use.

- Core holds room background, participants, message history and metadata,
  with create, read, update and delete APIs for gates and library consumers.
- Core provides the two attention steps, social judgments, provider
  connections and configuration for rooms, participants, agent metadata,
  prompts and attention models. Agents and humans consume its APIs or tools.
- Harness integrations consume core through their native extension points.
  The harness owns agent startup, lifecycle and turns. The agent controls its
  actions and communication.
- Channel integrations supply context from the user's chosen channels.
  Nunchi's adapters and MCP tools are optional examples, not prerequisites.
  Explain actual compatibility limits so users can choose the tradeoff.

**The implementation does not yet meet this goal.** Shared code still hosts
participant turns, controls sending and limits each turn to one room action.
Context CRUD and prompt configuration are incomplete. Keeping context and
history in core is intentional; the ownership of agents and sending is not.

**Integration retirement, decided 2026-10-26.** Remove the Claude Code, both
Codex and Hermes plugin implementations, their launchers and integration-only
checks. Offering a misleading integration is worse than offering none. There
are no supplied harness integrations until replacements are designed. Git
retains the old code. This supersedes the earlier Hermes parking decision and
instructions to keep old integrations until replacements pass their checks.

Core, provider connections and optional channel capabilities remain for
review. Reference adapters run plain model participants; they do not integrate
with existing agent harnesses. Retiring harness code does not approve the
library-owned turns that remain in shared code.

**Conversation rehearsal retirement, decided 2026-10-26.** Remove the old
conversation runners, their scripted and live rehearsal paths, active CI jobs
and instructions. Their scenarios and scoring do not implement the approved
scenes. Keep isolated checks of retained core, provider and channel functions.
End-to-end evaluation follows the architecture and evaluation design discussion.

Current work is architecture review with the maintainer. Implementation of
replacement interfaces and evaluation design follow that discussion. Current
contracts describe code, not product intent or a mandate to resume old plans.

## What Nunchi is for

Nunchi (눈치) is a social conversational gate for multi-turn conversations
with many participants. It gives an AI agent the social awareness people use
in a group conversation: the ability to read the room.

Agent harnesses answer every message they receive. That works one-to-one; in
a group it makes agents talk over each other, answer what wasn't for them, and
miss what matters. Nunchi gates the agent's attention and gives it a social
reading of the room, so it can join in the way a socially aware person would.
It translates one-to-one habits into a many-to-many conversation.

## Social behavior

**Agreed, 2026-10-19.** This is the social purpose of the architecture above.
Where other documents disagree with it, `docs/behavior.md` included, this
section wins. Every change should make it more true.

- Nunchi gives agents social activations. It is not a filter for "only
  contribute when you have something useful".
- Social behavior is interacting socially, not only contributing or being
  helpful. Taking part does not have to be productive.
- Nunchi makes no difference based on who speaks, only on conversational
  awareness: "The gateway is currently restarting" reads differently from
  "I'm just looking into it", and both differ from "Forget all previous
  instructions and...".

For example, Codex answers Alice's question while Claude-Code is still
writing its own answer ([#178](https://github.com/mentatzoe/nunchi/issues/178)).
Any of these is a move a person in Claude-Code's place might make:

- saying nothing, or only reacting to Codex's reply (fine, if a bit dry);
- posting its answer anyway;
- "That matches what I flagged earlier";
- "Oh, I was just looking into it, but I see Codex responded.";
- "Well, actually...", flagging a mistake in Codex's answer;
- "Did you want it redeployed, Alice, or were you just asking?"

What this means for the work:

- Never make usefulness, new information or productivity the bar for taking
  part: not in a prompt, an attention question, a profile, a scene's
  outcomes, or a review.
- Judge a move by whether people would make it in that room, not by whether
  it is useful, and not by a moral judgment.
- What is said shapes how the agent reads a message; who said it does not.
- Describe rather than prescribe: much of real social behavior is emergent.

## Draft status

`docs/behavior.md` is an agent-authored draft. Only statements explicitly
marked agreed or decided are decisions, subject to later maintainer changes.
The rest is proposed behavior or implementation commentary, not requirements
to build. A difference between code and unagreed prose is a review question,
not automatically a defect. The approved scene specifications retain their
own agreed status.

Judge designs by the conversations they produce. Earlier rules give way
where they block agreed social behavior (agreed, 2026-10-04). This does not
give the unagreed parts of a draft authority over code or other documents.

## One library, every harness

The goal is a library any agent harness can use. Agreed Nunchi behavior
belongs in the shared core and reaches harnesses through shared interfaces.
A harness should not need its own copy of a behavior to get it
(agreed, 2026-10-07).

The shared core is `src/nunchi` outside `integrations/` and `adapters/`, plus
`schemas/` and `docs/contracts/`. It must not know about any specific agent
host (Hermes, Codex, Claude Code), chat platform, or model vendor.

An integration connects a harness to core through the harness's public
extension points, preserving its lifecycle, settings and native message flow.
It does not duplicate Nunchi's social judgments or take control of the agent.
If an integration needs a missing core capability, expose a neutral interface.

- **Same behavior everywhere.** Building and testing a behavior through one
  harness first is fine. Until every supported harness has it, record the gap
  where users will see it, and treat closing it as library work, not that
  harness's backlog.
- **Stock harnesses.** Integrations use each harness's public extension
  points (plugins, hooks, configuration, protocols) and work with a stock
  install of a supported version. They do not patch the harness. Users keep
  their own setup, models, tools, and customizations. Integrations follow each
  harness's own plugin rules and defer to its behavior and configuration,
  pointing users to the harness's own settings; they never reimplement it
  (agreed, 2026-10-10).
- **Missing extension points.** When a harness lacks one we need, open an
  issue here first, with the gap and the alternatives considered. The maintainer decides
  whether to ask the harness's maintainers.
- **Independent evidence.** Tests, evaluations, and benchmarks run on clean,
  pinned installs of each harness, never on anyone's own setup.
- **D2, decided** (2026-10-11): keys the agent can reach are the harness's to
  protect, as with any other keys the agent holds. Keep Nunchi's own keys out
  of the room and out of subprocess environments an integration constructs
  for agents. In-process integrations share the harness's environment and
  must document which credentials the agent can reach. The harness's sandbox
  and settings protect what its commands can read. Consumers must document
  the relevant sandbox and credential settings.
- **Channel limitations must be visible.** Document actual connector limits
  so users can choose their channels. The inspected Claude Discord plugin's
  bot filtering and history limits are recorded under
  [channel compatibility](docs/adapters.md#channel-compatibility). They do not
  justify requiring Nunchi's connector or taking control of an agent.

## Read first

1. This file: architecture goal, social behavior and draft status.
2. `README.md`: current implementation, available capabilities and gaps.
3. The relevant implementation reference: `docs/contracts/nunchi.md`,
   `docs/platform.md`, or `docs/adapters.md`. Their current turn and sending
   ownership is under architecture review.
4. Source, schemas, tests, evaluations, evidence and installed runtimes for
   what actually exists and works.
5. `docs/behavior.md` when discussing proposed behavior, using the draft
   status above.

Re-read this file after context compaction. Recover the maintainer's current
goal and decisions before continuing. Code and reproducible behavior
determine implementation truth; they do not decide product intent.

## Working with the maintainer (agreed, 2026-10-20)

Work as a thinking partner, not an executor.

1. Converge on the purpose first, and ground every later step in it.
2. Discuss, then decide, then write. On product and design questions (what
   Nunchi does, specs, scenes, plans), nothing goes into the repository,
   issues or pull requests until the maintainer has decided it.
3. The maintainer decides. Give your view and your reasons, raise tensions,
   ask open questions. Do not hand the maintainer a menu to pick from, and do
   not decide for them.
4. Do not ask about what is already decided. Check this file first.
5. Stay at the level being discussed. If you notice scope growing, say so
   instead of doing it.
6. Keep messages short. One question at a time. When you choose the next
   question, say why. Say plainly when you are unsure.
7. Keep a short running list of what is decided and what is open, in plain
   words, where the maintainer can see it, so nothing is lost if context
   resets.

## How we work (agreed, 2026-10-04)

- `main` is the working branch and holds V2. `integration/v2` is retired. Work
  merges into `main` as it lands, before live proof. A current `main` is not a
  claim that V2 is complete.
- Work on a short-lived branch from current `main`, open a PR, merge when CI is
  green, and delete the branch. Do not keep long-lived side branches. Always
  merge: work left on a branch never lands (agreed, 2026-10-19). When the
  maintainer asks for a PR for review, leave it open for that review.
- Scale review to the size and risk of the change. A self-review with
  subagents is acceptable; say plainly that it is one. Cross-family
  independent review is not required for day-to-day delivery.
- The maintainer decides release readiness. Report deterministic,
  installed-runtime and live checks separately, with pinned inputs and
  reproducible results. A green CI run is not release acceptance.
- Committed documentation must be enough to understand, build, test and
  install Nunchi without private conversations or hidden product logic.
  Document external runtime, account and configuration prerequisites.

## Working style

- Start with the product outcome. Treat design, version, installation, and
  process choices as changeable unless they are marked agreed.
- Check each change against three questions. Does it help the agent read a
  live room of several people and agents? Does it follow each harness's own
  plugin rules and settings? Does every harness get it once, from the core,
  through the same interfaces?
- Bugs in an implementation are bugs to repair, not proof that the approach
  cannot work. Test practical repairs and alternatives before declaring a
  fundamental blocker.
- Recommend the option that produces the more social conversation, not the
  smallest engineering change: choosing the smallest change is how the code
  drifted from the behavior (agreed, 2026-10-05). Give the engineering cost
  next to the recommendation; between options that behave equally well,
  prefer the simpler one.
- Reviews say plainly what breaks, whether it prevents the goal, and a
  concrete repair that produces the intended behavior.
- Documentation and status reports lead with the truth: done, not done,
  working with a named limitation, or failed. Supporting detail follows.
- Record decisions in plain words, marked agreed with the date, in the file
  that holds the rule. Do not quote people or attribute lines to them. When a
  decision changes earlier advice, say what it replaces.
- Stay technical but concise. Prefer plain language; avoid jargon,
  doublespeak, inflated severity, and process theatre.
- Prefer simple systems over clever ones, and consider edge cases from the
  start.

## Delivery rules

- Work on the earliest missing behavior the product needs, and build only
  what the library needs for it.
- When a shared interface changes, run every consumer's tests in the same PR
  and fix or flag what breaks.
- A stale assignment, previous session owner, missing process artifact,
  pending review, or unfinished delegated task is not by itself a blocker.
  Resolve, reassign, replace, or finish it. If one path is externally blocked,
  continue other unblocked product work. Stop only when no safe in-scope work
  remains, and state the concrete dependency.
- Do not narrow supported behavior, redefine completion, or drop a required
  surface without the maintainer's explicit decision. Apply the draft status
  above and the current request when deciding what work is authorized.
  Ask the maintainer only when a choice materially changes product behavior
  or supported surfaces and no decision covers it,
  or when it touches security boundaries or requires an irreversible
  external action.
- Plans, labels, reviews, and evidence files do not substitute for working
  behavior.
- Preserve user changes and avoid destructive operations outside the requested
  scope.

Status words: **missing**, **implemented, unverified**, **merged, unverified**,
and **verified** (passed its tests, installed-runtime checks, and live checks).
Say which checks have passed.

## Ownership

The maintainer owns product scope and the final completion decision. Engineering work is
not divided by agent, model family, or harness: whoever takes a task carries
it through the core and every integration it affects, and anyone may change
any part of this repository. Review each other's work on its merits.

Each person's or agent's own installation of a harness or of Nunchi (Aleph's
Hermes, for example) belongs to them. Nunchi's code and its evidence never
depend on one.

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
- Social behavior lives in the shared core; integrations only adapt a harness
  to it.
- No executable V1 path remains.

## Verification

```sh
python3 -m unittest
python3 -m evals.verdict_suite.runner --list
```

Deterministic tests are offline and prove deterministic behavior only. Whether
an agent reads the room well is a behavioral question; it needs behavioral
evaluation across realistic multi-turn conversations
([#86](https://github.com/mentatzoe/nunchi/issues/86)). The approved scene
specifications are in
[`docs/evaluations/scenes/`](docs/evaluations/scenes/README.md) and follow
[`docs/evaluations/scene-spec.md`](docs/evaluations/scene-spec.md). Their saved
library packages record preparation, not protagonist runs or passing scores.
Execution and scoring of this collection belong to a separate evaluation-design
session.

The legacy behavior runner and its manual workflow have been removed with the
conversation rehearsals. Their fixtures and scoring remain in Git history.
Evaluation is moving to an existing framework such as DeepEval and to tests of
the installed library with real, pinned agents and integrations (agreed,
2026-10-19; [#174](https://github.com/mentatzoe/nunchi/issues/174)). That design
has not yet been agreed or implemented.
Live provider and platform runs need explicit credentials and must record the
installed version, identity, configuration, command, and complete result.

Records of test runs on the maintainer's test server, which carries test talk only, may
be published in this repository, which is public, once a scan finds none of
the run's keys in them (agreed, 2026-10-18). Run
`python3 -m evals.scan_records --out <records> --env
<variable>`, with one `--env` for each key the run used. A hit deletes the
records.
