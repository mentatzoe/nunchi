"""The Hermes plugin under the turn conformance kit (#94 step 9e).

Each scenario runs inside a real Hermes gateway (`GatewayRunner` with a
platform adapter that records what it would send, Hermes's own gateway test
pattern) from a throwaway `HERMES_HOME`. Hermes discovers and loads the plugin
from that home's `plugins/` directory, with the plugin's own `plugin.yaml`, and
runs the agent's turns with its real agent loop. Only the model is scripted:
an OpenAI-compatible server on localhost, configured as Hermes's custom
endpoint, answers each of the agent's model calls with the scripted agent's
next step.

So the script reaches its turn exactly as a model would: the plugin's driver
injects the turn, `pre_llm_call` binds it, a ``finish`` step is the model's
final text (`transform_llm_output`), a ``call`` step is a tool call the model
makes, and what the agent is told comes back in Hermes's next model request.

Hermes must be importable (a clean, pinned install; see `.github/workflows`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import shutil
import tempfile
import threading
import time
from typing import Any

from ..attention import ParticipantProfile
from ..turn import SecretGuard
from ..turn_conformance import ScriptedAgent
from .hermes_plugin.plugin import PLUGIN_NAME, TOOL_NAMES, WAKE_MARKER, HermesRoomPlugin, HermesRoute

ROOM = "conformance-room"
TURN_USER = "nunchi-turns"
_STEP_SECONDS = 20.0
_PLUGIN_YAML = Path(__file__).parent / "hermes_plugin" / "plugin.yaml"
_KIT_PLUGIN_INIT = (
    '"""The Nunchi Hermes plugin, wired to the turn conformance kit."""\n'
    "from nunchi.integrations.hermes_plugin_conformance import register_for_kit as register\n"
)

# The scenario being set up: what `register_for_kit` builds the plugin from.
_PENDING: dict[str, Any] = {}
_ISOLATION: dict[str, Any] = {}


def hermes_available() -> bool:
    """Whether Hermes is installed, without importing it (its import has side effects)."""

    import importlib.util

    return all(importlib.util.find_spec(name) is not None for name in ("gateway", "hermes_cli", "run_agent"))


def isolate() -> Path:
    """A throwaway base for every Hermes home this process uses; call before importing Hermes.

    Importing Hermes points ``TMPDIR`` at ``$HERMES_HOME/cache/scratch`` unless it is
    already set (`hermes_bootstrap.export_scratch_tmp_env`). With no ``HERMES_HOME`` that
    is the user's own ``~/.hermes``, which the kit must never touch.
    """

    if "base" not in _ISOLATION:
        import atexit

        base = Path(tempfile.mkdtemp(prefix="nunchi-hermes-kit-"))
        (base / "tmp").mkdir()
        (base / "home").mkdir()
        os.environ.setdefault("TMPDIR", str(base / "tmp"))
        os.environ["HERMES_HOME"] = str(base / "home")
        _ISOLATION["base"] = base
        _ISOLATION["count"] = 0
        atexit.register(shutil.rmtree, base, True)
    return _ISOLATION["base"]


def register_for_kit(ctx: Any) -> None:
    """Hermes calls this for the kit's plugin directory: the plugin, with the kit's participant."""

    plugin = HermesRoomPlugin(
        profile=_PENDING["profile"],
        guard=_PENDING["guard"],
        route=_PENDING["route"],
        result_wait_seconds=_PENDING.get("result_wait_seconds", 5.0),
        start_timeout_seconds=_PENDING.get("start_timeout_seconds", 30.0),
    )
    plugin.register(ctx)
    _PENDING["plugin"] = plugin


# -- the model: the only scripted part ---------------------------------------------------


class ScriptedModel:
    """An OpenAI-compatible chat endpoint whose answers the scripted agent supplies.

    Only the agent's own model calls (those offering tools) are scripted. Hermes's
    auxiliary calls, such as naming the session, get a fixed answer.
    """

    def __init__(self) -> None:
        self._replies: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self.requests: list[dict[str, Any]] = []
        self.on_request: Any = None
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, name="nunchi-kit-model", daemon=True).start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def reply(self, reply: Mapping[str, Any]) -> None:
        self._replies.put(dict(reply))

    def count(self) -> int:
        with self._lock:
            return len(self.requests)

    def latest(self) -> dict[str, Any]:
        with self._lock:
            return self.requests[-1]

    def close(self) -> None:
        # Unblock any request still waiting for a step.
        for _ in range(4):
            self._replies.put({"text": ""})
        self._server.shutdown()
        self._server.server_close()

    def _answer(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if not request.get("tools"):
            return {"text": "Room"}
        with self._lock:
            self.requests.append(dict(request))
        if self.on_request is not None:
            self.on_request()
        try:
            return self._replies.get(timeout=_STEP_SECONDS * 3)
        except queue.Empty:
            return {"text": ""}

    def _handler(self):
        model = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args: Any) -> None:
                pass

            def _json(self, body: Mapping[str, Any]) -> None:
                payload = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:  # noqa: N802
                self._json({"object": "list", "data": [{"id": "conformance/model", "object": "model"}]})

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(length) or b"{}")
                if not self.path.endswith("/chat/completions"):
                    self._json({})
                    return
                reply = model._answer(request)
                message: dict[str, Any] = {"role": "assistant", "content": reply.get("text", "")}
                finish = "stop"
                if "tool" in reply:
                    message = {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": f"call_{model.count()}",
                                "type": "function",
                                "function": {"name": reply["tool"], "arguments": json.dumps(reply.get("arguments", {}))},
                            }
                        ],
                    }
                    finish = "tool_calls"
                usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
                if not request.get("stream"):
                    self._json(
                        {
                            "id": "conformance",
                            "object": "chat.completion",
                            "created": int(time.time()),
                            "model": "conformance/model",
                            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                            "usage": usage,
                        }
                    )
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Connection", "close")
                self.end_headers()
                delta: dict[str, Any] = {"role": "assistant"}
                if message.get("content"):
                    delta["content"] = message["content"]
                if message.get("tool_calls"):
                    delta["tool_calls"] = [dict(call, index=i) for i, call in enumerate(message["tool_calls"])]
                base = {"id": "conformance", "object": "chat.completion.chunk", "created": int(time.time()),
                        "model": "conformance/model"}
                for chunk in (
                    dict(base, choices=[{"index": 0, "delta": delta, "finish_reason": None}]),
                    dict(base, choices=[{"index": 0, "delta": {}, "finish_reason": finish}], usage=usage),
                ):
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                self.close_connection = True

        return Handler


# -- a real Hermes gateway in a throwaway home ------------------------------------------------


class HermesGateway:
    """A `GatewayRunner` with a recording platform adapter, on its own event loop."""

    def __init__(self, *, model: ScriptedModel, tool_search: str = "off", extra_config: Mapping[str, Any] | None = None) -> None:
        base = isolate()
        _ISOLATION["count"] += 1
        self.directory = base / f"scenario-{_ISOLATION['count']}"
        self.home = self.directory / "home"
        plugin_dir = self.home / "plugins" / PLUGIN_NAME
        plugin_dir.mkdir(parents=True)
        shutil.copyfile(_PLUGIN_YAML, plugin_dir / "plugin.yaml")
        (plugin_dir / "__init__.py").write_text(_KIT_PLUGIN_INIT, encoding="utf-8")
        config: dict[str, Any] = {
            "model": {"default": "conformance/model", "provider": "custom", "base_url": model.base_url,
                      "api_key": "sk-local-conformance"},
            "plugins": {"enabled": [PLUGIN_NAME], "entries": {PLUGIN_NAME: {"allow_gateway_injection": True}}},
            # Operator setup for a Nunchi room (integrations/hermes-plugin/README.md).
            "display": {"platforms": {"telegram": {"streaming": False, "tool_progress": "off"}}},
            "tools": {"tool_search": {"enabled": tool_search}},
        }
        for key, value in (extra_config or {}).items():
            config[key] = value
        # JSON is YAML: Hermes reads it as its config.yaml.
        (self.home / "config.yaml").write_text(json.dumps(config), encoding="utf-8")
        (self.home / ".env").write_text(f"TELEGRAM_ALLOWED_USERS=u1,u2,{TURN_USER}\n", encoding="utf-8")
        self._saved_env = {key: os.environ.get(key) for key in (
            "HERMES_HOME", "TELEGRAM_ALLOWED_USERS", "GATEWAY_ALLOWED_USERS", "GATEWAY_ALLOW_ALL_USERS")}
        os.environ["HERMES_HOME"] = str(self.home)
        os.environ["TELEGRAM_ALLOWED_USERS"] = f"u1,u2,{TURN_USER}"
        os.environ.pop("GATEWAY_ALLOWED_USERS", None)
        os.environ.pop("GATEWAY_ALLOW_ALL_USERS", None)
        import gateway.run as gateway_run  # only once HERMES_HOME is the throwaway home

        self._gateway_run = gateway_run
        self._saved_home = getattr(gateway_run, "_hermes_home", None)
        gateway_run._hermes_home = self.home
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self.loop.run_forever, name="nunchi-kit-gateway", daemon=True)
        self._thread.start()
        self.runner, self.adapter = self.run(self._start(), timeout=60)

    def run(self, coroutine: Any, timeout: float = 30) -> Any:
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout)

    async def _start(self) -> tuple[Any, Any]:
        from gateway.config import GatewayConfig, Platform, PlatformConfig
        from gateway.platforms.base import BasePlatformAdapter, SendResult
        from gateway.run import GatewayRunner
        from hermes_cli.plugins import discover_plugins

        class RecordingAdapter(BasePlatformAdapter):
            def __init__(self) -> None:
                super().__init__(
                    PlatformConfig(enabled=True, token="conformance", extra={"group_sessions_per_user": True}),
                    Platform.TELEGRAM,
                )
                self.sent: list[tuple[str, str]] = []
                self._running = True

            async def connect(self, *, is_reconnect: bool = False) -> bool:
                return True

            async def disconnect(self) -> None:
                self._mark_disconnected()

            async def send(self, chat_id, content, reply_to=None, metadata=None):
                self.sent.append((str(chat_id), content))
                return SendResult(success=True, message_id=f"sent-{len(self.sent)}")

            async def send_typing(self, chat_id, metadata=None):
                return None

            async def get_chat_info(self, chat_id):
                return {"id": chat_id, "type": "group"}

        # Hermes discovers and loads the plugin from this home, as at startup.
        await asyncio.to_thread(discover_plugins)
        runner = GatewayRunner(GatewayConfig(sessions_dir=self.home / "sessions", group_sessions_per_user=True))
        adapter = RecordingAdapter()
        runner.adapters = {Platform.TELEGRAM: adapter}
        adapter.gateway_runner = runner
        adapter.set_message_handler(runner._handle_message)
        runner._gateway_loop = asyncio.get_running_loop()
        runner._running = True
        runner._install_plugin_message_injector()
        return runner, adapter

    async def person_says(self, text: str, *, user_id: str = "u1", user_name: str = "Sam", message_id: str) -> None:
        from gateway.platforms.base import MessageEvent, MessageType

        source = self.adapter.build_source(chat_id=ROOM, chat_type="group", user_id=user_id, user_name=user_name)
        await self.adapter.handle_message(
            MessageEvent(text=text, message_type=MessageType.TEXT, source=source, message_id=message_id)
        )

    def idle(self) -> bool:
        """Hermes's own test pattern for a settled gateway: nothing in flight."""

        return not (
            getattr(self.runner, "_background_tasks", None)
            or getattr(self.adapter, "_session_tasks", None)
            or getattr(self.adapter, "_active_sessions", None)
        )

    def close(self) -> None:
        async def stop() -> None:
            self.runner._running = False
            with contextlib.suppress(Exception):
                self.runner._clear_plugin_message_injector()

        with contextlib.suppress(Exception):
            self.run(stop(), timeout=10)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=10)
        self._gateway_run._hermes_home = self._saved_home
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        # The home stays until the process exits (`isolate`): Hermes keeps
        # logging to the first home it saw.


# -- the scripted agent's surface: Hermes's real I/O --------------------------------------------


def _user_text(request: Mapping[str, Any]) -> str:
    for message in reversed(request.get("messages", ())):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, list):
                content = "\n".join(part.get("text", "") for part in content if isinstance(part, Mapping))
            text = str(content or "")
            first, _, rest = text.partition("\n")
            return rest if first.startswith("<nunchi_wake ") else text
    return ""


def _tool_text(request: Mapping[str, Any]) -> str:
    for message in reversed(request.get("messages", ())):
        if message.get("role") == "tool":
            return str(message.get("content") or "")
    return ""


class HermesSurface:
    """One turn, as the model inside a real Hermes run reaches it."""

    def __init__(self, gateway: HermesGateway, model: ScriptedModel, plugin: HermesRoomPlugin, turn: Any) -> None:
        self.gateway = gateway
        self.model = model
        self.plugin = plugin
        self.turn = turn
        self.news: str | None = None

    def bind(self, turn_id: str) -> bool:
        # Hermes binds in `pre_llm_call`, before it asks the model; the script
        # starts when Hermes first asks, so the binding has happened if it will.
        return self.turn.turn_id is not None

    def _next_request(self, before: int) -> bool:
        deadline = time.monotonic() + _STEP_SECONDS
        while time.monotonic() < deadline:
            if self.model.count() > before:
                return True
            time.sleep(0.02)
        return False

    def call(self, turn_id: str, role: str, arguments: Mapping[str, Any]) -> tuple[bool, str]:
        before = self.model.count()
        self.model.reply({"tool": TOOL_NAMES.get(role, role), "arguments": dict(arguments)})
        if not self._next_request(before):
            return False, "Hermes did not ask the model again after the tool call"
        content, marker, update = _tool_text(self.model.latest()).partition("\n\nRoom update:")
        self.news = "Room update:" + update if marker else None
        try:
            answer = json.loads(content)
        except json.JSONDecodeError:
            return False, content
        if isinstance(answer, Mapping) and "result" in answer:
            return True, str(answer["result"])
        if isinstance(answer, Mapping) and "error" in answer:
            return False, str(answer["error"])
        return False, content

    def after_tool(self, turn_id: str) -> str | None:
        # Hermes asks for the news inside `transform_tool_result`, at the tool call.
        news, self.news = self.news, None
        return news

    def finish(self, turn_id: str, answer: str) -> tuple[str, str]:
        before_requests = self.model.count()
        before_sent = len(self.gateway.adapter.sent)
        self.model.reply({"text": answer})
        deadline = time.monotonic() + _STEP_SECONDS
        while time.monotonic() < deadline:
            if self.model.count() > before_requests:
                # A fresh run in the same turn: the library asked the agent to answer again.
                return "continue", _user_text(self.model.latest())
            if self.turn.ended.is_set() and self.gateway.idle():
                break
            time.sleep(0.02)
        sent = self.gateway.adapter.sent[before_sent:]
        if sent:
            return "deliver", sent[-1][1]
        return "silent", ""

    def end(self, turn_id: str, ok: bool) -> None:
        # The run ends by itself after its final answer; wait for Hermes to report it.
        deadline = time.monotonic() + _STEP_SECONDS
        while time.monotonic() < deadline and not (self.turn.ended.is_set() and self.gateway.idle()):
            time.sleep(0.02)


# -- the kit's integration -----------------------------------------------------------------------


class HermesKitIntegration:
    name = "Hermes plugin"
    posting = "final-answer"

    def __init__(self, *, tool_search: str = "off") -> None:
        self.tool_search = tool_search
        self.gateway: HermesGateway | None = None
        self.model: ScriptedModel | None = None
        self.plugin: HermesRoomPlugin | None = None

    def participant(self, *, profile: ParticipantProfile, guard: SecretGuard, agent: ScriptedAgent) -> Any:
        if not hermes_available():
            raise RuntimeError("Hermes is not installed in this Python environment")
        self.model = ScriptedModel()
        _PENDING.clear()
        _PENDING.update(
            profile=profile,
            guard=guard,
            route=HermesRoute(platform="telegram", chat_id=ROOM, turn_user_id=TURN_USER),
        )
        self.gateway = HermesGateway(model=self.model, tool_search=self.tool_search)
        plugin = _PENDING.get("plugin")
        if plugin is None:
            raise RuntimeError("Hermes did not load the plugin")
        self.plugin = plugin
        playing = threading.Lock()
        model, gateway = self.model, self.gateway

        def first_request() -> None:
            # Hermes asked the model for the first time in this turn: the script starts.
            if playing.acquire(blocking=False):
                agent.play(HermesSurface(gateway, model, plugin, plugin.participant.active))

        self.model.on_request = first_request
        return plugin.participant

    def close(self) -> None:
        if self.model is not None:
            self.model.close()
            self.model = None
        if self.gateway is not None:
            self.gateway.close()
            self.gateway = None
        _PENDING.clear()


def conformance_integrations() -> list[HermesKitIntegration]:
    return [HermesKitIntegration()]


__all__ = [
    "HermesGateway",
    "HermesKitIntegration",
    "HermesSurface",
    "ScriptedModel",
    "WAKE_MARKER",
    "conformance_integrations",
    "hermes_available",
    "register_for_kit",
]
