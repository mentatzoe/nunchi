"""One-chat Telegram V2 reference adapter over the shared live runtime."""

from __future__ import annotations

import argparse
import copy
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
from .v2 import TelegramEventSourceV2


logger = logging.getLogger("nunchi.adapters.telegram_v2")
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


class TelegramV2Error(RuntimeError):
    pass


class TelegramClientLike(Protocol):
    def get_me(self) -> dict[str, Any]: ...

    def get_updates(
        self,
        offset: int | None,
        *,
        timeout_seconds: int,
        limit: int,
    ) -> list[dict[str, Any]]: ...

    def send_message(
        self,
        chat_id: str,
        content: str,
        *,
        reply_to_message_id: int | None,
    ) -> int: ...

    def set_reaction(
        self,
        chat_id: str,
        message_id: int,
        reaction: str,
    ) -> None: ...


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
        raise TelegramV2Error("Telegram network request failed") from exc
    with response:
        payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise TelegramV2Error("Telegram response exceeded its size budget")
        return int(response.status), payload


def _api_base(value: str, *, allow_insecure_http: bool) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 8192
        or any(ord(character) <= 32 or ord(character) == 127 for character in value)
        or not isinstance(allow_insecure_http, bool)
    ):
        raise TelegramV2Error("Telegram API base is invalid")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise TelegramV2Error("Telegram API base is invalid") from exc
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
        raise TelegramV2Error("Telegram API base is invalid")
    return value.rstrip("/")


class TelegramClientV2:
    def __init__(
        self,
        token: str,
        *,
        api_base: str = "https://api.telegram.org",
        allow_insecure_http: bool = False,
        http: HttpCall = _urllib_call,
    ) -> None:
        if not is_bounded_ascii_credential(token) or "/" in token:
            raise TelegramV2Error("Telegram client binding is invalid")
        self.token = token
        self.api_base = _api_base(
            api_base,
            allow_insecure_http=allow_insecure_http,
        )
        self.http = http

    def _call(
        self,
        method: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: float = 30,
    ) -> Any:
        body = json.dumps(
            arguments or {},
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        encoded_token = urllib.parse.quote(self.token, safe=":")
        status, raw = self.http(
            "POST",
            f"{self.api_base}/bot{encoded_token}/{method}",
            {"Accept": "application/json", "Content-Type": "application/json"},
            body,
            timeout,
        )
        if status < 200 or status >= 300:
            raise TelegramV2Error(
                f"Telegram API request failed with status {status}"
            )
        try:
            document = _strict_json(raw)
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            raise TelegramV2Error("Telegram API returned invalid JSON") from exc
        if (
            not isinstance(document, dict)
            or document.get("ok") is not True
            or "result" not in document
        ):
            raise TelegramV2Error("Telegram API rejected the request")
        return document["result"]

    def get_me(self) -> dict[str, Any]:
        result = self._call("getMe")
        if not isinstance(result, dict):
            raise TelegramV2Error("Telegram account identity is unavailable")
        user_id = result.get("id")
        if isinstance(user_id, bool) or not isinstance(user_id, int):
            raise TelegramV2Error("Telegram account identity is unavailable")
        return copy.deepcopy(result)

    def get_updates(
        self,
        offset: int | None,
        *,
        timeout_seconds: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        if (
            offset is not None
            and (isinstance(offset, bool) or not isinstance(offset, int))
        ):
            raise TelegramV2Error("Telegram update cursor is invalid")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or not 0 <= timeout_seconds <= 50
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise TelegramV2Error("Telegram polling limits are invalid")
        arguments: dict[str, Any] = {
            "timeout": timeout_seconds,
            "limit": limit,
            "allowed_updates": [
                "message",
                "chat_member",
                "my_chat_member",
                "message_reaction",
            ],
        }
        if offset is not None:
            arguments["offset"] = offset
        result = self._call(
            "getUpdates",
            arguments,
            timeout=max(30.0, timeout_seconds + 15.0),
        )
        if (
            not isinstance(result, list)
            or len(result) > limit
            or any(not isinstance(update, dict) for update in result)
        ):
            raise TelegramV2Error("Telegram updates response is invalid")
        return copy.deepcopy(result)

    def send_message(
        self,
        chat_id: str,
        content: str,
        *,
        reply_to_message_id: int | None,
    ) -> int:
        arguments: dict[str, Any] = {
            "chat_id": chat_id,
            "text": content,
            "link_preview_options": {"is_disabled": True},
        }
        if reply_to_message_id is not None:
            arguments["reply_parameters"] = {
                "message_id": reply_to_message_id,
                "allow_sending_without_reply": False,
            }
        result = self._call("sendMessage", arguments)
        message_id = result.get("message_id") if isinstance(result, dict) else None
        if isinstance(message_id, bool) or not isinstance(message_id, int):
            raise TelegramV2Error("Telegram send result is invalid")
        return message_id

    def set_reaction(
        self,
        chat_id: str,
        message_id: int,
        reaction: str,
    ) -> None:
        result = self._call(
            "setMessageReaction",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "reaction": [{"type": "emoji", "emoji": reaction}],
            },
        )
        if result is not True:
            raise TelegramV2Error("Telegram reaction result is invalid")


def _telegram_target(value: Any, chat_id: str) -> int:
    prefix = f"telegram:message:{chat_id}:"
    if not isinstance(value, str) or not value.startswith(prefix):
        raise TelegramV2Error("Telegram message identity is invalid")
    raw = value[len(prefix):]
    try:
        result = int(raw)
    except ValueError as exc:
        raise TelegramV2Error("Telegram message identity is invalid") from exc
    if result < 0 or str(result) != raw:
        raise TelegramV2Error("Telegram message identity is invalid")
    return result


class TelegramActionSinkV2:
    def __init__(
        self,
        *,
        chat_id: str,
        client: TelegramClientLike,
        backstop: SendBackstop,
        receipt_sink: Callable[[dict[str, Any]], None],
        max_request_ids: int = 4096,
    ) -> None:
        if not isinstance(chat_id, str) or not chat_id or not callable(receipt_sink):
            raise ValueError("Telegram action binding is invalid")
        if not isinstance(backstop, SendBackstop):
            raise ValueError("Telegram action backstop is invalid")
        if (
            isinstance(max_request_ids, bool)
            or not isinstance(max_request_ids, int)
            or not 1 <= max_request_ids <= 100000
        ):
            raise ValueError("Telegram action capacity is invalid")
        self.chat_id = chat_id
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
            raise TelegramV2Error(
                "Telegram action and receipt status are unknown"
            ) from receipt_error
        raise TelegramV2Error("Telegram action failed") from cause

    def _unknown(self, request_id: str, detail: str, cause: Exception) -> None:
        try:
            self._receipt(request_id, "unknown", detail)
        except Exception as receipt_error:
            raise TelegramV2Error(
                "Telegram action and receipt status are unknown"
            ) from receipt_error
        raise TelegramV2Error("Telegram action outcome is unknown") from cause

    def __call__(self, request_id: str, action: dict[str, Any]) -> None:
        if not isinstance(request_id, str) or not request_id:
            raise TelegramV2Error("Telegram action correlation is invalid")
        with self._lock:
            if request_id in self._consumed:
                raise TelegramV2Error("Telegram action request was already consumed")
            if len(self._consumed) >= self.max_request_ids:
                raise TelegramV2Error("Telegram action capacity is exhausted")
            self._consumed.add(request_id)
        try:
            accepted = copy.deepcopy(action)
            if accepted.get("kind") == "message":
                content = accepted.get("content")
                if not isinstance(content, str) or not content or len(content) > 4096:
                    raise TelegramV2Error("Telegram message is invalid")
                if accepted.get("mention_actor_ids"):
                    raise TelegramV2Error(
                        "Telegram exact outbound mentions are unavailable"
                    )
                reply = accepted.get("reply_to_event_id")
                operation = (
                    "message",
                    content,
                    (
                        _telegram_target(reply, self.chat_id)
                        if reply is not None
                        else None
                    ),
                )
            elif accepted.get("kind") == "reaction":
                reaction = accepted.get("reaction")
                if not isinstance(reaction, str) or not reaction:
                    raise TelegramV2Error("Telegram reaction is invalid")
                operation = (
                    "reaction",
                    _telegram_target(
                        accepted.get("target_event_id"),
                        self.chat_id,
                    ),
                    reaction,
                )
            else:
                raise TelegramV2Error("Telegram action kind is unsupported")
        except Exception as exc:
            self._fail(request_id, "invalid-action", exc)
        if self.backstop.try_acquire(self.chat_id) > 0:
            self._fail(request_id, "send-backstop")
        try:
            if operation[0] == "message":
                result = self.client.send_message(
                    self.chat_id,
                    operation[1],
                    reply_to_message_id=operation[2],
                )
                if (
                    isinstance(result, bool)
                    or not isinstance(result, int)
                    or result < 1
                ):
                    raise TelegramV2Error("Telegram message result is invalid")
            else:
                result = self.client.set_reaction(
                    self.chat_id,
                    operation[1],
                    operation[2],
                )
                if result is not None:
                    raise TelegramV2Error("Telegram reaction result is invalid")
        except Exception as exc:
            self._unknown(request_id, "telegram-api-outcome-unknown", exc)
        try:
            self._receipt(request_id, "sent")
        except Exception as exc:
            raise TelegramV2Error(
                "Telegram send receipt persistence is unknown"
            ) from exc


def _ordered_updates(updates: list[dict[str, Any]]) -> tuple[int | None, list[dict[str, Any]]]:
    previous: int | None = None
    for update in updates:
        update_id = update.get("update_id")
        if (
            isinstance(update_id, bool)
            or not isinstance(update_id, int)
            or update_id < 0
            or (previous is not None and update_id <= previous)
        ):
            raise TelegramV2Error("Telegram update order is invalid")
        previous = update_id
    return (previous + 1 if previous is not None else None), updates


class TelegramChatAdapterV2:
    def __init__(
        self,
        arguments: argparse.Namespace,
        *,
        client: TelegramClientLike,
        self_user: dict[str, Any] | None = None,
    ) -> None:
        self.arguments = arguments
        self.client = client
        identity = copy.deepcopy(self_user if self_user is not None else client.get_me())
        user_id = identity.get("id") if isinstance(identity, dict) else None
        if (
            isinstance(user_id, bool)
            or not isinstance(user_id, int)
            or user_id < 1
            or identity.get("is_bot") is not True
        ):
            raise TelegramV2Error("Telegram self identity is invalid")
        self.source = TelegramEventSourceV2(
            allowed_chat_ids=frozenset({arguments.chat_id})
        )
        self.cursor = DurableCursorStoreV2(
            arguments.state,
            platform="telegram",
            room_id=arguments.chat_id,
            cursor_type=int,
        )
        try:
            self.native: NativeRuntimeV2 = build_native_runtime(
                arguments,
                participant_actor_id=TelegramEventSourceV2.actor_id(user_id),
                platform="telegram",
                room_id=arguments.chat_id,
                continuity_scope_id=f"telegram:chat:{arguments.chat_id}",
                continuity="session-only",
                has_restart_gap=True,
                event_visibility={
                    "message": "live-only",
                    "reaction": "unavailable",
                    "membership": "live-only",
                },
                action_sink_factory=lambda sink: TelegramActionSinkV2(
                    chat_id=arguments.chat_id,
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
        cursor = self.cursor.load()
        initial = cursor is None
        updates = self.client.get_updates(
            -1 if initial else cursor,
            timeout_seconds=(0 if initial else self.arguments.poll_timeout_seconds),
            limit=(1 if initial else 100),
        )
        next_cursor, ordered = _ordered_updates(updates)
        normalized = [self.source.native_input(update) for update in ordered]
        if initial:
            dispositions = self.native.runtime.observe_context_batch(normalized)
            opportunity = None
            mode = "initial-context"
            checkpoint = next_cursor if next_cursor is not None else 0
        else:
            accepted = self.native.runtime.accept_batch(normalized)
            dispositions = accepted.observation_dispositions
            opportunity = accepted.opportunity
            mode = "live"
            checkpoint = next_cursor if next_cursor is not None else cursor
        self.cursor.save(checkpoint)
        results = (
            self.native.runtime.drain(opportunity)
            if opportunity is not None
            else ()
        )
        return {
            "mode": mode,
            "update_count": len(ordered),
            "dispositions": dispositions,
            "results": results,
        }

    def close(self) -> None:
        self.native.close()
        self.cursor.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nunchi-telegram",
        description=(
            "Run one exact Telegram chat as a Nunchi V2 participant. "
            "Participant command arguments must come last."
        ),
    )
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--token-env", default="NUNCHI_TELEGRAM_TOKEN")
    parser.add_argument("--api-base", default="https://api.telegram.org")
    parser.add_argument("--allow-insecure-http", action="store_true")
    parser.add_argument("--poll-timeout-seconds", type=int, default=30)
    parser.add_argument("--poll-delay-seconds", type=float, default=1)
    parser.add_argument("--max-sends", type=int, default=3)
    parser.add_argument("--send-window-seconds", type=float, default=30)
    parser.add_argument("--once", action="store_true")
    add_participant_arguments(parser)
    return parser


def _configuration(
    arguments: argparse.Namespace,
) -> tuple[TelegramClientV2, dict[str, Any]]:
    if _ENV_NAME_RE.fullmatch(arguments.token_env) is None:
        raise TelegramV2Error("Telegram token environment name is invalid")
    token = os.environ.get(arguments.token_env)
    if not token:
        raise TelegramV2Error("Telegram token is unavailable")
    if (
        isinstance(arguments.poll_timeout_seconds, bool)
        or not 0 <= arguments.poll_timeout_seconds <= 50
        or isinstance(arguments.poll_delay_seconds, bool)
        or not 0 <= arguments.poll_delay_seconds <= 300
        or isinstance(arguments.max_sends, bool)
        or not 1 <= arguments.max_sends <= 1000
        or isinstance(arguments.send_window_seconds, bool)
        or not 1 <= arguments.send_window_seconds <= 3600
    ):
        raise TelegramV2Error("Telegram runtime limits are invalid")
    client = TelegramClientV2(
        token,
        api_base=arguments.api_base,
        allow_insecure_http=arguments.allow_insecure_http,
    )
    return client, client.get_me()


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    try:
        client, self_user = _configuration(arguments)
        adapter = TelegramChatAdapterV2(
            arguments,
            client=client,
            self_user=self_user,
        )
    except Exception:
        print("nunchi-telegram: V2 configuration is invalid", file=sys.stderr)
        return 2
    try:
        while True:
            try:
                result = adapter.poll_once()
                logger.info(
                    "Telegram V2 poll mode=%s updates=%d opportunities=%d",
                    result["mode"],
                    result["update_count"],
                    len(result["results"]),
                )
            except Exception:
                logger.error("Telegram V2 poll failed")
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
    "TelegramActionSinkV2",
    "TelegramChatAdapterV2",
    "TelegramClientV2",
    "TelegramV2Error",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
