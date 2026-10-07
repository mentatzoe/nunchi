"""The turn conformance kit (#94 step 9d): its checks catch broken rules."""

from __future__ import annotations

import unittest
from unittest import mock

from nunchi import pipeline, turn, turn_conformance as kit
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
        ), mock.patch.object(turn.Turn, "after_tool_call", lambda self: None), mock.patch.object(
            turn.Turn, "keep_note", lambda self, text: None
        ):
            results = _run([kit.ReferenceIntegration("tools"), kit.ReferenceIntegration("final-answer")])
        failed = {r["scenario"] for r in results if r["status"] == "fail"}
        self.assertEqual(
            {
                "look-again", "steering", "secret", "silence-reason", "pause",
                "final-look-again", "final-secret", "final-silence", "final-pause",
            },
            failed,
        )

    def test_the_pause_and_outcome_checks_catch_a_library_that_does_not_start_them(self):
        later = {"pause", "outcome", "final-pause", "final-outcome"}

        def run_later():
            integrations = [kit.ReferenceIntegration("tools"), kit.ReferenceIntegration("final-answer")]
            return {
                result["scenario"]: result
                for result in (kit.run_scenario(name, integration) for integration in integrations for name in later)
                if result["status"] != "n/a"
            }

        with mock.patch.object(pipeline.NunchiV2Pipeline, "_arm_look_again", lambda *args: None):
            results = run_later()
        self.assertEqual({"pause", "final-pause"}, {name for name, r in results.items() if r["status"] == "fail"})
        with mock.patch.object(pipeline.AsyncDeliveryLane, "outcome_arrived", lambda *args: None):
            results = run_later()
        self.assertEqual({"outcome", "final-outcome"}, {name for name, r in results.items() if r["status"] == "fail"})
        self.assertIn("the outcome turn never reached the agent", results["outcome"]["failures"][0])
        # The agent must be told why the library started the turn.
        run = pipeline.NunchiV2Pipeline.run_opportunities
        with mock.patch.object(
            pipeline.NunchiV2Pipeline, "run_opportunities", lambda self, token, occasion=None: run(self, token)
        ):
            results = run_later()
        self.assertEqual(later, {name for name, r in results.items() if r["status"] == "fail"})

    def test_a_room_without_reactions_fails_the_mhm_scenarios(self):
        from nunchi.reactions import UNAVAILABLE_REACTION_CAPABILITY

        with mock.patch(
            "nunchi.participant.ParticipantTurnHost.reaction_capability",
            lambda self: UNAVAILABLE_REACTION_CAPABILITY,
        ):
            results = [
                kit.run_scenario(name, kit.ReferenceIntegration(kit.SCENARIOS[name].posting))
                for name in ("mhm", "final-mhm", "post", "final-deliver")
            ]
        self.assertEqual(
            {"mhm": "fail", "final-mhm": "fail", "post": "pass", "final-deliver": "pass"},
            {r["scenario"]: r["status"] for r in results},
        )

    def test_an_integration_that_cannot_offer_privileged_actions_fails_the_outcome_scenario(self):
        class NoPrivileged(kit.ReferenceIntegration):
            def participant(self, *, profile, guard, agent):
                return super().participant(profile=profile, guard=guard, agent=agent)

        result = kit.run_scenario("outcome", NoPrivileged("tools"))
        self.assertEqual("fail", result["status"])
        self.assertIn("cannot offer privileged actions", result["failures"][0])
        self.assertEqual("pass", kit.run_scenario("post", NoPrivileged("tools"))["status"])

    def test_the_scripted_agent_plays_one_turn_per_start_and_counts_the_rest(self):
        surfaces = []

        class Surface:
            def bind(self, turn_id):
                surfaces.append(turn_id)
                return True

        agent = kit.ScriptedAgent([("bind",)], lambda text: text, later=[[("bind",)]])
        first, second = object(), object()
        for key in (first, first, second, second):
            agent.play_once(key, Surface)
        self.assertTrue(agent.done.wait(5))
        agent.play(Surface())
        # Each turn plays in its own thread, so the order may vary.
        self.assertEqual(["turn-1", "turn-2"], sorted(surfaces))
        self.assertEqual(1, agent.unexpected)

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
