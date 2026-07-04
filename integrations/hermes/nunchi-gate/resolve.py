"""Effective model resolution and available-channel helpers for the nunchi-gate dashboard.

All functions are pure stdlib — no FastAPI, no third-party imports — so they
are directly testable by the stdlib unittest suite without venv surgery.

Model resolution
----------------
``resolve_effective_model`` implements the same lookup order that the plugin
uses at gate time so the dashboard can show an honest
"currently: <value> (from <source>)" label instead of a placeholder like
"(inherit from env)".

Resolution order (highest precedence first):

  1. ``cfg["model"]`` — the operator set a model explicitly in config.yaml
     or in a runtime state override.
  2. ``environ["NUNCHI_CLASSIFIER_MODEL"]`` — inherited from the dashboard
     service process environment.
  3. Parse *dotenv_path* for ``NUNCHI_CLASSIFIER_MODEL`` — the value that
     ``_load_dotenv_into`` in ``__init__.py`` would inject into the subprocess
     env at gate time (``~/.hermes/.env`` by default).
  4. ``None`` — no model is configured anywhere.

Source labels:
  ``"config"``      — step 1 matched.
  ``"environment"`` — step 2 matched.
  ``"dotenv"``      — step 3 matched.
  ``None``          — nothing matched (value is also ``None``).

Available channels
------------------
``available_channels_from_directory`` returns entries from the channel
directory file that are not already in the configured set, suitable for
populating the dashboard "Add channel" dropdown.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Default locations that match __init__.py conventions.
_DEFAULT_DOTENV_PATH = Path.home() / ".hermes" / ".env"
_DEFAULT_CHANNEL_DIR_PATH = Path.home() / ".hermes" / "channel_directory.json"

_MODEL_KEY = "NUNCHI_CLASSIFIER_MODEL"


# ---------------------------------------------------------------------------
# Model resolution
# ---------------------------------------------------------------------------


def resolve_effective_model(
    cfg: dict[str, Any],
    environ: dict[str, str],
    dotenv_path: "Path | str | None" = None,
) -> dict[str, "str | None"]:
    """Resolve the effective classifier model and its source.

    Parameters
    ----------
    cfg:
        The nunchi config dict (as returned by ``_nunchi_config()``).
        Inspected for the ``"model"`` key.
    environ:
        The process environment mapping.  Typically ``os.environ``, but pass
        a snapshot in tests for determinism.
    dotenv_path:
        Path to the ``.env`` file to scan when ``cfg["model"]`` and
        ``environ["NUNCHI_CLASSIFIER_MODEL"]`` are both absent.  Defaults to
        ``~/.hermes/.env`` when ``None``.  Tolerates file absence and parse
        errors silently.

    Returns
    -------
    dict
        ``{"value": str | None, "source": "config" | "environment" | "dotenv" | None}``
    """
    # 1. Explicit config / state override.
    model = str(cfg.get("model") or "").strip()
    if model:
        return {"value": model, "source": "config"}

    # 2. Process environment (e.g. already exported in ~/.hermes/.env by the
    #    Hermes daemon's own startup logic).
    env_val = str(environ.get(_MODEL_KEY) or "").strip()
    if env_val:
        return {"value": env_val, "source": "environment"}

    # 3. .env file — mirrors the tiny parser in __init__._load_dotenv_into.
    resolved_path = Path(dotenv_path) if dotenv_path is not None else _DEFAULT_DOTENV_PATH
    dotenv_val = _parse_dotenv_key(resolved_path, _MODEL_KEY)
    if dotenv_val:
        return {"value": dotenv_val, "source": "dotenv"}

    # 4. Not found anywhere.
    return {"value": None, "source": None}


def _parse_dotenv_key(path: Path, key: str) -> "str | None":
    """Extract the value of *key* from a .env file, or return ``None``.

    Uses the same tiny parser as ``_load_dotenv_into`` in ``__init__.py``:

    - Handles ``KEY=value`` and ``export KEY=value``.
    - Unwraps single and double quotes.
    - Ignores blank lines and ``#`` comments.
    - Tolerates file absence and parse errors (returns ``None``).

    Does **not** expand shell variables or handle multi-line values.
    """
    if not path.exists():
        return None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            if stripped.startswith("export "):
                stripped = stripped[len("export "):].strip()
            k, v = stripped.split("=", 1)
            k = k.strip()
            if k != key:
                continue
            v = v.strip().strip('"').strip("'")
            return v or None
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Available channels helper
# ---------------------------------------------------------------------------


def available_channels_from_directory(
    configured_ids: "set[str]",
    path: "Path | str | None" = None,
) -> "list[dict[str, str]]":
    """Return channel directory entries whose IDs are not in *configured_ids*.

    Reads ``~/.hermes/channel_directory.json`` (or *path* when given),
    which has the same structure that ``_load_channel_names`` in
    ``plugin_api.py`` handles.  Returns a sorted list of
    ``{"id": str, "name": str}`` dicts suitable for populating the
    dashboard "Add channel" dropdown.

    Tolerates:
    - File absence (returns ``[]``).
    - Malformed JSON (returns ``[]``).
    - Missing or unexpected structure (returns ``[]``).

    Parameters
    ----------
    configured_ids:
        Set of channel IDs already configured in either the baseline
        config.yaml channels block or the current state overrides.
    path:
        Override path to the channel directory file.  Defaults to
        ``~/.hermes/channel_directory.json``.

    Returns
    -------
    list[dict[str, str]]
        Each entry is ``{"id": str, "name": str}`` where *name* uses the
        same format as ``_load_channel_names``:
        ``"<guild> / #<name>"`` when a guild is present, else ``"#<name>"``.
        Sorted by (name.lower(), id).
    """
    resolved = Path(path) if path is not None else _DEFAULT_CHANNEL_DIR_PATH
    names = _load_directory_names(resolved)
    result: list[dict[str, str]] = []
    for cid, name in names.items():
        if cid not in configured_ids:
            result.append({"id": cid, "name": name})
    result.sort(key=lambda x: (x["name"].lower(), x["id"]))
    return result


def _load_directory_names(path: Path) -> dict[str, str]:
    """Parse channel_directory.json and return id → display-name mapping.

    Mirrors the logic in ``plugin_api._load_channel_names`` (without the
    mtime-cache layer, since this is a one-shot helper called from tests and
    from plugin_api which handles caching itself).
    """
    if not path.exists():
        return {}
    try:
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
                names[cid] = f"{guild} / #{name}" if guild else f"#{name}"
        return names
    except Exception:
        return {}
