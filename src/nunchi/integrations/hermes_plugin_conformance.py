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
A ``stand_in`` step is a run whose model gives no answer, so Hermes ends it
with its own text. When the model wrote something, it wrote it beside a tool
call: with the kit's budget of one model call (``agent.max_turns: 1``), Hermes
ends the run with its iteration-limit text. When the model wrote nothing, it
answers empty every time Hermes asks: Hermes retries, then ends the run with
``(empty)``.

Hermes runs with the room settings `integrations/hermes-plugin/README.md`
gives (`room_settings`), and the recording adapter takes its platform settings
from the config Hermes loads, so the README's keys are what the kit tests.

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
from .hermes_plugin.plugin import (
    DEFAULT_FAILURE_GRACE_SECONDS,
    PLUGIN_NAME,
    TOOL_NAMES,
    WAKE_MARKER,
    HermesRoomPlugin,
    HermesRoute,
)

ROOM = "conformance-room"
TURN_USER = "nunchi-turns"
# The Hermes settings a Nunchi room needs, so that people see only what the
# agent chose to do (integrations/hermes-plugin/README.md, "Hermes setup the
# room needs"). Per platform, under display.platforms.<platform>: no streamed
# drafts, tool progress lines, interim assistant text, "still working" notes,
# retry and budget status lines, or reasoning.
ROOM_DISPLAY = {
    "streaming": False,
    "tool_progress": "off",
    "interim_assistant_messages": False,
    "long_running_notifications": False,
    "suppress_warning_notifications": True,
    "show_reasoning": False,
}
# Display settings Hermes reads only at the top level of `display`, for the
# whole profile: no footer after a failed file edit, no explanation added to
# a short or missing answer (agent/turn_explainers.py), and no busy notice.
ROOM_DISPLAY_GLOBAL = {
    "file_mutation_verifier": False,
    "turn_completion_explainer": False,
    "busy_ack_enabled": False,
}
# The platform's own block (`telegram:`, `discord:`), for the whole bot: no
# typing indicator and no processing reactions on people's messages.
ROOM_PLATFORM = {
    "typing_indicator": False,
    "reactions": False,
}
# Hermes toolsets that reach people outside the agent's answer: clarify
# prompts and scheduled deliveries.
ROOM_DISABLED_TOOLSETS = ("clarify", "cronjob")
_STEP_SECONDS = 20.0
# Hermes's own text for a run with no answer can take a few retries.
_STAND_IN_SECONDS = 90.0
_PLUGIN_YAML = Path(__file__).parent / "hermes_plugin" / "plugin.yaml"
_KIT_PLUGIN_INIT = (
    '"""The Nunchi Hermes plugin, wired to the turn conformance kit."""\n'
    "from nunchi.integrations.hermes_plugin_conformance import register_for_kit as register\n"
)

# The scenario being set up: what `register_for_kit` builds the plugin from.
_PENDING: dict[str, Any] = {}
_ISOLATION: dict[str, Any] = {}


def room_settings(platform: str = "telegram") -> dict[str, Any]:
    """The Hermes config a Nunchi room on ``platform`` needs, beside the plugin's entry."""

    return {
        "display": {**ROOM_DISPLAY_GLOBAL, "platforms": {platform: dict(ROOM_DISPLAY)}},
        platform: dict(ROOM_PLATFORM),
        "agent": {"disabled_toolsets": list(ROOM_DISABLED_TOOLSETS)},
    }


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
        failure_grace_seconds=_PENDING.get("failure_grace_seconds", DEFAULT_FAILURE_GRACE_SECONDS),
        roles=_PENDING.get("roles", ("react", "context")),
        # The kit builds its own Room; an end-to-end test lets the plugin build one.
        room_factory=_PENDING.get("room_factory"),
    )
    plugin.register(ctx)
    _PENDING["plugin"] = plugin


# -- the model: the only scripted part ---------------------------------------------------


class ScriptedModel:
    """An OpenAI-compatible chat endpoint whose answers the scripted agent supplies.

    Only the agent's own model calls (those offering tools) are scripted. Hermes's
    auxiliary calls, such as naming the session, get a fixed answer. A reply
    is ``{"text": ...}``, ``{"tool": name, "arguments": {...}}`` (with optional
    text), or ``{"status": 400, "error": message}``: the provider refuses.
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
                if "status" in reply:
                    payload = json.dumps({"error": {"message": str(reply.get("error", "refused")),
                                                    "type": "invalid_request_error"}}).encode()
                    self.send_response(int(reply["status"]))
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                message: dict[str, Any] = {"role": "assistant", "content": reply.get("text", "")}
                finish = "stop"
                if "tool" in reply:
                    message = {
                        "role": "assistant",
                        # A model may write text alongside its tool call.
                        "content": reply.get("text") or None,
                        "tool_calls": [
                            {
                                "id": f"call_{model.count()}",
                                "type": "function",
                                "function": {"name": reply["tool"], "arguments": json.dumps(reply.get("arguments", {}))},
                            }
                        ],
                    }
                    finish = "tool_calls"
                # An empty reply generated nothing, as a provider reports it.
                output = 5 if message.get("content") or message.get("tool_calls") else 0
                usage = {"prompt_tokens": 10, "completion_tokens": output, "total_tokens": 10 + output}
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

    def __init__(
        self,
        *,
        model: ScriptedModel,
        tool_search: str = "off",
        allowed_users: str = f"u1,u2,{TURN_USER}",
        extra_config: Mapping[str, Any] | None = None,
        plugin_source: Path | None = None,
        plugin_settings: Mapping[str, Any] | None = None,
        platform_actions: bool = False,
    ) -> None:
        base = isolate()
        _ISOLATION["count"] += 1
        self.directory = base / f"scenario-{_ISOLATION['count']}"
        self.home = self.directory / "home"
        plugin_dir = self.home / "plugins" / PLUGIN_NAME
        if plugin_source is not None:
            # The shipped plugin directory, loaded with its own register().
            shutil.copytree(plugin_source, plugin_dir, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            plugin_dir.mkdir(parents=True)
            shutil.copyfile(_PLUGIN_YAML, plugin_dir / "plugin.yaml")
            (plugin_dir / "__init__.py").write_text(_KIT_PLUGIN_INIT, encoding="utf-8")
        entry: dict[str, Any] = {"allow_gateway_injection": True}
        if platform_actions:
            # The operator's grant for reactions (legacy key of gateway.platform_actions).
            entry["allow_platform_actions"] = True
        if plugin_settings:
            entry["settings"] = dict(plugin_settings)
        config: dict[str, Any] = {
            "model": {"default": "conformance/model", "provider": "custom", "base_url": model.base_url,
                      "api_key": "sk-local-conformance"},
            "plugins": {"enabled": [PLUGIN_NAME], "entries": {PLUGIN_NAME: entry}},
            # Operator setup for a Nunchi room (integrations/hermes-plugin/README.md):
            # only what the agent chose to do may reach the room.
            **room_settings("telegram"),
            "tools": {"tool_search": {"enabled": tool_search}},
        }
        for key, value in (extra_config or {}).items():
            if isinstance(value, Mapping) and isinstance(config.get(key), dict):
                config[key] = {**config[key], **value}
            else:
                config[key] = value
        # JSON is YAML: Hermes reads it as its config.yaml.
        (self.home / "config.yaml").write_text(json.dumps(config), encoding="utf-8")
        (self.home / ".env").write_text(f"TELEGRAM_ALLOWED_USERS={allowed_users}\n", encoding="utf-8")
        # Hermes copies agent.max_turns into HERMES_MAX_ITERATIONS for the whole
        # process (gateway/run.py), so it is put back with the rest on close.
        self._saved_env = {key: os.environ.get(key) for key in (
            "HERMES_HOME", "TELEGRAM_ALLOWED_USERS", "GATEWAY_ALLOWED_USERS", "GATEWAY_ALLOW_ALL_USERS",
            "HERMES_MAX_ITERATIONS")}
        os.environ["HERMES_HOME"] = str(self.home)
        os.environ["TELEGRAM_ALLOWED_USERS"] = allowed_users
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
        import dataclasses

        from gateway.config import GatewayConfig, Platform, PlatformConfig, load_gateway_config
        from gateway.platforms.base import BasePlatformAdapter, SendResult

        # The platform settings as Hermes loads them from this home's config
        # (the README's `telegram:` block), as a real adapter gets them.
        loaded = await asyncio.to_thread(load_gateway_config)
        settings = loaded.platforms.get(Platform.TELEGRAM) or PlatformConfig()
        platform_config = dataclasses.replace(
            settings,
            enabled=True,
            token="conformance",
            extra={**settings.extra, "group_sessions_per_user": True},
        )
        from gateway.run import GatewayRunner
        from hermes_cli.plugins import discover_plugins

        class RecordingAdapter(BasePlatformAdapter):
            def __init__(self) -> None:
                super().__init__(platform_config, Platform.TELEGRAM)
                self.sent: list[tuple[str, str]] = []
                self.reactions: list[tuple[str, str, str]] = []
                # Each typing action Hermes sent, by chat.
                self.typing: list[str] = []
                self._running = True

            async def connect(self, *, is_reconnect: bool = False) -> bool:
                return True

            async def disconnect(self) -> None:
                self._mark_disconnected()

            async def send(self, chat_id, content, reply_to=None, metadata=None):
                self.sent.append((str(chat_id), content))
                return SendResult(success=True, message_id=f"sent-{len(self.sent)}")

            async def _set_reaction(self, chat_id, message_id, emoji) -> bool:
                # What Hermes's Telegram add_reaction verb calls on the adapter.
                self.reactions.append((str(chat_id), str(message_id), emoji))
                return True

            async def send_typing(self, chat_id, metadata=None):
                self.typing.append(str(chat_id))
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

    async def person_says(
        self, text: str, *, user_id: str = "u1", user_name: str = "Sam", message_id: str, **fields: Any
    ) -> None:
        """A message as the platform adapter hands it to Hermes; ``fields`` are more `MessageEvent` fields."""

        from gateway.platforms.base import MessageEvent, MessageType

        source = self.adapter.build_source(chat_id=ROOM, chat_type="group", user_id=user_id, user_name=user_name)
        await self.adapter.handle_message(
            MessageEvent(text=text, message_type=MessageType.TEXT, source=source, message_id=message_id, **fields)
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
        # Made at the turn's first model request: what Hermes gave the model.
        self.shown = _user_text(model.latest())

    def bind(self, turn_id: str) -> bool:
        # Hermes binds in `pre_llm_call`, before it asks the model; the script
        # starts when Hermes first asks, so the binding has happened if it will.
        return self.turn.turn_id is not None

    def read(self, turn_id: str) -> str:
        return self.shown

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

    def stand_in(self, turn_id: str, text: str, wrote: str) -> tuple[str, str]:
        # Hermes answers for the model with its own words, not ``text``. When
        # the model wrote ``wrote``, it wrote it beside a tool call and runs out
        # of budget; Hermes may ask it to sum up, and it calls a tool again, so
        # no answer comes. When it wrote nothing, it answers empty each time.
        before_sent = len(self.gateway.adapter.sent)
        if wrote:
            again: dict[str, Any] = {"tool": TOOL_NAMES["context"], "arguments": {}}
            first = {**again, "text": wrote}
        else:
            again = first = {"text": ""}
        self.model.reply(first)
        answered = self.model.count()
        deadline = time.monotonic() + _STAND_IN_SECONDS
        while time.monotonic() < deadline:
            if self.model.count() > answered:
                answered += 1
                self.model.reply(again)
            if self.turn.ended.is_set() and self.gateway.idle():
                break
            time.sleep(0.02)
        sent = self.gateway.adapter.sent[before_sent:]
        return ("deliver", sent[-1][1]) if sent else ("silent", "")

    def end(self, turn_id: str, ok: bool, note: str | None = None) -> None:
        # The run ends by itself after its final answer; wait for Hermes to report it.
        deadline = time.monotonic() + _STEP_SECONDS
        while time.monotonic() < deadline and not (self.turn.ended.is_set() and self.gateway.idle()):
            time.sleep(0.02)


# -- the plugin in a real gateway -----------------------------------------------------------------


class HermesHarness:
    """The plugin, loaded by a real Hermes gateway from a throwaway home, with a scripted model.

    ``room_factory`` lets the plugin build its own `Room` (end-to-end, through
    Hermes's ingress); without it the caller builds the room, as the kit does.

    Hermes runs with the room settings (`room_settings`). ``display`` replaces
    the platform's display settings, ``agent`` adds Hermes agent settings, and
    ``extra_config`` changes any other part of the config, one level deep
    (``{"display": {"turn_completion_explainer": True}}`` keeps the rest of
    ``display``).
    """

    def __init__(
        self,
        *,
        profile: ParticipantProfile,
        guard: SecretGuard,
        room_factory: Any = None,
        tool_search: str = "off",
        allowed_users: str = f"u1,u2,{TURN_USER}",
        start_timeout_seconds: float = 30.0,
        result_wait_seconds: float = 5.0,
        platform_actions: bool = False,
        display: Mapping[str, Any] | None = None,
        roles: tuple[str, ...] = ("react", "context"),
        agent: Mapping[str, Any] | None = None,
        extra_config: Mapping[str, Any] | None = None,
        failure_grace_seconds: float | None = None,
    ) -> None:
        if not hermes_available():
            raise RuntimeError("Hermes is not installed in this Python environment")
        self.route = HermesRoute(platform="telegram", chat_id=ROOM, turn_user_id=TURN_USER)
        self.model = ScriptedModel()
        _PENDING.clear()
        _PENDING.update(
            profile=profile,
            guard=guard,
            route=self.route,
            room_factory=room_factory,
            start_timeout_seconds=start_timeout_seconds,
            result_wait_seconds=result_wait_seconds,
            roles=roles,
            **({} if failure_grace_seconds is None else {"failure_grace_seconds": failure_grace_seconds}),
        )
        extra: dict[str, Any] = {}
        if display is not None:
            extra["display"] = {"platforms": {"telegram": dict(display)}}
        if agent is not None:
            # Hermes's own agent settings, such as its budget of model calls.
            extra["agent"] = dict(agent)
        for key, value in (extra_config or {}).items():
            if isinstance(value, Mapping) and isinstance(extra.get(key), dict):
                extra[key] = {**extra[key], **value}
            else:
                extra[key] = value
        try:
            self.gateway = HermesGateway(
                model=self.model, tool_search=tool_search, allowed_users=allowed_users,
                platform_actions=platform_actions,
                extra_config=extra or None,
            )
        except BaseException:
            self.model.close()
            raise
        plugin = _PENDING.get("plugin")
        if plugin is None:
            self.close()
            raise RuntimeError("Hermes did not load the plugin")
        self.plugin: HermesRoomPlugin = plugin

    def person_says(
        self, text: str, *, message_id: str, user_id: str = "u1", user_name: str = "Sam", **fields: Any
    ) -> None:
        self.gateway.run(
            self.gateway.person_says(text, user_id=user_id, user_name=user_name, message_id=message_id, **fields)
        )

    def wait_observed(self, event_id: str, timeout: float = _STEP_SECONDS) -> bool:
        """Hermes hands a message to its admission hook asynchronously; wait for the room."""

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            room = self.plugin.room
            if room is not None and room.observation.resolve_event(event_id) is not None:
                return True
            time.sleep(0.02)
        return False

    def wait_for_requests(self, count: int, timeout: float = _STEP_SECONDS) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.model.count() >= count:
                return True
            time.sleep(0.02)
        return False

    def settle(self, timeout: float = _STEP_SECONDS) -> bool:
        """Hermes is idle, the turn has ended, and the room has recorded it."""

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.gateway.idle() and self.plugin.participant.active is None:
                room = self.plugin.room
                return room is None or room.drain(max(0.0, deadline - time.monotonic()))
            time.sleep(0.02)
        return False

    def close(self) -> None:
        self.model.close()
        gateway = getattr(self, "gateway", None)
        if gateway is not None:
            gateway.close()
        _PENDING.clear()


# -- the kit's integration -----------------------------------------------------------------------


class HermesKitIntegration:
    name = "Hermes plugin"
    posting = "final-answer"
    # Hermes ends a run with its own text when its model gives no answer.
    harness_text = True

    def __init__(self, *, tool_search: str = "off") -> None:
        self.tool_search = tool_search
        self.harness: HermesHarness | None = None

    def participant(
        self, *, profile: ParticipantProfile, guard: SecretGuard, agent: ScriptedAgent, privileged: bool = False
    ) -> Any:
        # A model that writes beside a tool call and gets no further: one model
        # call, then Hermes's own text.
        budget = any(step[0] == "stand_in" and step[2] for turn in agent.turns for step in turn)
        self.harness = harness = HermesHarness(
            profile=profile,
            guard=guard,
            tool_search=self.tool_search,
            roles=("react", "context", "propose", "withdraw") if privileged else ("react", "context"),
            agent={"max_turns": 1} if budget else None,
        )
        plugin = harness.plugin

        def first_request() -> None:
            # Hermes asked the model for the first time in a turn: that turn's script starts.
            turn = plugin.participant.active
            if turn is not None:
                agent.play_once(turn, lambda: HermesSurface(harness.gateway, harness.model, plugin, turn))

        harness.model.on_request = first_request
        return plugin.participant

    def close(self) -> None:
        if self.harness is not None:
            self.harness.close()
            self.harness = None


def conformance_integrations() -> list[HermesKitIntegration]:
    return [HermesKitIntegration()]


__all__ = [
    "HermesGateway",
    "HermesHarness",
    "HermesKitIntegration",
    "HermesSurface",
    "ScriptedModel",
    "ROOM_DISABLED_TOOLSETS",
    "ROOM_DISPLAY",
    "ROOM_DISPLAY_GLOBAL",
    "ROOM_PLATFORM",
    "WAKE_MARKER",
    "conformance_integrations",
    "hermes_available",
    "isolate",
    "register_for_kit",
    "room_settings",
]
