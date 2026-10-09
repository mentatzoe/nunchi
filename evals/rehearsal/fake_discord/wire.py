"""The wire log (``discord-wire.jsonl``) and the verdict (``discord-standin.json``).

Every record is one event: a TLS hello or handshake, an HTTP exchange, a
gateway frame or close, a control call, a raised message time, or an
``unknown``: a route, op, host, request, gateway query or payload shape the
stand-in does not model, or a request it failed on. An unknown fails the run
(`verdict`), because clients such as Hermes swallow many REST errors and
only the stand-in's own record shows them. Each bot token is
replaced by ``<bot:name>`` before a record is kept or written, wherever it
appears.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time
from typing import Any

# What the stand-in does not model, in every verdict.
FIDELITY = [
    "Content is never trimmed: leading or trailing whitespace is kept, and marked whitespace: true on the request.",
    "Length is counted in Python code points; how Discord counts it is unverified.",
    "Every gateway frame is an uncompressed TEXT frame, whatever compress= asks.",
    "Content is never blanked for a bot without MESSAGE_CONTENT: a bot that asks for the intent without it enabled is closed with 4014.",
    "Rate limits: fixed, generous numbers (limit 50, remaining 49, reset after 1 s); a 429 comes only when injected.",
    "Emoji: an approximate check refuses words, custom emoji and more than one emoji (10014); a symbol that is no emoji, "
    "such as ✓, passes, and which emoji Discord accepts is unverified.",
    "Whether a reply without allowed_mentions pings its target's author is the world's reply_ping; Discord's default is unverified.",
    "Mentions that allowed_mentions suppresses are left out of mentions and mention_roles.",
    "A reply with fail_if_not_exists: false to a message in another channel is refused (400 50035); Discord's answer is unverified.",
    "GUILD_CREATE goes only to bots with the GUILDS intent; what Discord sends the others is unverified.",
    "GUILD_CREATE lists only the bot's own member unless it asks for GUILD_PRESENCES, as discord.py assumes; "
    "whether a small guild lists everyone, which would mean no op 8, is unverified.",
    "Heartbeats are answered but never required: a connection that stops heartbeating is not closed.",
    "A client's close never ends its session; Discord ends it on 1000 or 1001.",
    "Events sent: READY, RESUMED, GUILD_CREATE, GUILD_MEMBERS_CHUNK, MESSAGE_CREATE, MESSAGE_REACTION_ADD/REMOVE, THREAD_CREATE. "
    "No typing, edits, deletes, member joins or leaves, presences, or thread system messages (types 18 and 21).",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _heartbeat(record: Mapping[str, Any]) -> bool:
    return record.get("kind") == "ws" and record.get("op") in (1, 11)


class Wire:
    """An append-only record of the stand-in's traffic, safe across threads; ``redactions`` maps each secret to its label."""

    def __init__(self, path: Path | None, redactions: Mapping[str, str]) -> None:
        self.path = path
        self.redactions = dict(redactions)
        self.records: list[dict[str, Any]] = []
        self._changed = threading.Condition()
        self._last_traffic = time.monotonic()

    def write(self, kind: str, **fields: Any) -> dict[str, Any]:
        text = json.dumps({"kind": kind, "at": now_iso(), **fields}, ensure_ascii=False, sort_keys=True, default=str)
        for secret, label in self.redactions.items():
            text = text.replace(secret, label)
        record = json.loads(text)
        with self._changed:
            record["n"] = len(self.records)
            self.records.append(record)
            if self.path is not None:
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            if not _heartbeat(record):
                self._last_traffic = time.monotonic()
            self._changed.notify_all()
        return record

    def wait_for(self, predicate: Callable[[dict[str, Any]], bool], timeout: float, *, since: int = 0) -> dict[str, Any]:
        """The first record from ``since`` on that matches; waits up to ``timeout`` seconds, then raises TimeoutError."""
        deadline = time.monotonic() + timeout
        with self._changed:
            while True:
                for record in self.records[since:]:
                    if predicate(record):
                        return record
                since = len(self.records)
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError("no wire record matched in time")
                self._changed.wait(left)

    def settle(self, quiet: float, timeout: float) -> bool:
        """Wait until nothing but heartbeats has crossed the wire for ``quiet`` seconds.

        That is a quiet wire, not a finished turn: combine it with Nunchi's receipts.
        """
        deadline = time.monotonic() + timeout
        with self._changed:
            while True:
                now = time.monotonic()
                if now - self._last_traffic >= quiet:
                    return True
                if now >= deadline:
                    return False
                self._changed.wait(min(deadline, self._last_traffic + quiet) - now)


def verdict(records: list[dict[str, Any]], bots: list[str]) -> dict[str, Any]:
    """What each bot did, every unknown record, every raised time, and what is not modelled. Clean only with no unknown."""

    def count(bot: str, test: Callable[[dict[str, Any]], bool]) -> int:
        return sum(1 for r in records if r.get("bot") == bot and test(r))

    per_bot = {}
    for bot in bots:
        identifies = [r for r in records if r.get("bot") == bot and r["kind"] == "ws" and r["dir"] == "in" and r["op"] == 2]
        per_bot[bot] = {
            "identify": len(identifies),
            "intents": identifies[-1]["d"].get("intents") if identifies else None,
            "resume": count(bot, lambda r: r["kind"] == "ws" and r["dir"] == "in" and r["op"] == 6),
            "ready": count(bot, lambda r: r["kind"] == "ws" and r["dir"] == "out" and r.get("t") == "READY"),
            "chunks": count(bot, lambda r: r["kind"] == "ws" and r["dir"] == "out" and r.get("t") == "GUILD_MEMBERS_CHUNK"),
            "requests": count(bot, lambda r: r["kind"] == "http"),
            "writes": count(bot, lambda r: r["kind"] == "http" and r["method"] != "GET" and 200 <= r["status"] < 300),
        }
    unknown = [r for r in records if r["kind"] == "unknown"]
    return {
        "clean": not unknown,
        "bots": per_bot,
        "unknown": unknown,
        "raised": [r for r in records if r["kind"] == "raise"],
        "fidelity": FIDELITY,
    }
