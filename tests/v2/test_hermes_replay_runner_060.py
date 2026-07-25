from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from evals.v2.hermes import runner


ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "evals" / "v2" / "hermes" / "manifest.json"


class HermesReplayRunner060Tests(unittest.TestCase):
    def _copy_bundle(self, directory: str) -> tuple[Path, Path]:
        destination = Path(directory)
        manifest = destination / "manifest.json"
        cases = destination / "cases.jsonl"
        manifest.write_bytes(MANIFEST.read_bytes())
        cases.write_bytes((MANIFEST.parent / "cases.jsonl").read_bytes())
        return manifest, cases

    def test_complete_manifest_executes_every_required_scenario(self):
        report = runner.run_replay(MANIFEST, require_complete=True)

        self.assertEqual("060-v2-hermes", report["slice"])
        self.assertEqual("replay", report["mode"])
        self.assertEqual("repository-fixture", report["source_mode"])
        self.assertEqual("deterministic-replay", report["evidence_mode"])
        self.assertEqual(
            {"source_behavior": False, "installed": False, "live": False},
            report["evidence_claims"],
        )
        self.assertEqual(
            hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
            report["manifest"]["sha256"],
        )
        self.assertEqual(len(runner.REQUIRED_SCENARIO_IDS), report["summary"]["required"])
        self.assertEqual(len(runner.REQUIRED_SCENARIO_IDS), report["summary"]["executed"])
        self.assertEqual(len(runner.REQUIRED_SCENARIO_IDS), report["summary"]["passed"])
        self.assertEqual(0, report["summary"]["failed"])
        self.assertEqual(
            list(runner.REQUIRED_SCENARIO_IDS),
            [item["scenario_id"] for item in report["results"]],
        )

    def test_replay_report_is_byte_deterministic(self):
        first = runner.run_replay(MANIFEST, require_complete=True)
        second = runner.run_replay(MANIFEST, require_complete=True)
        encode = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"))
        self.assertEqual(encode(first), encode(second))

    def test_require_complete_names_every_missing_required_scenario(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest, _ = self._copy_bundle(directory)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            missing = document["scenarios"].pop(0)["id"]
            manifest.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(runner.ManifestValidationError, missing):
                runner.run_replay(manifest, require_complete=True)

    def test_manifest_cannot_claim_fixture_replay_is_installed_or_live_evidence(self):
        for field, value in (
            ("source_mode", "installed-runtime"),
            ("evidence_mode", "live"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                manifest, _ = self._copy_bundle(directory)
                document = json.loads(manifest.read_text(encoding="utf-8"))
                document[field] = value
                manifest.write_text(json.dumps(document), encoding="utf-8")

                with self.assertRaisesRegex(runner.ManifestValidationError, field):
                    runner.run_replay(manifest, require_complete=True)

    def test_expected_result_tampering_fails_the_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest, cases = self._copy_bundle(directory)
            rows = [json.loads(line) for line in cases.read_text(encoding="utf-8").splitlines()]
            rows[0]["expected"]["admitted"] = not rows[0]["expected"]["admitted"]
            cases.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

            with self.assertRaisesRegex(runner.ReplayFailure, rows[0]["scenario_id"]):
                runner.run_replay(manifest, require_complete=True)

    def test_receipt_scenarios_preserve_stage_ownership_and_truth(self):
        report = runner.run_replay(MANIFEST, require_complete=True)
        by_id = {item["scenario_id"]: item for item in report["results"]}

        for suffix, delivery in (("SENT", "sent"), ("FAILED", "failed"), ("UNKNOWN", "unknown")):
            with self.subTest(delivery=delivery):
                receipts = by_id[f"HM060-RECEIPT-{suffix}"]["actual"]["receipts"]
                self.assertEqual(
                    ["participant-host", "transport"],
                    [receipt["stage"] for receipt in receipts],
                )
                self.assertEqual(
                    ["participant-host", "transport"],
                    [receipt["writer"] for receipt in receipts],
                )
                self.assertEqual("unknown", receipts[0]["outcome"])
                self.assertEqual(delivery, receipts[1]["delivery"])

    def test_cli_emits_one_machine_readable_document_and_exact_digest(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = runner.main(
                ["--mode", "replay", "--manifest", str(MANIFEST), "--require-complete"]
            )

        self.assertEqual(0, status)
        self.assertEqual("", stderr.getvalue())
        report = json.loads(stdout.getvalue())
        self.assertEqual(
            hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
            report["manifest"]["sha256"],
        )
        self.assertNotIn("credential", stdout.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
