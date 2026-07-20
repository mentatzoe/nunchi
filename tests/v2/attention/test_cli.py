from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from nunchi.cli import main
from tests.v2.attention.test_core import judgment
from tests.v2.contract.schema_helpers import make_request, validate_attention_decision
from tests.v2.security.helpers import clone_policy, write_policy


class AttentionV2CLICases(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.receipts = Path(self.temporary.name) / "receipts"
        self.receipts.mkdir(mode=0o700)
        document = clone_policy()
        document["recoverability"]["continuity_scope_id"] = "discord:room:42#2026-07"
        document["receipt_sink"]["directory"] = str(self.receipts)
        self.config = write_policy(self.temporary.name, document)

    def run_cli(self, stdin: str, config: Path | None = None):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch("sys.stdin", io.StringIO(stdin)),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = main(["attention-v2", "--config", str(config or self.config)])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_ok_writes_one_json_result_and_one_receipt(self):
        with patch(
            "nunchi.classifiers.classify_attention_v2",
            return_value=judgment("WAKE"),
        ):
            code, stdout, stderr = self.run_cli(json.dumps(make_request()))
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        result = json.loads(stdout)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(validate_attention_decision(result), [])
        files = list(self.receipts.iterdir())
        self.assertEqual(len(files), 1)
        self.assertEqual(json.loads(files[0].read_text()), {
            "body": {
                "classifier": {
                    "model": "participant-shaped-model",
                    "name": "participant-shaped-v2",
                    "provider": "openai-compatible",
                },
                "classifier_disposition": "WAKE",
                "effective_disposition": "WAKE",
                "evidence_event_ids": ["e1"],
                "policy_provenance": json.loads(self.config.read_text())["source"]
                + "@sha256:"
                + __import__("hashlib").sha256(self.config.read_bytes()).hexdigest(),
                "routing_audit": {
                    "margin_status": "active",
                    "override_cause": "none",
                    "valve": "none",
                },
            },
            "request_id": "req-0001",
            "stage": "attention",
            "writer": "attention-engine",
        })

    def test_invalid_json_is_stderr_only_exit_2_before_config(self):
        missing = Path(self.temporary.name) / "missing.json"
        code, stdout, stderr = self.run_cli("{", missing)
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("input error", stderr)

    def test_config_failure_is_tagged_exit_3(self):
        missing = Path(self.temporary.name) / "missing.json"
        code, stdout, stderr = self.run_cli(json.dumps(make_request()), missing)
        self.assertEqual(code, 3)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["error"]["code"], "configuration-error")

    def test_request_validation_failure_is_tagged_exit_3(self):
        request = make_request()
        del request["self"]["actor_id"]
        code, stdout, stderr = self.run_cli(json.dumps(request))
        self.assertEqual(code, 3)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["error"]["code"], "invalid-request")

    def test_provider_failure_is_tagged_exit_1(self):
        with patch(
            "nunchi.classifiers.classify_attention_v2",
            side_effect=RuntimeError("provider secret"),
        ):
            code, stdout, stderr = self.run_cli(json.dumps(make_request()))
        self.assertEqual(code, 1)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["error"]["code"], "provider-error")
        self.assertNotIn("secret", stdout)


if __name__ == "__main__":
    unittest.main()
