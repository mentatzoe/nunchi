"""Stateless, restart-stable Discord history continuation capabilities."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
from typing import Any


class DiscordContinuationError(ValueError):
    pass


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))
    except Exception as exc:
        raise DiscordContinuationError("continuation token is invalid") from exc


class DiscordHistoryContinuations:
    """Mint and verify HMAC-bound I-010D handles and cursors.

    The signing key derives from the process-scoped MCP credential, so tokens
    remain valid across a process restart with the same trusted binding but
    cannot be redirected to another participant or room.
    """

    def __init__(
        self,
        secret: str,
        *,
        participant_id: str,
        room_id: str,
        continuity_scope_id: str,
        max_events: int = 100,
        max_bytes: int = 32768,
    ) -> None:
        if (
            not isinstance(secret, str)
            or len(secret) < 32
            or not isinstance(participant_id, str)
            or not participant_id
            or not isinstance(room_id, str)
            or not room_id.isdigit()
            or not isinstance(continuity_scope_id, str)
            or not continuity_scope_id
        ):
            raise DiscordContinuationError("Discord continuation binding is invalid")
        self._key = hashlib.sha256(
            b"nunchi-discord-continuation-v2\0" + secret.encode("ascii")
        ).digest()
        self.participant_id = participant_id
        self.room_id = room_id
        self.continuity_scope_id = continuity_scope_id
        self.max_events = max_events
        self.max_bytes = max_bytes
        self._state_lock = threading.Lock()
        # This store and the gateway replay buffer are process-local. A newly
        # constructed process cannot prove what happened before its epoch, so
        # continuity begins conservatively tainted and remains so until a
        # future explicit bounded recovery mechanism proves closure.
        self._has_restart_gap = True

    def mark_restart_gap(self) -> None:
        """Conservatively retain known gateway discontinuity for this process."""
        with self._state_lock:
            self._has_restart_gap = True

    def _restart_gap(self) -> bool:
        with self._state_lock:
            return self._has_restart_gap

    @property
    def has_restart_gap(self) -> bool:
        return self._restart_gap()

    def _token(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(
            payload,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return _b64encode(raw) + "." + _b64encode(
            hmac.digest(self._key, raw, "sha256")
        )

    def _open(self, token: object, *, kind: str) -> dict[str, Any]:
        if not isinstance(token, str) or not token or len(token) > 4096:
            raise DiscordContinuationError("continuation token is invalid")
        parts = token.split(".")
        if len(parts) != 2:
            raise DiscordContinuationError("continuation token is invalid")
        raw = _b64decode(parts[0])
        signature = _b64decode(parts[1])
        if not hmac.compare_digest(signature, hmac.digest(self._key, raw, "sha256")):
            raise DiscordContinuationError("continuation token is invalid")
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, ValueError) as exc:
            raise DiscordContinuationError("continuation token is invalid") from exc
        if not isinstance(payload, dict) or payload.get("kind") != kind:
            raise DiscordContinuationError("continuation token is invalid")
        return payload

    def issue(self, trigger_event_id: str) -> dict[str, Any]:
        if (
            not isinstance(trigger_event_id, str)
            or not trigger_event_id.startswith("discord:message:")
            or not trigger_event_id.removeprefix("discord:message:").isdigit()
        ):
            raise DiscordContinuationError("Discord continuation trigger is invalid")
        binding = {
            "participant_id": self.participant_id,
            "room_id": self.room_id,
            "continuity_scope_id": self.continuity_scope_id,
            "trigger_event_id": trigger_event_id,
        }
        handle = self._token(
            {
                "kind": "handle",
                **binding,
                "has_restart_gap": self._restart_gap(),
            }
        )
        return {
            "handle_id": handle,
            "bound_to": binding,
            "can_fetch_before": True,
            "can_fetch_after": False,
            "can_fetch_around_event": False,
            "max_events_per_fetch": self.max_events,
            "max_bytes_per_fetch": self.max_bytes,
        }

    def verify_request(self, request: dict[str, Any]) -> tuple[dict[str, Any], str]:
        required = {"request_id", "handle_id", "direction", "max_events", "max_bytes"}
        optional = {"cursor", "anchor_event_id"}
        if (
            not isinstance(request, dict)
            or not required <= set(request)
            or set(request) - required - optional
            or not isinstance(request["request_id"], str)
            or not request["request_id"]
            or request["direction"] != "before"
            or isinstance(request["max_events"], bool)
            or not isinstance(request["max_events"], int)
            or not 1 <= request["max_events"] <= self.max_events
            or isinstance(request["max_bytes"], bool)
            or not isinstance(request["max_bytes"], int)
            or not 1 <= request["max_bytes"] <= self.max_bytes
        ):
            raise DiscordContinuationError("continuation request is invalid")
        handle = self._open(request["handle_id"], kind="handle")
        expected = {
            "kind": "handle",
            "participant_id": self.participant_id,
            "room_id": self.room_id,
            "continuity_scope_id": self.continuity_scope_id,
            "trigger_event_id": handle.get("trigger_event_id"),
            "has_restart_gap": handle.get("has_restart_gap"),
        }
        if handle != expected or not isinstance(handle.get("has_restart_gap"), bool):
            raise DiscordContinuationError("continuation binding is invalid")
        anchor = request.get("anchor_event_id", handle["trigger_event_id"])
        if anchor != handle["trigger_event_id"]:
            raise DiscordContinuationError("continuation anchor is invalid")
        before = handle["trigger_event_id"].removeprefix("discord:message:")
        if "cursor" in request:
            cursor = self._open(request["cursor"], kind="cursor")
            if (
                cursor.get("handle_id") != request["handle_id"]
                or not isinstance(cursor.get("before"), str)
                or not cursor["before"].isdigit()
            ):
                raise DiscordContinuationError("continuation cursor binding is invalid")
            before = cursor["before"]
        return handle, before

    def coverage(self, handle: dict[str, Any]) -> dict[str, Any]:
        """Return conservative coverage for an issued/verified handle.

        A gap learned after handle issuance still taints that handle.  This
        state is intentionally not cleared: bounded REST history alone cannot
        prove recovery of every gateway event kind in the missed interval.
        """
        has_restart_gap = bool(handle.get("has_restart_gap")) or self._restart_gap()
        return {
            "has_gaps": has_restart_gap,
            "continuity": "session-only" if has_restart_gap else "restart-safe",
            "has_restart_gap": has_restart_gap,
        }

    def cursor(self, handle_id: str, before: str) -> str:
        if not isinstance(before, str) or not before.isdigit():
            raise DiscordContinuationError("continuation cursor frontier is invalid")
        self._open(handle_id, kind="handle")
        return self._token(
            {"kind": "cursor", "handle_id": handle_id, "before": before}
        )


__all__ = ["DiscordContinuationError", "DiscordHistoryContinuations"]
