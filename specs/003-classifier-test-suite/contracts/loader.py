"""Fixture loader and validator for the verdict test suite.

See ../data-model.md sections 1, 2, 5 and "Validation rules".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_VERDICTS = {"PASS", "ACK", "ASK", "SPEAK"}
_SOURCE_SHAPES = {"multica", "discord", "contract"}
_EVIDENCE = {"runtime", "predicted"}


class LoaderError(Exception):
    """Raised when a fixture pair is malformed."""


@dataclass(frozen=True)
class Fixture:
    """A loaded fixture-envelope + metadata pair."""

    id: str
    envelope_path: Path
    meta_path: Path
    envelope: dict[str, Any]
    meta: dict[str, Any]
    source_shape: str
    evidence: str
    expected_verdicts: tuple[str, ...]
    surface_contract: str | None
    failure_mode: str
    invariant: str | None
    rationale: str
    fr_refs: tuple[str, ...]
    sc_refs: tuple[str, ...]
    runtime_source: str | None = None
    predicted_basis: str | None = None
    mock_adapter_output: str | None = None
    title: str = ""


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LoaderError(f"{path}: invalid JSON ({exc.msg})") from exc
    except OSError as exc:
        raise LoaderError(f"{path}: could not read ({exc.strerror})") from exc


def _validate_envelope(envelope: Any, where: Path) -> dict[str, Any]:
    if not isinstance(envelope, dict):
        raise LoaderError(f"{where}: envelope is not a JSON object")
    trigger = envelope.get("trigger")
    if not isinstance(trigger, dict) or not isinstance(trigger.get("content"), str):
        raise LoaderError(
            f"{where}: envelope.trigger.content must be a non-empty string "
            f"(public turnaware admit schema)"
        )
    return envelope


def _coerce_str_tuple(value: Any, where: Path, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(x, str) for x in value):
        return tuple(value)
    raise LoaderError(f"{where}: {field_name} must be a string or list of strings")


def _validate_meta(meta: Any, where: Path) -> dict[str, Any]:
    if not isinstance(meta, dict):
        raise LoaderError(f"{where}: metadata is not a JSON object")
    for key in ("id", "source_shape", "evidence", "expected", "failure_mode", "rationale"):
        if key not in meta:
            raise LoaderError(f"{where}: missing required metadata field {key!r}")
    if meta["source_shape"] not in _SOURCE_SHAPES:
        raise LoaderError(
            f"{where}: source_shape={meta['source_shape']!r} not in {_SOURCE_SHAPES}"
        )
    if meta["evidence"] not in _EVIDENCE:
        raise LoaderError(f"{where}: evidence={meta['evidence']!r} not in {_EVIDENCE}")
    expected = meta["expected"]
    if not isinstance(expected, dict) or "verdict" not in expected:
        raise LoaderError(f"{where}: expected.verdict missing")
    if expected.get("surface_contract") not in (None, "typed-verdict"):
        raise LoaderError(
            f"{where}: expected.surface_contract must be null or 'typed-verdict'"
        )
    verdicts = expected["verdict"]
    if isinstance(verdicts, str):
        verdicts = [verdicts]
    if (
        not isinstance(verdicts, list)
        or not verdicts
        or any(v not in _VERDICTS for v in verdicts)
    ):
        raise LoaderError(
            f"{where}: expected.verdict must be a non-empty string or list from {_VERDICTS}"
        )
    if meta["evidence"] == "runtime" and "runtime_source" not in meta:
        raise LoaderError(f"{where}: evidence=runtime requires runtime_source field")
    if meta["evidence"] == "predicted" and "predicted_basis" not in meta:
        raise LoaderError(f"{where}: evidence=predicted requires predicted_basis field")
    return meta


def load_fixture(envelope_path: Path) -> Fixture:
    """Load and validate a single envelope + meta pair from envelope_path."""
    meta_path = envelope_path.with_suffix(".meta.json")
    if envelope_path.name.endswith(".meta.json"):
        raise LoaderError(f"{envelope_path}: passed a metadata file, not an envelope")
    if not meta_path.exists():
        raise LoaderError(f"{envelope_path}: missing sibling {meta_path.name}")
    envelope = _validate_envelope(_read_json(envelope_path), envelope_path)
    meta = _validate_meta(_read_json(meta_path), meta_path)
    verdicts = meta["expected"]["verdict"]
    if isinstance(verdicts, str):
        verdicts = [verdicts]
    return Fixture(
        id=meta["id"],
        envelope_path=envelope_path,
        meta_path=meta_path,
        envelope=envelope,
        meta=meta,
        source_shape=meta["source_shape"],
        evidence=meta["evidence"],
        expected_verdicts=tuple(verdicts),
        surface_contract=meta["expected"].get("surface_contract"),
        failure_mode=meta["failure_mode"],
        invariant=meta.get("invariant"),
        rationale=meta["rationale"],
        fr_refs=_coerce_str_tuple(meta.get("fr_refs"), meta_path, "fr_refs"),
        sc_refs=_coerce_str_tuple(meta.get("sc_refs"), meta_path, "sc_refs"),
        runtime_source=meta.get("runtime_source"),
        predicted_basis=meta.get("predicted_basis"),
        mock_adapter_output=meta.get("mock_adapter_output"),
        title=meta.get("title", ""),
    )


def discover_fixtures(
    fixtures_root: Path, source: str | None = None
) -> list[Fixture]:
    """Walk fixtures_root for envelope+meta pairs; return Fixtures sorted by id (FR-015)."""
    if not fixtures_root.is_dir():
        raise LoaderError(f"{fixtures_root}: fixtures root is not a directory")
    out: list[Fixture] = []
    envelopes = sorted(p for p in fixtures_root.rglob("*.json") if not p.name.endswith(".meta.json"))
    seen_ids: dict[str, Path] = {}
    for envelope_path in envelopes:
        fixture = load_fixture(envelope_path)
        if fixture.id in seen_ids:
            raise LoaderError(
                f"duplicate fixture id {fixture.id!r}: "
                f"{seen_ids[fixture.id]} vs {envelope_path}"
            )
        seen_ids[fixture.id] = envelope_path
        if source is not None and source != "all" and fixture.source_shape != source:
            continue
        out.append(fixture)
    out.sort(key=lambda f: f.id)
    return out


def build_index(fixtures: list[Fixture]) -> dict[str, Any]:
    """Build the index.json content per data-model.md section 5."""
    from datetime import datetime, timezone

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixtures": [
            {
                "id": f.id,
                "envelope": str(f.envelope_path),
                "meta": str(f.meta_path),
                "source_shape": f.source_shape,
                "evidence": f.evidence,
                "expected_verdict": list(f.expected_verdicts),
                "surface_contract": f.surface_contract,
                "fr_refs": list(f.fr_refs),
                "sc_refs": list(f.sc_refs),
            }
            for f in fixtures
        ],
    }
