"""Authoritative-order native-shape replay loader (T002).

Loads a JSONL scene of native event inputs (the shape
:mod:`nunchi.observation`'s ``ObservationProvider.ingest`` accepts) in
authoritative array order and replays them into a fresh provider, without
importing any native transport. Reusable by every downstream owner's own
replay harness (plan Sec. "Integration Strategy").
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from nunchi.observation import ObservationProvider


def load_scene(path: Path) -> list[dict[str, Any]]:
    """Load one JSONL file of native event inputs in authoritative order."""
    native_inputs: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                native_inputs.append(json.loads(raw_line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON ({exc})") from exc
    return native_inputs


def replay_into(provider: ObservationProvider, native_inputs: Iterable[dict[str, Any]]) -> list[str]:
    """Ingest every native input in order; returns the ordered dispositions."""
    return [provider.ingest(native_input) for native_input in native_inputs]


def replay_scene(provider: ObservationProvider, path: Path) -> list[str]:
    return replay_into(provider, load_scene(path))
