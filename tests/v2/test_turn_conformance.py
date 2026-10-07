"""The turn conformance kit (#94 step 9d): its checks catch broken rules."""

from __future__ import annotations

import unittest
from unittest import mock

from nunchi import turn, turn_conformance as kit
from nunchi.integrations.claude_code_conformance import ClaudeCodeKitIntegration


def _run(integrations):
    return [kit.run_scenario(name, integration) for integration in integrations for name in kit.SCENARIOS]


class TurnConformanceTests(unittest.TestCase):
    def test_the_reference_and_the_claude_code_gate_pass_every_scenario_for_their_style(self):
        results = _run(
            [kit.ReferenceIntegration("tools"), kit.ReferenceIntegration("final-answer"), ClaudeCodeKitIntegration()]
        )
        failing = [(r["integration"], r["scenario"], r["failures"]) for r in results if r["status"] == "fail"]
        self.assertEqual([], failing)
        passed = {(r["integration"], r["scenario"]) for r in results if r["status"] == "pass"}
        tools = {name for name, scenario in kit.SCENARIOS.items() if scenario.posting == "tools"}
        self.assertEqual(tools, {name for integration, name in passed if integration == "Claude Code gate"})

    def test_the_checks_catch_broken_rules(self):
        with mock.patch.object(turn.Turn, "look_again", lambda self, action: None), mock.patch.object(
            turn.SecretGuard, "refusal", lambda self, action: None
        ), mock.patch.object(turn.Turn, "after_tool_call", lambda self: None):
            results = _run([kit.ReferenceIntegration("tools"), kit.ReferenceIntegration("final-answer")])
        failed = {r["scenario"] for r in results if r["status"] == "fail"}
        self.assertEqual({"look-again", "steering", "secret", "final-look-again", "final-secret"}, failed)

    def test_the_parity_table_has_a_row_per_scenario_and_a_column_per_integration(self):
        results = _run([kit.ReferenceIntegration("tools")])
        table = kit.parity_table(results).splitlines()
        self.assertEqual("| Scenario | reference (tools) |", table[0])
        self.assertEqual(len(kit.SCENARIOS) + 2, len(table))
        self.assertIn("| final-deliver: ", table[2 + list(kit.SCENARIOS).index("final-deliver")])
        self.assertTrue(table[2 + list(kit.SCENARIOS).index("final-deliver")].endswith("| n/a |"))

    def test_the_command_runs_the_reference_by_default(self):
        with mock.patch("builtins.print"):
            self.assertEqual(0, kit.main([]))


if __name__ == "__main__":
    unittest.main()
