# How Nunchi behaves

**Status: draft for Zoe's review, 2026-10-04.** This document defines the
behavior Nunchi exists for. Code, contracts, specs and older designs follow
it. Where they conflict, this document wins, and the conflict is a gap to
close ([#94](https://github.com/mentatzoe/nunchi/issues/94)).

## Purpose

Agent harnesses answer every message they receive. That works one-to-one. In
a group it doesn't: agents talk over each other, answer what wasn't meant for
them, and miss the moment that was.

Nunchi gives an agent the social awareness people use in a group
conversation. It gates the agent's attention and hands the agent a social
reading of the room, so the agent can take part the way a socially aware
person would. It translates one-to-one habits into a many-to-many
conversation, across many turns and many participants.

Social awareness can be learned and described explicitly. This document is
that description. Every model and prompt in Nunchi should carry it.

## What a socially aware participant does

This is the yardstick. Every change is judged against it.

- **Reads who is talking to whom.** It knows a question to Codex is to
  Codex, and that a remark to the room includes it.
- **Remembers what has been said, and by whom.** It doesn't repeat what
  someone already said, and it notices when a question has been answered.
- **Notices the pace.** A burst of messages, someone mid-thought, a pause, a
  room that has been quiet for hours.
- **Lets people finish.** While someone is telling something across several
  messages, it gives a "mhm" rather than taking the floor.
- **Lets the addressee answer first.** It joins if they don't answer, or if
  it knows something they don't.
- **Speaks when it has something that serves the moment.** The test is "do I
  have something to add?", not "do I *have* to take this?". One clarifying
  question beats a guess.
- **Holds back when others have it covered.**
- **Keeps track of its own share.** It neither dominates nor vanishes.
- **Notices when the floor opens.** When someone finishes, it may take its
  turn.
- **Avoids collective silence and pile-ons.** Several agents each thinking
  "someone else will answer" leave the room silent. Several agents all
  answering at once bury the person who asked.
- **Follows the room's own norms.** A room may set a stricter or looser bar.

## How Nunchi does it

### Step 1: is this conversation, and could someone like me take part?

This step is conservative. It suppresses only what clearly isn't
conversation:

- status reports;
- bot and CI noise;
- system events;
- the agent's own echoes.

It never suppresses a message just because it was addressed to someone else.
An agent that overhears "hey Codex, how is X implemented?" and knows the
answer may reasonably join.

Nor does it suppress a status report the agent has reason to speak to. A CI
line saying the nightly passed is noise to most of the room, but not to an
agent that promised to tell Zoe when it finished. When the judgment's own
most likely move is to speak, the message passes.

When unsure, the message passes. A wrong suppression is invisible to
everyone. A wrong pass costs one turn.

### Step 2: what is happening, and what kinds of response could fit?

This step produces a social reading of the moment. It draws on the recent
history, the pace and the conversation memory. It names:

- **What has happened, with pointers to the messages.** For example:
  "already answered by Castor", "Zoe is mid-thought: three messages in twenty
  seconds", "addressed to Codex", "you know something nobody has said".
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

### Looking again

Some moves depend on what happens next: wait for the addressee, or let the
speaker finish. When the pause ends, Nunchi reads the room again and gives
the agent a fresh reading.

### Catching up

While the agent is busy answering one person, others keep talking. When it
is free again, it catches up the way a person does: it reads the newest
message, then glances back at what it missed. Nunchi reads those messages
together as one moment, so a question Sam asked meanwhile is not lost
behind Zoe's "thanks". An agent that can take news while it works hears of
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

- **Facts with pointers, not verdicts.** "Castor answered Zoe's question
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
  - The litmus corpus in `evals/verdict_suite/fixtures/` has 60 scenes,
    many taken from real rooms.
  - New scenes cover rhythm, memory and several agents
    ([#86](https://github.com/mentatzoe/nunchi/issues/86)).
- **The suite is `evals/behavior/`.** Each scene lists what a socially
  aware participant would notice, the moves that fit and the clear misses.
  A run reports how each model spreads across that range. See
  `evals/behavior/README.md`.
- **Deterministic tests prove plumbing only.**
- **Scenes the new suite must include:**
  - a story told across five messages: the agent nods, then replies at the
    end;
  - a question someone else already answered;
  - a question to another agent that this agent can answer: it waits, then
    joins if nobody answers;
  - two agents about to answer the same question;
  - a room quiet for hours, then a new message;
  - after the agent nodded, someone asks "did you see what I said?";
  - a status report from a bot, which is suppressed;
  - the agent addressed in a busy room, where 30 messages later the mention
    is still known.

## Fast decisions

Steps 1 and 2 run at every conversational moment, including pauses, so they
need to be fast and cheap.

- Typed decision models, such as System One–style classifiers
  ([#87](https://github.com/mentatzoe/nunchi/issues/87)), fit well. They
  return typed facts with calibrated probabilities. Those facts can be kept in
  the conversation memory and shown to the agent.
- Any model provider can serve these steps
  ([#85](https://github.com/mentatzoe/nunchi/issues/85)).

## Older rules this replaces

Zoe, 2026-10-04: the rules of earlier versions give way wherever they block
this behavior. The rules replaced so far:

- the "sparse" attention instruction limited to "whether the supplied event is
  worth waking for now";
- the ban on naming a social move;
- the ban on any social memory (a work queue is still out);
- ACK as a cheaper answer that Nunchi sends itself (removed in #94 step 7);
- ASK as its own kind of move (Zoe, 2026-10-05: too specific; speaking
  covers asking);
- advice only on WAKE (030 FR-005, 010 FR-013). Zoe, 2026-10-05: the
  reading reaches the agent on every turn it takes, and a bad reading never
  throws away a judgment;
- suppressing a message because the agent is "neither addressed nor
  useful", and the PASS/ACK/ASK/SPEAK confidence vector behind it. Since
  #94 step 4 step 1 suppresses only what is not conversation, and the
  judgment is a set of typed answers.

## Where the code is today

| Behavior here | Today (`main`) |
|---|---|
| Step 1 suppresses only non-conversation | A typed question ("is this conversation?") decides; only a "no" suppresses, and a message addressed to someone else is still conversation. A "no" never suppresses when the judgment's most likely move is to speak, such as a CI line the agent promised to report on; with the agent's memory, the judgment knows of the promise after it has left the window |
| Step 2 gives a social reading with reasons | Typed questions with pointers to messages (addressed to whom, asks for something, already answered and by which message, which earlier message it responds to, mid-thought, something to add, which moves fit); the reading the agent gets on every turn is written from the answers, and ends with the kinds of response that could fit and their probabilities. A chat model or a typed decision model can answer |
| The agent's turn carries social context | The turn prompt describes how a socially aware person takes part in a group conversation; the turn carries the reading and the agent's conversation memory |
| Conversation memory | The agent's own moves (what it said, replied and reacted to, and where it stayed quiet), each pointing at its message: the newest 8 visible moves and the latest 3 silences within a day. The threads: who asked what, and which messages responded, from attention's answers about each message it judged and from platform replies, plus the agent's own messages that others responded to; the newest 6 within a day. Each move may carry the agent's own reason at the time, in its words, never posted; the Claude Code participant keeps its reasons in its own session transcript instead. Its privileged proposals appear among its moves with what became of them, and it can withdraw one still awaiting approval (#90). When an operator's approval settles one, the agent gets a turn to tell the room itself, without a new message. Each move about a message also says who wrote it and what it said, so a promise still makes sense after the request has left the window. Attention's judgment carries the same memory, so it reads a message as the agent would; a typed model is not given it yet. Not yet: memory on Hermes. Messages that arrive while the agent is mid-turn wait: only the newest gets the next turn, but up to 3 it replaced are judged for the memory first, so a question asked meanwhile starts a thread; the newest one's judgment and turn then read them with it as one moment, attention names any that still calls for the agent, and step 1 never hides it (Zoe, 2026-10-06). The judgment itself still sees a window of the newest 24 events, plus up to 6 older messages of the agent's direct exchange |
| The agent sees the room as it is now | During its turn the agent can read the live room (older, newer, or new since it last looked), and before its first post it is shown what others said meanwhile, once; Hermes does not offer this yet |
| Pace and pauses | The judgment and the agent's turn get the room's pace as facts: the current time, how long ago the judged message came, how long the room was quiet before it, its author's run of quick messages, and the agent's own share and last post; a reading written from typed answers notes a quiet of an hour or more and a run of messages within five minutes. When the judgment's most likely move is to wait, and nothing new is said for five minutes, Nunchi looks again: it judges the same message again as a pause, and the agent may get a turn that knows it is looking again and remembers why it waited. It looks again once per quiet stretch; the Hermes plugin does too, the older Hermes integration does not. When an approved action finishes after the agent's turn, the agent gets a turn to say so; Nunchi never says it for the agent |
| The agent sends its own "mhm" | A judgment that leans to a "mhm" gives the agent a turn and any "mhm" is its own; Nunchi never reacts for it, and an older setting that turned Nunchi's nod on is ignored |

The defects and the full history are in
[#94](https://github.com/mentatzoe/nunchi/issues/94).
