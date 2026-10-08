"""Nunchi as a Hermes plugin: consume and start, final-answer posting (#94 step 9e).

Built from `docs/harness-guide.md`, on Hermes's public plugin surface only
(`hermes_cli.plugins.PluginContext`): hooks, tools, `inject_message` and
`platform_actions`. Nothing in Hermes is patched or wrapped.

How a turn goes:

1. **Ingress.** `pre_gateway_dispatch` notes what Hermes knows about each
   message in the bound chat that its admission payload leaves out: the
   message it replies to, when it was sent, who it mentions, and whether its
   author is a bot. `post_gateway_admission` hands the message to the `Room`
   with those facts and answers ``handled`` with no reply, so Hermes never
   runs its agent on a person's message.
2. **Start.** When the library decides, `start` injects the turn's text into
   the chat as the plugin's own message (`ctx.inject_message(origin=...)`),
   after a wake marker that only this plugin knows.
3. **Bind.** `pre_llm_call` sees the run's user message; when it carries the
   open wake's marker, the run is bound to the turn.
4. **Steering.** `transform_tool_result` adds the room's news to every tool
   result in a bound run.
5. **What the model wrote.** `post_api_request` reports each of the run's
   model responses to the library (``model_text``), so only the model's own
   words can become the agent's post. Text Hermes puts in place of a missing
   answer, such as ``(empty)`` or its iteration-limit notice, fails the turn.
6. **Finish.** `transform_llm_output` hands the final answer to the library
   and returns what Hermes should deliver: the answer, or `[SILENT]`. On
   ``continue`` the answer is silenced and, when the run ends, a fresh run is
   injected with the library's text. If the hook itself fails, the turn
   fails and Hermes gets `[SILENT]`: a raising hook makes Hermes post the
   raw draft.
7. **End.** `on_session_end` reports the run's end. A provider failure that
   Hermes does not recover from fires no end hook; `api_request_error` and
   `pre_api_request` let the plugin end that turn as a failure promptly.

The adapter decides nothing about whether or what the agent says. Any run that
carries a Nunchi marker but is not bound to the open turn (a cancelled or
stale turn) is silenced, since only the library may commit a post.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import hmac
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
from collections.abc import Iterable, Mapping
from typing import Any

from nunchi.adapters.telegram import TELEGRAM_TOKEN_PATTERNS
from nunchi.attention import AttentionModelSelection, HostStructuredAttentionModel
from nunchi.integrations.discord_participant_transport import DISCORD_TOKEN_PATTERNS
from nunchi.participant import TransportResult
from nunchi.reactions import UNAVAILABLE_REACTION_CAPABILITY, ReactionCapability
from nunchi.turn import HarnessDelivery, SecretGuard, Turn, TurnParticipant

logger = logging.getLogger("nunchi.hermes_plugin")

PLUGIN_NAME = "nunchi-room"
TOOLSET = "nunchi_room"
SECTION = "hermes"
# Hermes's own silence: a bare marker on a plugin-injected turn sends nothing
# (gateway/response_filters.py). The agent is taught this one.
SILENCE_MARKER = "[SILENT]"
# The other whole answers Hermes treats as silence: LIVE_GATEWAY_SILENT_MARKERS
# in gateway/response_filters.py at Hermes a50406d9, without the taught marker.
# Hermes sends nothing for them, so the library must remember silence too.
HERMES_SILENT_ANSWERS = ("SILENT", "NO_REPLY", "NO REPLY", "[静默]", "静默", "[沉默]", "沉默")
WAKE_MARKER = '<nunchi_wake id="{}"/>'
_WAKE = re.compile(r'<nunchi_wake id="([A-Za-z0-9_-]+)"/>')
TOOL_NAMES = {
    "react": "room_react",
    "context": "room_context",
    "propose": "room_propose",
    "withdraw": "room_withdraw",
}
# Hermes ships add_reaction for these platforms (hermes_cli/platform_actions.py).
_REACTION_PLATFORMS = frozenset({"telegram", "discord"})
# The capability `ctx.platform_actions` checks on every call.
PLATFORM_ACTIONS = "gateway.platform_actions"
# Platform credentials Hermes holds that the agent must never post, unless
# the hermes section names its own (``withheld_env``).
DEFAULT_WITHHELD_ENV = ("TELEGRAM_BOT_TOKEN", "DISCORD_BOT_TOKEN", "SLACK_BOT_TOKEN")
# Slack's bot and user tokens (``xoxb-``, ``xoxp-`` and kin) and app-level
# tokens (``xapp-``).
SLACK_TOKEN_PATTERNS = (
    re.compile(r"\bxox[abeprs]-\d+-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bxapp-\d-[A-Za-z0-9]+-\d+-[A-Za-z0-9]+"),
)
# The shapes of the platform tokens Hermes may hold.
TOKEN_PATTERNS = (*TELEGRAM_TOKEN_PATTERNS, *DISCORD_TOKEN_PATTERNS, *SLACK_TOKEN_PATTERNS)
DEFAULT_START_TIMEOUT_SECONDS = 120.0
_REACTION_TIMEOUT_SECONDS = 20.0
# The library waits this long for the host's commit inside `finish`. Hermes
# abandons a transform hook after `plugins.hook_callback_timeout` (30 s by
# default) and then delivers the raw draft, so stay well under it.
DEFAULT_RESULT_WAIT_SECONDS = 20.0
# After a provider failure Hermes will not retry, how long to wait for it to
# start another model request (a fallback provider, a rotated credential)
# before the turn ends as a failure. Hermes fires no end hook on that path.
DEFAULT_FAILURE_GRACE_SECONDS = 5.0
# Attention on Hermes's own model (`ctx.llm`), instead of a configured route.
HOST_MODEL_KIND = "hermes-host"
HOST_MODEL_REFUSED = (
    "Hermes refused the attention provider/model this plugin asked for. Allow it "
    "under plugins.entries.nunchi-room.llm (allow_provider_override, "
    "allow_model_override, allowed_providers, allowed_models), then restart "
    "Hermes. No other attention model was used."
)
_THINKING = re.compile(r"<thinking>.*?(?:</thinking>|\Z)", re.S | re.I)
# Messages noted at dispatch whose admission has not come yet, and runs the
# plugin closed itself that Hermes may still finish.
_NOTED_MESSAGES = 256
_CLOSED_RUNS = 256


class HermesPluginError(RuntimeError):
    """The plugin could not hand a turn to Hermes. Never silence."""


@dataclass(frozen=True)
class HermesRoute:
    """The one Hermes chat this participant lives in, and who its turns run as.

    ``turn_user_id`` is the identity Hermes runs injected turns as. It must be
    one of the platform's allowed users, or Hermes drops the turn.
    """

    platform: str
    chat_id: str
    turn_user_id: str
    chat_type: str = "group"
    thread_id: str | None = None
    turn_user_name: str = "Nunchi"

    @classmethod
    def from_section(cls, section: Any) -> "HermesRoute":
        if not isinstance(section, Mapping):
            raise ValueError("the hermes section must be an object")
        allowed = {
            "platform",
            "chat_id",
            "chat_type",
            "thread_id",
            "turn_user_id",
            "turn_user_name",
            "withheld_env",
            "start_timeout_seconds",
        }
        unknown = set(section) - allowed
        if unknown:
            raise ValueError(f"the hermes section has unknown keys: {sorted(unknown)}")
        try:
            route = cls(
                platform=str(section["platform"]).strip().lower(),
                chat_id=str(section["chat_id"]),
                turn_user_id=str(section["turn_user_id"]),
                chat_type=str(section.get("chat_type", "group")),
                thread_id=None if section.get("thread_id") is None else str(section["thread_id"]),
                turn_user_name=str(section.get("turn_user_name", "Nunchi")),
            )
        except KeyError as exc:
            raise ValueError(f"the hermes section needs {exc.args[0]}") from exc
        if not route.platform or not route.chat_id or not route.turn_user_id:
            raise ValueError("platform, chat_id and turn_user_id must be non-empty")
        return route

    def origin(self) -> dict[str, Any]:
        """Where injected turns run: `SessionSource.to_dict()` shape."""

        origin: dict[str, Any] = {
            "platform": self.platform,
            "chat_id": self.chat_id,
            "chat_type": self.chat_type,
            "user_id": self.turn_user_id,
            "user_name": self.turn_user_name,
        }
        if self.thread_id is not None:
            origin["thread_id"] = self.thread_id
        return origin

    def holds(self, platform: str, source: Mapping[str, Any]) -> bool:
        """Whether an admitted message was posted in this chat."""

        if str(platform).lower() != self.platform or str(source.get("chat_id")) != self.chat_id:
            return False
        if self.thread_id is None:
            return True
        return str(source.get("thread_id")) == self.thread_id

    def event_id(self, message_id: str) -> str:
        return f"{self.platform}:message:{message_id}"

    def message_id(self, event_id: str) -> str | None:
        prefix = f"{self.platform}:message:"
        return event_id[len(prefix):] if event_id.startswith(prefix) else None

    def actor_id(self, user_id: str) -> str:
        return f"{self.platform}:user:{user_id}"


@dataclass(frozen=True)
class _MessageFacts:
    """What Hermes's dispatch hook knew about one message.

    ``mentioned`` and ``author_is_bot`` come from the platform's own message
    object, which exists only in-process: under `plugins.isolation: host` they
    are unknown (None).
    """

    reply_to_message_id: str | None = None
    timestamp: str | None = None
    addressed: bool = False
    mentioned: tuple[str, ...] | None = None
    mentions_room: bool | None = None
    author_is_bot: bool | None = None


def _timestamp(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    # Hermes's default is a naive local time; platforms give aware ones.
    moment = value.astimezone(timezone.utc)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _message_facts(event: Any, route: HermesRoute) -> _MessageFacts:
    """Read a Hermes `MessageEvent`, and its platform message when there is one."""

    reply_to = getattr(event, "reply_to_message_id", None)
    raw = getattr(event, "raw_message", None)
    mentioned: list[str] | None = None
    users = getattr(raw, "mentions", None)  # Discord
    if isinstance(users, (list, tuple)):
        mentioned = [route.actor_id(str(user.id)) for user in users if getattr(user, "id", None) is not None]
    entities = getattr(raw, "entities", None)  # Telegram: only a text mention names a user id
    if isinstance(entities, (list, tuple)):
        mentioned = [
            route.actor_id(str(entity.user.id))
            for entity in entities
            if getattr(entity, "type", None) == "text_mention" and getattr(entity, "user", None) is not None
        ]
    everyone = getattr(raw, "mention_everyone", None)
    author = getattr(raw, "author", None) or getattr(raw, "from_user", None)
    is_bot = getattr(author, "bot", None)
    if not isinstance(is_bot, bool):
        is_bot = getattr(author, "is_bot", None)
    return _MessageFacts(
        reply_to_message_id=str(reply_to) if reply_to else None,
        timestamp=_timestamp(getattr(event, "timestamp", None)),
        # The platform adapter says the message was meant for this bot.
        addressed=getattr(event, "reply_expected", None) is True,
        mentioned=tuple(dict.fromkeys(mentioned)) if mentioned is not None else None,
        mentions_room=everyone if isinstance(everyone, bool) else None,
        author_is_bot=is_bot if isinstance(is_bot, bool) else None,
    )


@dataclass
class _Run:
    """One Hermes run (one `run_conversation`) that carried a Nunchi marker."""

    turn_id: str
    session_id: str
    task_id: str
    bound: bool = False
    raw_answer: str | None = None
    # Model requests Hermes started in this run (`pre_api_request`).
    requests: int = 0
    # Why the run is failing: a provider error Hermes will not retry. Cleared
    # when Hermes starts another request.
    failure: str | None = None


@dataclass
class _Wake:
    """The open turn as the driver started it."""

    turn: Turn
    # The text of a fresh run to start when the current run ends (final-answer
    # posting's `continue` on a harness that cannot continue a run).
    fresh_run: str | None = None
    # A fresh run was injected; it binds with no wake id.
    continuing: bool = False


class HermesReactions:
    """The `native` side of `HarnessDelivery`: the agent's own reactions.

    Hermes lets a plugin react through `ctx.platform_actions.add_reaction`,
    behind the `gateway.platform_actions` capability. It is a coroutine bound to
    the gateway's loop; the plugin learns that loop in its async ingress hook.
    """

    def __init__(self, plugin: "HermesRoomPlugin") -> None:
        self.plugin = plugin

    def _available(self) -> bool:
        ctx = self.plugin.ctx
        if ctx is None or self.plugin.route.platform not in _REACTION_PLATFORMS:
            return False
        try:
            return bool(ctx.has_capability(PLATFORM_ACTIONS))
        except Exception:
            return False

    def ordinary_action_capabilities(self) -> list[str]:
        return ["reaction"] if self._available() else []

    def reaction_capability(self) -> ReactionCapability:
        if not self._available():
            return UNAVAILABLE_REACTION_CAPABILITY
        return ReactionCapability(
            supported=True,
            authenticated=True,
            # Hermes offers add_reaction only; Telegram replaces the bot's reaction.
            operations=("add",),
            reactions=("*",),
            permissions_revision=f"hermes:{PLATFORM_ACTIONS}",
        )

    def dispatch(self, *, action: Mapping[str, Any], wake: Mapping[str, Any]) -> TransportResult:
        if action.get("kind") != "reaction" or action.get("operation", "add") != "add":
            return TransportResult("unavailable", "Hermes lets this plugin add reactions only")
        route = self.plugin.route
        message_id = route.message_id(str(action.get("target_event_id", "")))
        loop = self.plugin.gateway_loop
        ctx = self.plugin.ctx
        if message_id is None or ctx is None:
            return TransportResult("failed", "the reaction's target is not a message in this chat")
        if loop is None or loop.is_closed():
            return TransportResult("unavailable", "the Hermes gateway is not running")
        future = asyncio.run_coroutine_threadsafe(
            ctx.platform_actions.add_reaction(
                platform=route.platform,
                chat_id=route.chat_id,
                message_id=message_id,
                emoji=str(action.get("reaction", "")),
            ),
            loop,
        )
        try:
            result = future.result(timeout=_REACTION_TIMEOUT_SECONDS)
        except Exception as exc:  # timeout or a loop that went away
            future.cancel()
            return TransportResult("unknown", f"Hermes did not confirm the reaction: {type(exc).__name__}")
        if isinstance(result, Mapping) and result.get("ok"):
            return TransportResult("sent", "Hermes added the reaction")
        error = result.get("error", "unknown") if isinstance(result, Mapping) else "unknown"
        return TransportResult("failed", f"Hermes refused the reaction ({error})")


class HermesRoomPlugin:
    """One participant in one Hermes chat: the turn driver and Hermes's hooks.

    The library's side is a `TurnParticipant` (with this object as its driver)
    and a `Room`. In a running gateway the plugin builds the `Room` on the
    first admitted message (`room_factory`), so plain `hermes` CLI processes
    that load the plugin never open the room's state. The conformance kit
    builds its own `Room` around `participant` instead.
    """

    def __init__(
        self,
        *,
        profile: Any,
        guard: SecretGuard,
        route: HermesRoute,
        roles: Iterable[str] = ("react", "context"),
        result_wait_seconds: float = DEFAULT_RESULT_WAIT_SECONDS,
        start_timeout_seconds: float = DEFAULT_START_TIMEOUT_SECONDS,
        failure_grace_seconds: float = DEFAULT_FAILURE_GRACE_SECONDS,
        room_factory: Any = None,
    ) -> None:
        self.route = route
        self.room_factory = room_factory
        self.room: Any = None
        self.ctx: Any = None
        self.gateway_loop: asyncio.AbstractEventLoop | None = None
        self.failure_grace_seconds = float(failure_grace_seconds)
        self.participant = TurnParticipant(
            profile=profile,
            driver=self,
            guard=guard,
            tool_names=TOOL_NAMES,
            roles=tuple(roles),
            result_wait_seconds=result_wait_seconds,
            silence_marker=SILENCE_MARKER,
            also_silent=HERMES_SILENT_ANSWERS,
            # `post_api_request` reports what the model wrote: Hermes's own
            # text in place of a missing answer is never the agent's post.
            model_text=True,
            # Hermes may accept an injected turn and drop it later at dispatch,
            # telling no plugin: the library fails a run that never binds.
            bind_timeout_seconds=float(start_timeout_seconds),
        )
        self._lock = threading.RLock()
        self._wake: _Wake | None = None
        self._runs: dict[str, _Run] = {}
        # Runs the plugin ended itself (a provider failure); whatever Hermes
        # still hands over for them is silenced.
        self._closed_runs: OrderedDict[str, None] = OrderedDict()
        # Tool handlers get task_id and session_id, not the run's turn_id.
        self._run_keys: dict[str, str] = {}
        self._room_lock = threading.Lock()
        # Facts noted at dispatch, by Hermes message id, until admission.
        self._noted: OrderedDict[str, _MessageFacts] = OrderedDict()

    # -- registration --------------------------------------------------------------

    def register(self, ctx: Any) -> None:
        """Register the room tools and the hooks on Hermes's plugin context."""

        self.ctx = ctx
        for spec in self.participant.attach():
            name = spec["name"]
            ctx.register_tool(
                name=name,
                toolset=TOOLSET,
                schema={
                    "name": name,
                    "description": spec["description"],
                    "parameters": spec["inputSchema"],
                },
                handler=self._tool_handler(name),
            )
        ctx.register_hook("pre_gateway_dispatch", self.on_dispatch)
        ctx.register_hook("post_gateway_admission", self.on_admission)
        ctx.register_hook("pre_llm_call", self.on_pre_llm_call)
        ctx.register_hook("transform_tool_result", self.on_tool_result)
        ctx.register_hook("pre_api_request", self.on_api_request)
        ctx.register_hook("post_api_request", self.on_api_response)
        ctx.register_hook("api_request_error", self.on_api_error)
        ctx.register_hook("transform_llm_output", self.on_final_answer)
        ctx.register_hook("on_session_end", self.on_run_end)

    # -- the room --------------------------------------------------------------------

    def _ensure_room(self) -> Any:
        if self.room is None and self.room_factory is not None:
            with self._room_lock:
                if self.room is None:
                    self.room = self.room_factory(self)
        return self.room

    def transport(self) -> HarnessDelivery:
        """Hermes posts the agent's messages; reactions go through platform actions."""

        # Hermes drops the bot's own messages before any plugin hook, so the
        # library puts each delivered message into the room log itself.
        return HarnessDelivery(HermesReactions(self), room_shows_own_messages=False)

    # -- ingress -----------------------------------------------------------------------

    def on_dispatch(self, event: Any = None, **_: Any) -> None:
        """Note what Hermes knows about a message in the bound chat; dispatch goes on.

        Hermes's admission payload has no reply target, time, mentions or bot
        flag, and on Discord Hermes takes the bot's own mention out of the
        text. Without these, the room cannot tell who a message was for.
        """

        try:
            source = getattr(event, "source", None)
            platform = getattr(getattr(source, "platform", None), "value", getattr(source, "platform", ""))
            where = {"chat_id": getattr(source, "chat_id", None), "thread_id": getattr(source, "thread_id", None)}
            message_id = getattr(event, "message_id", None)
            if not message_id or not self.route.holds(str(platform or ""), where):
                return None
            facts = _message_facts(event, self.route)
            with self._lock:
                self._noted[str(message_id)] = facts
                while len(self._noted) > _NOTED_MESSAGES:
                    self._noted.popitem(last=False)
        except Exception:
            # The message still reaches the room, with fewer facts.
            logger.exception("nunchi-room: could not read a message at dispatch")
        return None

    async def on_admission(
        self,
        session_key: str = "",
        platform: str = "",
        source: Mapping[str, Any] | None = None,
        message_id: str | None = None,
        text: str = "",
        **_: Any,
    ) -> dict[str, Any] | None:
        """Every admitted message in the bound chat goes to the room; Hermes skips its run."""

        self.gateway_loop = asyncio.get_running_loop()
        source = source or {}
        if not self.route.holds(platform, source):
            return None
        try:
            room = self._ensure_room()
            if room is not None:
                self._deliver(room, source=source, message_id=message_id, text=text)
            else:
                logger.warning("nunchi-room: no room is configured; the message is not observed")
        except Exception:
            # Fail closed: Hermes answering a person directly would bypass the room.
            logger.exception("nunchi-room: could not hand a message to the room")
        return {"action": "handled"}

    def _deliver(self, room: Any, *, source: Mapping[str, Any], message_id: str | None, text: str) -> None:
        user_id = str(source.get("user_id") or "unknown")
        author = self.route.actor_id(user_id)
        if message_id:
            event_id = self.route.event_id(str(message_id))
        else:
            # Hermes gave no id: the message is still observed, but nothing can target it.
            event_id = self.route.event_id(f"unidentified-{time.time_ns()}")
        with self._lock:
            facts = self._noted.pop(str(message_id), None) if message_id else None
        facts = facts or _MessageFacts()
        mentioned = list(facts.mentioned or ())
        own = self.participant.profile.actor_id
        if facts.addressed and own not in mentioned:
            # Meant for this bot without naming it, such as a reply to it.
            mentioned.append(own)
        event: dict[str, Any] = {
            "id": event_id,
            "type": "message",
            "author_id": author,
            "text": text or "",
            # Unknown mentions read as none: the host-isolated plugin cannot see them.
            "mentioned_actor_ids": mentioned,
            "mentions_room": bool(facts.mentions_room),
        }
        if facts.timestamp is not None:
            event["timestamp"] = facts.timestamp
        if facts.reply_to_message_id is not None:
            event["reply_to_event_id"] = self.route.event_id(facts.reply_to_message_id)
        kind = {True: "bot", False: "human", None: "unknown"}[facts.author_is_bot]
        room.deliver(
            delivery_id=f"hermes:{event_id}",
            event=event,
            actors={author: {"kind": kind, "display_name": str(source.get("user_name") or user_id)}},
        )

    # -- the driver (the library calls these) ------------------------------------------

    def start(self, turn: Turn) -> None:
        with self._lock:
            self._wake = _Wake(turn)
        if not self._inject(turn.wake_id, turn.text):
            with self._lock:
                self._wake = None
            raise HermesPluginError(
                "Hermes did not accept the turn: check allow_gateway_injection and that the "
                "gateway is running"
            )

    def interrupt(self, turn: Turn) -> None:
        """Hermes has no plugin interrupt.

        The library closes a cancelled turn, so its run's answer is silenced at
        the output hook, and a run that starts later is stale and silenced too.
        Tools the run already ran stay run.
        """

    def _inject(self, wake_id: str, text: str) -> bool:
        if self.ctx is None:
            return False
        try:
            return bool(self.ctx.inject_message(WAKE_MARKER.format(wake_id) + "\n" + text, origin=self.route.origin()))
        except Exception:
            logger.exception("nunchi-room: inject_message failed")
            return False

    # -- hooks inside the agent's run ---------------------------------------------------

    def on_pre_llm_call(
        self,
        session_id: str = "",
        task_id: str = "",
        turn_id: str = "",
        user_message: Any = "",
        **_: Any,
    ) -> None:
        """Bind a run that starts with the open turn's wake marker."""

        match = _WAKE.search(_text(user_message)[:512])
        if match is None or not turn_id:
            return None
        run = _Run(turn_id=turn_id, session_id=session_id, task_id=task_id)
        with self._lock:
            self._runs[turn_id] = run
            wake = self._wake
            if wake is None or not hmac.compare_digest(match.group(1).encode(), wake.turn.wake_id.encode()):
                return None  # a stale turn's run: it is silenced at the end
            run.bound = self.participant.bind_turn(
                turn_id=turn_id, wake_id=None if wake.continuing else wake.turn.wake_id
            )
            if run.bound:
                for key in (task_id, session_id):
                    if key:
                        self._run_keys[key] = turn_id
        return None

    def _tool_handler(self, name: str):
        def handler(args: Any, **kwargs: Any) -> str:
            with self._lock:
                turn_id = self._run_keys.get(str(kwargs.get("task_id") or "")) or self._run_keys.get(
                    str(kwargs.get("session_id") or "")
                )
            ok, text = self.participant.call_tool(
                turn_id=turn_id, tool=name, arguments=args if isinstance(args, Mapping) else {}
            )
            return json.dumps({"result": text} if ok else {"error": text}, ensure_ascii=False)

        handler.__name__ = f"nunchi_{name}"
        return handler

    def on_tool_result(self, result: Any = None, turn_id: str = "", **_: Any) -> str | None:
        """Steering: what others posted meanwhile, after every tool in a bound run."""

        with self._lock:
            run = self._runs.get(turn_id)
        if run is None or not run.bound or not isinstance(result, str):
            return None
        update = self.participant.news(turn_id=turn_id)
        return f"{result}\n\n{update}" if update else None

    def on_api_request(self, turn_id: str = "") -> None:
        """Hermes starts a model request in a Nunchi run: it has not given up on the run.

        The signature is narrow on purpose: Hermes passes a hook only the
        arguments it declares, and this one need not carry the conversation
        into the plugin host.
        """

        with self._lock:
            run = self._runs.get(turn_id)
            if run is not None:
                run.requests += 1
                run.failure = None
        return None

    def on_api_response(
        self, turn_id: str = "", assistant_message: Any = None, response: Any = None, **_: Any
    ) -> None:
        """Report what the model wrote, and keep its raw answer.

        Hermes strips `<thinking>` before the output hook; the raw answer keeps
        it. The library compares the final answer with what the model wrote
        (``model_text``): its text, and its reasoning when the provider sent
        any. Under `plugins.isolation: host` the message object does not cross
        into the plugin host, so its text comes from Hermes's JSON summary of
        the response instead.
        """

        with self._lock:
            run = self._runs.get(turn_id)
        if run is None:
            return None
        content = _field(assistant_message, "content")
        if not isinstance(content, str) and isinstance(response, Mapping):
            content = _field(response.get("assistant_message"), "content")
        run.raw_answer = content if isinstance(content, str) else None
        if run.bound:
            self.participant.model_wrote(turn_id=turn_id, text=run.raw_answer or "")
            for name in ("reasoning", "reasoning_content"):
                reasoning = _field(assistant_message, name)
                if isinstance(reasoning, str):
                    self.participant.model_wrote(turn_id=turn_id, text=reasoning)
        return None

    def on_api_error(
        self,
        turn_id: str = "",
        retryable: Any = None,
        retry_count: Any = None,
        max_retries: Any = None,
        status_code: Any = None,
        reason: Any = None,
    ) -> None:
        """A model request in a Nunchi run failed.

        When Hermes will not retry it (the provider refused, or the retries
        are spent), Hermes ends the run with no output or end hook, and posts
        its own failed-turn notice. Before that it may still recover, through a
        fallback provider or a rotated credential, so the turn ends as a
        failure only if no new model request starts within
        ``failure_grace_seconds``. Without this the turn would stay open until
        the library's deadline, holding up the room's next moment.
        """

        spent = isinstance(retry_count, int) and isinstance(max_retries, int) and retry_count + 1 >= max_retries
        if retryable is not False and not spent:
            return None  # Hermes retries it
        with self._lock:
            run = self._runs.get(turn_id)
            if run is None or not run.bound:
                return None
            what = ", ".join(str(part) for part in (status_code, reason) if part not in (None, ""))
            run.failure = f"the model provider failed ({what or 'no detail'}) and Hermes did not recover"
            seen = run.requests
        timer = threading.Timer(self.failure_grace_seconds, self._end_failed_run, args=(turn_id, seen))
        timer.daemon = True
        timer.start()
        return None

    def _end_failed_run(self, turn_id: str, seen: int) -> None:
        with self._lock:
            run = self._runs.get(turn_id)
            if run is None or not run.bound or run.failure is None or run.requests != seen:
                return  # the run ended, or Hermes started another request
            detail = run.failure
            self._close_run(run)
            if self._wake is not None and self._wake.turn.bound(turn_id):
                self._wake = None
        self.participant.end_turn(turn_id=turn_id, ok=False, detail=detail)

    def _close_run(self, run: _Run) -> None:
        """Forget a run the plugin ended itself; whatever Hermes still hands over is silenced."""

        self._runs.pop(run.turn_id, None)
        for key in (run.task_id, run.session_id):
            if self._run_keys.get(key) == run.turn_id:
                del self._run_keys[key]
        self._closed_runs[run.turn_id] = None
        while len(self._closed_runs) > _CLOSED_RUNS:
            self._closed_runs.popitem(last=False)

    def on_final_answer(
        self, response_text: str = "", turn_id: str = "", session_id: str = "", **_: Any
    ) -> str | None:
        """Hand the final answer to the library; Hermes delivers what this returns.

        It fails closed: if anything here raises, the turn fails and Hermes
        gets the silence marker. Hermes would post the raw draft for a hook
        that raised.
        """

        with self._lock:
            run = self._runs.get(turn_id)
            if run is None and session_id:
                run = next(
                    (item for item in self._runs.values() if item.session_id == session_id), None
                )
            closed = run is None and turn_id in self._closed_runs
        if closed:
            return SILENCE_MARKER  # the plugin already ended this run's turn
        if run is None:
            return None  # not a Nunchi run
        try:
            return self._final_answer(run, response_text)
        except Exception:
            logger.exception("nunchi-room: the output hook failed; the turn fails and nothing is posted")
            try:
                self.participant.end_turn(
                    turn_id=run.turn_id, ok=False, detail="the plugin's output hook failed"
                )
            except Exception:
                logger.exception("nunchi-room: could not end the turn")
            return SILENCE_MARKER

    def _final_answer(self, run: _Run, response_text: str) -> str:
        if not run.bound:
            return SILENCE_MARKER  # nothing posts without the library's commit
        answer = response_text or ""
        raw = run.raw_answer
        if raw and _THINKING.search(raw) and _THINKING.sub("", raw).strip() == answer.strip():
            # The same answer with the agent's thinking, which the library keeps as its reason.
            answer = raw
        decision = self.participant.finish(turn_id=run.turn_id, answer=answer)
        if decision.kind == "deliver":
            return decision.text
        if decision.kind == "continue":
            with self._lock:
                if self._wake is not None and self._wake.turn.bound(run.turn_id):
                    self._wake.fresh_run = decision.text
        return SILENCE_MARKER

    def on_run_end(
        self,
        turn_id: str = "",
        completed: bool = False,
        failed: bool = False,
        interrupted: bool = False,
        turn_exit_reason: Any = "",
        **_: Any,
    ) -> None:
        """Report the run's end, or start the fresh run a `continue` asked for."""

        with self._lock:
            run = self._runs.pop(turn_id, None)
            if run is None:
                self._closed_runs.pop(turn_id, None)
                return None
            for key in (run.task_id, run.session_id):
                if self._run_keys.get(key) == turn_id:
                    del self._run_keys[key]
            if not run.bound:
                return None
            wake = self._wake
            if wake is not None and not wake.turn.bound(turn_id):
                wake = None  # this run's turn already ended; the wake is a newer turn's
            fresh = wake.fresh_run if wake is not None else None
            if wake is not None:
                wake.fresh_run = None
        ok = bool(completed) and not failed and not interrupted
        detail = str(turn_exit_reason or "")
        if fresh is not None and ok and wake is not None and not wake.turn.cancelled.is_set():
            with self._lock:
                wake.continuing = True
            if self._inject(wake.turn.wake_id, fresh):
                return None
            ok, detail = False, "Hermes did not accept the fresh run"
        if wake is not None:
            with self._lock:
                if self._wake is wake:
                    self._wake = None
        self.participant.end_turn(turn_id=turn_id, ok=ok, detail=detail)
        return None


def _field(message: Any, name: str) -> Any:
    """One field of a model message: a mapping, an object, or a placeholder from the plugin host."""

    if isinstance(message, Mapping):
        return message.get(name)
    try:
        return getattr(message, name, None)
    except Exception:
        return None


def _text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        return "\n".join(
            part.get("text", "") for part in message if isinstance(part, Mapping) and isinstance(part.get("text"), str)
        )
    return ""


# -- loading from Hermes ---------------------------------------------------------------------


def withheld_values(names: Iterable[str]) -> list[str]:
    """The values of environment variables the agent must never post."""

    return [value for name in names if (value := os.environ.get(name))]


def _host_model_selection(model: Mapping[str, Any] | None) -> AttentionModelSelection | None:
    """The provider and model to ask Hermes for, when attention uses Hermes's own model."""

    if not isinstance(model, Mapping) or model.get("kind") != HOST_MODEL_KIND:
        return None
    return AttentionModelSelection.from_trusted_config(
        {key: value for key, value in model.items() if key != "kind"}
    )


def _hermes_refused(exc: BaseException) -> bool:
    """Hermes refuses a provider or model the operator has not allowed with a bare
    PermissionError; an OS permission failure carries an errno."""

    return isinstance(exc, PermissionError) and exc.errno is None


def build_plugin(config: Mapping[str, Any]) -> HermesRoomPlugin:
    """The plugin for one Nunchi config (`docs/harness-guide.md`, step 1)."""

    from nunchi.adapters.model_apis import ATTENTION_KINDS
    from nunchi.room import Room, RoomSettings, room_guard

    settings = RoomSettings.from_config(config, label="Hermes plugin", sections=(SECTION,))
    host_model = _host_model_selection(settings.attention_model)
    section = settings.sections[SECTION]
    route = HermesRoute.from_section(section)
    # One guard for the agent's turns and the room: what the config names in
    # its ``*_env`` keys (the hermes section's ``withheld_env``, an attention
    # route's key), Hermes's platform tokens when the section names none, and
    # their shapes.
    defaults = () if "withheld_env" in section else DEFAULT_WITHHELD_ENV
    guard = room_guard(settings, values=withheld_values(defaults), patterns=TOKEN_PATTERNS)
    roles = ["react", "context"]
    if settings.authorization is not None:
        roles += ["propose", "withdraw"]

    def room_factory(plugin: HermesRoomPlugin) -> Room:
        attention_model = None
        if host_model is not None and settings.attention.preattention_enabled:
            attention_model = HostStructuredAttentionModel(
                plugin.ctx.llm,
                host_model,
                is_denial=_hermes_refused,
                denied_detail=HOST_MODEL_REFUSED,
            )
        return Room(
            settings,
            participant=plugin.participant,
            transport=plugin.transport(),
            # Hermes shows messages as they arrive; it has no history API for
            # plugins, and reactions and membership never reach a plugin hook.
            event_visibility={"message": "live-only", "reaction": "unavailable", "membership": "unavailable"},
            state_prefix="hermes-plugin-",
            attention_model=attention_model,
            attention_kinds=ATTENTION_KINDS,
            guard=guard,
        )

    return HermesRoomPlugin(
        profile=settings.profile,
        guard=guard,
        route=route,
        roles=roles,
        start_timeout_seconds=float(section.get("start_timeout_seconds", DEFAULT_START_TIMEOUT_SECONDS)),
        room_factory=room_factory,
    )


def register(ctx: Any) -> None:
    """Hermes's entry point: `plugins.entries.nunchi-room.settings.config_path`."""

    path = ctx.get_config("config_path") or os.environ.get("NUNCHI_HERMES_CONFIG")
    if not path:
        logger.warning(
            "nunchi-room: set plugins.entries.%s.settings.config_path to a Nunchi config; "
            "the plugin stays idle",
            PLUGIN_NAME,
        )
        return
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    build_plugin(config).register(ctx)
