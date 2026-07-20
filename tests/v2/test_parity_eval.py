from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from evals.v2.parity import runner


class SceneCatalogCases(unittest.TestCase):
    def test_catalog_is_exactly_ordered_s01_through_s18(self):
        catalog = runner.load_catalog()
        self.assertEqual(
            tuple(scene["scene_id"] for scene in catalog["scenes"]),
            runner.EXPECTED_SCENE_IDS,
        )
        self.assertEqual(len(catalog["scenes"]), 18)

    def test_external_obligations_cannot_be_reported_complete_offline(self):
        record = runner.run(
            selected_ids=("S12", "S14"),
            deterministic_time=True,
        )
        self.assertEqual(record["summary"]["mechanics_failed"], [])
        self.assertEqual(record["summary"]["incomplete"], ["S12", "S14"])
        self.assertFalse(record["summary"]["candidate_complete"])
        self.assertEqual(
            [scene["mechanics"] for scene in record["scenes"]],
            ["passed", "not-applicable"],
        )
        self.assertIn(
            "accepted-hermes-v2-packet",
            record["summary"]["missing_external_evidence"],
        )
        self.assertFalse(record["external_evidence_index"]["available"])

    def test_selected_mechanics_scene_runs_its_existing_tests(self):
        record = runner.run(selected_ids=("S17",), deterministic_time=True)
        self.assertEqual(record["scenes"][0]["mechanics"], "passed")
        self.assertIn("S17", record["summary"]["incomplete"])


class RunnerBoundaryCases(unittest.TestCase):
    def test_output_is_exclusive_and_record_is_valid_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evidence.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                first = runner.main(
                    ["--scene", "S12", "--deterministic-time", "--output", str(output)]
                )
                second = runner.main(
                    ["--scene", "S12", "--deterministic-time", "--output", str(output)]
                )
            self.assertEqual(first, 0)
            self.assertEqual(second, 2)
            document = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(document["summary"]["incomplete"], ["S12"])

    def test_unknown_scene_is_a_usage_error(self):
        with redirect_stderr(StringIO()):
            self.assertEqual(runner.main(["--scene", "S99"]), 2)

    def test_require_complete_makes_missing_external_evidence_blocking(self):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(
                runner.main(["--scene", "S14", "--require-complete"]),
                1,
            )


class ExternalEvidenceIndexCases(unittest.TestCase):
    def _git(self, root: Path, *arguments: str) -> str:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout.strip()

    def test_index_is_commit_bound_hash_checked_and_invalidated_by_product_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "nunchi-test@example.invalid")
            self._git(root, "config", "user.name", "Nunchi Test")
            (root / "product.txt").write_text("frozen product\n", encoding="utf-8")
            self._git(root, "add", "product.txt")
            self._git(root, "commit", "-q", "-m", "candidate")
            candidate = self._git(root, "rev-parse", "HEAD")

            evidence_dir = root / "evidence" / "v2" / "parity"
            evidence_dir.mkdir(parents=True)
            artifact = evidence_dir / "review.json"
            artifact.write_text('{"review":"pass"}\n', encoding="utf-8")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            index = evidence_dir / "external-evidence-index.json"
            index.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "candidate_commit": candidate,
                        "records": [
                            {
                                "evidence_id": "cross-family-participant-behavior-review",
                                "candidate_commit": candidate,
                                "status": "PASS",
                                "recorded_at": "2026-07-20T16:00:00Z",
                                "attestations": [
                                    {"identity": "independent-reviewer", "family": "anthropic"}
                                ],
                                "artifacts": [
                                    {
                                        "path": "evidence/v2/parity/review.json",
                                        "sha256": digest,
                                    }
                                ],
                                "limitations": [],
                            }
                        ],
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            self._git(root, "add", "evidence")
            self._git(root, "commit", "-q", "-m", "review evidence")

            loaded = runner.load_external_evidence_index(root=root)
            self.assertTrue(loaded["available"])
            self.assertEqual(loaded["candidate_commit"], candidate)
            self.assertEqual(
                loaded["records"]["cross-family-participant-behavior-review"]["status"],
                "satisfied",
            )

            document = json.loads(index.read_text(encoding="utf-8"))
            document["records"][0]["attestations"][0]["family"] = "openai"
            index.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")
            self._git(root, "add", str(index.relative_to(root)))
            self._git(root, "commit", "-q", "-m", "same-family review")
            with self.assertRaisesRegex(runner.EvidenceIndexError, "non-OpenAI"):
                runner.load_external_evidence_index(root=root)

            document["records"][0]["attestations"][0]["family"] = "anthropic"
            index.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")
            artifact.write_text('{"review":"changed-after-attestation"}\n', encoding="utf-8")
            with self.assertRaisesRegex(runner.EvidenceIndexError, "committed cleanly"):
                runner.load_external_evidence_index(root=root)
            self._git(root, "add", "evidence")
            self._git(root, "commit", "-q", "-m", "drifted review artifact")
            with self.assertRaisesRegex(runner.EvidenceIndexError, "digest does not match"):
                runner.load_external_evidence_index(root=root)

            document["records"][0]["artifacts"][0]["sha256"] = hashlib.sha256(
                artifact.read_bytes()
            ).hexdigest()
            index.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")
            self._git(root, "add", str(index.relative_to(root)))
            self._git(root, "commit", "-q", "-m", "re-attested review artifact")
            self.assertTrue(runner.load_external_evidence_index(root=root)["available"])

            (root / "product.txt").write_text("changed product\n", encoding="utf-8")
            self._git(root, "add", "product.txt")
            self._git(root, "commit", "-q", "-m", "unreviewed successor")
            with self.assertRaisesRegex(runner.EvidenceIndexError, "unchanged frozen"):
                runner.load_external_evidence_index(root=root)


if __name__ == "__main__":
    unittest.main()
