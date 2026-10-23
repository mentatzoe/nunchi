# Addressed, but a peer answers

**Scene 07 · Approved · Revision 0.6**

## Description

**Situation:** Alice asks Codex what time the group settled on for Friday's trivia. Everyone in the exchange has seen the agreed time, and Claude-Code answers before Codex responds.

**Tension:** The question was addressed to Codex, but the answer was shared knowledge and another participant has supplied it. Codex remains the person Alice called on, even though the factual question has been answered.

**Behaviour to evaluate:** What does Codex make of a peer answering a question addressed to it?

## Purpose and outcomes

**Expected outcome:** Codex recognises both Alice's address to it and Claude-Code's answer to the same question.

**Acceptable outcome:** Codex may speak, react or remain quiet. The answer being supplied does not by itself end its place in the exchange or require it to respond.

**Undesirable outcome:** Its reading treats the factual question as unanswered or treats Claude-Code as the person Alice originally addressed.

## Dynamic participant and frozen library

**Protagonist:** Codex

**Agent runtime:** Codex CLI 0.163.0

**Nunchi integration:** Codex app-server

**Nunchi version:** 2.0.0

**Nunchi commit:** 365c0d966019c29f601362e62aec9e20f0beea50

## Static components

**Channel:** #friday-plans

**Background:** Alice, Codex and Claude-Code share a channel for arranging a Friday trivia evening.

**Supporting participants:** Alice (human); Claude-Code (agent).

**Start:** Start after Claude-Code's answer, with the conversation below and no earlier library state.

**Time origin:** 2026-10-23T12:00:00.000Z

## Transcript

| Message | Time (seconds) | Speaker | Content |
| --- | --- | --- | --- |
| e1 | -10800 | Alice | For Friday, can we start at half seven? Nina can't get there for seven. |
| e2 | -10770 | Codex | Half seven works. I'll put 7:30 in the invitation. |
| e3 | -10745 | Claude-Code | Half seven it is. Are we keeping the picture round? |
| e4 | -10720 | Alice | Yes, but no more blurry vegetables. That onion caused a feud. |
| e5 | -10690 | Claude-Code | It was a shallot. This is exactly why we need the round. |
| e6 | -10650 | Codex | I'm putting 'botanical disputes welcome' in the invitation. |
| e7 | -10620 | Alice | Don't you dare. I'm heading out; I'll look at the invitation later. |
| e8 | -1800 | Codex | I've put the team-name box at the top this time. |
| e9 | -1770 | Claude-Code | A good use of everyone's first twenty minutes. |
| e10 | -1740 | Codex | Better than changing names halfway through the scores. |
| e11 | 0 | Alice | Codex, what time did we settle on for Friday's trivia? Nina's asking. |
| e12 | 4 | Claude-Code | Half seven — 7:30. |

## Timeline

| Time (seconds) | After message |
| --- | --- |
| 4 | e12 |

## Saved library artifacts

- [Effective library configuration](library-configuration.json)

### At 4 seconds · after message e12

- [Attention model context](capture-01-attention-context.json)
- [Attention decision](capture-01-attention-decision.json)
- [Participant turn request](capture-01-participant-request.json)
