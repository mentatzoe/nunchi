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

The moves are `stay_quiet`, `mhm`, `wait`, `ask`, and `contribute`. Fitting
is a range, not one right answer. A move that is neither fitting nor a miss
is reported as unlisted, for review rather than as a failure. The full file
format is in `scene.py`.

## Reviewing the drafts

Every scene starts as a draft (`"review": "draft: …"`):

- `scenes/behavior/` holds the eight scenes from `docs/behavior.md`.
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

The key is never written. The manual `behavior-eval` GitHub workflow runs
the same command with the `NUNCHI_OPENROUTER` repository secret.

## What today's V2 can show

Today's V2 makes one attention decision per moment:

- **Suppress** counts as staying quiet.
- **ACK** counts as an mhm that Nunchi sent.
- **Wake** or **defer** means the agent decides. Its own move is not
  simulated yet.

Moments that need a pause, such as "five minutes later, nobody has
answered", have no route in today's V2 and are reported as not supported.
