"""Fail-closed installer boundary for the Nunchi V2 integration candidate.

The inherited repository contains V1 Hermes and Claude Code artifacts.  They
are deliberately not installable through the V2 product entry point.  The
installer keeps its public command surface so packaging and operator tooling
do not silently lose a required product capability, but every command reports
the same explicit blocker until the exact accepted V2 packets are integrated.

This module must remain stdlib-only and import-safe.  It performs no filesystem
discovery and no writes in its blocked state.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import TextIO


EXIT_OK = 0
EXIT_UNAVAILABLE = 2

BLOCKER = "accepted-v2-integration-packets-unavailable"
BLOCKER_DETAIL = (
    "Accepted Hermes and Claude Code V2 integration packets are not present "
    "in this candidate; no changes were made."
)

COMMANDS = (
    "install",
    "upgrade",
    "verify",
    "uninstall",
    "print-claude-settings",
)


def build_parser() -> argparse.ArgumentParser:
    """Return the stable, V2-only installer command line."""

    parser = argparse.ArgumentParser(
        prog="nunchi-install",
        description=(
            "Install and verify accepted Nunchi V2 Hermes and Claude Code "
            "integration packets. This candidate currently fails closed "
            "because those packets have not been accepted."
        ),
    )
    parser.add_argument(
        "command",
        choices=COMMANDS,
        help="requested lifecycle operation (all currently report the packet blocker)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the blocked result as one JSON object",
    )
    return parser


def blocked_result(command: str) -> dict[str, object]:
    """Return the deterministic result for a command that cannot run safely."""

    if command not in COMMANDS:
        raise ValueError("unsupported installer command")
    return {
        "command": command,
        "status": "blocked",
        "reason": BLOCKER,
        "changed": False,
        "detail": BLOCKER_DETAIL,
    }


def _emit(result: dict[str, object], *, as_json: bool, stream: TextIO) -> None:
    if as_json:
        stream.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
        return
    stream.write(f"BLOCKED: {result['detail']}\n")
    stream.write(f"Reason: {result['reason']}\n")


def main(argv: Sequence[str] | None = None) -> int:
    """Report the explicit packet blocker without inspecting or changing disk."""

    args = build_parser().parse_args(argv)
    result = blocked_result(args.command)
    _emit(result, as_json=args.json, stream=sys.stdout)
    return EXIT_UNAVAILABLE


if __name__ == "__main__":  # pragma: no cover - exercised through the script
    raise SystemExit(main())
