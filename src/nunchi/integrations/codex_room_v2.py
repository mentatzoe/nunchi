"""Installable Codex V2 room presence over the shared Discord MCP transport."""

from __future__ import annotations

import argparse
import logging
import time
import urllib.error
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..authorization import PrivilegedActionGuard
from ..mcp_discord.events import DiscordEventSourceV2, MessageEvent, V2_NOTIFICATION_METHOD
from ..mcp_discord.v2 import MCPDiscordActionSinkV2
from ..observation import ObservationProvider
from ..policy import OperatorPolicySource
from ..receipts import ReloadingPolicyReceiptSink
from ..runtime import LiveRoomRuntime
from .codex_participant_v2 import CodexParticipantV2
from .codex_room_runner import TransportClient


logger = logging.getLogger("nunchi.integrations.codex_room_v2")


class CodexRoomV2Error(RuntimeError):
    pass


class CodexRoomV2:
    """One exact Codex participant binding in one exact Discord room."""

    def __init__(
        self,
        *,
        policy_path: Path,
        channel_id: str,
        self_user_id: str,
        participant_id: str,
        participant_name: str,
        client: TransportClient,
        session_path: Path,
        codex_bin: str = "codex",
        model: str | None = None,
        history_limit: int = 100,
        classifier_transport=None,
        participant=None,
        receipt_sink=None,
    ) -> None:
        if not channel_id.isdigit() or not self_user_id.isdigit():
            raise ValueError("Codex Discord identity and room must be exact snowflakes")
        if not participant_id or not 1 <= history_limit <= 100:
            raise ValueError("Codex V2 room configuration is invalid")
        self.channel_id = channel_id
        self.client = client
        self.history_limit = history_limit
        self.source = DiscordEventSourceV2(
            allowed_channel_ids=frozenset({channel_id})
        )
        self.policy_source = OperatorPolicySource(policy_path)
        initial_policy = self.policy_source.load()
        if initial_policy.attention.participant_id != participant_id:
            raise CodexRoomV2Error("operator policy does not bind this participant")
        self.receipt_sink = receipt_sink or ReloadingPolicyReceiptSink(
            self.policy_source.load
        )
        self.observation = ObservationProvider(
            participant_id=participant_id,
            actor_id=f"discord:user:{self_user_id}",
            names=[participant_name],
            role="participant",
            platform="discord",
            room_id=channel_id,
            room_kind="group",
            continuity_scope_id=f"discord:channel:{channel_id}",
            continuity="session-only",
            has_restart_gap=True,
            event_visibility={
                "message": "history-and-live",
                "reaction": "live-only",
                "membership": "unavailable",
            },
        )
        participant_callable = participant or CodexParticipantV2(
            codex_bin=codex_bin,
            participant_name=participant_name,
            session_path=session_path,
            model=model,
        )
        action_sink = MCPDiscordActionSinkV2(
            channel_id=channel_id,
            client=client,
            receipt_sink=self.receipt_sink,
        )
        self.runtime = LiveRoomRuntime(
            observation=self.observation,
            policy_loader=self.policy_source.load,
            receipt_sink=self.receipt_sink,
            participant=participant_callable,
            correlated_action_sink=action_sink,
            classifier_transport=classifier_transport,
            authorization_guard=PrivilegedActionGuard(self.policy_source.load),
        )
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nunchi-codex-v2")
        self._futures: set[Future] = set()

    @staticmethod
    def _message_event(params: dict[str, Any]) -> MessageEvent | None:
        required = ("channel_id", "message_id", "author_id", "content")
        if any(name not in params for name in required):
            return None
        mentioned = params.get("mentioned_user_ids") or []
        if not isinstance(mentioned, list):
            return None
        return MessageEvent(
            guild_id=params.get("guild_id"),
            channel_id=str(params.get("channel_id") or ""),
            message_id=str(params.get("message_id") or ""),
            author_id=str(params.get("author_id") or ""),
            author_name=str(params.get("author_name") or ""),
            author_is_bot=bool(params.get("author_is_bot", False)),
            content=params.get("content") if isinstance(params.get("content"), str) else "",
            timestamp=(params.get("timestamp") if isinstance(params.get("timestamp"), str) else None),
            mentioned_user_ids=tuple(str(value) for value in mentioned),
            reply_to_message_id=(
                str(params["reply_to_message_id"])
                if params.get("reply_to_message_id") is not None
                else None
            ),
            reply_to_author_id=None,
            reply_to_author_name=None,
            reply_to_author_is_bot=None,
            reply_to_content=None,
            mentions_room=bool(params.get("mentions_room", False)),
            thread_root_message_id=(
                str(params["thread_root_message_id"])
                if params.get("thread_root_message_id") is not None
                else None
            ),
        )

    def backfill(self) -> int:
        """Restore bounded history as context only; never schedule wake work."""
        result = self.client.call_tool(
            "read_history",
            {"channel_id": self.channel_id, "limit": self.history_limit},
        )
        messages = result.get("messages")
        if not isinstance(messages, list):
            raise CodexRoomV2Error("Discord history result is invalid")
        retained = 0
        for params in reversed(messages):
            event = self._message_event(params) if isinstance(params, dict) else None
            if event is None:
                continue
            native = self.source.native_input(event)
            if native.get("disposition") != "candidate-event":
                continue
            self.observation.ingest(native)
            retained += 1
        return retained

    def accept_notification(self, params: dict[str, Any]) -> str:
        if not isinstance(params, dict):
            raise CodexRoomV2Error("Discord V2 notification is invalid")
        if (
            params.get("schema_version") != 2
            or params.get("platform") != "discord"
            or str(params.get("channel_id") or "") != self.channel_id
        ):
            raise CodexRoomV2Error("Discord V2 notification binding is invalid")
        native = params.get("native_input")
        if not isinstance(native, dict):
            raise CodexRoomV2Error("Discord V2 notification lacks native input")
        accepted = self.runtime.accept(native)
        if accepted.opportunity is None:
            return accepted.observation_disposition
        self._futures = {future for future in self._futures if not future.done()}
        future = self._executor.submit(self.runtime.drain, accepted.opportunity)
        self._futures.add(future)
        return "scheduled"

    def wait_idle(self, timeout: float | None = None) -> tuple[tuple[dict[str, Any], ...], ...]:
        deadline = None if timeout is None else time.monotonic() + timeout
        results = []
        targets = tuple(self._futures)
        for future in targets:
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            results.append(future.result(timeout=remaining))
            self._futures.discard(future)
        return tuple(results)

    def close(self) -> None:
        self._executor.shutdown(wait=True)
        close = getattr(self.receipt_sink, "close", None)
        if callable(close):
            close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nunchi-codex-room-v2",
        description="Run one Codex V2 participant in one trusted Discord room.",
    )
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--transport-url", default="http://127.0.0.1:3993/mcp")
    parser.add_argument("--channel-id", required=True)
    parser.add_argument("--self-user-id", required=True)
    parser.add_argument("--participant-id", required=True)
    parser.add_argument("--participant-name", default="Codex")
    parser.add_argument("--session-path", required=True, type=Path)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--model")
    parser.add_argument("--history-limit", type=int, default=100)
    parser.add_argument("--once", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = _parser().parse_args(argv)
    client = TransportClient(args.transport_url)
    room: CodexRoomV2 | None = None
    try:
        client.initialize()
        room = CodexRoomV2(
            policy_path=args.policy,
            channel_id=args.channel_id,
            self_user_id=args.self_user_id,
            participant_id=args.participant_id,
            participant_name=args.participant_name,
            client=client,
            session_path=args.session_path,
            codex_bin=args.codex_bin,
            model=args.model,
            history_limit=args.history_limit,
        )
        restored = room.backfill()
        logger.info("restored %d bounded message(s) as context", restored)
        for params in client.stream_events(V2_NOTIFICATION_METHOD):
            room.accept_notification(params)
            if args.once:
                room.wait_idle()
                return 0
    except (CodexRoomV2Error, RuntimeError, OSError, urllib.error.URLError) as exc:
        logger.error("Codex V2 room failed: %s", exc)
        return 1
    finally:
        if room is not None:
            room.close()
    return 0


__all__ = ["CodexRoomV2", "CodexRoomV2Error", "main"]
