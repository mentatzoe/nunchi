# Nunchi

Nunchi (눈치) is a library intended to help existing AI agents read the room
and take part in group conversations. Social participation includes listening,
reacting, joking, disagreeing and staying silent; it does not have to be useful
or productive.

> **Redesign in progress. No agent harness integrations are currently
> supplied.** The Claude Code, Codex and Hermes integrations were
> removed because they took control of agents' turns or lifecycle. Keeping
> them available would present the wrong architecture as a usable integration.
> Their code remains in Git history.

## The goal and the remaining gap

Core holds room context and history, makes attention and social judgments,
and exposes configurable APIs and tools. Harnesses own agent startup,
lifecycle and turns. Agents control their actions and communication. Users
choose their channels. The [agreed architecture goal](AGENTS.md#architecture-goal-and-current-gap)
is the starting point for the redesign.

Removing the integrations does not complete that goal. Shared code still
hosts participant turns, controls sending and limits each turn to one room
action. Context create/read/update/delete APIs and prompt configuration are
incomplete. The replacement design must address these gaps before new harness
integrations are built.

## What remains available

- Context storage, observation, attention models, provider adapters, data
  validation and authorization code, all subject to the redesign.
- Optional JSONL, Discord, Matrix and Telegram [reference adapters](docs/adapters.md).
  These run a plain model participant. They do not connect Nunchi to an
  existing agent harness.
- A shared [Discord MCP transport](integrations/mcp-discord/README.md).
- Configuration, diagnostics, a local dashboard and service tools for the
  existing runtime.
- Deterministic tests and evaluation tooling. The [approved social scenes](docs/evaluations/scenes/README.md)
  are specifications and preparation artifacts; they have not been executed
  or scored as a collection.

The implementation is incomplete and has no current end-to-end proof of the
intended library architecture. Check [CI](https://github.com/mentatzoe/nunchi/actions/workflows/ci.yml)
for a revision's test results. A passing test or package build does not establish
that an agent reads a live room well.

## Install and inspect

```sh
python3 -m venv .venv
.venv/bin/python -m pip install '.[test]'
.venv/bin/nunchi probe
.venv/bin/nunchi-install probe
```

See [installation and configuration](docs/INSTALL.md) for the existing runtime
and [command compatibility](docs/STABILITY.md) for its interfaces. Installing
the package does not add Nunchi to Claude Code, Codex or Hermes.

## Check the implementation

```sh
.venv/bin/python -m unittest
.venv/bin/python -m evals.verdict_suite.runner --list
.venv/bin/python -m evals.verdict_suite.runner
```

CI checks retained core and channel functions, data contracts and packaging.
The old conversation rehearsals and behavior runner have been removed.
Realistic evaluation with pinned library releases and real agent integrations
remains a separate design task. The approved scenes have not been executed.

## Read next

- [Architecture goal, social behavior and decisions](AGENTS.md)
- [Behavior draft](docs/behavior.md)
- [Data contracts](docs/contracts/nunchi.md)
- [Current runtime components](docs/platform.md)
- [Reference adapters and their limits](docs/adapters.md)
- [Privileged-action authorization](docs/security/privileged-action-authorization.md)
- [Scene specification](docs/evaluations/scene-spec.md) and [evaluation handoff](docs/evaluations/eval-design-handoff.md)
