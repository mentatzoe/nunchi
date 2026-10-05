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
  (`answered-while-composing`, `never-mind-while-composing`).
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
- **ACK** counts as an mhm that Nunchi sent.
- **Wake** or **defer** gives the agent a turn. With `--agent-model`, that
  model plays the turn through the shared participant protocol, and its
  move is graded: a message or reply is speaking, its own reaction is an
  mhm, and silence is staying quiet (which also fits where waiting does).
  Without it, the run counts the moment as "agent decides".

A moment's `during_turn` messages reach the room after the agent's turn
began, so the agent sees them only by looking at the room again; each
record says how many new messages it was shown before posting.

Step 1 is graded on attention alone. Scenes with several participants can
check for collective silence and for pile-ons, where everyone speaks at
once. The `behavior-eval` workflow uses `anthropic/claude-haiku-4.5` as the
agent by default; one fixed agent model keeps differences between runs down
to attention.

Each agent turn records how the agent got it (a wake, or a defer and why)
and whether attention's reading came with it. When the turn protocol rejects
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
- `--ack` says who sends the "mhm". The default, `agent`, matches Nunchi's
  default: an ACK judgment gives the agent a turn, and any "mhm" is its
  own. `--ack nunchi` turns Nunchi's own nod back on, for comparison.

Moments that need a pause, such as "five minutes later, nobody has
answered", have no route in today's V2 and are reported as not supported.

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
that served it). The summary adds a cost and tokens table per model. A call
that failed or timed out reports nothing, so it is not counted. The agent's
calls ask for at most 4096 output tokens; without a cap, OpenRouter reserves
the model's whole output limit against the balance on every call.
