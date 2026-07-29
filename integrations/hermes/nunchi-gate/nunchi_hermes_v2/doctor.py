"""Installed-Hermes capability and Nunchi activation health check."""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from . import (
    _GATEWAY_MESSAGE_HOOK_CAPABILITY,
    _PARTICIPANT_HOST_CAPABILITY,
    _PLUGIN_ID,
    _SUPPORTED_PARTICIPANT_HOST_API_MAJOR,
    _participant_host_failure,
)

_MISSING = object()


def _read_context_capability(
    context_type: type[Any],
    name: str,
) -> tuple[str, int | None]:
    descriptor = inspect.getattr_static(context_type, name, _MISSING)
    if descriptor is _MISSING:
        return "missing", None
    try:
        if hasattr(descriptor, "__get__"):
            observed = descriptor.__get__(
                object.__new__(context_type),
                context_type,
            )
        else:
            observed = descriptor
    except Exception:
        return "unreadable", None
    if type(observed) is not int:
        return "malformed", None
    return "readable", observed


def _installed_capabilities() -> tuple[str, int | None, int | None]:
    try:
        module = importlib.import_module("hermes_cli.plugins")
        context_type = getattr(module, "PluginContext")
    except Exception:
        return "unreadable", None, None
    participant_status, participant_version = _read_context_capability(
        context_type,
        _PARTICIPANT_HOST_CAPABILITY,
    )
    _gateway_status, gateway_version = _read_context_capability(
        context_type,
        _GATEWAY_MESSAGE_HOOK_CAPABILITY,
    )
    return participant_status, participant_version, gateway_version


def _empty_activation(*, status: str, checked: bool) -> dict[str, Any]:
    return {
        "active": None,
        "checked": checked,
        "configured_status": None,
        "error": None,
        "runtime_status": None,
        "status": status,
    }


def _run_plugin_status() -> Any:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hermes_cli.main",
            "plugins",
            "list",
            "--json",
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ValueError("Hermes plugin status command failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Hermes plugin status was not valid JSON") from exc


def _activation_health(payload: Any) -> tuple[dict[str, Any], bool, str]:
    if not isinstance(payload, list):
        raise ValueError("Hermes plugin status must be a JSON array")
    matches = [
        item
        for item in payload
        if isinstance(item, Mapping) and item.get("name") == _PLUGIN_ID
    ]
    if len(matches) != 1:
        activation = _empty_activation(status="missing", checked=True)
        return (
            activation,
            False,
            "nunchi-v2 plugin status was not found; install Nunchi and retry.",
        )
    item = matches[0]
    configured_status = item.get("status")
    active = item.get("active")
    runtime_status = item.get("runtime_status")
    error = item.get("error")
    if (
        not isinstance(configured_status, str)
        or type(active) is not bool
        or not isinstance(runtime_status, str)
        or (error is not None and not isinstance(error, str))
    ):
        raise ValueError("Hermes nunchi-v2 plugin status was malformed")
    activation = {
        "active": active,
        "checked": True,
        "configured_status": configured_status,
        "error": error,
        "runtime_status": runtime_status,
        "status": "active" if active else runtime_status,
    }
    if (
        configured_status == "enabled"
        and active
        and runtime_status == "active"
        and error is None
    ):
        return activation, True, "nunchi-v2 is enabled and active."
    if configured_status != "enabled":
        return (
            activation,
            False,
            "nunchi-v2 is not enabled; enable it and retry.",
        )
    return (
        activation,
        False,
        "nunchi-v2 is enabled but not active; inspect "
        "`hermes plugins list --json`, repair the reported error, and retry.",
    )


def _capability_message(status: str, version: int | None) -> str:
    if status == "missing":
        return _participant_host_failure("is missing")
    if status == "malformed":
        return _participant_host_failure("is malformed")
    if status != "readable":
        return _participant_host_failure("could not be read")
    return _participant_host_failure(
        f"reported unsupported major {version}"
    )


def doctor(*, check_activation: bool) -> tuple[dict[str, Any], int]:
    participant_status, participant_version, gateway_version = (
        _installed_capabilities()
    )
    capability_ok = (
        participant_status == "readable"
        and participant_version == _SUPPORTED_PARTICIPANT_HOST_API_MAJOR
    )
    capability_status = (
        "compatible"
        if capability_ok
        else "unsupported"
        if participant_status == "readable"
        else participant_status
    )
    capability = {
        "gateway_message_hook_api_version": gateway_version,
        "participant_host_api_version": participant_version,
        "required_participant_host_api_major": (
            _SUPPORTED_PARTICIPANT_HOST_API_MAJOR
        ),
        "status": capability_status,
    }
    activation = _empty_activation(
        status=(
            "not-checked"
            if not check_activation
            else "skipped-incompatible-host"
        ),
        checked=False,
    )
    if not capability_ok:
        return (
            {
                "activation": activation,
                "capability": capability,
                "message": _capability_message(
                    participant_status,
                    participant_version,
                ),
                "ok": False,
                "plugin": _PLUGIN_ID,
                "schema_version": 1,
            },
            1,
        )

    message = "Hermes participant host API major 2 is compatible."
    ok = True
    if check_activation:
        try:
            status_payload = _run_plugin_status()
            activation, ok, message = _activation_health(status_payload)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            activation = _empty_activation(
                status="unavailable",
                checked=True,
            )
            ok = False
            message = (
                "Hermes plugin activation status could not be read; run "
                "`hermes plugins list --json` and retry."
            )
    return (
        {
            "activation": activation,
            "capability": capability,
            "message": message,
            "ok": ok,
            "plugin": _PLUGIN_ID,
            "schema_version": 1,
        },
        0 if ok else 1,
    )


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        prog="nunchi-hermes-v2-doctor",
        description="Check the installed Hermes participant-host capability.",
    )
    command.add_argument(
        "--check-activation",
        action="store_true",
        help="Also require nunchi-v2 to be enabled and active.",
    )
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    result, exit_code = doctor(check_activation=args.check_activation)
    print(json.dumps(result, sort_keys=True))
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
