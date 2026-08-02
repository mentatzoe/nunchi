"""Discord REST client for the transport tools (stdlib urllib, sync).

Runs in worker threads via ``asyncio.to_thread`` so rate-limit sleeps never
block the event loop. Retry policy:

- 429: honor retry-after (body ``retry_after`` or Retry-After header,
  global flag respected), retry up to ``max_retries`` times;
- 5xx: bounded retry with short backoff for reads only; mutating requests
  return uncertainty immediately because retrying without target idempotency
  could duplicate an effect;
- 401/403 (and other 4xx): non-retryable — abort immediately. Permanent
  auth/permission errors must not burn retries.

Error messages never include the token or request headers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Mapping

from .ratelimit import RateLimiter

logger = logging.getLogger("nunchi.mcp_discord.rest")

API_BASE_URL = "https://discord.com/api/v10"
_USER_AGENT = "DiscordBot (https://github.com/mentatzoe/nunchi, 2.0.0)"
_TIMEOUT_SECONDS = 15.0

_ADMINISTRATOR = 1 << 3
_ADD_REACTIONS = 1 << 6
_VIEW_CHANNEL = 1 << 10
_READ_MESSAGE_HISTORY = 1 << 16

# method, url, headers, body -> (status, lower-cased headers, body)
HttpCall = Callable[[str, str, Mapping[str, str], "bytes | None"], "tuple[int, dict[str, str], bytes]"]


class DiscordRestError(Exception):
    """A REST call failed. ``status`` is None for network-level failures."""

    def __init__(self, status: int | None, message: str) -> None:
        super().__init__(message)
        self.status = status


def _urllib_call(
    method: str, url: str, headers: Mapping[str, str], body: bytes | None
) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            return (
                response.status,
                {k.lower(): v for k, v in response.headers.items()},
                response.read(),
            )
    except urllib.error.HTTPError as exc:
        return (exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read())
    except urllib.error.URLError as exc:
        raise DiscordRestError(None, f"network error reaching Discord API: {exc.reason}") from None


def _error_detail(body: bytes) -> str:
    """Extract Discord's error message from a response body (never echoes headers)."""
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return ""
    message = payload.get("message") if isinstance(payload, dict) else None
    return str(message)[:200] if message else ""


def _permission_bits(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise DiscordRestError(None, f"Discord {label} permissions are malformed")
    if isinstance(value, str) and not value.isdigit():
        raise DiscordRestError(None, f"Discord {label} permissions are malformed")
    bits = int(value)
    if bits < 0:
        raise DiscordRestError(None, f"Discord {label} permissions are malformed")
    return bits


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
        self, channel_id: str, content: str, *, reply_to_message_id: str | None = None
    ) -> dict:
        body: dict = {"content": content}
        if reply_to_message_id is not None:
            body["message_reference"] = {
                "message_id": reply_to_message_id,
                "channel_id": channel_id,
                "fail_if_not_exists": False,
            }
        return self._request("POST", f"/channels/{channel_id}/messages", body=body)

    def get_messages(
        self, channel_id: str, *, limit: int = 50, before: str | None = None
    ) -> list[dict]:
        limit = max(1, min(int(limit), 100))
        path = f"/channels/{channel_id}/messages?limit={limit}"
        if before is not None:
            path += f"&before={before}"
        result = self._request("GET", path)
        return result if isinstance(result, list) else []

    def add_reaction(self, channel_id: str, message_id: str, reaction: str) -> None:
        encoded = urllib.parse.quote(reaction, safe="")
        self._request(
            "PUT",
            f"/channels/{channel_id}/messages/{message_id}/reactions/{encoded}/@me",
        )

    def remove_reaction(self, channel_id: str, message_id: str, reaction: str) -> None:
        encoded = urllib.parse.quote(reaction, safe="")
        self._request(
            "DELETE",
            f"/channels/{channel_id}/messages/{message_id}/reactions/{encoded}/@me",
        )

    def reaction_capability(self, channel_id: str, expected_user_id: str) -> dict:
        """Measure this bot's effective reaction permissions in one guild channel."""
        channel = self._request("GET", f"/channels/{channel_id}")
        if not isinstance(channel, Mapping) or str(channel.get("id", "")) != channel_id:
            raise DiscordRestError(None, "Discord channel capability response is malformed")
        guild_id = str(channel.get("guild_id", ""))
        overwrites = channel.get("permission_overwrites")
        if not guild_id.isdigit() or not isinstance(overwrites, list):
            raise DiscordRestError(
                None,
                "Discord channel capability lacks guild permission facts",
            )

        member = self._request(
            "GET",
            f"/guilds/{guild_id}/members/{expected_user_id}",
        )
        roles = self._request("GET", f"/guilds/{guild_id}/roles")
        if not isinstance(member, Mapping) or not isinstance(roles, list):
            raise DiscordRestError(None, "Discord member capability response is malformed")
        user = member.get("user")
        user_id = str(user.get("id", "")) if isinstance(user, Mapping) else ""
        member_roles = member.get("roles")
        if user_id != expected_user_id or not isinstance(member_roles, list):
            raise DiscordRestError(None, "Discord capability self identity is untrustworthy")
        role_ids = {str(item) for item in member_roles if str(item).isdigit()}
        if len(role_ids) != len(member_roles):
            raise DiscordRestError(None, "Discord member roles are malformed")
        role_ids.add(guild_id)

        base = 0
        found_everyone = False
        for role in roles:
            if not isinstance(role, Mapping):
                raise DiscordRestError(None, "Discord guild roles are malformed")
            role_id = str(role.get("id", ""))
            permissions = _permission_bits(role.get("permissions"), "guild role")
            if not role_id.isdigit():
                raise DiscordRestError(None, "Discord guild role permissions are malformed")
            if role_id in role_ids:
                base |= permissions
            if role_id == guild_id:
                found_everyone = True
        if not found_everyone:
            raise DiscordRestError(None, "Discord guild everyone role is unavailable")

        if base & _ADMINISTRATOR:
            effective = base
            allowed = True
        else:
            everyone_allow = everyone_deny = 0
            roles_allow = roles_deny = 0
            member_allow = member_deny = 0
            for overwrite in overwrites:
                if not isinstance(overwrite, Mapping):
                    raise DiscordRestError(None, "Discord permission overwrites are malformed")
                overwrite_id = str(overwrite.get("id", ""))
                overwrite_type = overwrite.get("type")
                allow = _permission_bits(overwrite.get("allow"), "overwrite allow")
                deny = _permission_bits(overwrite.get("deny"), "overwrite deny")
                if (
                    not overwrite_id.isdigit()
                    or overwrite_type not in (0, 1)
                ):
                    raise DiscordRestError(None, "Discord permission overwrites are malformed")
                if overwrite_type == 0 and overwrite_id == guild_id:
                    everyone_allow, everyone_deny = allow, deny
                elif overwrite_type == 0 and overwrite_id in role_ids:
                    roles_allow |= allow
                    roles_deny |= deny
                elif overwrite_type == 1 and overwrite_id == user_id:
                    member_allow, member_deny = allow, deny
            effective = (base & ~everyone_deny) | everyone_allow
            effective = (effective & ~roles_deny) | roles_allow
            effective = (effective & ~member_deny) | member_allow
            required = _VIEW_CHANNEL | _READ_MESSAGE_HISTORY | _ADD_REACTIONS
            allowed = effective & required == required

        revision = hashlib.sha256(
            (
                f"discord-rest-v2\0{guild_id}\0{channel_id}\0{user_id}\0"
                f"{effective}\0{int(allowed)}"
            ).encode()
        ).hexdigest()
        return {
            "channel_id": channel_id,
            "actor_id": user_id,
            "capability": {
                "supported": allowed,
                "authenticated": True,
                "operations": ["add", "remove"] if allowed else [],
                "reactions": ["*"] if allowed else [],
                "permissions_revision": revision,
                **(
                    {}
                    if allowed
                    else {
                        "detail": (
                            "Discord room does not grant view, history, and add-reaction permissions"
                        )
                    }
                ),
            },
        }

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
        data = json.dumps(body).encode("utf-8") if body is not None else None
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
                detail = _error_detail(resp_body)
                raise DiscordRestError(
                    status,
                    f"Discord API {status} on {route}: "
                    f"{detail or 'check the bot token and channel permissions'}",
                )

            if 500 <= status < 600:
                if method != "GET":
                    raise DiscordRestError(
                        status,
                        f"Discord API {status} on {route}; effect outcome is unknown",
                    )
                attempts += 1
                if attempts > self._max_retries:
                    raise DiscordRestError(status, f"Discord API {status} on {route}; retries exhausted")
                backoff = min(2.0 ** attempts, 10.0)
                logger.warning("HTTP %d on %s; retrying in %.1fs", status, route, backoff)
                self._sleep(backoff)
                continue

            if status >= 400:
                detail = _error_detail(resp_body)
                raise DiscordRestError(status, f"Discord API {status} on {route}: {detail}")

            if not resp_body:
                return {}
            try:
                return json.loads(resp_body)
            except ValueError:
                raise DiscordRestError(status, f"malformed JSON from Discord API on {route}") from None

    @staticmethod
    def _parse_retry_after(headers: Mapping[str, str], body: bytes) -> tuple[float, bool]:
        retry_after = 1.0
        is_global = headers.get("x-ratelimit-global", "").lower() == "true"
        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                retry_after = float(payload.get("retry_after", retry_after))
                is_global = bool(payload.get("global", is_global))
        except (ValueError, TypeError):
            header_val = headers.get("retry-after")
            if header_val is not None:
                try:
                    retry_after = float(header_val)
                except ValueError:
                    pass
        return (retry_after, is_global)
