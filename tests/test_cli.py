import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.provider_helpers import fixture_case, provider_env
from tests.test_core import load_fixture
from turnaware import evaluate

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures"


def run_cli(args=None, stdin=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    cmd = [sys.executable, "-m", "turnaware", "admit"]
    if args:
        cmd.extend(args)
    return subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


class CliTests(unittest.TestCase):
    def test_admit_reads_json_from_stdin_and_writes_success_json(self):
        fixture = (FIXTURE_DIR / "speak.json").read_text(encoding="utf-8")

        with patch.dict(os.environ, fixture_case("speak", "SPEAK"), clear=True):
            completed = run_cli(stdin=fixture)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["classifier"], "product")
        self.assertEqual(payload["verdict"], "SPEAK")
        self.assertEqual(completed.stderr, "")

    def test_admit_reads_json_from_file(self):
        env = provider_env(
            "PASS",
            checked=["trigger:trigger-pass", "context:ctx-pass-handled"],
            confidences={"PASS": 0.8, "ACK": 0.05, "ASK": 0.1, "SPEAK": 0.05},
        )
        with patch.dict(os.environ, env, clear=True):
            completed = run_cli(["--input", str(FIXTURE_DIR / "pass.json")])

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["classifier"], "product")
        self.assertEqual(payload["verdict"], "PASS")
        self.assertNotIn("reply", payload)

    def test_cli_classifier_overrides_envelope_classifier(self):
        with patch.dict(os.environ, fixture_case("speak-cli-precedence", "SPEAK"), clear=True):
            completed = run_cli(["--classifier", "product", "--input", str(FIXTURE_DIR / "speak_cli_precedence.json")])

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["classifier"], "product")
        self.assertEqual(payload["verdict"], "SPEAK")

    def test_cli_classifier_config_json_is_used(self):
        env = fixture_case("speak", "SPEAK")
        with patch.dict(os.environ, env, clear=True):
            completed = run_cli([
                "--classifier",
                "product",
                "--classifier-config",
                '{"model": "turnaware-test-model"}',
                "--input",
                str(FIXTURE_DIR / "speak.json"),
            ])

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["classifier"], "product")
        self.assertEqual(payload["classifier_model"], "turnaware-test-model")

    def test_cli_and_core_are_contract_equivalent_for_fixture_set(self):
        fixture_cases = {
            "pass": ("PASS", ["trigger:trigger-pass", "context:ctx-pass-handled"]),
            "ack": ("ACK", ["trigger:trigger-ack"]),
            "ask": ("ASK", ["trigger:trigger-ask"]),
            "speak": ("SPEAK", ["trigger:trigger-speak"]),
            "false_ack_comment_back": (
                "SPEAK",
                ["trigger:trigger-false-ack-comment-back", "context:ctx-false-ack-assignment"],
            ),
            "false_pass_contradicted_done": (
                "SPEAK",
                ["trigger:trigger-false-pass-contradicted-done", "context:ctx-false-pass-missing-work"],
            ),
            "false_pass_no_corroboration": ("ASK", ["trigger:trigger-false-pass-no-corroboration"]),
        }
        for fixture_name, (expected, checked) in fixture_cases.items():
            with self.subTest(fixture=fixture_name):
                env = provider_env(expected, checked=checked)
                with patch.dict(os.environ, env, clear=True):
                    completed = run_cli(["--input", str(FIXTURE_DIR / f"{fixture_name}.json")])
                    core_payload = evaluate(load_fixture(fixture_name), classifier="product")
                self.assertEqual(completed.returncode, 0, completed.stderr)
                cli_payload = json.loads(completed.stdout)
                self.assertEqual(cli_payload, core_payload)

    def test_invalid_classifier_fails_without_success_stdout(self):
        completed = run_cli(["--classifier", "does-not-exist", "--input", str(FIXTURE_DIR / "speak.json")])

        self.assertEqual(completed.returncode, 3)
        self.assertEqual(completed.stdout, "")
        self.assertIn("unsupported classifier", completed.stderr.lower())

    def test_malformed_json_fails_as_input_error(self):
        completed = run_cli(stdin="{not json")

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("input error", completed.stderr.lower())

    def test_missing_trigger_fails_as_validation_error(self):
        completed = run_cli(stdin="{}")

        self.assertEqual(completed.returncode, 3)
        self.assertEqual(completed.stdout, "")
        self.assertIn("validation error", completed.stderr.lower())

    def test_missing_input_file_fails_as_input_error(self):
        completed = run_cli(["--input", str(FIXTURE_DIR / "missing.json")])

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("input error", completed.stderr.lower())


if __name__ == "__main__":
    unittest.main()
