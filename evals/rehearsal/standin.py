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
one answer. `ScriptedClaudeAgent` is the same agent as an Anthropic Messages
endpoint, for the real ``claude -p``, and `RefusingProxy` refuses, and names,
whatever else Claude Code tries to reach. Only ``--scripted`` runs use these.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
import time
from typing import Any
from urllib.parse import urlsplit

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
    def origin(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    @property
    def base_url(self) -> str:
        return f"{self.origin}/v1"

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


# -- the scripted Anthropic Messages endpoint for Claude Code, and what else it tries to reach ---------

# The request headers kept from Claude Code's model calls: never a key's.
_CLAUDE_HEADERS = ("anthropic-beta", "anthropic-version", "user-agent", "x-app")


def _message_events(model: str, blocks: list[dict[str, Any]], stop: str) -> Iterator[tuple[str, dict[str, Any]]]:
    """One assistant message as the Messages API streams it."""

    usage = {"input_tokens": 1, "output_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    message = {
        "id": f"msg_scripted_{secrets.token_hex(8)}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": usage,
    }
    yield "message_start", {"type": "message_start", "message": message}
    for index, block in enumerate(blocks):
        if block["type"] == "text":
            start: dict[str, Any] = {"type": "text", "text": ""}
            delta: dict[str, Any] = {"type": "text_delta", "text": block["text"]}
        else:
            start = {"type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}
            delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
        yield "content_block_start", {"type": "content_block_start", "index": index, "content_block": start}
        yield "content_block_delta", {"type": "content_block_delta", "index": index, "delta": delta}
        yield "content_block_stop", {"type": "content_block_stop", "index": index}
    yield "message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None}, "usage": {"output_tokens": 1}}
    yield "message_stop", {"type": "message_stop"}


class ScriptedClaudeAgent:
    """An Anthropic Messages endpoint for the real ``claude -p``, answering as an agent that posts once.

    Claude Code 2.1.289 calls ``POST /v1/messages?beta=true`` with ``stream``
    set and reads server-sent events (``message_start``, each content block's
    start, delta and stop, ``message_delta``, ``message_stop``). Only such a
    call is answered: a call that offers the room's send tool (``tool``) and
    carries no tool result yet gets a ``tool_use`` of it with ``answer``; a
    call that carries the result gets a short final text, which ends the
    turn; a streamed call without the room tools gets a short text. Anything
    else, a call without ``stream`` included, gets a 404 in the API's error
    shape: when Claude Code cannot read the stream it retries without it,
    and that fallback must fail the turn, not pass it. Every request is
    kept, with its body and a few headers, never a key's (``requests``).
    """

    def __init__(self, answer: str, tool: str) -> None:
        self.answer = answer
        self.tool = tool
        self.seen: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._server = _Server(self._handler())

    @property
    def base_url(self) -> str:
        # Claude Code adds /v1/messages itself, as it does on OpenRouter's Anthropic endpoint.
        return self._server.origin

    def requests(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.seen)

    def close(self) -> None:
        self._server.close()

    def reply(self, body: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]], str]:
        """What the scripted agent answers: the request's kind, the content blocks, the stop reason."""

        tools = [tool.get("name") for tool in body.get("tools") or () if isinstance(tool, Mapping)]
        if self.tool not in tools:
            return "other", [{"type": "text", "text": "Room"}], "end_turn"
        messages = body.get("messages") or []
        last = messages[-1] if messages and isinstance(messages[-1], Mapping) else {}
        content = last.get("content")
        if isinstance(content, list) and any(isinstance(block, Mapping) and block.get("type") == "tool_result" for block in content):
            return "agent", [{"type": "text", "text": "Posted my answer."}], "end_turn"
        call = {"type": "tool_use", "id": f"toolu_scripted_{secrets.token_hex(8)}", "name": self.tool, "input": {"text": self.answer}}
        return "agent-tool-call", [call], "tool_use"

    def _keep(self, kind: str, handler: BaseHTTPRequestHandler, body: Any) -> None:
        authorization = handler.headers.get("Authorization") or ""
        entry = {
            "kind": kind,
            "method": handler.command,
            "path": handler.path,
            "headers": {name: handler.headers[name] for name in _CLAUDE_HEADERS if name in handler.headers},
            # Which credential Claude Code sent, never its value.
            "credential": "bearer" if authorization.startswith("Bearer ") else ("x-api-key" if handler.headers.get("x-api-key") else None),
            "body": body,
        }
        with self._lock:
            self.seen.append(entry)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        agent = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args: Any) -> None:
                pass

            def _json(self, status: int, document: Mapping[str, Any]) -> None:
                payload = json.dumps(document).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _not_found(self, body: Any = None) -> None:
                agent._keep("unknown", self, body)
                self._json(404, {"type": "error", "error": {"type": "not_found_error", "message": f"scripted: no {self.path}"}})

            def do_GET(self) -> None:  # noqa: N802
                self._not_found()

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    body = {}
                if urlsplit(self.path).path != "/v1/messages" or not isinstance(body, Mapping) or not body.get("stream"):
                    self._not_found(body)
                    return
                kind, blocks, stop = agent.reply(body)
                agent._keep(kind, self, body)
                model = str(body.get("model") or "scripted")
                # A stream without a length: it ends when the connection closes.
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                for name, data in _message_events(model, blocks, stop):
                    self.wfile.write(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode())
                self.wfile.flush()

        return Handler


class RefusingProxy:
    """An HTTP proxy on localhost that refuses every request and records where it was going.

    A scripted Claude Code run points the proxy variables at it, with
    ``NO_PROXY`` naming only this machine, so the scripted endpoint is reached
    directly and anything else sent through the proxy settings is refused
    here (HTTP 403) and named: the ``host:port`` of each ``CONNECT``, or of a
    plain request's URL. A connection that ignores the proxy settings never
    comes here and is not seen.
    """

    VARIABLES = ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy")
    LOCAL = "127.0.0.1,localhost"

    def __init__(self) -> None:
        self.attempts: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._server = _Server(self._handler())

    @property
    def url(self) -> str:
        return self._server.origin

    def environment(self) -> dict[str, str]:
        """The proxy variables for a process that must reach only this machine."""

        return {**{name: self.url for name in self.VARIABLES}, "NO_PROXY": self.LOCAL, "no_proxy": self.LOCAL}

    def tried(self) -> list[dict[str, Any]]:
        """Each place something tried to reach, and how often, in the order first tried."""

        with self._lock:
            counts = Counter((attempt["method"], attempt["target"]) for attempt in self.attempts)
        return [{"method": method, "target": target, "count": count} for (method, target), count in counts.items()]

    def close(self) -> None:
        self._server.close()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args: Any) -> None:
                pass

            def _refuse(self) -> None:
                if self.command == "CONNECT":
                    target = self.path
                else:
                    parts = urlsplit(self.path)
                    target = parts.netloc or self.headers.get("Host") or "?"
                    if ":" not in target:
                        target += ":443" if parts.scheme == "https" else ":80"
                    length = int(self.headers.get("Content-Length") or 0)
                    if length:
                        self.rfile.read(length)
                with proxy._lock:
                    proxy.attempts.append({"method": self.command, "target": target})
                payload = b"rehearsal: offline; this proxy refuses every request\n"
                self.send_response(403)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                if self.command != "HEAD":
                    self.wfile.write(payload)

            do_CONNECT = do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _refuse

        return Handler
