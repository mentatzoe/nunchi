"""Pluggable adapters for the verdict test suite.

See ../data-model.md section 4 and ../research.md R1 / R3 for the contract this
module implements.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Protocol

_VERDICTS = ("PASS", "ACK", "ASK", "SPEAK")
_SENTINEL_LEAK_MARKERS = (
    "__CC_CONNECT_SILENT_PASS__",
    "__CC_CONNECT_SILENT_PASS___",
    "__CC_CONNECT_SILENT_PASS____",
    "CC_CONNECT_SILENT_PASS",
)


class Adapter(Protocol):
    name: str

    def classify(self, envelope: dict) -> dict: ...


def _classify_raw_stdout(raw: str) -> dict:
    """Take an adapter's raw stdout string and return the typed adapter response.

    Centralizes the verdict-surface contract (FR-020): rejects malformed sentinel
    leaks and bare verdict strings, accepts a JSON object with `verdict` field.
    """
    stripped = raw.strip()
    if not stripped:
        return {
            "ok": False,
            "error_kind": "malformed-output",
            "error_detail": "adapter produced no output",
            "raw_stdout": raw,
        }
    for marker in _SENTINEL_LEAK_MARKERS:
        if marker in stripped and not stripped.startswith("{"):
            return {
                "ok": False,
                "error_kind": "sentinel-leak",
                "error_detail": (
                    f"adapter received {stripped[:80]!r} as classifier output; "
                    "expected typed verdict (FR-020)"
                ),
                "raw_stdout": raw,
            }
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "error_kind": "malformed-output",
            "error_detail": f"could not parse adapter output as JSON: {exc.msg}",
            "raw_stdout": raw,
        }
    if not isinstance(parsed, dict):
        return {
            "ok": False,
            "error_kind": "schema-violation",
            "error_detail": "adapter output is not a JSON object",
            "raw_stdout": raw,
        }
    verdict = parsed.get("verdict")
    if verdict not in _VERDICTS:
        return {
            "ok": False,
            "error_kind": "schema-violation",
            "error_detail": (
                f"adapter output verdict={verdict!r} is not one of {_VERDICTS} (FR-020)"
            ),
            "raw_stdout": raw,
        }
    return {
        "ok": True,
        "verdict": verdict,
        "confidences": parsed.get("confidences", {}),
        "context_checked": parsed.get("context_checked", []),
        "raw_stdout": raw,
    }


class SubprocessAdapter:
    """Default adapter: shells out to `turnaware admit --input <tmp>.json` (research.md R1)."""

    def __init__(self, cmd: list[str] | None = None, timeout: float = 10.0) -> None:
        if cmd is not None:
            self._cmd = list(cmd)
        else:
            resolved = shutil.which("turnaware")
            if resolved:
                self._cmd = [resolved]
            else:
                self._cmd = [sys.executable, "-m", "turnaware"]
        self._timeout = timeout
        self.name = "subprocess:" + " ".join(self._cmd)

    def classify(self, envelope: dict) -> dict:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as tmp:
            json.dump(envelope, tmp)
            tmp_path = tmp.name
        try:
            completed = subprocess.run(
                [*self._cmd, "admit", "--input", tmp_path],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "ok": False,
                "error_kind": "timeout",
                "error_detail": f"adapter timed out after {self._timeout}s",
                "raw_stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "returncode": None,
            }
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        if completed.returncode != 0 and not completed.stdout.strip():
            return {
                "ok": False,
                "error_kind": "subprocess-crash",
                "error_detail": (
                    f"adapter exited rc={completed.returncode} with no stdout; "
                    f"stderr={completed.stderr.strip()[:200]}"
                ),
                "raw_stdout": completed.stdout,
                "stderr": completed.stderr,
                "returncode": completed.returncode,
            }
        result = _classify_raw_stdout(completed.stdout)
        result["returncode"] = completed.returncode
        result["stderr"] = completed.stderr
        return result


class InProcessAdapter:
    """In-process adapter: imports turnaware.core.evaluate (research.md R1 alt)."""

    name = "in-process:turnaware.core.evaluate"

    def __init__(self) -> None:
        from turnaware.core import evaluate

        self._evaluate = evaluate

    def classify(self, envelope: dict) -> dict:
        try:
            output = self._evaluate(envelope)
        except Exception as exc:  # noqa: BLE001 — classifier-internal error reported as adapter error
            return {
                "ok": False,
                "error_kind": "schema-violation",
                "error_detail": f"in-process classifier raised {type(exc).__name__}: {exc}",
                "raw_stdout": "",
            }
        return _classify_raw_stdout(json.dumps(output))


class MockAdapter:
    """Used only by c-* verdict-surface contract fixtures (research.md R3).

    Returns the raw text of `mock_adapter_output` (from metadata) as the
    classifier's stdout, then runs it through the same response-validation
    path so sentinel-leak rejection is exercised end-to-end.
    """

    name = "mock:fixture-driven"

    def __init__(self, mock_output: str) -> None:
        self._mock_output = mock_output

    def classify(self, envelope: dict) -> dict:
        return _classify_raw_stdout(self._mock_output)


def make_adapter(spec: str, cmd: str | None = None) -> Adapter:
    """Build an adapter from a CLI spec string.

    spec: "subprocess" | "in-process" | "custom:path/to/file.py:ClassName"
    """
    if spec == "subprocess":
        cmd_list = cmd.split() if cmd else None
        return SubprocessAdapter(cmd=cmd_list)
    if spec == "in-process":
        return InProcessAdapter()
    if spec.startswith("custom:"):
        _, path_and_class = spec.split(":", 1)
        path_str, class_name = path_and_class.rsplit(":", 1)
        import importlib.util

        module_name = Path(path_str).stem
        module_spec = importlib.util.spec_from_file_location(module_name, path_str)
        if module_spec is None or module_spec.loader is None:
            raise ValueError(f"could not load custom adapter from {path_str!r}")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        adapter_class = getattr(module, class_name)
        return adapter_class()
    raise ValueError(f"unknown adapter spec: {spec!r}")
