"""Every object the stand-in sends, built from the world in one place, so the shape pin (`shapes.py`) covers them all.

REST message objects carry neither ``guild_id`` nor ``member``, as Discord
documents them; the gateway's MESSAGE_CREATE adds both, and a member to each
mention. Ids are strings, as Discord sends them.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .world import INTENTS, PERMISSIONS, Channel, Member, Role, World, id_ms, iso

# What each payload is, by its gateway event or its REST kind, as discord.py 2.7.1's ``discord.types`` names it.
SHAPES = {
    "READY": "gateway.ReadyEvent",
    "GUILD_CREATE": "gateway.GuildCreateEvent",
    "GUILD_MEMBERS_CHUNK": "gateway.GuildMembersChunkEvent",
    "MESSAGE_CREATE": "gateway.MessageCreateEvent",
    "MESSAGE_REACTION_ADD": "gateway.MessageReactionAddEvent",
    "MESSAGE_REACTION_REMOVE": "gateway.MessageReactionRemoveEvent",
    "THREAD_CREATE": "gateway.ThreadCreateEvent",
    "user": "user.User",
    "application": "appinfo.AppInfo",
    "message": "message.Message",
    "text": "channel.TextChannel",
    "thread": "channel.ThreadChannel",
    "member": "member.MemberWithUser",
    "role": "role.Role",
}


def user(m: Member) -> dict[str, Any]:
    data = {"id": m.id, "username": m.name, "discriminator": "0", "global_name": None if m.bot else m.name.title(),
            "avatar": None, "public_flags": 0}
    return {**data, "bot": True} if m.bot else data  # a person's user has no "bot" field at all


def member(m: Member, *, with_user: bool = True) -> dict[str, Any]:
    data = {"roles": list(m.roles), "joined_at": m.joined_at, "deaf": False, "mute": False, "flags": 0,
            "nick": None, "avatar": None, "premium_since": None, "pending": False}
    return {**data, "user": user(m)} if with_user else data


def role(r: Role) -> dict[str, Any]:
    return {"id": r.id, "name": r.name, "color": 0, "colors": {"primary_color": 0, "secondary_color": None, "tertiary_color": None},
            "hoist": False, "position": r.position, "permissions": str(r.permissions), "managed": False,
            "mentionable": False, "flags": 0, "icon": None, "unicode_emoji": None}


def channel(world: World, c: Channel) -> dict[str, Any]:
    data = {"id": c.id, "guild_id": world.guild_id, "name": c.name, "nsfw": False, "flags": 0, "rate_limit_per_user": 0,
            "last_message_id": c.last_id if c.messages else None}
    if c.parent_id is None:
        overwrites = [{"id": o["id"], "type": o["type"], "allow": str(o["allow"]), "deny": str(o["deny"])} for o in c.overwrites]
        return {**data, "type": 0, "position": c.position, "parent_id": None, "topic": None, "permission_overwrites": overwrites}
    created = iso(id_ms(c.id))
    return {**data, "type": 11, "parent_id": c.parent_id, "owner_id": c.owner_id, "message_count": c.messages,
            "total_message_sent": c.messages, "member_count": 1,
            "thread_metadata": {"archived": False, "auto_archive_duration": 1440, "archive_timestamp": created,
                                "locked": False, "create_timestamp": created}}


def message(world: World, record: dict[str, Any], *, gateway: bool = False, nested: bool = False) -> dict[str, Any]:
    author = world.members[record["author_id"]]

    def mention(user_id: str) -> dict[str, Any]:
        m = world.members[user_id]
        return {**user(m), "member": member(m, with_user=False)} if gateway else user(m)

    data = {
        "id": record["id"], "channel_id": record["channel_id"], "author": user(author), "content": record["content"],
        "timestamp": iso(id_ms(record["id"])), "edited_timestamp": None, "tts": False,
        "mention_everyone": record["mention_everyone"], "mentions": [mention(u) for u in record["mentions"]],
        "mention_roles": list(record["mention_roles"]), "attachments": [], "embeds": [], "components": [],
        "pinned": False, "type": 19 if record["reply_to"] else 0, "flags": 0,
    }
    if record["nonce"] is not None and not nested:
        data["nonce"] = record["nonce"]
    if record["reply_to"]:
        target = world.messages[record["reply_to"]]
        data["message_reference"] = {"type": 0, "message_id": target["id"], "channel_id": target["channel_id"], "guild_id": world.guild_id}
        if not nested:
            data["referenced_message"] = message(world, target, nested=True)
    if gateway:
        data["guild_id"] = world.guild_id
        data["member"] = member(author, with_user=False)
    return data


def reaction(world: World, user_id: str, record: dict[str, Any], emoji: str, *, add: bool) -> dict[str, Any]:
    data = {"user_id": user_id, "channel_id": record["channel_id"], "message_id": record["id"], "guild_id": world.guild_id,
            "emoji": {"id": None, "name": emoji}, "burst": False, "type": 0}
    if add:
        data.update(member=member(world.members[user_id]), message_author_id=record["author_id"], burst_colors=[])
    return data


def ready(world: World, bot: Member, session_id: str, resume_gateway_url: str) -> dict[str, Any]:
    return {"v": 10, "user": user(bot), "guilds": [{"id": world.guild_id, "unavailable": True}], "session_id": session_id,
            "session_type": "normal", "resume_gateway_url": resume_gateway_url, "application": {"id": bot.id, "flags": 0}}


def guild_create(world: World, bot: Member, intents: int) -> dict[str, Any]:
    everyone = intents & INTENTS["GUILD_PRESENCES"]  # without it Discord sends only the bot's own member
    channels = [channel(world, c) for c in world.channels.values()]
    return {
        "id": world.guild_id, "name": world.name, "icon": None, "splash": None, "discovery_splash": None, "banner": None,
        "description": None, "emojis": [], "stickers": [], "features": [], "incidents_data": None,
        "owner_id": world.owner_id, "afk_channel_id": None, "afk_timeout": 300, "verification_level": 0,
        "default_message_notifications": 0, "explicit_content_filter": 0, "mfa_level": 0, "nsfw_level": 0,
        "application_id": None, "system_channel_id": None, "system_channel_flags": 0, "rules_channel_id": None,
        "public_updates_channel_id": None, "vanity_url_code": None, "premium_tier": 0, "premium_subscription_count": 0,
        "preferred_locale": "en-US", "stage_instances": [], "guild_scheduled_events": [], "soundboard_sounds": [],
        "unavailable": False, "joined_at": bot.joined_at, "large": False, "member_count": len(world.members),
        "roles": [role(r) for r in world.roles.values()],
        "members": [member(m) for m in world.members.values() if everyone or m is bot],
        "channels": [c for c in channels if c["type"] == 0], "threads": [
            c for c in channels if c["type"] == 11 and world.permissions(bot.id, c["id"]) & PERMISSIONS["VIEW_CHANNEL"]
        ],
        "voice_states": [], "presences": [],
    }


def members_chunk(world: World, members: list[Member], nonce: Any) -> dict[str, Any]:
    data = {"guild_id": world.guild_id, "members": [member(m) for m in members], "chunk_index": 0, "chunk_count": 1, "not_found": []}
    return {**data, "nonce": nonce} if nonce is not None else data


def application(world: World, bot: Member) -> dict[str, Any]:
    return {"id": bot.id, "name": bot.name, "icon": None, "description": "", "summary": "", "flags": 0,
            "verify_key": hashlib.sha256(bot.id.encode()).hexdigest(), "bot_public": False, "bot_require_code_grant": False,
            "owner": user(world.members[world.owner_id]), "interactions_endpoint_url": None}
