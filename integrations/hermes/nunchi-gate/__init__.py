"""Nunchi admission gate for Hermes gateway messages.

Install shape:
- Hermes calls this plugin through the synchronous ``pre_gateway_dispatch`` hook.
- The plugin is deliberately channel-scoped, so rollout can start in a smoke lane.
- The payload targets nunchi's *channel adapter* (``nunchi-channel``): trigger
  with author/author_kind/message_id, recent history parsed from the
  backfilled ``event.channel_context``, and the agent's id + mention_id.
- A ``silent`` directive suppresses the Hermes reply via ``{"action": "skip"}``;
  everything else allows the normal Hermes agent path to continue.

Config block (in Hermes config.yaml):

    nunchi:
      # enabled (bool, default false) — gate is inactive unless explicitly enabled.
      enabled: true

      # platforms (str or list, default "discord") — platform names to gate.
      # Use "*" to gate all platforms regardless of name.
      platforms: discord

      # channels (str or list of chat-ids, REQUIRED unless "*") — only these
      # channel/chat IDs are gated.  Use "*" to gate every channel on the
      # matched platform(s).
      channels: "1518384310321811456"

      # agent_id (str, default "agent") — the Hermes agent's display name as it
      # appears in channel history [bot] tags.  Operators MUST set this to the
      # bot's actual display name; the default is intentionally generic.
      agent_id: my-bot

      # mention_id (str, optional) — Discord mention snowflake included in the
      # payload so the classifier can detect direct @-mentions.
      # mention_id: "1496355876234199040"

      # binary (str, optional) — path to the nunchi-channel executable.
      # Defaults to shutil.which("nunchi-channel") or /usr/local/bin/nunchi-channel.
      # binary: /usr/local/bin/nunchi-channel

      # model (str, optional) — when set, NUNCHI_CLASSIFIER_MODEL is exported into
      # the subprocess environment, overriding any inherited value.  Useful for
      # selecting a non-default classifier model without touching the system env.
      # model: anthropic/claude-opus-4-5

      # pinned_rules_file (str, optional) — path to a text file whose contents are
      # passed as "pinned_rules" in the payload on every gate invocation.  The file
      # is read lazily and cached with an mtime check so edits take effect without
      # restarting Hermes.
      # pinned_rules_file: ~/.hermes/nunchi-pinned-rules.md

      # timeout_seconds (number, default 30) — subprocess timeout; values < 1 are
      # clamped to 1 second.
      timeout_seconds: 30

      # fail_open (bool, default true) — when true, classifier errors allow the
      # Hermes reply through.  Set to false for strict gating.
      fail_open: true

      # bypass_commands (bool, default true) — skip the gate for messages that
      # start with "/" (slash commands).
      bypass_commands: true

      # log_path (str, default ~/.hermes/logs/nunchi-gate.jsonl) — append-only
      # JSONL file recording every gated message.  Set to "" or false to disable.
      log_path: ~/.hermes/logs/nunchi-gate.jsonl

Legacy support:
- Config block ``turnaware:`` is accepted when ``nunchi:`` is absent and a
  deprecation warning is emitted.  Rename the block to migrate.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PLUGIN_NAME = "nunchi-gate"
_DEFAULT_BINARY = shutil.which("nunchi-channel") or "/usr/local/bin/nunchi-channel"
_DEFAULT_LOG_PATH = "~/.hermes/logs/nunchi-gate.jsonl"
_DEFAULT_TIMEOUT_SECONDS = 30
_SPEAK_VERDICTS = {"SPEAK", "ASK", "ACK"}

# One backfilled channel_context line: "[DisplayName] content" with an
# optional " [bot]" tag inside the brackets.
_CONTEXT_LINE = re.compile(r"^\[(?P<name>[^\]]+?)(?P<bot_tag>\s+\[bot\])?\]\s*(?P<content>.+)$")

# Pinned-rules file cache: maps absolute path string -> (mtime, content)
_PINNED_RULES_CACHE: dict[str, tuple[float, str]] = {}


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

    payload: dict[str, Any] = {"trigger": trigger, "agent": agent}
    if history:
        payload["history"] = history

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

    channels = set(_coerce_list(cfg.get("channels") or cfg.get("channel_ids")))
    if not channels:
        return False
    if "*" not in channels and not (_channel_ids(source) & channels):
        return False

    text = str(getattr(event, "text", "") or "")
    return bool(text.strip())


def _gate_event(event: Any, gateway: Any = None, session_store: Any = None, **_: Any):
    cfg = _nunchi_config()
    if not _should_gate(event, cfg):
        return None

    source = getattr(event, "source", None)
    started = time.time()
    agent_id = str(cfg.get("agent_id") or "agent").strip() or "agent"
    history = _parse_channel_context(event, agent_id)
    payload = _build_payload(event, cfg, history)
    base_log = {
        "ts": started,
        "platform": _platform_name(source),
        "channel_ids": sorted(_channel_ids(source)),
        "message_id": getattr(event, "message_id", None),
        "payload_keys": sorted(payload.keys()),
        "history_len": len(history),
        "trigger_author": payload["trigger"].get("author"),
        "trigger_author_kind": payload["trigger"].get("author_kind"),
    }

    try:
        result = _run_nunchi(payload, cfg)
        verdict = str(result.get("verdict") or "").upper()
        elapsed_ms = round((time.time() - started) * 1000)
        log_entry = {
            **base_log,
            "elapsed_ms": elapsed_ms,
            "verdict": verdict,
            "silent": result.get("silent"),
            "classifier_model": result.get("classifier_model"),
            "reasons": (result.get("reasons") or [])[:3],
        }
        if result.get("silent") is True or verdict == "PASS":
            log_entry["action"] = "skip"
            _write_gate_log(log_entry, cfg)
            logger.info("nunchi-gate PASS -> skip channel_ids=%s", log_entry["channel_ids"])
            return {"action": "skip", "reason": "nunchi:PASS"}
        if verdict in _SPEAK_VERDICTS:
            log_entry["action"] = "allow"
            _write_gate_log(log_entry, cfg)
            logger.info("nunchi-gate %s -> allow channel_ids=%s", verdict, log_entry["channel_ids"])
            return None
        raise RuntimeError(f"unknown nunchi verdict {verdict!r}")
    except Exception as exc:
        fail_open = _coerce_bool(cfg.get("fail_open"), default=True)
        log_entry = {
            **base_log,
            "elapsed_ms": round((time.time() - started) * 1000),
            "action": "allow" if fail_open else "skip",
            "error": str(exc)[:500],
            "fail_open": fail_open,
        }
        _write_gate_log(log_entry, cfg)
        logger.warning("nunchi-gate error (%s); fail_open=%s", exc, fail_open)
        if fail_open:
            return None
        return {"action": "skip", "reason": "nunchi:error"}


def register(ctx):
    ctx.register_hook("pre_gateway_dispatch", _gate_event)
