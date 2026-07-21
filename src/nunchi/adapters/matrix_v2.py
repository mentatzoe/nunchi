"""One-room Matrix V2 reference adapter over the shared live runtime."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from ..mcp_discord.ratelimit import SendBackstop
from ..net import (
    is_bounded_ascii_credential,
    is_loopback_hostname,
    open_no_redirect,
)
from ..receipts import transport_receipt
from .native_host_v2 import (
    DurableCursorStoreV2,
    NativeRuntimeV2,
    add_participant_arguments,
    build_native_runtime,
)
from .v2 import MatrixEventSourceV2


logger = logging.getLogger("nunchi.adapters.matrix_v2")
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_MESSAGE_BYTES = 64 * 1024
_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


class MatrixV2Error(RuntimeError):
    pass


class MatrixClientLike(Protocol):
    def whoami(self) -> str: ...

    def sync(self, since: str | None, *, timeout_ms: int) -> dict[str, Any]: ...

    def send_message(
        self,
        room_id: str,
        transaction_id: str,
        content: str,
        *,
        reply_to_event_id: str | None,
        mention_user_ids: tuple[str, ...],
    ) -> str: ...

    def send_reaction(
        self,
        room_id: str,
        transaction_id: str,
        target_event_id: str,
        reaction: str,
    ) -> str: ...


HttpCall = Callable[
    [str, str, Mapping[str, str], bytes | None, float],
    tuple[int, bytes],
]


def _strict_json(raw: bytes) -> Any:
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


def _urllib_call(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: bytes | None,
    timeout: float,
) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers=dict(headers),
    )
    try:
        response = open_no_redirect(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    except (socket.timeout, urllib.error.URLError, OSError) as exc:
        raise MatrixV2Error("Matrix network request failed") from exc
    with response:
        payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise MatrixV2Error("Matrix response exceeded its size budget")
        return int(response.status), payload


def _homeserver(value: str, *, allow_insecure_http: bool) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 8192
        or any(ord(character) <= 32 or ord(character) == 127 for character in value)
        or not isinstance(allow_insecure_http, bool)
    ):
        raise MatrixV2Error("Matrix homeserver is invalid")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise MatrixV2Error("Matrix homeserver is invalid") from exc
    permitted = parsed.scheme == "https" or (
        allow_insecure_http
        and parsed.scheme == "http"
        and is_loopback_hostname(parsed.hostname)
    )
    if (
        not permitted
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port is not None and not 1 <= port <= 65535
    ):
        raise MatrixV2Error("Matrix homeserver is invalid")
    return value.rstrip("/")


class MatrixClientV2:
    def __init__(
        self,
        homeserver: str,
        token: str,
        *,
        room_id: str,
        allow_insecure_http: bool = False,
        http: HttpCall = _urllib_call,
    ) -> None:
        if (
            not is_bounded_ascii_credential(token)
            or not isinstance(room_id, str)
            or not room_id
        ):
            raise MatrixV2Error("Matrix client binding is invalid")
        self.homeserver = _homeserver(
            homeserver,
            allow_insecure_http=allow_insecure_http,
        )
        self.token = token
        self.room_id = room_id
        self.http = http

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        timeout: float = 30,
    ) -> Any:
        payload = None
        if body is not None:
            payload = json.dumps(
                body,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        status, raw = self.http(
            method,
            self.homeserver + path,
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            payload,
            timeout,
        )
        if status < 200 or status >= 300:
            raise MatrixV2Error(f"Matrix API request failed with status {status}")
        try:
            return _strict_json(raw)
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            raise MatrixV2Error("Matrix API returned invalid JSON") from exc

    def whoami(self) -> str:
        result = self._request("GET", "/_matrix/client/v3/account/whoami")
        user_id = result.get("user_id") if isinstance(result, dict) else None
        if not isinstance(user_id, str) or not user_id.startswith("@") or ":" not in user_id:
            raise MatrixV2Error("Matrix account identity is unavailable")
        return user_id

    def sync(self, since: str | None, *, timeout_ms: int) -> dict[str, Any]:
        if (
            isinstance(timeout_ms, bool)
            or not isinstance(timeout_ms, int)
            or not 0 <= timeout_ms <= 120000
        ):
            raise MatrixV2Error("Matrix sync timeout is invalid")
        query: dict[str, str | int] = {
            "timeout": timeout_ms,
            "filter": json.dumps(
                {
                    "room": {
                        "rooms": [self.room_id],
                        "timeline": {"limit": 100},
                    }
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
        if since is not None:
            if not isinstance(since, str) or not since:
                raise MatrixV2Error("Matrix sync cursor is invalid")
            query["since"] = since
        result = self._request(
            "GET",
            "/_matrix/client/v3/sync?" + urllib.parse.urlencode(query),
            timeout=max(30.0, timeout_ms / 1000 + 15.0),
        )
        if not isinstance(result, dict):
            raise MatrixV2Error("Matrix sync response is invalid")
        return result

    def _send_event(
        self,
        room_id: str,
        event_type: str,
        transaction_id: str,
        content: dict[str, Any],
    ) -> str:
        room = urllib.parse.quote(room_id, safe="")
        kind = urllib.parse.quote(event_type, safe="")
        transaction = urllib.parse.quote(transaction_id, safe="")
        result = self._request(
            "PUT",
            f"/_matrix/client/v3/rooms/{room}/send/{kind}/{transaction}",
            body=content,
        )
        event_id = result.get("event_id") if isinstance(result, dict) else None
        if not isinstance(event_id, str) or not event_id:
            raise MatrixV2Error("Matrix send result is invalid")
        return event_id

    def send_message(
        self,
        room_id: str,
        transaction_id: str,
        content: str,
        *,
        reply_to_event_id: str | None,
        mention_user_ids: tuple[str, ...],
    ) -> str:
        body: dict[str, Any] = {"msgtype": "m.text", "body": content}
        if reply_to_event_id is not None:
            body["m.relates_to"] = {
                "m.in_reply_to": {"event_id": reply_to_event_id}
            }
        if mention_user_ids:
            body["m.mentions"] = {"user_ids": list(mention_user_ids)}
        return self._send_event(
            room_id,
            "m.room.message",
            transaction_id,
            body,
        )

    def send_reaction(
        self,
        room_id: str,
        transaction_id: str,
        target_event_id: str,
        reaction: str,
    ) -> str:
        return self._send_event(
            room_id,
            "m.reaction",
            transaction_id,
            {
                "m.relates_to": {
                    "rel_type": "m.annotation",
                    "event_id": target_event_id,
                    "key": reaction,
                }
            },
        )


def _matrix_event_id(value: Any) -> str:
    prefix = "matrix:event:"
    if (
        not isinstance(value, str)
        or not value.startswith(prefix)
        or not value[len(prefix):]
    ):
        raise MatrixV2Error("Matrix event identity is invalid")
    return value[len(prefix):]


def _matrix_actor_id(value: Any) -> str:
    prefix = "matrix:user:"
    if not isinstance(value, str) or not value.startswith(prefix):
        raise MatrixV2Error("Matrix actor identity is invalid")
    user_id = value[len(prefix):]
    if not user_id.startswith("@") or ":" not in user_id:
        raise MatrixV2Error("Matrix actor identity is invalid")
    return user_id


class MatrixActionSinkV2:
    def __init__(
        self,
        *,
        room_id: str,
        client: MatrixClientLike,
        backstop: SendBackstop,
        receipt_sink: Callable[[dict[str, Any]], None],
        max_request_ids: int = 4096,
    ) -> None:
        if (
            not isinstance(room_id, str)
            or not room_id
            or not callable(receipt_sink)
        ):
            raise ValueError("Matrix action binding is invalid")
        if not isinstance(backstop, SendBackstop):
            raise ValueError("Matrix action backstop is invalid")
        if (
            isinstance(max_request_ids, bool)
            or not isinstance(max_request_ids, int)
            or not 1 <= max_request_ids <= 100000
        ):
            raise ValueError("Matrix action capacity is invalid")
        self.room_id = room_id
        self.client = client
        self.backstop = backstop
        self.receipt_sink = receipt_sink
        self.max_request_ids = max_request_ids
        self._consumed: set[str] = set()
        self._lock = threading.RLock()

    def _receipt(self, request_id: str, delivery: str, detail: str | None = None) -> None:
        self.receipt_sink(
            transport_receipt(request_id, delivery, detail=detail)
        )

    def _fail(self, request_id: str, detail: str, cause: Exception | None = None) -> None:
        try:
            self._receipt(request_id, "failed", detail)
        except Exception as receipt_error:
            raise MatrixV2Error(
                "Matrix action and receipt status are unknown"
            ) from receipt_error
        raise MatrixV2Error("Matrix action failed") from cause

    def __call__(self, request_id: str, action: dict[str, Any]) -> None:
        if not isinstance(request_id, str) or not request_id:
            raise MatrixV2Error("Matrix action correlation is invalid")
        with self._lock:
            if request_id in self._consumed:
                raise MatrixV2Error("Matrix action request was already consumed")
            if len(self._consumed) >= self.max_request_ids:
                raise MatrixV2Error("Matrix action capacity is exhausted")
            self._consumed.add(request_id)
        if self.backstop.try_acquire(self.room_id) > 0:
            self._fail(request_id, "send-backstop")
        try:
            accepted = copy.deepcopy(action)
            transaction = "nunchi-" + hashlib.sha256(
                request_id.encode("utf-8")
            ).hexdigest()
            if accepted.get("kind") == "message":
                content = accepted.get("content")
                if (
                    not isinstance(content, str)
                    or not content
                    or len(content.encode("utf-8")) > MAX_MESSAGE_BYTES
                ):
                    raise MatrixV2Error("Matrix message is invalid")
                reply = accepted.get("reply_to_event_id")
                mentions = tuple(
                    dict.fromkeys(
                        _matrix_actor_id(value)
                        for value in accepted.get("mention_actor_ids", [])
                    )
                )
                self.client.send_message(
                    self.room_id,
                    transaction,
                    content,
                    reply_to_event_id=(
                        _matrix_event_id(reply) if reply is not None else None
                    ),
                    mention_user_ids=mentions,
                )
            elif accepted.get("kind") == "reaction":
                reaction = accepted.get("reaction")
                if not isinstance(reaction, str) or not reaction:
                    raise MatrixV2Error("Matrix reaction is invalid")
                self.client.send_reaction(
                    self.room_id,
                    transaction,
                    _matrix_event_id(accepted.get("target_event_id")),
                    reaction,
                )
            else:
                raise MatrixV2Error("Matrix action kind is unsupported")
        except Exception as exc:
            self._fail(request_id, "matrix-api-failure", exc)
        try:
            self._receipt(request_id, "sent")
        except Exception as exc:
            raise MatrixV2Error(
                "Matrix send receipt persistence is unknown"
            ) from exc


def _timeline(sync: dict[str, Any], room_id: str) -> tuple[str, list[dict[str, Any]]]:
    next_batch = sync.get("next_batch")
    rooms = sync.get("rooms") or {}
    joined = rooms.get("join") if isinstance(rooms, dict) else None
    room = joined.get(room_id) if isinstance(joined, dict) else None
    timeline = room.get("timeline") if isinstance(room, dict) else None
    events = timeline.get("events", []) if isinstance(timeline, dict) else []
    if (
        not isinstance(next_batch, str)
        or not next_batch
        or not isinstance(events, list)
        or len(events) > 1000
        or any(not isinstance(event, dict) for event in events)
    ):
        raise MatrixV2Error("Matrix sync timeline is invalid")
    return next_batch, events


class MatrixRoomAdapterV2:
    def __init__(
        self,
        arguments: argparse.Namespace,
        *,
        client: MatrixClientLike,
        self_user_id: str | None = None,
    ) -> None:
        self.arguments = arguments
        self.client = client
        self.self_user_id = self_user_id or client.whoami()
        if (
            not isinstance(self.self_user_id, str)
            or not self.self_user_id.startswith("@")
            or ":" not in self.self_user_id
        ):
            raise MatrixV2Error("Matrix self identity is invalid")
        self.source = MatrixEventSourceV2(
            allowed_room_ids=frozenset({arguments.room_id})
        )
        self.cursor = DurableCursorStoreV2(
            arguments.state,
            platform="matrix",
            room_id=arguments.room_id,
            cursor_type=str,
        )
        try:
            self.native: NativeRuntimeV2 = build_native_runtime(
                arguments,
                participant_actor_id=MatrixEventSourceV2.actor_id(self.self_user_id),
                platform="matrix",
                room_id=arguments.room_id,
                continuity_scope_id=f"matrix:room:{arguments.room_id}",
                continuity="session-only",
                has_restart_gap=True,
                event_visibility={
                    "message": "history-and-live",
                    "reaction": "history-and-live",
                    "membership": "history-and-live",
                },
                action_sink_factory=lambda sink: MatrixActionSinkV2(
                    room_id=arguments.room_id,
                    client=client,
                    backstop=SendBackstop(
                        arguments.max_sends,
                        arguments.send_window_seconds,
                    ),
                    receipt_sink=sink,
                ),
            )
        except Exception:
            self.cursor.close()
            raise

    def poll_once(self) -> dict[str, Any]:
        since = self.cursor.load()
        sync = self.client.sync(since, timeout_ms=self.arguments.sync_timeout_ms)
        next_batch, events = _timeline(sync, self.arguments.room_id)
        normalized = [
            self.source.native_input(self.arguments.room_id, event)
            for event in events
        ]
        if since is None:
            dispositions = self.native.runtime.observe_context_batch(normalized)
            opportunity = None
            mode = "initial-context"
        else:
            accepted = self.native.runtime.accept_batch(normalized)
            dispositions = accepted.observation_dispositions
            opportunity = accepted.opportunity
            mode = "live"
        # Checkpoint before any participant effect. A crash never turns the
        # same transport batch into a durable replay obligation.
        self.cursor.save(next_batch)
        results = (
            self.native.runtime.drain(opportunity)
            if opportunity is not None
            else ()
        )
        return {
            "mode": mode,
            "event_count": len(events),
            "dispositions": dispositions,
            "results": results,
        }

    def close(self) -> None:
        self.native.close()
        self.cursor.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nunchi-matrix",
        description=(
            "Run one exact Matrix room as a Nunchi V2 participant. "
            "Participant command arguments must come last."
        ),
    )
    parser.add_argument("--homeserver", required=True)
    parser.add_argument("--room-id", required=True)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--token-env", default="NUNCHI_MATRIX_TOKEN")
    parser.add_argument("--allow-insecure-http", action="store_true")
    parser.add_argument("--sync-timeout-ms", type=int, default=30000)
    parser.add_argument("--poll-delay-seconds", type=float, default=1)
    parser.add_argument("--max-sends", type=int, default=3)
    parser.add_argument("--send-window-seconds", type=float, default=30)
    parser.add_argument("--once", action="store_true")
    add_participant_arguments(parser)
    return parser


def _configuration(arguments: argparse.Namespace) -> tuple[MatrixClientV2, str]:
    if _ENV_NAME_RE.fullmatch(arguments.token_env) is None:
        raise MatrixV2Error("Matrix token environment name is invalid")
    token = os.environ.get(arguments.token_env)
    if not token:
        raise MatrixV2Error("Matrix token is unavailable")
    if (
        isinstance(arguments.poll_delay_seconds, bool)
        or not 0 <= arguments.poll_delay_seconds <= 300
        or isinstance(arguments.max_sends, bool)
        or not 1 <= arguments.max_sends <= 1000
        or isinstance(arguments.send_window_seconds, bool)
        or not 1 <= arguments.send_window_seconds <= 3600
    ):
        raise MatrixV2Error("Matrix runtime limits are invalid")
    client = MatrixClientV2(
        arguments.homeserver,
        token,
        room_id=arguments.room_id,
        allow_insecure_http=arguments.allow_insecure_http,
    )
    return client, client.whoami()


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    try:
        client, self_user_id = _configuration(arguments)
        adapter = MatrixRoomAdapterV2(
            arguments,
            client=client,
            self_user_id=self_user_id,
        )
    except Exception:
        print("nunchi-matrix: V2 configuration is invalid", file=sys.stderr)
        return 2
    try:
        while True:
            try:
                result = adapter.poll_once()
                logger.info(
                    "Matrix V2 poll mode=%s events=%d opportunities=%d",
                    result["mode"],
                    result["event_count"],
                    len(result["results"]),
                )
            except Exception:
                logger.error("Matrix V2 poll failed")
                if arguments.once:
                    return 1
            if arguments.once:
                return 0
            time.sleep(arguments.poll_delay_seconds)
    except KeyboardInterrupt:
        return 0
    finally:
        adapter.close()


__all__ = [
    "MatrixActionSinkV2",
    "MatrixClientV2",
    "MatrixRoomAdapterV2",
    "MatrixV2Error",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
