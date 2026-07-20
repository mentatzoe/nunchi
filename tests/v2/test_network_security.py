"""Cross-client HTTP redirect and response parsing security checks."""

from __future__ import annotations

import urllib.request
import unittest
from unittest import mock

from nunchi.adapters import matrix_v2, telegram_v2
from nunchi.mcp_discord import rest
from nunchi.mcp_discord.ratelimit import RateLimiter
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

    def test_discord_client_rejects_untrusted_origin_and_header_injection(self) -> None:
        for token in ("", "secret\r\nX-Injected: yes", "é"):
            with self.subTest(token=token):
                with self.assertRaises(ValueError):
                    rest.DiscordRestClient(token)
        with self.assertRaisesRegex(ValueError, "trusted API origin"):
            rest.DiscordRestClient(
                "secret",
                base_url="https://attacker.example/api/v10",
            )
        with self.assertRaises(ValueError):
            rest.DiscordRestClient("secret", max_retries=1000)

    def test_discord_redirect_status_and_malformed_history_fail_closed(self) -> None:
        client = rest.DiscordRestClient(
            "secret",
            http=lambda *_args: (302, {"location": "https://attacker.example"}, b""),
        )
        with self.assertRaisesRegex(rest.DiscordRestError, "unexpected"):
            client.create_message("1", "hello")

        client = rest.DiscordRestClient(
            "secret",
            http=lambda *_args: (200, {}, b'{"messages":[]}'),
        )
        with self.assertRaisesRegex(rest.DiscordRestError, "malformed message history"):
            client.get_messages("1")

    def test_discord_rate_limit_numbers_are_finite_and_bounded(self) -> None:
        clock = lambda: 100.0
        sleeps: list[float] = []
        limiter = RateLimiter(clock=clock, sleeper=sleeps.append)
        for value in ("NaN", "Infinity", "90001", "-1"):
            limiter.after_response(
                "GET /channels/1/messages",
                {
                    "x-ratelimit-remaining": "0",
                    "x-ratelimit-reset-after": value,
                },
            )
        limiter.before_request("GET /channels/1/messages")
        self.assertEqual(sleeps, [])

        limiter.note_retry_after(
            "GET /channels/1/messages",
            float("inf"),
            is_global=False,
        )
        limiter.before_request("GET /channels/1/messages")
        self.assertEqual(sleeps, [1.0])

        self.assertEqual(
            rest.DiscordRestClient._parse_retry_after({}, b'{"retry_after":1e1000}'),
            (1.0, False),
        )
        self.assertEqual(
            rest.DiscordRestClient._parse_retry_after(
                {}, b'{"retry_after":900,"global":true}'
            ),
            (rest.MAX_RETRY_AFTER_SECONDS, True),
        )
        self.assertEqual(
            rest.DiscordRestClient._parse_retry_after(
                {}, b'{"retry_after":2,"global":"false"}'
            ),
            (1.0, False),
        )


if __name__ == "__main__":
    unittest.main()
