"""Discord's REST API: the routes something has been shown to call, and nothing else.

Every response is ``Content-Type: application/json`` exactly (discord.py
compares it with ``==``), or a 204 with no body, and a known route sends all
five ``X-RateLimit-*`` headers (the transport needs Remaining and
Reset-After, discord.py Reset-After or Reset). Errors are ``{message, code}``.
An injected fault answers in place of the route; a 429 carries ``Via`` and a
JSON body, without which discord.py takes it for a Cloudflare ban. Any
other route, host, request field or body (a file's multipart, say) the
stand-in does not model, and any request a handler fails on, gets 599 and an
``unknown`` record that fails the run. discord.py does not retry a 599;
Nunchi's transport retries a GET three times (about 14 s), and each attempt
is recorded.

One route is the stand-in's own, not Discord's: ``GET /_preflight/{nonce}``
takes no token and answers the run's nonce, so a process can prove before it
starts that Discord's names lead it here (`evals/rehearsal/preflight.py`).
Any other nonce gets 404 and an ``unknown`` record.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Any
from urllib.parse import unquote

from . import payloads
from .world import INTENTS, DiscordError, iso

API = "/api/v10"
# The body fields of a message post that the stand-in models; any other that is set (tts, embeds, files...) is unknown.
MESSAGE_FIELDS = {"content", "nonce", "enforce_nonce", "message_reference", "allowed_mentions"}


@dataclass
class Request:
    conn: int
    host: str
    method: str
    target: str
    headers: dict[str, str]
    body: bytes


class Unmodelled(Exception):
    """A request the stand-in cannot answer as Discord would."""


def _me(fd: Any, bot: Any, params: dict[str, str], body: Any) -> tuple[int, Any, str | None]:
    return 200, payloads.user(bot), "user"


def _application(fd: Any, bot: Any, params: dict[str, str], body: Any) -> tuple[int, Any, str | None]:
    return 200, payloads.application(fd.world, bot), "application"


def _post(fd: Any, bot: Any, params: dict[str, str], body: Any) -> tuple[int, Any, str | None]:
    if not isinstance(body, dict):
        raise DiscordError(400, 50109, "The request body contains invalid JSON.")
    unmodelled = sorted(k for k, v in body.items() if v and k not in MESSAGE_FIELDS)
    reference = body.get("message_reference")
    if unmodelled or (isinstance(reference, dict) and reference.get("type", 0) != 0):
        raise Unmodelled(f"message fields not modelled: {', '.join(unmodelled) or 'a forward'}")
    world = fd.world
    record, new = world.create_message(
        bot.id, params["channel"], body.get("content"), reference=reference, allowed_mentions=body.get("allowed_mentions"),
        nonce=body.get("nonce"), enforce_nonce=bool(body.get("enforce_nonce")), wall=True,
    )
    if new:
        fd.hub.fan_out("MESSAGE_CREATE", payloads.message(world, record, gateway=True), record["channel_id"], INTENTS["GUILD_MESSAGES"])
    return 200, payloads.message(world, record), "message"


def _reaction(add: bool):
    def handle(fd: Any, bot: Any, params: dict[str, str], body: Any) -> tuple[int, Any, str | None]:
        if fd.world.react(bot.id, params["channel"], params["message"], params["emoji"], add=add):
            record = fd.world.messages[params["message"]]
            event = "MESSAGE_REACTION_ADD" if add else "MESSAGE_REACTION_REMOVE"
            data = payloads.reaction(fd.world, bot.id, record, params["emoji"], add=add)
            fd.hub.fan_out(event, data, record["channel_id"], INTENTS["GUILD_MESSAGE_REACTIONS"])
        return 204, None, None

    return handle


def _channel(fd: Any, bot: Any, params: dict[str, str], body: Any) -> tuple[int, Any, str | None]:
    channel = fd.world.find_channel(params["channel"])
    fd.world.require(bot.id, channel.id)
    return 200, payloads.channel(fd.world, channel), "thread" if channel.parent_id else "text"


def _guild(fd: Any, guild_id: str) -> None:
    if guild_id != fd.world.guild_id:
        raise DiscordError(404, 10004, "Unknown Guild")


def _member(fd: Any, bot: Any, params: dict[str, str], body: Any) -> tuple[int, Any, str | None]:
    _guild(fd, params["guild"])
    member = fd.world.members.get(params["user"])
    if member is None:
        raise DiscordError(404, 10007, "Unknown Member")
    return 200, payloads.member(member), "member"


def _roles(fd: Any, bot: Any, params: dict[str, str], body: Any) -> tuple[int, Any, str | None]:
    _guild(fd, params["guild"])
    return 200, [payloads.role(r) for r in fd.world.roles.values()], "role"


def _preflight(fd: Any, bot: Any, params: dict[str, str], body: Any) -> tuple[int, Any, str | None]:
    if params["nonce"] != fd.preflight_nonce:  # another run's check, or a guess: this is not its stand-in
        fd.wire.write("unknown", what="preflight nonce", nonce=params["nonce"])
        raise DiscordError(404, 0, "404: Not Found")
    return 200, {"nonce": fd.preflight_nonce}, None


ROUTES = {
    ("GET", "/users/@me"): _me,
    ("GET", "/oauth2/applications/@me"): _application,
    ("POST", "/channels/{channel}/messages"): _post,
    ("PUT", "/channels/{channel}/messages/{message}/reactions/{emoji}/@me"): _reaction(True),
    ("DELETE", "/channels/{channel}/messages/{message}/reactions/{emoji}/@me"): _reaction(False),
    ("GET", "/channels/{channel}"): _channel,
    ("GET", "/guilds/{guild}/members/{user}"): _member,
    ("GET", "/guilds/{guild}/roles"): _roles,
    ("GET", "/_preflight/{nonce}"): _preflight,
}
# The routes that take no token: only the stand-in's own preflight.
OPEN_ROUTES = {"/_preflight/{nonce}"}


def match(method: str, path: str) -> tuple[str, dict[str, str]] | None:
    """The route template a request path takes, with its percent-decoded parameters."""
    if not path.startswith(API + "/"):
        return None
    parts = path[len(API):].split("/")
    for route_method, template in ROUTES:
        pattern = template.split("/")
        if route_method != method or len(pattern) != len(parts):
            continue
        params = {}
        for want, got in zip(pattern, parts):
            if want.startswith("{"):
                params[want[1:-1]] = unquote(got)
            elif want != got:
                break
        else:
            return template, params
    return None


def ratelimit(template: str, *, remaining: int = 49, reset_after: float = 1.0) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": "50",
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": f"{time.time() + reset_after:.3f}",
        "X-RateLimit-Reset-After": f"{reset_after:.3f}",
        "X-RateLimit-Bucket": hashlib.sha256(template.encode()).hexdigest()[:32],
    }


def _fault(fd: Any, method: str, template: str, path: str) -> tuple[int, Any, dict[str, str]] | None:
    """The answer of the next injected fault for this request, if one is due: a 429 as Discord's, anything else bare."""
    for fault in fd.faults:
        if fault["count"] > 0 and fault["method"] == method and fault["path"] in (template, path):
            fault["count"] -= 1
            if fault["status"] != 429:
                return fault["status"], {"message": f"injected {fault['status']}", "code": 0}, {}
            retry = 1.0 if fault["retry_after"] is None else fault["retry_after"]
            headers = {**ratelimit(template, remaining=0, reset_after=retry), "Via": "1.1 google", "Retry-After": str(math.ceil(retry)),
                       "X-RateLimit-Scope": "user"}
            return 429, {"message": "You are being rate limited.", "retry_after": retry, "global": False}, headers
    return None


def handle(fd: Any, request: Request) -> tuple[int, dict[str, str], bytes]:
    """Answer one request as Discord would, and log the exchange."""
    path, _, query = request.target.partition("?")
    content_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    body: Any = None
    gap = None
    if request.body and content_type != "application/json":
        gap = f"a {content_type} body (a file, say)" if content_type else "a body without a Content-Type"
        body = {"not modelled": gap, "bytes": len(request.body)}
    elif request.body:
        try:
            body = json.loads(request.body)
        except ValueError:
            body = request.body.decode("utf-8", "replace")  # a post answers it 50109, as Discord would
    auth = request.headers.get("authorization", "")
    bot = fd.world.bot_by_token(auth[4:]) if auth.startswith("Bot ") else None  # a bot token without "Bot " is a 401
    record: dict[str, Any] = {
        "conn": request.conn, "host": request.host, "method": request.method, "path": path, "decoded_path": unquote(path),
        "query": query, "headers": sorted(request.headers), "user_agent": request.headers.get("user-agent"),
        "bot": bot.name if bot else None, "request": body,
    }
    if isinstance(body, dict) and isinstance(body.get("content"), str) and body["content"] != body["content"].strip():
        record["whitespace"] = True
    found = match(request.method, path) if request.host in fd.rest_hosts else None
    headers: dict[str, str] = {}
    kind = None
    if found is None:
        status, payload = 599, {"message": f"the stand-in does not model {request.method} {path} on {request.host}", "code": 0}
        fd.wire.write("unknown", what="route", method=request.method, path=path, host=request.host)
    else:
        template, params = found
        record["route"] = template
        fault = _fault(fd, request.method, template, path[len(API):])
        if fault is not None:
            (status, payload, headers), record["fault"] = fault, True
        elif bot is None and template not in OPEN_ROUTES:
            status, payload, headers = 401, {"message": "401: Unauthorized", "code": 0}, ratelimit(template)
        else:
            headers = ratelimit(template)
            try:
                if gap:
                    raise Unmodelled(gap)
                status, payload, kind = ROUTES[request.method, template](fd, bot, params, body)
            except DiscordError as error:
                status, payload = error.status, error.body
            except Exception as error:  # unmodelled, or a request nobody foresaw: answered and recorded, never a dropped socket
                what, detail = ("request", str(error)) if isinstance(error, Unmodelled) else ("stand-in error", repr(error))
                status, payload, headers = 599, {"message": detail, "code": 0}, {}
                fd.wire.write("unknown", what=what, method=request.method, path=path, detail=detail)
            channel = fd.world.channels.get(params.get("channel", ""))
            if channel is not None:
                record["room_time"] = iso(fd.world.room_ms(channel))
    if kind is not None:
        for item in payload if isinstance(payload, list) else [payload]:
            fd.check_shape(kind, item)
    data = b"" if payload is None else json.dumps(payload).encode()
    if payload is not None:
        headers["Content-Type"] = "application/json"
    fd.wire.write("http", **record, status=status, response=payload, ratelimit={k: v for k, v in headers.items() if k.startswith("X-RateLimit")} or None)
    return status, headers, data
