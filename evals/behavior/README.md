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

A scene can also be played as a conversation on Discord, with a director
that posts its people and bots and grades what the agent did with the same
`fitting`, `misses` and `step1` (`evals/rehearsal/directed.py`; see
[`docs/rehearsal.md`](../../docs/rehearsal.md), "Directed scenes"). Eleven
scenes can be played today, on the reference, Claude Code and Codex
columns, offline, with a scripted agent. The director never posts as the
agent, so the agent says the events of its own that a scene holds (a promise, a
nod) itself, as its scripted move on the message they answer, with a cue where
one answers nothing; a message that lands while a turn is under way is posted
into a turn the scripted model holds. `asked-while-busy` is played in another
order than it is written (z1, s1, z2, then the agent's reply, not z1, s1, the
reply, z2), because the thanks must land while the agent is busy; a live model
could drop that reply, so it cannot be assumed there. A scene that needs a pause, a long quiet,
an approval, a snapshot or a second agent cannot be set up. Results there say
"draft expectations", like these. The manual `rehearsal` workflow can also play
them live (`room: discord`, [Live scenes](../../docs/rehearsal.md)): a live agent
behind each column, every grade reported and none a failure, and a scene whose
setup the live agent did not make is reported `precondition not met` and not
graded.

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
- `--agent-posting final-answer` has the agent write its post as a plain
  reply, as an agent does in a harness whose final answer is its post
  (Hermes), instead of one JSON envelope per reply (`envelope`, the
  default). The core `Turn` decides each reply: it is posted, it is silence
  (the `[SILENT]` marker in any case or formatting, such as `**[SILENT]**`,
  at the start of the reply or on a line of its own, or bare after a
  finished sentence at its end), or the agent replies again after looking
  again. This style has no tools, so the agent cannot react or ask
  for more of the room; compare it with the envelope arm on the same
  attention route. In the workflow, the `agent_posting` input sets it, and
  `agent_model: none` grades attention alone. Each record keeps the agent's
  plain replies (`agent.replies`), so a silence can be read too.
- `--agent-posting tools` takes the agent's turn through tools, the way Claude
  Code and Codex take it, so the core's tool-turn wording is measured here
  and not only in live rehearsal. The agent gets exactly the core's tool turn
  and nothing else: its one user message is the turn's text
  (`participant_tool_turn_text`, through `Turn.text`), with no system message,
  and its tools are the room tools the turn offers (`PARTICIPANT_TOOL_SPECS`:
  send, react, quiet and context, and propose and withdraw only on a moment
  whose scene settles an approval), as OpenAI-style function tools in the same
  chat completions request as the other arms. They are named `room_send`,
  `room_react`, `room_quiet` and `room_context`, the names both active
  integrations register them under (Claude Code shows its model a prefix,
  `mcp__nunchi__`, that the eval leaves off). A short loop runs the turn as a
  harness would, at most `TOOL_STEPS` (6) model calls:
  1. The model answers with words, tool calls, or both.
  2. Each tool call goes through the core's own turn (`TurnParticipant` with
     this loop as its driver, so `Turn.call` decides): a reaction that is a
     word, a malformed call (arguments that are not a JSON object), a call to
     a tool the turn does not offer, or a second room action comes back as
     the core's tool error, which the agent reads and may try again. Before
     the first post or reaction the core looks again, and holds it if others
     posted while the agent composed ("Not posted yet", with their messages).
     After each call the core's steering adds what others posted since.
  3. The results go back as tool messages, and the model is called again.
  4. The turn ends at its one room action (a post or a reaction), at the quiet
     tool, or when the model answers with no tool call. The quiet tool and the
     answer with no call are both silence, and the quiet tool's `why` or the
     answer's last words are the reason. A turn that uses all its steps with
     none of the three ends in silence with no reason, and its record says
     `step-bound`.

  The move the room sees is graded exactly as in the other arms. Each record
  keeps the turn under `agent.tool_turn`: how it ended (`action`, `quiet`,
  `no-call`, `step-bound`) and each step's words and calls, with each call's
  tool, arguments, whether the core accepted it, and what the core answered.
  The call that takes the room action is answered "not confirmed yet", because
  the host commits the action after the loop returns; the turn ends there, so
  the model never sees a later answer. The words beside tool calls and the
  last words are never posted, so the leak count's `machinery_written` here is
  each `send` call's text, held or refused ones included. Steering's looks at
  the room are in `agent.expansions` (direction `news`), and count in
  `looked_again`. The summary adds *The tool turn*: per moment, how many turns
  ended at the quiet tool, with a no-call silence, with a reaction, with a post,
  or at the step bound, and how many room tool calls the core refused.
- `--agent-posting tools-coding` is the same turn with a coding harness's
  framing added, **as an approximation**: a short coding-agent system prompt
  (`CODING_SYSTEM_PROMPT`, our own wording, not any vendor's) and two generic
  tools, `shell` and `read_file`, whose every call returns "Not available in
  this evaluation." and lets the turn go on. A real coding harness carries a
  much longer prompt, many more tools and its own conventions for when to ask
  and when to run something, so this arm shows whether the core's wording
  survives a coding agent's framing, not what Claude Code or Codex do. Compare
  it with `tools` on the same attention route and agent model.

The grade covers the move, not its words. The summary also counts leaks: the
room should receive only what the library committed, and nothing that names
Nunchi's machinery. The core's `nunchi.turn.machinery_in` decides what does,
the same check the conformance kit uses: a wake marker, the turn's tag
(`<nunchi_participant_turn_v1>`), a Nunchi tool's name (`mcp__nunchi…`, and
the names the turn gave its tools, `room_send` and the rest, in the tool arms
only), thinking tags (`<think>`, `<thinking>`, `<reasoning>`, `<thought>`, in lowercase) outside
code that mark thinking (an opening tag with its closing tag, or a tag alone
on its line; balanced ``` or ~~~ fences and inline `code` are removed
first, with a simple regex; "What does <thinking> do?" in prose is not
counted), the `[SILENT]` marker, the turn's field names that only
Nunchi uses (`own_moves`, `trigger_event_id`) or a path to an object's own
field (`attention.advice`, `binding.request_id`), and the turn's request
id. Prose about Nunchi, the words "attention model", field names other APIs
use on their own (`request_id`, `event_id`) and dotted words that are no
object's field (`memory.text`) are not counted. It counts two things apart:

- `agent.machinery_written`: what the model wrote for the room in the turn,
  before the library's commit: each envelope's message text, each plain
  reply meant as a post, or each `send` call's text in the tool arms. In
  final-answer posting a reply the library reads as silence is not counted,
  since nothing of it would be posted (a taught `[SILENT]` is not a leak), and
  the `<thinking>` block the turn teaches is the agent's private place, read
  as the turn reads it (`<thinking>(.*?)(?:</thinking>|\Z)`, any case).
- `agent.machinery_posted`: what the committed post carried into the room.

The library takes each wake marker out of a post, and in final-answer
posting also the taught `<thinking>` block, so these count as written and
not posted. In final-answer posting a bare marker after a finished sentence
is silence. In the envelope arm a marker after a sentence ("On it.
[SILENT]") is posted as written, and counts as both. The rest is posted as
written: another thinking tag such as `<think>` (the model's native
reasoning is the harness's to strip, Zoe's decision, and the eval has no
harness), a field name, or the turn's tag (whether the library refuses a
post that quotes it is still open, D6).

Leak counts from runs before 2026-10-08 (for example run 58's "18 of 111
posts") are not comparable with these: they used another pattern, counted
posts and not turns, and had no written/posted split. To compare, re-score
the stored posts with `posted_machinery` from `evals/behavior/run.py`.

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
| Which model should answer steps 1 and 2? | `--agent-model` empty (`none` in the workflow): attention alone, graded on step 1 and on each route's own top move | $2 |
| Did a change to the agent's turn help? | `--agent-model anthropic/claude-haiku-4.5` | $9 |
| Did a change to the reading help? | the same agent, with `--paired` | $16 |
| Does the core's tool-turn wording make the agent nod, stay quiet or promise? | one attention route, the same agent, `--agent-posting tools`, targeted scenes and 10 runs | $2 (an estimate, below) |
| Does that wording hold under a coding agent's framing? | the same, `--agent-posting tools-coding` | $2 to $3 (an estimate) |

The agent's turns cost the most: a Haiku turn costs several times an
attention call, and `--paired` plays each turn twice. Since step 5b each
moment also replays its earlier messages through attention, which roughly
doubles the attention calls; these figures predate that.

The two `--agent-posting tools` rows are an estimate, not a measurement. A tool
turn is one to three model calls, not one. Take the per-call figures the
rehearsal assumes (`evals/rehearsal/spend.py`: $0.002 an attention call, $0.01
an agent call of about 5,000 tokens in at Haiku's list price; the tool
definitions and the later steps' history are inside that round-up). For
`story-across-messages` and `said-it-would-check`, 10 runs each, with the
replay counted, that is 160 attention calls and at most 90 agent turns of about
two calls each: about $0.3 for attention and $1.8 for the agent. The cost
multiplies with the number of routes in `--models`, so give a targeted run one:

```sh
NUNCHI_OPENROUTER=... python3 -m evals.behavior.run \
  --models anthropic/claude-haiku-4.5 --runs 10 \
  --scenes story-across-messages,said-it-would-check \
  --agent-model anthropic/claude-haiku-4.5 --agent-posting tools
```

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
- which move fits: speak, mhm, wait, or stay quiet.

Chat models answer them as one JSON object through the OpenAI-compatible
endpoint. Models named `typesafe/...` (for example `typesafe/jev-1.13`) are
typed decision models: they go through OpenRouter's Decisions API
(`src/nunchi/adapters/decisions_api.py`, `--jev-url`) and answer with
probabilities, never text. A chat model's name may start with `messages:` or
`responses:` to send its attention through the Messages API or the Responses
API instead of chat completions (`src/nunchi/adapters/model_apis.py`; #94
step 8), for example `responses:openai/gpt-6-luna@low` or
`messages:anthropic/claude-haiku-4.5`. On OpenRouter both go to the same base
URL. The core decides from the answers on every route, so a run compares the
routes on the same scenes. Each record keeps the
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
