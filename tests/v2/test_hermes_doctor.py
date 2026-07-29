"""Stable-output checks for the installed Hermes/Nunchi doctor."""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "integrations" / "hermes" / "nunchi-gate"
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from nunchi_hermes_v2 import doctor as hermes_doctor  # noqa: E402


class HermesDoctorTests(unittest.TestCase):
    def run_doctor(self, *args: str) -> tuple[int, dict]:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = hermes_doctor.main(list(args))
        return exit_code, json.loads(output.getvalue())

    def test_capable_preflight_has_stable_json_and_zero_exit(self) -> None:
        with (
            mock.patch.object(
                hermes_doctor,
                "_installed_capabilities",
                return_value=("readable", 2, 2),
            ),
            mock.patch.object(hermes_doctor, "_run_plugin_status") as status,
        ):
            exit_code, payload = self.run_doctor()

        self.assertEqual(0, exit_code)
        self.assertEqual(
            {
                "activation": {
                    "active": None,
                    "checked": False,
                    "configured_status": None,
                    "error": None,
                    "runtime_status": None,
                    "status": "not-checked",
                },
                "capability": {
                    "gateway_message_hook_api_version": 2,
                    "participant_host_api_version": 2,
                    "required_participant_host_api_major": 2,
                    "status": "compatible",
                },
                "message": "Hermes participant host API major 2 is compatible.",
                "ok": True,
                "plugin": "nunchi-v2",
                "schema_version": 1,
            },
            payload,
        )
        status.assert_not_called()

    def test_incapable_preflight_has_actionable_json_and_nonzero_exit(self) -> None:
        with (
            mock.patch.object(
                hermes_doctor,
                "_installed_capabilities",
                return_value=("missing", None, 2),
            ),
            mock.patch.object(hermes_doctor, "_run_plugin_status") as status,
        ):
            exit_code, payload = self.run_doctor("--check-activation")

        self.assertEqual(1, exit_code)
        self.assertFalse(payload["ok"])
        self.assertEqual("missing", payload["capability"]["status"])
        self.assertIsNone(
            payload["capability"]["participant_host_api_version"]
        )
        self.assertEqual(
            "skipped-incompatible-host",
            payload["activation"]["status"],
        )
        self.assertIn("Nunchi was not activated", payload["message"])
        self.assertIn("`hermes update`", payload["message"])
        self.assertIn("upgrade `hermes-agent`", payload["message"])
        status.assert_not_called()

    def test_enabled_but_inactive_plugin_status_fails(self) -> None:
        status_payload = [
            {
                "active": False,
                "error": "registration failed",
                "name": "nunchi-v2",
                "runtime_status": "error",
                "status": "enabled",
            }
        ]
        with (
            mock.patch.object(
                hermes_doctor,
                "_installed_capabilities",
                return_value=("readable", 2, 2),
            ),
            mock.patch.object(
                hermes_doctor,
                "_run_plugin_status",
                return_value=status_payload,
            ),
        ):
            exit_code, payload = self.run_doctor("--check-activation")

        self.assertEqual(1, exit_code)
        self.assertFalse(payload["ok"])
        self.assertEqual(
            {
                "active": False,
                "checked": True,
                "configured_status": "enabled",
                "error": "registration failed",
                "runtime_status": "error",
                "status": "error",
            },
            payload["activation"],
        )
        self.assertIn("enabled but not active", payload["message"])

    def test_active_plugin_status_succeeds(self) -> None:
        status_payload = [
            {
                "active": True,
                "error": None,
                "name": "nunchi-v2",
                "runtime_status": "active",
                "status": "enabled",
            }
        ]
        with (
            mock.patch.object(
                hermes_doctor,
                "_installed_capabilities",
                return_value=("readable", 2, 2),
            ),
            mock.patch.object(
                hermes_doctor,
                "_run_plugin_status",
                return_value=status_payload,
            ),
        ):
            exit_code, payload = self.run_doctor("--check-activation")

        self.assertEqual(0, exit_code)
        self.assertTrue(payload["ok"])
        self.assertEqual("active", payload["activation"]["status"])
        self.assertTrue(payload["activation"]["active"])
        self.assertEqual("nunchi-v2 is enabled and active.", payload["message"])

    def test_activation_check_uses_the_same_python_environment(self) -> None:
        completed = mock.Mock(returncode=0, stdout="[]")
        with mock.patch.object(
            hermes_doctor.subprocess,
            "run",
            return_value=completed,
        ) as run:
            self.assertEqual([], hermes_doctor._run_plugin_status())

        self.assertEqual(
            [
                sys.executable,
                "-m",
                "hermes_cli.main",
                "plugins",
                "list",
                "--json",
            ],
            run.call_args.args[0],
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
