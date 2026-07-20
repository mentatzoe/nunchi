"""Safety tests for the V2 installer while external packets are unavailable."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from nunchi import install


class BlockedInstallerTest(unittest.TestCase):
    def test_every_lifecycle_command_fails_closed_without_filesystem_access(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nunchi-install-blocked-") as raw:
            root = Path(raw)
            sentinel = root / "sentinel"
            sentinel.write_text("unchanged\n", encoding="utf-8")

            for command in install.COMMANDS:
                with self.subTest(command=command):
                    output = io.StringIO()
                    before = sorted((path.name, path.read_bytes()) for path in root.iterdir())
                    with contextlib.redirect_stdout(output):
                        code = install.main([command, "--json"])
                    after = sorted((path.name, path.read_bytes()) for path in root.iterdir())

                    self.assertEqual(code, install.EXIT_UNAVAILABLE)
                    self.assertEqual(before, after)
                    result = json.loads(output.getvalue())
                    self.assertEqual(result["command"], command)
                    self.assertEqual(result["status"], "blocked")
                    self.assertEqual(
                        result["reason"],
                        "accepted-v2-integration-packets-unavailable",
                    )
                    self.assertIs(result["changed"], False)

    def test_result_does_not_disclose_operator_or_repository_paths(self) -> None:
        secret_path = "/private/operator/location"
        previous = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = secret_path
        self.addCleanup(self._restore_env, "HERMES_HOME", previous)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = install.main(["verify", "--json"])

        self.assertEqual(code, install.EXIT_UNAVAILABLE)
        self.assertNotIn(secret_path, output.getvalue())

    def test_human_output_states_that_no_change_was_made(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = install.main(["install"])
        self.assertEqual(code, install.EXIT_UNAVAILABLE)
        self.assertIn("BLOCKED", output.getvalue())
        self.assertIn("no changes were made", output.getvalue())

    def test_help_is_import_safe_and_successful(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            install.main(["--help"])
        self.assertEqual(raised.exception.code, install.EXIT_OK)
        self.assertIn("accepted Nunchi V2", output.getvalue())

    @staticmethod
    def _restore_env(name: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
