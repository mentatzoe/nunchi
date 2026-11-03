# Nunchi contributor guidance

## Architecture goal

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

Where code, tests or other documents disagree with this goal, the goal wins.

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

## Integrations and channels

- Core must not know about any specific agent host (Hermes, Codex, Claude
  Code), chat platform, or model vendor.
- An integration connects a harness to core through the harness's public
  extension points, preserving its lifecycle, settings and native message
  flow. It does not duplicate Nunchi's social judgments or take control of
  the agent.
- **Stock harnesses.** Integrations use each harness's public extension
  points (plugins, hooks, configuration, protocols) and work with a stock
  install of a supported version. They do not patch the harness. Users keep
  their own setup, models, tools, and customizations. Integrations follow each
  harness's own plugin rules and defer to its behavior and configuration,
  pointing users to the harness's own settings; they never reimplement it
  (agreed, 2026-10-10).
- **Missing extension points.** When a harness lacks one we need, open an
  issue here first, with the gap and the alternatives considered. The
  maintainer decides whether to ask the harness's maintainers.
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
  so users can choose their channels. Limits do not justify requiring
  Nunchi's connector or taking control of an agent.

## Read first

- `docs/behavior.md` for the social behaviors under discussion, using the
  draft status above.
- For existing code, the source and tests show what the code does. They do
  not decide product intent.

Re-read this file after context compaction. Recover the maintainer's current
goal and decisions before continuing.

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

## Working style

- Start with the product outcome. Treat design, version, installation, and
  process choices as changeable unless they are marked agreed.
- Check each change against three questions. Does it help the agent read a
  live room of several people and agents? Does it follow each harness's own
  plugin rules and settings? Does it keep the agent in control of its own
  actions and communication?
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
