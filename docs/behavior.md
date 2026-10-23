# How Nunchi behaves

**Status: Claude's draft, under review.** Claude sessions wrote this
document, starting on 2026-10-04; it has not been agreed. Only its lines
marked agreed are decided. Social behavior, at the top of
[`AGENTS.md`](../AGENTS.md#social-behavior), wins wherever this document
disagrees. Code, contracts, specs and older designs
follow this document; where they conflict, the conflict is a gap to close
([#94](https://github.com/mentatzoe/nunchi/issues/94)).

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

## How Nunchi does it

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
- **Earlier fixtures retain their historical role.** The litmus corpus in
  `evals/verdict_suite/fixtures/` and the older-format suite in
  [`evals/behavior/`](../evals/behavior/README.md) document earlier experiments.
  Their expected moves and review metadata do not define the published
  scenes' purposes or approval.
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

## Older rules this replaces

The rules of earlier versions give way wherever they block this behavior
(agreed, 2026-10-04). The rules replaced so far:

- the "sparse" attention instruction limited to "whether the supplied event is
  worth waking for now";
- the ban on naming a social move;
- the ban on any social memory (a work queue is still out);
- ACK as a cheaper answer that Nunchi sends itself (removed in #94 step 7);
- ASK as its own kind of move (agreed, 2026-10-05: too specific; speaking
  covers asking);
- advice only on WAKE (030 FR-005, 010 FR-013). The reading reaches the
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

## Where the code is today

| Behavior here | Today (`main`) |
|---|---|
| Step 1 suppresses only non-conversation | A typed question ("is this conversation?") decides; only a "no" suppresses, and a message addressed to someone else is still conversation. A "no" never suppresses when the judgment's most likely move is to speak, such as a CI line the agent promised to report on; with the agent's memory, the judgment knows of the promise after it has left the window |
| Step 2 gives a social reading with reasons | Typed questions with pointers to messages (addressed to whom, asks for something, already answered and by which message, which earlier message it responds to, mid-thought, which moves fit); the reading the agent gets on every turn is written from the answers, and ends with the kinds of response that could fit and their probabilities. A chat model or a typed decision model can answer |
| The agent's turn carries social context | The turn prompt describes how a socially aware person takes part in a group conversation, including letting someone finish a story told across several messages and answering as a person in the room would (the people there cannot see the agent's tools or machine); the turn carries the reading and the agent's conversation memory. A tool turn names the three normal choices in order, stay quiet, nod, speak, and offers a quiet tool for the first, so silence is a choice with a reason, as in a plain call |
| Takes part socially, not only when it has something useful to add | Implemented, unverified (2026-10-19). The turn prompt says people join in for social reasons, not only to add something new (agree, joke, thank, correct someone, check what someone meant, follow up on what they said they would do), that saying nothing is a normal choice, and that the agent neither dominates nor vanishes (`participant_model.py`). Attention no longer asks whether the agent has something to add (I-010B@10), and describes staying quiet as a move, not "nothing is needed" (`attention_questions.py`). The example operator profile and the behavior suite's profiles say only who the agent is (`profiles/open-floor.json`, `evals/behavior/participants.json`). No behavior run has measured the new wording yet |
| Conversation memory | The agent's own moves (what it said, replied and reacted to, and where it stayed quiet), each pointing at its message: the newest 8 visible moves and the latest 3 silences within a day. The threads: who asked what, and which messages responded, from attention's answers about each message it judged and from platform replies, plus the agent's own messages that others responded to; the newest 6 within a day. Each move may carry the agent's own reason at the time, in its words, never posted; the Claude Code participant keeps its reasons in its own session transcript instead. Its privileged proposals appear among its moves with what became of them, and it can withdraw one still awaiting approval (#90). When an operator's approval settles one, the agent gets a turn to tell the room itself, without a new message. Each move about a message also says who wrote it and what it said, so a promise still makes sense after the request has left the window. That holds for a message the agent posted too: the host keeps which message prompted it (the room shows it back with no trace of that) and the post points at it, and counts as a response on that message's thread, so the thread no longer reads unanswered (a restart forgets it). Attention's judgment carries the same memory, so it reads a message as the agent would; a typed model is not given it yet. The parked Hermes plugin has this memory too (the older Hermes integration, which did not, was removed on 2026-10-11). Messages that arrive while the agent is mid-turn wait: only the newest gets the next turn, but up to 3 it replaced are judged for the memory first, so a question asked meanwhile starts a thread; the newest one's judgment and turn then read them with it as one moment, attention names any that still calls for the agent, and step 1 never hides it (agreed, 2026-10-06). The judgment itself still sees a window of the newest 24 events, plus up to 6 older messages of the agent's direct exchange |
| The agent sees the room as it is now | During its turn the agent can read the live room (older, newer, or new since it last looked), and before its first post it is shown what others said meanwhile, once; the parked Hermes plugin does too |
| Pace and pauses | The judgment and the agent's turn get the room's pace as facts: the current time, how long ago the judged message came, how long the room was quiet before it, its author's run of quick messages, and the agent's own share and last post; a reading written from typed answers notes a quiet of an hour or more and a run of messages within five minutes. When the judgment's most likely move is to wait, and nothing new is said for five minutes, Nunchi looks again: it judges the same message again as a pause, and the agent may get a turn that knows it is looking again and remembers why it waited. It looks again once per quiet stretch; the Hermes plugin does too (the older Hermes integration, which did not, was removed on 2026-10-11). When an approved action finishes after the agent's turn, the agent gets a turn to say so; Nunchi never says it for the agent |
| The agent can say it will report back, and is brought what it waits for | Nunchi reads each message as it arrives, a bot's status line included. A chat-model judgment carries the agent's memory, so it knows what the agent said it would do, and step 1 does not hide such a line when the judgment's most likely move is to speak; the turn's guide says this much and no more. Not yet: the typed decision model is not given the memory (`attention_questions.py`: with it, that route fell from 186 to 175 of 231 moments where the agent should speak), so on that route a status line the agent promised to report on can be passed over; messages that arrive while the agent is mid-turn wait, and only the newest gets the next turn (up to 3 it replaced are judged for the memory first); and the parked Hermes plugin drops other bots' messages unless the operator allows them (`discord.allow_bots`) |
| The agent sends its own "mhm" | A judgment that leans to a "mhm" gives the agent a turn and any "mhm" is its own; Nunchi never reacts for it, and an older setting that turned Nunchi's nod on is ignored. In a tool turn the react tool's own description says it is the "mhm" and that the reaction is exactly one emoji; a word, a `:name:` code or two emoji is refused before anything is committed, with a tool error the agent reads, so the turn is not spent and it can still nod properly, stay quiet or speak |

The defects and the full history are in
[#94](https://github.com/mentatzoe/nunchi/issues/94).
