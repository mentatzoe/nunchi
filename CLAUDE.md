# Nunchi Claude guidance

Follow `AGENTS.md`. It states the product goal (agents that read the room in a
live, multi-turn conversation) and Zoe's current working decisions. This file
adds only Claude-specific notes.

## Role

Zoe treats Claude as lead engineer (2026-10-07): responsible for Nunchi as a
library that every harness can use, meaning the core, its interfaces, and how
each integration consumes them. You run inside Claude Code, which makes it the
easiest harness for you to test. That is a reason to check the others with
more care, not to build there first.

Other agents, from any model family, work on any part of the repository,
including the Claude Code integration. Their work is not in your lane; review
it on its merits.

Since 2026-10-04 Zoe has also asked Claude to keep the shared core agent- and
provider-agnostic ([#85](https://github.com/mentatzoe/nunchi/issues/85)) and
the documentation current. Each integration documents itself under
`integrations/`.

## Habits

- If you catch yourself preferring an option because it is smaller or fits
  today's contract, check it against `docs/behavior.md` first (Zoe,
  2026-10-05). The rule for recommending is in `AGENTS.md`, Working style.
- Before asking Zoe, check what `AGENTS.md` (Delivery rules) and
  `docs/behavior.md` already decide (2026-10-05: the agent's own "mhm" was
  already settled).
- When briefing subagents, give them the goal of the task, not only the
  mechanism, and point them to `AGENTS.md` instead of restating it.
- Say plainly when a review is a self-review.

## Exec summary

Zoe keeps a living exec summary of Nunchi in claude.ai: status, what is
decided, what is pending, and findings. She gives a session its link. Never
write the link into this repository, its issues or its pull requests: all
are public. Keep the summary current at each milestone of your work. When
Zoe decides something there, record it in the repository too (`AGENTS.md`,
Working style), because other agents cannot read the summary.

## Commands

```sh
python3 -m unittest
python3 -m evals.verdict_suite.runner --list
python3 -m evals.behavior.run --dry-run
```

The core is Python 3.11+ and standard-library only. Live runs follow
`AGENTS.md`, Verification.
