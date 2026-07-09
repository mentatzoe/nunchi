#!/usr/bin/env python3
"""Compatibility wrapper for the packaged Codex configuration app."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if _SRC.exists():
    sys.path.insert(0, str(_SRC))

from nunchi.integrations.codex_config_app import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
