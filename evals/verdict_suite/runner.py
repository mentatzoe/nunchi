#!/usr/bin/env python3
"""Stable repository entry point for installed V2 lifecycle conformance."""

from __future__ import annotations

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from nunchi.conformance import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
