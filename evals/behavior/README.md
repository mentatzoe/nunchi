# Behavior scenes

These scenes check whether a participant reads the room, as defined in
[`docs/behavior.md`](../../docs/behavior.md). Each scene is a short
conversation plus the moments to judge in it.

## What a scene says

For each moment, a scene names:

- **what to notice**: facts with pointers to the messages they come from;
- **fitting moves**: the moves a socially aware participant might make here;
- **clear misses**: moves that go wrong, each with a reason;
- **step 1**: whether the conservative first step must `pass` the moment,
  may `suppress` it, or `either`.

The moves are `stay_quiet`, `mhm`, `wait`, and `speak`. Speaking covers
anything said to the room: an answer, a question, an opinion. Fitting
is a range, not one right answer. A move that is neither fitting nor a miss
is reported as unlisted, for review rather than as a failure. The full file
format is in `scene.py`.

## Reviewing the drafts

Every scene starts as a draft (`"review": "draft: …"`):

- `scenes/behavior/` holds the eight scenes from `docs/behavior.md`, plus
  two where a message arrives while the agent is composing
  (`answered-while-composing`, `never-mind-while-composing`), and two where
  the agent's own earlier turn in the scene matters
  (`addressee-never-answers`, `said-it-would-check`), one where looking
  again after a pause should still stay quiet (`only-they-can-do-it`), and
  one where an approval comes through after the agent said it would report
  back (`approval-comes-through`), and two where a CI line arrives that the
  agent promised to report on: while the promise is in attention's window
  (`build-finishes-after-promise`) and after it left
  (`build-finishes-long-after-promise`), and one where a question arrives
  while the agent is answering someone else (`asked-while-busy`).
- `scenes/litmus/` holds 57 scenes converted from the V1 litmus corpus by
  `litmus.py`. Their ranges come from V1 verdicts, and their `review` field
  quotes the V1 rationale. They have no notice facts yet.

To review a scene, check its fitting moves and misses against how a socially
aware person would act, add notice facts where they help, and set `review` to
something like `"reviewed by Zoe, 2026-10-05"`. The converter never
overwrites an existing scene unless run with `--force`.

## Running

```sh
python3 -m evals.behavior.run --list
python3 -m evals.behavior.run --dry-run
NUNCHI_OPENROUTER=... python3 -m evals.behavior.run --models google/gemini-3.8-flash --runs 3
```

`--dry-run` uses an offline model that always wakes, to check the plumbing.
A live run sends each moment through the production observation and
attention path to each model, then writes three files to `--out`:

- `results.jsonl`: every call;
- `summary.md`: per-model counts, a table of moments, and the clear misses;
- `run.json`: the commit, Nunchi version, models, settings, and command.

The key is never written. If any call fails, the summary lists the errors
first and the run exits non-zero, because a failed call would otherwise
count as a woken agent. When a model answers but its reply is rejected,
`results.jsonl` keeps the reply and the reason. `--per-model` (default 3)
caps how many calls go to one model at once, to stay under rate limits. The manual `behavior-eval` GitHub workflow runs
the same command with the `NUNCHI_OPENROUTER` repository secret.

## What a run grades

Each moment runs through Nunchi's own pipeline: observation, attention, the
participant host and the transport.

- **Suppress** counts as staying quiet, decided by attention.
- **Wake** or **defer** gives the agent a turn. With `--agent-model`, that
  model plays the turn through the shared participant protocol, and its
  move is graded: a message or reply is speaking, its own reaction is an
  mhm, and silence is staying quiet (which also fits where waiting does).
  Without it, the run counts the moment as "agent decides".

A moment's `during_turn` messages reach the room after the agent's turn
began, so the agent sees them only by looking at the room again; each
record says how many new messages it was shown before posting.

A moment's `unattended` messages arrived earlier, while the agent was busy
with its previous turn. The suite hands them, and the judged message, to
Nunchi while a stand-in turn runs, then ends that turn, as the scheduler
would live. So the judged message comes as the newest of them, Nunchi judges
them for the memory first, and the judgment and the turn read them with it
as one moment.

Live, attention judges each message as it arrives, and the participant's
memory of who asked what is built from those judgments. So before a moment
is judged, attention first judges each earlier message the participant
would have judged live (messages by others, in order), with the same model.
These replayed judgments only feed the memory: no turn follows them, and
they are not graded. With an agent, an earlier moment of the same scene is
played in full instead: the agent takes that turn, anything it posts enters
the room as its own message or reaction, and its silences and the reasons it
gave stay in its memory, as they would live. Only the judged moment is
graded. Each record's `memory_replay` says how many messages were judged,
how many failed, their usage, and each played turn's move and reason, with
the agent's usage for them. `--no-replay` skips all of it, to measure what
the memory changes.

Step 1 is graded on attention alone, and so is attention's own most likely
move: each record's `top_move` grades it as if the agent followed it, with
waiting graded like staying quiet, and the summary's *Top move fits / miss*
column counts them. That compares how well each model reads the moment
without paying for an agent. Scenes with several participants can
check for collective silence and for pile-ons, where everyone speaks at
once. The `behavior-eval` workflow uses `anthropic/claude-haiku-4.5` as the
agent by default; one fixed agent model keeps differences between runs down
to attention.

Each agent turn records how the agent got it (a wake, or a defer and why),
whether attention's reading came with it, which of its own earlier moves
its memory carried (`memory_moves`) with the reasons it had given
(`memory_reasons`), which threads it carried, each with the messages that
responded (`memory_threads`), and the reason it gave for this move (`why`). When the turn protocol rejects
the agent's reply, the record keeps that reply under `raw_reply`, so the
failure can be read. Two options measure the
agent's side of the room:

- `--paired` plays every turn that carried a reading a second time, on the
  same wake without the reading, with its own fresh view of the room. That
  second move is graded but never sent, so the summary shows what the
  reading changed at the same moment.
- `--reading-items` and `--reading-chars` set how long a reading attention
  is asked for: at most 4 notes of at most 400 characters by default, and
  `--reading-items 0` asks for none. Shorter readings answer faster; the
  paired arm shows what each length changes.

A pause moment, such as "five minutes later, nobody has answered", plays
the scene through the message before the pause as it happened live: that
message is judged, and with an agent its turn is played. The scene clock
then moves on by the pause, and Nunchi looks again (#94 step 6). It looks
again only when that judgment's most likely move was to wait and the agent
did not post; otherwise the record counts as staying quiet, and step 1,
which never ran, is graded `not judged`. Each pause record's
`looked_again` says whether it did, and its `detail` says why not; a turn
from a look again carries `occasion: "pause"`.

A pause moment with an `outcome` is the turn an approved action starts when
it settles after the pause (Zoe, #90 decision 2 on #94). The scene's own
events say the agent asked for approval; a scripted proposal stands in for
the authorization coordinator, shows it awaiting approval in the agent's
memory, and settles as the moment says. The agent then gets its outcome
turn, which carries `occasion: "outcome"`, and its move is graded. Each
such record has `outcome_turn`. The grade covers the move only: whether the
agent's words match how the action ended has to be read from the record's
text.

## Which run to use

Each run answers one kind of question. Pick the cheapest one that answers
it. Costs are what the providers reported for eight attention routes over
all scenes, three runs each, with Haiku as the agent (run 21, 2026-10-06:
$1.92 for attention, $7.03 for the agent's turns, $6.60 for the paired
play).

| Question | Settings | About |
|---|---|---|
| Which model should answer steps 1 and 2? | `--agent-model` empty: attention alone, graded on step 1 and on each route's own top move | $2 |
| Did a change to the agent's turn help? | `--agent-model anthropic/claude-haiku-4.5` | $9 |
| Did a change to the reading help? | the same agent, with `--paired` | $16 |

The agent's turns cost the most: a Haiku turn costs several times an
attention call, and `--paired` plays each turn twice. Since step 5b each
moment also replays its earlier messages through attention, which roughly
doubles the attention calls; these figures predate that.

**The implementation baseline keeps one agent.** Every run that judges a
step of the plan on [#94](https://github.com/mentatzoe/nunchi/issues/94)
uses `anthropic/claude-haiku-4.5` as the agent, at least through step 5, so
before and after compare the same agent. The agent's own moves already vary
from run to run (23% of moments woken in more than one run got different
moves across runs), so a second change would hide the step's effect.
Comparing other agent families, and the real agents on their own quota, is a
separate refinement track
([#116](https://github.com/mentatzoe/nunchi/issues/116)) whose results don't
gate a step.

## Two routes for attention

Every attention model answers the same typed questions about the judged
message (`src/nunchi/attention_questions.py`):

- is it conversation (step 1);
- who is it addressed to;
- has someone already answered it, and with which message;
- is the author mid-thought;
- does the participant have something to add;
- which move fits: speak, mhm, wait, or stay quiet.

Chat models answer them as one JSON object through the OpenAI-compatible
endpoint. Models named `typesafe/...` (for example `typesafe/jev-1.13`) are
typed decision models: they go through OpenRouter's Decisions API
(`src/nunchi/adapters/decisions_api.py`, `--jev-url`) and answer with
probabilities, never text. The core decides from the answers either way, so
a run compares the two routes on the same scenes. Each record keeps the
answers under `decision.answers`, and a typed model's full response and the
snapshot that served it under `model_response`.

## Reasoning effort, tokens and cost

A chat model's name may end in `@` and a reasoning effort (`none`,
`minimal`, `low`, `medium`, `high`, `xhigh` or `max`), for example
`deepseek/deepseek-v4.1-flash@low`. On OpenRouter it is sent as
`reasoning.effort`, elsewhere as `reasoning_effort`. `@off` turns reasoning
off (`reasoning.enabled: false`), for models that take only on/off or a token
budget, such as Qwen3.8 Flash, which ignored `@low` in run 20. Without one, the
provider's default applies, and several models reason by default: OpenRouter
lists DeepSeek V4.1 Flash at `high` and GLM 5.3 Flash at `max`. Listing a
model with and without an effort compares them in one run; tables show the
name as given. Which efforts a model accepts is the provider's to say, and a
refused effort fails that model's calls.

On OpenRouter every call asks for its cost. Each record keeps what the
provider reported: `attention_usage` for the attention call, and
`agent.usage` and `agent.without_reading.usage` for the agent's real and
paired plays (tokens in and out, reasoning tokens, cost, and the provider
that served it), and `memory_replay.usage` for the replayed judgments. The
summary adds a cost and tokens table per model, with the replay in its own
column. A call
that failed or timed out reports nothing, so it is not counted. The agent's
calls ask for at most 4096 output tokens; without a cap, OpenRouter reserves
the model's whole output limit against the balance on every call.
