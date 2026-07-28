"""Truthfulness guards for the active V2 product and delivery documentation."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "AGENTS.md"
README = ROOT / "README.md"
DELIVERY = ROOT / "docs" / "v2-delivery.md"
PLATFORM = ROOT / "docs" / "platform-v2.md"
HERMES_README = ROOT / "integrations" / "hermes" / "README.md"
HERMES_GUIDE = ROOT / "docs" / "integrations" / "hermes-v2.md"
VERIFICATION = ROOT / "docs" / "v2-verification.md"
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
            "public gateway participant-hook API major 2",
            "Runtime capability negotiation",
            "must land in a Hermes release",
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

    def test_hermes_guide_documents_capability_negotiation_and_release_blocker(self) -> None:
        normalized = " ".join(HERMES_README.read_text(encoding="utf-8").split())
        for phrase in (
            "versioned public gateway participant hooks",
            "Nunchi does not modify, replace, or wrap Hermes files",
            "`PluginContext.gateway_message_hook_api_version == 2`",
            "must land in a Hermes release",
            "Ordinary users cannot activate",
            "Nunchi V2 was not activated",
            "`hermes update`",
            "does not claim an upstream merge, release, or acceptance",
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

    def test_active_hermes_docs_have_no_obsolete_exact_host_patch_claims(self) -> None:
        plugin_package = (
            ROOT
            / "integrations"
            / "hermes"
            / "nunchi-gate"
            / "nunchi_hermes_v2"
        )
        self.assertFalse((plugin_package / "host_patch.py").exists())
        self.assertFalse((plugin_package / "host_patch_assets").exists())
        self.assertFalse(
            (ROOT / "docs" / "integrations" / "hermes-v2-host-seam.md").exists()
        )
        for document in (
            HERMES_README,
            HERMES_GUIDE,
            PLATFORM,
            VERIFICATION,
            ROOT / "docs" / "INSTALL.md",
            ROOT / "docs" / "STABILITY.md",
        ):
            text = document.read_text(encoding="utf-8")
            with self.subTest(document=document.relative_to(ROOT)):
                for obsolete in (
                    "hermes-agent==0.19.0",
                    "v2026.7.20",
                    "3ef6bbd201263d354fd83ec55b3c306ded2eb72a",
                    "nunchi-hermes-v2-host-patch",
                    "host_patch_assets",
                ):
                    self.assertNotIn(obsolete, text)

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
