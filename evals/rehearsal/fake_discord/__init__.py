"""A Discord stand-in that answers as discord.com and gateway.discord.gg (step 9f, PR 3a).

Rehearsals run each harness's real Discord client against it before Zoe's
room: the same processes, unmodified, with only the hostnames, the tokens
and the ids changed. It behaves like Discord wherever the room's social
facts come from (the time of each message, who it addresses, what it
replies to, who wrote it, who may see, post or react, and the limits on the
agent's own small moves), and serves only the routes something has been
shown to call. Anything else is answered 599 and recorded as unknown, which
fails the run, so the modelled subset grows only from evidence.

- `world.py`: the guild, its members, roles and channels; the clock and
  snowflakes; the permission function; messages, mentions, replies,
  reactions and their limits.
- `payloads.py`: every object sent, in one place.
- `rest.py`, `gateway.py`, `server.py`: the wire.
- `wire.py`: the wire log, the verdict and what is not modelled.
- `shapes.py`: the shape pin against discord.py 2.7.1 (`discord_types.json`).
- `control.py`: `FakeDiscord`, run in the caller's process, and what a
  probe or director may do to it.

See `docs/rehearsal.md`. The package imports nothing itself, so that test
discovery from a checkout can walk it before Nunchi is on the path.
"""
