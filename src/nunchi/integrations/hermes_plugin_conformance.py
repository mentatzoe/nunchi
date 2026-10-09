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

Two lanes, one per platform the plugin supports:

- **Telegram**: a recording adapter in place of Telegram's, fed Hermes's
  `MessageEvent` directly.
- **Discord**: Hermes's stock Discord adapter (`plugins.platforms.discord`),
  with fake discord channels, threads and messages as Hermes's own Discord
  tests make them. A person's message enters through the adapter's own
  ingress (`_dispatch_discord_message`, what its `on_message` runs), so
  Hermes's mention gate, allowlists (the room's role, `ALLOWED_ROLES`) and
  auto-threading apply. Only the calls that would reach Discord are
  recorded instead: `send`, `send_typing`, the threads it opens
  (`_auto_create_thread`, which runs stock against the fake message) and
  every reaction added to a message. The kit does for the adapter what its
  `connect()` and `on_ready` do without a connection: gate settings,
  allowlists, resolving the allowed usernames against the guild's members
  (which rewrites ``DISCORD_ALLOWED_USERS``), ready. Text batching is as the
  profile's ``.env`` sets it (`ROOM_ENV`).

On both lanes the gateway installs the handlers Hermes installs on every
adapter before it connects (`GatewayRunner._wire_adapter_handlers`),
Hermes's busy-session handler among them.

For the kit's leak count, `HermesKitIntegration.visible` reports what the
gateway hands the adapter: its sends (on Discord at the stock adapter's send
boundary, so Hermes's formatting and chunking are not recorded), reactions,
typing, and the threads Hermes opened. Edits and DMs are not recorded; no
scenario plays them. What nothing public can stop is declared as known gaps
(`HERMES_KNOWN_GAPS`), and so is Hermes changing a real answer before the
plugin sees it. A ``fail`` step is the provider refusing the model call
(HTTP 400).

Hermes must be importable (a clean, pinned install with its ``[messaging]``
extra for discord.py; see `.github/workflows`). Without discord.py the
Discord lane is left out (`conformance_integrations`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import contextlib
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import shutil
import tempfile
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from ..attention import ParticipantProfile
from ..turn import SecretGuard
from ..turn_conformance import MODEL_REFUSED, KnownGap, ScriptedAgent
from .hermes_plugin.plugin import (
    DEFAULT_FAILURE_GRACE_SECONDS,
    DEFAULT_RECOVERY_GRACE_SECONDS,
    DISCORD_EPOCH_MS,
    PLUGIN_NAME,
    TOOL_NAMES,
    WAKE_MARKER,
    HermesRoomPlugin,
    HermesRoute,
)

ROOM = "conformance-room"
TURN_USER = "nunchi-turns"
# The Discord lane's bound channel, guild, bot and people: Discord ids are numbers.
DISCORD_ROOM = "1100"
DISCORD_GUILD = "70"
DISCORD_BOT = "9900"
DISCORD_PEOPLE = {"42": "Sam", "43": "Kim"}
# The room's role in the guild: everyone in DISCORD_PEOPLE has it.
DISCORD_ROOM_ROLE = "5500"
ROOMS = {"telegram": ROOM, "discord": DISCORD_ROOM}
# Who Hermes lets in: every person the room should hear, as Hermes drops
# anyone else before any plugin hook (integrations/hermes-plugin/README.md).
# On Telegram the user allowlist (`TELEGRAM_ALLOWED_USERS`), with the injected
# turns' identity. On Discord the room's role (`DISCORD_ALLOWED_ROLES`) and no
# user allowlist, so that Hermes refuses the people's direct messages; the
# turns' identity is in GATEWAY_ALLOWED_USERS (`ROOM_ENV`).
ALLOWED_USERS = {"telegram": f"u1,u2,{TURN_USER}", "discord": ""}
ALLOWED_ROLES = {"discord": DISCORD_ROOM_ROLE}
# What the room's profile `.env` needs besides the allowlist, by platform
# (integrations/hermes-plugin/README.md, On Discord):
# - GATEWAY_ALLOWED_USERS: the injected turns' identity. At each connect
#   Hermes's Discord adapter resolves DISCORD_ALLOWED_USERS against the
#   guild's members and drops every entry that is not a member, rewriting
#   the variable; it leaves this one alone.
# - HERMES_DISCORD_TEXT_BATCH_DELAY_SECONDS=0: no text batching, so each
#   message reaches the room with its own id, author, mentions and reply
#   target. Hermes's default (0.6 s) merges quick messages into the first.
ROOM_ENV: dict[str, dict[str, str]] = {
    "telegram": {},
    "discord": {
        "GATEWAY_ALLOWED_USERS": TURN_USER,
        "HERMES_DISCORD_TEXT_BATCH_DELAY_SECONDS": "0",
    },
}
# The Hermes settings a Nunchi room needs, so that people see only what the
# agent chose to do (integrations/hermes-plugin/README.md, "Hermes setup the
# room needs"). Per platform, under display.platforms.<platform>: no streamed
# drafts, tool progress lines, interim assistant text, "still working" notes,
# retry and budget status lines, reasoning, or runtime footer. The per-platform
# footer setting outranks the top-level one Hermes's /footer command writes.
ROOM_DISPLAY = {
    "streaming": False,
    "tool_progress": "off",
    "interim_assistant_messages": False,
    "long_running_notifications": False,
    "suppress_warning_notifications": True,
    "show_reasoning": False,
    "runtime_footer": {"enabled": False},
}
# Display settings Hermes reads only at the top level of `display`, for the
# whole profile: no footer after a failed file edit, no explanation added to
# a short or missing answer (agent/turn_explainers.py), and no busy notice.
# `busy_input_mode: interrupt` (Hermes's default, pinned): a person's message
# that arrives while Hermes still hands their previous one to the plugin
# waits in Hermes's busy queue as a message of its own. With `queue` Hermes
# merges such messages into the first one; with `steer` it files them out of
# order.
ROOM_DISPLAY_GLOBAL = {
    "file_mutation_verifier": False,
    "turn_completion_explainer": False,
    "busy_ack_enabled": False,
    "busy_input_mode": "interrupt",
}
# The display settings Hermes copies into the process's environment once,
# when it first imports gateway.run (`_DISPLAY_ENV_BRIDGE`).
_BUSY_ENV = {
    "busy_input_mode": "HERMES_GATEWAY_BUSY_INPUT_MODE",
    "busy_text_mode": "HERMES_GATEWAY_BUSY_TEXT_MODE",
    "busy_ack_enabled": "HERMES_GATEWAY_BUSY_ACK_ENABLED",
}
# The platform's own block (`telegram:`, `discord:`), for the whole bot: no
# typing indicator and no processing reactions on people's messages.
ROOM_PLATFORM = {
    "typing_indicator": False,
    "reactions": False,
}
# Discord's ingress, in the `discord:` block beside ROOM_PLATFORM: every
# message in the bound channel, and in the threads under it, reaches the
# plugin without an @mention, and Hermes opens no thread for it. Hermes's
# defaults (`require_mention`, `auto_thread`) drop unmentioned messages before
# any plugin hook and move each @mention into a new thread. The setting also
# makes every thread under the channel free-response, which this plugin
# version holds as part of the room.
BOUND_CHANNEL = "<bound channel id>"
ROOM_DISCORD = {
    "free_response_channels": [BOUND_CHANNEL],
    "free_response_auto_thread": False,
}
# Hermes's session keys, at the top of config.yaml: one session per person in
# a thread too (a Discord thread, a Telegram forum topic). Hermes's default
# shares a thread's session among everyone in it, and its text batching and
# busy queue, keyed by session, then merge different people's messages into
# the first one's event.
ROOM_SESSIONS = {"thread_sessions_per_user": True}
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


def room_settings(platform: str = "telegram", *, channel: str = BOUND_CHANNEL) -> dict[str, Any]:
    """The Hermes config a Nunchi room on ``platform`` needs, beside the plugin's entry.

    ``channel`` is the bound Discord channel's id.
    """

    block = dict(ROOM_PLATFORM)
    if platform == "discord":
        block.update(copy.deepcopy(ROOM_DISCORD), free_response_channels=[channel])
    return {
        **ROOM_SESSIONS,
        "display": {**ROOM_DISPLAY_GLOBAL, "platforms": {platform: copy.deepcopy(ROOM_DISPLAY)}},
        platform: block,
        "agent": {"disabled_toolsets": list(ROOM_DISABLED_TOOLSETS)},
    }


def room_env(platform: str = "telegram", *, allowed_users: str | None = None) -> dict[str, str]:
    """The room profile's `.env` the kit runs ``platform`` with: who Hermes lets in
    (`ALLOWED_USERS`, `ALLOWED_ROLES`) and `ROOM_ENV`."""

    allowed = ALLOWED_USERS[platform] if allowed_users is None else allowed_users
    roles = {f"{platform.upper()}_ALLOWED_ROLES": ALLOWED_ROLES[platform]} if platform in ALLOWED_ROLES else {}
    return {f"{platform.upper()}_ALLOWED_USERS": allowed, **roles, **ROOM_ENV[platform]}


def hermes_available() -> bool:
    """Whether Hermes is installed, without importing it (its import has side effects)."""

    import importlib.util

    return all(importlib.util.find_spec(name) is not None for name in ("gateway", "hermes_cli", "run_agent"))


def discord_available() -> bool:
    """Whether Hermes and discord.py (Hermes's ``[messaging]`` extra) are installed, without importing them."""

    import importlib.util

    try:
        return hermes_available() and importlib.util.find_spec("discord") is not None
    except (ImportError, ValueError):
        return False


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
        recovery_grace_seconds=_PENDING.get("recovery_grace_seconds", DEFAULT_RECOVERY_GRACE_SECONDS),
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
    text), or ``{"status": 400, "error": message}``: the provider refuses, or
    with a 5xx status is out of service. A text reply may add ``reasoning``
    (the provider's ``reasoning_content``), ``finish`` (its finish reason,
    such as ``length``), or ``drop``: the stream breaks off after the text.
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
                    kind = "server_error" if int(reply["status"]) >= 500 else "invalid_request_error"
                    payload = json.dumps({"error": {"message": str(reply.get("error", "refused")),
                                                    "type": kind}}).encode()
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
                if reply.get("reasoning"):
                    message["reasoning_content"] = reply["reasoning"]
                finish = reply.get("finish", finish)
                # An empty reply generated nothing, as a provider reports it.
                output = 5 if message.get("content") or message.get("tool_calls") or reply.get("reasoning") else 0
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
                if message.get("reasoning_content"):
                    delta["reasoning_content"] = message["reasoning_content"]
                if message.get("content"):
                    delta["content"] = message["content"]
                if message.get("tool_calls"):
                    delta["tool_calls"] = [dict(call, index=i) for i, call in enumerate(message["tool_calls"])]
                base = {"id": "conformance", "object": "chat.completion.chunk", "created": int(time.time()),
                        "model": "conformance/model"}
                if reply.get("drop"):
                    # The connection breaks mid-answer: no finish reason, no [DONE].
                    chunk = dict(base, choices=[{"index": 0, "delta": delta, "finish_reason": None}])
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                    self.wfile.flush()
                    self.close_connection = True
                    return
                for chunk in (
                    dict(base, choices=[{"index": 0, "delta": delta, "finish_reason": None}]),
                    dict(base, choices=[{"index": 0, "delta": {}, "finish_reason": finish}], usage=usage),
                ):
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                self.close_connection = True

        return Handler


# -- Discord, faked the way Hermes's own Discord tests fake it ----------------------------------


class _DiscordChannel:
    """A guild text channel: what Hermes's Discord adapter reads of one."""

    def __init__(self, world: "DiscordWorld", channel_id: int, name: str) -> None:
        self.world = world
        self.id = channel_id
        self.name = name
        self.guild = world.guild
        self.topic = None
        self.messages: dict[int, Any] = {}

    def history(self, *, limit: Any = None, before: Any = None, after: Any = None, oldest_first: Any = None):
        async def _none():
            return
            yield

        return _none()

    async def fetch_message(self, message_id: int) -> Any:
        message = self.messages.get(int(message_id))
        if message is None:
            # Discord answers 404 Unknown Message: the message is in another channel.
            raise LookupError(f"Unknown Message {message_id} in channel {self.id}")
        return message

    async def send(self, content: Any = None, **_: Any) -> Any:
        # Hermes posting straight into a channel, around the adapter's `send`.
        self.world.sent.append((str(self.id), str(content)))
        return SimpleNamespace(id=self.world.next_id())


class _DiscordThread(_DiscordChannel):
    """A thread under a channel."""

    def __init__(self, world: "DiscordWorld", thread_id: int, parent: _DiscordChannel, name: str) -> None:
        super().__init__(world, thread_id, name)
        self.parent = parent
        self.parent_id = parent.id


class _DiscordDM:
    """A direct message channel between one person and the bot."""

    def __init__(self, world: "DiscordWorld", channel_id: int, user: Any) -> None:
        self.world = world
        self.id = channel_id
        self.recipient = user
        self.guild = None
        self.name = None
        self.messages: dict[int, Any] = {}

    def history(self, **_: Any):
        return _DiscordChannel.history(self)

    async def fetch_message(self, message_id: int) -> Any:
        return await _DiscordChannel.fetch_message(self, message_id)


class _DiscordForum:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id


class _DiscordMessage:
    """A message as discord.py hands it to Hermes's `on_message`."""

    def __init__(
        self,
        world: "DiscordWorld",
        *,
        message_id: int,
        channel: _DiscordChannel,
        author: Any,
        content: str,
        mentions: list[Any],
        reply_to: int | None,
    ) -> None:
        import discord

        self.world = world
        self.id = message_id
        self.content = content
        self.mentions = mentions
        self.mention_everyone = False
        self.attachments: list[Any] = []
        self.reference = SimpleNamespace(message_id=reply_to, resolved=None) if reply_to else None
        self.type = discord.MessageType.reply if reply_to else discord.MessageType.default
        # Discord's own time for a message is in its id (`DiscordWorld.snowflake`);
        # the kit's short ids are not snowflakes and are sent now.
        sent = message_id >> 22
        self.created_at = (datetime.fromtimestamp((DISCORD_EPOCH_MS + sent) / 1000, timezone.utc) if sent > 0
                           else datetime.now(timezone.utc))
        self.channel = channel
        self.guild = channel.guild
        self.author = author
        channel.messages[message_id] = self

    async def add_reaction(self, emoji: Any) -> None:
        self.world.reactions.append((str(self.channel.id), str(self.id), str(emoji)))

    async def remove_reaction(self, emoji: Any, member: Any) -> None:
        self.world.reactions_removed.append((str(self.channel.id), str(self.id), str(emoji)))

    async def create_thread(self, *, name: str, auto_archive_duration: Any = None, reason: Any = None) -> Any:
        # A thread started from a message has that message's id; the message stays in its channel.
        return self.world.thread(self.id, parent=int(self.channel.id), name=name)


class _DiscordGuild:
    """The guild: Hermes reads its members to resolve allowlisted usernames, and their roles."""

    def __init__(self, world: "DiscordWorld") -> None:
        self.world = world
        self.id = int(DISCORD_GUILD)
        self.name = "Conformance"

    @property
    def members(self) -> list[Any]:
        return [self.world.bot, *self.world.people.values()]

    @property
    def member_count(self) -> int:
        return len(self.members)

    def get_member(self, user_id: int) -> Any:
        return next((member for member in self.members if member.id == int(user_id)), None)


def _discord_user(user_id: str, name: str, *, bot: bool) -> Any:
    return SimpleNamespace(id=int(user_id), bot=bot, name=name, display_name=name, global_name=None,
                           discriminator="0", roles=[])


class DiscordWorld:
    """The guild the Discord lane's bot is in: the bound channel, its threads, and who is there.

    What Hermes sends, the reactions it adds (its processing reactions and
    the plugin's), and the threads it opens are recorded here.
    """

    def __init__(self) -> None:
        self.guild = _DiscordGuild(self)
        self.bot = _discord_user(DISCORD_BOT, "Vigil", bot=True)
        self.people = {user_id: _discord_user(user_id, name, bot=False) for user_id, name in DISCORD_PEOPLE.items()}
        self.channels: dict[int, _DiscordChannel] = {}
        self.sent: list[tuple[str, str]] = []
        self.reactions: list[tuple[str, str, str]] = []
        self.reactions_removed: list[tuple[str, str, str]] = []
        self._ids = 900000
        self._last_snowflake_ms = 0
        self.channel(int(DISCORD_ROOM), name="room")
        for user_id in DISCORD_PEOPLE:
            self.give_role(user_id, DISCORD_ROOM_ROLE)

    def next_id(self) -> int:
        self._ids += 1
        return self._ids

    def snowflake(self) -> str:
        """A message id as Discord makes them, for a message sent now: the milliseconds
        since Discord's epoch above the 22nd bit. Each is at least 1 ms after the last."""

        moment = max(int(time.time() * 1000) - DISCORD_EPOCH_MS, self._last_snowflake_ms + 1)
        self._last_snowflake_ms = moment
        return str(moment << 22)

    def channel(self, channel_id: int, *, name: str = "channel") -> _DiscordChannel:
        return self.channels.setdefault(int(channel_id), _DiscordChannel(self, int(channel_id), name))

    def thread(self, thread_id: int, *, parent: int = int(DISCORD_ROOM), name: str = "thread") -> _DiscordThread:
        thread = _DiscordThread(self, int(thread_id), self.channels[int(parent)], name)
        self.channels[thread.id] = thread
        return thread

    def peer_bot(self, user_id: str, name: str) -> Any:
        """Another agent's bot in the guild."""

        return self.people.setdefault(user_id, _discord_user(user_id, name, bot=True))

    def person(self, user_id: str, name: str) -> Any:
        """Another person in the guild, without the room's role: Hermes does not let them in."""

        return self.people.setdefault(user_id, _discord_user(user_id, name, bot=False))

    def give_role(self, user_id: str, role_id: str, name: str = "room") -> None:
        """A guild role for a member, as Hermes's role allowlist (`DISCORD_ALLOWED_ROLES`) reads it."""

        member = self.people[user_id]
        member.roles = [*member.roles, SimpleNamespace(id=int(role_id), name=name)]
        member.guild = self.guild

    def dm(self, channel_id: int, user_id: str) -> _DiscordDM:
        """A direct message channel between ``user_id`` and the bot."""

        channel = _DiscordDM(self, int(channel_id), self.people[user_id])
        self.channels[channel.id] = channel
        return channel

    def message(
        self,
        text: str,
        *,
        message_id: str,
        user_id: str = "42",
        channel: str = DISCORD_ROOM,
        mentions: tuple[str, ...] = (),
        reply_to: str | None = None,
        reply_ping: bool = False,
    ) -> _DiscordMessage:
        """A message from ``user_id`` in ``channel``; each id in ``mentions`` is @mentioned in its text.

        ``reply_to`` makes it a reply; ``reply_ping`` pings the replied-to
        author, as Discord's Reply does by default.
        """

        mentioned = [self.bot if user == DISCORD_BOT else self.people[user] for user in mentions]
        content = " ".join([*(f"<@{user}>" for user in mentions), text]).strip()
        message = _DiscordMessage(
            self,
            message_id=int(message_id),
            channel=self.channels[int(channel)],
            author=self.people[user_id],
            content=content,
            mentions=mentioned,
            reply_to=int(reply_to) if reply_to else None,
        )
        if reply_to and reply_ping:
            # Discord's reply ping: the replied-to author is in the message's
            # mentions, though its text names nobody.
            target = self.channels[int(channel)].messages.get(int(reply_to))
            if target is not None and target.author not in message.mentions:
                message.mentions = [*message.mentions, target.author]
        return message


class _DiscordClient:
    """The parts of discord.py's client Hermes's adapter and platform actions use."""

    def __init__(self, world: DiscordWorld) -> None:
        self.world = world
        self.user = world.bot

    @property
    def guilds(self) -> list[Any]:
        return [self.world.guild]

    def get_channel(self, channel_id: int) -> Any:
        return self.world.channels.get(int(channel_id))

    async def fetch_channel(self, channel_id: int) -> Any:
        channel = self.get_channel(channel_id)
        if channel is None:
            raise LookupError(f"Unknown Channel {channel_id}")
        return channel

    def get_guild(self, guild_id: int) -> Any:
        return self.world.guild if int(guild_id) == self.world.guild.id else None

    def is_closed(self) -> bool:
        return False


def _discord_adapter(platform_config: Any, world: DiscordWorld) -> Any:
    """Hermes's stock Discord adapter, recording what would reach Discord."""

    from gateway.platforms.base import SendResult
    from plugins.platforms.discord.adapter import DiscordAdapter

    class RecordingDiscordAdapter(DiscordAdapter):
        def __init__(self) -> None:
            super().__init__(platform_config)
            self.world = world
            self.sent = world.sent
            self.reactions = world.reactions
            # Each typing action Hermes started, by channel, and each thread it opened.
            self.typing: list[str] = []
            self.threads: list[str] = []
            self._client = _DiscordClient(world)
            # What connect() sets up before it reaches Discord; the gateway
            # then does what on_ready does (`HermesGateway._start`).
            self._snapshot_gate_env()
            self._allowed_user_ids = self._get_allowed_users()
            self._allowed_role_ids = self._get_allowed_roles()
            self._running = True

        async def connect(self, *, is_reconnect: bool = False) -> bool:
            return True

        async def disconnect(self) -> None:
            self._mark_disconnected()

        async def send(self, chat_id, content, reply_to=None, metadata=None):
            # A thread in the metadata wins over the chat, as in Hermes's send.
            target = (metadata or {}).get("thread_id") or chat_id
            self.sent.append((str(target), content))
            return SendResult(success=True, message_id=str(world.next_id()))

        async def send_typing(self, chat_id, metadata=None):
            self.typing.append(str(chat_id))

        async def stop_typing(self, chat_id) -> None:
            return None

        async def _auto_create_thread(self, message):
            thread = await super()._auto_create_thread(message)
            if thread is not None:
                self.threads.append(str(thread.id))
            return thread

    return RecordingDiscordAdapter()


# -- a real Hermes gateway in a throwaway home ------------------------------------------------


class HermesGateway:
    """A `GatewayRunner` with a recording platform adapter, on its own event loop.

    ``platform`` is the lane: ``telegram`` (a recording adapter) or ``discord``
    (Hermes's stock Discord adapter on a fake guild, `DiscordWorld`).
    ``platform_block`` replaces the platform's own block (``telegram:`` or
    ``discord:``) of the room settings, for Hermes's defaults. The profile's
    ``.env`` is `room_env`; ``allowed_users`` replaces the platform's
    allowlist in it, and ``env`` adds variables or, with None, leaves one
    out.
    """

    def __init__(
        self,
        *,
        model: ScriptedModel,
        tool_search: str = "off",
        allowed_users: str | None = None,
        extra_config: Mapping[str, Any] | None = None,
        plugin_source: Path | None = None,
        plugin_settings: Mapping[str, Any] | None = None,
        platform_actions: bool = False,
        platform: str = "telegram",
        platform_block: Mapping[str, Any] | None = None,
        env: Mapping[str, str | None] | None = None,
    ) -> None:
        if platform not in ROOMS:
            raise ValueError(f"the kit has no {platform} lane")
        if platform == "discord" and not discord_available():
            # Before any process state changes.
            raise RuntimeError("the Discord lane needs discord.py: install Hermes with its [messaging] extra")
        self.platform = platform
        self.room = ROOMS[platform]
        self.world = DiscordWorld() if platform == "discord" else None
        profile_env = {**room_env(platform, allowed_users=allowed_users), **(env or {})}
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
        settings = room_settings(platform, channel=self.room)
        if platform_block is not None:
            settings[platform] = dict(platform_block)
        config: dict[str, Any] = {
            "model": {"default": "conformance/model", "provider": "custom", "base_url": model.base_url,
                      "api_key": "sk-local-conformance"},
            "plugins": {"enabled": [PLUGIN_NAME], "entries": {PLUGIN_NAME: entry}},
            # Operator setup for a Nunchi room (integrations/hermes-plugin/README.md):
            # only what the agent chose to do may reach the room.
            **settings,
            "tools": {"tool_search": {"enabled": tool_search}},
        }
        for key, value in (extra_config or {}).items():
            if isinstance(value, Mapping) and isinstance(config.get(key), dict):
                config[key] = {**config[key], **value}
            else:
                config[key] = value
        # JSON is YAML: Hermes reads it as its config.yaml.
        (self.home / "config.yaml").write_text(json.dumps(config), encoding="utf-8")
        (self.home / ".env").write_text(
            "".join(f"{key}={value}\n" for key, value in profile_env.items() if value is not None), encoding="utf-8"
        )
        # Hermes copies agent.max_turns into HERMES_MAX_ITERATIONS, and
        # display's busy settings into HERMES_GATEWAY_BUSY_* (`_BUSY_ENV`), for
        # the whole process (gateway/run.py), so they are put back with the rest
        # on close. Hermes bridges the busy settings only when it first imports
        # gateway.run: each gateway sets them from its own config, as that would.
        # Loading the config also copies the platform's block into the
        # platform's environment variables (DISCORD_REACTIONS and kin), where
        # the first value written wins over every later config: each gateway
        # starts without them and puts them back on close.
        platform_env = [key for key in os.environ if key.startswith(("TELEGRAM_", "DISCORD_"))]
        self._saved_env = {key: os.environ.get(key) for key in (
            "HERMES_HOME", "GATEWAY_ALLOWED_USERS", "GATEWAY_ALLOW_ALL_USERS",
            "HERMES_MAX_ITERATIONS", *_BUSY_ENV.values(),
            *(key for lane in ROOM_ENV.values() for key in lane), *profile_env, *platform_env)}
        for key in platform_env:
            if key.startswith(f"{platform.upper()}_"):
                del os.environ[key]
        for setting, variable in _BUSY_ENV.items():
            value = config.get("display", {}).get(setting)
            if value is None:
                os.environ.pop(variable, None)
            else:
                os.environ[variable] = str(value)
        os.environ["HERMES_HOME"] = str(self.home)
        # The profile's .env, as Hermes loads it; nothing from another lane's.
        for key in ("GATEWAY_ALLOWED_USERS", "GATEWAY_ALLOW_ALL_USERS",
                    *(key for lane in ROOM_ENV.values() for key in lane), *profile_env):
            os.environ.pop(key, None)
        for key, value in profile_env.items():
            if value is not None:
                os.environ[key] = value
        import gateway.run as gateway_run  # only once HERMES_HOME is the throwaway home

        self._gateway_run = gateway_run
        self._saved_home = getattr(gateway_run, "_hermes_home", None)
        gateway_run._hermes_home = self.home
        self._saved_discord: dict[str, Any] = {}
        try:
            if self.world is not None:
                # Hermes's Discord adapter tells channels, threads and DMs apart with
                # isinstance on discord.py's classes: its tests swap in fakes.
                import plugins.platforms.discord.adapter as discord_adapter

                if discord_adapter.discord is None:
                    raise RuntimeError("Hermes's Discord adapter found no discord.py")
                fakes = {"Thread": _DiscordThread, "DMChannel": _DiscordDM, "ForumChannel": _DiscordForum}
                self._discord_module = discord_adapter.discord
                self._saved_discord = {name: getattr(self._discord_module, name, None) for name in fakes}
                for name, fake in fakes.items():
                    setattr(self._discord_module, name, fake)
            self.loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self.loop.run_forever, name="nunchi-kit-gateway", daemon=True)
            self._thread.start()
            self.runner, self.adapter = self.run(self._start(), timeout=60)
        except BaseException:
            self.close()
            raise

    def run(self, coroutine: Any, timeout: float = 30) -> Any:
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout)

    async def _start(self) -> tuple[Any, Any]:
        import dataclasses

        from gateway.config import GatewayConfig, Platform, PlatformConfig, load_gateway_config
        from gateway.platforms.base import BasePlatformAdapter, SendResult

        # The platform settings as Hermes loads them from this home's config
        # (the README's `telegram:` or `discord:` block), as a real adapter gets them.
        loaded = await asyncio.to_thread(load_gateway_config)
        platform = Platform(self.platform)
        settings = loaded.platforms.get(platform) or PlatformConfig()
        # The session keys at the top of config.yaml, copied into the
        # adapter's settings as GatewayRunner._instantiate_adapter does.
        sessions = {
            "group_sessions_per_user": loaded.group_sessions_per_user,
            "thread_sessions_per_user": loaded.thread_sessions_per_user,
        }
        platform_config = dataclasses.replace(
            settings,
            enabled=True,
            token="conformance",
            extra={**sessions, **settings.extra},
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
        runner = GatewayRunner(GatewayConfig(sessions_dir=self.home / "sessions", **sessions))
        if self.world is not None:
            adapter = _discord_adapter(platform_config, self.world)
            # What on_ready runs on a live connect: allowlisted usernames
            # resolved against the guild's members, the rest dropped.
            await adapter._resolve_allowed_usernames()
            adapter._ready_event.set()
        else:
            adapter = RecordingAdapter()
        runner.adapters = {platform: adapter}
        adapter.gateway_runner = runner
        # The handlers Hermes installs on every adapter before it connects
        # (run_startup.py, and run_adapters.py on a reconnect): its message
        # handler, and its busy-session handler, which files a message that
        # arrives while the sender's previous one is still being handled.
        runner._wire_adapter_handlers(adapter)
        runner._gateway_loop = asyncio.get_running_loop()
        runner._running = True
        runner._install_plugin_message_injector()
        return runner, adapter

    async def person_says(
        self, text: str, *, user_id: str = "u1", user_name: str = "Sam", message_id: str, **fields: Any
    ) -> bool:
        """A person's message, as the platform adapter hands it to Hermes.

        On Telegram ``fields`` are more `MessageEvent` fields. On Discord the
        message enters through the adapter's own ingress, which may drop it
        (the answer is whether it reached the gateway); ``fields`` are
        `DiscordWorld.message`'s (``channel``, ``mentions``, ``reply_to``) and
        ``user_id`` is one of `DISCORD_PEOPLE` (``u1`` and ``u2`` stand for
        the first two).
        """

        if self.world is not None:
            people = list(DISCORD_PEOPLE)
            user_id = {"u1": people[0], "u2": people[1]}.get(user_id, user_id)
            message = self.world.message(text, message_id=message_id, user_id=user_id, **fields)
            return bool(await self.adapter._dispatch_discord_message(message))
        from gateway.platforms.base import MessageEvent, MessageType

        source = self.adapter.build_source(chat_id=ROOM, chat_type="group", user_id=user_id, user_name=user_name)
        await self.adapter.handle_message(
            MessageEvent(text=text, message_type=MessageType.TEXT, source=source, message_id=message_id, **fields)
        )
        return True

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

        if hasattr(self, "runner"):
            with contextlib.suppress(Exception):
                self.run(stop(), timeout=10)
        if hasattr(self, "loop"):
            self.loop.call_soon_threadsafe(self.loop.stop)
            if hasattr(self, "_thread"):
                self._thread.join(timeout=10)
        self._gateway_run._hermes_home = self._saved_home
        for name, original in self._saved_discord.items():
            setattr(self._discord_module, name, original)
        for key in [key for key in os.environ if key.startswith(("TELEGRAM_", "DISCORD_"))]:
            if key not in self._saved_env:
                del os.environ[key]
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

    def fail(self, turn_id: str) -> None:
        # The provider refuses the call for good (HTTP 400); Hermes fails the
        # run, and the plugin ends the turn once Hermes stops asking.
        self.model.reply({"status": 400, "error": MODEL_REFUSED})
        self.end(turn_id, False)

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

    Hermes runs with the room settings (`room_settings`) for ``platform``
    (``telegram`` or ``discord``, see `HermesGateway`). ``display`` replaces
    the platform's display settings, ``platform_block`` its own block
    (``discord:``), ``agent`` adds Hermes agent settings, and
    ``extra_config`` changes any other part of the config, one level deep
    (``{"display": {"turn_completion_explainer": True}}`` keeps the rest of
    ``display``). ``allowed_users`` and ``env`` change the profile's
    ``.env`` (`HermesGateway`).
    """

    def __init__(
        self,
        *,
        profile: ParticipantProfile,
        guard: SecretGuard,
        room_factory: Any = None,
        tool_search: str = "off",
        allowed_users: str | None = None,
        start_timeout_seconds: float = 30.0,
        result_wait_seconds: float = 5.0,
        platform_actions: bool = False,
        display: Mapping[str, Any] | None = None,
        roles: tuple[str, ...] = ("react", "context"),
        agent: Mapping[str, Any] | None = None,
        extra_config: Mapping[str, Any] | None = None,
        failure_grace_seconds: float | None = None,
        recovery_grace_seconds: float | None = None,
        platform: str = "telegram",
        platform_block: Mapping[str, Any] | None = None,
        env: Mapping[str, str | None] | None = None,
    ) -> None:
        if not hermes_available():
            raise RuntimeError("Hermes is not installed in this Python environment")
        self.platform = platform
        self.room = ROOMS[platform]
        self.route = HermesRoute(platform=platform, chat_id=self.room, turn_user_id=TURN_USER)
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
            **({} if recovery_grace_seconds is None else {"recovery_grace_seconds": recovery_grace_seconds}),
        )
        extra: dict[str, Any] = {}
        if display is not None:
            extra["display"] = {"platforms": {platform: dict(display)}}
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
                platform=platform,
                platform_block=platform_block,
                env=env,
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
    ) -> bool:
        """A person's message (`HermesGateway.person_says`); on Discord, whether it reached the gateway."""

        return self.gateway.run(
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
        if getattr(self, "_closed", False):
            return
        self._closed = True
        self.model.close()
        gateway = getattr(self, "gateway", None)
        if gateway is not None:
            gateway.close()
        _PENDING.clear()


# -- the kit's integration -----------------------------------------------------------------------


# What Hermes a50406d9's strip_think_blocks makes of each final-real-post
# form it changes, for when Hermes cannot be imported.
_HERMES_STRIPPED = {
    "Here's what R1 returned:\n```\n<think>\nThe user wants a haiku.\n```": "Here's what R1 returned:\n```",
    "Wrap the panel in it:\n```jsx\n<Reasoning>{text}</Reasoning>\n```": "Wrap the panel in it:\n```jsx\n\n```",
    "The schema:\n```xml\n<thought>check inputs</thought>\n```": "The schema:\n```xml\n\n```",
    "<reasoning> tags are what the model hides from you.": "",
    "<think>plan</think> is how R1 marks its plan.": " is how R1 marks its plan.",
}


def hermes_strips(text: str) -> str:
    """Hermes's own change to a final answer before any plugin hook (contract gap 15).

    Its ``strip_think_blocks``, from the installed Hermes; without one, the
    text it makes of each final-real-post form. A text with no known result
    is returned unchanged, so any change the kit sees in it fails.
    """

    try:
        from agent.agent_runtime_helpers import strip_think_blocks
    except ImportError:
        return _HERMES_STRIPPED.get(text, text)
    return strip_think_blocks(None, text)


# What Hermes shows the room by itself, in a room set up as the README says,
# that no hook or setting stops: the contract's candidate gaps, and the
# README's Known gaps.
HERMES_KNOWN_GAPS = (
    KnownGap(
        "Hermes posts its own failed-turn notice when the model call fails; no hook or setting stops it "
        "(harness-contract.md, candidate gap 7)",
        scenarios=("final-harness-failure",),
        kind="message",
        text="Your request was not processed",
    ),
    KnownGap(
        "the fresh run the plugin starts for the agent to answer again (after looking again, or after a "
        "refused answer) runs as Hermes's queued follow-up, which sends typing whatever typing_indicator "
        "says (harness-contract.md, candidate gap 10)",
        scenarios=("final-look-again", "final-secret"),
        kind="typing",
    ),
    KnownGap(
        "Hermes strips thinking-tag names (<think>, <thinking>, <reasoning>, <thought>, any case, code "
        "included) from the final answer before any plugin hook, so a real answer that names or quotes "
        "a tag reaches the library changed, or as nothing when it starts with one (harness-contract.md, "
        "candidate gap 15)",
        scenarios=("final-real-post",),
        kind="post",
        transform=hermes_strips,
    ),
)


class HermesKitIntegration:
    """The plugin in a real Hermes gateway, on one platform's lane."""

    posting = "final-answer"
    # Hermes ends a run with its own text when its model gives no answer.
    harness_text = True
    # The scripted model can refuse a call, as a provider does.
    model_failure = True
    known_gaps = HERMES_KNOWN_GAPS

    def __init__(self, *, tool_search: str = "off", platform: str = "telegram") -> None:
        self.tool_search = tool_search
        self.platform = platform
        self.name = f"Hermes plugin ({platform.capitalize()})"
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
            platform=self.platform,
        )
        plugin = harness.plugin

        def first_request() -> None:
            # Hermes asked the model for the first time in a turn: that turn's script starts.
            turn = plugin.participant.active
            if turn is not None:
                agent.play_once(turn, lambda: HermesSurface(harness.gateway, harness.model, plugin, turn))

        harness.model.on_request = first_request
        return plugin.participant

    def visible(self) -> list[dict[str, Any]]:
        """Everything the adapter would have shown on the platform: messages, reactions, typing, threads."""

        if self.harness is None:
            return []
        adapter = self.harness.gateway.adapter
        world = self.harness.gateway.world
        shown: list[dict[str, Any]] = [
            {"kind": "message", "where": chat, "text": text} for chat, text in adapter.sent
        ]
        shown += [
            {"kind": "reaction", "where": chat, "reaction": emoji} for chat, _, emoji in adapter.reactions
        ]
        if world is not None:
            shown += [
                {"kind": "reaction removed", "where": chat, "reaction": emoji}
                for chat, _, emoji in world.reactions_removed
            ]
        shown += [{"kind": "typing", "where": chat} for chat in adapter.typing]
        shown += [{"kind": "thread", "where": thread} for thread in getattr(adapter, "threads", ())]
        return shown

    def close(self) -> None:
        if self.harness is not None:
            self.harness.close()
            self.harness = None


def conformance_integrations() -> list[HermesKitIntegration]:
    """Both lanes: the plugin on Telegram and on Discord.

    Without discord.py the Discord lane is left out, with a note on stderr.
    """

    lanes = [HermesKitIntegration(platform="telegram")]
    if discord_available():
        lanes.append(HermesKitIntegration(platform="discord"))
    else:
        import sys

        print("Hermes plugin (Discord): not run, discord.py is not installed (hermes-agent[messaging])",
              file=sys.stderr)
    return lanes


__all__ = [
    "ALLOWED_ROLES",
    "ALLOWED_USERS",
    "BOUND_CHANNEL",
    "DISCORD_BOT",
    "DISCORD_ROOM",
    "DISCORD_ROOM_ROLE",
    "DiscordWorld",
    "HERMES_KNOWN_GAPS",
    "HermesGateway",
    "HermesHarness",
    "HermesKitIntegration",
    "HermesSurface",
    "ScriptedModel",
    "ROOM_DISABLED_TOOLSETS",
    "ROOM_DISCORD",
    "ROOM_DISPLAY",
    "ROOM_DISPLAY_GLOBAL",
    "ROOM_ENV",
    "ROOM_PLATFORM",
    "ROOM_SESSIONS",
    "WAKE_MARKER",
    "conformance_integrations",
    "discord_available",
    "hermes_available",
    "isolate",
    "register_for_kit",
    "room_env",
    "room_settings",
]
