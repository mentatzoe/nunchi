#!/usr/bin/env python3
"""List the archived V1 verdict corpus without executing a V1 product path."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import loader


DEFAULT_FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"
SOURCES = (
    "all",
    "multica",
    "discord",
    "contract",
    "injection",
    "tool-chrome",
    "addressing",
)


def _print_list(fixtures: list, stream) -> None:
    stream.write(f"{len(fixtures)} archived V1 fixture(s) discovered:\n")
    for fixture in fixtures:
        evidence = "runtime" if fixture.evidence == "runtime" else "predicted"
        expected = "|".join(fixture.expected_verdicts)
        stream.write(
            f"  [{evidence}] {fixture.source_shape:11s} {fixture.id:48s} "
            f"expected={expected:14s} FRs={','.join(fixture.fr_refs)}\n"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verdict-test-suite",
        description=(
            "Archived Nunchi V1 verdict corpus. Listing remains available for "
            "historical traceability; execution moved to evals.v2."
        ),
    )
    parser.add_argument("--source", choices=SOURCES, default="all")
    parser.add_argument("--fixtures-root", type=Path, default=DEFAULT_FIXTURES_ROOT)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    if not args.list:
        print(
            "The V1 verdict runner is archived and list-only; use evals.v2.",
            file=sys.stderr,
        )
        return 2
    try:
        fixtures = loader.discover_fixtures(
            args.fixtures_root,
            source=None if args.source == "all" else args.source,
        )
    except loader.LoaderError as exc:
        print(f"loader error: {exc}", file=sys.stderr)
        return 2
    _print_list(fixtures, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
