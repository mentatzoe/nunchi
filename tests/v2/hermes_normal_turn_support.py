"""Support for installed-host normal-turn probes (tests/v2/test_hermes_normal_turn.py).

Everything here runs against an *installed* stock Hermes: the probes import
``gateway.run``, ``gateway.platforms.base``, ``hermes_cli.plugins`` and the
shipped Discord platform plugin from wherever the interpreter resolves them.
Nothing in this module monkeypatches Hermes ingress, authorisation,
participant or delivery code. The only test doubles sit at the network
boundaries Hermes itself treats as external:

* ``FakeOpenAIServer`` – a loopback HTTP server speaking the OpenAI
  ``/chat/completions`` shape. Hermes reaches it through its own
  ``model.provider: custom`` + ``model.base_url`` route in ``config.yaml``.
  This is a deterministic double, **not** live-provider acceptance.
* ``FakeDiscordClient`` – stands in for ``discord.ext.commands.Bot`` on the
  shipped Discord adapter. It records ``channel.send`` calls and returns the
  same ``discord.Message``-shaped acknowledgement objects the real client
  would. No socket is opened. Discord-side authentication is therefore not
  exercised; Hermes-side authorisation (allowlists, ``_is_user_authorized``,
  ``_discord_message_admission``) is the real code.

Helpers are intentionally thin so a reader can see which Hermes object does
what; the probes are the product.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Environment facts
# ---------------------------------------------------------------------------

_AMBIENT_PREFIXES = ("DISCORD_", "TELEGRAM_", "HERMES_", "GATEWAY_", "OPENAI_", "OPENROUTER_", "ANTHROPIC_")
_KEEP = {"HERMES_HOME", "HERMES_KANBAN_WORKSPACE"}


def scrub_ambient_environment() -> list[str]:
    """Drop inherited Hermes/platform env so only the probe's config applies.

    A developer or Kanban shell often carries the live profile's
    ``DISCORD_ALLOWED_CHANNELS`` and friends. Stock Hermes reads those at
    ingress, which would silently change admission results. Returns the
    names removed so a test can record them.
    """

    removed = []
    for name in list(os.environ):
        if name in _KEEP:
            continue
        if name.startswith(_AMBIENT_PREFIXES) or name == "TERMINAL_CWD":
            os.environ.pop(name, None)
            removed.append(name)
    os.environ.pop("PYTHONPATH", None)
    return sorted(removed)


def hermes_version() -> str:
    return importlib.metadata.version("hermes-agent")


def nunchi_version() -> str:
    return importlib.metadata.version("nunchi")


def installed_paths() -> dict[str, str]:
    """Where the host modules actually resolve from in this interpreter."""

    out: dict[str, str] = {"python": sys.executable}
    for name in (
        "gateway.run",
        "gateway.platforms.base",
        "hermes_cli.plugins",
        "hermes_cli.middleware",
        "plugins.platforms.discord.adapter",
        "nunchi.integrations.hermes_v2",
    ):
        try:
            out[name] = str(importlib.import_module(name).__file__)
        except Exception as exc:  # noqa: BLE001 - report, don't hide
            out[name] = f"IMPORT-ERROR {exc!r}"
    return out


# ---------------------------------------------------------------------------
# Loopback OpenAI-compatible model double
# ---------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    server: "FakeOpenAIServer"

    def log_message(self, *_args: Any) -> None:  # silence
        return None

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/").endswith("/models"):
            body = json.dumps({"object": "list", "data": [{"id": "probe-model"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {"_raw": raw.decode("utf-8", "replace")}
        if "messages" not in payload:
            # Not a chat completion (e.g. a probe/ping). Record and 404 so the
            # scripted FIFO is reserved for real model turns.
            with self.server.lock:
                self.server.other_requests.append({"path": self.path, "body": payload})
            self.send_response(404)
            self.end_headers()
            return
        with self.server.lock:
            self.server.requests.append(
                {
                    "path": self.path,
                    "authorization": self.headers.get("Authorization"),
                    "body": payload,
                }
            )
            self.server.arrived.set()
            classifier = self.server.classify(payload)
            if classifier is not None:
                script = classifier
            elif self.server.scripted:
                script = self.server.scripted.pop(0)
            else:
                script = {"content": "stock fallback reply"}
        if callable(script):
            script = script(payload)
        status = int(script.get("status", 200))
        if status != 200:
            body = json.dumps({"error": {"message": script.get("error", "scripted failure")}}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        hold = script.get("hold")
        if hold is not None:
            hold.wait(timeout=float(script.get("hold_timeout", 30)))
        model = payload.get("model", "probe-model")
        if payload.get("stream"):
            self._write_sse(script, model)
            return
        message: dict[str, Any] = {"role": "assistant", "content": script.get("content")}
        finish = "stop"
        if script.get("tool_calls"):
            message["tool_calls"] = script["tool_calls"]
            finish = "tool_calls"
        response = {
            "id": f"chatcmpl-probe-{len(self.server.requests)}",
            "object": "chat.completion",
            "created": 0,
            "model": model,
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        body = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_sse(self, script: dict[str, Any], model: str) -> None:
        """Stock Hermes streams chat completions; answer in SSE chunk form."""

        chunk_id = f"chatcmpl-probe-{len(self.server.requests)}"

        def chunk(delta: dict[str, Any], finish: str | None = None, usage: dict[str, Any] | None = None) -> bytes:
            body: dict[str, Any] = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": 0,
                "model": model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            if usage is not None:
                body["usage"] = usage
            return b"data: " + json.dumps(body).encode() + b"\n\n"

        parts: list[bytes] = [chunk({"role": "assistant"})]
        content = script.get("content")
        if content:
            parts.append(chunk({"content": content}))
        tool_calls = script.get("tool_calls") or []
        for index, call in enumerate(tool_calls):
            parts.append(
                chunk(
                    {
                        "tool_calls": [
                            {
                                "index": index,
                                "id": call["id"],
                                "type": "function",
                                "function": {
                                    "name": call["function"]["name"],
                                    "arguments": call["function"]["arguments"],
                                },
                            }
                        ]
                    }
                )
            )
        finish = "tool_calls" if tool_calls else "stop"
        parts.append(chunk({}, finish=finish, usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}))
        parts.append(b"data: [DONE]\n\n")
        body = b"".join(parts)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()


class FakeOpenAIServer(ThreadingHTTPServer):
    """Deterministic ``/chat/completions`` double on 127.0.0.1.

    ``scripted`` is a FIFO of dicts: ``{"content": str}``,
    ``{"tool_calls": [...], "content": None}``, ``{"status": 500}``, or
    ``{"content": str, "hold": threading.Event}`` to park a request until the
    test releases it. A callable entry receives the request body.
    """

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.lock = threading.Lock()
        self.requests: list[dict[str, Any]] = []
        self.other_requests: list[dict[str, Any]] = []
        self.scripted: list[Any] = []
        # Optional callable answering Nunchi's structured attention call
        # (recognised by its instructions text), kept apart from the FIFO so a
        # refused/absent attention call can never shift the stock-turn script.
        self.attention: Callable[[dict[str, Any]], dict[str, Any]] | None = None
        self.arrived = threading.Event()
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}/v1"

    def script(self, *entries: Any) -> None:
        with self.lock:
            self.scripted.extend(e for e in entries if e is not None)

    def classify(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Answer stock side-calls deterministically without touching the FIFO.

        Stock Hermes makes auxiliary model calls that are not the
        participant turn: the smart-approval guard (``tools/approval.py``
        ``_smart_approve``) and title generation. Each is recognised by its
        own system prompt. The guard is answered ESCALATE so the native human
        approval path is exercised instead of auto-approval.
        """

        messages = payload.get("messages") or []
        system = " ".join(str(m.get("content", "")) for m in messages if m.get("role") == "system")
        if "security reviewer for an AI coding agent" in system:
            return {"content": "ESCALATE"}
        if "Generate a short, descriptive title" in system:
            return {"content": "probe title"}
        if self.attention is not None and "tools" not in payload and "Uncertainty must return DEFER" in json.dumps(messages):
            return self.attention(payload)
        return None

    def reset(self) -> None:
        """Forget recorded requests and scripts (one server per process)."""

        with self.lock:
            self.requests.clear()
            self.other_requests.clear()
            self.scripted.clear()
            self.attention = None
            self.arrived.clear()

    def close(self) -> None:
        self.shutdown()
        self.server_close()

    def bodies(self) -> list[dict[str, Any]]:
        with self.lock:
            return [r["body"] for r in self.requests]


def tool_call(name: str, arguments: dict[str, Any], call_id: str = "call_probe_1") -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


# ---------------------------------------------------------------------------
# Discord client double (shape-compatible with discord.py objects Hermes uses)
# ---------------------------------------------------------------------------


class FakeDiscordUser:
    def __init__(self, user_id: int, *, name: str, bot: bool = False) -> None:
        self.id = user_id
        self.name = name
        self.display_name = name
        self.global_name = name
        self.bot = bot
        self.mention = f"<@{user_id}>"
        self.roles: list[Any] = []

    def __eq__(self, other: object) -> bool:
        return isinstance(other, FakeDiscordUser) and other.id == self.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __repr__(self) -> str:
        return f"FakeDiscordUser({self.id}, {self.name!r}, bot={self.bot})"


class FakeDiscordPermissions:
    """Labelled double of a discord.py Permissions result. Not a live grant."""

    def __init__(
        self,
        *,
        view_channel: bool = True,
        read_message_history: bool = True,
        add_reactions: bool = True,
    ) -> None:
        self.view_channel = view_channel
        self.read_message_history = read_message_history
        self.add_reactions = add_reactions


class FakeGuild:
    def __init__(self, guild_id: int = 7000) -> None:
        self.id = guild_id
        self.name = "probe-guild"
        self.members: list[Any] = []

    def get_member(self, _member_id: int) -> Any:
        return None


class FakeTextChannel:
    """Guild text channel. ``send`` records and acknowledges like discord.py."""

    def __init__(self, channel_id: int, client: "FakeDiscordClient", *, name: str = "probe-room") -> None:
        self.id = channel_id
        self.name = name
        self.guild = client.guild
        self.topic = None
        self.type = 0  # discord.ChannelType.text
        self.client = client
        self.sent: list[dict[str, Any]] = []
        self.messages: dict[int, "FakeDiscordMessage"] = {}
        self.permissions = FakeDiscordPermissions()

    def permissions_for(self, member: Any) -> "FakeDiscordPermissions":
        """SDK-shaped permission read. Only the authenticated bot is allowed.

        This is a labelled double of discord.py ``permissions_for``. It does
        not open a socket. A subject that is not the probe bot is denied, so
        a capability probe cannot treat the message author as the bot.
        """

        if str(getattr(member, "id", "")) != str(self.client.user.id):
            return FakeDiscordPermissions(
                view_channel=False,
                read_message_history=False,
                add_reactions=False,
            )
        return self.permissions

    async def send(self, content: str | None = None, *, reference: Any = None, **kwargs: Any) -> "FakeDiscordMessage":
        self.client.send_calls.append(
            {
                "channel_id": self.id,
                "content": content,
                "reference": getattr(reference, "message_id", reference),
                "kwargs": {k: v for k, v in kwargs.items() if k not in {"file", "files", "view"}},
            }
        )
        if self.client.send_failure is not None:
            exc = self.client.send_failure
            raise exc
        message = FakeDiscordMessage(
            self.client.next_message_id(),
            channel=self,
            author=self.client.user,
            content=content or "",
        )
        self.messages[message.id] = message
        self.sent.append({"id": message.id, "content": content})
        return message

    async def fetch_message(self, message_id: int) -> "FakeDiscordMessage":
        try:
            return self.messages[int(message_id)]
        except KeyError as exc:
            raise self.client.not_found_error(message_id) from exc

    def history(self, **_kwargs: Any) -> Any:
        async def _iter():
            return
            yield

        return _iter()

    async def typing(self) -> None:
        return None

    def __repr__(self) -> str:
        return f"FakeTextChannel({self.id})"


class _Typing:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: Any) -> None:
        return None


class FakeDiscordMessage:
    def __init__(
        self,
        message_id: int,
        *,
        channel: FakeTextChannel,
        author: FakeDiscordUser,
        content: str,
        mentions: list[FakeDiscordUser] | None = None,
    ) -> None:
        import discord

        self.id = message_id
        self.channel = channel
        self.author = author
        self.content = content
        self.clean_content = content
        self.mentions = list(mentions or [])
        self.mention_everyone = False
        self.role_mentions: list[Any] = []
        self.attachments: list[Any] = []
        self.embeds: list[Any] = []
        self.stickers: list[Any] = []
        self.reference = None
        self.message_snapshots: list[Any] = []
        self.guild = channel.guild
        self.created_at = datetime.now(timezone.utc)
        self.type = discord.MessageType.default
        self.reactions: list[tuple[str, str]] = []
        self.jump_url = f"https://discord.test/{channel.id}/{message_id}"

    async def add_reaction(self, emoji: str) -> None:
        client = self.channel.client
        started = getattr(client, "reaction_started", None)
        if started is not None:
            started.set()
        hold = getattr(client, "reaction_hold", None)
        if hold is not None:
            await hold.wait()
        self.reactions.append(("add", str(emoji)))

    async def remove_reaction(self, emoji: str, _member: Any) -> None:
        self.reactions.append(("remove", str(emoji)))

    async def reply(self, content: str | None = None, **kwargs: Any) -> "FakeDiscordMessage":
        return await self.channel.send(content, reference=self, **kwargs)

    def to_reference(self, *, fail_if_not_exists: bool = True) -> types.SimpleNamespace:
        return types.SimpleNamespace(message_id=self.id, channel_id=self.channel.id)

    def __repr__(self) -> str:
        return f"FakeDiscordMessage({self.id}, by={self.author.id}, {self.content!r})"


class FakeDiscordClient:
    """Stands in for ``commands.Bot`` after ``connect()``; no socket."""

    def __init__(self, *, bot_user_id: int = 999, bot_name: str = "nunchi-bot") -> None:
        self.user = FakeDiscordUser(bot_user_id, name=bot_name, bot=True)
        self.guild = FakeGuild()
        self.guilds = [self.guild]
        self.channels: dict[int, FakeTextChannel] = {}
        self.send_calls: list[dict[str, Any]] = []
        self.send_failure: BaseException | None = None
        self._next_id = 100_000
        self.latency = 0.01
        self.application_id = bot_user_id
        self.http = types.SimpleNamespace()
        self.tree = types.SimpleNamespace(sync=self._noop_sync, get_commands=lambda **_: [])
        self.ws = types.SimpleNamespace(open=True)

    async def _noop_sync(self, *_a: Any, **_k: Any) -> list[Any]:
        return []

    def next_message_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def channel(self, channel_id: int) -> FakeTextChannel:
        if channel_id not in self.channels:
            self.channels[channel_id] = FakeTextChannel(channel_id, self)
        return self.channels[channel_id]

    def get_channel(self, channel_id: int) -> FakeTextChannel | None:
        return self.channels.get(int(channel_id))

    async def fetch_channel(self, channel_id: int) -> FakeTextChannel:
        chan = self.channels.get(int(channel_id))
        if chan is None:
            raise self.not_found_error(channel_id)
        return chan

    def not_found_error(self, what: Any) -> Exception:
        import discord

        response = types.SimpleNamespace(status=404, reason="Not Found")
        return discord.NotFound(response, {"message": f"Unknown {what}", "code": 10008})

    def is_ready(self) -> bool:
        return True

    def is_closed(self) -> bool:
        return False

    async def close(self) -> None:
        return None

    def get_user(self, user_id: int) -> FakeDiscordUser | None:
        return self.user if user_id == self.user.id else None


# ---------------------------------------------------------------------------
# Hermes home / config materialisation
# ---------------------------------------------------------------------------


def write_hermes_home(
    home: Path,
    *,
    model_base_url: str,
    enable_nunchi: bool,
    trust_nunchi_llm: bool = False,
    extra_config: dict[str, Any] | None = None,
) -> Path:
    """Materialise a minimal stock ``HERMES_HOME`` using a custom provider route.

    ``trust_nunchi_llm`` writes the stock ``plugins.entries.nunchi.llm``
    override flags. Stock defaults them to false, and Nunchi's attention call
    passes ``provider=``/``model=`` so it is refused with
    ``PluginLlmTrustError`` on a default install. Probes run both ways.
    """

    home.mkdir(parents=True, exist_ok=True)
    (home / "sessions").mkdir(exist_ok=True)
    config: dict[str, Any] = {
        "model": {
            "default": "probe-model",
            "provider": "custom",
            "base_url": model_base_url,
            "api_key": "probe-key-not-a-secret",
        },
        "auxiliary": {
            # Keep every auxiliary task (title generation, compression…) on
            # the same loopback double so nothing leaves the host.
            "title_generation": {"provider": "custom", "model": "probe-model", "base_url": model_base_url, "api_key": "probe-key-not-a-secret"},
        },
        "plugins": {
            "enabled": ["nunchi"] if enable_nunchi else [],
            **(
                {"entries": {"nunchi": {"llm": {"allow_provider_override": True, "allow_model_override": True}}}}
                if trust_nunchi_llm
                else {}
            ),
        },
        "display": {"tool_progress": "off", "thinking_progress": False},
        "terminal": {"backend": "local"},
        "gateway": {"stream_output": False},
        "platforms": {
            "discord": {
                "enabled": True,
                "typing_indicator": False,
                # A home channel silences the stock first-turn "/sethome"
                # notice, which would otherwise count as an extra delivery.
                "home_channel": {"platform": "discord", "chat_id": "4242", "name": "probe-home"},
            },
        },
    }
    if extra_config:
        _deep_update(config, extra_config)
    import yaml  # provided by Hermes (pyyaml)

    (home / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    (home / ".env").write_text(
        "DISCORD_BOT_TOKEN=probe-token-not-a-secret\n"
        "DISCORD_ALLOWED_USERS=100\n"
        # Stock setting: reply in-channel instead of spawning a thread per
        # message. Nunchi rooms are flat rooms; thread auto-creation is an
        # orthogonal stock feature and the fake client has no thread API.
        "DISCORD_AUTO_THREAD=false\n",
        encoding="utf-8",
    )
    os.chmod(home / ".env", 0o600)
    return home


def _deep_update(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def write_nunchi_config(
    home: Path,
    *,
    profile: str = "default",
    room_id: str = "42",
    bot_user_id: int = 999,
    attention_provider: str = "custom",
    attention_model: str = "probe-model",
    timeout_seconds: float = 20.0,
    suppression_enabled: bool = True,
) -> tuple[Path, Path]:
    """Write the dashboard-default pinned config + digest for one Discord room."""

    from nunchi.integrations.hermes_dashboard_store import default_config_paths

    paths = default_config_paths(profile, hermes_home=home)
    paths.config.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(paths.config.parent, 0o700)
    document = {
        "schema_version": 2,
        "hermes_profile": profile,
        "state_directory": str(paths.state_directory),
        "rooms": [
            {
                "binding": {
                    "participant_id": "participant",
                    "actor_id": f"discord:actor:{bot_user_id}",
                    "platform": "discord",
                    "room_id": room_id,
                    "continuity_scope_id": f"discord-room-{room_id}",
                    "names": ["Nunchi"],
                    "room_kind": "group",
                    "provenance": "test:normal-turn-probe",
                },
                "profile": {
                    "document": {
                        "profile_id": "participant-profile",
                        "participant_id": "participant",
                        "actor_id": f"discord:actor:{bot_user_id}",
                        "instructions": "Be useful and concise.",
                        "provenance": "test:normal-turn-probe",
                    }
                },
                "attention": {
                    "model": {"provider": attention_provider, "model": attention_model},
                    "policy": {
                        "suppression_enabled": suppression_enabled,
                        "suppression_recovery_verified": suppression_enabled,
                    },
                },
                "limits": {},
                "participant": {"timeout_seconds": timeout_seconds, "max_expansions": 1},
            }
        ],
    }
    raw = (json.dumps(document, sort_keys=True, indent=2) + "\n").encode("utf-8")
    paths.config.write_bytes(raw)
    os.chmod(paths.config, 0o600)
    paths.digest.write_text(hashlib.sha256(raw).hexdigest() + "\n", encoding="ascii")
    os.chmod(paths.digest, 0o600)
    return paths.config, paths.digest


def attention_judgment(disposition: str, event_id: str) -> str:
    """JSON text the attention double returns for Nunchi's structured call."""

    speak = disposition in {"WAKE", "DEFER"}
    return json.dumps(
        {
            "disposition": disposition,
            "reasons": ["probe decision"],
            "evidence_event_ids": [event_id],
            "legacy_verdict_confidences": {
                "PASS": 0.01 if speak else 0.9,
                "ACK": 0.01,
                "ASK": 0.08,
                "SPEAK": 0.9 if speak else 0.01,
            },
        }
    )


# ---------------------------------------------------------------------------
# Runner + adapter assembly (real objects, no handler substitution)
# ---------------------------------------------------------------------------


class ProbeHost:
    """One real GatewayRunner + one real DiscordAdapter wired like ``start()``.

    ``GatewayRunner.start()`` would open the live Discord socket and HTTP
    control surfaces; we replicate only the adapter wiring lines from
    ``start()`` (set_message_handler / set_session_store / busy handler /
    authorization check) so every inbound event takes the stock path:
    ``DiscordAdapter._dispatch_discord_message`` → ``BasePlatformAdapter.handle_message``
    → ``GatewayRunner._handle_message`` → ``_handle_message_with_agent`` →
    ``AIAgent`` → HTTP → ``BasePlatformAdapter._process_message_background``
    → ``DiscordAdapter.send``.
    """

    def __init__(self, *, home: Path, client: FakeDiscordClient) -> None:
        import gateway.run as gateway_run
        from gateway.config import Platform, load_gateway_config
        from gateway.run import GatewayRunner

        # ``gateway.run._hermes_home`` is bound at import time (0.19.0
        # gateway/run.py:1418). Stock's own tests monkeypatch it per fixture
        # (tests/gateway/test_internal_event_bypass_pairing.py); do the same so
        # ``_load_gateway_config`` reads this probe's temp home instead of the
        # process launch home. This is test-fixture plumbing, not a product shim.
        gateway_run._hermes_home = home
        try:
            from hermes_cli.config import _LOAD_CONFIG_CACHE, _RAW_CONFIG_CACHE

            _LOAD_CONFIG_CACHE.clear()
            _RAW_CONFIG_CACHE.clear()
        except Exception:
            pass

        self.home = home
        self.client = client
        self.config = load_gateway_config()
        self.runner = GatewayRunner(self.config)
        platform_config = self.config.platforms[Platform.DISCORD]
        adapter = self.runner._create_adapter(Platform.DISCORD, platform_config)
        if adapter is None:
            raise RuntimeError("stock Hermes did not create a Discord adapter; is the messaging extra installed?")
        self.adapter = adapter
        # Lines mirrored from GatewayRunner.start() (0.19.0 gateway/run.py ~7653-7660).
        adapter.set_message_handler(self.runner._handle_message)
        adapter.set_fatal_error_handler(self.runner._handle_adapter_fatal_error)
        adapter.set_session_store(self.runner.session_store)
        adapter.set_busy_session_handler(self.runner._handle_active_session_busy_message)
        adapter.set_topic_recovery_fn(self.runner._recover_telegram_topic_thread_id)
        adapter.set_authorization_check(self.runner._make_adapter_auth_check(adapter.platform))
        adapter._busy_text_mode = self.runner._busy_text_mode
        # Stand in for the post-connect state the real ``connect()`` leaves
        # behind (client object, allowlist parse, ready flag). The allowlist
        # parse is the same code ``connect()`` runs.
        allowed_env = os.getenv("DISCORD_ALLOWED_USERS", "")
        if allowed_env:
            from plugins.platforms.discord.adapter import _clean_discord_id

            adapter._allowed_user_ids = {_clean_discord_id(uid) for uid in allowed_env.split(",") if uid.strip()}
        adapter._client = client
        adapter._ready_event.set()
        adapter._running = True
        adapter._text_batch_delay_seconds = 0
        self.runner.adapters[Platform.DISCORD] = adapter
        self.runner._startup_restore_in_progress = False
        self.platform = Platform.DISCORD

    async def deliver(self, message: FakeDiscordMessage) -> bool:
        """Push one raw Discord message through the shipped adapter path."""

        return await self.adapter._dispatch_discord_message(message)

    async def settle(self, *, timeout: float = 30.0) -> None:
        """Wait until every session owner task has finished.

        Keyed on ``_session_tasks`` rather than ``_active_sessions``: stock
        releases the guard in the owner task's ``finally`` only when
        ``asyncio.current_task()`` is the registered task. A plugin that
        re-wraps the owner coroutine in a child task defeats that check and
        leaves the guard behind (see ``test_stock_session_guard_released``).
        """

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            tasks = getattr(self.adapter, "_session_tasks", {}) or {}
            pending = [k for k, t in tasks.items() if not t.done()]
            background = [t for t in getattr(self.adapter, "_background_tasks", set()) if not t.done()]
            if not pending and not background:
                return
            await asyncio.sleep(0.05)
        raise TimeoutError(
            "gateway did not settle: "
            f"pending={[k for k, t in (getattr(self.adapter, '_session_tasks', {}) or {}).items() if not t.done()]}"
        )

    def leaked_session_guards(self) -> list[str]:
        """Session keys whose guard is still held although the owner task finished."""

        tasks = getattr(self.adapter, "_session_tasks", {}) or {}
        return [
            key
            for key in getattr(self.adapter, "_active_sessions", {})
            if key not in tasks or tasks[key].done()
        ]

    async def close(self) -> None:
        try:
            await self.runner._async_session_store.close()  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            self.runner.session_store.close()
        except Exception:
            pass


def human_message(host: ProbeHost, *, channel_id: int, author_id: int, content: str, name: str = "person") -> FakeDiscordMessage:
    channel = host.client.channel(channel_id)
    return FakeDiscordMessage(
        host.client.next_message_id(),
        channel=channel,
        author=FakeDiscordUser(author_id, name=name),
        content=content,
    )


def peer_bot_message(host: ProbeHost, *, channel_id: int, author_id: int, content: str, name: str = "peer-bot") -> FakeDiscordMessage:
    channel = host.client.channel(channel_id)
    return FakeDiscordMessage(
        host.client.next_message_id(),
        channel=channel,
        author=FakeDiscordUser(author_id, name=name, bot=True),
        content=content,
    )


# ---------------------------------------------------------------------------
# Plugin loading through the stock PluginManager
# ---------------------------------------------------------------------------


def load_nunchi_via_plugin_manager() -> dict[str, Any]:
    """Load Nunchi the way ``gateway/run.py`` does: ``discover_plugins()`` on
    the process-global PluginManager with ``plugins.enabled: [nunchi]`` in
    ``config.yaml``. ``force=True`` so a second probe in the same process
    re-registers after ``unload_nunchi``.

    Tracks every host attribute Nunchi replaces (same technique as
    ``tests/v2/test_hermes_installed_contract.py``) so ``unload_nunchi`` can
    restore stock between probes. Tracking wraps Nunchi's own
    ``_set_shim_attribute`` only; it does not alter what is patched.
    """

    plugins = importlib.import_module("hermes_cli.plugins")
    hermes_v2 = importlib.import_module("nunchi.integrations.hermes_v2")
    patched: dict[tuple[Any, str], Any] = {}
    original_set = hermes_v2._set_shim_attribute

    def tracking_set(target: Any, name: str, replacement: Any) -> None:
        patched.setdefault((target, name), getattr(target, name))
        original_set(target, name, replacement)

    hermes_v2._set_shim_attribute = tracking_set
    try:
        plugins.discover_plugins(force=True)
    finally:
        hermes_v2._set_shim_attribute = original_set
    manager = plugins.get_plugin_manager()
    state = next((x for x in manager.list_plugins() if x["name"] == "nunchi"), None)
    if state is None:
        raise RuntimeError("installed nunchi entry point not found by hermes_cli.plugins")
    return {
        "manager": manager,
        "state": state,
        "module": plugins,
        "patched": patched,
        "owner": hermes_v2._SHIM_OWNER,
    }


def unload_nunchi(loaded: dict[str, Any]) -> None:
    """Restore the stock attributes Nunchi replaced so the next probe starts clean."""

    hermes_v2 = importlib.import_module("nunchi.integrations.hermes_v2")
    for (target, name), original in reversed(tuple(loaded["patched"].items())):
        setattr(target, name, original)
    hermes_v2._SHIM_OWNER = None
    hermes_v2._ORIGINAL_BASE_HANDLE = None


def unload_plugin_manager(loaded: dict[str, Any]) -> None:
    unload_nunchi(loaded)


def reset_nunchi_shims() -> None:
    """Undo Nunchi's process-local shims so later probes start from stock."""

    hermes_v2 = importlib.import_module("nunchi.integrations.hermes_v2")
    hermes_v2._SHIM_OWNER = None
    hermes_v2._ORIGINAL_BASE_HANDLE = None


def receipts(home: Path, profile: str = "default", *, room_id: str | None = None) -> list[dict[str, Any]]:
    """Read Nunchi receipts under the dashboard-default state dir (optionally one room)."""

    from nunchi.integrations.hermes_dashboard_store import default_config_paths
    from nunchi.integrations.hermes_v2 import load_pinned_config, room_state_directory

    paths = default_config_paths(profile, hermes_home=home)
    state = paths.state_directory
    out: list[dict[str, Any]] = []
    if not state.exists():
        return out
    wanted: Path | None = None
    if room_id is not None:
        config = load_pinned_config(paths.config, expected_sha256=paths.digest.read_text().strip(), hermes_profile=profile)
        for room in config.rooms:
            if room.binding.room_id == room_id:
                wanted = room_state_directory(config.state_directory, profile=profile, binding=room.binding)
    for path in sorted(state.rglob("receipts.jsonl")):
        if wanted is not None and path.parent.resolve() != wanted.resolve():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def run(coro: Any, *, timeout: float = 90.0) -> Any:
    async def _bounded():
        return await asyncio.wait_for(coro, timeout=timeout)

    return asyncio.run(_bounded())


def wait_until(predicate: Callable[[], bool], *, timeout: float = 20.0, interval: float = 0.05) -> bool:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def new_home() -> tuple[tempfile.TemporaryDirectory, Path]:
    tmp = tempfile.TemporaryDirectory(prefix="nunchi-normal-turn-")
    return tmp, Path(tmp.name) / "hermes-home"
