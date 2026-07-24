"""One-use HMAC binding for shared Discord MCP effects and history reads."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
import time
from typing import Any


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def make_tool_authorization(
    *,
    secret: bytes,
    request_id: str,
    participant_id: str,
    room_id: str,
    tool: str,
    arguments: Mapping[str, Any],
    now: int | None = None,
) -> dict[str, Any]:
    issued_at = int(time.time()) if now is None else int(now)
    binding = {
        "request_id": request_id,
        "participant_id": participant_id,
        "room_id": room_id,
        "tool": tool,
        "action_digest": hashlib.sha256(_canonical(arguments)).hexdigest(),
        "issued_at": issued_at,
        "nonce": secrets.token_urlsafe(24),
    }
    binding["mac"] = hmac.new(secret, _canonical(binding), hashlib.sha256).hexdigest()
    return binding


class ToolAuthorizer:
    def __init__(
        self,
        *,
        secret: bytes,
        participant_ids: frozenset[str],
        room_ids: frozenset[str],
        max_age_seconds: int = 60,
        journal_path: str | Path | None = None,
    ) -> None:
        if len(secret) < 32:
            raise ValueError("Discord output authorization secret must be at least 32 bytes")
        if not participant_ids or not room_ids:
            raise ValueError("Discord output authorization requires participants and rooms")
        self._secret = secret
        self._participants = participant_ids
        self._rooms = room_ids
        self._max_age = max_age_seconds
        self._used: dict[str, int] = {}
        self._journal_path = Path(journal_path) if journal_path is not None else None
        self._lock = threading.Lock()
        if self._journal_path is not None:
            self._journal_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_journal()

    def _load_journal(self) -> None:
        assert self._journal_path is not None
        if not self._journal_path.exists():
            return
        try:
            with self._journal_path.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    if (
                        not isinstance(record, dict)
                        or set(record) != {"nonce", "accepted_at"}
                        or not isinstance(record["nonce"], str)
                        or isinstance(record["accepted_at"], bool)
                        or not isinstance(record["accepted_at"], int)
                    ):
                        raise ValueError(f"invalid record at line {line_number}")
                    self._used[record["nonce"]] = record["accepted_at"]
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Discord output authorization journal is untrustworthy: {exc}"
            ) from exc

    def _persist_nonce(self, nonce: str, current: int) -> None:
        if self._journal_path is None:
            return
        payload = (
            json.dumps(
                {"nonce": nonce, "accepted_at": current},
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
        fd = os.open(
            self._journal_path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o600,
        )
        try:
            if os.write(fd, payload) != len(payload):
                raise OSError("short output-authorization journal write")
            os.fsync(fd)
        finally:
            os.close(fd)

    def verify(
        self,
        *,
        authorization: Any,
        tool: str,
        arguments: Mapping[str, Any],
        now: int | None = None,
    ) -> tuple[bool, str]:
        required = {
            "request_id",
            "participant_id",
            "room_id",
            "tool",
            "action_digest",
            "issued_at",
            "nonce",
            "mac",
        }
        if not isinstance(authorization, Mapping) or set(authorization) != required:
            return False, "missing or malformed Nunchi V2 tool authorization"
        for name in required - {"issued_at"}:
            if not isinstance(authorization[name], str) or not authorization[name]:
                return False, f"authorization {name} must be non-empty"
        if isinstance(authorization["issued_at"], bool) or not isinstance(authorization["issued_at"], int):
            return False, "authorization issued_at must be an integer"
        if authorization["tool"] != tool:
            return False, "authorization tool binding mismatch"
        if authorization["room_id"] not in self._rooms:
            return False, "authorization room is outside trusted routes"
        if authorization["participant_id"] not in self._participants:
            return False, "authorization participant is outside trusted routes"
        if arguments.get("channel_id") != authorization["room_id"]:
            return False, "authorization channel binding mismatch"
        try:
            digest = hashlib.sha256(_canonical(arguments)).hexdigest()
        except (TypeError, ValueError):
            return False, "tool arguments are not canonical JSON"
        if not hmac.compare_digest(digest, authorization["action_digest"]):
            return False, "authorization action digest mismatch"
        signed = dict(authorization)
        supplied_mac = signed.pop("mac")
        expected_mac = hmac.new(self._secret, _canonical(signed), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied_mac, expected_mac):
            return False, "authorization MAC is invalid"
        current = int(time.time()) if now is None else int(now)
        age = current - authorization["issued_at"]
        if age < 0 or age > self._max_age:
            return False, "authorization is expired or from the future"
        nonce = authorization["nonce"]
        with self._lock:
            self._used = {
                item: timestamp
                for item, timestamp in self._used.items()
                if current - timestamp <= self._max_age
            }
            if nonce in self._used:
                return False, "authorization nonce was replayed"
            try:
                self._persist_nonce(nonce, current)
            except OSError:
                return False, "authorization persistence is uncertain"
            self._used[nonce] = current
        return True, ""
