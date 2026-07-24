"""Installed standalone Discord V2 adapter using reactive gateway events."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Mapping, Sequence

from .. import __version__
from ..errors import NunchiError, ValidationError
from ..participant import TransportResult
from .runtime import CAPABILITIES, ReferenceAdapterRuntime, load_pinned_config


class DiscordPyTransport:
    def __init__(self, bot, loop: asyncio.AbstractEventLoop) -> None:
        self.bot = bot
        self.loop = loop

    async def _dispatch(self, action, wake):
        channel_id = int(wake["room"]["id"])
        channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
        if action["kind"] == "message":
            sent = await channel.send(action["text"])
            return TransportResult("sent", f"discord:message:{sent.id}")
        if action["kind"] == "reply":
            target_id = int(action["target_event_id"].removeprefix("discord:message:"))
            target = channel.get_partial_message(target_id)
            sent = await target.reply(action["text"], mention_author=False)
            return TransportResult("sent", f"discord:message:{sent.id}")
        if action["kind"] == "reaction":
            target_id = int(action["target_event_id"].removeprefix("discord:message:"))
            target = channel.get_partial_message(target_id)
            if action["operation"] == "add":
                await target.add_reaction(action["reaction"])
            else:
                if self.bot.user is None:
                    return TransportResult("failed", "Discord self identity is unavailable")
                await target.remove_reaction(action["reaction"], self.bot.user)
            return TransportResult("sent", f"discord:reaction:{target_id}")
        return TransportResult("unavailable", "Discord action is unsupported")

    def dispatch(self, *, action, wake) -> TransportResult:
        future = asyncio.run_coroutine_threadsafe(self._dispatch(action, wake), self.loop)
        try:
            result = future.result(timeout=30)
        except asyncio.TimeoutError:
            return TransportResult("unknown", "Discord acknowledgement deadline expired")
        except BaseException as exc:
            return TransportResult("unknown", f"Discord acknowledgement lost: {exc}")
        return result


def _parser():
    parser = argparse.ArgumentParser(prog="nunchi-discord")
    parser.add_argument("--config")
    parser.add_argument(
        "--config-sha256",
        default=os.environ.get("NUNCHI_ADAPTER_CONFIG_SHA256"),
    )
    parser.add_argument("--probe", action="store_true")
    return parser


def _static_probe():
    return {
        "product": "nunchi",
        "product_version": __version__,
        "generation": 2,
        "surface": "discord",
        "capabilities": CAPABILITIES["discord"],
        "configured": False,
        "v1_fallback": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if not args.config:
            if args.probe:
                print(json.dumps(_static_probe(), sort_keys=True, separators=(",", ":")))
                return 0
            raise ValidationError("--config is required")
        if not args.config_sha256:
            raise ValidationError("--config-sha256 is required")
        config = load_pinned_config(args.config, args.config_sha256)
        transport_raw = config.get("transport")
        if not isinstance(transport_raw, Mapping):
            raise ValidationError("Discord config must contain transport")
        if set(transport_raw) - {"bot_token_env"}:
            raise ValidationError("Discord transport config has unexpected fields")
        token_env = str(transport_raw.get("bot_token_env", "DISCORD_BOT_TOKEN"))
        token = os.environ.get(token_env)
        if not token:
            raise ValidationError(f"Discord credential is absent from {token_env}")
        try:
            import discord
        except ImportError as exc:
            raise ValidationError(
                "Discord runtime requires the installed nunchi[discord] extra"
            ) from exc

        intents = discord.Intents.none()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        intents.reactions = True
        intents.members = True
        bot = discord.Client(intents=intents)
        runtime_holder = {}

        @bot.event
        async def on_ready():
            actor_id = f"discord:actor:{bot.user.id}"
            if actor_id != config["binding"]["actor_id"]:
                await bot.close()
                raise RuntimeError("authenticated Discord bot does not match exact self binding")
            if "runtime" not in runtime_holder:
                runtime_holder["runtime"] = ReferenceAdapterRuntime(
                    surface="discord",
                    config=config,
                    transport=DiscordPyTransport(bot, asyncio.get_running_loop()),
                )

        async def process(payload):
            runtime = runtime_holder.get("runtime")
            if runtime is None:
                return
            try:
                await asyncio.to_thread(runtime.process, payload)
            except BaseException as exc:
                print(f"discord delivery error: {exc}", file=sys.stderr)

        @bot.event
        async def on_message(message):
            payload = {
                "t": "MESSAGE_CREATE",
                "s": None,
                "d": {
                    "id": str(message.id),
                    "channel_id": str(message.channel.id),
                    "guild_id": str(message.guild.id) if message.guild else None,
                    "author": {
                        "id": str(message.author.id),
                        "username": message.author.name,
                        "global_name": getattr(message.author, "global_name", None),
                        "display_name": message.author.display_name,
                        "bot": message.author.bot,
                    },
                    "content": message.content,
                    "mentions": [
                        {
                            "id": str(member.id),
                            "username": member.name,
                            "global_name": getattr(member, "global_name", None),
                            "display_name": member.display_name,
                            "bot": member.bot,
                        }
                        for member in message.mentions
                    ],
                    "mention_everyone": message.mention_everyone,
                    "timestamp": message.created_at.isoformat().replace("+00:00", "Z"),
                    "message_reference": (
                        {"message_id": str(message.reference.message_id)}
                        if message.reference and message.reference.message_id
                        else None
                    ),
                    "thread": (
                        {"id": str(message.channel.id)}
                        if isinstance(message.channel, discord.Thread)
                        else None
                    ),
                },
            }
            await process(payload)

        async def reaction_payload(raw, event_type):
            await process(
                {
                    "t": event_type,
                    "s": None,
                    "d": {
                        "channel_id": str(raw.channel_id),
                        "guild_id": str(raw.guild_id) if raw.guild_id else None,
                        "user_id": str(raw.user_id),
                        "message_id": str(raw.message_id),
                        "emoji": {
                            "id": str(raw.emoji.id) if raw.emoji.id else None,
                            "name": raw.emoji.name,
                        },
                    },
                }
            )

        @bot.event
        async def on_raw_reaction_add(payload):
            await reaction_payload(payload, "MESSAGE_REACTION_ADD")

        @bot.event
        async def on_raw_reaction_remove(payload):
            await reaction_payload(payload, "MESSAGE_REACTION_REMOVE")

        async def member_payload(member, event_type):
            await process(
                {
                    "t": event_type,
                    "s": None,
                    "d": {
                        "guild_id": str(member.guild.id),
                        "room_id": str(config["binding"]["room_id"]),
                        "user": {
                            "id": str(member.id),
                            "username": member.name,
                            "global_name": getattr(member, "global_name", None),
                            "bot": member.bot,
                        },
                    },
                }
            )

        @bot.event
        async def on_member_join(member):
            await member_payload(member, "GUILD_MEMBER_ADD")

        @bot.event
        async def on_member_remove(member):
            await member_payload(member, "GUILD_MEMBER_REMOVE")

        if args.probe:
            # Config and credential integrity have been checked; no live
            # connection is claimed by this non-mutating probe.
            result = _static_probe()
            result.update(
                {
                    "configured": True,
                    "participant_id": config["binding"]["participant_id"],
                    "actor_id": config["binding"]["actor_id"],
                    "room_id": config["binding"]["room_id"],
                }
            )
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return 0
        bot.run(token, log_handler=None)
        return 0
    except (NunchiError, ValueError) as exc:
        print(f"discord adapter error: {exc}", file=sys.stderr)
        return 3 if isinstance(exc, ValidationError) else 1


if __name__ == "__main__":
    raise SystemExit(main())
