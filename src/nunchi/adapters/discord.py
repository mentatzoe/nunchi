"""Installed standalone Discord V2 adapter using reactive gateway events."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
from collections.abc import Mapping, Sequence

from .. import __version__
from ..errors import NunchiError, ValidationError
from ..ack import ReactionCapability
from ..participant import TransportResult
from .runtime import CAPABILITIES, ReferenceAdapterRuntime, load_pinned_config


class DurableGatewaySequence:
    """Fsync a monotonic occurrence ID for callbacks lacking native IDs."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._value = 0
        self._lock = threading.Lock()
        if self.path.exists():
            try:
                state = json.loads(self.path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise ValidationError(
                    "Discord synthetic sequence state is untrustworthy"
                ) from exc
            if (
                not isinstance(state, dict)
                or set(state) != {"schema_version", "value"}
                or state["schema_version"] != 2
                or isinstance(state["value"], bool)
                or not isinstance(state["value"], int)
                or state["value"] < 0
            ):
                raise ValidationError(
                    "Discord synthetic sequence state has an invalid closed shape"
                )
            self._value = state["value"]

    def next(self) -> int:
        with self._lock:
            value = self._value + 1
            payload = json.dumps(
                {"schema_version": 2, "value": value},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            temporary = self.path.with_suffix(".tmp")
            fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
            try:
                if os.write(fd, payload) != len(payload):
                    raise OSError("short Discord synthetic-sequence write")
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(temporary, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            self._value = value
            return value


class DiscordPyTransport:
    def __init__(self, bot, loop: asyncio.AbstractEventLoop, room_id: str) -> None:
        self.bot = bot
        self.loop = loop
        self.room_id = room_id

    def ordinary_action_capabilities(self) -> tuple[str, ...]:
        return ("message", "reply", "reaction")

    def reaction_capability(self) -> ReactionCapability:
        user = getattr(self.bot, "user", None)
        actor = getattr(user, "id", None)
        authenticated = actor is not None
        try:
            channel = self.bot.get_channel(int(self.room_id))
        except (TypeError, ValueError):
            channel = None
        permissions_for = getattr(channel, "permissions_for", None)
        permissions = (
            permissions_for(user)
            if callable(permissions_for) and user is not None
            else None
        )
        allowed = bool(
            permissions is not None
            and getattr(permissions, "view_channel", False)
            and getattr(permissions, "read_message_history", False)
            and getattr(permissions, "add_reactions", False)
        )
        revision = hashlib.sha256(
            (
                f"discord.py-v1\0{actor if actor is not None else 'unknown'}\0"
                f"{self.room_id}\0{int(allowed)}"
            ).encode()
        ).hexdigest()
        return ReactionCapability(
            supported=allowed,
            authenticated=authenticated,
            operations=("add", "remove") if allowed else (),
            reactions=("*",) if allowed else (),
            permissions_revision=revision,
            detail=(
                ""
                if allowed
                else "Discord room reaction permission is unavailable or unattested"
            ),
        )

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
        except BaseException:
            return TransportResult("unknown", "Discord acknowledgement was lost")
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


def _declare_fresh_gateway_gap(runtime: ReferenceAdapterRuntime) -> None:
    runtime.pipeline.observation.mark_continuity_gap(
        delivery_id=f"discord:standalone-startup-gap:{time.time_ns()}",
        detail=(
            "fresh standalone Discord gateway session cannot attest "
            "events missed before READY"
        ),
    )


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
                runtime_holder["synthetic_sequence"] = DurableGatewaySequence(
                    Path(config["state_directory"])
                    / "discord-synthetic-sequence.json"
                )
                runtime_holder["runtime"] = ReferenceAdapterRuntime(
                    surface="discord",
                    config=config,
                    transport=DiscordPyTransport(
                        bot,
                        asyncio.get_running_loop(),
                        config["binding"]["room_id"],
                    ),
                )
                _declare_fresh_gateway_gap(runtime_holder["runtime"])

        @bot.event
        async def on_disconnect():
            runtime = runtime_holder.get("runtime")
            if runtime is None:
                return
            runtime.lane.cancel()
            runtime.pipeline.observation.mark_continuity_gap(
                delivery_id=f"discord:standalone-stream-gap:{time.time_ns()}",
                detail="standalone Discord gateway continuity is uncertain",
            )

        async def process(payload):
            runtime = runtime_holder.get("runtime")
            if runtime is None:
                return
            try:
                await asyncio.to_thread(runtime.submit, payload)
            except BaseException:
                print("discord delivery error", file=sys.stderr)

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
                    "s": runtime_holder["synthetic_sequence"].next(),
                    "delivery_epoch": "standalone-durable",
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
                    "s": runtime_holder["synthetic_sequence"].next(),
                    "delivery_epoch": "standalone-durable",
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
        runtime = runtime_holder.get("runtime")
        if runtime is not None:
            runtime.lane.cancel()
            runtime.drain(35)
        return 0
    except (NunchiError, ValueError) as exc:
        print(f"discord adapter error: {exc}", file=sys.stderr)
        return 3 if isinstance(exc, ValidationError) else 1


if __name__ == "__main__":
    raise SystemExit(main())
