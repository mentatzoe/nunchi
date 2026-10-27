# Social behavior draft

**Status: draft, under review.** Follow the [draft-status guidance](../AGENTS.md#draft-status):
only explicitly agreed statements are decisions, subject to later maintainer
changes. The [architecture goal](../AGENTS.md#architecture-goal-and-current-gap)
and [social purpose](../AGENTS.md#social-behavior) take precedence. Unagreed
recommendations here do not prescribe implementation or authorize work.

## Purpose

Agent harnesses answer every message they receive. That works one-to-one. In
a group it doesn't: agents talk over each other, answer what wasn't meant for
them, and miss the moment that was.

Nunchi gives an agent the social awareness people use in a group
conversation. It gates the agent's attention and hands the agent a social
reading of the room, so the agent can take part the way a socially aware
person would. It translates one-to-one habits into a many-to-many
conversation, across many turns and many participants.

This draft explores how to describe social awareness explicitly. Its proposed
behaviors and mechanisms remain open for discussion.

## What a socially aware participant does

Proposals for discussion, except where explicitly marked agreed:

- **Reads who is talking to whom.** It knows a question to Codex is to
  Codex, and that a remark to the room includes it.
- **Remembers what has been said, and by whom.** It notices when a question
  has been answered.
- **Notices the pace.** A burst of messages, someone mid-thought, a pause, a
  room that has been quiet for hours.
- **Lets people finish.** While someone is telling something across several
  messages, it gives a "mhm" rather than taking the floor.
- **Lets the addressee answer first.**
- **Takes part socially, not only when it has something useful to add.**
  Nunchi gives agents social activations, not "only contribute when you have
  something useful" (agreed, 2026-10-19).
- **Says only what it knows.** One clarifying question beats a guess.
- **Keeps track of its own share.** It neither dominates nor vanishes.
- **Notices when the floor opens.** When someone finishes, it may take its
  turn.
- **Avoids collective silence and pile-ons.** Several agents each thinking
  "someone else will answer" leave the room silent. Several agents all
  answering at once bury the person who asked.
- **Follows the room's own norms.** A room may set a stricter or looser bar.

## Proposed behavior and current mechanisms

### Step 1: is this conversation, and could someone like me take part?

This step is conservative. It suppresses only what clearly isn't
conversation:

- status reports;
- bot and CI noise;
- system events;
- the agent's own echoes.

It never suppresses a message just because it was addressed to someone else.
An agent that overhears "hey Codex, how is X implemented?" may reasonably
join.

Nor does it suppress a status report the agent has reason to speak to. A CI
line saying the nightly passed is noise to most of the room, but not to an
agent that promised to tell Alice when it finished. When the judgment's own
most likely move is to speak, the message passes.

When unsure, the message passes. A wrong suppression is invisible to
everyone. A wrong pass costs one turn.

### Step 2: what is happening, and what kinds of response could fit?

This step produces a social reading of the moment. It draws on the recent
history, the pace and the conversation memory. It names:

- **What has happened, with pointers to the messages.** For example:
  "already answered by Codex", "Alice is mid-thought: three messages in
  twenty seconds", "addressed to Bob".
- **The kinds of response that could fit, each with its reason.**
  - Stay quiet.
  - "Mhm".
  - Wait: for the addressee, or for the speaker to finish.
  - Speak: answer, ask, give an opinion, or say anything else to the room.

The reading is a recommendation with reasons, not an order.

### The agent's turn

The agent receives:

- the reading;
- the recent history;
- its conversation memory;
- its own recent moves.

Then it decides, and it acts.

**Every visible move is the agent's own act, including a "mhm".** Nunchi
never posts on the agent's behalf. If Nunchi nodded for an agent that never
knew, the room would believe the agent was listening when the agent has no
memory of it. A judgment that a "mhm" could fit gives the agent a turn, and
any "mhm" is the agent's own. Nunchi's own nod was off by default from
2026-10-05 and was removed in step 7 of the plan.

**A gap is told once, at the gap.** When what the agent reads runs up to or
across a point where messages may be missing (a restart, a lost connection),
the turn says so in one plain sentence and attention sees the same fact; once
the agent has taken a turn past it, it is no longer news (agreed, 2026-10-10).

### Looking again

Some moves depend on what happens next: wait for the addressee, or let the
speaker finish. When the pause ends, Nunchi reads the room again and gives
the agent a fresh reading.

### Catching up

While the agent is busy answering one person, others keep talking. When it
is free again, it catches up the way a person does: it reads the newest
message, then glances back at what it missed. Nunchi reads those messages
together as one moment, so a question Bob asked meanwhile is not lost
behind Alice's "thanks". An agent that can take news while it works hears of
new messages as they come, as a person glances up from what they are
writing, and can fold them into its reply.

## Conversation memory

Each participant keeps its own memory of the conversation, like a person
does:

- who asked what;
- what got answered, and by whom;
- what the agent itself said or nodded at, and why;
- which threads are still open;
- the pace of the conversation.

Rules for the memory:

- **Facts with pointers, not verdicts.** "Codex answered Alice's question
  (this message)" is a reason the reading can cite. The memory never says
  "handled, don't answer".
- **Nothing in it obliges a reply.** It is a memory, not a work queue.
- **Old items fade.**
- **Every fact can be checked against the messages it came from.** A summary
  that can't be checked is how intent drifts.

## The "mhm" (ACK)

ACK is a backchannel. It shows the agent is following without taking the
floor.

- **When it fits.** Someone is telling something across several messages, or
  makes a point to the agent that doesn't need an answer yet.
- **How often.** Sparingly. One now and then shows attention; one on every
  message is a tic.
- **Where it goes.** On the message it acknowledges.
- **What it means.** "I'm with you." Not "I agree", and not "I'll do it".
- **What happens after.** When the speaker finishes, the agent may still
  reply or stay quiet.
- **Who sends it.** The agent itself.

## Many agents in one room

- Agents read each other's messages as peers, the same as anyone else's.
- The addressee goes first. Others wait a beat.
- The reading watches for collective silence and for pile-ons.

## How we know it works

- **Behavior is judged by conversations, with real models.**
  The [approved scene specifications](evaluations/scenes/README.md) describe
  the social situations and purposes reviewed with the maintainer, under the
  [scene spec](evaluations/scene-spec.md). Judge a move by whether a person
  might make it in that room, as [Social behavior](../AGENTS.md#social-behavior)
  requires. Observational scenes may leave outcome fields blank; that is not
  an invitation to invent required responses.
- **Preparation is separate from evaluation.** The collection's saved
  library packages are not protagonist runs or evidence of passing scenes.
  Running and scoring the collection belong to a separate evaluation-design
  session.
- **Old conversation fixtures are not evaluation criteria.** The retired
  behavior runner's expectations remain in Git history. They do not define
  the published scenes' purposes or approval.
- **Deterministic tests prove plumbing only.**

## Fast decisions

Steps 1 and 2 run at every conversational moment, including pauses, so they
need to be fast and cheap.

- Typed decision models, such as System One–style classifiers
  ([#87](https://github.com/mentatzoe/nunchi/issues/87)), fit well. They
  return typed facts with calibrated probabilities. Those facts can be kept in
  the conversation memory and shown to the agent.
- Any model provider can serve these steps
  ([#85](https://github.com/mentatzoe/nunchi/issues/85)).

## Earlier decisions and implementation changes

Earlier rules give way where they block agreed social behavior
(agreed, 2026-10-04). The notes below distinguish explicitly agreed changes
from implementation history; they do not approve the rest of this draft:

- the "sparse" attention instruction limited to "whether the supplied event is
  worth waking for now";
- the ban on naming a social move;
- the ban on any social memory (a work queue is still out);
- ACK as a cheaper answer that Nunchi sends itself (removed in #94 step 7);
- ASK as its own kind of move (agreed, 2026-10-05: too specific; speaking
  covers asking);
- advice only on WAKE. The reading reaches the
  agent on every turn it takes, and a bad reading never throws away a
  judgment (agreed, 2026-10-05);
- suppressing a message because the agent is "neither addressed nor
  useful", and the PASS/ACK/ASK/SPEAK confidence vector behind it. Since
  #94 step 4 step 1 suppresses only what is not conversation, and the
  judgment is a set of typed answers;
- this document's own first yardstick, which said the agent "doesn't repeat
  what someone already said", tested speaking with "do I have something to
  add?", and "holds back when others have it covered". The idea is social
  activations for agents, not "only contribute when you have something
  useful" (agreed, 2026-10-19);
- the first draft's lines that made knowing something the reason to join: the
  addressee goes first and the agent "joins if they don't answer, or if it
  knows something they don't"; an agent that overhears a question to someone
  else "and knows the answer may reasonably join"; and "you know something
  nobody has said" as an example of the reading. They don't fit Social
  behavior at the top of `AGENTS.md` (agreed, 2026-10-19).

## Implementation references

The [runtime guide](platform.md) describes the remaining code and its gaps.
There are no supplied harness integrations. The former implementation table
mixed dated observations with this draft's proposals and has been removed;
Git retains it.

The catch-up behavior above was agreed on 2026-10-06: attention reads messages
that arrived while the participant was busy together with the newest message,
so an earlier question is not hidden. The current implementation judges at most
three superseded messages for memory before the newest message; that bound is
an implementation detail, not the social goal.
