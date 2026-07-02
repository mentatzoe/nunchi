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
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter()

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
        for cid in all_cids:
            try:
                eff = state.merge_effective(
                    cfg, overrides, {cid},
                    _resolve_channel_config=resolve_fn,
                )
                effective[cid] = eff if eff is not None else None
            except Exception as exc:
                log.warning("nunchi dashboard: merge_effective failed for %s: %s", cid, exc)
                effective[cid] = None

    return {"baseline": cfg, "overrides": overrides, "effective": effective}


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

class StatePatch(BaseModel):
    global_: Optional[dict[str, Any]] = None
    channels: Optional[dict[str, dict[str, Any]]] = None

    class Config:
        # Allow "global" as the JSON key (maps to global_ in Python).
        populate_by_name = True

    @classmethod
    def model_validate_json_body(cls, body: dict) -> "StatePatch":
        # Re-map "global" JSON key -> "global_" field
        mapped = dict(body)
        if "global" in mapped:
            mapped["global_"] = mapped.pop("global")
        return cls(**mapped)


@router.put("/state")
def put_state(body: dict[str, Any]) -> dict[str, Any]:
    """Apply whitelist-validated overrides.  Only OVERRIDABLE_KEYS are accepted."""
    state = _get_state_mod()
    if state is None:
        raise HTTPException(status_code=503, detail="state module unavailable")

    cfg = _nunchi_config()
    sp = _state_path(cfg)

    try:
        current = state.load_state(sp)
    except Exception:
        current = {}

    out: dict[str, Any] = dict(current)

    # Apply global overrides (whitelist-enforced).
    if "global" in body and body["global"] is not None:
        g = dict(out.get("global") or {})
        g.update(state.filter_overridable(body["global"]))
        out["global"] = g

    # Apply per-channel overrides (whitelist-enforced per channel).
    if "channels" in body and body["channels"] is not None:
        channels_patch = body["channels"]
        if not isinstance(channels_patch, dict):
            raise HTTPException(status_code=422, detail="'channels' must be an object")
        channels = dict(out.get("channels") or {})
        for cid, ch_patch in channels_patch.items():
            if not isinstance(ch_patch, dict):
                continue
            ch = dict(channels.get(cid) or {})
            ch.update(state.filter_overridable(ch_patch))
            channels[cid] = ch
        out["channels"] = channels

    try:
        state.save_state(sp, out, updated_by="dashboard")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to save state: {exc}")

    return {"status": "ok", "state_path": str(sp)}


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
