"""Command-line interface for Nunchi."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .core import evaluate_v2
from .errors import (
    EXIT_INPUT,
    EXIT_RUNTIME,
    EXIT_SUCCESS,
    EXIT_VALIDATION,
    InputError,
    NunchiError,
    ValidationError,
)
from .policy import PolicyLoadError, load_operator_policy
from .receipts import ExclusiveJSONFileReceiptSink, ReceiptSinkConstructionError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nunchi")
    subparsers = parser.add_subparsers(dest="command", required=True)
    attention = subparsers.add_parser(
        "attention-v2",
        help="evaluate one V2 attention request using trusted operator configuration",
    )
    attention.add_argument(
        "--config",
        required=True,
        metavar="PATH",
        help="absolute owner-only V2 operator policy path",
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


def _write_error(error: NunchiError) -> None:
    print(f"{error.label}: {error}", file=sys.stderr)


def main(argv: Sequence[str] | None = None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "attention-v2":
            raw = _read_input(None)
            request = _load_request(raw)
            try:
                operator = load_operator_policy(args.config)
                sink = ExclusiveJSONFileReceiptSink(operator.receipt_sink)
            except (PolicyLoadError, ReceiptSinkConstructionError):
                request_id = request.get("request_id") if isinstance(request, dict) else None
                result = {
                    "status": "error",
                    "error": {
                        "code": "configuration-error",
                        "detail": "trusted attention configuration is invalid",
                    },
                }
                if isinstance(request_id, str) and request_id:
                    result["request_id"] = request_id
                exit_code = EXIT_VALIDATION
            else:
                try:
                    result = evaluate_v2(
                        request,
                        policy=operator.attention,
                        recoverability=operator.recoverability,
                        classifier_config=operator.classifier,
                        receipt_sink=sink,
                    )
                finally:
                    sink.close()
                if result["status"] in ("ok", "bypass"):
                    exit_code = EXIT_SUCCESS
                elif result["error"]["code"] in {
                    "invalid-request",
                    "configuration-error",
                    "attention-budget-error",
                }:
                    exit_code = EXIT_VALIDATION
                else:
                    exit_code = EXIT_RUNTIME
        else:
            raise InputError(f"unsupported command: {args.command}")
    except InputError as exc:
        _write_error(exc)
        return EXIT_INPUT
    except ValidationError as exc:
        _write_error(exc)
        return EXIT_VALIDATION
    except NunchiError as exc:
        _write_error(exc)
        return EXIT_RUNTIME

    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return exit_code
