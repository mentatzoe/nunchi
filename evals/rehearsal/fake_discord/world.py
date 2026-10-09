"""The stand-in's world: one guild, its people and bots, its channels, and the social facts Discord decides.

Everything a column reads to judge the room comes from here, the same for
every client: the time of each message, who it addresses, what it replies
to, who wrote it, and who may see, post or react. Each refusal carries
Discord's own status and error code. The world never touches the network;
`rest.py`, `gateway.py` and the control API call it on the stand-in's own
thread.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
import secrets
import time
import unicodedata
from typing import Any, Callable

EPOCH_MS = 1_420_070_400_000  # Discord's epoch: a snowflake's time is milliseconds since it, above bit 22

PERMISSIONS = {
    "ADMINISTRATOR": 1 << 3,
    "ADD_REACTIONS": 1 << 6,
    "VIEW_CHANNEL": 1 << 10,
    "SEND_MESSAGES": 1 << 11,
    "SEND_TTS_MESSAGES": 1 << 12,
    "EMBED_LINKS": 1 << 14,
    "ATTACH_FILES": 1 << 15,
    "READ_MESSAGE_HISTORY": 1 << 16,
    "MENTION_EVERYONE": 1 << 17,
    "CREATE_PUBLIC_THREADS": 1 << 35,
    "SEND_MESSAGES_IN_THREADS": 1 << 38,
}
P = PERMISSIONS
ALL = (1 << 51) - 1
INTENTS = {"GUILDS": 1 << 0, "GUILD_MEMBERS": 1 << 1, "GUILD_PRESENCES": 1 << 8, "GUILD_MESSAGES": 1 << 9,
           "GUILD_MESSAGE_REACTIONS": 1 << 10, "MESSAGE_CONTENT": 1 << 15}
PRIVILEGED = INTENTS["GUILD_MEMBERS"] | INTENTS["GUILD_PRESENCES"] | INTENTS["MESSAGE_CONTENT"]

# The default roles: people get "room", every bot gets "agents"; @everyone grants nothing.
ROOM = ["VIEW_CHANNEL", "SEND_MESSAGES", "SEND_MESSAGES_IN_THREADS", "READ_MESSAGE_HISTORY", "ADD_REACTIONS", "CREATE_PUBLIC_THREADS"]
AGENTS = ["VIEW_CHANNEL", "SEND_MESSAGES", "SEND_MESSAGES_IN_THREADS", "READ_MESSAGE_HISTORY", "ADD_REACTIONS"]

USER_MENTION = re.compile(r"<@!?(\d+)>")
ROLE_MENTION = re.compile(r"<@&(\d+)>")
EVERYONE_MENTION = re.compile(r"@(?:everyone|here)\b")
MAX_LENGTH = 2000
MAX_REACTIONS = 20


class DiscordError(Exception):
    """A refusal as Discord answers it: HTTP status, JSON error code and message."""

    def __init__(self, status: int, code: int, message: str, errors: dict | None = None) -> None:
        super().__init__(f"{status} {code} {message}")
        self.status = status
        self.body: dict[str, Any] = {"message": message, "code": code, **({"errors": errors} if errors else {})}


def _form_error(field_name: str, code: str, message: str) -> DiscordError:
    return DiscordError(400, 50035, "Invalid Form Body", {field_name: {"_errors": [{"code": code, "message": message}]}})


MISSING_ACCESS = (403, 50001, "Missing Access")
MISSING_PERMISSIONS = (403, 50013, "Missing Permissions")


def bits(names: list[str]) -> int:
    value = 0
    for name in names:
        value |= PERMISSIONS[name]
    return value


def names(value: int) -> list[str]:
    return [name for name, bit in PERMISSIONS.items() if value & bit]


def iso(ms: int) -> str:
    """Discord's timestamp format: UTC, microseconds, ``+00:00``."""
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="microseconds")


def id_ms(snowflake: str) -> int:
    return (int(snowflake) >> 22) + EPOCH_MS


# Emoji whose base character is not a Unicode "So" symbol.
OTHER_EMOJI = set("\u203c\u2049\u2139\u2194\u2934\u2935\u3030\u303d\u25fb\u25fc\u25fd\u25fe")


def emoji_ok(emoji: str) -> bool:
    """An approximate check that a reaction is exactly one Unicode emoji, never a word or two emoji (custom emoji: the world has none).

    It counts bases: a symbol (or one of OTHER_EMOJI) not joined to the one before by a zero-width
    joiner, a pair of regional indicators (a flag), or a keycap's digit, # or
    *. Skin tones, variation selectors, joiners and the keycap mark are not.
    """
    if not emoji or ":" in emoji:
        return False
    keycap = "\u20e3" in emoji
    bases, previous, half_flag = 0, "", False
    for ch in emoji:
        if "\U0001f1e6" <= ch <= "\U0001f1ff":
            bases, half_flag = bases + (not half_flag), not half_flag
        elif unicodedata.category(ch) == "So" or ch in OTHER_EMOJI or (keycap and ch in "0123456789#*"):
            bases += previous != "\u200d"
        elif unicodedata.category(ch) not in ("Sk", "Me", "Mn", "Cf"):
            return False
        previous = ch
    return bases == 1


@dataclass
class Member:
    id: str
    name: str
    bot: bool
    harness: bool = False  # a harness's own bot: only that harness's process posts as it
    roles: list[str] = field(default_factory=list)
    token: str | None = None
    privileged: int = 0  # the privileged intents enabled for this bot
    joined_at: str = ""


@dataclass
class Role:
    id: str
    name: str
    permissions: int
    position: int


@dataclass
class Channel:
    id: str
    name: str
    position: int
    overwrites: list[dict[str, Any]] = field(default_factory=list)
    parent_id: str | None = None  # set for a thread
    owner_id: str | None = None
    last_id: str = "0"
    lag: float | None = None  # seconds the room's clock runs behind the wall; None until a message sets it; a thread's is unused
    messages: int = 0


def _named(table: dict[str, Any], name: str, what: str) -> Any:
    found = next((item for item in table.values() if item.name == name), None)
    if found is None:
        raise KeyError(f"the world has no {what} named {name!r}")
    return found


class World:
    """One guild, from ``spec`` (every key optional):

    - ``people``: names, or ``{name: {"roles": [...]}}``; each has the
      "room" role, and the first owns the guild;
    - ``bots``: ``{name: {"harness": bool, "roles": [...], "privileged": [...]}}``;
      each has the "agents" role. A bot is a harness's, run by that
      harness's process with its per-run token, unless ``"harness": false``
      makes it a scripted bot only the director posts as. ``privileged``
      lists the privileged intents enabled for it (default GUILD_MEMBERS and
      MESSAGE_CONTENT);
    - ``roles``: ``{name: [permission, ...]}`` beside @everyone (nothing),
      "room" and "agents"; no role is mentionable;
    - ``channels``: ``{name: {target: {"allow": [...], "deny": [...]}}}``,
      each target a role or a member (default: one channel, "room");
    - ``reply_ping`` and ``people_mention_everyone`` (both true), ``guild``.

    ``log(kind, **fields)`` receives what the world itself has to report: a
    message time raised to keep a channel's ids increasing.
    """

    def __init__(self, spec: dict[str, Any] | None = None, *, clock: Callable[[], float] = time.time) -> None:
        spec = spec or {}
        self.clock = clock
        self.log: Callable[..., Any] = lambda kind, **fields: None
        self.reply_ping = bool(spec.get("reply_ping", True))
        self.name = spec.get("guild", "nunchi-rehearsal")
        self._ids: set[int] = set()
        self._increment = 0
        created = int((clock() - 30 * 86400) * 1000)  # the guild and everyone in it predate any message
        self.guild_id = self._mint(created)
        joined = iso(created)
        room = ROOM + (["MENTION_EVERYONE"] if spec.get("people_mention_everyone", True) else [])
        role_specs = {"@everyone": [], "room": room, "agents": AGENTS, **spec.get("roles", {})}
        self.roles: dict[str, Role] = {}
        for position, (name, granted) in enumerate(role_specs.items()):
            role_id = self.guild_id if name == "@everyone" else self._mint(created)
            self.roles[role_id] = Role(role_id, name, bits(granted), position)
        self.members: dict[str, Member] = {}
        people = spec.get("people", ["zoe"])
        for name in people:
            extra = people[name].get("roles", []) if isinstance(people, dict) else []
            self._add(Member(self._mint(created), name, False, roles=self._role_ids(["room", *extra]), joined_at=joined))
        for name, options in spec.get("bots", {}).items():
            bot = Member(self._mint(created), name, True, harness=bool(options.get("harness", True)),
                         roles=self._role_ids(["agents", *options.get("roles", [])]), joined_at=joined,
                         privileged=sum(INTENTS[i] for i in options.get("privileged", ["GUILD_MEMBERS", "MESSAGE_CONTENT"])))
            bot.token = self._token(bot.id) if bot.harness else None  # no process runs as a scripted bot
            self._add(bot)
        self.owner_id = next(m.id for m in self.members.values() if not m.bot)
        self.channels: dict[str, Channel] = {}
        for position, (name, overwrites) in enumerate(spec.get("channels", {"room": {}}).items()):
            channel_id = self._mint(created)
            self.channels[channel_id] = Channel(channel_id, name, position, self._overwrites(overwrites), last_id=channel_id)
        self.messages: dict[str, dict[str, Any]] = {}
        self._nonces: dict[tuple[str, str], str] = {}

    # -- names, ids and tokens --------------------------------------------------------------------

    def _add(self, member: Member) -> None:
        if any(m.name == member.name for m in self.members.values()):
            raise ValueError(f"two members are named {member.name!r}")
        self.members[member.id] = member

    def _role_ids(self, role_names: list[str]) -> list[str]:
        return [self.role(name).id for name in role_names]

    def _overwrites(self, spec: dict[str, dict[str, list[str]]]) -> list[dict[str, Any]]:
        out = []
        for target, rule in spec.items():
            role = next((r for r in self.roles.values() if r.name == target), None)
            target_id, kind = (role.id, 0) if role else (self.member(target).id, 1)
            out.append({"id": target_id, "type": kind, "allow": bits(rule.get("allow", [])), "deny": bits(rule.get("deny", []))})
        return out

    def member(self, name: str) -> Member:
        return _named(self.members, name, "member")

    def channel(self, name: str) -> Channel:
        return _named(self.channels, name, "channel")

    def role(self, name: str) -> Role:
        return _named(self.roles, name, "role")

    def bot_by_token(self, token: Any) -> Member | None:
        return next((m for m in self.members.values() if m.token is not None and m.token == token), None)

    @staticmethod
    def _token(user_id: str) -> str:
        """A fake per-run token in Discord's three-part shape, so the token guards see one."""
        head = base64.urlsafe_b64encode(user_id.encode()).decode().rstrip("=")
        return f"{head}.{secrets.token_urlsafe(8)[:6]}.{secrets.token_urlsafe(32)[:38]}"

    def _mint(self, ms: int, floor: str = "0") -> str:
        """A snowflake for ``ms``, above ``floor``, never issued before."""
        self._increment += 1
        value = max(((ms - EPOCH_MS) << 22) | (self._increment & 0xFFF), int(floor) + 1)
        while value in self._ids:
            value += 1
        self._ids.add(value)
        return str(value)

    # -- the room's clock -------------------------------------------------------------------------

    def clock_of(self, channel: Channel) -> Channel:
        """The channel whose clock ``channel`` keeps: a thread keeps its parent's, since Discord's ids are time-ordered."""
        return self.channels[channel.parent_id] if channel.parent_id else channel

    def _floor(self, channel: Channel) -> str:
        """The last id in ``channel``'s clock: its parent's or its own, and every thread under it."""
        root = self.clock_of(channel)
        return max((c.last_id for c in self.channels.values() if c is root or c.parent_id == root.id), key=int)

    def room_ms(self, channel: Channel) -> int:
        return int((self.clock() - (self.clock_of(channel).lag or 0.0)) * 1000)

    def stamp(self, channel: Channel, *, at: datetime | None = None, wall: bool = False) -> str:
        """Mint the id of a new message in ``channel``, which is its time.

        A bot's post through REST is stamped when it arrives, which brings the
        room's clock up to the wall. A director's post takes ``at`` (never
        later than now), or else the room's time. The lag only shrinks, and an
        id is always above the last in the channel's clock: a time raised for
        that is logged.
        """
        clock, now = self.clock_of(channel), self.clock()
        if wall:
            when, clock.lag = now, 0.0
        else:
            when = now - (clock.lag or 0.0) if at is None else min(at.timestamp(), now)
            if clock.lag is None or now - when < clock.lag:
                clock.lag = now - when
        ms = int(when * 1000)
        message_id = self._mint(ms, self._floor(channel))
        if id_ms(message_id) > ms:
            self.log("raise", channel=channel.name, requested=iso(ms), stamped=iso(id_ms(message_id)))
        channel.last_id = message_id
        return message_id

    def advance(self, channel: Channel, seconds: float) -> None:
        """Move the room's clock forward; it never passes the wall."""
        clock = self.clock_of(channel)
        clock.lag = max(0.0, (clock.lag or 0.0) - seconds)

    # -- permissions ------------------------------------------------------------------------------

    def permissions(self, member_id: str, channel_id: str) -> int:
        """Discord's algorithm: the roles' base with @everyone; ADMINISTRATOR; then the @everyone, role and member overwrites.

        A thread takes its parent's. Without VIEW_CHANNEL nothing in the
        channel is allowed, and without SEND_MESSAGES (in a thread,
        SEND_MESSAGES_IN_THREADS) neither is mentioning everyone, as
        Discord's implicit permissions say.
        """
        member = self.members[member_id]
        channel = self.channels[channel_id]
        send = "SEND_MESSAGES_IN_THREADS" if channel.parent_id else "SEND_MESSAGES"
        if channel.parent_id:
            channel = self.channels[channel.parent_id]
        if member_id == self.owner_id:
            return ALL
        perms = self.roles[self.guild_id].permissions
        for role_id in member.roles:
            perms |= self.roles[role_id].permissions
        if perms & P["ADMINISTRATOR"]:
            return ALL
        for overwrite in channel.overwrites:
            if overwrite["type"] == 0 and overwrite["id"] == self.guild_id:
                perms = (perms & ~overwrite["deny"]) | overwrite["allow"]
        allow = deny = 0
        for overwrite in channel.overwrites:
            if overwrite["type"] == 0 and overwrite["id"] in member.roles:
                allow, deny = allow | overwrite["allow"], deny | overwrite["deny"]
        perms = (perms & ~deny) | allow
        for overwrite in channel.overwrites:
            if overwrite["type"] == 1 and overwrite["id"] == member_id:
                perms = (perms & ~overwrite["deny"]) | overwrite["allow"]
        if not perms & P["VIEW_CHANNEL"]:
            return 0
        if not perms & P[send]:
            perms &= ~bits(["MENTION_EVERYONE", "SEND_TTS_MESSAGES", "EMBED_LINKS", "ATTACH_FILES"])
        return perms

    def find_channel(self, channel_id: str) -> Channel:
        channel = self.channels.get(str(channel_id))
        if channel is None:
            raise DiscordError(404, 10003, "Unknown Channel")
        return channel

    def require(self, member_id: str, channel_id: str, *needed: str) -> int:
        perms = self.permissions(member_id, channel_id)
        if not perms & P["VIEW_CHANNEL"]:
            raise DiscordError(*MISSING_ACCESS)
        if any(not perms & P[name] for name in needed):
            raise DiscordError(*MISSING_PERMISSIONS)
        return perms

    # -- messages ---------------------------------------------------------------------------------

    def create_message(
        self,
        author_id: str,
        channel_id: str,
        content: Any,
        *,
        reference: dict[str, Any] | None = None,
        allowed_mentions: dict[str, Any] | None = None,
        nonce: Any = None,
        enforce_nonce: bool = False,
        at: datetime | None = None,
        wall: bool = False,
    ) -> tuple[dict[str, Any], bool]:
        """Post a message; returns it and whether it is new (False: ``enforce_nonce`` found the earlier one)."""
        channel = self.find_channel(channel_id)
        perms = self.require(author_id, channel.id, "SEND_MESSAGES_IN_THREADS" if channel.parent_id else "SEND_MESSAGES")
        if not isinstance(content, str) or not content.strip():
            raise DiscordError(400, 50006, "Cannot send an empty message")
        if len(content) > MAX_LENGTH:
            raise _form_error("content", "BASE_TYPE_MAX_LENGTH", f"Must be {MAX_LENGTH} or fewer in length.")
        if enforce_nonce and nonce is not None and (author_id, str(nonce)) in self._nonces:
            return self.messages[self._nonces[author_id, str(nonce)]], False
        target = None
        if reference is not None:
            if not perms & P["READ_MESSAGE_HISTORY"]:
                raise DiscordError(*MISSING_PERMISSIONS)
            target = self.messages.get(str(reference.get("message_id")))
            if str(reference.get("channel_id", channel.id)) != channel.id or (target and target["channel_id"] != channel.id):
                raise _form_error("message_reference", "REPLIES_CANNOT_REFERENCE_OTHER_CHANNEL", "Cannot reply to a message in a different channel")
            if target is None and reference.get("fail_if_not_exists", True):
                raise _form_error("message_reference", "REPLIES_UNKNOWN_MESSAGE", "Unknown message")
        users, roles, everyone = self._addressing(author_id, perms, content, target, allowed_mentions)
        message = {
            "id": self.stamp(channel, at=at, wall=wall),
            "channel_id": channel.id,
            "author_id": author_id,
            "content": content,
            "mentions": users,
            "mention_roles": roles,
            "mention_everyone": everyone,
            "reply_to": target["id"] if target else None,
            "nonce": nonce,
            "reactions": {},
        }
        self.messages[message["id"]] = message
        if enforce_nonce and nonce is not None:
            self._nonces[author_id, str(nonce)] = message["id"]
        channel.messages += 1
        return message, True

    def _addressing(self, author_id: str, perms: int, content: str, target: dict | None, allowed: dict | None) -> tuple[list[str], list[str], bool]:
        """Who a message addresses: mentioned users, roles, @everyone/@here, and the author it replies to.

        A room-wide or role mention needs MENTION_EVERYONE (no role here is
        mentionable). A bot's ``allowed_mentions`` limits what counts; without
        it everything parses, and whether a reply pings its target's author is
        the world's ``reply_ping`` (Discord's default there is unverified).
        """
        everyone_ok = bool(perms & P["MENTION_EVERYONE"])
        allowed_given = allowed is not None
        allowed = allowed or {}
        parse = set(allowed.get("parse") or []) if allowed_given else {"users", "roles", "everyone"}
        named_users = {str(u) for u in allowed.get("users") or []}
        named_roles = {str(r) for r in allowed.get("roles") or []}
        users = [u for u in dict.fromkeys(USER_MENTION.findall(content)) if u in self.members and ("users" in parse or u in named_users)]
        roles = [
            r for r in dict.fromkeys(ROLE_MENTION.findall(content))
            if r in self.roles and r != self.guild_id and everyone_ok and ("roles" in parse or r in named_roles)
        ]
        everyone = everyone_ok and "everyone" in parse and bool(EVERYONE_MENTION.search(content))
        ping = bool(allowed.get("replied_user", False)) if allowed_given else self.reply_ping
        if target and ping and target["author_id"] not in (author_id, *users):
            users.append(target["author_id"])
        return users, roles, everyone

    def react(self, user_id: str, channel_id: str, message_id: str, emoji: str, *, add: bool) -> bool:
        """Add or remove ``user_id``'s reaction; returns whether anything changed (Discord answers 204 either way)."""
        channel = self.find_channel(channel_id)
        message = self.messages.get(str(message_id))
        if message is None or message["channel_id"] != channel.id:
            raise DiscordError(404, 10008, "Unknown Message")
        perms = self.require(user_id, channel.id)
        if not emoji_ok(emoji):
            raise DiscordError(400, 10014, "Unknown Emoji")
        reactions = message["reactions"]
        if not add:
            users = reactions.get(emoji, [])
            if user_id not in users:
                return False
            users.remove(user_id)
            if not users:
                del reactions[emoji]
            return True
        if not perms & P["READ_MESSAGE_HISTORY"] or (emoji not in reactions and not perms & P["ADD_REACTIONS"]):
            raise DiscordError(*MISSING_PERMISSIONS)
        if emoji not in reactions and len(reactions) >= MAX_REACTIONS:
            raise DiscordError(400, 30010, f"Maximum number of reactions reached ({MAX_REACTIONS})")
        users = reactions.setdefault(emoji, [])
        if user_id in users:
            return False
        users.append(user_id)
        return True

    def create_thread(self, owner_id: str, parent_id: str, name: str, from_message: str | None = None) -> Channel:
        """A public thread under a text channel; one started from a message takes that message's id, as on Discord."""
        parent = self.find_channel(parent_id)
        if parent.parent_id or any(c.name == name for c in self.channels.values()):
            raise ValueError(f"a thread {name!r} cannot go under {parent.name!r}: threads hold no threads, and names are unique")
        if from_message is not None:
            message = self.messages.get(str(from_message))
            if message is None or message["channel_id"] != parent.id:
                raise DiscordError(404, 10008, "Unknown Message")
            thread_id = message["id"]
        else:
            thread_id = self._mint(self.room_ms(parent), self._floor(parent))
        thread = Channel(thread_id, name, 0, parent_id=parent.id, owner_id=owner_id, last_id=thread_id)
        self.channels[thread_id] = thread
        return thread

    # -- the world file ---------------------------------------------------------------------------

    def describe(self) -> dict[str, Any]:
        """What configs, and whoever sets up a real guild to match, need: ids, roles, permissions and intents. No token."""

        def overwrites(channel: Channel) -> list[dict[str, Any]]:
            targets = {**self.roles, **self.members}
            return [{"target": targets[o["id"]].name, "allow": names(o["allow"]), "deny": names(o["deny"])} for o in channel.overwrites]

        def role_names(member: Member) -> list[str]:
            return [self.roles[r].name for r in member.roles]

        return {
            "guild": {"id": self.guild_id, "name": self.name, "owner": self.members[self.owner_id].name},
            "roles": {r.name: {"id": r.id, "permissions": names(r.permissions)} for r in self.roles.values()},
            "channels": {
                c.name: {"id": c.id, "parent": self.channels[c.parent_id].name if c.parent_id else None, "overwrites": overwrites(c)}
                for c in self.channels.values()
            },
            "people": {m.name: {"id": m.id, "roles": role_names(m)} for m in self.members.values() if not m.bot},
            "bots": {
                m.name: {"id": m.id, "harness": m.harness, "roles": role_names(m),
                         "privileged_intents": [n for n, v in INTENTS.items() if v & m.privileged]}
                for m in self.members.values() if m.bot
            },
            "reply_ping": self.reply_ping,
        }
