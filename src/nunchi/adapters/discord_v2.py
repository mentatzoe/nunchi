"""One-channel Discord V2 adapter over discord.py and shared transport seams."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Sequence

from ..mcp_discord.events import (
    DiscordEventSourceV2,
    MessageEvent,
    message_text,
)
from ..mcp_discord.ratelimit import SendBackstop
from ..mcp_discord.rest import DiscordRestClient
from ..mcp_discord.v2 import DiscordActionSinkV2
from .native_host_v2 import (
    NativeRuntimeV2,
    add_participant_arguments,
    build_native_runtime,
)


logger = logging.getLogger("nunchi.adapters.discord_v2")
_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


class DiscordAdapterV2Error(RuntimeError):
    pass


def _snowflake(value: Any) -> str:
    text = str(value).strip() if value is not None else ""
    if not text.isdigit():
        raise DiscordAdapterV2Error("Discord identity is invalid")
    return text


def _object_dict(value: Any) -> dict[str, Any]:
    method = getattr(value, "to_dict", None)
    if not callable(method):
        return {}
    result = method()
    return result if isinstance(result, dict) else {}


def message_event_from_discord(message: Any) -> MessageEvent:
    """Project only exact discord.py native fields into the shared source."""
    author = getattr(message, "author", None)
    channel = getattr(message, "channel", None)
    message_id = _snowflake(getattr(message, "id", None))
    channel_id = _snowflake(getattr(channel, "id", None))
    author_id = _snowflake(getattr(author, "id", None))
    rich = {
        "content": getattr(message, "content", ""),
        "embeds": [
            _object_dict(item) for item in (getattr(message, "embeds", None) or [])
        ],
        "attachments": [
            {
                "filename": getattr(item, "filename", ""),
                "description": getattr(item, "description", None),
            }
            for item in (getattr(message, "attachments", None) or [])
        ],
        "components": [
            _object_dict(item)
            for item in (getattr(message, "components", None) or [])
        ],
        "sticker_items": [
            {"name": getattr(item, "name", "")}
            for item in (getattr(message, "stickers", None) or [])
        ],
    }
    reference = getattr(message, "reference", None)
    reply_message_id = getattr(reference, "message_id", None)
    if reply_message_id is not None:
        reply_message_id = _snowflake(reply_message_id)
    created_at = getattr(message, "created_at", None)
    timestamp = None
    if isinstance(created_at, datetime):
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        timestamp = created_at.astimezone(timezone.utc).isoformat().replace(
            "+00:00",
            "Z",
        )
    mentions = []
    for item in getattr(message, "mentions", None) or []:
        user_id = _snowflake(getattr(item, "id", None))
        if user_id not in mentions:
            mentions.append(user_id)
    guild = getattr(message, "guild", None)
    guild_id = getattr(guild, "id", None)
    return MessageEvent(
        guild_id=(_snowflake(guild_id) if guild_id is not None else None),
        channel_id=channel_id,
        message_id=message_id,
        author_id=author_id,
        author_name=(
            getattr(author, "name", "")
            if isinstance(getattr(author, "name", ""), str)
            else ""
        ),
        author_is_bot=bool(getattr(author, "bot", False)),
        content=message_text(rich),
        timestamp=timestamp,
        mentioned_user_ids=tuple(mentions),
        reply_to_message_id=reply_message_id,
        reply_to_author_id=None,
        reply_to_author_name=None,
        reply_to_author_is_bot=None,
        reply_to_content=None,
        mentions_room=bool(getattr(message, "mention_everyone", False)),
        thread_root_message_id=None,
    )


class DiscordRoomAdapterV2:
    def __init__(
        self,
        arguments: argparse.Namespace,
        *,
        self_user_id: str,
        rest: Any,
    ) -> None:
        self.arguments = arguments
        self.channel_id = _snowflake(arguments.channel_id)
        self.self_user_id = _snowflake(self_user_id)
        blocked = frozenset(_snowflake(value) for value in arguments.blocked_actor_id)
        self.source = DiscordEventSourceV2(
            allowed_channel_ids=frozenset({self.channel_id}),
            blocked_actor_ids=blocked,
        )
        self.native: NativeRuntimeV2 = build_native_runtime(
            arguments,
            participant_actor_id=f"discord:user:{self.self_user_id}",
            platform="discord",
            room_id=self.channel_id,
            continuity_scope_id=f"discord:channel:{self.channel_id}",
            continuity="session-only",
            has_restart_gap=True,
            event_visibility={
                "message": "history-and-live",
                "reaction": "unavailable",
                "membership": "unavailable",
            },
            action_sink_factory=lambda sink: DiscordActionSinkV2(
                channel_id=self.channel_id,
                rest=rest,
                backstop=SendBackstop(
                    arguments.max_sends,
                    arguments.send_window_seconds,
                ),
                receipt_sink=sink,
            ),
        )

    def observe_history(self, events: list[MessageEvent]) -> tuple[str, ...]:
        return self.native.runtime.observe_context_batch(
            [self.source.native_input(event) for event in events]
        )

    def process_message(self, event: MessageEvent) -> tuple[dict[str, Any], ...]:
        return self.native.runtime.process_delivery(self.source.native_input(event))

    def close(self) -> None:
        self.native.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nunchi-discord",
        description=(
            "Run one exact Discord channel as a Nunchi V2 participant. "
            "Participant command arguments must come last."
        ),
    )
    parser.add_argument("--channel-id", required=True)
    parser.add_argument("--token-env", default="NUNCHI_DISCORD_TOKEN")
    parser.add_argument("--blocked-actor-id", action="append", default=[])
    parser.add_argument("--history-limit", type=int, default=50)
    parser.add_argument("--max-live-events", type=int)
    parser.add_argument("--max-sends", type=int, default=3)
    parser.add_argument("--send-window-seconds", type=float, default=30)
    add_participant_arguments(parser)
    return parser


def _configuration(arguments: argparse.Namespace) -> str:
    _snowflake(arguments.channel_id)
    if _ENV_NAME_RE.fullmatch(arguments.token_env) is None:
        raise DiscordAdapterV2Error("Discord token environment name is invalid")
    token = os.environ.get(arguments.token_env)
    if not token:
        raise DiscordAdapterV2Error("Discord token is unavailable")
    if (
        isinstance(arguments.history_limit, bool)
        or not 0 <= arguments.history_limit <= 100
        or (
            arguments.max_live_events is not None
            and (
                isinstance(arguments.max_live_events, bool)
                or not 1 <= arguments.max_live_events <= 1000000
            )
        )
        or isinstance(arguments.max_sends, bool)
        or not 1 <= arguments.max_sends <= 1000
        or isinstance(arguments.send_window_seconds, bool)
        or not 1 <= arguments.send_window_seconds <= 3600
    ):
        raise DiscordAdapterV2Error("Discord runtime limits are invalid")
    for actor_id in arguments.blocked_actor_id:
        _snowflake(actor_id)
    return token


def _discord_client_class(discord, arguments, token):
    class NunchiDiscordClientV2(discord.Client):
        def __init__(self):
            intents = discord.Intents.default()
            intents.message_content = True
            super().__init__(intents=intents)
            self.adapter: DiscordRoomAdapterV2 | None = None
            self.initialized = asyncio.Event()
            self.live_events = 0
            self.startup_failed = False

        async def on_ready(self):
            if self.adapter is not None:
                return
            try:
                if self.user is None:
                    raise DiscordAdapterV2Error(
                        "Discord self identity is unavailable"
                    )
                rest = DiscordRestClient(token)
                adapter = DiscordRoomAdapterV2(
                    arguments,
                    self_user_id=str(self.user.id),
                    rest=rest,
                )
                channel = self.get_channel(int(adapter.channel_id))
                if channel is None:
                    channel = await self.fetch_channel(int(adapter.channel_id))
                barrier = datetime.now(timezone.utc)
                history = []
                if arguments.history_limit:
                    async for message in channel.history(
                        limit=arguments.history_limit,
                        oldest_first=True,
                    ):
                        created_at = getattr(message, "created_at", None)
                        if isinstance(created_at, datetime):
                            if created_at.tzinfo is None:
                                created_at = created_at.replace(tzinfo=timezone.utc)
                            if created_at > barrier:
                                continue
                        history.append(message_event_from_discord(message))
                await asyncio.to_thread(adapter.observe_history, history)
            except Exception:
                if "adapter" in locals():
                    adapter.close()
                self.startup_failed = True
                logger.error("Discord V2 initialization failed")
                await self.close()
                return
            self.adapter = adapter
            self.initialized.set()
            logger.info(
                "Discord V2 ready channel=%s history=%d",
                adapter.channel_id,
                len(history),
            )

        async def on_message(self, message):
            await self.initialized.wait()
            assert self.adapter is not None
            try:
                event = message_event_from_discord(message)
                results = await asyncio.to_thread(
                    self.adapter.process_message,
                    event,
                )
                logger.info(
                    "Discord V2 delivery message=%s opportunities=%d",
                    event.message_id,
                    len(results),
                )
            except Exception:
                logger.error("Discord V2 delivery failed")
            self.live_events += 1
            if (
                arguments.max_live_events is not None
                and self.live_events >= arguments.max_live_events
            ):
                await self.close()

    return NunchiDiscordClientV2


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    try:
        token = _configuration(arguments)
    except Exception:
        print("nunchi-discord: V2 configuration is invalid", file=sys.stderr)
        return 2
    try:
        import discord
    except ImportError:
        print(
            "nunchi-discord: install the 'discord' extra to run the gateway",
            file=sys.stderr,
        )
        return 2
    client = _discord_client_class(discord, arguments, token)()
    try:
        client.run(token, log_handler=None)
        return 1 if client.startup_failed else 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        print("nunchi-discord: V2 gateway failed", file=sys.stderr)
        return 1
    finally:
        if client.adapter is not None:
            client.adapter.close()


__all__ = [
    "DiscordAdapterV2Error",
    "DiscordRoomAdapterV2",
    "message_event_from_discord",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
