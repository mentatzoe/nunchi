"""Truthfulness guards for the active V2 product and delivery documentation."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "AGENTS.md"
README = ROOT / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
DELIVERY = ROOT / "docs" / "v2-delivery.md"
COMPLETION_GOAL = ROOT / "docs" / "v2-completion-goal.md"
PLATFORM = ROOT / "docs" / "platform-v2.md"
EXECUTION_SPINE = ROOT / "docs" / "governance" / "execution-spine.md"
SPECS_README = ROOT / "specs" / "README.md"


def _normalized(path: Path) -> str:
    """Collapse whitespace and blockquote markers so wrapped phrases match."""
    lines = (
        line.lstrip().removeprefix(">")
        for line in path.read_text(encoding="utf-8").splitlines()
    )
    return " ".join(" ".join(lines).split())


class V2DocumentationTruthfulnessTests(unittest.TestCase):
    def test_readme_describes_one_v2_path_and_platform_scope(self) -> None:
        normalized = _normalized(README)
        required = (
            "native event -> canonical observation -> participant-bound attention",
            "Conversation events are observations, not reply obligations",
            "Only the exact participant's delegated attention model",
            "There is no executable V1 `admit` command",
            "V2 is on `main` and is partial: **merged, unverified**",
            "No surface has passed a live real-room check",
            "incomplete Hermes, Codex, and Claude Code integrations",
            "Historical Hermes evidence is not current proof",
            "normal turns, ordinary tools, native approval, ACK",
            "installed-runtime checks, not live ones",
            "it has not run in a real room",
            "issues/43",
            "issue #41",
            "issues/44",
            "Source review, clean-wheel installation, configured probes",
        )
        for phrase in required:
            with self.subTest(required=phrase):
                self.assertIn(phrase, normalized)
        forbidden = (
            "Moving-main CI currently proves host contracts, not normal turns",
            "in candidate source",
            "headless runner",
        )
        for phrase in forbidden:
            with self.subTest(forbidden=phrase):
                self.assertNotIn(phrase, normalized)

    def test_delivery_guide_is_product_first_and_uses_the_working_agreement(
        self,
    ) -> None:
        normalized = _normalized(DELIVERY)
        required = (
            "**missing**",
            "**implemented, unverified**",
            "**merged, unverified**",
            "**verified**",
            "a current `main` is not a claim that V2 is complete",
            "issues/41",
            "issues/43",
            "issues/44",
            "Pick the earliest missing behavior the product needs",
            "Scale review to the size and risk of the change",
            "Cross-family independent review is not required for day-to-day delivery",
            "Merge when CI is green",
            "run every consumer's tests in the same PR",
            "A packet, label, test file, or report does not pass merely by existing",
            "platform-owned",
            "non-author review",
            "may be described as done, live, or parity-ready until its open gates pass",
            "docs/platform-v2.md",
            "tests/v2/contract",
        )
        for phrase in required:
            with self.subTest(required=phrase):
                self.assertIn(phrase, normalized)
        forbidden = (
            "git merge-base --is-ancestor",
            "Landed, unverified",
            "**Integrated**",
            "issues/40)",
        )
        for phrase in forbidden:
            with self.subTest(forbidden=phrase):
                self.assertNotIn(phrase, normalized)

    def test_completion_goal_records_the_main_and_review_decision(self) -> None:
        normalized = _normalized(COMPLETION_GOAL)
        required = (
            "Decision, Zoe, 2026-10-04",
            "`main` holds V2 before completion",
            "now govern the release tag (`v*`), not the merge to `main`",
            "The final completion decision and the release proof are unchanged",
        )
        for phrase in required:
            with self.subTest(required=phrase):
                self.assertIn(phrase, normalized)

    def test_changelog_has_one_unreleased_section_that_describes_main(
        self,
    ) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertEqual(text.count("## [Unreleased]"), 1)
        self.assertEqual(text.count("\n## Unreleased"), 0)
        normalized = " ".join(text.split())
        self.assertIn("is **merged, unverified**", normalized)
        self.assertNotIn("neither implemented nor armed", normalized)

    def test_agent_guidance_cannot_turn_process_friction_into_a_stop_condition(
        self,
    ) -> None:
        normalized = _normalized(AGENTS)
        required = (
            "not by itself a blocker",
            "continue other unblocked product work",
            "Do not narrow supported behavior",
            "Ask Zoe only when a choice materially changes product behavior",
            "`main` is the working branch and holds V2",
            "Scale review to the size and risk of the change",
            "Only the exact participant's delegated model may make a social suppression judgment",
            "The shared core names no agent host, chat platform, or model vendor",
            "**missing**, **implemented, unverified**, **merged, unverified**, and **verified**",
        )
        for phrase in required:
            with self.subTest(required=phrase):
                self.assertIn(phrase, normalized)
        self.assertNotIn("report the concrete missing outcome and stop", normalized)

    def test_platform_interface_keeps_social_judgment_and_authority_separate(
        self,
    ) -> None:
        normalized = _normalized(PLATFORM)
        required = (
            "current downstream interface for Hermes and Claude Code",
            "Both platform implementations consume the shared owners",
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
