"""Cross-client HTTP redirect and response parsing security checks."""

from __future__ import annotations

import urllib.request
import unittest
from unittest import mock

from nunchi.adapters import matrix_v2, telegram_v2
from nunchi.mcp_discord import rest
from nunchi.net import NoRedirectHandler


class Response:
    def __init__(self, body: bytes, *, status: int = 200) -> None:
        self.body = body
        self.status = status
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


class CredentialBearingHttpCases(unittest.TestCase):
    def test_redirect_handler_never_constructs_a_followup_request(self) -> None:
        handler = NoRedirectHandler()
        original = urllib.request.Request(
            "https://trusted.example/api",
            headers={"Authorization": "Bearer secret"},
        )
        self.assertIsNone(
            handler.redirect_request(
                original,
                None,
                302,
                "Found",
                {},
                "https://attacker.example/collect",
            )
        )

    def test_matrix_telegram_and_discord_use_the_no_redirect_opener(self) -> None:
        with mock.patch(
            "nunchi.adapters.matrix_v2.open_no_redirect",
            return_value=Response(b'{}'),
        ) as opened:
            self.assertEqual(
                matrix_v2._urllib_call("GET", "https://matrix.example/x", {}, None, 1),
                (200, b"{}"),
            )
            opened.assert_called_once()

        with mock.patch(
            "nunchi.adapters.telegram_v2.open_no_redirect",
            return_value=Response(b'{}'),
        ) as opened:
            self.assertEqual(
                telegram_v2._urllib_call("GET", "https://telegram.example/x", {}, None, 1),
                (200, b"{}"),
            )
            opened.assert_called_once()

        with mock.patch(
            "nunchi.mcp_discord.rest.open_no_redirect",
            return_value=Response(b'{}'),
        ) as opened:
            self.assertEqual(
                rest._urllib_call("GET", "https://discord.example/x", {}, None),
                (200, {}, b"{}"),
            )
            opened.assert_called_once()

    def test_discord_rejects_duplicate_nonfinite_and_oversized_json(self) -> None:
        client = rest.DiscordRestClient(
            "secret",
            http=lambda *_args: (200, {}, b'{"id":"a","id":"b"}'),
        )
        with self.assertRaises(rest.DiscordRestError):
            client.create_message("1", "hello")

        client = rest.DiscordRestClient(
            "secret",
            http=lambda *_args: (200, {}, b'{"value":NaN}'),
        )
        with self.assertRaises(rest.DiscordRestError):
            client.create_message("1", "hello")

        with (
            mock.patch.object(rest, "MAX_RESPONSE_BYTES", 4),
            mock.patch(
                "nunchi.mcp_discord.rest.open_no_redirect",
                return_value=Response(b"12345"),
            ),
        ):
            with self.assertRaisesRegex(rest.DiscordRestError, "size budget"):
                rest._urllib_call("GET", "https://discord.example/x", {}, None)


if __name__ == "__main__":
    unittest.main()
