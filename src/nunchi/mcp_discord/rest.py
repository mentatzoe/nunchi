"""Discord REST client for the transport tools (stdlib urllib, sync).

Runs in worker threads via ``asyncio.to_thread`` so rate-limit sleeps never
block the event loop. Retry policy:

- 429: honor retry-after (body ``retry_after`` or Retry-After header,
  global flag respected), retry up to ``max_retries`` times;
- 5xx: bounded retry with short backoff;
- 401/403 (and other 4xx): non-retryable — abort immediately. Permanent
  auth/permission errors must not burn retries.

Error messages never include the token or request headers.
"""

from __future__ import annotations

import json
import logging
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Mapping

from ..net import open_no_redirect
from .ratelimit import RateLimiter

logger = logging.getLogger("nunchi.mcp_discord.rest")

API_BASE_URL = "https://discord.com/api/v10"
_USER_AGENT = "DiscordBot (https://github.com/mentatzoe/nunchi, 0.2.0)"
_TIMEOUT_SECONDS = 15.0
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_RETRY_AFTER_SECONDS = 300.0

# method, url, headers, body -> (status, lower-cased headers, body)
HttpCall = Callable[[str, str, Mapping[str, str], "bytes | None"], "tuple[int, dict[str, str], bytes]"]


class DiscordRestError(Exception):
    """A REST call failed. ``status`` is None for network-level failures."""

    def __init__(self, status: int | None, message: str) -> None:
        super().__init__(message)
        self.status = status


def _strict_json(raw: str | bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    return json.loads(
        raw,
        object_pairs_hook=pairs,
        parse_constant=lambda _value: (_ for _ in ()).throw(
            ValueError("non-finite")
        ),
    )


def _bounded_read(response) -> bytes:
    body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise DiscordRestError(None, "Discord API response exceeded its size budget")
    return body


def _urllib_call(
    method: str, url: str, headers: Mapping[str, str], body: bytes | None
) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with open_no_redirect(request, timeout=_TIMEOUT_SECONDS) as response:
            return (
                response.status,
                {k.lower(): v for k, v in response.headers.items()},
                _bounded_read(response),
            )
    except urllib.error.HTTPError as exc:
        with exc:
            return (
                exc.code,
                {k.lower(): v for k, v in exc.headers.items()},
                _bounded_read(exc),
            )
    except urllib.error.URLError:
        raise DiscordRestError(None, "network error reaching Discord API") from None


class DiscordRestClient:
    """Minimal REST surface: create message, fetch history."""

    def __init__(
        self,
        token: str,
        *,
        limiter: RateLimiter | None = None,
        http: HttpCall | None = None,
        base_url: str = API_BASE_URL,
        max_retries: int = 3,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if (
            not isinstance(token, str)
            or not token
            or len(token) > 4096
            or not token.isascii()
            or any(ord(character) < 33 or ord(character) > 126 for character in token)
        ):
            raise ValueError("Discord token is invalid")
        if (
            not isinstance(base_url, str)
            or base_url.rstrip("/") != API_BASE_URL
        ):
            raise ValueError("Discord REST origin is not the trusted API origin")
        if (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or not 0 <= max_retries <= 10
            or not callable(sleeper)
            or (http is not None and not callable(http))
        ):
            raise ValueError("Discord REST client configuration is invalid")
        self._token = token
        self._limiter = limiter or RateLimiter(sleeper=sleeper)
        self._http = http or _urllib_call
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._sleep = sleeper

    # ------------------------------------------------------------------ #
    # Public surface
    # ------------------------------------------------------------------ #

    def create_message(
        self,
        channel_id: str,
        content: str,
        *,
        reply_to_message_id: str | None = None,
        allowed_mention_user_ids: tuple[str, ...] | None = None,
        fail_if_reply_missing: bool = False,
    ) -> dict:
        body: dict = {"content": content}
        if allowed_mention_user_ids is not None:
            body["allowed_mentions"] = {
                "parse": [],
                "users": list(allowed_mention_user_ids),
                "roles": [],
                "replied_user": False,
            }
        if reply_to_message_id is not None:
            body["message_reference"] = {
                "message_id": reply_to_message_id,
                "channel_id": channel_id,
                "fail_if_not_exists": fail_if_reply_missing,
            }
        return self._request("POST", f"/channels/{channel_id}/messages", body=body)

    def create_reaction(
        self,
        channel_id: str,
        message_id: str,
        reaction: str,
    ) -> None:
        encoded = urllib.parse.quote(reaction, safe="")
        self._request(
            "PUT",
            f"/channels/{channel_id}/messages/{message_id}/reactions/{encoded}/@me",
        )

    def get_messages(
        self, channel_id: str, *, limit: int = 50, before: str | None = None
    ) -> list[dict]:
        limit = max(1, min(int(limit), 100))
        path = f"/channels/{channel_id}/messages?limit={limit}"
        if before is not None:
            path += f"&before={before}"
        result = self._request("GET", path)
        if not isinstance(result, list) or any(
            not isinstance(message, dict) for message in result
        ):
            raise DiscordRestError(200, "malformed message history from Discord API")
        return result

    # ------------------------------------------------------------------ #
    # Request core
    # ------------------------------------------------------------------ #

    def _request(self, method: str, path: str, *, body: dict | None = None):
        route = f"{method} {path.split('?', 1)[0]}"
        headers = {
            "Authorization": f"Bot {self._token}",
            "User-Agent": _USER_AGENT,
            "Content-Type": "application/json",
        }
        data = (
            json.dumps(body, allow_nan=False, separators=(",", ":")).encode("utf-8")
            if body is not None
            else None
        )
        attempts = 0
        while True:
            self._limiter.before_request(route)
            status, resp_headers, resp_body = self._http(
                method, self._base_url + path, headers, data
            )
            self._limiter.after_response(route, resp_headers)

            if status == 429:
                attempts += 1
                retry_after, is_global = self._parse_retry_after(resp_headers, resp_body)
                self._limiter.note_retry_after(route, retry_after, is_global=is_global)
                if attempts > self._max_retries:
                    raise DiscordRestError(
                        429, f"rate limited on {route}; retries exhausted"
                    )
                logger.warning(
                    "429 on %s (global=%s); retrying after %.2fs (attempt %d/%d)",
                    route, is_global, retry_after, attempts, self._max_retries,
                )
                continue  # before_request sleeps out the retry-after

            if status in (401, 403):
                # Permanent auth/permission failure: abort immediately, no retry.
                raise DiscordRestError(
                    status,
                    f"Discord API {status} on {route}; check the bot token "
                    "and channel permissions",
                )

            if 500 <= status < 600:
                attempts += 1
                if attempts > self._max_retries:
                    raise DiscordRestError(status, f"Discord API {status} on {route}; retries exhausted")
                backoff = min(2.0 ** attempts, 10.0)
                logger.warning("HTTP %d on %s; retrying in %.1fs", status, route, backoff)
                self._sleep(backoff)
                continue

            if status >= 400:
                raise DiscordRestError(status, f"Discord API {status} on {route}")

            if not 200 <= status < 300:
                raise DiscordRestError(status, f"unexpected Discord API status on {route}")

            if not resp_body:
                return {}
            try:
                return _strict_json(resp_body)
            except ValueError:
                raise DiscordRestError(status, f"malformed JSON from Discord API on {route}") from None

    @staticmethod
    def _parse_retry_after(headers: Mapping[str, str], body: bytes) -> tuple[float, bool]:
        retry_after = 1.0
        is_global = headers.get("x-ratelimit-global", "").lower() == "true"
        try:
            payload = _strict_json(body)
            if isinstance(payload, dict):
                retry_value = payload.get("retry_after", retry_after)
                if isinstance(retry_value, bool) or not isinstance(
                    retry_value, (int, float)
                ):
                    raise ValueError("invalid retry-after value")
                retry_after = float(retry_value)
                global_value = payload.get("global", is_global)
                if type(global_value) is bool:
                    is_global = global_value
                else:
                    raise ValueError("invalid global rate-limit flag")
        except (ValueError, TypeError):
            retry_after = 1.0
            header_val = headers.get("retry-after")
            if header_val is not None:
                try:
                    retry_after = float(header_val)
                except ValueError:
                    pass
        if not math.isfinite(retry_after) or retry_after < 0:
            retry_after = 1.0
        return (min(retry_after, MAX_RETRY_AFTER_SECONDS), is_global)
