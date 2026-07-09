#!/usr/bin/env python3
"""Compatibility wrapper for the packaged Codex inbound prompt gate."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if _SRC.exists():
    sys.path.insert(0, str(_SRC))

from nunchi.integrations import codex_prompt_gate as _impl  # noqa: E402

globals().update(
    {
        name: value
        for name, value in vars(_impl).items()
        if name
        not in {
            "__builtins__",
            "__cached__",
            "__file__",
            "__loader__",
            "__name__",
            "__package__",
            "__spec__",
        }
    }
)
main = _impl.main


if __name__ == "__main__":
    main()
