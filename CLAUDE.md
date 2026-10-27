# Nunchi Claude guidance

Follow `AGENTS.md`. It states the product goal (agents that read the room in a
live, multi-turn conversation) and the current working decisions. This file
adds only Claude-specific notes.

## Social, not only useful

Nunchi gives agents social activations. It is not "only contribute when you
have something useful": social behavior is interacting socially, not only
contributing or being helpful. The full statement, with examples, is Social
behavior at the top of `AGENTS.md`.

Claude sessions have put the usefulness bar back again and again: in
`docs/behavior.md`'s yardstick, an attention question and a scene's expected
moves. Before you write any of those, check your words against that section.

Use the [draft-status guidance](AGENTS.md#draft-status) when reading
`docs/behavior.md` or other proposed designs.

The [approved scene specifications](docs/evaluations/scenes/README.md) follow
the [scene spec](docs/evaluations/scene-spec.md). Use the
[scene skill](skills/nunchi-scenes/SKILL.md) for scene work. Older fixtures'
expected moves and review labels do not define these scenes' purposes or
approval. Saved library packages record preparation; running and scoring the
approved collection are separate evaluation-design work.

## Discuss before writing

Follow "Working with the maintainer" in `AGENTS.md`. Claude sessions have
broken it again and again: drafting specs and requirements, opening issues
and pull requests, and planning builds before the maintainer had decided
anything. When the maintainer wants to discuss, discuss: short messages, one
question at a time, your view with its reasons, no menus to pick from, and
nothing written until it is decided.

## Ownership

Follow the ownership and architecture goal in `AGENTS.md`. Work is not divided
by model family or harness. Review other agents' work on its merits and check
every affected integration, not only the harness you run in.

## Habits

- If you catch yourself preferring an option because it is smaller or fits
  today's contract, check it against Social behavior at the top of
  `AGENTS.md` first. The rule for recommending is in `AGENTS.md`, Working
  style.
- Before asking the maintainer, check what is already decided: lines marked agreed or
  decided, with a date, in `AGENTS.md` and `docs/behavior.md`. Anything else
  in those files is an agent's writing, not a decision.
- Write decisions in plain words, marked agreed with the date. Do not quote
  the maintainer or attribute lines to the maintainer in this repository.
- When briefing subagents, give them the goal of the task, not only the
  mechanism, and point them to `AGENTS.md` instead of restating it.
- Say plainly when a review is a self-review.
- Follow the requested review boundary. A PR requested for maintainer review
  stays open; do not merge it automatically.

## Commands

```sh
python3 -m unittest
python3 -m evals.verdict_suite.runner --list
```

The core is Python 3.11+ and standard-library only. Live runs follow
`AGENTS.md`, Verification.
