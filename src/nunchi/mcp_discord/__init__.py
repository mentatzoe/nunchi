"""nunchi-mcp-discord: a standing Discord transport server speaking MCP.

One server per Discord bot account. It connects to the Discord gateway
(GUILD_MESSAGES | MESSAGE_CONTENT intents), pushes every non-self message to
connected MCP clients as ``notifications/discord/message``, and exposes
``send_message`` / ``reply_message`` / ``read_history`` tools.

This package carries NO gate logic. Gating (nunchi admission) happens
harness-side; this is pure transport ("1 transport + N thin gate hooks").

Requires the ``mcp`` SDK (opt-in only):

    pip install nunchi[mcp-discord]

All modules except :mod:`._binding` are import-safe without the SDK; the
gateway itself is a stdlib-only implementation (no discord.py).

See ``integrations/mcp-discord/`` for setup docs and the design record.
"""

from __future__ import annotations
