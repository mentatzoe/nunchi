"""The probe's in-process stand-ins: the room's transport, and the scripted model endpoints.

`StandInRoomClient` stands in for the shared Discord transport
(`nunchi-mcp-discord`) that `ClaudeCodeRoomRuntime` and `CodexRoomRunner`
take as their ``client``. Only Discord itself is stood in for: every call
after the registration goes through the transport's own `ToolExecutor`
(`nunchi.mcp_discord.tools`), with its `ToolAuthorizer`, its argument checks
(a snowflake channel and reply target, non-empty content of at most 2000
characters), its send backstop and its acknowledgement shape, so the stand-in
refuses what the real transport refuses. As the transport's server does, it
answers the registration with the exact attestation and refuses every other
call before it. It keeps a wire log of every call and the room's echo of each
post, which the probe delivers back as the shared transport would.

`ScriptedAttention` is an OpenAI-compatible chat endpoint that answers
attention offline: it wakes for the messages the probe names and lets
everything else pass. `ScriptedCodexAgent` and `ScriptedHermesAgent` drive
the conformance kit's scripted model endpoints as a minimal agent that posts
one answer. Only ``--scripted`` runs use these three.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
import time
from typing import Any

from nunchi.attention_questions import answers_leaning
from nunchi.mcp_discord.authorization import ToolAuthorizer
from nunchi.mcp_discord.config import Config
from nunchi.mcp_discord.ratelimit import SendBackstop
from nunchi.mcp_discord.tools import ToolExecutor

# Discord's epoch, in milliseconds: a snowflake's time is the milliseconds since it, above bit 22.
DISCORD_EPOCH_MS = 1_420_070_400_000


def snowflake(at: datetime, sequence: int = 0) -> str:
    """A Discord message id for a message sent at ``at``."""

    since = int(at.timestamp() * 1000) - DISCORD_EPOCH_MS
    return str((max(since, 1) << 22) | (sequence & 0x3FFFFF))


def timestamp(at: datetime) -> str:
    return at.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class JsonLines:
    """An append-only JSONL file, safe across threads."""

    def __init__(self, path: Any = None) -> None:
        self.path = path
        self.entries: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def write(self, entry: Mapping[str, Any]) -> None:
        record = {"at": timestamp(datetime.now(timezone.utc)), **entry}
        with self._lock:
            self.entries.append(record)
            if self.path is not None:
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _result(body: Mapping[str, Any], *, error: bool = False) -> dict[str, Any]:
    return {"isError": error, "content": [{"type": "text", "text": json.dumps(body)}]}


class StandInRoomClient:
    """The shared Discord transport's MCP session, in process, for one participant in one room.

    ``secret`` is the participant's output key: every effect must carry an
    authorization made with it, as on the real transport. ``wire`` receives
    every call, without its authorization.
    """

    # The room lets the agent react, as Discord does for a bot with the permission.
    REACTIONS = {
        "supported": True,
        "authenticated": True,
        "operations": ["add", "remove"],
        "reactions": ["*"],
        "permissions_revision": "rehearsal-standin:v1",
    }

    def __init__(
        self,
        *,
        participant_id: str,
        room_id: str,
        actor_id: str,
        secret: bytes,
        display_name: str,
        wire: JsonLines | None = None,
    ) -> None:
        self.participant_id = participant_id
        self.room_id = room_id
        self.actor_id = actor_id
        self.native_actor_id = actor_id.removeprefix("discord:actor:")
        self.display_name = display_name
        self.authorizer = ToolAuthorizer(secret=secret, participant_routes={participant_id: frozenset({room_id})})
        # The transport's own executor, with its default send backstop; only Discord is stood in for.
        self.executor = ToolExecutor(
            _StandInDiscord(self),
            SendBackstop(Config.backstop_max_sends, Config.backstop_window_seconds),
            authorizer=self.authorizer,
        )
        self.registered = False
        self.wire = wire if wire is not None else JsonLines()
        # What reached the room: each post and reaction the transport made.
        self.effects: list[dict[str, Any]] = []
        self._echoes: list[dict[str, Any]] = []
        self._sequence = 0
        self._lock = threading.Lock()
        self.connected = 0

    # -- the client as the room connection uses it ------------------------------------

    def connect(self) -> str:
        self.connected += 1
        return "rehearsal-standin"

    def notifications(self) -> Iterator[tuple[str, Mapping[str, Any]]]:
        # The probe hands each room event to the connection itself.
        return iter(())

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        supplied = dict(arguments)
        authorization = supplied.pop("_nunchi_authorization", None)
        entry: dict[str, Any] = {
            "tool": name,
            "arguments": deepcopy(supplied),
            "request_id": authorization.get("request_id") if isinstance(authorization, Mapping) else None,
        }
        if name == "register_participant":
            # As the transport's server registers a session (`nunchi.mcp_discord._binding`).
            ok, why = self.authorizer.verify(
                authorization=authorization,
                tool=name,
                arguments=supplied,
                expected_participant_id=self.participant_id,
                expected_room_id=self.room_id,
            )
            body: dict[str, Any] = {"error": why}
            if ok:
                self.registered = True
                body = {
                    "registered": True,
                    "participant_id": self.participant_id,
                    "room_id": self.room_id,
                    "transport_self_actor_id": self.actor_id,
                }
        elif not self.registered:
            ok, body = False, {"error": "MCP session is not authenticated for a participant route"}
        else:
            body, ok = self.executor.call(
                name,
                dict(arguments),
                expected_route=(self.participant_id, self.room_id),
                expected_self_actor_id=self.actor_id,
            )
        entry["ok"] = ok
        if ok:
            entry["answer"] = body
        else:
            entry["refused"] = body.get("error")
        self.wire.write(entry)
        return _result(body, error=not ok)

    def _next_id(self, at: datetime) -> str:
        with self._lock:
            self._sequence += 1
            return snowflake(at, self._sequence)

    # -- what the probe reads -----------------------------------------------------------

    def take_echoes(self) -> list[dict[str, Any]]:
        """The room's own copy of each post since the last call: the transport shows the bot's messages."""

        with self._lock:
            echoes, self._echoes = self._echoes, []
        return echoes

    def notification(self, event: Mapping[str, Any], actors: Mapping[str, Any], delivery_id: str) -> dict[str, Any]:
        """One room event as the shared transport notifies it."""

        return {
            "schema_version": 2,
            "delivery_id": delivery_id,
            "room_id": self.room_id,
            "event": dict(event),
            "actors": dict(actors),
            "continuity_gap": False,
            "target_participant_id": self.participant_id,
            "transport_self_actor_id": self.actor_id,
        }

    def self_actor(self) -> dict[str, Any]:
        return {self.actor_id: {"display_name": self.display_name, "kind": "bot"}}


class _StandInDiscord:
    """Discord's REST API as the transport's `ToolExecutor` calls it (`nunchi.mcp_discord.tools.RestLike`).

    A post or reaction lands in the room: it is recorded as an effect, and a
    post is echoed back as Discord shows a bot its own message. The answer is
    Discord's own message object, which the executor checks and shapes.
    """

    def __init__(self, client: StandInRoomClient) -> None:
        self.client = client

    def create_message(self, channel_id: str, content: str, *, reply_to_message_id: str | None = None) -> dict[str, Any]:
        client = self.client
        now = datetime.now(timezone.utc)
        message_id = client._next_id(now)
        message: dict[str, Any] = {
            "id": message_id,
            "channel_id": channel_id,
            "author": {"id": client.native_actor_id, "username": client.display_name, "bot": True},
            "content": content,
            "mentions": [],
            "timestamp": timestamp(now),
        }
        event: dict[str, Any] = {
            "id": f"discord:message:{message_id}",
            "type": "message",
            "author_id": client.actor_id,
            "text": content,
            "mentioned_actor_ids": [],
            "mentions_room": False,
            "timestamp": timestamp(now),
        }
        if reply_to_message_id is not None:
            message["message_reference"] = {"message_id": reply_to_message_id, "channel_id": channel_id}
            event["reply_to_event_id"] = f"discord:message:{reply_to_message_id}"
        with client._lock:
            client.effects.append({"kind": "message", "message_id": message_id, "text": content, "reply_to": reply_to_message_id})
            client._echoes.append(event)
        return message

    def get_messages(self, channel_id: str, *, limit: int = 50, before: str | None = None) -> list[dict[str, Any]]:
        # The stand-in keeps no history of its own; the room's history is Nunchi's.
        return []

    def _reaction(self, channel_id: str, message_id: str, reaction: str, operation: str) -> None:
        effect = {"kind": "reaction", "channel_id": channel_id, "message_id": message_id, "reaction": reaction, "operation": operation}
        with self.client._lock:
            self.client.effects.append(effect)

    def add_reaction(self, channel_id: str, message_id: str, reaction: str) -> None:
        self._reaction(channel_id, message_id, reaction, "add")

    def remove_reaction(self, channel_id: str, message_id: str, reaction: str) -> None:
        self._reaction(channel_id, message_id, reaction, "remove")

    def reaction_capability(self, channel_id: str, expected_user_id: str) -> dict[str, Any]:
        return {"channel_id": channel_id, "actor_id": expected_user_id, "capability": dict(self.client.REACTIONS)}


# -- scripted attention ---------------------------------------------------------------------------


class _Server:
    """A local HTTP endpoint on its own thread."""

    def __init__(self, handler: type[BaseHTTPRequestHandler]) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, name="nunchi-rehearsal-scripted", daemon=True).start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


class ScriptedAttention:
    """Attention for a scripted run: an OpenAI-compatible chat endpoint on localhost.

    It wakes for a message whose text holds one of ``wake_phrases`` and lets
    every other message pass, with the typed answers the conformance checks
    use (`answers_leaning`). Each judgment is kept in ``judged``.
    """

    def __init__(self, wake_phrases: Iterable[str] = ()) -> None:
        self.wake_phrases = list(wake_phrases)
        self.judged: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._server = _Server(self._handler())

    @property
    def base_url(self) -> str:
        return self._server.base_url

    def close(self) -> None:
        self._server.close()

    def disposition(self, body: Mapping[str, Any]) -> tuple[str, str | None]:
        try:
            observation = json.loads(body["messages"][-1]["content"])["observation"]
            trigger = observation["trigger_event_id"]
            text = next(event.get("text", "") for event in observation["events"] if event["id"] == trigger)
        except (KeyError, IndexError, TypeError, ValueError, StopIteration):
            return "WAKE", None  # uncertainty wakes
        wake = any(phrase in (text or "") for phrase in self.wake_phrases)
        return ("WAKE" if wake else "SUPPRESS"), trigger

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        attention = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args: Any) -> None:
                pass

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    body = {}
                disposition, trigger = attention.disposition(body)
                with attention._lock:
                    attention.judged.append({"trigger_event_id": trigger, "disposition": disposition})
                answer = {
                    "id": f"scripted-{secrets.token_hex(4)}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": body.get("model", "scripted"),
                    "provider": "scripted",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": json.dumps(answers_leaning(disposition))},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost": 0},
                }
                payload = json.dumps(answer).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        return Handler


# -- scripted agents on the conformance kit's model endpoints ----------------------------------------


class ScriptedCodexAgent:
    """The kit's Responses endpoint for Codex, answering as an agent that posts once.

    The first model call of a turn gets a ``room_send`` call with ``answer``;
    the call after the tool's result gets a short final message, which ends
    Codex's turn. Every request Codex made is in ``model.requests``.
    """

    def __init__(self, answer: str) -> None:
        from nunchi.integrations.codex_app_server.integration import TOOL_NAMES
        from nunchi.integrations.codex_app_server_conformance import ScriptedModel

        self.answer = answer
        self.tool = TOOL_NAMES["send"]
        self.model = ScriptedModel()
        self.model.on_request = self._next

    @property
    def base_url(self) -> str:
        return self.model.base_url

    def _next(self) -> None:
        request = self.model.latest()
        items = [item for item in request.get("input", ()) if isinstance(item, Mapping)]
        if items and items[-1].get("type") == "function_call_output":
            self.model.reply({"text": "Posted my answer."})
        else:
            self.model.reply(
                {"tool": self.tool, "arguments": {"text": self.answer}, "call_id": f"call-{secrets.token_hex(6)}"}
            )

    def requests(self) -> list[dict[str, Any]]:
        return [*self.model.requests, *self.model.other_requests]

    def close(self) -> None:
        self.model.close()


class ScriptedHermesAgent:
    """The kit's chat endpoint for Hermes, answering every turn with ``answer``: its final answer is its post."""

    def __init__(self, answer: str) -> None:
        from nunchi.integrations.hermes_plugin_conformance import ScriptedModel

        self.answer = answer
        self.model = ScriptedModel()
        self.model.on_request = lambda: self.model.reply({"text": self.answer})

    @property
    def base_url(self) -> str:
        return self.model.base_url

    def requests(self) -> list[dict[str, Any]]:
        return list(self.model.requests)

    def close(self) -> None:
        self.model.close()
