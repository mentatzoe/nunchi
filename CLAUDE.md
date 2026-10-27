# Nunchi Claude guidance

Follow `AGENTS.md`. This file adds only Claude-specific notes.

## Social, not only useful

Nunchi gives agents social activations. It is not "only contribute when you
have something useful": social behavior is interacting socially, not only
contributing or being helpful. The full statement, with examples, is Social
behavior in `AGENTS.md`.

Claude sessions have put the usefulness bar back again and again: in
`docs/behavior.md`'s yardstick, an attention question and a scene's expected
moves. Before you write any of those, check your words against that section.

For scene work, use the [scene spec](docs/evaluations/scene-spec.md) and the
[scene skill](skills/nunchi-scenes/SKILL.md).

## Discuss before writing

Follow "Working with the maintainer" in `AGENTS.md`. Claude sessions have
broken it again and again: drafting specs and requirements, opening issues
and pull requests, and planning builds before the maintainer had decided
anything. When the maintainer wants to discuss, discuss: short messages, one
question at a time, your view with its reasons, no menus to pick from, and
nothing written until it is decided.

## Habits

- If you catch yourself preferring an option because it is smaller or fits
  today's code, check it against the architecture goal and Social behavior in
  `AGENTS.md` first.
- Before asking the maintainer, check what is already decided: lines marked
  agreed or decided, with a date, in `AGENTS.md` and `docs/behavior.md`.
  Anything else in those files is an agent's writing, not a decision.
- Write decisions in plain words, marked agreed with the date. Do not quote
  the maintainer or attribute lines to the maintainer in this repository.
- When briefing subagents, give them the goal of the task, not only the
  mechanism, and point them to `AGENTS.md` instead of restating it.
