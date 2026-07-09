"""Telegram Bot API reference adapter for nunchi.

Joins Telegram chats as a gated participant using the Telegram Bot HTTP API
over stdlib urllib (zero extra dependencies). Long-polls getUpdates
(timeout=30 s), runs each inbound text message through the nunchi admission
gate, and delegates non-silent verdicts to a pluggable responder callable.

Obtain a bot token from BotFather on Telegram (send /newbot to @BotFather).

Required env vars:

    NUNCHI_TELEGRAM_TOKEN    Bot token from BotFather
    NUNCHI_TELEGRAM_CHATS    Comma-separated chat IDs to watch (integers;
                             negative for groups/supergroups, positive for DMs)

Optional env vars:

    NUNCHI_TELEGRAM_STATE    Offset persistence path
                             (default: ~/.nunchi/telegram-sync.json)
    NUNCHI_TELEGRAM_LOG      JSONL receipt log path
                             (default: ~/.nunchi/telegram-gate.jsonl)
    NUNCHI_TELEGRAM_AGENT_ID Agent identity (default: bot_<username>)
    NUNCHI_TELEGRAM_HISTORY  Number of recent messages in gate context
                             (default: 20)
    NUNCHI_TELEGRAM_BACKSTOP_MAX_SENDS
                             Send backstop (amplification-loops guard, default
                             ON): max sends per chat per window (default: 5)
    NUNCHI_TELEGRAM_BACKSTOP_WINDOW_SECONDS
                             Send backstop window in seconds (default: 10).
                             When the cap trips, the send is suppressed and the
                             receipt records action='rate-limited'.
    NUNCHI_RESPONDER_MODEL   LLM model for the built-in demo responder;
                             defaults to NUNCHI_CLASSIFIER_MODEL
    OPENROUTER_API_KEY       API key for the demo responder
    NUNCHI_CLASSIFIER_MODEL  Model used by both classifier and demo responder

The responder callback contract:

    respond(trigger: dict, history: list[dict], gate_result: ChannelGateResult)
        -> str | None

``trigger`` and each ``history`` item are dicts with ``content``, ``author``,
``author_kind``, and ``message_id``. Return a string to send, or None to post
nothing (receipt: responder-declined). The built-in demo responder is wired by
default when OPENROUTER_API_KEY and a model are set.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from ._backstop import SendBackstop, backstop_from_env
from ._responder import _demo_responder
from .channel import ChannelGateResult, gate as channel_gate

logger = logging.getLogger("nunchi.adapters.telegram")

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

_DEFAULT_POLL_TIMEOUT = 30  # seconds for getUpdates long-poll
_DEFAULT_HISTORY_LEN = 20
_DEFAULT_STATE_FILE = "~/.nunchi/telegram-sync.json"
_DEFAULT_LOG_FILE = "~/.nunchi/telegram-gate.jsonl"

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds; doubles on each attempt

_TG_API = "https://api.telegram.org"


# --------------------------------------------------------------------------- #
# Telegram HTTP helpers
# --------------------------------------------------------------------------- #


def _tg_call(
    token: str,
    method: str,
    params: dict | None = None,
    *,
    timeout: float = 60.0,
    max_retries: int = _MAX_RETRIES,
    retry_base_delay: float = _RETRY_BASE_DELAY,
) -> dict | list:
    """Call a Telegram Bot API method and return the ``result`` field.

    Uses POST with a JSON body for methods that have parameters; GET otherwise.
    Only 429 and 5xx are retried; all other 4xx abort immediately (mirrors the
    classifier resilience policy — permanent errors must never waste retries).
    On 429, honours ``retry_after`` from the JSON response body first, then the
    ``Retry-After`` HTTP header.
    """
    url = f"{_TG_API}/bot{token}/{method}"
    if params is not None:
        data: bytes | None = json.dumps(params).encode()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    else:
        req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                body = json.loads(raw) if raw.strip() else {}
            if not body.get("ok"):
                raise RuntimeError(f"Telegram {method} returned ok=false: {body}")
            return body.get("result") or {}
        except RuntimeError:
            raise  # application-level errors propagate immediately
        except urllib.error.HTTPError as exc:
            body_bytes = exc.read()
            body_text = body_bytes.decode("utf-8", errors="replace")
            err_msg = f"Telegram HTTP {exc.code} {method}: {body_text[:200]}"
            if exc.code not in (429, 500, 502, 503, 504):
                # Permanent error — abort immediately, do not retry
                raise RuntimeError(err_msg) from exc
            retry_after: float | None = None
            if exc.code == 429:
                # Prefer retry_after from JSON body (Telegram's canonical location)
                try:
                    err_json = json.loads(body_text)
                    ra = err_json.get("parameters", {}).get("retry_after")
                    if ra is not None:
                        retry_after = float(ra)
                except (json.JSONDecodeError, AttributeError, ValueError):
                    pass
                # Fallback: Retry-After header
                if retry_after is None:
                    header_val = exc.headers.get("Retry-After")
                    if header_val:
                        try:
                            retry_after = float(header_val)
                        except ValueError:
                            pass
            last_exc = RuntimeError(err_msg)
            if retry_after is not None:
                logger.debug("429 rate-limited; waiting %.1fs (retry_after)", retry_after)
                time.sleep(retry_after)
                continue  # skip default exponential delay
        except (socket.timeout, urllib.error.URLError, OSError) as exc:
            last_exc = RuntimeError(f"Telegram request failed {method}: {exc}")

        if attempt < max_retries:
            delay = retry_base_delay * (2 ** attempt)
            logger.debug("Transient error; retry %d/%d after %.1fs", attempt + 1, max_retries, delay)
            time.sleep(delay)

    assert last_exc is not None
    raise last_exc


# --------------------------------------------------------------------------- #
# High-level API wrappers
# --------------------------------------------------------------------------- #


def _get_me(token: str) -> dict:
    """GET /getMe — resolve the bot's own identity."""
    result = _tg_call(token, "getMe", timeout=15.0, max_retries=1)
    if not isinstance(result, dict) or not result.get("id"):
        raise RuntimeError(f"getMe returned unexpected result: {result}")
    return result


def _get_updates(
    token: str,
    offset: int | None,
    poll_timeout: int,
) -> list[dict]:
    """POST /getUpdates — long-poll for new updates."""
    params: dict = {
        "timeout": poll_timeout,
        "allowed_updates": ["message"],
    }
    if offset is not None:
        params["offset"] = offset
    # Socket timeout must exceed long-poll timeout
    socket_timeout = float(poll_timeout) + 15.0
    result = _tg_call(token, "getUpdates", params, timeout=socket_timeout, max_retries=2)
    return result if isinstance(result, list) else []


def _send_message(token: str, chat_id: int, text: str) -> int:
    """POST /sendMessage — return the sent message_id."""
    result = _tg_call(token, "sendMessage", {"chat_id": chat_id, "text": text})
    if not isinstance(result, dict):
        raise RuntimeError(f"sendMessage result unexpected: {result}")
    return int(result["message_id"])


# --------------------------------------------------------------------------- #
# Offset (state) persistence
# --------------------------------------------------------------------------- #


def _load_offset(state_path: Path) -> int | None:
    if state_path.exists():
        try:
            obj = json.loads(state_path.read_text())
            val = obj.get("offset")
            return int(val) if val is not None else None
        except (json.JSONDecodeError, OSError, ValueError):
            logger.warning("Could not read offset from %s; starting fresh", state_path)
    return None


def _save_offset(state_path: Path, offset: int) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        state_path.write_text(json.dumps({"offset": offset}))
    except OSError as exc:
        logger.warning("Could not persist offset to %s: %s", state_path, exc)


# --------------------------------------------------------------------------- #
# Receipt logging (JSONL)
# --------------------------------------------------------------------------- #


def _write_receipt(log_path: Path, record: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with log_path.open("a") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError as exc:
        logger.warning("Could not write receipt to %s: %s", log_path, exc)


# --------------------------------------------------------------------------- #
# Core poll loop
# --------------------------------------------------------------------------- #


class TelegramPollLoop:
    """Drives the Telegram getUpdates long-poll loop and gates each message.

    Instantiate directly to inject a custom responder or settings; see
    ``main()`` for the env-var-driven entry point.
    """

    def __init__(
        self,
        *,
        token: str,
        chat_ids: list[int],
        agent_id: str,
        own_user_id: int,
        own_username: str,
        history_len: int,
        state_path: Path,
        log_path: Path,
        responder: Callable[[dict, list[dict], ChannelGateResult], str | None] | None,
        dry_run: bool = False,
        fail_policy: str = "open",
        pinned_rules: str | None = None,
        poll_timeout: int = _DEFAULT_POLL_TIMEOUT,
        backstop: SendBackstop | None = None,
    ) -> None:
        self.token = token
        self.chat_ids = frozenset(chat_ids)
        self.agent_id = agent_id
        self.own_user_id = own_user_id
        self.own_username = own_username
        self.history_len = history_len
        self.state_path = state_path
        self.log_path = log_path
        self.responder = responder
        self.dry_run = dry_run
        self.fail_policy = fail_policy
        self.pinned_rules = pinned_rules
        self.poll_timeout = poll_timeout
        # Per-chat send backstop (amplification-loops guard) — default ON.
        self._backstop = backstop if backstop is not None else SendBackstop()

        # Per-chat in-memory history: chat_id -> list of msg dicts
        self._chat_history: dict[int, list[dict]] = {}

    # ---------------------------------------------------------------------- #
    # Author-kind resolution
    # ---------------------------------------------------------------------- #

    def _author_kind(self, from_user: dict | None) -> str:
        """Map a Telegram ``from`` object to an author_kind string.

        - own bot user_id  -> "self"   (skip as gate trigger)
        - is_bot == True   -> "peer_bot"
        - everything else  -> "human"
        """
        if from_user is None:
            return "human"
        user_id = from_user.get("id")
        if user_id == self.own_user_id:
            return "self"
        if from_user.get("is_bot"):
            return "peer_bot"
        return "human"

    # ---------------------------------------------------------------------- #
    # History management
    # ---------------------------------------------------------------------- #

    def _append_history(self, chat_id: int, msg: dict) -> None:
        bucket = self._chat_history.setdefault(chat_id, [])
        bucket.append(msg)
        if len(bucket) > self.history_len + 10:
            del bucket[: len(bucket) - self.history_len]

    def _get_history(self, chat_id: int) -> list[dict]:
        return list(self._chat_history.get(chat_id, [])[-self.history_len :])

    # ---------------------------------------------------------------------- #
    # Update processing
    # ---------------------------------------------------------------------- #

    def _process_update(self, update: dict) -> None:
        """Process one Telegram update dict."""
        message = update.get("message")
        if not message:
            return  # Ignore non-message updates (edits, polls, etc.)

        chat = message.get("chat") or {}
        chat_id: int | None = chat.get("id")
        if chat_id is None or chat_id not in self.chat_ids:
            return  # Not in the allowlist

        text = (message.get("text") or "").strip()
        if not text:
            return  # Text messages only

        from_user = message.get("from")
        msg_id = str(message.get("message_id", ""))
        date = message.get("date")

        # Prefer username, then first_name, then user_id as author label
        if from_user:
            author = (
                from_user.get("username")
                or from_user.get("first_name")
                or str(from_user.get("id", "unknown"))
            )
        else:
            author = "unknown"

        author_kind = self._author_kind(from_user)

        msg_record = {
            "content": text,
            "author": author,
            "author_kind": author_kind,
            "message_id": msg_id,
            "timestamp": str(date) if date else None,
        }

        # Skip own messages: record in history so future context is correct
        if author_kind == "self":
            self._append_history(chat_id, msg_record)
            return

        # Capture pre-trigger history snapshot
        history_snapshot = self._get_history(chat_id)
        # Append trigger to history so it appears in future context
        self._append_history(chat_id, msg_record)

        self._gate_and_respond(
            chat_id=chat_id,
            trigger_record=msg_record,
            history_snapshot=history_snapshot,
        )

    # ---------------------------------------------------------------------- #
    # Gate and respond
    # ---------------------------------------------------------------------- #

    def _gate_and_respond(
        self,
        chat_id: int,
        trigger_record: dict,
        history_snapshot: list[dict],
    ) -> None:
        t0 = time.monotonic()
        try:
            result: ChannelGateResult = channel_gate(
                trigger_record,
                history_snapshot,
                agent_id=self.agent_id,
                pinned_rules=self.pinned_rules,
                fail_policy=self.fail_policy,  # type: ignore[arg-type]
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Gate error for msg=%s chat=%s: %s",
                trigger_record.get("message_id"),
                chat_id,
                exc,
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            self._receipt(chat_id, trigger_record, len(history_snapshot), None, "error", elapsed_ms, error=str(exc))
            return

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if result.silent:
            logger.debug(
                "PASS (silent) msg=%s chat=%s",
                trigger_record.get("message_id"),
                chat_id,
            )
            self._receipt(chat_id, trigger_record, len(history_snapshot), result, "silent", elapsed_ms)
            return

        if self.dry_run:
            logger.info(
                "[dry-run] verdict=%s msg=%s chat=%s reasons=%s",
                result.verdict,
                trigger_record.get("message_id"),
                chat_id,
                result.reasons[:2],
            )
            self._receipt(chat_id, trigger_record, len(history_snapshot), result, "dry-run", elapsed_ms)
            return

        if self.responder is None:
            logger.info(
                "verdict=%s (no responder) msg=%s chat=%s",
                result.verdict,
                trigger_record.get("message_id"),
                chat_id,
            )
            self._receipt(chat_id, trigger_record, len(history_snapshot), result, "silent", elapsed_ms)
            return

        try:
            reply_text = self.responder(trigger_record, history_snapshot, result)
        except Exception as exc:  # noqa: BLE001
            logger.error("Responder error msg=%s: %s", trigger_record.get("message_id"), exc)
            self._receipt(chat_id, trigger_record, len(history_snapshot), result, "error", elapsed_ms, error=str(exc))
            return

        if reply_text is None:
            logger.debug("Responder declined msg=%s", trigger_record.get("message_id"))
            self._receipt(chat_id, trigger_record, len(history_snapshot), result, "responder-declined", elapsed_ms)
            return

        # Empty-send guard: never post empty/whitespace-only text to the chat.
        if not reply_text.strip():
            logger.info(
                "Responder returned empty text; suppressing send msg=%s chat=%s",
                trigger_record.get("message_id"),
                chat_id,
            )
            self._receipt(chat_id, trigger_record, len(history_snapshot), result, "empty-suppressed", elapsed_ms)
            return

        # Send backstop: sliding-window cap on sends per chat (default ON).
        # A tripped cap suppresses the send — it never queues.
        wait = self._backstop.try_acquire(str(chat_id))
        if wait > 0:
            logger.warning(
                "Send backstop tripped chat=%s (max %d per %.0fs); suppressing send, retry in %.1fs",
                chat_id,
                self._backstop.max_sends,
                self._backstop.window_seconds,
                wait,
            )
            self._receipt(chat_id, trigger_record, len(history_snapshot), result, "rate-limited", elapsed_ms)
            return

        try:
            sent_id = _send_message(self.token, chat_id, reply_text)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "sendMessage error msg=%s chat=%s: %s",
                trigger_record.get("message_id"),
                chat_id,
                exc,
            )
            self._receipt(chat_id, trigger_record, len(history_snapshot), result, "error", elapsed_ms, error=str(exc))
            return

        # Record the sent message in own history
        self._append_history(
            chat_id,
            {
                "content": reply_text,
                "author": self.own_username,
                "author_kind": "self",
                "message_id": str(sent_id),
                "timestamp": None,
            },
        )

        logger.info(
            "spoke verdict=%s msg=%s sent=%s chat=%s",
            result.verdict,
            trigger_record.get("message_id"),
            sent_id,
            chat_id,
        )
        self._receipt(chat_id, trigger_record, len(history_snapshot), result, "spoke", elapsed_ms)

    # ---------------------------------------------------------------------- #
    # Receipt helper
    # ---------------------------------------------------------------------- #

    def _receipt(
        self,
        chat_id: int,
        trigger: dict,
        history_len: int,
        result: ChannelGateResult | None,
        action: str,
        elapsed_ms: int,
        error: str | None = None,
    ) -> None:
        record: dict = {
            "ts": trigger.get("timestamp"),
            "room_id": str(chat_id),
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
        _write_receipt(self.log_path, record)

    # ---------------------------------------------------------------------- #
    # Poll loop
    # ---------------------------------------------------------------------- #

    def poll_once(self, offset: int | None) -> int | None:
        """Call getUpdates once, process all returned updates, return next offset."""
        try:
            updates = _get_updates(self.token, offset, self.poll_timeout)
        except RuntimeError as exc:
            logger.error("getUpdates error: %s", exc)
            return offset

        next_offset = offset
        for update in updates:
            uid = update.get("update_id")
            if uid is not None:
                next_offset = uid + 1
            self._process_update(update)

        return next_offset

    def run(self, *, stop_after_one: bool = False) -> None:
        """Run the poll loop until interrupted.

        ``stop_after_one=True`` processes a single getUpdates batch then returns
        (used by the ``--once`` flag).
        """
        offset = _load_offset(self.state_path)
        logger.info(
            "Starting Telegram poll loop chats=%s agent=%s",
            sorted(self.chat_ids),
            self.agent_id,
        )

        try:
            while True:
                new_offset = self.poll_once(offset)
                if new_offset is not None and new_offset != offset:
                    offset = new_offset
                    _save_offset(self.state_path, offset)
                if stop_after_one:
                    break
        except KeyboardInterrupt:
            logger.info("Interrupted; persisting offset and exiting.")
            if offset is not None:
                _save_offset(self.state_path, offset)


# --------------------------------------------------------------------------- #
# Env-var config loader
# --------------------------------------------------------------------------- #


def _require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(f"Required environment variable {name} is not set.")
    return val


def _build_loop_from_env(dry_run: bool = False) -> TelegramPollLoop:
    """Construct a TelegramPollLoop from environment variables."""
    token = _require_env("NUNCHI_TELEGRAM_TOKEN")
    chats_raw = _require_env("NUNCHI_TELEGRAM_CHATS")
    try:
        chat_ids = [int(c.strip()) for c in chats_raw.split(",") if c.strip()]
    except ValueError as exc:
        raise RuntimeError(
            f"NUNCHI_TELEGRAM_CHATS must contain comma-separated integers: {exc}"
        ) from exc
    if not chat_ids:
        raise RuntimeError("NUNCHI_TELEGRAM_CHATS must contain at least one chat ID.")

    state_path = Path(os.environ.get("NUNCHI_TELEGRAM_STATE", _DEFAULT_STATE_FILE)).expanduser()
    log_path = Path(os.environ.get("NUNCHI_TELEGRAM_LOG", _DEFAULT_LOG_FILE)).expanduser()

    history_len_raw = os.environ.get("NUNCHI_TELEGRAM_HISTORY", str(_DEFAULT_HISTORY_LEN))
    try:
        history_len = int(history_len_raw)
    except ValueError:
        history_len = _DEFAULT_HISTORY_LEN

    # Resolve own identity via getMe
    me = _get_me(token)
    own_user_id: int = me["id"]
    own_username: str = me.get("username") or me.get("first_name") or f"bot_{own_user_id}"

    agent_id_raw = os.environ.get("NUNCHI_TELEGRAM_AGENT_ID", "").strip()
    agent_id = agent_id_raw if agent_id_raw else f"bot_{own_username}"

    # Responder setup
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("NUNCHI_CLASSIFIER_API_KEY", "")
    responder_model = (
        os.environ.get("NUNCHI_RESPONDER_MODEL")
        or os.environ.get("NUNCHI_CLASSIFIER_MODEL")
        or ""
    )

    responder: Callable[[dict, list[dict], ChannelGateResult], str | None] | None = None
    if api_key and responder_model:
        base_url = (
            os.environ.get("NUNCHI_CLASSIFIER_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://openrouter.ai/api/v1"
        )

        def _responder(
            trigger: dict,
            history: list[dict],
            gate_result: ChannelGateResult,
        ) -> str | None:
            return _demo_responder(
                trigger,
                history,
                gate_result,
                agent_id=agent_id,
                model=responder_model,
                api_key=api_key,
                base_url=base_url,
            )

        responder = _responder
    else:
        logger.info(
            "Demo responder disabled: set OPENROUTER_API_KEY and NUNCHI_RESPONDER_MODEL "
            "(or NUNCHI_CLASSIFIER_MODEL) to enable it."
        )

    return TelegramPollLoop(
        token=token,
        chat_ids=chat_ids,
        agent_id=agent_id,
        own_user_id=own_user_id,
        own_username=own_username,
        history_len=history_len,
        state_path=state_path,
        log_path=log_path,
        responder=responder,
        dry_run=dry_run,
        backstop=backstop_from_env("NUNCHI_TELEGRAM"),
    )


# --------------------------------------------------------------------------- #
# Console script entry point
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``nunchi-telegram`` console script.

    Usage::

        nunchi-telegram [--once] [--dry-run]

    Flags:
        --once      Process one getUpdates batch then exit (for testing/cron).
        --dry-run   Run the gate but never send; receipts record 'dry-run'.
    """
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    parser = argparse.ArgumentParser(
        prog="nunchi-telegram",
        description=(
            "nunchi-telegram: join Telegram chats as a gated participant. "
            "Reads NUNCHI_TELEGRAM_TOKEN and NUNCHI_TELEGRAM_CHATS from env."
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process one getUpdates batch then exit (for testing or cron).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the gate but never send; receipts record action='dry-run'.",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    missing = []
    for var in ("NUNCHI_TELEGRAM_TOKEN", "NUNCHI_TELEGRAM_CHATS"):
        if not os.environ.get(var, "").strip():
            missing.append(var)
    if missing:
        print(
            "nunchi-telegram: required environment variables not set:\n"
            + "\n".join(f"  {v}" for v in missing)
            + "\n\nSee the module docstring for setup instructions.",
            file=sys.stderr,
        )
        return 1

    try:
        loop = _build_loop_from_env(dry_run=args.dry_run)
    except RuntimeError as exc:
        print(f"nunchi-telegram: configuration error: {exc}", file=sys.stderr)
        return 1

    print(
        f"nunchi-telegram starting\n"
        f"  chats      : {sorted(loop.chat_ids)}\n"
        f"  agent_id   : {loop.agent_id}\n"
        f"  dry_run    : {loop.dry_run}\n"
        f"  state      : {loop.state_path}\n"
        f"  log        : {loop.log_path}",
        file=sys.stderr,
    )

    loop.run(stop_after_one=args.once)
    return 0
