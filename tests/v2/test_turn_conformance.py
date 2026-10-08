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
                # Each silent form keeps its reason.
                "final-silence-forms",
            },
            failed,
        )

    def test_the_final_answer_safety_scenarios_catch_their_rules_turned_off(self):
        safety = ("final-not-own-words", "final-no-answer", "final-silence-forms")

        def failed():
            reference = kit.ReferenceIntegration("final-answer")
            return {
                name: result["failures"]
                for name in (*safety, "final-deliver", "final-silence", "final-thinking")
                if (result := kit.run_scenario(name, reference))["status"] == "fail"
            }

        self.assertEqual({}, failed())
        # Any answer counts as the model's: the harness's text is posted and remembered.
        with mock.patch.object(turn.Turn, "_not_the_models", lambda self, text: None):
            self.assertEqual({"final-not-own-words", "final-no-answer"}, set(failed()))
        # The harness's text is read as the agent's silence instead of a failure.
        decide = turn.Turn.decide

        def as_silence(self, answer):
            decision = decide(self, answer)
            self.unattributed = None
            return decision

        with mock.patch.object(turn.Turn, "decide", as_silence):
            failures = failed()
        self.assertEqual({"final-not-own-words", "final-no-answer"}, set(failures))
        self.assertIn("a move it never made", " ".join(failures["final-no-answer"]))
        # Formatting around the marker is not stripped.
        plain = lambda text: " ".join(text.split()).casefold()  # noqa: E731
        with mock.patch.object(turn, "_silence_form", plain), mock.patch.object(turn, "_silence_lead", plain):
            failures = failed()
        self.assertEqual({"final-silence-forms"}, set(failures))
        self.assertIn("'**[SILENT]**': expected silence", failures["final-silence-forms"][0])
        # The harness's other silent answer is listed but not read as silence.
        silent_forms = turn._silent_forms

        def only_the_marker(silence_marker, also_silent, model_text):
            return silent_forms(silence_marker, (), model_text)

        with mock.patch.object(turn, "_silent_forms", only_the_marker):
            failures = failed()
        self.assertEqual({"final-silence-forms"}, set(failures))
        self.assertTrue(all(failure.startswith("'NO_REPLY'") for failure in failures["final-silence-forms"]))
        # The harness posts its own text although the library said silent.
        stand_in = kit._DirectSurface.stand_in

        def posts_anyway(self, turn_id, text, wrote):
            stand_in(self, turn_id, text, wrote)
            return "deliver", text

        with mock.patch.object(kit._DirectSurface, "stand_in", posts_anyway):
            failures = failed()
        self.assertEqual({"final-not-own-words", "final-no-answer"}, set(failures))
        self.assertIn("the harness posted ('deliver', '(empty)')", failures["final-no-answer"])

    def test_the_other_silence_word_is_the_integrations_own(self):
        # A harness with no silent answer besides its marker lists none: that
        # play is skipped, and no word the harness lacks is required.
        init = turn.TurnParticipant.__init__

        def without_also_silent(self, **kwargs):
            init(self, **{**kwargs, "also_silent": ()})

        with mock.patch.object(turn.TurnParticipant, "__init__", without_also_silent):
            result = kit.run_scenario("final-silence-forms", kit.ReferenceIntegration("final-answer"))
        self.assertEqual(("pass", [kit.ALSO_SILENT]), (result["status"], result.get("skipped")))

        # A harness with another word is tested on its own word.
        def other_word(self, **kwargs):
            init(self, **{**kwargs, "also_silent": ("NOTHING_TO_ADD",)})

        with mock.patch.object(turn.TurnParticipant, "__init__", other_word):
            self.assertEqual("pass", kit.run_scenario(
                "final-silence-forms", kit.ReferenceIntegration("final-answer"))["status"])
            with mock.patch.object(turn, "_silent_forms", lambda marker, also, model_text: frozenset({"[silent]"})):
                result = kit.run_scenario("final-silence-forms", kit.ReferenceIntegration("final-answer"))
        self.assertEqual("fail", result["status"])
        self.assertTrue(all(failure.startswith("'NOTHING_TO_ADD'") for failure in result["failures"]))

    def test_the_stand_in_scenarios_need_a_harness_that_puts_its_own_text_in(self):
        class NeverStandsIn(kit.ReferenceIntegration):
            def __init__(self):
                super().__init__("final-answer")
                self.harness_text = False

        for name in ("final-not-own-words", "final-no-answer"):
            with self.subTest(name):
                self.assertEqual("n/a", kit.run_scenario(name, NeverStandsIn())["status"])
                self.assertEqual("n/a", kit.run_scenario(name, ClaudeCodeKitIntegration())["status"])
        self.assertEqual("pass", kit.run_scenario("final-silence-forms", NeverStandsIn())["status"])

    def test_the_launch_secret_scenario_needs_a_launch_secret_and_catches_a_leak(self):
        # The reference turn has no launch secret: the scenario does not apply.
        self.assertEqual("n/a", kit.run_scenario("launch-secret", kit.ReferenceIntegration("tools"))["status"])
        self.assertEqual("pass", kit.run_scenario("launch-secret", ClaudeCodeKitIntegration())["status"])
        # A server that does not withhold its secret lets the agent post it.
        with mock.patch.object(turn.TurnParticipant, "withhold", lambda self, values: None):
            result = kit.run_scenario("launch-secret", ClaudeCodeKitIntegration())
        self.assertEqual("fail", result["status"])
        self.assertIn("the launch secret was not refused", result["failures"][0])

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
