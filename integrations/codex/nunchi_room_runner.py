#!/usr/bin/env python3
"""Nunchi room runner for Codex: the agent's ear on a Discord room.

Codex CLI is pull-only as an MCP client — it never reacts to server
notifications on its own. This long-running process is the missing consumer:
it subscribes to the nunchi-mcp-discord transport's streamable-HTTP SSE
stream, runs every room message through the nunchi admission gate
(``nunchi-channel``), and wakes Codex (``codex exec``) only for admitted
turns (SPEAK / ACK / ASK).

Verdict routing
---------------
PASS is a hard stop: the runner writes a receipt and does nothing else. A
suppressed turn costs one gate call and zero frontier tokens — that is the
whole point. SPEAK / ACK / ASK wake Codex with the verdict, the trigger, and
the recent history window; Codex composes (or declines to compose) the turn
and sends it via the transport's ``send_message`` / ``reply_message`` tools.
The gate decides admission, never composition.

Gate-failure policy: fail-CLOSED by default
-------------------------------------------
Deliberately the OPPOSITE of the Claude Code inbound hook. That hook is
fail-open because a broken gate must never silence an operator typing at
their own terminal. Here the input is an unattended firehose of room
messages: if the gate goes down and the runner failed open, EVERY message in
every watched channel would trigger a frontier ``codex exec`` call — a gate
outage must not turn into a frontier-call storm. So on gate error, timeout,
or malformed output the runner does NOT wake and writes a loud
``no-wake-gate-error`` receipt. Set ``NUNCHI_RUNNER_FAIL_POLICY=open`` to
degrade to waking instead (the wake prompt is marked degraded).

Wake serialization
------------------
One wake at a time. The runner is single-threaded and processes events
strictly in stream order, so a wake (up to ``NUNCHI_RUNNER_WAKE_TIMEOUT``
seconds) blocks the consume loop; triggers arriving mid-wake queue in the
TCP stream / the transport's bounded notification queue and are gated after
the wake returns, against the then-current history. The transport drops the
oldest queued notification when its bounded queue overflows, so a long wake
degrades to missing the oldest backlog, never to unbounded memory.

Environment variables
---------------------
NUNCHI_TRANSPORT_URL          Streamable-HTTP MCP endpoint of the transport
                              (default: ``http://127.0.0.1:3993/mcp``).
NUNCHI_RUNNER_SELF_ID         Discord user id of the runner's own bot; matching
                              authors are skipped (belt and braces — the
                              transport already drops its own bot's messages).
NUNCHI_RUNNER_CHANNELS        Comma-separated channel ids to watch (empty = all).
NUNCHI_RUNNER_HISTORY_WINDOW  Rolling per-channel history size (default: 20).
NUNCHI_RUNNER_AGENT_ID        Agent identifier in the nunchi payload (default: ``agent``).
NUNCHI_RUNNER_MENTION_ID      Optional @mention handle for the agent.
NUNCHI_CHANNEL_BIN            Path or name of the nunchi-channel binary
                              (default: located via ``shutil.which("nunchi-channel")``).
NUNCHI_RUNNER_GATE_TIMEOUT    Gate subprocess timeout in seconds (default: 30).
NUNCHI_RUNNER_CODEX_BIN       Codex binary for wakes (default: ``codex``).
NUNCHI_RUNNER_CODEX_ARGS      Extra args for ``codex exec``, shell-split.
NUNCHI_RUNNER_WAKE_TIMEOUT    Wake subprocess timeout in seconds (default: 300).
NUNCHI_RUNNER_FAIL_POLICY     ``closed`` (default) | ``open`` — see above.
NUNCHI_RUNNER_LOG             Receipt JSONL path
                              (default: ``~/.nunchi/codex-runner-receipts.jsonl``).

Receipts never contain tokens, keys, or message content.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

logger = logging.getLogger("nunchi.integrations.codex.room_runner")

NOTIFICATION_METHOD = "notifications/discord/message"

_DEFAULT_TRANSPORT_URL = "http://127.0.0.1:3993/mcp"
_DEFAULT_HISTORY_WINDOW = 20
_DEFAULT_GATE_TIMEOUT = 30.0
_DEFAULT_WAKE_TIMEOUT = 300.0
_HTTP_TIMEOUT = 10.0  # POST handshake calls
_STREAM_READ_TIMEOUT = 900.0  # idle SSE read; expiry just triggers a clean reconnect
_BACKOFF_INITIAL = 1.0
_BACKOFF_CAP = 60.0

# Shape guidance per admitted verdict (mirrors RUN_SHAPE in
# src/nunchi/adapters/channel.py — guidance only, never composed prose).
_WAKE_SHAPE = {
    "SPEAK": "a full participant turn (1-3 short paragraphs of plain prose)",
    "ASK": "exactly one blocking clarifying question",
    "ACK": "a minimal acknowledgment (an emoji or a single short sentence)",
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunnerConfig:
    transport_url: str = _DEFAULT_TRANSPORT_URL
    self_id: str | None = None
    channels: frozenset[str] = frozenset()
    history_window: int = _DEFAULT_HISTORY_WINDOW
    agent_id: str = "agent"
    mention_id: str | None = None
    channel_bin: str | None = None
    gate_timeout: float = _DEFAULT_GATE_TIMEOUT
    codex_bin: str = "codex"
    codex_extra_args: tuple[str, ...] = ()
    wake_timeout: float = _DEFAULT_WAKE_TIMEOUT
    fail_policy: str = "closed"  # closed | open
    log_path: Path = field(
        default_factory=lambda: Path.home() / ".nunchi" / "codex-runner-receipts.jsonl"
    )

    @classmethod
    def from_env(cls, environ=os.environ) -> "RunnerConfig":
        channels = frozenset(
            c.strip()
            for c in (environ.get("NUNCHI_RUNNER_CHANNELS", "") or "").split(",")
            if c.strip()
        )
        return cls(
            transport_url=environ.get("NUNCHI_TRANSPORT_URL", _DEFAULT_TRANSPORT_URL),
            self_id=environ.get("NUNCHI_RUNNER_SELF_ID") or None,
            channels=channels,
            history_window=int(
                environ.get("NUNCHI_RUNNER_HISTORY_WINDOW", str(_DEFAULT_HISTORY_WINDOW))
            ),
            agent_id=environ.get("NUNCHI_RUNNER_AGENT_ID", "agent"),
            mention_id=environ.get("NUNCHI_RUNNER_MENTION_ID") or None,
            channel_bin=environ.get("NUNCHI_CHANNEL_BIN") or shutil.which("nunchi-channel"),
            gate_timeout=float(environ.get("NUNCHI_RUNNER_GATE_TIMEOUT", str(_DEFAULT_GATE_TIMEOUT))),
            codex_bin=environ.get("NUNCHI_RUNNER_CODEX_BIN", "codex"),
            codex_extra_args=tuple(shlex.split(environ.get("NUNCHI_RUNNER_CODEX_ARGS", ""))),
            wake_timeout=float(environ.get("NUNCHI_RUNNER_WAKE_TIMEOUT", str(_DEFAULT_WAKE_TIMEOUT))),
            fail_policy=environ.get("NUNCHI_RUNNER_FAIL_POLICY", "closed").strip().lower(),
            log_path=Path(
                environ.get(
                    "NUNCHI_RUNNER_LOG",
                    str(Path.home() / ".nunchi" / "codex-runner-receipts.jsonl"),
                )
            ),
        )


# ---------------------------------------------------------------------------
# SSE parsing
# ---------------------------------------------------------------------------


def iter_sse_data(lines: Iterable[str]) -> Iterator[str]:
    """Yield the ``data`` payload of each SSE event from an iterable of lines.

    Handles multi-line ``data:`` fields (joined with newlines per the SSE
    spec) and ignores every other field (``event:``, ``id:``, ``retry:``,
    ``:`` comments). An event is emitted at each blank-line boundary.
    """
    data_lines: list[str] = []
    for raw in lines:
        line = raw.rstrip("\r\n")
        if line == "":
            if data_lines:
                yield "\n".join(data_lines)
                data_lines = []
            continue
        if line.startswith(":"):
            continue
        field_name, _, value = line.partition(":")
        if field_name != "data":
            continue
        data_lines.append(value.removeprefix(" "))
    if data_lines:  # stream ended without a trailing blank line
        yield "\n".join(data_lines)


# ---------------------------------------------------------------------------
# Streamable-HTTP MCP client (raw, stdlib urllib only)
# ---------------------------------------------------------------------------


class TransportClient:
    """Minimal streamable-HTTP MCP client: handshake + SSE notification stream."""

    def __init__(self, url: str, *, http_timeout: float = _HTTP_TIMEOUT) -> None:
        self.url = url.rstrip("/")
        self.http_timeout = http_timeout
        self.session_id: str | None = None

    def _post(self, body: dict, *, with_session: bool) -> "urllib.request.http.client.HTTPResponse":
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if with_session and self.session_id:
            headers["mcp-session-id"] = self.session_id
        req = urllib.request.Request(
            self.url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers
        )
        return urllib.request.urlopen(req, timeout=self.http_timeout)

    def initialize(self) -> str:
        """Run the initialize / notifications-initialized handshake.

        Returns the ``mcp-session-id`` issued by the server.
        """
        init = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "nunchi-room-runner", "version": "0"},
            },
        }
        with self._post(init, with_session=False) as resp:
            self.session_id = resp.headers.get("mcp-session-id")
            resp.read()  # drain; only the header matters here
        if not self.session_id:
            raise RuntimeError("transport did not return an mcp-session-id header")
        with self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}, with_session=True
        ) as resp:
            resp.read()
        return self.session_id

    def open_stream(self):
        """GET the server->client SSE stream for the current session."""
        headers = {"Accept": "text/event-stream"}
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        req = urllib.request.Request(self.url, method="GET", headers=headers)
        return urllib.request.urlopen(req, timeout=_STREAM_READ_TIMEOUT)

    def events(self) -> Iterator[dict]:
        """Handshake, then yield params of each discord message notification.

        Returns when the stream ends; raises on connection errors. The caller
        owns reconnection (with a fresh handshake).
        """
        self.initialize()
        with self.open_stream() as stream:
            lines = (raw.decode("utf-8", errors="replace") for raw in stream)
            for data in iter_sse_data(lines):
                try:
                    msg = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(msg, dict) or msg.get("method") != NOTIFICATION_METHOD:
                    continue
                params = msg.get("params")
                if isinstance(params, dict):
                    yield params


# ---------------------------------------------------------------------------
# Wake prompt
# ---------------------------------------------------------------------------


def build_wake_prompt(
    directive: dict,
    trigger: dict,
    history: list[dict],
    *,
    degraded: bool = False,
) -> str:
    """Render the prompt handed to ``codex exec`` for an admitted turn."""
    verdict = directive.get("verdict", "SPEAK")
    reasons = directive.get("reasons") or []
    shape = _WAKE_SHAPE.get(verdict, _WAKE_SHAPE["SPEAK"])
    channel_id = trigger.get("channel_id", "")
    message_id = trigger.get("message_id", "")

    lines = [
        f"[nunchi] Admitted room turn — verdict: {verdict}"
        + (" (DEGRADED: gate unavailable, fail-open)" if degraded else ""),
    ]
    if reasons:
        lines.append("Gate reasons:")
        lines.extend(f"- {r}" for r in reasons)
    lines += [
        "",
        "Trigger message (Discord):",
        f"  channel_id: {channel_id}",
        f"  message_id: {message_id}",
        f"  author: {trigger.get('author', '')}",
        f"  content: {trigger.get('content', '')}",
        "",
    ]
    if history:
        lines.append(f"Recent channel history (oldest first, {len(history)} messages):")
        lines.extend(f"  [{m.get('author', '?')}] {m.get('content', '')}" for m in history)
    else:
        lines.append("Recent channel history: (none seen yet)")
    lines += [
        "",
        "If you choose to respond, you MUST send it with the nunchi-discord MCP "
        f'server\'s send_message tool (channel_id "{channel_id}") or reply_message '
        f'(channel_id "{channel_id}", message_id "{message_id}"). Do not answer in '
        "plain output — only the MCP tool reaches the room.",
        f"Keep to the verdict's shape: {verdict} means {shape}.",
        "If, after reading the context, responding is no longer warranted, do "
        "nothing and end without sending.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class RoomRunner:
    """Per-event gate + wake logic. Network-free; tests drive it directly."""

    def __init__(self, config: RunnerConfig) -> None:
        self.config = config
        self._history: dict[str, deque[dict]] = {}

    # -- history -----------------------------------------------------------

    def _channel_history(self, channel_id: str) -> deque[dict]:
        if channel_id not in self._history:
            self._history[channel_id] = deque(maxlen=self.config.history_window)
        return self._history[channel_id]

    @staticmethod
    def _to_message(params: dict, author_kind: str) -> dict:
        return {
            "content": params.get("content") or "",
            "author": params.get("author_name") or params.get("author_id") or "unknown",
            "author_kind": author_kind,
            "message_id": params.get("message_id") or "",
            "timestamp": params.get("timestamp"),
        }

    # -- receipts ----------------------------------------------------------

    def _write_receipt(
        self,
        params: dict,
        *,
        verdict: str | None,
        confidences: dict | None,
        action: str,
        history_len: int,
        wake_exit: int | None = None,
        reasons: list[str] | None = None,
        error: str | None = None,
    ) -> None:
        try:
            self.config.log_path.parent.mkdir(parents=True, exist_ok=True)
            record: dict = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "channel": params.get("channel_id"),
                "message_id": params.get("message_id"),
                "author": params.get("author_name") or params.get("author_id"),
                "verdict": verdict,
                "action": action,
                "history_len": history_len,
            }
            if confidences:
                record["confidences"] = confidences
            if wake_exit is not None:
                record["wake_exit"] = wake_exit
            if reasons:
                record["reasons"] = reasons[:3]
            if error:
                record["error"] = error
            with open(self.config.log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        except OSError:
            pass  # Receipts are telemetry; never fatal

    # -- gate --------------------------------------------------------------

    def _call_gate(self, payload: dict) -> tuple[dict | None, str | None]:
        """Run nunchi-channel; return (directive, error). Exactly one is set."""
        bin_path = self.config.channel_bin
        if not bin_path:
            return None, "nunchi-channel not found; set NUNCHI_CHANNEL_BIN or install nunchi"
        try:
            result = subprocess.run(
                [bin_path],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=self.config.gate_timeout,
            )
        except subprocess.TimeoutExpired:
            return None, f"nunchi-channel timed out after {self.config.gate_timeout}s"
        except OSError as exc:
            return None, f"failed to run nunchi-channel: {exc}"
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            return None, stderr or f"nunchi-channel exited {result.returncode}"
        try:
            directive = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError) as exc:
            return None, f"nunchi-channel returned invalid JSON: {exc}"
        if not isinstance(directive, dict) or "verdict" not in directive:
            return None, "nunchi-channel returned a malformed directive"
        return directive, None

    # -- wake --------------------------------------------------------------

    def _wake_codex(self, prompt: str) -> tuple[int | None, str | None]:
        """Run one serialized ``codex exec`` wake; return (exit_code, error)."""
        cmd = [
            self.config.codex_bin,
            "exec",
            "--skip-git-repo-check",
            "--full-auto",
            *self.config.codex_extra_args,
            prompt,
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.wake_timeout,
            )
        except subprocess.TimeoutExpired:
            return None, f"codex wake timed out after {self.config.wake_timeout}s"
        except OSError as exc:
            return None, f"failed to run codex: {exc}"
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            return result.returncode, stderr[-500:] or f"codex exited {result.returncode}"
        return result.returncode, None

    # -- per-event entry ----------------------------------------------------

    def handle_notification(self, params: dict) -> str:
        """Gate one room event and route the verdict. Returns the receipt action."""
        channel_id = str(params.get("channel_id") or "")
        author_id = str(params.get("author_id") or "")

        if self.config.channels and channel_id not in self.config.channels:
            self._write_receipt(
                params, verdict=None, confidences=None, action="skipped-channel", history_len=0
            )
            return "skipped-channel"

        history = self._channel_history(channel_id)

        if self.config.self_id and author_id == self.config.self_id:
            # Belt and braces (the transport already drops its own bot). Still
            # record it as self context so duplicate suppression can see it.
            if (params.get("content") or "").strip():
                history.append(self._to_message(params, "self"))
            self._write_receipt(
                params,
                verdict=None,
                confidences=None,
                action="skipped-self",
                history_len=len(history),
            )
            return "skipped-self"

        author_kind = "peer_bot" if params.get("author_is_bot") else "human"
        message = self._to_message(params, author_kind)

        if not message["content"].strip():
            # Embed/attachment-only messages: the gate contract requires
            # non-empty content, so these are skipped (and kept out of history).
            self._write_receipt(
                params,
                verdict=None,
                confidences=None,
                action="skipped-empty",
                history_len=len(history),
            )
            return "skipped-empty"

        agent: dict = {"id": self.config.agent_id}
        if self.config.mention_id:
            agent["mention_id"] = self.config.mention_id
        payload = {
            "trigger": message,
            "history": list(history),
            "agent": agent,
            "surface": {"type": "channel", "channel_id": channel_id},
            "fail_policy": "raise",
        }
        history_len = len(history)
        history_snapshot = list(history)
        history.append(message)  # part of room context for the next trigger

        directive, gate_error = self._call_gate(payload)

        trigger_view = {
            "channel_id": channel_id,
            "message_id": message["message_id"],
            "author": message["author"],
            "content": message["content"],
        }

        if gate_error is not None:
            if self.config.fail_policy != "open":
                # Fail-CLOSED (default): a gate outage must not become a
                # frontier-call storm. Loud receipt, no wake.
                logger.error("gate error (fail-closed, no wake): %s", gate_error)
                self._write_receipt(
                    params,
                    verdict=None,
                    confidences=None,
                    action="no-wake-gate-error",
                    history_len=history_len,
                    error=gate_error,
                )
                return "no-wake-gate-error"
            logger.warning("gate error (fail-open, degraded wake): %s", gate_error)
            directive = {
                "verdict": "SPEAK",
                "reasons": [f"admission gate unavailable; fail-open -> SPEAK ({gate_error})"],
            }
            return self._route_wake(
                params, directive, trigger_view, history_snapshot, history_len, degraded=True
            )

        verdict = directive.get("verdict", "")
        if verdict == "PASS" or directive.get("silent"):
            self._write_receipt(
                params,
                verdict=verdict,
                confidences=directive.get("confidences"),
                action="pass-suppressed",
                history_len=history_len,
                reasons=directive.get("reasons") or [],
            )
            return "pass-suppressed"

        return self._route_wake(params, directive, trigger_view, history_snapshot, history_len)

    def _route_wake(
        self,
        params: dict,
        directive: dict,
        trigger_view: dict,
        history: list[dict],
        history_len: int,
        *,
        degraded: bool = False,
    ) -> str:
        prompt = build_wake_prompt(directive, trigger_view, history, degraded=degraded)
        wake_exit, wake_error = self._wake_codex(prompt)
        action = "wake-ok" if wake_error is None else "wake-error"
        self._write_receipt(
            params,
            verdict=directive.get("verdict"),
            confidences=directive.get("confidences"),
            action=action,
            history_len=history_len,
            wake_exit=wake_exit,
            reasons=directive.get("reasons") or [],
            error=wake_error,
        )
        return action


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run_forever(config: RunnerConfig) -> None:
    """Consume the transport's SSE stream forever, reconnecting with backoff."""
    runner = RoomRunner(config)
    backoff = _BACKOFF_INITIAL
    while True:
        try:
            client = TransportClient(config.transport_url)
            for params in client.events():
                backoff = _BACKOFF_INITIAL  # healthy stream resets the clock
                runner.handle_notification(params)
            logger.info("SSE stream ended; reconnecting in %.0fs", backoff)
        except (urllib.error.URLError, OSError, RuntimeError, TimeoutError) as exc:
            logger.warning("transport connection failed (%s); retrying in %.0fs", exc, backoff)
        time.sleep(backoff)
        backoff = min(backoff * 2, _BACKOFF_CAP)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    config = RunnerConfig.from_env()
    if not config.channel_bin:
        # Fail-closed would suppress every turn silently; refuse to start instead.
        print(
            "nunchi_room_runner: nunchi-channel not found; "
            "set NUNCHI_CHANNEL_BIN or install nunchi",
            file=sys.stderr,
        )
        return 1
    logger.info(
        "room runner starting: transport=%s channels=%s window=%d fail_policy=%s",
        config.transport_url,
        ",".join(sorted(config.channels)) or "(all)",
        config.history_window,
        config.fail_policy,
    )
    try:
        run_forever(config)
    except KeyboardInterrupt:
        logger.info("room runner stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
