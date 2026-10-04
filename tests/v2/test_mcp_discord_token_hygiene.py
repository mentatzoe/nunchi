"""The Discord bot token and output key never surface outside the wire.

The token must reach Discord in IDENTIFY and the Authorization header, and
nowhere else: not in tool schemas, configuration reprs, error text that can
become a tool result, or logs.
"""

from __future__ import annotations

import json
import logging
import unittest

from nunchi.mcp_discord.config import load_config
from nunchi.mcp_discord.gateway import GatewayProtocol
from nunchi.mcp_discord.hygiene import REDACTED, TokenRedactionFilter
from nunchi.mcp_discord.rest import DiscordRestClient, DiscordRestError
from nunchi.mcp_discord.tools import TOOL_SCHEMAS

TOKEN = "NUNCHI-TEST-TOKEN-4f9a2bconfidential"
OUTPUT_KEY = b"NUNCHI-TEST-OUTPUT-KEY-" + b"x" * 16


class _Collector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(self.format(record))


class _CapturedLogs:
    """Capture everything the transport package logs at DEBUG and above."""

    def __init__(self, *, redact: bool = False) -> None:
        self.collector = _Collector()
        if redact:
            self.collector.addFilter(TokenRedactionFilter(TOKEN))
        self._logger = logging.getLogger("nunchi.mcp_discord")

    def __enter__(self) -> _Collector:
        self._old_level = self._logger.level
        self._logger.addHandler(self.collector)
        self._logger.setLevel(logging.DEBUG)
        return self.collector

    def __exit__(self, *_exc: object) -> None:
        self._logger.removeHandler(self.collector)
        self._logger.setLevel(self._old_level)


class TokenHygieneTests(unittest.TestCase):
    def test_tool_schemas_never_carry_the_token(self) -> None:
        self.assertNotIn(TOKEN, json.dumps(TOOL_SCHEMAS))

    def test_configuration_repr_hides_token_and_output_key(self) -> None:
        config = load_config(
            {
                "NUNCHI_DISCORD_TOKEN": TOKEN,
                "NUNCHI_DISCORD_PARTICIPANT_ROUTES": '{"vigil": ["152"]}',
                "NUNCHI_DISCORD_OUTPUT_HMAC_KEY": OUTPUT_KEY.decode(),
                "NUNCHI_DISCORD_STATE_DIRECTORY": "/nonexistent",
            }
        )
        for text in (repr(config), str(config)):
            self.assertNotIn(TOKEN, text)
            self.assertNotIn("NUNCHI-TEST-OUTPUT-KEY", text)

    def test_rest_errors_never_echo_the_token(self) -> None:
        echoed = json.dumps({"message": f"Bot {TOKEN} is not authorized"}).encode()

        def http(_method, _url, _headers, _body):
            return 401, {}, echoed

        client = DiscordRestClient(TOKEN, http=http, sleeper=lambda _s: None)
        with self.assertRaises(DiscordRestError) as raised:
            client.create_message("100", "hi")
        text = str(raised.exception)
        self.assertNotIn(TOKEN, text)
        self.assertNotIn("Authorization", text)

    def test_identify_carries_the_token_but_logs_never_do(self) -> None:
        with _CapturedLogs() as logs:
            protocol = GatewayProtocol(TOKEN)
            protocol.on_connection_open()
            actions = protocol.handle({"op": 10, "d": {"heartbeat_interval": 45000}})
        identify = [a for a in actions if getattr(a, "payload", {}).get("op") == 2]
        self.assertTrue(identify, "HELLO must produce an IDENTIFY")
        self.assertEqual(identify[0].payload["d"]["token"], TOKEN)
        self.assertNotIn(TOKEN, "\n".join(logs.messages))

    def test_redaction_backstop_rewrites_a_leaking_line(self) -> None:
        with _CapturedLogs(redact=True) as logs:
            logging.getLogger("nunchi.mcp_discord.adversarial").warning(
                "connecting with token %s", TOKEN
            )
        joined = "\n".join(logs.messages)
        self.assertNotIn(TOKEN, joined)
        self.assertIn(REDACTED, joined, "the line must be redacted, not dropped")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
