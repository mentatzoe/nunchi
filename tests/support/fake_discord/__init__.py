"""A local Discord fixture for isolated transport tests.

It models messages, addressing, replies, permissions, reactions and selected
REST and gateway behavior. Unknown operations are recorded and answered with
599 so tests can detect gaps in the fixture. It does not run conversations or
judge social behavior.

- `world.py`: guild, members, roles, channels, messages and permissions.
- `payloads.py`: objects sent to clients.
- `rest.py`, `gateway.py`, `server.py`: HTTP and WebSocket handling.
- `wire.py`: traffic records and documented differences from Discord.
- `shapes.py`: payload checks against discord.py 2.7.1 (`discord_types.json`).
- `control.py`: `FakeDiscord`, running in the caller's process.

The package imports nothing itself, so test discovery can walk it before
Nunchi is on the path.
"""
