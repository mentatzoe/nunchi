"""Matrix reference adapter for nunchi.

Joins Matrix rooms as a gated participant: long-polls /sync, runs each inbound
message through the nunchi admission gate, and delegates non-silent verdicts to
a pluggable responder callable.

Zero runtime dependencies — stdlib only (urllib, json, os, time, etc.).
Encrypted rooms (m.room.encrypted) are skipped with a one-time per-room warning.

Obtain a Matrix access token with a curl one-liner (replace placeholders):

    curl -XPOST 'https://HOMESERVER/_matrix/client/v3/login' \\
         -H 'Content-Type: application/json' \\
         -d '{"type":"m.login.password","identifier":{"type":"m.id.user","user":"@BOT:HOMESERVER"},"password":"SECRET"}'

The JSON response contains ``access_token``; export it as NUNCHI_MATRIX_TOKEN.
Alternatively call ``login(homeserver, user, password)`` from this module.

Required env vars:

    NUNCHI_MATRIX_TOKEN       Matrix access token
    NUNCHI_MATRIX_HOMESERVER  Base URL of the homeserver, e.g. https://matrix.example.com
    NUNCHI_MATRIX_ROOMS       Comma-separated list of room IDs to watch, e.g.
                              !abc:example.com,!xyz:example.com

Optional env vars:

    NUNCHI_MATRIX_STATE       Path for since-token persistence
                              (default: ~/.nunchi/matrix-sync.json)
    NUNCHI_MATRIX_LOG         Path for per-event JSONL receipts
                              (default: ~/.nunchi/matrix-gate.jsonl)
    NUNCHI_MATRIX_AGENT_ID    Agent identity (default: bot_<localpart-of-user-id>)
    NUNCHI_MATRIX_PEER_BOTS   Comma-separated Matrix user IDs (or @prefix prefixes)
                              treated as peer_bot, not human
    NUNCHI_MATRIX_HISTORY     Number of recent messages to include in gate context
                              (default: 10)
    NUNCHI_RESPONDER_MODEL    LLM model for the built-in demo responder; defaults
                              to NUNCHI_CLASSIFIER_MODEL
    OPENROUTER_API_KEY        API key for the built-in demo responder
    NUNCHI_CLASSIFIER_MODEL   Model used by both classifier and demo responder

The responder callback contract:

    respond(trigger: dict, history: list[dict], gate_result: ChannelGateResult) -> str | None

``trigger`` and each ``history`` item are dicts with ``content``, ``author``,
``author_kind``, and ``message_id``. Return a string to post into the room, or
None to post nothing (the receipt will record ``responder-declined``). The
built-in demo responder is wired by default; pass ``responder=`` to ``main()``
or construct ``MatrixSyncLoop`` directly to inject your own.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from ._responder import _demo_responder
from .channel import ChannelGateResult, gate as channel_gate

logger = logging.getLogger("nunchi.adapters.matrix")

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

_DEFAULT_SYNC_TIMEOUT_MS = 30_000
_DEFAULT_HISTORY_LEN = 20
_DEFAULT_STATE_FILE = "~/.nunchi/matrix-sync.json"
_DEFAULT_LOG_FILE = "~/.nunchi/matrix-gate.jsonl"

# Transient HTTP status codes that trigger a retry.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds; doubles on each attempt


# --------------------------------------------------------------------------- #
# Low-level Matrix HTTP helpers
# --------------------------------------------------------------------------- #


def _make_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _http(
    method: str,
    url: str,
    *,
    token: str,
    body: dict | None = None,
    timeout: float = 60.0,
    max_retries: int = _MAX_RETRIES,
    retry_base_delay: float = _RETRY_BASE_DELAY,
) -> dict:
    """Perform one Matrix CS-API call with retry/backoff.

    Only 429 and 5xx are retried; all other 4xx abort immediately (permanent
    errors must never waste tokens or time by retrying — mirrors the classifier
    resilience policy in classifiers.py).
    """
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=_make_headers(token))

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            err_msg = f"Matrix HTTP {exc.code} {url}: {details[:200]}"
            if exc.code not in _RETRYABLE_STATUS:
                raise RuntimeError(err_msg) from exc
            last_exc = RuntimeError(err_msg)
            if exc.code == 429:
                # Honour Retry-After when present
                retry_after = exc.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        delay = retry_base_delay * (2 ** attempt)
                    logger.debug("429 rate-limited; waiting %.1fs", delay)
                    time.sleep(delay)
                    continue
        except (socket.timeout, urllib.error.URLError, OSError) as exc:
            last_exc = RuntimeError(f"Matrix request failed {url}: {exc}")

        if attempt < max_retries:
            delay = retry_base_delay * (2 ** attempt)
            logger.debug("Transient error; retry %d/%d after %.1fs", attempt + 1, max_retries, delay)
            time.sleep(delay)

    assert last_exc is not None
    raise last_exc


# --------------------------------------------------------------------------- #
# Public helper: login (token acquisition)
# --------------------------------------------------------------------------- #


def login(homeserver: str, user: str, password: str) -> str:
    """Obtain a Matrix access token via password login.

    Returns the ``access_token`` string. Store it in NUNCHI_MATRIX_TOKEN.
    For production deployments prefer obtaining the token with the curl
    one-liner documented at the top of this module and exporting it as an env
    var rather than embedding credentials in code.
    """
    url = f"{homeserver.rstrip('/')}/_matrix/client/v3/login"
    payload = {
        "type": "m.login.password",
        "identifier": {"type": "m.id.user", "user": user},
        "password": password,
    }
    # login does not need an existing token; use a minimal urllib call
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Matrix login failed HTTP {exc.code}: {details}") from exc
    token = body.get("access_token")
    if not token:
        raise RuntimeError(f"Matrix login response did not include access_token: {body}")
    return token


# --------------------------------------------------------------------------- #
# Since-token persistence
# --------------------------------------------------------------------------- #


def _load_since(state_path: Path) -> str | None:
    if state_path.exists():
        try:
            obj = json.loads(state_path.read_text())
            return obj.get("since") or None
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read since-token from %s; starting fresh", state_path)
    return None


def _save_since(state_path: Path, since: str) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        state_path.write_text(json.dumps({"since": since}))
    except OSError as exc:
        logger.warning("Could not persist since-token to %s: %s", state_path, exc)


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
# Peer-bot detection
# --------------------------------------------------------------------------- #


def _is_peer_bot(sender: str, peer_bot_specs: list[str]) -> bool:
    """Return True if *sender* matches any peer-bot spec (exact id or @prefix)."""
    for spec in peer_bot_specs:
        spec = spec.strip()
        if not spec:
            continue
        if spec.endswith("*"):
            # glob-style prefix match
            if fnmatch.fnmatch(sender, spec):
                return True
        elif spec == sender:
            return True
    return False


# --------------------------------------------------------------------------- #
# /sync long-poll
# --------------------------------------------------------------------------- #


def _sync_once(
    homeserver: str,
    token: str,
    since: str | None,
    timeout_ms: int = _DEFAULT_SYNC_TIMEOUT_MS,
) -> dict:
    """Call GET /_matrix/client/v3/sync and return the parsed JSON body.

    Uses a longer socket timeout than the long-poll timeout to give the server
    room to respond before we declare the connection dead.
    """
    params: dict[str, Any] = {"timeout": timeout_ms}
    if since:
        params["since"] = since
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{homeserver.rstrip('/')}/_matrix/client/v3/sync?{qs}"
    socket_timeout = (timeout_ms / 1000) + 15
    return _http("GET", url, token=token, timeout=socket_timeout, max_retries=2)


# --------------------------------------------------------------------------- #
# Message send
# --------------------------------------------------------------------------- #

_TXN_COUNTER = 0


def _next_txn_id() -> str:
    global _TXN_COUNTER
    _TXN_COUNTER += 1
    return f"nunchi-{int(time.monotonic() * 1000)}-{_TXN_COUNTER}"


def _send_message(homeserver: str, token: str, room_id: str, text: str) -> str:
    """PUT /_matrix/client/v3/rooms/{roomId}/send/m.room.message/{txnId}.

    Returns the event_id of the sent event.
    """
    txn_id = _next_txn_id()
    encoded_room = urllib.parse.quote(room_id, safe="")
    url = (
        f"{homeserver.rstrip('/')}/_matrix/client/v3/rooms/"
        f"{encoded_room}/send/m.room.message/{txn_id}"
    )
    body = {"msgtype": "m.text", "body": text}
    resp = _http("PUT", url, token=token, body=body)
    return resp.get("event_id", txn_id)


# --------------------------------------------------------------------------- #
# Resolve own user_id
# --------------------------------------------------------------------------- #


def _whoami(homeserver: str, token: str) -> str:
    """GET /_matrix/client/v3/account/whoami -> user_id string."""
    url = f"{homeserver.rstrip('/')}/_matrix/client/v3/account/whoami"
    resp = _http("GET", url, token=token, timeout=15.0, max_retries=1)
    user_id = resp.get("user_id")
    if not user_id:
        raise RuntimeError(f"Could not determine own user_id from whoami: {resp}")
    return user_id


# _demo_responder is imported from ._responder (shared with telegram + discord).


# --------------------------------------------------------------------------- #
# Core sync loop
# --------------------------------------------------------------------------- #


class MatrixSyncLoop:
    """Drives the Matrix /sync loop and gates each message through nunchi.

    Instantiate directly to inject a custom responder or settings; see
    ``main()`` for the env-var-driven entry point.
    """

    def __init__(
        self,
        *,
        homeserver: str,
        token: str,
        room_ids: list[str],
        agent_id: str,
        own_user_id: str,
        peer_bot_specs: list[str],
        history_len: int,
        state_path: Path,
        log_path: Path,
        responder: Callable[[dict, list[dict], ChannelGateResult], str | None] | None,
        dry_run: bool = False,
        fail_policy: str = "open",
        pinned_rules: str | None = None,
        sync_timeout_ms: int = _DEFAULT_SYNC_TIMEOUT_MS,
    ) -> None:
        self.homeserver = homeserver
        self.token = token
        self.room_ids = set(room_ids)
        self.agent_id = agent_id
        self.own_user_id = own_user_id
        self.peer_bot_specs = peer_bot_specs
        self.history_len = history_len
        self.state_path = state_path
        self.log_path = log_path
        self.responder = responder
        self.dry_run = dry_run
        self.fail_policy = fail_policy
        self.pinned_rules = pinned_rules
        self.sync_timeout_ms = sync_timeout_ms

        # Per-room in-memory history: list of dicts with content/author/author_kind/message_id
        self._room_history: dict[str, list[dict]] = {}
        # Rooms for which we have already emitted the encrypted-room warning
        self._encrypted_warned: set[str] = set()
        # True after the very first /sync returns; events in that first batch
        # are skipped (they are already-delivered history, not new messages)
        self._initial_sync_done = False

    # ---------------------------------------------------------------------- #
    # Author-kind resolution
    # ---------------------------------------------------------------------- #

    def _author_kind(self, sender: str) -> str:
        if sender == self.own_user_id:
            return "self"
        if _is_peer_bot(sender, self.peer_bot_specs):
            return "peer_bot"
        return "human"

    # ---------------------------------------------------------------------- #
    # History management
    # ---------------------------------------------------------------------- #

    def _append_history(self, room_id: str, msg: dict) -> None:
        bucket = self._room_history.setdefault(room_id, [])
        bucket.append(msg)
        # Keep only the last N+1 to avoid unbounded growth
        if len(bucket) > self.history_len + 10:
            del bucket[: len(bucket) - self.history_len]

    def _get_history(self, room_id: str) -> list[dict]:
        return list(self._room_history.get(room_id, [])[-self.history_len :])

    # ---------------------------------------------------------------------- #
    # Process one room's timeline from a /sync batch
    # ---------------------------------------------------------------------- #

    def _process_room_timeline(self, room_id: str, timeline: dict) -> None:
        events = timeline.get("events") or []
        for event in events:
            etype = event.get("type", "")
            sender = event.get("sender", "")
            event_id = event.get("event_id", "")
            origin_ts = event.get("origin_server_ts")

            # Encrypted room: log-and-skip with one-time warning per room
            if etype == "m.room.encrypted":
                if room_id not in self._encrypted_warned:
                    logger.warning(
                        "Room %s uses encryption; nunchi-matrix only supports unencrypted rooms. "
                        "Skipping all events in this room.",
                        room_id,
                    )
                    self._encrypted_warned.add(room_id)
                continue

            # Only handle text/notice messages
            if etype != "m.room.message":
                continue
            content_block = event.get("content") or {}
            msgtype = content_block.get("msgtype", "")
            if msgtype not in ("m.text", "m.notice"):
                continue

            body_text = content_block.get("body", "")
            if not body_text.strip():
                continue

            author_kind = self._author_kind(sender)

            # Record in history regardless of whether we respond
            msg_record = {
                "content": body_text,
                "author": sender,
                "author_kind": author_kind,
                "message_id": event_id,
                "timestamp": str(origin_ts) if origin_ts else None,
            }

            # Skip own messages (record in history so future context is correct)
            if sender == self.own_user_id:
                self._append_history(room_id, msg_record)
                continue

            # Capture pre-event history (before appending the trigger)
            history_snapshot = self._get_history(room_id)

            # Now append trigger to history so it appears in future context
            self._append_history(room_id, msg_record)

            # Skip processing during initial sync (events already delivered)
            if not self._initial_sync_done:
                continue

            self._gate_and_respond(
                room_id=room_id,
                trigger_record=msg_record,
                history_snapshot=history_snapshot,
            )

    # ---------------------------------------------------------------------- #
    # Gate and respond
    # ---------------------------------------------------------------------- #

    def _gate_and_respond(
        self,
        room_id: str,
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
            logger.error("Gate error for %s in %s: %s", trigger_record.get("message_id"), room_id, exc)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            self._receipt(
                room_id=room_id,
                trigger=trigger_record,
                history_len=len(history_snapshot),
                result=None,
                action="error",
                elapsed_ms=elapsed_ms,
                error=str(exc),
            )
            return

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if result.silent:
            logger.debug(
                "PASS (silent) event=%s room=%s",
                trigger_record.get("message_id"),
                room_id,
            )
            self._receipt(room_id, trigger_record, len(history_snapshot), result, "silent", elapsed_ms)
            return

        # Non-silent verdict — invoke responder
        if self.dry_run:
            logger.info(
                "[dry-run] verdict=%s event=%s room=%s reasons=%s",
                result.verdict,
                trigger_record.get("message_id"),
                room_id,
                result.reasons[:2],
            )
            self._receipt(room_id, trigger_record, len(history_snapshot), result, "dry-run", elapsed_ms)
            return

        if self.responder is None:
            logger.info(
                "verdict=%s (no responder) event=%s room=%s",
                result.verdict,
                trigger_record.get("message_id"),
                room_id,
            )
            self._receipt(room_id, trigger_record, len(history_snapshot), result, "silent", elapsed_ms)
            return

        try:
            reply_text = self.responder(trigger_record, history_snapshot, result)
        except Exception as exc:  # noqa: BLE001
            logger.error("Responder error event=%s: %s", trigger_record.get("message_id"), exc)
            self._receipt(room_id, trigger_record, len(history_snapshot), result, "error", elapsed_ms, error=str(exc))
            return

        if reply_text is None:
            logger.debug("Responder declined event=%s", trigger_record.get("message_id"))
            self._receipt(room_id, trigger_record, len(history_snapshot), result, "responder-declined", elapsed_ms)
            return

        try:
            sent_event_id = _send_message(self.homeserver, self.token, room_id, reply_text)
        except Exception as exc:  # noqa: BLE001
            logger.error("Send error event=%s room=%s: %s", trigger_record.get("message_id"), room_id, exc)
            self._receipt(room_id, trigger_record, len(history_snapshot), result, "error", elapsed_ms, error=str(exc))
            return

        # Record the sent message in own history
        self._append_history(
            room_id,
            {
                "content": reply_text,
                "author": self.own_user_id,
                "author_kind": "self",
                "message_id": sent_event_id,
                "timestamp": None,
            },
        )

        logger.info(
            "spoke verdict=%s event=%s sent=%s room=%s",
            result.verdict,
            trigger_record.get("message_id"),
            sent_event_id,
            room_id,
        )
        self._receipt(room_id, trigger_record, len(history_snapshot), result, "spoke", elapsed_ms)

    # ---------------------------------------------------------------------- #
    # Receipt helper
    # ---------------------------------------------------------------------- #

    def _receipt(
        self,
        room_id: str,
        trigger: dict,
        history_len: int,
        result: ChannelGateResult | None,
        action: str,
        elapsed_ms: int,
        error: str | None = None,
    ) -> None:
        record: dict = {
            "ts": trigger.get("timestamp"),
            "room_id": room_id,
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
    # Main loop
    # ---------------------------------------------------------------------- #

    def run_once(self, since: str | None) -> str | None:
        """Run one /sync batch. Returns the new since token (or None on error)."""
        try:
            batch = _sync_once(self.homeserver, self.token, since, self.sync_timeout_ms)
        except RuntimeError as exc:
            logger.error("Sync error: %s", exc)
            return since

        new_since = batch.get("next_batch")
        rooms_data = batch.get("rooms", {})
        join_data = rooms_data.get("join") or {}

        for room_id, room_data in join_data.items():
            if room_id not in self.room_ids:
                continue
            timeline = room_data.get("timeline") or {}
            self._process_room_timeline(room_id, timeline)

        # Mark initial sync done only after processing all rooms in first batch
        if not self._initial_sync_done:
            self._initial_sync_done = True

        return new_since or since

    def run(self, *, stop_after_one: bool = False) -> None:
        """Run the sync loop until interrupted.

        ``stop_after_one=True`` processes a single /sync batch then returns
        (used by ``--once`` flag).
        """
        since = _load_since(self.state_path)
        logger.info(
            "Starting Matrix sync loop homeserver=%s rooms=%s agent=%s",
            self.homeserver,
            sorted(self.room_ids),
            self.agent_id,
        )

        try:
            while True:
                new_since = self.run_once(since)
                if new_since and new_since != since:
                    since = new_since
                    _save_since(self.state_path, since)
                if stop_after_one:
                    break
        except KeyboardInterrupt:
            logger.info("Interrupted; persisting since-token and exiting.")
            if since:
                _save_since(self.state_path, since)


# --------------------------------------------------------------------------- #
# Env-var config loader
# --------------------------------------------------------------------------- #


def _require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(f"Required environment variable {name} is not set.")
    return val


def _build_loop_from_env(dry_run: bool = False) -> MatrixSyncLoop:
    """Construct a MatrixSyncLoop from environment variables."""
    homeserver = _require_env("NUNCHI_MATRIX_HOMESERVER")
    token = _require_env("NUNCHI_MATRIX_TOKEN")
    rooms_raw = _require_env("NUNCHI_MATRIX_ROOMS")
    room_ids = [r.strip() for r in rooms_raw.split(",") if r.strip()]
    if not room_ids:
        raise RuntimeError("NUNCHI_MATRIX_ROOMS must contain at least one room ID.")

    state_path = Path(os.environ.get("NUNCHI_MATRIX_STATE", _DEFAULT_STATE_FILE)).expanduser()
    log_path = Path(os.environ.get("NUNCHI_MATRIX_LOG", _DEFAULT_LOG_FILE)).expanduser()

    peer_bot_specs_raw = os.environ.get("NUNCHI_MATRIX_PEER_BOTS", "")
    peer_bot_specs = [s.strip() for s in peer_bot_specs_raw.split(",") if s.strip()]

    history_len_raw = os.environ.get("NUNCHI_MATRIX_HISTORY", str(_DEFAULT_HISTORY_LEN))
    try:
        history_len = int(history_len_raw)
    except ValueError:
        history_len = _DEFAULT_HISTORY_LEN

    # Resolve own user_id
    own_user_id = _whoami(homeserver, token)

    # Derive agent_id from user_id localpart if not explicitly set
    agent_id_raw = os.environ.get("NUNCHI_MATRIX_AGENT_ID", "").strip()
    if not agent_id_raw:
        # @localpart:server -> bot_localpart
        if own_user_id.startswith("@") and ":" in own_user_id:
            localpart = own_user_id[1:].split(":")[0]
        else:
            localpart = own_user_id
        agent_id = f"bot_{localpart}"
    else:
        agent_id = agent_id_raw

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

    return MatrixSyncLoop(
        homeserver=homeserver,
        token=token,
        room_ids=room_ids,
        agent_id=agent_id,
        own_user_id=own_user_id,
        peer_bot_specs=peer_bot_specs,
        history_len=history_len,
        state_path=state_path,
        log_path=log_path,
        responder=responder,
        dry_run=dry_run,
    )


# --------------------------------------------------------------------------- #
# Console script entry point
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``nunchi-matrix`` console script.

    Usage::

        nunchi-matrix [--once] [--dry-run]

    Flags:
        --once      Process one /sync batch then exit (useful for testing/cron).
        --dry-run   Run the gate but never send; receipts record 'dry-run'.
    """
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    parser = argparse.ArgumentParser(
        prog="nunchi-matrix",
        description=(
            "nunchi-matrix: join Matrix rooms as a gated participant. "
            "Reads NUNCHI_MATRIX_TOKEN, NUNCHI_MATRIX_HOMESERVER, NUNCHI_MATRIX_ROOMS from env."
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process one /sync batch then exit (for testing or cron).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the gate but never send; receipts record action='dry-run'.",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    # Validate environment before touching the network
    missing = []
    for var in ("NUNCHI_MATRIX_TOKEN", "NUNCHI_MATRIX_HOMESERVER", "NUNCHI_MATRIX_ROOMS"):
        if not os.environ.get(var, "").strip():
            missing.append(var)
    if missing:
        print(
            "nunchi-matrix: required environment variables not set:\n"
            + "\n".join(f"  {v}" for v in missing)
            + "\n\nSee the module docstring for setup instructions.",
            file=sys.stderr,
        )
        return 1

    try:
        loop = _build_loop_from_env(dry_run=args.dry_run)
    except RuntimeError as exc:
        print(f"nunchi-matrix: configuration error: {exc}", file=sys.stderr)
        return 1

    print(
        f"nunchi-matrix starting\n"
        f"  homeserver : {os.environ.get('NUNCHI_MATRIX_HOMESERVER')}\n"
        f"  rooms      : {', '.join(sorted(loop.room_ids))}\n"
        f"  agent_id   : {loop.agent_id}\n"
        f"  own_user   : {loop.own_user_id}\n"
        f"  dry_run    : {loop.dry_run}\n"
        f"  state      : {loop.state_path}\n"
        f"  log        : {loop.log_path}",
        file=sys.stderr,
    )

    loop.run(stop_after_one=args.once)
    return 0
