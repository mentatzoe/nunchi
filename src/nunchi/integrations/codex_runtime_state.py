"""Hot, atomic runtime policy for the Codex room integration.

The operator TOML and environment remain the baseline for process-level
settings.  This module owns the smaller set of presence controls that may be
changed while the room runner is live, including per-channel overrides used by
the Codex configuration app.
"""

from __future__ import annotations

import datetime
import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


STATE_VERSION = 1
SENDERS = frozenset({"all", "humans", "allowlist"})
VERBOSITIES = frozenset({"minimal", "normal", "debug"})
OVERRIDABLE_KEYS = frozenset(
    {
        "enabled",
        "senders",
        "allow_from",
        "verbosity",
        "model",
        "pinned_rules",
    }
)
DEFAULT_POLICY: dict[str, Any] = {
    "enabled": True,
    "senders": "all",
    "allow_from": [],
    "verbosity": "normal",
    "model": None,
    "pinned_rules": None,
}


class RuntimeStateError(ValueError):
    """Raised when persisted or incoming runtime state is invalid."""


def default_state_path(
    environ: Mapping[str, str] | None = None,
    *,
    home: Path | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    raw = env.get("NUNCHI_RUNNER_STATE") or env.get("NUNCHI_CODEX_STATE")
    if raw:
        return Path(raw).expanduser()
    root = home if home is not None else Path.home()
    return root / ".nunchi" / "codex-room.state.json"


def _dedupe_strings(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _normalize_value(key: str, value: Any) -> Any:
    if key == "enabled":
        if not isinstance(value, bool):
            raise RuntimeStateError("enabled must be a boolean")
        return value

    if key == "senders":
        text = str(value).strip().lower()
        if text not in SENDERS:
            raise RuntimeStateError("senders must be all, humans, or allowlist")
        return text

    if key == "verbosity":
        text = str(value).strip().lower()
        if text not in VERBOSITIES:
            raise RuntimeStateError("verbosity must be minimal, normal, or debug")
        return text

    if key == "allow_from":
        if isinstance(value, str):
            values = value.replace(",", "\n").splitlines()
        elif isinstance(value, (list, tuple, set, frozenset)):
            values = value
        else:
            raise RuntimeStateError("allow_from must be a string or list of strings")
        out = _dedupe_strings(values)
        if len(out) > 200:
            raise RuntimeStateError("allow_from cannot contain more than 200 entries")
        return out

    if key == "model":
        text = str(value).strip()
        if not text:
            return None
        if len(text) > 256:
            raise RuntimeStateError("model cannot exceed 256 characters")
        return text

    if key == "pinned_rules":
        text = str(value).strip()
        if not text:
            return None
        if len(text) > 20_000:
            raise RuntimeStateError("pinned_rules cannot exceed 20000 characters")
        return text

    raise RuntimeStateError(f"unsupported runtime key: {key}")


def _normalize_scope(scope: Mapping[str, Any], *, location: str) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in scope.items():
        if key not in OVERRIDABLE_KEYS:
            raise RuntimeStateError(f"unsupported runtime key: {location}.{key}")
        if value is None:
            continue
        normalized_value = _normalize_value(key, value)
        if normalized_value is not None:
            normalized[key] = normalized_value
    return normalized


def _validate_channel_id(value: Any) -> str:
    channel_id = str(value).strip()
    if not channel_id:
        raise RuntimeStateError("channel id cannot be empty")
    if any(ch.isspace() for ch in channel_id):
        raise RuntimeStateError("channel id cannot contain whitespace")
    if len(channel_id) > 128:
        raise RuntimeStateError("channel id cannot exceed 128 characters")
    return channel_id


def normalize_state(raw: Mapping[str, Any]) -> dict[str, Any]:
    version = raw.get("version", STATE_VERSION)
    if version != STATE_VERSION:
        raise RuntimeStateError(f"unsupported runtime state version: {version!r}")

    out: dict[str, Any] = {"version": STATE_VERSION}
    global_raw = raw.get("global")
    if global_raw is not None:
        if not isinstance(global_raw, Mapping):
            raise RuntimeStateError("global runtime state must be an object")
        normalized_global = _normalize_scope(global_raw, location="global")
        if normalized_global:
            out["global"] = normalized_global

    channels_raw = raw.get("channels")
    if channels_raw is not None:
        if not isinstance(channels_raw, Mapping):
            raise RuntimeStateError("channels runtime state must be an object")
        channels: dict[str, dict[str, Any]] = {}
        for raw_channel_id, channel_raw in channels_raw.items():
            channel_id = _validate_channel_id(raw_channel_id)
            if not isinstance(channel_raw, Mapping):
                raise RuntimeStateError(f"channels.{channel_id} must be an object")
            normalized = _normalize_scope(channel_raw, location=f"channels.{channel_id}")
            if normalized:
                channels[channel_id] = normalized
        if channels:
            out["channels"] = channels

    if isinstance(raw.get("updated_at"), str):
        out["updated_at"] = raw["updated_at"]
    if isinstance(raw.get("updated_by"), str):
        out["updated_by"] = raw["updated_by"]
    return out


def load_state(path: Path) -> dict[str, Any]:
    """Load and validate state; absence is empty, corruption is explicit."""
    try:
        raw_text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"version": STATE_VERSION}
    except OSError as exc:
        raise RuntimeStateError(f"cannot read runtime state {path}: {exc}") from exc
    if not raw_text.strip():
        raise RuntimeStateError(f"runtime state {path} is empty")
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeStateError(f"invalid runtime state JSON in {path}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise RuntimeStateError("runtime state root must be an object")
    return normalize_state(raw)


def apply_patch(
    current: Mapping[str, Any],
    patch: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Apply null-delete/empty-reset semantics and report rejected keys."""
    normalized_current = normalize_state(current)
    out: dict[str, Any] = {"version": STATE_VERSION}
    if normalized_current.get("global"):
        out["global"] = dict(normalized_current["global"])
    if normalized_current.get("channels"):
        out["channels"] = {
            channel_id: dict(values)
            for channel_id, values in normalized_current["channels"].items()
        }

    rejected = [str(key) for key in patch if key not in {"global", "channels"}]

    if "global" in patch:
        global_patch = patch["global"]
        if not isinstance(global_patch, Mapping):
            raise RuntimeStateError("global patch must be an object")
        if not global_patch:
            out.pop("global", None)
        else:
            values = dict(out.get("global") or {})
            for key, value in global_patch.items():
                if key not in OVERRIDABLE_KEYS:
                    rejected.append(f"global.{key}")
                    continue
                normalized = None if value is None else _normalize_value(key, value)
                if normalized is None:
                    values.pop(key, None)
                else:
                    values[key] = normalized
            if values:
                out["global"] = values
            else:
                out.pop("global", None)

    if "channels" in patch:
        channels_patch = patch["channels"]
        if not isinstance(channels_patch, Mapping):
            raise RuntimeStateError("channels patch must be an object")
        if not channels_patch:
            out.pop("channels", None)
        else:
            channels = {
                channel_id: dict(values)
                for channel_id, values in (out.get("channels") or {}).items()
            }
            for raw_channel_id, channel_patch in channels_patch.items():
                channel_id = _validate_channel_id(raw_channel_id)
                if not isinstance(channel_patch, Mapping):
                    raise RuntimeStateError(f"channels.{channel_id} patch must be an object")
                if not channel_patch:
                    channels.pop(channel_id, None)
                    continue
                values = dict(channels.get(channel_id) or {})
                for key, value in channel_patch.items():
                    if key not in OVERRIDABLE_KEYS:
                        rejected.append(f"channels.{channel_id}.{key}")
                        continue
                    normalized = None if value is None else _normalize_value(key, value)
                    if normalized is None:
                        values.pop(key, None)
                    else:
                        values[key] = normalized
                if values:
                    channels[channel_id] = values
                else:
                    channels.pop(channel_id, None)
            if channels:
                out["channels"] = channels
            else:
                out.pop("channels", None)

    return out, sorted(set(rejected))


def save_state(path: Path, state: Mapping[str, Any], *, updated_by: str) -> dict[str, Any]:
    canonical = normalize_state(state)
    canonical["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    canonical["updated_by"] = str(updated_by)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=".codex-room-state-",
        suffix=".tmp",
    )
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(canonical, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return canonical


def resolve_channel_policy(
    baseline: Mapping[str, Any],
    state: Mapping[str, Any],
    channel_id: str,
    baseline_channels: Iterable[str],
) -> dict[str, Any] | None:
    """Resolve global and per-channel policy, including hot add/disable."""
    canonical = normalize_state(state)
    baseline_ids = {str(value) for value in baseline_channels}
    channel_overrides = dict((canonical.get("channels") or {}).get(channel_id) or {})
    baseline_matches = not baseline_ids or channel_id in baseline_ids
    if not baseline_matches and channel_overrides.get("enabled") is not True:
        return None

    effective = dict(DEFAULT_POLICY)
    effective.update(_normalize_scope(baseline, location="baseline"))
    effective.update(canonical.get("global") or {})
    effective.update(channel_overrides)
    if effective.get("enabled") is not True:
        return None
    return effective


def configured_channel_ids(
    baseline_channels: Iterable[str],
    state: Mapping[str, Any],
) -> tuple[str, ...]:
    canonical = normalize_state(state)
    values = {str(value) for value in baseline_channels if str(value).strip()}
    values.update((canonical.get("channels") or {}).keys())
    return tuple(sorted(values))


def sender_is_admitted(policy: Mapping[str, Any], params: Mapping[str, Any]) -> bool:
    senders = str(policy.get("senders") or "all").lower()
    if senders == "all":
        return True
    if senders == "humans":
        return not bool(params.get("author_is_bot"))
    if senders != "allowlist":
        return False
    allow = {str(value).strip().casefold() for value in policy.get("allow_from") or []}
    author_id = str(params.get("author_id") or "").strip().casefold()
    author_name = str(params.get("author_name") or "").strip().casefold()
    return bool((author_id and author_id in allow) or (author_name and author_name in allow))


def tail_receipts(path: Path, *, limit: int = 50) -> list[dict[str, Any]]:
    capped = max(1, min(int(limit), 500))
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise RuntimeStateError(f"cannot read receipt log {path}: {exc}") from exc
    receipts: list[dict[str, Any]] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            receipts.append(parsed)
        if len(receipts) >= capped:
            break
    return receipts
