"""Rehearsals: a live model in each real harness, taking part in a room through Nunchi (#94 step 9f).

The probe (`probe.py`) is the first rehearsal. For each harness it runs two
moments of a room against a live model reached through OpenRouter, on a
clean, pinned install, and records the run as AGENTS.md asks: what was
installed, who the participant was, how everything was configured, the exact
commands, and the complete result. ``--scripted`` runs the same probe offline
against scripted model endpoints, for CI.

- `routes.py`: each harness's model route and keys, by variable name.
- `standin.py`: the in-process stand-ins for the room's transport and the
  scripted model endpoints.
- `record.py`: the run record and the harnesses' own transcripts.
- `scan.py`: the key and canary scan over every output file.
- `spend.py`: the spend watchdog on the OpenRouter key.
- `checks.py`: the hard checks, and what is reported but not judged.
- `fake_discord/`: a Discord stand-in for the production Discord clients
  (PR 3a).
- `discord_net.py`: the launcher that leads Discord's names to the stand-in
  in a private namespace, and `preflight.py`, the check each Discord process
  runs first (PR 3b).
- `discord_room.py`: the probe's ``--room discord``: the harnesses' own Discord
  processes, unmodified, on the stand-in: Nunchi's for Claude Code, Codex and
  the reference (PR 3b), and Hermes's gateway, `hermes gateway run`, with the
  Nunchi plugin, whose evidence is read from outside its process (PR 3c).

See `docs/rehearsal.md`.
"""
