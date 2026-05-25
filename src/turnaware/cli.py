"""Command-line interface for TurnAware."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .core import evaluate
from .errors import (
    EXIT_INPUT,
    EXIT_RUNTIME,
    EXIT_SUCCESS,
    EXIT_VALIDATION,
    InputError,
    TurnAwareError,
    ValidationError,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="turnaware")
    subparsers = parser.add_subparsers(dest="command", required=True)
    admit = subparsers.add_parser("admit", help="evaluate one admission request")
    admit.add_argument("--input", "-i", metavar="PATH", help="read admission request JSON from a file")
    admit.add_argument("--classifier", metavar="PATH", help="classifier path to use; only product is supported")
    admit.add_argument(
        "--classifier-config",
        metavar="JSON_OR_PATH",
        help="classifier configuration as a JSON object or path to a JSON object file",
    )
    return parser


def _read_input(path: str | None) -> str:
    if path is None:
        return sys.stdin.read()

    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"could not read input file {path!r}: {exc.strerror}") from exc


def _load_request(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid JSON: {exc.msg}") from exc


def _load_classifier_config(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None

    source = raw
    path = Path(raw)
    if path.exists():
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise InputError(f"could not read classifier config file {raw!r}: {exc.strerror}") from exc

    try:
        config = json.loads(source)
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid classifier config JSON: {exc.msg}") from exc
    if not isinstance(config, dict):
        raise ValidationError("classifier config must be a JSON object")
    return config


def _write_error(error: TurnAwareError) -> None:
    print(f"{error.label}: {error}", file=sys.stderr)


def main(argv: Sequence[str] | None = None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command != "admit":
            raise InputError(f"unsupported command: {args.command}")
        raw = _read_input(args.input)
        request = _load_request(raw)
        classifier_config = _load_classifier_config(args.classifier_config)
        result = evaluate(request, classifier=args.classifier, classifier_config=classifier_config)
    except InputError as exc:
        _write_error(exc)
        return EXIT_INPUT
    except ValidationError as exc:
        _write_error(exc)
        return EXIT_VALIDATION
    except TurnAwareError as exc:
        _write_error(exc)
        return EXIT_RUNTIME

    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return EXIT_SUCCESS
