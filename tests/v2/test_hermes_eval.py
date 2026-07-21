from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from evals.v2.hermes.runner import run_all, write_results
from scripts.verify_hermes_v2_packet import validate


ROOT = Path(__file__).resolve().parents[2]
HERMES_SOURCE = Path("/Users/zmll/.hermes/hermes-agent")


class HermesV2EvaluationTest(unittest.TestCase):
    def test_fixture_corpus_covers_hm01_through_hm05_and_action_surface(self):
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "v2" / "hermes" / "cases.json").read_text()
        )
        ids = {row["fixture_id"] for row in fixture["cases"]}
        cases = {row["hm_case_id"] for row in fixture["cases"]}
        self.assertTrue({"HM-01", "HM-02", "HM-03", "HM-04", "HM-05"} <= cases)
        self.assertIn("hermes-action-surface-matrix", ids)

    def test_hm01_through_hm06_pass_against_pinned_installed_source(self):
        rows = run_all(hermes_source=HERMES_SOURCE)
        self.assertEqual([row["hm_case_id"] for row in rows], [
            "HM-01", "HM-02", "HM-03", "HM-04", "HM-05", "HM-06"
        ])
        self.assertTrue(all(row["result"] == "PASS" for row in rows), rows)
        self.assertTrue(all(row["scene_id"] for row in rows))

    def test_results_are_written_as_replayable_jsonl(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "hermes-scenes.jsonl"
            rows = write_results(output, hermes_source=HERMES_SOURCE)
            self.assertEqual(len(output.read_text().splitlines()), 6)
            self.assertEqual(len(rows), 6)

    def test_complete_packet_requires_canonical_slice_lifecycle_records(self):
        errors = validate(
            hermes_source=HERMES_SOURCE,
            require_lifecycle=True,
        )
        self.assertEqual(
            [error for error in errors if error.startswith("missing-lifecycle:")],
            [
                "missing-lifecycle:evidence/v2/hermes/slice-activation.md",
                "missing-lifecycle:evidence/v2/hermes/slice-candidate.md",
                "missing-lifecycle:evidence/v2/hermes/slice-handoff.md",
            ],
        )

    def test_scene_verifier_rejects_false_duplicate_and_incompatible_rows(self):
        rows = run_all(hermes_source=HERMES_SOURCE)
        catalog = [
            json.loads(line)
            for line in (ROOT / "evals/v2/hermes/scenes.jsonl").read_text().splitlines()
            if line.strip()
        ]
        false_rows = json.loads(json.dumps(rows))
        assertion = next(iter(false_rows[0]["assertions"]))
        false_rows[0]["assertions"][assertion] = False
        incompatible = json.loads(json.dumps(rows))
        incompatible[0]["claim"] = "invented claim"
        cases = (
            (false_rows, f"hm-assertion-not-true:HM-01:{assertion}"),
            ([*rows, rows[-1]], "hm-case-duplicate"),
            (incompatible, "hm-catalog-mismatch:HM-01:claim"),
        )
        for candidate_rows, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                evidence = root / "evidence/v2/hermes/hermes-scenes.jsonl"
                evidence.parent.mkdir(parents=True)
                evidence.write_text(
                    "\n".join(json.dumps(row) for row in candidate_rows) + "\n"
                )
                scene_catalog = root / "evals/v2/hermes/scenes.jsonl"
                scene_catalog.parent.mkdir(parents=True)
                scene_catalog.write_text(
                    "\n".join(json.dumps(row) for row in catalog) + "\n"
                )
                self.assertIn(
                    expected,
                    validate(hermes_source=HERMES_SOURCE, root=root),
                )

    def test_lifecycle_verifier_rejects_nonempty_junk_while_slice_is_planned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker = root / "scripts/check_governance.py"
            checker.parent.mkdir(parents=True)
            checker.write_text("raise SystemExit(1)\n")
            for relative in (
                "evidence/v2/hermes/slice-activation.md",
                "evidence/v2/hermes/slice-candidate.md",
                "evidence/v2/hermes/slice-handoff.md",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("junk\n")
            self.assertIn(
                "lifecycle-governance-invalid",
                validate(
                    hermes_source=HERMES_SOURCE,
                    root=root,
                    require_lifecycle=True,
                ),
            )

    def test_manifest_scope_detects_omitted_dirty_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"],
                cwd=root, check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"], cwd=root, check=True
            )
            candidate = root / "candidate.py"
            candidate.write_text("before\n")
            subprocess.run(["git", "add", "candidate.py"], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "baseline"], cwd=root, check=True
            )
            candidate.write_text("after\n")
            manifest = root / "evidence/v2/hermes/candidate-files.sha256"
            manifest.parent.mkdir(parents=True)
            manifest.write_text("# intentionally omitted candidate\n")
            self.assertIn(
                "candidate-manifest-omitted:candidate.py",
                validate(hermes_source=HERMES_SOURCE, root=root),
            )


if __name__ == "__main__":
    unittest.main()
