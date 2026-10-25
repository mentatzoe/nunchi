"""Truthfulness guards for the active V2 product and delivery documentation."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "AGENTS.md"
README = ROOT / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
PLATFORM = ROOT / "docs" / "platform-v2.md"


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
            "the incomplete Codex and Claude Code integrations",
            "Hermes has no supported path today",
            "The old Hermes integration was removed on 2026-10-11",
            "Historical Hermes evidence is not current proof",
            "installed-runtime checks, not live ones",
            "it has not run in a real room",
            "issues/43",
            "issue #41",
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
            "Ask the maintainer only when a choice materially changes product behavior",
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
            "current downstream interface for Claude Code and Codex",
            "These implementations consume the shared owners",
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
