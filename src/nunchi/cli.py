"""Command-line interface for the installed Nunchi V2 contract and core."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from . import __version__
from .attention import (
    AttentionPolicy,
    OpenAICompatibleAttentionModel,
    ParticipantProfile,
)
from .core import evaluate
from .errors import (
    EXIT_INPUT,
    EXIT_RUNTIME,
    EXIT_SUCCESS,
    EXIT_VALIDATION,
    InputError,
    NunchiError,
    ValidationError,
)
from .receipts import ReceiptJournal
from .v2_contracts import (
    validate_attention_decision,
    validate_attention_request,
    validate_participant_wake,
    validate_receipt,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nunchi")
    subparsers = parser.add_subparsers(dest="command", required=True)

    attention = subparsers.add_parser(
        "attention",
        help="run one participant-bound I-030A attention judgment",
    )
    attention.add_argument("--input", "-i", metavar="PATH")
    attention.add_argument("--profile", required=True, metavar="PATH")
    attention.add_argument(
        "--profile-sha256",
        default=os.environ.get("NUNCHI_PROFILE_SHA256"),
        metavar="HEX",
        help="trusted sha256 pin (or NUNCHI_PROFILE_SHA256)",
    )
    attention.add_argument("--config", required=True, metavar="PATH")
    attention.add_argument(
        "--config-sha256",
        default=os.environ.get("NUNCHI_ATTENTION_CONFIG_SHA256"),
        metavar="HEX",
        help="trusted sha256 pin (or NUNCHI_ATTENTION_CONFIG_SHA256)",
    )
    attention.add_argument(
        "--receipt-journal",
        required=True,
        metavar="PATH",
        help="append to a journal already containing this request's observation stage",
    )

    validate = subparsers.add_parser(
        "validate",
        help="validate one closed V2 contract document",
    )
    validate.add_argument(
        "interface",
        choices=("attention-request", "attention-decision", "participant-wake", "attention-receipt"),
    )
    validate.add_argument("--input", "-i", metavar="PATH")

    subparsers.add_parser("probe", help="print installed V2 interface provenance")
    return parser


def _read_input(path: str | None) -> str:
    if path is None:
        return sys.stdin.read()
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"could not read input file {path!r}: {exc}") from exc


def _load_json(raw: str, *, label: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid {label} JSON: {exc.msg}") from exc


def _load_pinned_json(path: str, digest: str | None, *, label: str) -> dict[str, Any]:
    if not digest:
        raise ValidationError(f"{label} sha256 pin is required from trusted host configuration")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValidationError(f"{label} sha256 pin must be 64 lowercase hex characters")
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise InputError(f"could not read {label} file {path!r}: {exc}") from exc
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValidationError(f"{label} bytes do not match the trusted sha256 pin")
    data = _load_json(raw.decode("utf-8"), label=label)
    if not isinstance(data, dict):
        raise ValidationError(f"{label} must be a JSON object")
    return data


def _load_attention_policy(raw: Any) -> AttentionPolicy:
    if not isinstance(raw, Mapping):
        raise ValidationError("attention policy must be an object")
    allowed = {
        "preattention_enabled",
        "suppression_enabled",
        "suppression_recovery_verified",
        "margin_status",
        "effective_margin",
        "margin_source",
        "provenance",
        "timeout_seconds",
        "error_action",
    }
    if set(raw) - allowed:
        raise ValidationError("attention policy contains unexpected fields")
    try:
        return AttentionPolicy(**raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"attention policy is invalid: {exc}") from exc


def _attention(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    request = _load_json(_read_input(args.input), label="request")
    checked = validate_attention_request(request)
    config = _load_pinned_json(
        args.config,
        args.config_sha256,
        label="attention config",
    )
    if set(config) != {"policy", "model"}:
        raise ValidationError("attention config must contain exactly policy and model")
    profile = ParticipantProfile.load(
        args.profile,
        expected_sha256=args.profile_sha256,
    )
    policy = _load_attention_policy(config["policy"])
    if policy.preattention_enabled:
        if not isinstance(config["model"], Mapping):
            raise ValidationError("attention model config must be an object")
        model = OpenAICompatibleAttentionModel.from_trusted_config(config["model"])
    else:
        if config["model"] not in (None, {}):
            raise ValidationError("bypass config must not carry a model redirect")
        model = None
    journal = ReceiptJournal(args.receipt_journal)
    if journal.next_stage(checked["request_id"]) != "attention":
        raise ValidationError(
            "receipt journal must already contain exactly this request's observation stage"
        )
    decision = evaluate(
        checked,
        profile=profile,
        model=model,
        policy=policy,
        receipts=journal,
    )
    return (EXIT_RUNTIME if decision["status"] == "error" else EXIT_SUCCESS), decision


def _validate(args: argparse.Namespace) -> dict[str, Any]:
    document = _load_json(_read_input(args.input), label="contract")
    validator = {
        "attention-request": validate_attention_request,
        "attention-decision": validate_attention_decision,
        "participant-wake": validate_participant_wake,
        "attention-receipt": validate_receipt,
    }[args.interface]
    validator(document)
    return {
        "valid": True,
        "interface": args.interface,
        "product_version": __version__,
    }


def _probe() -> dict[str, Any]:
    return {
        "product": "nunchi",
        "product_version": __version__,
        "generation": 2,
        "interfaces": {
            "I-010A": 1,
            "I-010B": 2,
            "I-010C": 1,
            "I-010D": 1,
            "I-010E": 2,
            "I-010F": 1,
            "I-020A": 1,
            "I-030A": 1,
            "I-040A": 1,
            "I-040B": 1,
            "I-040C": 1,
        },
        "v1_fallback": False,
    }


def _write_error(error: NunchiError) -> None:
    print(f"{error.label}: {error}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "attention":
            code, output = _attention(args)
        elif args.command == "validate":
            code, output = EXIT_SUCCESS, _validate(args)
        elif args.command == "probe":
            code, output = EXIT_SUCCESS, _probe()
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
    json.dump(output, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return code
