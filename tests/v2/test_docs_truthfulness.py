"""Truthfulness guards for the active V2 product and delivery documentation."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "AGENTS.md"
README = ROOT / "README.md"
DELIVERY = ROOT / "docs" / "v2-delivery.md"
PLATFORM = ROOT / "docs" / "platform-v2.md"
HERMES_README = ROOT / "integrations" / "hermes" / "README.md"
HOST_SEAM = ROOT / "docs" / "integrations" / "hermes-v2-host-seam.md"
VERIFICATION = ROOT / "docs" / "v2-verification.md"
HOST_ASSETS = (
    ROOT
    / "integrations"
    / "hermes"
    / "nunchi-gate"
    / "nunchi_hermes_v2"
    / "host_patch_assets"
)
EXECUTION_SPINE = ROOT / "docs" / "governance" / "execution-spine.md"
SPECS_README = ROOT / "specs" / "README.md"
FOUNDATION_COMMIT = "014546d2ec685341106b177bcf2f6e52e758e0a9"


class V2DocumentationTruthfulnessTests(unittest.TestCase):
    def test_readme_describes_one_v2_path_and_explicit_exclusions(self) -> None:
        normalized = " ".join(README.read_text(encoding="utf-8").split())
        required = (
            "native event -> canonical observation -> participant-bound attention",
            "Conversation events are observations, not reply obligations",
            "Only the exact participant's delegated attention model",
            "There is no executable V1 `admit` command",
            "Hermes V2 participant integration",
            "Source review, clean-wheel installation, configured probes",
        )
        for phrase in required:
            with self.subTest(required=phrase):
                self.assertIn(phrase, normalized)

    def test_delivery_guide_is_product_first_and_handoff_is_ancestry_bound(
        self,
    ) -> None:
        normalized = " ".join(DELIVERY.read_text(encoding="utf-8").split())
        required = (
            "Missing",
            "Implemented, unverified",
            "Verified",
            "Integrated",
            "Select the earliest missing product behavior",
            "A packet, label, test file, or report does not pass merely by existing",
            "platform-owned",
            "non-author review",
            FOUNDATION_COMMIT,
            "git merge-base --is-ancestor",
            "docs/platform-v2.md",
            "tests/v2/contract",
        )
        for phrase in required:
            with self.subTest(required=phrase):
                self.assertIn(phrase, normalized)

    def test_agent_guidance_cannot_turn_process_friction_into_a_stop_condition(
        self,
    ) -> None:
        normalized = " ".join(AGENTS.read_text(encoding="utf-8").split())
        required = (
            "not by itself a blocker",
            "continue other unblocked product work",
            "Do not narrow supported behavior",
            "Ask Zoe only when a choice materially changes product behavior",
        )
        for phrase in required:
            with self.subTest(required=phrase):
                self.assertIn(phrase, normalized)
        self.assertNotIn("report the concrete missing outcome and stop", normalized)

    def test_platform_interface_keeps_social_judgment_and_authority_separate(
        self,
    ) -> None:
        normalized = " ".join(PLATFORM.read_text(encoding="utf-8").split())
        required = (
            "complete downstream interface for platform adapters",
            "Nunchi-owned, exact-version compatibility seam",
            "no upstream NousResearch or developer-checkout dependency",
            "exactly one participant-delegated social judgment",
            "requester, scope, digest, approval, expiry, revocation",
            "Room payloads are never trusted configuration",
            "A downstream platform candidate must reuse these shared owners",
            "authenticated native self and wrong-route cases",
            "active-plus-newest-pending coalescing",
            "clean installed-artifact probes and attributable real-platform evidence",
        )
        for phrase in required:
            with self.subTest(required=phrase):
                self.assertIn(phrase, normalized)

    def test_hermes_guide_keeps_compatibility_delivery_inside_nunchi(self) -> None:
        normalized = " ".join(HERMES_README.read_text(encoding="utf-8").split())
        for phrase in (
            "complete compatibility implementation travels in the Nunchi artifact",
            "do not depend on an upstream NousResearch change",
            "untouched Hermes `v2026.7.20`",
            "closed, exact-version compatibility patch",
            "transactional applicator",
            "nunchi-hermes-v2-host-patch",
            "no source checkout or Git metadata is required",
            "--rollback",
            "No repository checkout or editable install counts",
        ):
            with self.subTest(required=phrase):
                self.assertIn(phrase, normalized)

    def test_hermes_guide_documents_the_actual_config_generator_interface(self) -> None:
        text = HERMES_README.read_text(encoding="utf-8")
        for flag in (
            "--hermes-profile",
            "--platform",
            "--room-id",
            "--actor-id",
            "--participant-id",
            "--profile-id",
            "--instructions-file",
            "--output-dir",
            "--state-root",
        ):
            with self.subTest(required_flag=flag):
                self.assertIn(flag, text)
        for obsolete in ("--config", "--participant-profile", "--state-dir"):
            with self.subTest(obsolete_flag=obsolete):
                self.assertNotIn(obsolete, text)

    def test_host_seam_documented_digests_match_bundled_artifacts(self) -> None:
        manifest = HOST_ASSETS / "manifest.json"
        manifest_bytes = manifest.read_bytes()
        manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
        patch_name = json.loads(manifest_bytes)["patch"]
        patch_digest = hashlib.sha256((HOST_ASSETS / patch_name).read_bytes()).hexdigest()

        for document in (HOST_SEAM, VERIFICATION):
            text = document.read_text(encoding="utf-8")
            with self.subTest(document=document.relative_to(ROOT)):
                self.assertIn(manifest_digest, text)
                self.assertIn(patch_digest, text)

    def test_spec_workflow_remains_retired(self) -> None:
        self.assertFalse(
            [path for path in (ROOT / ".specify").rglob("*") if path.is_file()]
        )
        self.assertFalse((ROOT / "scripts" / "run_slice_workflow.py").exists())
        self.assertFalse((ROOT / "scripts" / "check_governance.py").exists())
        self.assertFalse(list(ROOT.glob("specs/**/tasks.md")))
        self.assertFalse(list(ROOT.glob("specs/**/checklists/*.md")))
        for path in sorted(ROOT.glob("specs/*/spec.md")) + sorted(
            ROOT.glob("specs/*/plan.md")
        ):
            with self.subTest(reference=path.relative_to(ROOT)):
                self.assertIn("**Reference only.**", path.read_text(encoding="utf-8"))

        self.assertIn(
            "reference documents, not an executable workflow",
            SPECS_README.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "retired on 2026-07-24",
            EXECUTION_SPINE.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
