"""Token hygiene helpers.

Hard requirement: neither the bot token nor the MCP bearer token may appear in
any tool schema, tool result, notification payload, log line, or error message.

- the token is only ever read from NUNCHI_DISCORD_TOKEN (:mod:`.config`) and
  is excluded from ``Config.__repr__``;
- no module logs raw gateway payloads or HTTP headers (IDENTIFY/RESUME carry
  the token; the Authorization header carries it);
- :class:`TokenRedactionFilter` is installed on every root log handler as a
  last-resort backstop — any record whose formatted message contains the
  token is rewritten before it reaches a stream;
- ``tests/test_mcp_discord_server.py`` asserts the token is absent from
  serialized tool schemas, sample notifications, error strings, and captured
  log output.
"""

from __future__ import annotations

import logging

REDACTED = "[REDACTED]"


class TokenRedactionFilter(logging.Filter):
    """Rewrites any log record whose message contains the token."""

    def __init__(self, token: str) -> None:
        super().__init__()
        self._token = token

    def filter(self, record: logging.LogRecord) -> bool:
        if self._token:
            try:
                message = record.getMessage()
            except Exception:  # noqa: BLE001 — malformed record; let it through
                return True
            if self._token in message:
                record.msg = message.replace(self._token, REDACTED)
                record.args = ()
        return True


def install_redaction(token: str) -> TokenRedactionFilter:
    """Attach a redaction filter to all root logger handlers; returns the filter."""
    fil = TokenRedactionFilter(token)
    for handler in logging.getLogger().handlers:
        handler.addFilter(fil)
    return fil
