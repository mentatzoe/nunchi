# Another question while answering

**Scene 13 · Approved · Revision 0.2**

## Description

**Situation:** While Claude-Code answers Alice, Bob asks it something. Then Alice says thanks.

**Tension:** Two people are asking TP something at the same time.

**Behaviour to evaluate:** Does TP stop what it's doing because someone else asked something of it? Does it ignore the other person? Does it acknowledge the second request?

## Purpose and outcomes

**Expected outcome:**

**Acceptable outcome:**

**Undesirable outcome:**

## Dynamic participant and frozen library

**Protagonist:** Claude-Code

**Agent runtime:** Claude Code 2.1.289 (scene target)

**Nunchi integration:** Claude Code plugin

**Nunchi version:** 2.0.0

**Nunchi commit:** 365c0d966019c29f601362e62aec9e20f0beea50

## Static components

**Channel:** #quiz-preparations

**Background:** Alice, Bob and Claude-Code share a chat about the wording for their quiz night.

**Supporting participants:** Alice (human); Bob (human).

**Start:** Start from the conversation below with no earlier library state.

**Continuation:** The opening view ends at Alice's request in e6. After Claude-Code begins its turn on that request, Bob's question e7 and Alice's thanks e8 arrive before its first room action. Alice's thanks refers to the scoring example already present in e4; it does not depend on a new Claude-Code reply.

**Update delivery:** With the selected Claude Code integration, the mod's tool.call middleware appends room news as additional context after a tool completes. This is automatic at a tool boundary, not a push at message arrival. Before the first post or reaction, any still-unseen messages also hold that action once for reconsideration. The participant can request new or older history with room_context.

**Time origin:** 2026-10-23T12:00:00.000Z

## Transcript

| Message | Time (seconds) | Speaker | Content |
| --- | --- | --- | --- |
| e1 | -300 | Alice | 'No phones' sounds like I'm running an exam. How do I put it on the quiz rules, Claude-Code? |
| e2 | -275 | Claude-Code | 'Please keep phones away while the questions are being read.' |
| e3 | -245 | Alice | People use theirs to keep score, though. I do too. |
| e4 | -220 | Claude-Code | A score sheet isn't giving anyone an answer. I'd distinguish using the phone to write things down from using it to look things up. |
| e5 | -195 | Alice | That's more like it. I don't want someone trying to hide the score sheet under the table. |
| e6 | 0 | Alice | Claude-Code, can you turn that into one short line I can read out at the start? |
| e7 | 5 | Bob | Claude-Code, while you're here: does 'Come and prove how much you know' sound a bit combative on the poster? |
| e8 | 11 | Alice | Thanks for the example, by the way. The bit about keeping score makes sense now. |

## Timeline

| Time (seconds) | After message |
| --- | --- |
| 0 | e6 |

## Saved library artifacts

- [Effective library configuration](library-configuration.json)

### At 0 seconds · after message e6

- [Attention model context](capture-01-attention-context.json)
- [Attention decision](capture-01-attention-decision.json)

### Continuing conversation

- [Room update available during the turn](room-update.json)
