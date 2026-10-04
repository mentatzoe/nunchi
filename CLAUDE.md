# Nunchi Claude guidance

Follow `AGENTS.md`. It states the product goal (agents that read the room in a
live, multi-turn conversation) and Zoe's current working decisions. This file
adds only Claude-specific notes.

## Scope

- Default scope: the Claude Code integration and security assurance.
- As of 2026-10-04 Zoe has also directed Claude to make the shared core agent-
  and provider-agnostic ([#85](https://github.com/mentatzoe/nunchi/issues/85))
  and to keep the documentation current.

## Claude Code integration

The integration is a Claude Code mod plus one Python gate per room
([#43](https://github.com/mentatzoe/nunchi/issues/43)):

- The participant is a dedicated Claude Code session per room that uses the
  user's normal configuration, memory, tools, MCP servers, and skills.
- The gate owns transport, observation, attention, scheduling, authority, and
  receipts. The mod starts a turn on `WAKE`, gives the session the only
  room-send tool, and reports how each turn ended.
- Native tools follow the user's Claude Code permission rules, plus an optional
  configured deny list applied when the session starts.
- The earlier headless subprocess runner and channel-plugin designs are
  superseded.

## Habits

- Before changing the core, ask two questions: does this help an agent read
  the room across a multi-turn conversation, and does it stay agent- and
  provider-agnostic?
- When briefing subagents, give them the goal of the task, not only the
  mechanism, and point them to `AGENTS.md` instead of restating it.
- Say plainly when a review is a self-review.

## Commands

```sh
python3 -m unittest
python3 -m evals.verdict_suite.runner --list
```

The core is Python 3.11+ and standard-library only. Live calls need explicit
provider and platform credentials and must record the installed version,
identity, configuration, command, and complete result.
