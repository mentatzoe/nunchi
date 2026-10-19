# Scene spec

**Status:** agreed, 2026-10-19. It replaces the earlier scene format. The
existing scenes ([#136](https://github.com/mentatzoe/nunchi/issues/136)) have
not yet been reviewed against it.

## Purpose

Scenes are behavioral evaluations of social situations, repeatable as far as
live models allow. Each scene shows, through behavior, whether the Nunchi
library acts as it should and gives the agent the social context it should.

## Goals

- Flag regressions, and capture new regression tests.
- Catch the library's implementation compressing the intended social
  behavior until it is no longer understood. One recurring example: a
  library meant for social behavior that collapses into "only contribute
  when you have something important to contribute".
- Keep scenes from compressing that intent themselves, as fixed lists of
  expected moves did in earlier scenes.

The intended social behavior is described at the top of
[`AGENTS.md`](../../AGENTS.md#social-behavior-in-zoes-words).

## Structure

A scene has four parts.

1. **Description:** a short account of the scene.
2. **Static components**, the same on every run:
   - supporting participants;
   - transcript / history;
   - timeline: key points in time for the scene, and previous library
     packages if the scene does not start cold;
   - background: any context that would be part of the scene if it happened
     live, such as the room description;
   - library configuration, such as the attention model, window size and
     profile.
3. **Dynamic components**, what is under test:
   - the active participant, in the form closest to its production form;
   - a version of the library, frozen or packaged.
4. **Purpose**, what is being judged:
   - expected and acceptable outcomes;
   - undesirable outcomes.

## Not part of a scene

- Scoring and running belong to the evaluation design. An outcome a scene
  names holds whether the scene runs once or a hundred times.
- A scene has no rubric. Its outcomes are what it is judged against; how to
  judge them is part of the evaluation design.

## Conventions

People are named Alice, Bob, Carol and so on. Agents are named after their
harness: Claude-Code, Codex, Hermes.

## Open questions

- Whether checking that facts reach the agent belongs in ordinary tests
  rather than in scenes.
