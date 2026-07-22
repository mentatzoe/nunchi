from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from evals.v2.hermes.runner import run_all, write_results
from scripts.verify_hermes_v2_packet import EXPECTED_HERMES_COMMIT, validate


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
        matrix = next(
            row
            for row in fixture["cases"]
            if row["fixture_id"] == "hermes-action-surface-matrix"
        )
        self.assertEqual(
            set(matrix["supported"]),
            {
                "normal-final-message",
                "normal-silence",
                "explicit-non-privileged-tool-after-participant-receipt",
                "I-040B-authorized-file-terminal-host-command",
                "I-040B-authorized-canonical-room-reaction",
            },
        )
        self.assertEqual(
            set(matrix["fail_closed"]),
            {
                "privileged-model-tool-effect-without-I-040B-authorization",
                "cross-room-reaction",
                "approval-required-effect-from-room-prose",
            },
        )
        self.assertNotIn("reaction", matrix["unsupported"])

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

    def test_verifier_rejects_stale_documented_installed_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = root / "docs/integrations/hermes-v2.md"
            document.parent.mkdir(parents=True)
            document.write_text(
                "Installed Hermes classes at `0.19.0` / "
                f"`{EXPECTED_HERMES_COMMIT}`; stale mirror "
                "`f657840e06e03b9552cf2d28175a1e4e4af0210b`.\n"
            )
            self.assertIn(
                "hermes-provenance:docs/integrations/hermes-v2.md",
                validate(hermes_source=HERMES_SOURCE, root=root),
            )

    def test_verifier_rejects_role_swapped_documented_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = root / "docs/integrations/hermes-v2.md"
            document.parent.mkdir(parents=True)
            document.write_text(
                "- Installed Hermes version: `0.19.0`\n"
                "- Installed Hermes commit: "
                "`8e64746970f9910d03b372291c5aa173883e869f`\n"
                f"- Candidate base: `{EXPECTED_HERMES_COMMIT}`\n"
            )
            self.assertIn(
                "hermes-provenance:docs/integrations/hermes-v2.md",
                validate(hermes_source=HERMES_SOURCE, root=root),
            )

    def test_verifier_rejects_installed_version_mismatch_and_tracked_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "candidate"
            root.mkdir()
            source = Path(directory) / "hermes"
            source.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=source, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"],
                cwd=source,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"], cwd=source, check=True
            )
            (source / "pyproject.toml").write_text(
                '[project]\nname = "hermes-agent"\nversion = "0.18.0"\n'
            )
            tracked = source / "tracked.py"
            tracked.write_text("clean = True\n")
            subprocess.run(["git", "add", "."], cwd=source, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "fixture"], cwd=source, check=True
            )
            tracked.write_text("clean = False\n")
            (source / "sitecustomize.py").write_text("DRIFT = True\n")

            errors = validate(hermes_source=source, root=root)
            self.assertIn("hermes-version:0.18.0", errors)
            self.assertIn("hermes-tracked-dirty", errors)
            self.assertIn("hermes-untracked:sitecustomize.py", errors)

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

    def test_manifest_scope_excludes_tracked_manifest_from_its_own_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"], cwd=root, check=True
            )
            candidate = root / "candidate.py"
            manifest = root / "evidence/v2/hermes/candidate-files.sha256"
            manifest.parent.mkdir(parents=True)
            candidate.write_text("before\n")
            before = hashlib.sha256(candidate.read_bytes()).hexdigest()
            manifest.write_text(f"{before}  candidate.py\n")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "baseline"], cwd=root, check=True
            )

            candidate.write_text("after\n")
            after = hashlib.sha256(candidate.read_bytes()).hexdigest()
            manifest.write_text(f"{after}  candidate.py\n")
            errors = validate(hermes_source=HERMES_SOURCE, root=root)

            self.assertNotIn(
                "candidate-manifest-omitted:evidence/v2/hermes/candidate-files.sha256",
                errors,
            )
            self.assertNotIn("candidate-manifest-extra:candidate.py", errors)


if __name__ == "__main__":
    unittest.main()
