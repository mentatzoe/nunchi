"""Command-line interface for the installed Nunchi V2 contract and core."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
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
from .install import InstallError, _default_config_root, _default_state_root
from .operator import (
    OperatorStore,
    ServiceManager,
    build_operator_config,
    registered_platforms,
)
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

    setup = subparsers.add_parser(
        "setup",
        help="create one validated profile without hand-written JSON or digests",
    )
    _operator_roots(setup)
    setup.add_argument("--participant-id", required=True)
    setup.add_argument("--actor-id", required=True)
    setup.add_argument("--display-name", required=True)
    setup.add_argument("--instructions", required=True)
    setup.add_argument("--platform", required=True, choices=tuple(registered_platforms()))
    setup.add_argument("--room-id", required=True)
    setup.add_argument("--room-name", required=True)
    setup.add_argument("--continuity-scope-id", required=True)
    setup.add_argument("--attention-model", required=True)
    setup.add_argument("--participant-model", required=True)
    setup.add_argument("--attention-provider", default="openai-compatible")
    setup.add_argument("--participant-provider", default="openai-compatible")
    setup.add_argument("--attention-credential-env", default="NUNCHI_ATTENTION_API_KEY")
    setup.add_argument("--participant-credential-env", default="NUNCHI_PARTICIPANT_API_KEY")
    setup.add_argument("--ack-reaction", default="👂")
    setup.add_argument("--ack-disabled", action="store_true")
    setup.add_argument(
        "--service",
        action="append",
        default=[],
        metavar="NAME=COMMAND",
        help="profile service command; may be repeated",
    )
    setup.add_argument("--replace", action="store_true")

    config = subparsers.add_parser("config", help="inspect or update the shared profile schema")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    for name in ("show", "validate"):
        command = config_commands.add_parser(name)
        _operator_roots(command)
    rollback = config_commands.add_parser("rollback")
    _operator_roots(rollback)
    rollback.add_argument("revision")
    ack = config_commands.add_parser("set-ack")
    _operator_roots(ack)
    ack_state = ack.add_mutually_exclusive_group()
    ack_state.add_argument("--enabled", action="store_true")
    ack_state.add_argument("--disabled", action="store_true")
    ack.add_argument("--reaction")
    room = config_commands.add_parser("add-room")
    _operator_roots(room)
    room.add_argument("--platform", required=True, choices=tuple(registered_platforms()))
    room.add_argument("--room-id", required=True)
    room.add_argument("--room-name", required=True)
    room.add_argument("--continuity-scope-id", required=True)

    diagnose = subparsers.add_parser("diagnose", help="validate install, config, health, and receipts")
    _operator_roots(diagnose)

    dashboard = subparsers.add_parser("dashboard", help="serve the bundled shared dashboard")
    _operator_roots(dashboard)
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8765)

    service = subparsers.add_parser("service", help="control profile-scoped persistent services")
    service_commands = service.add_subparsers(dest="service_command", required=True)
    for name in ("start", "stop", "drain", "restart", "status", "logs", "reset", "install", "uninstall"):
        command = service_commands.add_parser(name)
        _operator_roots(command)
        command.add_argument("name")
        if name == "logs":
            command.add_argument("--lines", type=int, default=100)

    uninstall = subparsers.add_parser("uninstall", help="remove one exact operator profile")
    _operator_roots(uninstall)
    return parser


def _operator_roots(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", default="default")
    parser.add_argument("--config-root", type=Path, default=_default_config_root())
    parser.add_argument("--state-root", type=Path, default=_default_state_root())


def _operator_store(args: argparse.Namespace) -> OperatorStore:
    return OperatorStore(args.config_root, args.state_root, args.profile)


def _service_definitions(values: Sequence[str]) -> list[dict[str, Any]]:
    services = []
    for value in values:
        name, separator, raw_command = value.partition("=")
        if not separator:
            raise ValidationError("--service must use NAME=COMMAND")
        try:
            command = shlex.split(raw_command)
        except ValueError as exc:
            raise ValidationError(f"service command is invalid: {exc}") from exc
        services.append(
            {
                "name": name,
                "command": command,
                "restart": "always",
                "environment": {},
            }
        )
    return services


def _setup(args: argparse.Namespace) -> dict[str, Any]:
    store = _operator_store(args)
    expected = None
    if store.paths.config.exists():
        _, expected = store.read()
        if not args.replace:
            raise ValidationError("profile already exists; use --replace with deliberate new fields")
    document = build_operator_config(
        profile_id=args.profile,
        participant_id=args.participant_id,
        actor_id=args.actor_id,
        display_name=args.display_name,
        instructions=args.instructions,
        platform=args.platform,
        room_id=args.room_id,
        room_name=args.room_name,
        continuity_scope_id=args.continuity_scope_id,
        attention_model=args.attention_model,
        participant_model=args.participant_model,
        attention_provider=args.attention_provider,
        participant_provider=args.participant_provider,
        attention_credential_env=args.attention_credential_env,
        participant_credential_env=args.participant_credential_env,
        ack_enabled=not args.ack_disabled,
        ack_reaction=args.ack_reaction,
        services=_service_definitions(args.service),
    )
    return store.write(document, expected_revision=expected)


def _config(args: argparse.Namespace) -> dict[str, Any]:
    store = _operator_store(args)
    document, revision = store.read()
    if args.config_command == "show":
        return store.snapshot()
    if args.config_command == "validate":
        return {"status": "valid", "profile_id": args.profile, "revision": revision}
    if args.config_command == "rollback":
        return store.rollback(args.revision)
    if args.config_command == "set-ack":
        policy = dict(document["ack_policy"])
        if args.enabled:
            policy["enabled"] = True
        if args.disabled:
            policy["enabled"] = False
        if args.reaction is not None:
            policy["reaction"] = args.reaction
        document["ack_policy"] = policy
        return store.write(document, expected_revision=revision)
    if args.config_command == "add-room":
        document["rooms"].append(
            {
                "platform": args.platform,
                "room_id": args.room_id,
                "continuity_scope_id": args.continuity_scope_id,
                "name": args.room_name,
                "enabled": True,
            }
        )
        return store.write(document, expected_revision=revision)
    raise InputError(f"unsupported config command: {args.config_command}")


def _service(args: argparse.Namespace) -> dict[str, Any]:
    manager = ServiceManager(_operator_store(args))
    operations = {
        "start": manager.start,
        "stop": manager.stop,
        "drain": manager.drain,
        "restart": manager.restart,
        "status": manager.status,
        "logs": lambda name: manager.logs(name, lines=args.lines),
        "reset": manager.reset,
        "install": manager.install_persistent,
        "uninstall": manager.uninstall_persistent,
    }
    return operations[args.service_command](args.name)


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
            "I-010B": 3,
            "I-010C": 2,
            "I-010D": 1,
            "I-010E": 3,
            "I-010F": 1,
            "I-020A": 1,
            "I-030A": 2,
            "I-040A": 2,
            "I-040B": 1,
            "I-040C": 1,
        },
        "participant_turn_protocol_version": 1,
        "operator_schema_version": 1,
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
        elif args.command == "setup":
            code, output = EXIT_SUCCESS, _setup(args)
        elif args.command == "config":
            code, output = EXIT_SUCCESS, _config(args)
        elif args.command == "diagnose":
            code, output = EXIT_SUCCESS, _operator_store(args).diagnose()
        elif args.command == "dashboard":
            from .dashboard import serve_dashboard

            serve_dashboard(
                _operator_store(args),
                host=args.host,
                port=args.port,
            )
            return EXIT_SUCCESS
        elif args.command == "service":
            code, output = EXIT_SUCCESS, _service(args)
        elif args.command == "uninstall":
            code, output = EXIT_SUCCESS, _operator_store(args).uninstall()
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
    except (InstallError, OSError, ValueError) as exc:
        print(f"runtime error: {exc}", file=sys.stderr)
        return EXIT_RUNTIME
    json.dump(output, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return code
