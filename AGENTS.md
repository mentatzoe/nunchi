# TurnAware Agent Guidelines

This repository builds TurnAware: a portable pre-reply admission gate for
turn-aware agents.

## Source of truth

Read these before substantive work:

1. `.specify/memory/constitution.md`
2. this file
3. the active SpecKit feature directory under `specs/`, when one exists

<!-- SPECKIT START -->
For the active bounded feature, read `specs/002-admission-classifier/plan.md` for
technologies, project structure, shell commands, and implementation constraints.
<!-- SPECKIT END -->

## Product boundary

TurnAware decides admission, not reply composition.

The core verdicts are exactly:

- `PASS`
- `ACK`
- `ASK`
- `SPEAK`

`PASS` is a hard stop: no ordinary user-visible room message may be emitted.
Telemetry belongs outside the conversation surface.

## SpecKit workflow

Use the full production gate path unless the project owner explicitly authorizes a spike:

```text
/speckit-constitution -> /speckit-specify -> /speckit-clarify ->
/speckit-plan -> /speckit-checklist -> /speckit-tasks ->
/speckit-analyze -> /speckit-implement
```

For Codex, invoke SpecKit skills through the installed `.agents/skills` skill
surface. For Claude, use the installed `.claude/skills` skill surface.

Each bounded spec has one accountable owner end-to-end. Reviewers may challenge
or red-team, but they do not silently co-own the same spec context.

## Execution hygiene

- Use isolated git worktrees under `.worktrees/<slug>` for non-trivial branch
  work after the initial bootstrap.
- Keep the main checkout on `main`.
- Do not implement adapters before the core CLI contract is usable.
- Do not treat schemas, fixtures, or docs as a completed product unless a
  runnable CLI verdict path exists.
- Pass explicit high-effort runtime flags when required:
  - Codex: `-c model_reasoning_effort=xhigh`
  - Claude Code: `--effort xhigh`

## Definition of done

A product claim is done only when it is verified by commands, tests, fixtures, or
runnable examples committed in the repo. Documentation is product and must stay
truthful about implemented vs planned capabilities.
