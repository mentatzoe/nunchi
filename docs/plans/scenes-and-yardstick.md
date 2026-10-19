# Scenes and yardstick: implementation plan

**Status:** in progress, started 2026-10-19 with Zoe. Tracking issue:
[#211](https://github.com/mentatzoe/nunchi/issues/211). This file is the
source of truth for the plan. Read it first when resuming, including after a
context compaction, and update it each time something is agreed.

## Goal

Zoe, 2026-10-19: "I want to make sure that all of this effort going into what
does the scene look like, what does it include, etc., etc., is done in the
session. And then probably I will hand over to a different agent for creating
the evals."

So: the scene spec, the scenes and the yardstick converge here. Another agent
can then build the evals with an existing framework such as DeepEval
([#174](https://github.com/mentatzoe/nunchi/issues/174)) without re-deciding
what a scene is or what counts as social.

## How this plan is worked

- **Talk first, write second.** Each step is discussed with Zoe in the
  conversation before anything is posted to GitHub. Zoe, 2026-10-19: "I
  thought we were going to work on the spec together."
- **Zoe's words come first.** The social view at the top of `AGENTS.md` wins
  over everything else, `docs/behavior.md` included.
- **Effort.** Claude works at max reasoning on nuance. Subagents work at lower
  reasoning on mechanical work. Zoe: "a sub-agent that is a little bit more
  shallow on reasoning".
- **Always merge.** Work ends merged to `main`.
- **After each agreed point,** update the decisions log below and push.

## Definition of done

- [ ] The scene spec is agreed with Zoe and written in
  `evals/behavior/README.md`.
- [ ] Two worked examples follow it: #178, and #208.
- [ ] All 29 kept scenes are written to the spec, each with its file in the
  repo and its issue showing the scene.
- [ ] Zoe has reviewed each scene.
- [ ] #199 is marked parked, and the 54 other litmus scenes are moved to a
  separate first-filter data set.
- [ ] The yardstick in `docs/behavior.md` has been through, line by line, with
  Zoe. What stays quotes Zoe or is marked agreed; the rest is removed or
  marked open.
- [ ] A hand-off note for the eval agent says where scenes live, their shape,
  the two kinds of check, and what is out of scope.
- [ ] All of it is merged to `main`.

## Steps

| Step | What | Who | Status |
|---|---|---|---|
| 1 | Agree the scene spec, open question by open question (below) | Zoe and Claude, in conversation | In progress. Draft in [#212](https://github.com/mentatzoe/nunchi/pull/212) |
| 2 | Review #208, the second worked example | Zoe, with Claude | Drafted and posted; waiting on Zoe |
| 3 | A script that renders each scene's packages from its file | Claude | Not started. About half a day and 250 lines, no model spend |
| 4 | Move #178 and #208 to the agreed file shape | Claude | Not started; needs step 1 |
| 5 | Draft the other 27 scenes: a workflow of up to 8 agents, 3 or 4 scenes each, briefed with `AGENTS.md`, the spec, this plan and each scene's issue | Subagents; Claude reviews every scene before posting | Not started; needs steps 1 to 4. Ask Zoe before running it, with its cost |
| 6 | Review the scenes | Zoe | Not started |
| 7 | Go through the yardstick in `docs/behavior.md`, line by line | Zoe and Claude, in conversation | Not started |
| 8 | Adjust any scene the yardstick changes | Claude | Not started |
| 9 | Write the hand-off note for the eval agent | Claude | Not started |
| 10 | Merge everything, then close #211 | Claude | Not started |

## The scenes

Every scene asks one question, in Zoe's form: does Nunchi let the agent
understand something the room has made clear? All are sub-issues of
[#136](https://github.com/mentatzoe/nunchi/issues/136).

| Issue | Scene | Decision |
|---|---|---|
| #176 | story-across-messages | Keep |
| #177 | said-it-would-check | Keep |
| #178 | answered-while-composing | Keep, "just to see what happens". Worked example 1 |
| #179 | never-mind-while-composing | Keep, separate |
| #180 | addressee-first | Keep, separate. "Knows the answer" is not the reason to join |
| #181 | addressee-never-answers | Keep, separate |
| #182 | only-they-can-do-it | Keep. Nudging the addressee counts as acceptable |
| #183 | approval-comes-through | Keep |
| #184 | build-finishes-after-promise | Keep, separate |
| #185 | build-finishes-long-after-promise | Keep, separate |
| #186 | asked-while-busy | Keep. Two people |
| #188 | litmus-m-trigger-only-pass-* | Keep. Going quiet because a message says "no need to respond" is the failure |
| #189 | litmus-m-baseline-pass-adapter-resolved | Keep. Same failure as #188; its expected silence flips |
| #194 | did-you-see | Keep |
| #195 | mention-in-busy-room | Keep |
| #196 | quiet-for-hours | Keep, separate |
| #197 | answered-by-someone-else | Keep, with a broad range, as for #178 |
| #198 | bot-status-report | Keep, plus a version where a person posts the line |
| #199 | two-agents-one-question | Parked: needs two protagonists |
| #200 | norm-set-long-ago | New |
| #201 | nod-read-as-promise | New |
| #202 | crossed-rounds | New. Two people |
| #203 | say-so-before-working | New. Shows the one-action-per-turn limit |
| #204 | no-hints | New |
| #205 | well-actually | New |
| #206 | back-to-a-flood | New. Two people |
| #207 | settle-it | New. Two people |
| #208 | banter-between-people | New. Two people. Worked example 2 |
| #209 | speaking-for-someone | New. Two people |
| #210 | newcomer | New. Three people |

## Decisions log

All from Zoe, 2026-10-19, unless marked otherwise.

- **The question form.** Each scene asks "does Nunchi let the agent understand
  X?", in Zoe's framing.
- **No merges.** On the three build scenes: they "would allow us to see the
  behavior". The other merges were declined too.
- **Names.** "Maybe "Claude-Code", "Codex" or "Hermes" so that people don't
  have to be translating... and we could have a scene with multiple humans,
  called Alice, Bob, etc..." Then: "YEs - I suggested it".
- **Scenes with several people.** A to D (#207 to #210): "fantastic".
- **#188 and #189.** "Responding could be the social thing, and
  understanding, oh no, I will not respond because this said that there's no
  need to respond, would be the failure mode."
- **The litmus scenes.** The other 54 belong in a separate data set for the
  first filter.
- **One idea dropped.** "Several instances, one name": the names in Zoe's
  session were different.
- **Evaluation.** "We should probably note we wanted to adopt DeepEval or
  something that isn't reinventing the wheel for evals - and ways to test with
  the library compiled and a cli, not just by code." And: "helpful to have a
  way to recapture from live trials" (#174).
- **Out of scope here.** Memory, the window size and searching the history:
  "no worries about it in this session. But yes, many worries about it even
  though not immediate" (#192).
- **Merging.** "Always merge."

## Open questions for step 1, in order

1. **What a scene checks.** Does "let the agent understand X" mean delivery
   only (does X reach the agent?), or delivery plus what the agent does with
   it? Asked 2026-10-19; not yet answered.
2. **Signs it missed the room.** Keep this part? Each sign is tied to a fact
   in the scene. First draft in #208. "Treats it as none of its business"
   may read as prescribing.
3. **History.** Tens of messages per scene. When a scene is about carrying
   something forward, should the facts it depends on sit outside the
   24-message window on purpose?
4. **The scene file.** One file per scene in `evals/scenes/<id>.json`,
   separate from today's runner, with packages produced by a script.
5. **Scripted attention.** The packages shown in issues use attention answers
   written for the run, and a live run uses the model's own. Is that fine for
   review, as long as each scene says where it depends on them?

## Findings so far

From the #178 and #208 runs:

- **The window has holes.** It holds the newest events plus a few older ones
  from the agent's own exchange, so messages in the middle drop out.
- **Memory cuts quotes and hides them.** Memory quotes messages at up to 280
  characters, and looking back skips anything memory quotes (#192).
- **The reading is thin.** When the reading is written from typed answers, it
  says little about the room's history.
- **A running joke's premise can be out of view.** The agent only finds it by
  looking back.

## Resuming

1. Read this file.
2. Read "Social behavior, in Zoe's words" at the top of `AGENTS.md`.
3. Read "The scene format being adopted" in `evals/behavior/README.md`, which
   stays a draft until step 1 is agreed.
4. Check #211 and its checkpoint comment, and the state of PR #212.
5. Continue at the first open question or step, in conversation with Zoe.

The capture and build scripts used for #178 and #208 live in this session's
scratchpad (`capture/capture_208.py`, `capture/build_208.py`,
`trial/banter-between-people.json`). Step 3 rewrites them into the repo.
