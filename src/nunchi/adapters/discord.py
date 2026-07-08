"""Discord adapter for nunchi.

Requires discord.py (not a default dependency — opt-in only):

    pip install nunchi[discord]

Joins Discord channels as a gated participant. Uses discord.py's event-driven
client with the message_content intent. Every inbound text message is run
through the nunchi admission gate; non-silent verdicts invoke a pluggable
responder callable.

Required env vars:
    NUNCHI_DISCORD_TOKEN      Bot token (from the Discord Developer Portal)
    NUNCHI_DISCORD_CHANNELS   Comma-separated channel IDs to watch (integers)

Optional env vars:
    NUNCHI_DISCORD_PEER_BOTS    Comma-separated bot user IDs treated as
                                gated peers (used with NUNCHI_DISCORD_BOT_POLICY)
    NUNCHI_DISCORD_BOT_POLICY   "all" (default) or "allowlist"
                                - "all": process all bot messages (skip only self)
                                - "allowlist": skip bots NOT in NUNCHI_DISCORD_PEER_BOTS,
                                  but still process those in the peer list
    NUNCHI_DISCORD_MAX_EVENTS   Stop after this many gated events (for bounded test
                                runs / integration tests). Unset = run forever.
    NUNCHI_DISCORD_LOG          JSONL receipt log path
                                (default: ~/.nunchi/discord-gate.jsonl)
    NUNCHI_DISCORD_AGENT_ID     Agent identity (default: bot_<username>)
    NUNCHI_DISCORD_HISTORY      History window per channel (default: 10)
    NUNCHI_DISCORD_BACKSTOP_MAX_SENDS
                                Send backstop (amplification-loops guard, default
                                ON): max sends per channel per window (default: 5)
    NUNCHI_DISCORD_BACKSTOP_WINDOW_SECONDS
                                Send backstop window in seconds (default: 10).
                                When the cap trips, the send is suppressed and
                                the receipt records action='rate-limited'.
    NUNCHI_RESPONDER_MODEL      LLM model for the built-in demo responder
    OPENROUTER_API_KEY          API key for the demo responder
    NUNCHI_CLASSIFIER_MODEL     Model used by both classifier and demo responder

NOTE: The built-in demo responder uses synchronous urllib calls inside an async
event handler. This blocks the discord.py event loop briefly during LLM calls.
For production use, supply your own async-compatible responder callable.

The responder callback contract:
    respond(trigger: dict, history: list[dict], gate_result: ChannelGateResult)
        -> str | None

Return a string to send to the channel, or None to stay silent.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Callable

from ._backstop import backstop_from_env
from ._responder import _demo_responder
from .channel import ChannelGateResult, gate as channel_gate

logger = logging.getLogger("nunchi.adapters.discord")

_DEFAULT_HISTORY_LEN = 20
_DEFAULT_LOG_FILE = "~/.nunchi/discord-gate.jsonl"


# --------------------------------------------------------------------------- #
# Pure import-safe helpers (no discord.py dependency)
# These functions can be imported and tested without discord.py installed.
# --------------------------------------------------------------------------- #


def _resolve_author_kind(
    user_id: int,
    own_user_id: int,
    is_bot: bool,
    bot_policy: str,
    peer_bot_ids: frozenset[int],
) -> str:
    """Map a Discord user to an author_kind string.

    Returns one of:
    - "self"     — own bot user
    - "peer_bot" — a bot that should be gated as a peer
    - "human"    — a human user
    - "_skip"    — a bot that should be silently ignored under allowlist policy

    Under bot_policy "all", every bot (excluding self) is "peer_bot".
    Under bot_policy "allowlist", bots not in peer_bot_ids return "_skip";
    bots in peer_bot_ids return "peer_bot".
    """
    if user_id == own_user_id:
        return "self"
    if is_bot:
        if bot_policy == "allowlist":
            return "peer_bot" if user_id in peer_bot_ids else "_skip"
        # "all" policy: process all bots as peer_bot
        return "peer_bot"
    return "human"


def _append_to_history(
    history: list[dict],
    msg: dict,
    history_len: int,
) -> list[dict]:
    """Return a new trimmed history list with *msg* appended.

    The original list is never mutated. The result is trimmed to at most
    ``history_len`` items.
    """
    result = list(history)
    result.append(msg)
    if len(result) > history_len:
        result = result[-history_len:]
    return result


def _build_receipt(
    channel_id: int,
    trigger: dict,
    history_len: int,
    result: ChannelGateResult | None,
    action: str,
    elapsed_ms: int,
    error: str | None = None,
) -> dict:
    """Build a JSONL receipt record (same field shape as matrix/telegram adapters)."""
    record: dict = {
        "ts": trigger.get("timestamp"),
        "room_id": str(channel_id),
        "event_id": trigger.get("message_id"),
        "author": trigger.get("author"),
        "author_kind": trigger.get("author_kind"),
        "history_len": history_len,
        "verdict": result.verdict if result else None,
        "silent": result.silent if result else None,
        "action": action,
        "elapsed_ms": elapsed_ms,
        "reasons": list(result.reasons[:3]) if result else [],
        "confidences": result.confidences if result else {},
    }
    if error is not None:
        record["error"] = error
    return record


def _write_receipt(log_path: Path, record: dict) -> None:
    """Append one JSON line to the receipt log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with log_path.open("a") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError as exc:
        logger.warning("Could not write receipt to %s: %s", log_path, exc)


# --------------------------------------------------------------------------- #
# Env-var helpers
# --------------------------------------------------------------------------- #


def _require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(f"Required environment variable {name} is not set.")
    return val


# --------------------------------------------------------------------------- #
# Console script entry point
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``nunchi-discord`` console script.

    Usage::

        nunchi-discord [--dry-run]

    discord.py is event-driven; there is no ``--once`` flag. To bound the run
    for testing, set NUNCHI_DISCORD_MAX_EVENTS=N — the client exits after N
    gated events.

    Flags:
        --dry-run   Run the gate but never send; receipts record 'dry-run'.
    """
    try:
        import discord
    except ImportError:
        print(
            "nunchi-discord: discord.py is not installed.\n"
            "Install it with: pip install nunchi[discord]",
            file=sys.stderr,
        )
        return 1

    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    parser = argparse.ArgumentParser(
        prog="nunchi-discord",
        description=(
            "nunchi-discord: join Discord channels as a gated participant. "
            "Reads NUNCHI_DISCORD_TOKEN and NUNCHI_DISCORD_CHANNELS from env."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the gate but never send; receipts record action='dry-run'.",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    # Validate required env vars before touching the network
    missing = []
    for var in ("NUNCHI_DISCORD_TOKEN", "NUNCHI_DISCORD_CHANNELS"):
        if not os.environ.get(var, "").strip():
            missing.append(var)
    if missing:
        print(
            "nunchi-discord: required environment variables not set:\n"
            + "\n".join(f"  {v}" for v in missing)
            + "\n\nSee the module docstring for setup instructions.",
            file=sys.stderr,
        )
        return 1

    # Parse config
    try:
        token = _require_env("NUNCHI_DISCORD_TOKEN")
        channels_raw = _require_env("NUNCHI_DISCORD_CHANNELS")
        channel_ids = frozenset(int(c.strip()) for c in channels_raw.split(",") if c.strip())
    except (RuntimeError, ValueError) as exc:
        print(f"nunchi-discord: configuration error: {exc}", file=sys.stderr)
        return 1

    peer_bots_raw = os.environ.get("NUNCHI_DISCORD_PEER_BOTS", "")
    peer_bot_ids: frozenset[int] = frozenset(
        int(b.strip()) for b in peer_bots_raw.split(",") if b.strip()
    )

    bot_policy = os.environ.get("NUNCHI_DISCORD_BOT_POLICY", "all").strip().lower()
    if bot_policy not in ("all", "allowlist"):
        print(
            f"nunchi-discord: NUNCHI_DISCORD_BOT_POLICY must be 'all' or 'allowlist', got {bot_policy!r}",
            file=sys.stderr,
        )
        return 1

    history_len_raw = os.environ.get("NUNCHI_DISCORD_HISTORY", str(_DEFAULT_HISTORY_LEN))
    try:
        history_len = int(history_len_raw)
    except ValueError:
        history_len = _DEFAULT_HISTORY_LEN

    log_path = Path(os.environ.get("NUNCHI_DISCORD_LOG", _DEFAULT_LOG_FILE)).expanduser()

    max_events_raw = os.environ.get("NUNCHI_DISCORD_MAX_EVENTS", "")
    max_events: int | None = int(max_events_raw) if max_events_raw.strip().isdigit() else None

    # Per-channel send backstop (amplification-loops guard) — default ON.
    backstop = backstop_from_env("NUNCHI_DISCORD")

    # Responder setup (resolved after we know the agent_id)
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("NUNCHI_CLASSIFIER_API_KEY", "")
    responder_model = (
        os.environ.get("NUNCHI_RESPONDER_MODEL")
        or os.environ.get("NUNCHI_CLASSIFIER_MODEL")
        or ""
    )
    base_url = (
        os.environ.get("NUNCHI_CLASSIFIER_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://openrouter.ai/api/v1"
    )

    # ------------------------------------------------------------------ #
    # Define the discord.Client subclass here (where discord is in scope)
    # ------------------------------------------------------------------ #

    class NunchiDiscordClient(discord.Client):
        """discord.py client that gates every inbound channel message."""

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            # Resolved after on_ready
            self._own_user_id: int | None = None
            self._agent_id: str = ""
            # Per-channel in-memory history: channel_id -> list[dict]
            self._channel_history: dict[int, list[dict]] = {}
            # Channels backfilled on first event
            self._backfilled: set[int] = set()
            self._event_count: int = 0
            # Build responder closure once we have agent_id (updated in on_ready)
            self._responder: Callable[[dict, list[dict], ChannelGateResult], str | None] | None = None

        async def on_ready(self):
            assert self.user is not None
            self._own_user_id = self.user.id
            username = self.user.name

            agent_id_raw = os.environ.get("NUNCHI_DISCORD_AGENT_ID", "").strip()
            self._agent_id = agent_id_raw if agent_id_raw else f"bot_{username}"

            if api_key and responder_model:
                _agent_id_capture = self._agent_id

                def _resp(
                    trigger: dict,
                    history: list[dict],
                    gate_result: ChannelGateResult,
                ) -> str | None:
                    return _demo_responder(
                        trigger,
                        history,
                        gate_result,
                        agent_id=_agent_id_capture,
                        model=responder_model,
                        api_key=api_key,
                        base_url=base_url,
                    )

                self._responder = _resp
            else:
                logger.info(
                    "Demo responder disabled: set OPENROUTER_API_KEY and NUNCHI_RESPONDER_MODEL "
                    "(or NUNCHI_CLASSIFIER_MODEL) to enable it."
                )

            logger.info(
                "Discord bot ready as %s (id=%s) agent_id=%s channels=%s",
                self.user,
                self._own_user_id,
                self._agent_id,
                sorted(channel_ids),
            )

        async def on_message(self, message):
            if message.channel.id not in channel_ids:
                return
            if not message.content or not message.content.strip():
                return

            assert self._own_user_id is not None, "on_message fired before on_ready"

            user_id: int = message.author.id
            is_bot: bool = message.author.bot

            author_kind = _resolve_author_kind(
                user_id, self._own_user_id, is_bot, bot_policy, peer_bot_ids
            )

            if author_kind == "_skip":
                # Bot not in allowlist — ignore silently
                return

            username: str = str(getattr(message.author, "name", str(user_id)))
            msg_record = {
                "content": message.content.strip(),
                "author": username,
                "author_kind": author_kind,
                "message_id": str(message.id),
                "timestamp": str(int(message.created_at.timestamp()))
                if message.created_at
                else None,
            }

            ch_id: int = message.channel.id

            if author_kind == "self":
                # Record own messages in history but don't gate
                self._channel_history[ch_id] = _append_to_history(
                    self._channel_history.get(ch_id, []), msg_record, history_len
                )
                return

            # Backfill history on the first event per channel
            if ch_id not in self._backfilled:
                await self._backfill(message.channel)
                self._backfilled.add(ch_id)

            current_history = list(
                self._channel_history.get(ch_id, [])[-history_len:]
            )
            # Append trigger to history for future context
            self._channel_history[ch_id] = _append_to_history(
                self._channel_history.get(ch_id, []), msg_record, history_len
            )

            # Gate and respond (synchronous gate call inside async handler)
            await self._gate_and_respond(ch_id, msg_record, current_history)

            # Max-events shutdown for bounded runs
            self._event_count += 1
            if max_events is not None and self._event_count >= max_events:
                logger.info("NUNCHI_DISCORD_MAX_EVENTS=%d reached; shutting down.", max_events)
                await self.close()

        async def _backfill(self, channel) -> None:
            """Seed history from the channel's 10 most recent messages."""
            try:
                messages = []
                async for msg in channel.history(limit=10, oldest_first=False):
                    messages.append(msg)
                # oldest_first=False means newest first; reverse for chronological
                for msg in reversed(messages):
                    if not msg.content or not msg.content.strip():
                        continue
                    user_id = msg.author.id
                    is_bot = msg.author.bot
                    ak = _resolve_author_kind(
                        user_id, self._own_user_id, is_bot, bot_policy, peer_bot_ids
                    )
                    if ak == "_skip":
                        continue
                    rec = {
                        "content": msg.content.strip(),
                        "author": str(getattr(msg.author, "name", str(user_id))),
                        "author_kind": ak,
                        "message_id": str(msg.id),
                        "timestamp": str(int(msg.created_at.timestamp()))
                        if msg.created_at
                        else None,
                    }
                    self._channel_history[channel.id] = _append_to_history(
                        self._channel_history.get(channel.id, []), rec, history_len
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("History backfill failed for channel %s: %s", channel.id, exc)

        async def _gate_and_respond(
            self,
            channel_id: int,
            trigger_record: dict,
            history_snapshot: list[dict],
        ) -> None:
            t0 = time.monotonic()
            try:
                result: ChannelGateResult = channel_gate(
                    trigger_record,
                    history_snapshot,
                    agent_id=self._agent_id,
                    fail_policy="open",
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Gate error msg=%s channel=%s: %s",
                    trigger_record.get("message_id"),
                    channel_id,
                    exc,
                )
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                receipt = _build_receipt(channel_id, trigger_record, len(history_snapshot), None, "error", elapsed_ms, error=str(exc))
                _write_receipt(log_path, receipt)
                return

            elapsed_ms = int((time.monotonic() - t0) * 1000)

            if result.silent:
                logger.debug("PASS (silent) msg=%s channel=%s", trigger_record.get("message_id"), channel_id)
                _write_receipt(log_path, _build_receipt(channel_id, trigger_record, len(history_snapshot), result, "silent", elapsed_ms))
                return

            if args.dry_run:
                logger.info("[dry-run] verdict=%s msg=%s channel=%s", result.verdict, trigger_record.get("message_id"), channel_id)
                _write_receipt(log_path, _build_receipt(channel_id, trigger_record, len(history_snapshot), result, "dry-run", elapsed_ms))
                return

            if self._responder is None:
                logger.info("verdict=%s (no responder) msg=%s channel=%s", result.verdict, trigger_record.get("message_id"), channel_id)
                _write_receipt(log_path, _build_receipt(channel_id, trigger_record, len(history_snapshot), result, "silent", elapsed_ms))
                return

            try:
                reply_text = self._responder(trigger_record, history_snapshot, result)
            except Exception as exc:  # noqa: BLE001
                logger.error("Responder error msg=%s: %s", trigger_record.get("message_id"), exc)
                _write_receipt(log_path, _build_receipt(channel_id, trigger_record, len(history_snapshot), result, "error", elapsed_ms, error=str(exc)))
                return

            if reply_text is None:
                logger.debug("Responder declined msg=%s", trigger_record.get("message_id"))
                _write_receipt(log_path, _build_receipt(channel_id, trigger_record, len(history_snapshot), result, "responder-declined", elapsed_ms))
                return

            # Send backstop: sliding-window cap on sends per channel (default
            # ON). A tripped cap suppresses the send — it never queues.
            wait = backstop.try_acquire(str(channel_id))
            if wait > 0:
                logger.warning(
                    "Send backstop tripped channel=%s (max %d per %.0fs); suppressing send, retry in %.1fs",
                    channel_id,
                    backstop.max_sends,
                    backstop.window_seconds,
                    wait,
                )
                _write_receipt(log_path, _build_receipt(channel_id, trigger_record, len(history_snapshot), result, "rate-limited", elapsed_ms))
                return

            try:
                channel = self.get_channel(channel_id)
                if channel is None:
                    raise RuntimeError(f"Channel {channel_id} not found in cache")
                await channel.send(reply_text)
            except Exception as exc:  # noqa: BLE001
                logger.error("channel.send error msg=%s channel=%s: %s", trigger_record.get("message_id"), channel_id, exc)
                _write_receipt(log_path, _build_receipt(channel_id, trigger_record, len(history_snapshot), result, "error", elapsed_ms, error=str(exc)))
                return

            logger.info("spoke verdict=%s msg=%s channel=%s", result.verdict, trigger_record.get("message_id"), channel_id)
            _write_receipt(log_path, _build_receipt(channel_id, trigger_record, len(history_snapshot), result, "spoke", elapsed_ms))

    # ------------------------------------------------------------------ #
    # Launch
    # ------------------------------------------------------------------ #

    intents = discord.Intents.default()
    intents.message_content = True

    client = NunchiDiscordClient(intents=intents)

    print(
        f"nunchi-discord starting\n"
        f"  channels   : {sorted(channel_ids)}\n"
        f"  bot_policy : {bot_policy}\n"
        f"  dry_run    : {args.dry_run}\n"
        f"  log        : {log_path}",
        file=sys.stderr,
    )

    client.run(token, log_handler=None)
    return 0
