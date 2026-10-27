# Behaviors the library should enable

**Status: draft, under review.** Only statements marked agreed are decisions
(see [draft status](../AGENTS.md#draft-status)). The purpose these behaviors
serve is [Social behavior](../AGENTS.md#social-behavior) in `AGENTS.md`, which
takes precedence.

Each is something an agent using Nunchi should be able to do in a group
conversation. How the library and the agent produce them is a design
question this page leaves open.

## Reading the room

- **Who is talking to whom.** A question to Codex is to Codex, and a remark to
  the room includes the agent.
- **What has been said, and by whom.** Who asked what, what got answered and by
  whom, which threads are still open, and what the agent itself said.
- **The pace.** A burst of messages, someone mid-thought, a pause, a room that
  has been quiet for hours.
- **What concerns it.** A CI line saying the nightly passed is noise to most of
  the room, but not to an agent that promised to tell Alice when it finished.
- **When the floor opens.** When someone finishes, the agent may take its turn.
- **The room's own norms.** A room may set a stricter or looser bar.

## Taking part

- **Socially, not only usefully.** Nunchi gives agents social activations, not
  "only contribute when you have something useful" (agreed, 2026-10-19).
- **Joining what wasn't addressed to it.** An agent that overhears "hey Codex,
  how is X implemented?" may reasonably join.
- **Letting people finish.** While someone tells something across several
  messages, a "mhm" rather than taking the floor.
- **Letting the addressee answer first.** Others wait a beat.
- **Waiting, then looking again.** Some moves depend on what happens next: the
  addressee answering, or the speaker finishing.
- **Saying only what it knows.** One clarifying question beats a guess.
- **Keeping track of its own share.** It neither dominates nor vanishes.
- **Avoiding collective silence and pile-ons.** Several agents each thinking
  "someone else will answer" leave the room silent. Several agents all
  answering at once bury the person who asked.
- **Reading other agents as peers.** Their messages count the same as anyone
  else's.

The kinds of response that can fit a moment: stay quiet, "mhm", wait, or speak
(answer, ask, give an opinion, or say anything else to the room). Asking is a
kind of speaking, not a separate move (agreed, 2026-10-05).

## The "mhm"

A backchannel shows the agent is following without taking the floor.

- **When it fits.** Someone is telling something across several messages, or
  makes a point to the agent that doesn't need an answer yet.
- **How often.** Sparingly. One now and then shows attention; one on every
  message is a tic.
- **Where it goes.** On the message it acknowledges.
- **What it means.** "I'm with you." Not "I agree", and not "I'll do it".
- **What happens after.** When the speaker finishes, the agent may still reply
  or stay quiet.
- **Who sends it.** The agent itself, like every visible move.

## Catching up

While the agent is busy answering one person, others keep talking. When it is
free again, it catches up the way a person does: it reads the newest message,
then glances back at what it missed, so a question Bob asked meanwhile is not
lost behind Alice's "thanks" (agreed, 2026-10-06). An agent that can take news
while it works hears of new messages as they come, as a person glances up from
what they are writing, and can fold them into its reply.

## Gaps

When what the agent reads runs up to or across a point where messages may be
missing (a restart, a lost connection), it is told so once, in one plain
sentence, at the gap, and attention sees the same fact. Once the agent has
acted past the gap, it is no longer news (agreed, 2026-10-10).
