"""Nunchi V2 admission and participant-turn boundary for Hermes 0.19.0.

The active ``register()`` entrypoint at the end of this module installs only
the V2 ``SUPPRESS / WAKE / DEFER`` path in :mod:`v2_plugin`.  The V1
``PASS / ACK / ASK / SPEAK`` helpers retained in this file are inactive
compatibility source: they are not registered, current, installed, or live.

Historical V1 configuration reference (inactive):

    nunchi:
      # enabled (bool, default false) — gate is inactive unless explicitly enabled.
      enabled: true

      # platforms (str or list, default "discord") — platform names to gate.
      # Use "*" to gate all platforms regardless of name.
      platforms: discord

      # channels — REQUIRED unless "*".  Three accepted forms:
      #
      #   Legacy CSV string (original behaviour, unchanged):
      #     channels: "1518384310321811456,2222222222222222222"
      #
      #   Legacy list (original behaviour, unchanged):
      #     channels:
      #       - "1518384310321811456"
      #       - "2222222222222222222"
      #
      #   Map form (new): channel-id -> per-channel config dict.
      #   Per-channel keys fall back to the matching global key when absent.
      #   Allowed per-channel keys: enabled, senders, allow_from, verbosity,
      #   model, pinned_rules, pinned_rules_file, fail_open, aliases,
      #   quiet_gateway_chatter.
      #   Use "*" as a key for a map-form wildcard (matches any channel).
      #     channels:
      #       "1518384310321811456":
      #         senders: all
      #         verbosity: debug
      #       "9999999999999999999":
      #         senders: allowlist
      #         allow_from: [alice, "99"]
      #         verbosity: normal
      channels: "1518384310321811456"

      # agent_id (str, default "agent") — the Hermes agent's display name as it
      # appears in channel history [bot] tags.  Operators MUST set this to the
      # bot's actual display name; the default is intentionally generic.
      agent_id: my-bot

      # mention_id (str, optional) — Discord mention snowflake included in the
      # payload so the classifier can detect direct @-mentions.  This is the
      # PLATFORM mention token (the numeric snowflake), NOT the display name:
      # a display name here makes the gate blind to real @-mentions — a direct
      # @<snowflake> mention read as "someone else" and PASSed in the retired
      # V1 implementation. Display names belonged in `aliases`.
      # mention_id: "1496355876234199040"

      # aliases (str CSV or list, optional) — additional identities this one
      # agent answers to beyond agent_id/mention_id: display names, nicknames,
      # secondary handles, profile names, extra mention tokens.  Sent as
      # agent.aliases in the payload so addressing recognizes the full bundle
      # (e.g. a bot whose agent_id is "vigil" may also be addressed as
      # "Vigil", "Codex", or "Aether").  Can be overridden per channel in the
      # map form of `channels` (a bot may carry a different display identity
      # per channel — see the channel-scoped display overrides core patch).
      # Absent means behavior is unchanged.  Not runtime-overridable (identity
      # must stay stable within a session, like agent_id/mention_id).
      # aliases: [Vigil, Codex, Aether]

      # binary (str, optional) — path to the nunchi-channel executable.
      # Defaults to shutil.which("nunchi-channel") or /usr/local/bin/nunchi-channel.
      # binary: /usr/local/bin/nunchi-channel

      # model (str, optional) — when set, NUNCHI_CLASSIFIER_MODEL is exported into
      # the subprocess environment, overriding any inherited value.  Useful for
      # selecting a non-default classifier model without touching the system env.
      # Can be overridden per channel in the map form of `channels`.
      # model: anthropic/claude-opus-4-5

      # senders (str, default "all") — controls which message senders are gated.
      # Can be overridden per channel in the map form of `channels`.
      #   all       — gate every message (retired V1 default).
      #   humans    — bot-authored messages are dropped without calling the
      #               classifier.  Requires DISCORD_ALLOW_BOTS=all globally so
      #               bot messages reach the plugin at all.
      #   allowlist — only senders whose user_name OR user_id (case-insensitive
      #               for names) appear in `allow_from` are gated; everything
      #               else is dropped without a classifier call.
      # senders: all

      # allow_from (list or CSV, optional) — required when senders=allowlist.
      # Values are matched case-insensitively against user_name and literally
      # against user_id.
      # allow_from: [alice, "42"]

      # verbosity (str, default "normal") — controls which fields are written
      # to the gate log.  Can be overridden per channel in the map form.
      #   minimal — ts, platform, channel_ids, message_id, verdict, silent,
      #             action, elapsed_ms.
      #   normal  — adds trigger_author, trigger_author_kind, history_len,
      #             classifier_model, reasons[:3], and the full `confidences`
      #             dict from the directive.
      #   debug   — adds the complete payload sent to nunchi-channel and the
      #             complete directive returned.
      # Errors always log regardless of verbosity level.
      # verbosity: normal

      # pinned_rules_file (str, optional) — path to a text file whose contents are
      # passed as "pinned_rules" in the payload on every gate invocation.  The file
      # is read lazily and cached with an mtime check so edits take effect without
      # restarting Hermes.
      # pinned_rules_file: ~/.hermes/nunchi-pinned-rules.md

      # timeout_seconds (number, default 30) — subprocess timeout; values < 1 are
      # clamped to 1 second.
      timeout_seconds: 30

      # backstop_max_sends (int, default 5) and backstop_window_seconds (number,
      # default 10) — per-channel send backstop (amplification-loops guard,
      # DEFAULT ON).  At most backstop_max_sends allowed replies per channel per
      # backstop_window_seconds; both allow paths are bounded (SPEAK/ASK/ACK
      # verdicts and fail-open error allows).  When the cap trips the reply is
      # suppressed ({"action": "skip", "reason": "nunchi:rate-limited"}) and the
      # gate log records action: rate-limited.  Like history_window these are
      # global config.yaml keys only — operator-only, never per-channel and
      # never runtime (state/slash/dashboard) overridable.
      # backstop_max_sends: 5
      # backstop_window_seconds: 10

      # fail_open (bool, default true) — when true, classifier errors allow the
      # Hermes reply through.  Set to false for strict gating.
      # Governs BOTH failure surfaces: the plugin's own exception path (a
      # crashed/missing nunchi-channel binary) AND the binary's internal
      # classifier errors — the resolved value is forwarded in the payload as
      # `fail_policy` ("open" when true, "closed" when false), overriding the
      # binary's own fail-open envelope default.
      # Can be overridden per channel in the map form of `channels`.
      fail_open: true

      # bypass_commands (bool, default true) — skip the gate for messages that
      # start with "/" (slash commands).
      bypass_commands: true

      # quiet_gateway_chatter (bool, default true) — for channels owned by
      # nunchi, keep Hermes-internal scaffolding off the shared surface. One
      # key governs all four gateway emitters: the busy-ACK send (⏩ Steered /
      # ⏳ Queued / ⚡ Interrupting), tool-progress / interim display receipts,
      # the per-turn "• Grant spent" credit notice, and compression / lifecycle
      # status chatter (📦 Preflight compression / 🗜️ Compacting context).
      # Final assistant responses, credit WARNINGS (⚠ Credits / ✕/✓ Credit
      # access), unrelated notices, and unrelated status updates still deliver
      # normally. Set false globally or per channel when an operator
      # deliberately wants visible progress receipts in a nunchi room.
      # Runtime-overridable via /nunchi chatter and the dashboard.
      quiet_gateway_chatter: true

      # log_path (str, default ~/.hermes/logs/nunchi-gate.jsonl) — append-only
      # JSONL file recording every gated message.  Set to "" or false to disable.
      log_path: ~/.hermes/logs/nunchi-gate.jsonl

      # history_window (int, default 20) — number of rolling per-channel history
      # entries kept in memory and passed to the gate as conversation context.
      # Global config.yaml only — NOT overridable per channel in the map form
      # of `channels`.
      # history_window: 20

Retired V1 helper support:
- Config block ``turnaware:`` is accepted when ``nunchi:`` is absent and a
  deprecation warning is emitted.  Rename the block to migrate.

Security / trust chain:
- The ``/nunchi`` slash command's authorization boundary is hermes' command
  dispatcher, not this plugin — see the ``_nunchi_command`` docstring for the
  precise trust chain and the whitelist that bounds its blast radius.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import inspect
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PLUGIN_NAME = "nunchi-gate"
_DEFAULT_BINARY = shutil.which("nunchi-channel") or "/usr/local/bin/nunchi-channel"
_DEFAULT_LOG_PATH = "~/.hermes/logs/nunchi-gate.jsonl"
_DEFAULT_STATE_PATH = "~/.hermes/nunchi-gate.state.json"
_DEFAULT_TIMEOUT_SECONDS = 30
_SPEAK_VERDICTS = {"SPEAK", "ASK", "ACK"}

# ---------------------------------------------------------------------------
# Quiet-room gateway chatter (one operator key: quiet_gateway_chatter).
#
# In a nunchi-owned shared channel the operator marks "quiet", the gateway's
# own scaffolding — busy-ACK bubbles, tool-progress/interim receipts, the
# per-turn "• Grant spent" credit notice, and compression/lifecycle status
# chatter — is suppressed so only the agent's intentional replies land.  The
# admission gate decides *whether the agent replies*; quiet-room decides
# *whether the gateway's scaffolding is visible*.  Four portable monkeypatches
# wire this in (display resolver, status sender, busy-ACK handler, and
# platform-notice handler); each is idempotent and fails safe (a missing
# target on a different Hermes → log once, no-op, stay verbose).
# ---------------------------------------------------------------------------

# Gateway display/progress messages that are useful local telemetry but wrong
# social output in shared nunchi channels. The nunchi plugin owns these defaults
# so operators do not have to remember separate Hermes display knobs.
_QUIET_DISPLAY_OVERRIDES: dict[str, Any] = {
    "tool_progress": "off",
    "interim_assistant_messages": False,
    "long_running_notifications": False,
    "busy_ack_detail": False,
}

_BUSY_ACK_PREFIXES = (
    "⏩ Steered into current run",
    "⏳ Queued for the next turn",
    "⏳ Subagent working",
    "⚡ Interrupting current task",
)

# Context-compression / lifecycle status chatter.  These are emitted through
# the gateway status path (``gateway.run._send_or_update_status_coro``), which
# bypasses both the display resolver and the busy-ACK handler — hence a fourth
# emitter with its own patch.  DELIBERATELY NARROW: only these specific status
# prefixes are matched, so unrelated status updates still deliver.
_STATUS_CHATTER_PREFIXES = (
    "📦 Preflight compression",
    "🗜️ Compacting context",
)

# The union predicate used by the busy-ACK adapter seam and the status sender:
# either surface should drop any known gateway-chatter string.
_GATEWAY_CHATTER_PREFIXES = _BUSY_ACK_PREFIXES + _STATUS_CHATTER_PREFIXES

# The credit/grant AgentNotice quiet-room suppresses.  DELIBERATELY NARROW:
# only the per-turn "Grant spent" spam is matched — NOT credit warnings
# (⚠ Credits low / ✕ access paused / ✓ access restored).  Suppressing those
# could hide a real account issue; grant-spent is the routine noise a quiet
# room exists to kill.  Matched on the structured notice key when present, else
# on the rendered text marker.
_CREDIT_GRANT_KEY = "credits.grant_spent"
_CREDIT_GRANT_TEXT_MARKER = "Grant spent"

# ---------------------------------------------------------------------------
# Sibling module loader: state.py lives next to __init__.py.  We load it via
# spec_from_file_location rather than a relative import so that the plugin
# works when loaded via importlib.util.spec_from_file_location in tests
# (where there is no package parent to anchor a relative import).
# ---------------------------------------------------------------------------
_state: Any = None
try:
    _state_file = Path(__file__).parent / "state.py"
    _state_spec = importlib.util.spec_from_file_location("nunchi_gate_state", _state_file)
    if _state_spec and _state_spec.loader:
        _state_mod = importlib.util.module_from_spec(_state_spec)
        _state_spec.loader.exec_module(_state_mod)  # type: ignore[union-attr]
        _state = _state_mod
except Exception:
    pass  # state module unavailable → fall back to baseline config only

# Canonical V2 entrypoint.  Like state.py, load by file location so both Hermes
# directory-plugin discovery and stdlib tests (which have no package parent)
# resolve the same bytes.
_v2_plugin: Any = None
try:
    _v2_file = Path(__file__).parent / "v2_plugin.py"
    _v2_spec = importlib.util.spec_from_file_location("nunchi_hermes_v2_plugin", _v2_file)
    if _v2_spec and _v2_spec.loader:
        _v2_mod = importlib.util.module_from_spec(_v2_spec)
        import sys as _sys
        _sys.modules[_v2_spec.name] = _v2_mod
        _v2_spec.loader.exec_module(_v2_mod)  # type: ignore[union-attr]
        _v2_plugin = _v2_mod
except Exception:
    _v2_plugin = None

# One backfilled channel_context line: "[DisplayName] content" with an
# optional " [bot]" tag inside the brackets.
_CONTEXT_LINE = re.compile(r"^\[(?P<name>[^\]]+?)(?P<bot_tag>\s+\[bot\])?\]\s*(?P<content>.+)$")

# Pinned-rules file cache: maps absolute path string -> (mtime, content)
_PINNED_RULES_CACHE: dict[str, tuple[float, str]] = {}

# Rolling per-channel history buffer: channel_id -> list of history entries.
# Bounded per channel by the `history_window` config key (default 20).
# Total entries capped at _HISTORY_MAX_TOTAL to prevent memory growth in
# long-running processes.
_CHANNEL_HISTORY: dict[str, list[dict[str, Any]]] = {}
_DEFAULT_HISTORY_WINDOW = 20
_HISTORY_MAX_TOTAL = 20_000  # ~1000 channels x 20 entries each

# Keys that can be specified per-channel in the map form of ``channels``.
# All other keys (binary, timeout_seconds, bypass_commands, log_path, …) are
# global-only and are never overridden at the per-channel level.
_PER_CHANNEL_KEYS: frozenset[str] = frozenset(
    {"enabled", "senders", "allow_from", "verbosity", "model", "pinned_rules", "pinned_rules_file", "fail_open", "aliases", "quiet_gateway_chatter"}
)

# ---------------------------------------------------------------------------
# Send backstop (amplification-loops guard) — DEFAULT ON.
#
# Sliding-window cap on *allowed* Hermes replies per channel: at most
# ``backstop_max_sends`` per ``backstop_window_seconds`` (defaults 5 / 10 s).
# Both allow paths are bounded — SPEAK/ASK/ACK verdicts and fail-open error
# allows.  When the cap trips the reply is suppressed via
# {"action": "skip", "reason": "nunchi:rate-limited"} and the gate log records
# action: rate-limited.  PASS/skip paths never consume window slots.
#
# Like ``history_window``, the knobs are global config.yaml keys only —
# operator-only, never per-channel (_PER_CHANNEL_KEYS) and never runtime
# overridable (state OVERRIDABLE_KEYS).  Mirrors the adapters' SendBackstop
# (nunchi.adapters._backstop); duplicated here because this plugin is
# standalone and must not import the nunchi package.
# ---------------------------------------------------------------------------
_DEFAULT_BACKSTOP_MAX_SENDS = 5
_DEFAULT_BACKSTOP_WINDOW_SECONDS = 10.0


class _SendBackstop:
    """Sliding-window cap: at most *max_sends* per channel per *window_seconds*.

    The ``clock`` attribute is injectable so tests run offline and instantly.
    Limits are passed per call because Hermes config can change between events.
    """

    def __init__(self, clock: Any = time.monotonic) -> None:
        self.clock = clock
        self._lock = threading.Lock()
        self._sent: dict[str, deque] = {}

    def try_acquire(self, channel_id: str, max_sends: int, window_seconds: float) -> float:
        """Returns 0.0 and records the send if allowed; else seconds to wait."""
        with self._lock:
            now = self.clock()
            window = self._sent.setdefault(str(channel_id), deque())
            while window and window[0] <= now - window_seconds:
                window.popleft()
            if len(window) >= max_sends:
                if not window:  # max_sends == 0: replies are disabled outright
                    return window_seconds
                return (window[0] + window_seconds) - now
            window.append(now)
            return 0.0


_SEND_BACKSTOP = _SendBackstop()


def _backstop_limits(cfg: dict[str, Any]) -> tuple[int, float]:
    """Read the operator-only backstop knobs with lenient parsing."""
    try:
        max_sends = int(cfg.get("backstop_max_sends", _DEFAULT_BACKSTOP_MAX_SENDS))
    except (TypeError, ValueError):
        max_sends = _DEFAULT_BACKSTOP_MAX_SENDS
    try:
        window_seconds = float(cfg.get("backstop_window_seconds", _DEFAULT_BACKSTOP_WINDOW_SECONDS))
    except (TypeError, ValueError):
        window_seconds = _DEFAULT_BACKSTOP_WINDOW_SECONDS
    return max(0, max_sends), max(0.0, window_seconds)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    text = str(value).strip()
    return [text] if text else []


def _load_config() -> dict[str, Any]:
    try:
        config_mod = importlib.import_module("hermes_cli.config")
        load_config = getattr(config_mod, "load_config")
        cfg = load_config()
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _nunchi_config() -> dict[str, Any]:
    """Return the nunchi plugin config dict from Hermes config.

    Checks ``nunchi:`` first.  Falls back to the legacy ``turnaware:`` block
    (emitting a deprecation warning) so existing deployments keep working
    without changes.
    """
    cfg = _load_config()
    if not isinstance(cfg, dict):
        return {}
    if "nunchi" in cfg:
        raw = cfg.get("nunchi")
        return raw if isinstance(raw, dict) else {}
    if "turnaware" in cfg:
        raw = cfg.get("turnaware")
        if isinstance(raw, dict):
            logger.warning(
                "nunchi-gate: config block 'turnaware:' is deprecated; "
                "rename it to 'nunchi:' to silence this warning"
            )
            return raw
    return {}


def _platform_name(source: Any) -> str:
    platform = getattr(source, "platform", None)
    value = getattr(platform, "value", None)
    return str(value or platform or "").strip()


def _channel_ids(source: Any) -> set[str]:
    ids: set[str] = set()
    for attr in ("chat_id", "parent_chat_id", "thread_id"):
        value = getattr(source, attr, None)
        if value is not None:
            text = str(value).strip()
            if text:
                ids.add(text)
    return ids


def _load_dotenv_into(env: dict[str, str]) -> None:
    """Best-effort .env load for the child process.

    Hermes gateway usually starts with ~/.hermes/.env already loaded, but this
    keeps the plugin usable in tests and non-standard launches.  Existing
    process environment values win.  Uses a tiny stdlib-only parser; no
    third-party dotenv package is required.
    """
    env_path = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / ".env"
    if not env_path.exists():
        return
    # Tiny fallback parser: handles KEY=value and export KEY=value. Quoted
    # values are unwrapped, but complex shell expansions are not supported.
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            if stripped.startswith("export "):
                stripped = stripped[len("export ") :].strip()
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in env:
                env[key] = value
    except Exception:
        return


def _load_pinned_rules(path_str: str) -> str | None:
    """Read pinned rules from *path_str*, returning cached content on mtime hit."""
    path = Path(path_str).expanduser()
    if not path.exists():
        return None
    try:
        mtime = path.stat().st_mtime
        if path_str in _PINNED_RULES_CACHE:
            cached_mtime, cached_content = _PINNED_RULES_CACHE[path_str]
            if cached_mtime == mtime:
                return cached_content
        content = path.read_text(encoding="utf-8")
        _PINNED_RULES_CACHE[path_str] = (mtime, content)
        return content
    except Exception:
        logger.debug("nunchi-gate: failed to read pinned_rules_file %s", path_str, exc_info=True)
        return None


def _rolling_history(channel_id: str, history_window: int) -> list[dict[str, Any]]:
    """Return a copy of the rolling buffer for *channel_id*, capped to *history_window*."""
    buf = _CHANNEL_HISTORY.get(channel_id, [])
    return list(buf[-history_window:])


def _record_to_buffer(channel_id: str, event: Any, source: Any, history_window: int) -> None:
    """Append the current event to the rolling buffer for *channel_id*.

    Called after each gate judgment so the NEXT event for this channel has
    history to work with.  Enforces per-channel FIFO eviction and a global
    total-entries cap so the buffer stays bounded in long-running processes.
    """
    text = str(getattr(event, "text", "") or "").strip()
    if not text:
        return

    author_raw = getattr(source, "user_name", None) or getattr(source, "user_id", None)
    author = str(author_raw).strip() if author_raw is not None else None
    is_bot = getattr(source, "is_bot", None)
    author_kind = "peer_bot" if _coerce_bool(is_bot) else "human"
    message_id = getattr(event, "message_id", None) or getattr(source, "message_id", None)

    entry: dict[str, Any] = {
        "content": text,
        "author": author,
        "author_kind": author_kind,
    }
    if message_id is not None:
        entry["message_id"] = str(message_id)

    buf = _CHANNEL_HISTORY.setdefault(channel_id, [])
    buf.append(entry)
    # Per-channel FIFO eviction.
    if len(buf) > history_window:
        del buf[: len(buf) - history_window]

    # Global cap: drop the oldest channel when total entries exceed the limit.
    total = sum(len(v) for v in _CHANNEL_HISTORY.values())
    if total > _HISTORY_MAX_TOTAL:
        oldest = next(iter(_CHANNEL_HISTORY))
        del _CHANNEL_HISTORY[oldest]


def resolve_channel_config(cfg: dict[str, Any], channel_ids: set[str]) -> dict[str, Any] | None:
    """Resolve the effective config for a given set of channel IDs.

    This is a pure function: given the global config dict and the event's
    channel IDs, it returns either the effective config dict to use for this
    event, or ``None`` if the event should not be gated (channel not matched).

    **Legacy form** (``channels`` is a CSV string or list):
    Returns *cfg* unchanged when any of *channel_ids* matches a listed ID, or
    when ``"*"`` appears in the channels list (wildcard).  Returns ``None`` when
    no channel matches.

    **Map form** (``channels`` is a dict):
    Searches *channel_ids* for an exact key match in the map; falls back to a
    ``"*"`` key if present.  Returns ``None`` when no entry matches or the
    matched entry has ``enabled: false``.  Otherwise merges per-channel keys
    (``enabled``, ``senders``, ``allow_from``, ``verbosity``, ``model``,
    ``pinned_rules``, ``pinned_rules_file``, ``fail_open``, ``aliases``,
    ``quiet_gateway_chatter``) on top of the global config and returns the
    merged dict.  Global keys absent from the per-channel entry are inherited
    unchanged.
    """
    channels_raw = cfg.get("channels") or cfg.get("channel_ids")

    if isinstance(channels_raw, dict):
        # Map form — find the best matching per-channel entry.
        per_ch_raw: Any = None
        found = False
        for cid in channel_ids:
            if cid in channels_raw:
                per_ch_raw = channels_raw[cid]
                found = True
                break
        if not found and "*" in channels_raw:
            per_ch_raw = channels_raw["*"]
            found = True
        if not found:
            return None

        per_ch: dict[str, Any] = per_ch_raw if isinstance(per_ch_raw, dict) else {}

        # Listed map channels are enabled by default; ``enabled: false`` opts out.
        if not _coerce_bool(per_ch.get("enabled", True)):
            return None

        # Merge: start with a shallow copy of global config, override with
        # per-channel keys that are explicitly present in the entry.
        resolved: dict[str, Any] = {**cfg}
        for key in _PER_CHANNEL_KEYS:
            if key in per_ch:
                resolved[key] = per_ch[key]
        return resolved

    # Legacy form: CSV string, list, or anything _coerce_list can handle.
    if channels_raw is None:
        return None
    channels = set(_coerce_list(channels_raw))
    if not channels:
        return None
    if "*" in channels or (channel_ids & channels):
        return cfg
    return None


# ---------------------------------------------------------------------------
# Quiet-room gateway chatter suppression.
#
# One operator key (``quiet_gateway_chatter``, default true, per-channel and
# runtime-overridable) controls all four gateway emitters in a nunchi-owned
# channel:
#   1. tool-progress / interim display receipts (via ``_patch_display_resolver``)
#   2. the busy-ACK send bubble           (via ``_patch_busy_ack_handler``)
#   3. the per-turn "• Grant spent" notice (via ``_patch_notice_handler``)
#   4. compression / lifecycle status chatter (via ``_patch_status_sender``)
# Everything else — final replies, credit WARNINGS, unrelated notices, and
# unrelated status updates — always delivers, and nothing is suppressed outside
# a quiet nunchi channel.  Each patch is idempotent and fails safe: a missing
# target on a different Hermes logs nothing fatal, no-ops, and leaves the
# gateway verbose.
# ---------------------------------------------------------------------------


def _load_runtime_state(base_cfg: dict[str, Any]) -> dict[str, Any]:
    """Best-effort load of nunchi runtime state overrides."""
    if _state is None:
        return {}
    state_path = Path(str(base_cfg.get("state_path") or _DEFAULT_STATE_PATH)).expanduser()
    try:
        data = _state.load_state(state_path)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _effective_surface_config(platform_key: str, channel_ids: set[str]) -> dict[str, Any] | None:
    """Resolve nunchi config for gateway surface-level UX shims.

    This intentionally mirrors the gate's config layering without requiring a
    message body or classifier call. It is used for Hermes gateway display
    quieting: if a surface is a nunchi-owned shared channel, progress/steering
    receipts are controlled by nunchi's config surface.
    """
    base_cfg = _nunchi_config()
    if not isinstance(base_cfg, dict):
        return None

    state_data = _load_runtime_state(base_cfg)
    cfg = base_cfg
    if _state is not None and state_data:
        g = _state.filter_overridable(state_data.get("global") or {})
        if g:
            cfg = {**base_cfg, **g}

    if not _coerce_bool(cfg.get("enabled"), default=False):
        return None

    platform = str(platform_key or "").strip()
    platforms = set(_coerce_list(cfg.get("platforms") or "discord"))
    if platforms and "*" not in platforms and platform not in platforms:
        return None

    clean_channel_ids = {str(cid).strip() for cid in channel_ids if str(cid).strip()}
    if not clean_channel_ids:
        return None

    if _state is not None:
        resolved = _state.merge_effective(
            base_cfg,
            state_data,
            clean_channel_ids,
            _resolve_channel_config=resolve_channel_config,
        )
    else:
        resolved = resolve_channel_config(cfg, clean_channel_ids)

    if resolved is None:
        return None
    if not _coerce_bool(resolved.get("enabled"), default=False):
        return None
    return resolved


def _quiet_gateway_chatter_enabled(cfg: dict[str, Any]) -> bool:
    """Return whether nunchi should suppress Hermes progress chatter.

    Default is true for nunchi-owned channels: using nunchi means the operator
    wants room-behaviour choices to be recognized in one place, not recalled as
    a separate Hermes display-config checklist.
    """
    return _coerce_bool(cfg.get("quiet_gateway_chatter"), default=True)


def _nunchi_quiet_display_override(platform_key: str, setting: str, channel_id: Any = None) -> Any | None:
    """Return a display override for nunchi shared channels, or ``None``.

    ``None`` means "let Hermes display_config decide". Non-None values are the
    nunchi-owned quiet defaults for progress/status surfaces.
    """
    if setting not in _QUIET_DISPLAY_OVERRIDES:
        return None
    if channel_id is None:
        return None
    resolved = _effective_surface_config(str(platform_key or ""), {str(channel_id)})
    if resolved is None or not _quiet_gateway_chatter_enabled(resolved):
        return None
    override = _QUIET_DISPLAY_OVERRIDES[setting]
    # This path is consulted per display-setting resolution (high frequency), so
    # the per-suppression audit line is DEBUG — unlike the discrete message-drop
    # emitters (busy-ACK / status / notice) which log at INFO.  The one-time
    # register() summary announces tool-progress quieting at INFO.
    logger.debug(
        "nunchi-gate suppressed gateway display setting platform=%s chat=%s setting=%s -> %r",
        platform_key,
        channel_id,
        setting,
        override,
    )
    return override


def _patch_display_resolver(display_config_module: Any | None = None) -> bool:
    """Monkeypatch Hermes' display resolver for nunchi-owned channels.

    This keeps the fix portable with the plugin: no Hermes core patch is
    required for users who install nunchi-gate into their profile.

    Returns True when the target is present (freshly wrapped or already
    wrapped), False when the target is missing on this Hermes (fail-safe
    no-op — tool-progress stays VISIBLE and register() reports it inert).
    """
    try:
        module = display_config_module or importlib.import_module("gateway.display_config")
        original = getattr(module, "resolve_display_setting", None)
    except Exception:
        return False
    if not callable(original):
        return False
    if getattr(original, "_nunchi_quiet_wrapped", False):
        return True  # idempotent — already installed

    def _resolve_display_setting(user_config, platform_key, setting, fallback=None, *, channel_id=None):
        override = _nunchi_quiet_display_override(platform_key, setting, channel_id)
        if override is not None:
            return override
        return original(user_config, platform_key, setting, fallback, channel_id=channel_id)

    _resolve_display_setting._nunchi_quiet_wrapped = True  # type: ignore[attr-defined]
    _resolve_display_setting._nunchi_original = original  # type: ignore[attr-defined]
    setattr(module, "resolve_display_setting", _resolve_display_setting)
    return True


def _is_gateway_chatter_message(content: Any) -> bool:
    text = str(content or "").strip()
    return any(text.startswith(prefix) for prefix in _GATEWAY_CHATTER_PREFIXES)


def _source_quiets_gateway_chatter(source: Any) -> bool:
    """True when *source* is a nunchi-owned channel marked quiet."""
    platform = _platform_name(source)
    resolved = _effective_surface_config(platform, _channel_ids(source))
    return bool(resolved is not None and _quiet_gateway_chatter_enabled(resolved))


def _event_quiets_gateway_chatter(event: Any) -> bool:
    return _source_quiets_gateway_chatter(getattr(event, "source", None))


def _patch_busy_ack_handler(runner_cls: Any | None = None) -> bool:
    """Suppress Hermes busy acknowledgements in nunchi-owned channels.

    The busy path sends directly via ``adapter._send_with_retry`` before the
    normal final-response path, so ``pre_gateway_dispatch`` cannot intercept it.
    We wrap only that handler and only drop known Hermes busy-ack strings; all
    other sends, including final responses, still call the original adapter.

    Returns True when the target is present (freshly wrapped or already
    wrapped), False when the target is missing on this Hermes (fail-safe
    no-op — busy-ACK bubbles stay VISIBLE and register() reports it inert).
    """
    try:
        if runner_cls is None:
            run_mod = importlib.import_module("gateway.run")
            runner_cls = getattr(run_mod, "GatewayRunner", None)
        original = getattr(runner_cls, "_handle_active_session_busy_message", None)
    except Exception:
        return False
    if not callable(original):
        return False
    if getattr(original, "_nunchi_quiet_wrapped", False):
        return True  # idempotent — already installed

    async def _handle_active_session_busy_message(self, event, session_key):
        if not _event_quiets_gateway_chatter(event):
            return await original(self, event, session_key)

        source = getattr(event, "source", None)
        adapter = getattr(self, "adapters", {}).get(getattr(source, "platform", None))
        send_with_retry = getattr(adapter, "_send_with_retry", None)
        if not callable(send_with_retry):
            return await original(self, event, session_key)

        async def _quiet_send_with_retry(*args, **kwargs):
            content = kwargs.get("content")
            if content is None and len(args) >= 2:
                content = args[1]
            if _is_gateway_chatter_message(content):
                logger.info(
                    "nunchi-gate suppressed gateway chatter platform=%s chat=%s",
                    _platform_name(source),
                    getattr(source, "chat_id", None),
                )
                return None
            result = send_with_retry(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        setattr(adapter, "_send_with_retry", _quiet_send_with_retry)
        try:
            return await original(self, event, session_key)
        finally:
            if getattr(adapter, "_send_with_retry", None) is _quiet_send_with_retry:
                setattr(adapter, "_send_with_retry", send_with_retry)

    _handle_active_session_busy_message._nunchi_quiet_wrapped = True  # type: ignore[attr-defined]
    _handle_active_session_busy_message._nunchi_original = original  # type: ignore[attr-defined]
    setattr(runner_cls, "_handle_active_session_busy_message", _handle_active_session_busy_message)
    return True


def _patch_status_sender(run_module: Any | None = None) -> bool:
    """Suppress Hermes status/lifecycle chatter in nunchi-owned quiet channels.

    Context-compression notices ("📦 Preflight compression", "🗜️ Compacting
    context") are emitted through the gateway status path
    (``gateway.run._send_or_update_status_coro``), which bypasses both the
    display resolver and the busy-ACK handler.  Wrapping the module-level
    status sender keeps the policy plugin-local while preserving final replies:
    only known status-chatter prefixes are dropped, and only for a quiet nunchi
    channel; every other status update passes through untouched.

    Async-correct (the target is a coroutine; suppression returns ``None``
    without awaiting the original), idempotent (``_nunchi_quiet_wrapped`` mark),
    and fail-safe (a Hermes without the target → no-op, never raise).

    Returns True when the target is present (freshly wrapped or already
    wrapped), False when the target is missing on this Hermes (fail-safe
    no-op — compression/status chatter stays VISIBLE and register() reports it
    inert).
    """
    try:
        module = run_module or importlib.import_module("gateway.run")
        original = getattr(module, "_send_or_update_status_coro", None)
    except Exception:
        return False
    if not callable(original):
        return False
    if getattr(original, "_nunchi_quiet_wrapped", False):
        return True  # idempotent — already installed

    async def _send_or_update_status_coro(adapter, chat_id, status_key, content, metadata):
        chat_text = str(chat_id or "").strip()
        if chat_text and _is_gateway_chatter_message(content):
            platform = _platform_name(adapter)
            resolved = _effective_surface_config(platform, {chat_text})
            if resolved is not None and _quiet_gateway_chatter_enabled(resolved):
                logger.info(
                    "nunchi-gate suppressed gateway status chatter platform=%s chat=%s status=%s",
                    platform,
                    chat_text,
                    status_key,
                )
                return None
        result = original(adapter, chat_id, status_key, content, metadata)
        if inspect.isawaitable(result):
            return await result
        return result

    _send_or_update_status_coro._nunchi_quiet_wrapped = True  # type: ignore[attr-defined]
    _send_or_update_status_coro._nunchi_original = original  # type: ignore[attr-defined]
    setattr(module, "_send_or_update_status_coro", _send_or_update_status_coro)
    return True


def _is_credit_grant_notice(line: Any, key: Any = None) -> bool:
    """True when a platform notice is the credit/grant-spent notice.

    Matches either the structured AgentNotice key (``credits.grant_spent``,
    when the caller has it) or the rendered text marker (``"Grant spent"``,
    as in ``"• Grant spent · …"``).  Deliberately narrow: only this notice
    family is suppressed, so credit WARNINGS (``⚠ Credits …``,
    ``✕/✓ Credit access``) and unrelated ``• …`` notices still reach a quiet
    room.
    """
    if key is not None and str(key).strip() == _CREDIT_GRANT_KEY:
        return True
    return _CREDIT_GRANT_TEXT_MARKER in str(line or "")


def _looks_like_source(obj: Any) -> bool:
    return obj is not None and (hasattr(obj, "chat_id") or hasattr(obj, "platform"))


def _notice_source(args: tuple, kwargs: dict) -> Any:
    """Find the ``source`` object in a ``_deliver_platform_notice`` call.

    Handles ``(source, content)`` positional, a ``source=`` kwarg, and an
    ``event``-carrying variant.  Returns ``None`` when nothing source-like is
    found (the wrapper then fails safe and delivers).
    """
    src = kwargs.get("source")
    if _looks_like_source(src):
        return src
    ev = kwargs.get("event")
    if ev is not None and _looks_like_source(getattr(ev, "source", None)):
        return getattr(ev, "source")
    for a in args:
        if _looks_like_source(a):
            return a
        nested = getattr(a, "source", None)
        if _looks_like_source(nested):
            return nested
    return None


def _notice_content(args: tuple, kwargs: dict) -> Any:
    """Find the rendered notice text of a ``_deliver_platform_notice`` call."""
    for name in ("content", "line", "text"):
        if name in kwargs and kwargs[name] is not None:
            return kwargs[name]
    for a in args:
        if isinstance(a, str):
            return a
    return None


def _patch_notice_handler(runner_cls: Any | None = None) -> bool:
    """Suppress the per-turn credit/grant notice in nunchi-owned quiet channels.

    Wraps ``GatewayRunner._deliver_platform_notice`` (async).  Only the narrow
    "• Grant spent" notice is dropped, and only in a quiet nunchi channel;
    credit WARNINGS (⚠ Credits, ✕/✓ Credit access) and every other notice
    always deliver so real account issues stay visible.  Suppression returns
    ``None`` without awaiting the original — the caller awaits the wrapper and
    ``_deliver_platform_notice`` is a ``-> None`` coroutine, so ``None`` is the
    correct suppressed result and nothing is left un-awaited.

    Returns True when the target is present (freshly wrapped or already
    wrapped), False when the target is missing on this Hermes (fail-safe
    no-op — the grant-spent notice stays VISIBLE and register() reports it
    inert).
    """
    try:
        if runner_cls is None:
            run_mod = importlib.import_module("gateway.run")
            runner_cls = getattr(run_mod, "GatewayRunner", None)
        original = getattr(runner_cls, "_deliver_platform_notice", None)
    except Exception:
        return False
    if not callable(original):
        return False
    if getattr(original, "_nunchi_quiet_wrapped", False):
        return True  # idempotent — already installed

    async def _deliver_platform_notice(self, *args, **kwargs):
        content = _notice_content(args, kwargs)
        key = kwargs.get("key") or kwargs.get("notice_key")
        if _is_credit_grant_notice(content, key):
            source = _notice_source(args, kwargs)
            if source is not None and _source_quiets_gateway_chatter(source):
                logger.info(
                    "nunchi-gate suppressed credit/grant notice platform=%s chat=%s",
                    _platform_name(source),
                    getattr(source, "chat_id", None),
                )
                return None
        return await original(self, *args, **kwargs)

    _deliver_platform_notice._nunchi_quiet_wrapped = True  # type: ignore[attr-defined]
    _deliver_platform_notice._nunchi_original = original  # type: ignore[attr-defined]
    setattr(runner_cls, "_deliver_platform_notice", _deliver_platform_notice)
    return True


def _parse_channel_context(event: Any, agent_id: str) -> list[dict[str, Any]]:
    """Parse the backfilled channel history into channel-adapter history items.

    The Discord adapter pre-fetches recent channel messages (back to this
    bot's own last turn) into ``event.channel_context`` as
    "[DisplayName]( [bot])? content" lines.  That pre-computed string is the
    only history reachable from this synchronous hook.

    Author classification:
    - A [bot]-tagged line whose name matches *agent_id* (case-insensitive)
      gets author_kind "self".
    - Any other [bot]-tagged line gets "peer_bot".
    - Lines without a [bot] tag get "human".
    """
    raw = getattr(event, "channel_context", None) or ""
    history: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("[Recent channel messages]"):
            continue
        match = _CONTEXT_LINE.match(line)
        if not match:
            continue
        author = match.group("name").strip()
        if match.group("bot_tag"):
            kind = "self" if author.lower() == agent_id.lower() else "peer_bot"
        else:
            kind = "human"
        history.append(
            {"content": match.group("content"), "author": author, "author_kind": kind}
        )
    return history


def _build_payload(event: Any, cfg: dict[str, Any], history: list | None = None) -> dict[str, Any]:
    agent_id = str(cfg.get("agent_id") or "agent").strip() or "agent"
    source = getattr(event, "source", None)

    # The classifier's addressing/suppressor judgment runs on who spoke and who
    # is addressed — starve these signals and every verdict degrades to "does
    # this text sound answerable" (observed: all-SPEAK on the thin payload).
    trigger: dict[str, Any] = {"content": str(getattr(event, "text", "") or "")}
    message_id = getattr(event, "message_id", None) or getattr(source, "message_id", None)
    if message_id:
        trigger["message_id"] = str(message_id)
    author = getattr(source, "user_name", None) or getattr(source, "user_id", None)
    if author:
        trigger["author"] = str(author)
    is_bot = getattr(source, "is_bot", None)
    if is_bot is not None:
        trigger["author_kind"] = "peer_bot" if is_bot else "human"

    agent: dict[str, Any] = {"id": agent_id}
    mention_id = str(cfg.get("mention_id") or "").strip()
    if mention_id:
        agent["mention_id"] = mention_id
    # aliases: every other identity this one agent answers to (display names,
    # nicknames, secondary handles, extra mention tokens).  Deduped against
    # agent_id/mention_id, order preserved.  Absent/empty -> key omitted, so
    # alias-free configs produce exactly the pre-alias payload.
    aliases: list[str] = []
    for alias in _coerce_list(cfg.get("aliases")):
        if alias not in aliases and alias != agent_id and alias != mention_id:
            aliases.append(alias)
    if aliases:
        agent["aliases"] = aliases

    payload: dict[str, Any] = {"trigger": trigger, "agent": agent}
    if history:
        payload["history"] = history

    # Forward the resolved fail_open as the envelope's fail_policy.  Without
    # this the nunchi-channel binary applies its own fail-open default, so a
    # classifier outage inside the binary degraded to SPEAK even under
    # fail_open: false (live event 2026-07-08).
    fail_open = _coerce_bool(cfg.get("fail_open"), default=True)
    payload["fail_policy"] = "open" if fail_open else "closed"

    # pinned_rules takes precedence over pinned_rules_file when both are set.
    pinned = str(cfg.get("pinned_rules") or "").strip()
    if not pinned:
        pinned_file = str(cfg.get("pinned_rules_file") or "").strip()
        if pinned_file:
            loaded = _load_pinned_rules(pinned_file)
            if loaded:
                pinned = loaded.strip()
    if pinned:
        payload["pinned_rules"] = pinned
    return payload


def _run_nunchi(payload: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    binary = str(cfg.get("binary") or _DEFAULT_BINARY).strip() or _DEFAULT_BINARY
    timeout = cfg.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
    try:
        timeout_s = max(1.0, float(timeout))
    except (TypeError, ValueError):
        timeout_s = float(_DEFAULT_TIMEOUT_SECONDS)

    # nunchi-channel reads the channel-adapter payload from stdin and prints a
    # transport-neutral directive (verdict + silent + run_shape) on stdout.
    cmd = [binary]

    env = os.environ.copy()
    _load_dotenv_into(env)

    # When ``model`` is configured, override the classifier model in the
    # subprocess environment so this gate can use a non-default model without
    # touching the system environment or the Hermes process env.
    model = str(cfg.get("model") or "").strip()
    if model:
        env["NUNCHI_CLASSIFIER_MODEL"] = model

    completed = subprocess.run(
        cmd,
        input=json.dumps(payload, separators=(",", ":")),
        text=True,
        capture_output=True,
        timeout=timeout_s,
        env=env,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise RuntimeError(f"nunchi-channel exited {completed.returncode}: {stderr[:500]}")
    try:
        result = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"nunchi-channel returned invalid JSON: {exc}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("nunchi-channel returned non-object JSON")
    return result


def _write_gate_log(entry: dict[str, Any], cfg: dict[str, Any]) -> None:
    raw_log_path = cfg.get("log_path", _DEFAULT_LOG_PATH)
    if raw_log_path is None:
        return
    log_path = str(raw_log_path).strip()
    if not log_path or log_path.lower() in {"0", "false", "no", "off", "none"}:
        return
    path = Path(log_path).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True, default=str) + "\n")
    except Exception:
        logger.debug("nunchi-gate: failed to write jsonl log", exc_info=True)


def _should_gate(event: Any, cfg: dict[str, Any]) -> bool:
    """Check basic gating criteria: enabled, bypass_commands, platforms, and
    non-empty text.

    Channel matching is handled separately by :func:`resolve_channel_config`
    after this function returns ``True``, so this function deliberately does
    not inspect the ``channels`` config key.
    """
    if not _coerce_bool(cfg.get("enabled"), default=False):
        return False

    if _coerce_bool(cfg.get("bypass_commands"), default=True):
        text = str(getattr(event, "text", "") or "")
        if text.strip().startswith("/"):
            return False

    source = getattr(event, "source", None)
    platform = _platform_name(source)
    platforms = set(_coerce_list(cfg.get("platforms") or "discord"))
    if platforms and "*" not in platforms and platform not in platforms:
        return False

    text = str(getattr(event, "text", "") or "")
    return bool(text.strip())


def _gate_event(event: Any, gateway: Any = None, session_store: Any = None, **_: Any):
    base_cfg = _nunchi_config()

    # Load runtime state overrides.  The state_path itself is config.yaml-only
    # (not overridable at runtime) to prevent a chat command from redirecting
    # the state file to an attacker-controlled path.
    state_data: dict[str, Any] = {}
    if _state is not None:
        state_path = Path(str(base_cfg.get("state_path") or _DEFAULT_STATE_PATH)).expanduser()
        try:
            state_data = _state.load_state(state_path)
        except Exception:
            pass

    # Pre-apply global state overrides so _should_gate sees the live 'enabled'
    # value (in case an operator ran /nunchi enable global after startup).
    cfg = base_cfg
    if _state is not None and state_data:
        g = _state.filter_overridable(state_data.get("global") or {})
        if g:
            cfg = {**base_cfg, **g}

    if not _should_gate(event, cfg):
        return None

    source = getattr(event, "source", None)
    ch_ids = _channel_ids(source)

    # Full per-channel resolution: config.yaml map form + runtime state overlays.
    # merge_effective re-applies the global overlay (idempotent) then adds the
    # per-channel state layer on top of the config.yaml per-channel merge.
    if _state is not None:
        resolved_cfg = _state.merge_effective(
            base_cfg, state_data, ch_ids,
            _resolve_channel_config=resolve_channel_config,
        )
    else:
        resolved_cfg = resolve_channel_config(base_cfg, ch_ids)
    if resolved_cfg is None:
        return None

    started = time.time()
    verbosity = str(resolved_cfg.get("verbosity") or "normal").strip().lower()
    agent_id = str(resolved_cfg.get("agent_id") or "agent").strip() or "agent"

    # ------------------------------------------------------------------ #
    # Sender policy — checked before any subprocess call.                 #
    # A "drop" emits {"action":"skip","reason":"nunchi:sender-policy"}    #
    # and a receipt log entry, but never invokes nunchi-channel.          #
    # ------------------------------------------------------------------ #
    senders = str(resolved_cfg.get("senders") or "all").strip().lower()
    if senders != "all":
        is_bot = getattr(source, "is_bot", None)
        user_name = str(getattr(source, "user_name", None) or "").strip()
        user_id = str(getattr(source, "user_id", None) or "").strip()

        drop = False
        if senders == "humans":
            drop = _coerce_bool(is_bot)
        elif senders == "allowlist":
            allow_from_raw = _coerce_list(resolved_cfg.get("allow_from") or [])
            allow_set = {a.lower() for a in allow_from_raw}
            drop = not (user_name.lower() in allow_set or user_id.lower() in allow_set)

        if drop:
            elapsed_ms = round((time.time() - started) * 1000)
            log_entry: dict[str, Any] = {
                "ts": started,
                "platform": _platform_name(source),
                "channel_ids": sorted(ch_ids),
                "message_id": getattr(event, "message_id", None),
                "action": "skip-sender-policy",
                "elapsed_ms": elapsed_ms,
            }
            _write_gate_log(log_entry, resolved_cfg)
            return {"action": "skip", "reason": "nunchi:sender-policy"}

    # ------------------------------------------------------------------ #
    # Normal classifier path.                                             #
    # ------------------------------------------------------------------ #
    history_window = max(1, int(resolved_cfg.get("history_window") or _DEFAULT_HISTORY_WINDOW))

    # Primary channel id for the rolling buffer.
    primary_ch_id = next(iter(sorted(ch_ids)), "") if ch_ids else ""

    # Rolling buffer: messages this plugin saw before the current event.
    rolling = _rolling_history(primary_ch_id, history_window)

    # event.channel_context is backfilled by the Discord adapter in some
    # deployments.  It never populates at hook time in production (155/155
    # calls returned empty), so rolling is the primary source.  When it
    # does populate, prefer whichever list is longer and log at DEBUG.
    ctx_history = _parse_channel_context(event, agent_id)
    if ctx_history:
        logger.debug(
            "nunchi-gate: channel_context populated for %s (%d entries); "
            "rolling=%d ctx=%d; using richer",
            primary_ch_id, len(ctx_history), len(rolling), len(ctx_history),
        )
        history = ctx_history if len(ctx_history) >= len(rolling) else rolling
    else:
        history = rolling

    payload = _build_payload(event, resolved_cfg, history)

    # Base log fields present at every verbosity level.
    base_log: dict[str, Any] = {
        "ts": started,
        "platform": _platform_name(source),
        "channel_ids": sorted(ch_ids),
        "message_id": getattr(event, "message_id", None),
    }
    # normal and debug add author / history metadata.
    if verbosity in ("normal", "debug"):
        base_log["trigger_author"] = payload["trigger"].get("author")
        base_log["trigger_author_kind"] = payload["trigger"].get("author_kind")
        base_log["history_len"] = len(history)

    try:
        result = _run_nunchi(payload, resolved_cfg)
        verdict = str(result.get("verdict") or "").upper()
        elapsed_ms = round((time.time() - started) * 1000)

        log_entry = {
            **base_log,
            "elapsed_ms": elapsed_ms,
            "verdict": verdict,
            "silent": result.get("silent"),
        }

        # normal adds classifier metadata + confidences; debug adds everything.
        if verbosity in ("normal", "debug"):
            log_entry["classifier_model"] = result.get("classifier_model")
            log_entry["reasons"] = (result.get("reasons") or [])[:3]
            confidences = result.get("confidences")
            if confidences is not None:
                log_entry["confidences"] = confidences
        if verbosity == "debug":
            log_entry["payload"] = payload
            log_entry["directive"] = result

        if result.get("silent") is True or verdict == "PASS":
            log_entry["action"] = "skip"
            _write_gate_log(log_entry, resolved_cfg)
            logger.info("nunchi-gate PASS -> skip channel_ids=%s", log_entry["channel_ids"])
            return {"action": "skip", "reason": "nunchi:PASS"}
        if verdict in _SPEAK_VERDICTS:
            # Send backstop: bound allowed replies per channel (default ON).
            max_sends, window_seconds = _backstop_limits(resolved_cfg)
            wait = _SEND_BACKSTOP.try_acquire(primary_ch_id, max_sends, window_seconds)
            if wait > 0:
                log_entry["action"] = "rate-limited"
                _write_gate_log(log_entry, resolved_cfg)
                logger.warning(
                    "nunchi-gate %s -> rate-limited (send backstop, max %d per %.0fs; retry in %.1fs) channel_ids=%s",
                    verdict, max_sends, window_seconds, wait, log_entry["channel_ids"],
                )
                return {"action": "skip", "reason": "nunchi:rate-limited"}
            log_entry["action"] = "allow"
            _write_gate_log(log_entry, resolved_cfg)
            logger.info("nunchi-gate %s -> allow channel_ids=%s", verdict, log_entry["channel_ids"])
            return None
        raise RuntimeError(f"unknown nunchi verdict {verdict!r}")
    except Exception as exc:
        fail_open = _coerce_bool(resolved_cfg.get("fail_open"), default=True)
        # A fail-open allow is still a reply — the backstop bounds it too, so a
        # classifier-error loop cannot amplify unbounded.
        rate_limited = False
        if fail_open:
            max_sends, window_seconds = _backstop_limits(resolved_cfg)
            rate_limited = _SEND_BACKSTOP.try_acquire(primary_ch_id, max_sends, window_seconds) > 0
        if rate_limited:
            action = "rate-limited"
        else:
            action = "allow" if fail_open else "skip"
        log_entry = {
            **base_log,
            "elapsed_ms": round((time.time() - started) * 1000),
            "action": action,
            "error": str(exc)[:500],
            "fail_open": fail_open,
        }
        _write_gate_log(log_entry, resolved_cfg)
        logger.warning("nunchi-gate error (%s); fail_open=%s", exc, fail_open)
        if rate_limited:
            return {"action": "skip", "reason": "nunchi:rate-limited"}
        if fail_open:
            return None
        return {"action": "skip", "reason": "nunchi:error"}
    finally:
        # Record this event in the rolling buffer so the next event for this
        # channel has history.  Runs on all paths including errors.
        _record_to_buffer(primary_ch_id, event, source, history_window)


# ---------------------------------------------------------------------------
# /nunchi slash command
# ---------------------------------------------------------------------------

_VALID_SENDERS = {"all", "humans", "allowlist"}
_VALID_VERBOSITY = {"minimal", "normal", "debug"}
_VALID_CHATTER = {"quiet": True, "visible": False, "on": True, "off": False, "true": True, "false": False}

_NUNCHI_USAGE = (
    "Usage: /nunchi <subcommand>\n"
    "  status\n"
    "  enable  <channel-id | global>\n"
    "  disable <channel-id | global>\n"
    "  senders <all | humans | allowlist> [channel-id | global]\n"
    "  verbosity <minimal | normal | debug> [channel-id | global]\n"
    "  chatter <quiet | visible> [channel-id | global]\n"
    "  reset   [channel-id | global]\n"
    "\n"
    "Channel IDs must be given explicitly (e.g. '1518384310321811456').\n"
    "Use 'global' to set or reset the cross-channel override."
)


def _nunchi_state_path(cfg: dict[str, Any]) -> Path:
    return Path(str(cfg.get("state_path") or _DEFAULT_STATE_PATH)).expanduser()


def _channel_list_from_cfg(cfg: dict[str, Any]) -> list[str]:
    """Return the list of explicitly configured channel IDs (no wildcards)."""
    channels_raw = cfg.get("channels") or cfg.get("channel_ids")
    if isinstance(channels_raw, dict):
        return [k for k in channels_raw if k != "*"]
    ids = _coerce_list(channels_raw)
    return [c for c in ids if c != "*"]


def _provenance(key: str, val: Any, ch_overrides: dict, global_overrides: dict) -> str:
    """Return a short provenance badge for a config value."""
    if key in ch_overrides:
        return f"{val!r}  [channel-override]"
    if key in global_overrides:
        return f"{val!r}  [global-override]"
    return f"{val!r}"


def _cmd_status(cfg: dict[str, Any], state_path: Path) -> str:
    """Return a compact effective-config summary per configured channel.

    Lists both baseline-configured channels (from config.yaml) and
    state-introduced channels (present in state["channels"] with
    enabled:true but absent from config.yaml).  Each config value carries
    a provenance badge: ``[channel-override]``, ``[global-override]``, or
    no badge (from baseline).  State-introduced channels are marked
    ``[state-introduced]``.
    """
    if _state is None:
        return "nunchi-gate: state module not available"

    state_data = _state.load_state(state_path)
    global_overrides = _state.filter_overridable(state_data.get("global") or {})
    ch_states: dict[str, Any] = state_data.get("channels") or {}

    lines = [
        "nunchi-gate status",
        f"  state_path: {state_path}",
    ]
    if global_overrides:
        lines.append(f"  global overrides: {global_overrides}")
    else:
        lines.append("  global overrides: none")

    # Collect all channels to display: baseline-listed + state-introduced.
    baseline_channels = set(_channel_list_from_cfg(cfg))
    state_channels = set(ch_states.keys())
    all_channel_ids = sorted(baseline_channels | state_channels)

    if not all_channel_ids:
        lines.append("  (no channels configured in config.yaml or state)")
    else:
        for cid in all_channel_ids:
            is_state_introduced = cid not in baseline_channels
            eff = _state.merge_effective(
                cfg, state_data, {cid},
                _resolve_channel_config=resolve_channel_config,
            )
            ch_ov = _state.filter_overridable(ch_states.get(cid) or {})
            if eff is None:
                tag = "  [state-disabled]" if cid in ch_states else "  [not gated]"
                lines.append(f"\n  [{cid}]{tag}")
                continue
            intro_tag = "  [state-introduced]" if is_state_introduced else ""
            lines.append(f"\n  [{cid}]{intro_tag}")
            for key in ("enabled", "senders", "verbosity", "quiet_gateway_chatter", "fail_open", "model"):
                val = eff.get(key)
                if val is not None or key in ("enabled", "senders", "verbosity", "quiet_gateway_chatter", "fail_open"):
                    lines.append(f"    {key:<22} {_provenance(key, val, ch_ov, global_overrides)}")

    updated_at = state_data.get("updated_at")
    if updated_at:
        lines.append(
            f"\n  last updated: {updated_at} by {state_data.get('updated_by', '?')}"
        )
    return "\n".join(lines)


def _apply_override(
    state_data: dict[str, Any],
    target: str,  # "global" or a channel ID
    key: str,
    value: Any,
) -> dict[str, Any]:
    """Return a new state dict with the given override applied."""
    out: dict[str, Any] = dict(state_data)
    if target == "global":
        g = dict(out.get("global") or {})
        g[key] = value
        out["global"] = g
    else:
        channels = dict(out.get("channels") or {})
        ch = dict(channels.get(target) or {})
        ch[key] = value
        channels[target] = ch
        out["channels"] = channels
    return out


def _cmd_enable_disable(sub: str, rest: list[str], cfg: dict[str, Any], state_path: Path) -> str:
    if not rest:
        return f"nunchi: '{sub}' requires a channel ID or 'global'\n\n{_NUNCHI_USAGE}"
    if _state is None:
        return "nunchi-gate: state module not available"
    target = rest[0]
    state_data = _state.load_state(state_path)
    new_state = _apply_override(state_data, target, "enabled", sub == "enable")
    _state.save_state(state_path, new_state, updated_by="slash")
    scope = "global override" if target == "global" else f"channel {target}"
    return f"nunchi: {sub}d ({scope})"


def _cmd_senders(rest: list[str], cfg: dict[str, Any], state_path: Path) -> str:
    if not rest:
        return f"nunchi: 'senders' requires a value (all|humans|allowlist)\n\n{_NUNCHI_USAGE}"
    value = rest[0].lower()
    if value not in _VALID_SENDERS:
        return (
            f"nunchi: invalid senders value {value!r}; "
            f"must be one of: {', '.join(sorted(_VALID_SENDERS))}"
        )
    if _state is None:
        return "nunchi-gate: state module not available"
    target = rest[1] if len(rest) > 1 else "global"
    state_data = _state.load_state(state_path)
    new_state = _apply_override(state_data, target, "senders", value)
    _state.save_state(state_path, new_state, updated_by="slash")
    scope = "global override" if target == "global" else f"channel {target}"
    return f"nunchi: senders set to {value!r} ({scope})"


def _cmd_verbosity(rest: list[str], cfg: dict[str, Any], state_path: Path) -> str:
    if not rest:
        return f"nunchi: 'verbosity' requires a level (minimal|normal|debug)\n\n{_NUNCHI_USAGE}"
    value = rest[0].lower()
    if value not in _VALID_VERBOSITY:
        return (
            f"nunchi: invalid verbosity {value!r}; "
            f"must be one of: {', '.join(sorted(_VALID_VERBOSITY))}"
        )
    if _state is None:
        return "nunchi-gate: state module not available"
    target = rest[1] if len(rest) > 1 else "global"
    state_data = _state.load_state(state_path)
    new_state = _apply_override(state_data, target, "verbosity", value)
    _state.save_state(state_path, new_state, updated_by="slash")
    scope = "global override" if target == "global" else f"channel {target}"
    return f"nunchi: verbosity set to {value!r} ({scope})"


def _cmd_chatter(rest: list[str], cfg: dict[str, Any], state_path: Path) -> str:
    if not rest:
        return f"nunchi: 'chatter' requires a value (quiet|visible)\n\n{_NUNCHI_USAGE}"
    value = rest[0].lower()
    if value not in _VALID_CHATTER:
        return (
            f"nunchi: invalid chatter value {value!r}; "
            "must be one of: quiet, visible"
        )
    if _state is None:
        return "nunchi-gate: state module not available"
    target = rest[1] if len(rest) > 1 else "global"
    quiet = _VALID_CHATTER[value]
    state_data = _state.load_state(state_path)
    new_state = _apply_override(state_data, target, "quiet_gateway_chatter", quiet)
    _state.save_state(state_path, new_state, updated_by="slash")
    scope = "global override" if target == "global" else f"channel {target}"
    surfaced = "quiet" if quiet else "visible"
    return f"nunchi: gateway chatter set to {surfaced!r} ({scope})"


def _cmd_reset(rest: list[str], cfg: dict[str, Any], state_path: Path) -> str:
    if _state is None:
        return "nunchi-gate: state module not available"
    state_data = _state.load_state(state_path)

    if not rest or rest[0].lower() == "global":
        # Clear all overrides (global + every channel).
        new_state: dict[str, Any] = {}
        _state.save_state(state_path, new_state, updated_by="slash")
        return "nunchi: all overrides cleared"

    cid = rest[0]
    channels = dict(state_data.get("channels") or {})
    if cid in channels:
        del channels[cid]
        new_state = dict(state_data)
        new_state["channels"] = channels
        _state.save_state(state_path, new_state, updated_by="slash")
        return f"nunchi: overrides cleared for channel {cid}"
    return f"nunchi: no overrides found for channel {cid}"


def _nunchi_command(raw_args: str) -> str:
    """Handler for the /nunchi slash command.

    Subcommands
    -----------
    status
        Compact effective-config summary per configured channel, with a
        provenance badge showing whether each value comes from a runtime
        override or the baseline config.yaml.

    enable|disable <channel-id|global>
        Set ``enabled`` true/false for the given channel or globally.

    senders <all|humans|allowlist> [channel-id|global]
        Set the sender policy.  Defaults to the global override when no
        channel is given.

    verbosity <minimal|normal|debug> [channel-id|global]
        Set the log verbosity.  Defaults to the global override when no
        channel is given.

    chatter <quiet|visible> [channel-id|global]
        Control whether Hermes gateway chatter (busy-ACK bubbles, tool-progress
        receipts, the per-turn "• Grant spent" notice, and compression/status
        chatter) is visible in nunchi channels.  Defaults to quiet.  Final
        responses, credit warnings, and unrelated notices/status are never
        affected.

    reset [channel-id|global]
        With a channel ID: clear that channel's overrides.
        With 'global' or no argument: clear all overrides.

    This handler has NO implicit channel context — channel IDs must be
    supplied explicitly.  Mutations write to the state file via
    ``state.save_state`` with ``updated_by='slash'`` so the gate path
    and dashboard see consistent state.

    Trust chain (authorization boundary)
    ------------------------------------
    Authorization does NOT live in this plugin.  Hermes' command dispatcher
    is the authorization boundary: it decides whose "/nunchi ..." messages
    are routed to this handler at all.  The handler receives only the raw
    argument string — no sender identity, channel, or role — so per-user
    checks are structurally impossible here, and every invocation hermes
    forwards is equally privileged.  Operators who need to restrict who can
    reconfigure the gate must do so in hermes' command permissions, not in
    chat-visible gate settings.

    Two properties bound the blast radius of whatever hermes lets through:

    1. Whitelist: all mutations funnel through ``state.save_state`` and are
       consumed via ``filter_overridable`` / ``merge_effective``, so only
       ``OVERRIDABLE_KEYS`` (see ``state.py``) ever take effect.  Operator-
       only keys — ``binary``, ``log_path``, ``state_path``, ``agent_id``,
       ``mention_id``, ``aliases``, ``timeout_seconds`` — are unreachable
       from any slash input.  The slash surface itself can write only
       ``enabled``, ``senders``, ``verbosity``, and ``quiet_gateway_chatter``.
    2. Pinned target: state is written only to the ``state_path`` resolved
       from config.yaml; since ``state_path`` is not overridable, no chat or
       UI input can redirect where state lands.

    Note the gate hook is NOT part of this chain: with ``bypass_commands``
    enabled, ``_gate_event`` simply declines to gate "/"-prefixed message
    text — it never executes commands, so a message that merely looks like
    "/nunchi disable global" cannot mutate state through the gate path.
    Covered by ``tests/test_slash_command_authz.py``.
    """
    args = raw_args.strip().split()
    if not args:
        return _NUNCHI_USAGE

    sub = args[0].lower()
    rest = args[1:]

    try:
        cfg = _nunchi_config()
        state_path = _nunchi_state_path(cfg)

        if sub == "status":
            return _cmd_status(cfg, state_path)
        if sub in ("enable", "disable"):
            return _cmd_enable_disable(sub, rest, cfg, state_path)
        if sub == "senders":
            return _cmd_senders(rest, cfg, state_path)
        if sub == "verbosity":
            return _cmd_verbosity(rest, cfg, state_path)
        if sub == "chatter":
            return _cmd_chatter(rest, cfg, state_path)
        if sub == "reset":
            return _cmd_reset(rest, cfg, state_path)
        return f"nunchi: unknown subcommand {sub!r}\n\n{_NUNCHI_USAGE}"
    except Exception as exc:
        # Never raise — always return a human-readable error string.
        return f"nunchi: error: {exc}"


# Emitter name -> (the exact Hermes symbol we patch, the patcher).  Named so an
# operator can grep the register-time summary line straight back to the method,
# and so a future Hermes refactor's blast radius is greppable in one place.
_QUIET_EMITTER_PATCHES: tuple[tuple[str, str, Any], ...] = (
    ("tool_progress", "gateway.display_config.resolve_display_setting", _patch_display_resolver),
    ("status_chatter", "gateway.run._send_or_update_status_coro", _patch_status_sender),
    ("busy_ack", "GatewayRunner._handle_active_session_busy_message", _patch_busy_ack_handler),
    ("grant_spent_notice", "GatewayRunner._deliver_platform_notice", _patch_notice_handler),
)


def _install_quiet_room_patches() -> dict[str, bool]:
    """Install the four quiet-room emission patches and emit ONE INFO summary.

    Visibility contract (Zoe): a plugin-level monkeypatch must be portable but
    NOT invisible.  This emits one clear INFO line naming exactly which emitters
    are ACTIVE (suppressed for quiet channels) and which are INERT (target
    missing on this Hermes → that emitter stays VISIBLE), each tagged with the
    exact patched Hermes symbol so the mechanism is greppable, not magic.  The
    line also restates the suppression boundary.  Never raises.

    Returns a ``{emitter: installed?}`` map (used by tests / callers).
    """
    active: list[str] = []
    inert: list[str] = []
    results: dict[str, bool] = {}
    for name, target, patcher in _QUIET_EMITTER_PATCHES:
        try:
            ok = bool(patcher())
        except Exception:
            ok = False
        results[name] = ok
        (active if ok else inert).append(f"{name} ({target})")

    boundary = (
        "suppresses ONLY per-turn agent telemetry (busy-ACK, tool-progress, "
        "compression/status, grant-spent); gateway LIFECYCLE notices "
        "(♻️ Gateway online, update-available, goal-status) and credit WARNINGS "
        "(⚠ Credits, ✕/✓ Credit access) are never suppressed"
    )
    if inert:
        logger.info(
            "nunchi-gate quiet-room: installed emission suppression for quiet "
            "channels (key=quiet_gateway_chatter, per-channel + runtime-overridable) "
            "— ACTIVE: [%s]; INERT on this Hermes (emitter stays VISIBLE): [%s]; %s.",
            ", ".join(active) or "none",
            ", ".join(inert),
            boundary,
        )
    else:
        logger.info(
            "nunchi-gate quiet-room: installed emission suppression for quiet "
            "channels (key=quiet_gateway_chatter, per-channel + runtime-overridable) "
            "— ACTIVE: [%s]; %s.",
            ", ".join(active),
            boundary,
        )
    return results


def register(ctx):
    if _v2_plugin is None:
        raise RuntimeError("nunchi-gate V2 entrypoint is unavailable")
    initial_config = _nunchi_config()
    participant_id = str(
        initial_config.get("participant_id")
        or os.environ.get("NUNCHI_HERMES_PARTICIPANT_ID")
        or "hermes"
    ).strip()

    def resolved_profile_config(source: Any, gateway: Any) -> dict[str, Any]:
        config = dict(_nunchi_config())
        full_config = _load_config()
        platform = _platform_name(source)
        try:
            display_module = importlib.import_module("gateway.display_config")
            resolve_display_setting = getattr(
                display_module, "resolve_display_setting"
            )
            platform_streaming = resolve_display_setting(
                full_config, platform, "streaming"
            )
        except Exception:
            platform_streaming = None
        raw_streaming = full_config.get("streaming", {})
        if isinstance(raw_streaming, dict):
            global_streaming = bool(raw_streaming.get("enabled", False)) and str(
                raw_streaming.get("transport", "auto")
            ).strip().lower() != "off"
        else:
            global_streaming = bool(raw_streaming)
        effective_streaming = (
            global_streaming
            if platform_streaming is None
            else bool(platform_streaming)
        )
        config["_host_streaming_disabled"] = not effective_streaming
        model_config = full_config.get("model")
        openai_runtime = (
            str(model_config.get("openai_runtime") or "").strip().lower()
            if isinstance(model_config, dict)
            else ""
        )
        proxy_resolver = getattr(gateway, "_get_proxy_url", None)
        try:
            proxy_url = proxy_resolver() if callable(proxy_resolver) else None
        except Exception:
            proxy_url = "unknown"
        config["_host_effect_runtime_supported"] = (
            openai_runtime != "codex_app_server" and not proxy_url
        )
        return config

    def profile_config(event: Any, gateway: Any) -> dict[str, Any]:
        source = getattr(event, "source", None)
        resolve_home = getattr(gateway, "_resolve_profile_home_for_source", None)
        profile_home = resolve_home(source) if callable(resolve_home) else None
        if profile_home:
            try:
                run_module = importlib.import_module("gateway.run")
                profile_scope = getattr(run_module, "_profile_runtime_scope")
                with profile_scope(profile_home):
                    return resolved_profile_config(source, gateway)
            except Exception:
                return {}
        return resolved_profile_config(source, gateway)

    def schedule_redispatch(event: Any, gateway: Any) -> None:
        source = getattr(event, "source", None)
        adapter_for_source = getattr(gateway, "_adapter_for_source", None)
        adapter = adapter_for_source(source) if callable(adapter_for_source) else None
        handle_message = getattr(adapter, "handle_message", None)
        if not callable(handle_message):
            raise RuntimeError("Hermes adapter redispatch seam is unavailable")
        loop = asyncio.get_running_loop()
        session_resolver = getattr(gateway, "_session_key_for_source", None)
        session_key = str(
            session_resolver(source) if callable(session_resolver) else ""
        )

        async def owned_redispatch() -> None:
            try:
                pending: Any = handle_message(event)
                accepted = await pending
                if accepted is False:
                    await asyncio.to_thread(
                        _v2_plugin._CONTROLLER.abort_participant_turn,
                        session_key,
                    )
            except BaseException:
                await asyncio.to_thread(
                    _v2_plugin._CONTROLLER.abort_participant_turn,
                    session_key,
                )
                raise

        task = loop.create_task(owned_redispatch())
        background = getattr(adapter, "_background_tasks", None)
        if isinstance(background, set):
            background.add(task)
            task.add_done_callback(background.discard)

    _v2_plugin.configure(
        config_loader=profile_config,
        participant_id=participant_id,
        schedule_redispatch=schedule_redispatch,
    )
    _v2_plugin.register(ctx)
