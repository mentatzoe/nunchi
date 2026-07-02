"""Runtime state overrides for nunchi-gate.

Provides hot, atomic JSON state that layers per-channel and global overrides
on top of the static config.yaml baseline without requiring a Hermes restart.

State file shape
----------------
::

    {
        "global": {<overridable keys only>},
        "channels": {
            "<channel-id>": {<overridable keys only>},
            ...
        },
        "updated_at": "<ISO-8601 string>",
        "updated_by": "slash" | "dashboard"
    }

Security note — config.yaml-only keys
--------------------------------------
Only ``OVERRIDABLE_KEYS`` can be written via state (slash command or dashboard
API).  The following config.yaml keys are intentionally excluded:

    binary, timeout_seconds, log_path, agent_id, mention_id, state_path

Rationale: no chat or UI surface should be able to redirect the
``nunchi-channel`` executable (``binary``), change the bot's identity
(``agent_id`` / ``mention_id``), alter where receipts are written
(``log_path``), change classifier timeouts (``timeout_seconds``), or
redirect the state file itself (``state_path``).  These operator-only
settings must survive unchanged in ``config.yaml``.
"""
from __future__ import annotations

import datetime
import json
import os
import tempfile
from pathlib import Path
from typing import Any

# Keys that callers (slash command, dashboard) are allowed to override.
# Anything NOT in this set is silently dropped from incoming override dicts.
OVERRIDABLE_KEYS: frozenset[str] = frozenset(
    {
        "enabled",
        "senders",
        "allow_from",
        "verbosity",
        "fail_open",
        "model",
        "pinned_rules_file",
    }
)

# State file mtime cache: abs-path-str -> (mtime_float, parsed-dict)
_STATE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def filter_overridable(d: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of *d* containing only ``OVERRIDABLE_KEYS``.

    Keys absent from ``OVERRIDABLE_KEYS`` — including ``binary``,
    ``timeout_seconds``, ``log_path``, ``agent_id``, ``mention_id``, and
    ``state_path`` — are silently dropped.  This enforces the security
    whitelist at the point of ingestion so both the slash command and the
    dashboard API inherit it without duplicating the check.
    """
    return {k: v for k, v in d.items() if k in OVERRIDABLE_KEYS}


def load_state(path: Path) -> dict[str, Any]:
    """Load the state file at *path* with mtime-based caching.

    Returns an empty dict when the file is absent, empty, or malformed —
    the gate degrades gracefully to the baseline config in all of these
    cases.  No exception is ever raised to the caller; parse errors are
    swallowed silently (the gate must not crash because the state file is
    temporarily invalid while being written by another process).

    Cache invalidation is mtime-driven: if the on-disk mtime differs from
    the cached mtime, the file is re-read.  Callers should not inspect the
    mtime themselves.
    """
    path_str = str(path)
    try:
        if not path.exists():
            return {}
        mtime = path.stat().st_mtime
        if path_str in _STATE_CACHE:
            cached_mtime, cached_data = _STATE_CACHE[path_str]
            if cached_mtime == mtime:
                return cached_data
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}
    except Exception:
        # Malformed JSON, permission error, race during write — return empty.
        return {}
    _STATE_CACHE[path_str] = (mtime, data)
    return data


def save_state(path: Path, state: dict[str, Any], *, updated_by: str) -> None:
    """Atomically write *state* to *path*, stamping ``updated_at`` / ``updated_by``.

    Uses a temporary file in the same directory followed by ``os.replace()``
    for atomic rename — readers always see a complete file or the previous
    version, never a partial write.  The mtime cache for *path* is invalidated
    after the rename so the next ``load_state`` reads the fresh content.

    ``updated_at`` is stamped by this function (UTC ISO-8601 with timezone);
    pure merge functions such as ``merge_effective`` must not invent clock
    reads — only ``save_state`` touches the clock.
    """
    out: dict[str, Any] = dict(state)
    out["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    out["updated_by"] = updated_by
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path_str = tempfile.mkstemp(
        dir=path.parent,
        prefix=".nunchi-state-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, sort_keys=True, default=str)
            f.write("\n")
        os.replace(tmp_path_str, path)
        # Invalidate the mtime cache so the next load_state call re-reads.
        _STATE_CACHE.pop(str(path), None)
    except Exception:
        try:
            os.unlink(tmp_path_str)
        except OSError:
            pass
        raise


def merge_effective(
    baseline_cfg: dict[str, Any],
    state: dict[str, Any],
    channel_ids: set[str],
    *,
    _resolve_channel_config: Any = None,
) -> dict[str, Any] | None:
    """Build the effective per-channel config by layering state overrides.

    Layering order (lowest to highest precedence):

    1. ``baseline_cfg``          — raw ``config.yaml`` nunchi block.
    2. ``state["global"]``       — runtime global overrides (slash / dashboard).
    3. ``resolve_channel_config`` result — per-channel keys from ``config.yaml``.
    4. ``state["channels"][id]`` — runtime per-channel overrides (slash / dashboard).

    State-introduced channels
    ~~~~~~~~~~~~~~~~~~~~~~~~~
    If ``resolve_channel_config`` returns ``None`` for the event's channel IDs
    (i.e. the channel is not listed in ``config.yaml``) but
    ``state["channels"][<id>]`` exists with an **explicit** ``enabled: true``
    value, the channel IS gated: effective config = global-patched baseline +
    the state channel entry.  This allows operators to hot-add a new channel
    with ``/nunchi enable <channel-id>`` without editing ``config.yaml`` or
    restarting Hermes.

    State-disabled channels
    ~~~~~~~~~~~~~~~~~~~~~~~
    If ``state["channels"][<id>]`` contains ``enabled: false``, the channel is
    suppressed even if the baseline config.yaml would gate it.  This lets an
    operator use ``/nunchi disable <channel-id>`` as a runtime circuit-breaker.

    Parameters
    ----------
    baseline_cfg:
        The raw nunchi config dict as returned by ``_nunchi_config()``.
    state:
        The parsed state file dict as returned by ``load_state()``.
    channel_ids:
        The set of channel IDs extracted from the event.
    _resolve_channel_config:
        Optional callable with the same signature as
        ``resolve_channel_config(cfg, channel_ids) -> dict | None``.
        When provided, it is called after the global overlay to apply
        ``config.yaml`` per-channel merges.  When ``None``, the
        global-overlay result is used directly (useful in isolated tests).

    Note: callers pass ``channel_ids`` in; this function does not read the
    clock, inspect the filesystem, or modify the cache.
    """
    # Steps 1 + 2: start from a shallow copy of the baseline and apply
    # whitelisted global state overrides.
    patched: dict[str, Any] = dict(baseline_cfg)
    global_overrides = filter_overridable(state.get("global") or {})
    if global_overrides:
        patched.update(global_overrides)

    # Step 3: per-channel config from config.yaml (handles map form / legacy
    # form / wildcards).  May return None when the channel is not configured.
    if _resolve_channel_config is not None:
        resolved: dict[str, Any] | None = _resolve_channel_config(patched, channel_ids)
    else:
        # No resolver provided — treat patched as the resolved config.
        resolved = patched

    # Step 4: runtime per-channel overrides from state["channels"].
    # Exact-match only (no wildcards in state; the slash command requires an
    # explicit channel ID).
    ch_state: dict[str, Any] = state.get("channels") or {}
    matching_entry: dict[str, Any] | None = None
    for cid in channel_ids:
        if cid in ch_state:
            matching_entry = filter_overridable(ch_state[cid])
            break

    if matching_entry is not None:
        state_enabled = matching_entry.get("enabled")

        if resolved is None:
            # Baseline did not gate this channel.  Gate it only if the state
            # entry explicitly introduces it with ``enabled: true``.
            if state_enabled is True:
                introduced: dict[str, Any] = dict(patched)
                introduced.update(matching_entry)
                return introduced
            # No explicit enabled:true → not gated.
            return None
        else:
            # Baseline matched.  State can suppress (enabled:false) or overlay.
            if state_enabled is False:
                return None
            resolved = dict(resolved)
            resolved.update(matching_entry)
    elif resolved is None:
        return None

    return resolved
