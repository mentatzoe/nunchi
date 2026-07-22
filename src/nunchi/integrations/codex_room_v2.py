"""Installable Codex V2 room presence over the shared Discord MCP transport."""

from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import re
import time
import urllib.error
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..mcp_discord.events import DiscordEventSourceV2, MessageEvent, V2_NOTIFICATION_METHOD
from ..mcp_discord.v2 import MCPDiscordActionSinkV2
from ..observation import ObservationProvider
from ..policy import OperatorPolicySource
from ..receipts import ReloadingPolicyReceiptSink
from ..runtime import LiveRoomRuntime
from .codex_participant_v2 import CodexParticipantV2
from .mcp_transport_v2 import MCPTransportClientV2, MCPTransportV2Error


logger = logging.getLogger("nunchi.integrations.codex_room_v2")
_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


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
        client: MCPTransportClientV2,
        session_path: Path,
        codex_home: Path,
        participant_workspace: Path,
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
        self.self_user_id = self_user_id
        self.participant_id = participant_id
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
            codex_home=codex_home,
            working_directory=participant_workspace,
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
            continuation_fetch=self._fetch_context,
            classifier_transport=classifier_transport,
        )
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nunchi-codex-v2")
        self._futures: set[Future] = set()

    def _fetch_context(self, request: dict[str, Any]) -> dict[str, Any]:
        """Use only the already-authenticated, exact-room MCP history seam."""
        try:
            accepted = copy.deepcopy(request)
        except Exception as exc:
            raise CodexRoomV2Error("Discord continuation request is invalid") from exc
        return self.client.call_tool("read_history", accepted)

    @staticmethod
    def _message_event(params: dict[str, Any]) -> MessageEvent | None:
        required = {
            "guild_id",
            "channel_id",
            "message_id",
            "author_id",
            "author_name",
            "author_is_bot",
            "content",
            "timestamp",
            "mentioned_user_ids",
            "reply_to_message_id",
            "reply_to_author_id",
            "reply_to_author_name",
            "reply_to_author_is_bot",
            "reply_to_content",
            "mentions_room",
        }
        if set(params) != required:
            return None
        guild_id = params["guild_id"]
        channel_id = params["channel_id"]
        message_id = params["message_id"]
        author_id = params["author_id"]
        mentioned = params["mentioned_user_ids"]
        reply_id = params["reply_to_message_id"]
        reply_author_id = params["reply_to_author_id"]
        reply_author_name = params["reply_to_author_name"]
        reply_author_is_bot = params["reply_to_author_is_bot"]
        reply_content = params["reply_to_content"]
        timestamp = params["timestamp"]
        if (
            (guild_id is not None and (not isinstance(guild_id, str) or not guild_id.isdigit()))
            or not isinstance(channel_id, str)
            or not channel_id.isdigit()
            or not isinstance(message_id, str)
            or not message_id.isdigit()
            or not isinstance(author_id, str)
            or not author_id.isdigit()
            or not isinstance(params["author_name"], str)
            or not isinstance(params["author_is_bot"], bool)
            or not isinstance(params["content"], str)
            or (timestamp is not None and not isinstance(timestamp, str))
            or not isinstance(mentioned, list)
            or any(not isinstance(value, str) or not value.isdigit() for value in mentioned)
            or len(set(mentioned)) != len(mentioned)
            or (reply_id is not None and (not isinstance(reply_id, str) or not reply_id.isdigit()))
            or (
                reply_author_id is not None
                and (
                    not isinstance(reply_author_id, str)
                    or not reply_author_id.isdigit()
                )
            )
            or (reply_author_name is not None and not isinstance(reply_author_name, str))
            or (reply_author_is_bot is not None and not isinstance(reply_author_is_bot, bool))
            or (reply_content is not None and not isinstance(reply_content, str))
            or not isinstance(params["mentions_room"], bool)
        ):
            return None
        return MessageEvent(
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=message_id,
            author_id=author_id,
            author_name=params["author_name"],
            author_is_bot=params["author_is_bot"],
            content=params["content"],
            timestamp=timestamp,
            mentioned_user_ids=tuple(mentioned),
            reply_to_message_id=reply_id,
            reply_to_author_id=reply_author_id,
            reply_to_author_name=reply_author_name,
            reply_to_author_is_bot=reply_author_is_bot,
            reply_to_content=reply_content,
            mentions_room=params["mentions_room"],
            thread_root_message_id=None,
        )

    def backfill(self, bootstrap: dict[str, Any]) -> int:
        """Restore the post-subscription snapshot without scheduling wake work."""
        if not isinstance(bootstrap, dict) or set(bootstrap) != {"subscription", "history"}:
            raise CodexRoomV2Error("Discord subscription result is invalid")
        subscription = bootstrap["subscription"]
        history = bootstrap["history"]
        capabilities = (
            subscription.get("capabilities")
            if isinstance(subscription, dict)
            else None
        )
        if (
            not isinstance(subscription, dict)
            or subscription.get("participant_id") != self.participant_id
            or subscription.get("room_id") != self.channel_id
            or subscription.get("self_actor_id") != self.self_user_id
            or not isinstance(capabilities, list)
            or any(not isinstance(capability, str) for capability in capabilities)
            or len(set(capabilities)) != len(capabilities)
            or not {"subscribe_events", "read_history"} <= set(capabilities)
            or not isinstance(subscription.get("has_restart_gap"), bool)
            or not isinstance(history, dict)
            or set(history) != {"messages", "coverage"}
        ):
            raise CodexRoomV2Error("Discord subscription binding is invalid")
        messages = history.get("messages")
        coverage = history.get("coverage")
        if (
            not isinstance(messages, list)
            or len(messages) > 100
            or not isinstance(coverage, dict)
            or set(coverage)
            != {
                "max_events",
                "max_bytes",
                "returned_events",
                "returned_bytes",
                "truncated_by",
            }
            or isinstance(coverage.get("max_events"), bool)
            or not isinstance(coverage.get("max_events"), int)
            or not 1 <= coverage["max_events"] <= 100
            or isinstance(coverage.get("max_bytes"), bool)
            or not isinstance(coverage.get("max_bytes"), int)
            or not 1 <= coverage["max_bytes"] <= 32768
            or isinstance(coverage.get("returned_events"), bool)
            or coverage.get("returned_events") != len(messages)
            or isinstance(coverage.get("returned_bytes"), bool)
            or not isinstance(coverage.get("returned_bytes"), int)
            or not 0 <= coverage["returned_bytes"] <= coverage["max_bytes"]
            or not isinstance(coverage.get("truncated_by"), list)
            or any(
                item not in {"events", "bytes"}
                for item in coverage["truncated_by"]
            )
            or len(set(coverage["truncated_by"]))
            != len(coverage["truncated_by"])
            or len(messages) > coverage["max_events"]
        ):
            raise CodexRoomV2Error("Discord history result is invalid")
        validated: list[tuple[dict[str, Any], dict[str, Any]]] = []
        returned_bytes = 0
        for params in messages:
            event = self._message_event(params) if isinstance(params, dict) else None
            if event is None:
                raise CodexRoomV2Error("Discord history message is invalid")
            try:
                returned_bytes += len(
                    json.dumps(
                        params,
                        allow_nan=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
            except (TypeError, ValueError) as exc:
                raise CodexRoomV2Error("Discord history result is invalid") from exc
            native = self.source.native_input(event)
            if native.get("disposition") != "candidate-event":
                raise CodexRoomV2Error("Discord history message binding is invalid")
            validated.append((params, native))
        if returned_bytes != coverage["returned_bytes"]:
            raise CodexRoomV2Error("Discord history coverage is invalid")
        local_omission = len(validated) > self.history_limit
        remote_truncation = coverage["truncated_by"]
        retained_messages = validated[: self.history_limit]
        self.observation.has_restart_gap = subscription["has_restart_gap"]
        truncated_by = []
        if local_omission:
            truncated_by.append("events")
        truncated_by.extend(
            cause for cause in remote_truncation if cause not in truncated_by
        )
        self.observation.record_upstream_coverage(
            has_more_before=local_omission or bool(remote_truncation),
            has_more_after=False,
            has_gaps=False,
            truncated_by=truncated_by,
        )
        retained = 0
        for _params, native in reversed(retained_messages):
            self.observation.ingest(native)
            retained += 1
        return retained

    def accept_notification(self, params: dict[str, Any]) -> str:
        if not isinstance(params, dict):
            raise CodexRoomV2Error("Discord V2 notification is invalid")
        if params.get("kind") == "continuity-boundary":
            expected_boundary = {
                "schema_version",
                "platform",
                "kind",
                "reason",
                "previous_gateway_session_id",
                "expected_gateway_sequence",
                "observed_gateway_sequence",
                "continuity",
                "has_restart_gap",
            }
            if (
                set(params) != expected_boundary
                or params.get("schema_version") != 2
                or params.get("platform") != "discord"
                or params.get("continuity") != "known-gap"
                or params.get("has_restart_gap") is not True
                or not isinstance(params.get("reason"), str)
            ):
                raise CodexRoomV2Error("Discord continuity boundary is invalid")
            self.observation.has_restart_gap = True
            return "continuity-gap-recorded"
        expected = {
            "schema_version",
            "platform",
            "guild_id",
            "channel_id",
            "gateway_session_id",
            "gateway_sequence",
            "gateway_self_user_id",
            "native_input",
        }
        if "continuation" in params:
            expected.add("continuation")
        guild_id = params.get("guild_id")
        channel_id = params.get("channel_id")
        if (
            set(params) != expected
            or params.get("schema_version") != 2
            or params.get("platform") != "discord"
            or (
                guild_id is not None
                and (not isinstance(guild_id, str) or not guild_id.isdigit())
            )
            or not isinstance(channel_id, str)
            or channel_id != self.channel_id
            or not isinstance(params.get("gateway_session_id"), str)
            or not params["gateway_session_id"]
            or isinstance(params.get("gateway_sequence"), bool)
            or not isinstance(params.get("gateway_sequence"), int)
            or params["gateway_sequence"] < 0
            or params.get("gateway_self_user_id") != self.self_user_id
        ):
            raise CodexRoomV2Error("Discord V2 notification binding is invalid")
        native = params.get("native_input")
        if not isinstance(native, dict):
            raise CodexRoomV2Error("Discord V2 notification lacks native input")
        if "continuation" in params:
            try:
                native = copy.deepcopy(native)
                native["continuation"] = copy.deepcopy(params["continuation"])
            except Exception as exc:
                raise CodexRoomV2Error(
                    "Discord V2 continuation is invalid"
                ) from exc
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
    parser.add_argument(
        "--transport-auth-env",
        default="NUNCHI_MCP_DISCORD_AUTH_TOKEN",
    )
    parser.add_argument("--channel-id", required=True)
    parser.add_argument("--self-user-id", required=True)
    parser.add_argument("--participant-id", required=True)
    parser.add_argument("--participant-name", default="Codex")
    parser.add_argument("--session-path", required=True, type=Path)
    parser.add_argument("--codex-home", required=True, type=Path)
    parser.add_argument("--participant-workspace", required=True, type=Path)
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
    if _ENV_NAME_RE.fullmatch(args.transport_auth_env) is None:
        logger.error("Codex V2 transport credential binding is invalid")
        return 2
    auth_token = os.environ.get(args.transport_auth_env)
    if not auth_token:
        logger.error("Codex V2 transport credential is unavailable")
        return 2
    try:
        client = MCPTransportClientV2(args.transport_url, auth_token)
    except MCPTransportV2Error:
        logger.error("Codex V2 transport configuration is invalid")
        return 2
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
            codex_home=args.codex_home,
            participant_workspace=args.participant_workspace,
            codex_bin=args.codex_bin,
            model=args.model,
            history_limit=args.history_limit,
        )
        restored = 0

        def _restore(bootstrap: dict[str, Any]) -> None:
            nonlocal restored
            restored = room.backfill(bootstrap)
            logger.info("restored %d bounded message(s) as context", restored)

        for params in client.stream_events(
            V2_NOTIFICATION_METHOD,
            on_subscribed=_restore,
        ):
            room.accept_notification(params)
            if args.once:
                room.wait_idle()
                return 0
    except (
        CodexRoomV2Error,
        MCPTransportV2Error,
        RuntimeError,
        OSError,
        urllib.error.URLError,
    ):
        logger.error("Codex V2 room failed")
        return 1
    finally:
        if room is not None:
            room.close()
    return 0


__all__ = ["CodexRoomV2", "CodexRoomV2Error", "main"]
