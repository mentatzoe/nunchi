"""Nunchi gate dashboard API routes.

Mounted at ``/api/plugins/nunchi/`` by the hermes dashboard plugin system.

This file runs inside hermes' venv, so FastAPI and Pydantic are available.
Keep it thin: load state via the sibling ``state.py`` module, read the nunchi
config block via ``hermes_cli.config``, and tail the log file for receipts.
No business logic lives here — the gate path in ``__init__.py`` is the
source of truth.

Routes
------
GET  /state
    Returns the current nunchi configuration as three views:
      ``baseline``  — the config.yaml nunchi block (no state overlays)
      ``overrides`` — the raw state file content (global + channel entries)
      ``effective`` — merged effective config per configured channel

PUT  /state
    Body: ``{"global": {...}, "channels": {"<id>": {...}}}``
    Applies whitelist-validated overrides via ``state.save_state``.
    Only ``OVERRIDABLE_KEYS`` are accepted; unknown keys are silently dropped.

GET  /receipts?limit=N
    Tail-parse the configured ``log_path`` JSONL (default 50, cap 500).
    Returns newest-first.  Malformed lines are skipped without error.

Security note: plugin HTTP routes go through the dashboard's session-token
auth middleware, just like core routes.  No additional auth is needed here.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

log = logging.getLogger(__name__)

# Increment when the response contract changes so old JS can detect a mismatch.
PLUGIN_API_VERSION = "2"

router = APIRouter()

# ---------------------------------------------------------------------------
# Channel directory: resolve human names from ~/.hermes/channel_directory.json
# ---------------------------------------------------------------------------

_CHANNEL_DIR_PATH = Path("~/.hermes/channel_directory.json").expanduser()

# Cache: (mtime_float, id_to_display_name_dict) | None
_CHANNEL_DIR_CACHE: tuple[float, dict[str, str]] | None = None


def _load_channel_names(path: Path | None = None) -> dict[str, str]:
    """Return a mapping of channel-id → display name from the channel directory.

    Display name format: ``"{guild} / #{name}"`` when a guild is present, else
    ``"#{name}"``.  Tolerates absence (returns ``{}``) and parse errors.

    Uses mtime-based caching: re-reads only when the file changes on disk.
    """
    global _CHANNEL_DIR_CACHE
    if path is None:
        path = _CHANNEL_DIR_PATH
    try:
        if not path.exists():
            return {}
        mtime = path.stat().st_mtime
        if _CHANNEL_DIR_CACHE is not None:
            cached_mtime, cached_names = _CHANNEL_DIR_CACHE
            if cached_mtime == mtime:
                return cached_names
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        names: dict[str, str] = {}
        platforms = data.get("platforms") or {}
        for entries in platforms.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                cid = str(entry.get("id") or "").strip()
                name = str(entry.get("name") or "").strip()
                guild = str(entry.get("guild") or "").strip()
                if not cid or not name:
                    continue
                if guild:
                    names[cid] = f"{guild} / #{name}"
                else:
                    names[cid] = f"#{name}"
        _CHANNEL_DIR_CACHE = (mtime, names)
        return names
    except Exception:
        return {}

# ---------------------------------------------------------------------------
# Helpers: load sibling modules without relying on package imports.
# ---------------------------------------------------------------------------

_state_mod: Any = None
_plugin_init_mod: Any = None


def _get_state_mod() -> Any:
    global _state_mod
    if _state_mod is None:
        state_file = Path(__file__).parent.parent / "state.py"
        spec = importlib.util.spec_from_file_location("nunchi_gate_state_api", state_file)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            _state_mod = mod
    return _state_mod


def _get_plugin_mod() -> Any:
    global _plugin_init_mod
    if _plugin_init_mod is None:
        init_file = Path(__file__).parent.parent / "__init__.py"
        spec = importlib.util.spec_from_file_location("nunchi_gate_api", init_file)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            _plugin_init_mod = mod
    return _plugin_init_mod


def _nunchi_config() -> dict[str, Any]:
    """Load the nunchi block from hermes config.yaml."""
    try:
        p = _get_plugin_mod()
        if p is not None:
            return p._nunchi_config()
    except Exception:
        pass
    return {}


def _state_path(cfg: dict[str, Any]) -> Path:
    default = "~/.hermes/nunchi-gate.state.json"
    return Path(str(cfg.get("state_path") or default)).expanduser()


def _log_path(cfg: dict[str, Any]) -> Path | None:
    raw = cfg.get("log_path", "~/.hermes/logs/nunchi-gate.jsonl")
    if not raw or str(raw).strip().lower() in {"0", "false", "no", "off", "none", ""}:
        return None
    return Path(str(raw).strip()).expanduser()


# ---------------------------------------------------------------------------
# GET /state
# ---------------------------------------------------------------------------

@router.get("/state")
def get_state() -> dict[str, Any]:
    """Return baseline config, raw overrides, and per-channel effective config."""
    state = _get_state_mod()
    cfg = _nunchi_config()
    sp = _state_path(cfg)

    overrides: dict[str, Any] = {}
    if state is not None:
        try:
            overrides = state.load_state(sp)
        except Exception as exc:
            log.warning("nunchi dashboard: failed to load state: %s", exc)

    effective: dict[str, Any] = {}
    if state is not None:
        plugin = _get_plugin_mod()
        resolve_fn = getattr(plugin, "resolve_channel_config", None) if plugin else None
        # Combine baseline-listed channels with state-introduced channels so
        # the effective view shows all currently active surfaces.
        channels_raw = cfg.get("channels") or cfg.get("channel_ids")
        if isinstance(channels_raw, dict):
            baseline_cids = set(k for k in channels_raw if k != "*")
        else:
            baseline_cids = set(_coerce_list_simple(channels_raw))
        state_cids = set((overrides.get("channels") or {}).keys())
        all_cids = sorted(baseline_cids | state_cids)
        # mn1: only expose the overridable keys (+ enabled) in effective so
        # operator-only fields (binary, timeout_seconds, log_path, agent_id,
        # mention_id, state_path) are never returned to the dashboard JS.
        effective_keys = state.OVERRIDABLE_KEYS  # enabled is already in the set
        for cid in all_cids:
            try:
                eff = state.merge_effective(
                    cfg, overrides, {cid},
                    _resolve_channel_config=resolve_fn,
                )
                if eff is not None:
                    eff = {k: v for k, v in eff.items() if k in effective_keys}
                effective[cid] = eff
            except Exception as exc:
                log.warning("nunchi dashboard: merge_effective failed for %s: %s", cid, exc)
                effective[cid] = None

    channel_names = _load_channel_names()
    return {
        "baseline": cfg,
        "overrides": overrides,
        "effective": effective,
        "channel_names": channel_names,
        "api_version": PLUGIN_API_VERSION,
    }


def _coerce_list_simple(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip() and p.strip() != "*"]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if item is not None and str(item).strip() not in ("", "*")]
    return []


# ---------------------------------------------------------------------------
# PUT /state
# ---------------------------------------------------------------------------

@router.put("/state")
def put_state(body: dict[str, Any]) -> dict[str, Any]:
    """Apply overrides via apply_state_patch (whitelist, null-delete, replace-empty).

    Delegates all merge/reset/delete semantics to ``state.apply_state_patch``
    so the logic is tested in isolation.  The body must be a JSON object with
    optional ``"global"`` and ``"channels"`` keys.
    """
    state = _get_state_mod()
    if state is None:
        raise HTTPException(status_code=503, detail="state module unavailable")

    cfg = _nunchi_config()
    sp = _state_path(cfg)

    try:
        current = state.load_state(sp)
    except Exception:
        current = {}

    try:
        audit = state.audit_patch(body)
        new_state = state.apply_state_patch(current, body, cfg)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"invalid patch: {exc}")

    try:
        state.save_state(sp, new_state, updated_by="dashboard")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to save state: {exc}")

    # Re-read the saved file to return the canonical overrides to the caller.
    # The dashboard JS diffs this against what it sent to detect silent failures.
    saved = state.load_state(sp)
    applied_state: dict[str, Any] = {}
    if "global" in saved:
        applied_state["global"] = saved["global"]
    if "channels" in saved:
        applied_state["channels"] = saved["channels"]

    return {
        "ok": True,
        "applied_state": applied_state,
        "rejected_keys": audit["rejected"],
    }


# ---------------------------------------------------------------------------
# GET /receipts
# ---------------------------------------------------------------------------

@router.get("/receipts")
def get_receipts(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
    """Tail the gate JSONL log; returns newest-first, up to *limit* entries."""
    cfg = _nunchi_config()
    lp = _log_path(cfg)
    if lp is None:
        return {"receipts": [], "log_path": None, "note": "logging disabled"}
    if not lp.exists():
        return {"receipts": [], "log_path": str(lp), "note": "log file not found"}

    receipts: list[dict[str, Any]] = []
    try:
        lines = lp.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    receipts.append(obj)
            except json.JSONDecodeError:
                continue  # skip malformed lines
            if len(receipts) >= limit:
                break
    except Exception as exc:
        log.warning("nunchi dashboard: failed to read receipts: %s", exc)
        return {"receipts": [], "log_path": str(lp), "error": str(exc)}

    return {"receipts": receipts, "log_path": str(lp)}
