"""The turn conformance kit (#94 step 9d): its checks catch broken rules."""

from __future__ import annotations

import unittest
from unittest import mock

from nunchi import pipeline, turn, turn_conformance as kit
from nunchi.integrations import claude_code_conformance
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
                # Each silent form keeps its reason, and so does each leak scenario.
                "final-silence-forms", "final-leak", "final-leak-markup", "final-trailing-silence",
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
        # A row per scenario, then the leak count.
        self.assertEqual(len(kit.SCENARIOS) + 3, len(table))
        self.assertIn("| final-deliver: ", table[2 + list(kit.SCENARIOS).index("final-deliver")])
        self.assertTrue(table[2 + list(kit.SCENARIOS).index("final-deliver")].endswith("| n/a |"))
        self.assertTrue(table[-1].startswith("| **leak count**"), table[-1])
        self.assertTrue(table[-1].endswith("| 0 |"), table[-1])

    def test_the_command_runs_the_reference_by_default(self):
        with mock.patch("builtins.print"):
            self.assertEqual(0, kit.main([]))


LEAK_SCENARIOS = ("leak", "leak-markup", "final-leak", "final-leak-markup", "final-trailing-silence")
FAILURE_SCENARIOS = ("harness-failure", "final-harness-failure")


def _reference(name):
    return kit.ReferenceIntegration(kit.SCENARIOS[name].posting)


class _ShowsMore(kit.ReferenceIntegration):
    """A harness that shows the room more than the library committed: typing, and a notice."""

    def __init__(self, posting, *, gaps=()):
        super().__init__(posting)
        self.known_gaps = tuple(gaps)

    def visible(self):
        return [*super().visible(), {"kind": "typing"}, {"kind": "message", "text": "⚠️ Something went wrong."}]


class LeakCountTests(unittest.TestCase):
    def test_the_leak_scenarios_pass_with_nothing_leaked(self):
        for name in (*LEAK_SCENARIOS, *FAILURE_SCENARIOS):
            with self.subTest(name):
                result = kit.run_scenario(name, _reference(name))
                self.assertEqual(("pass", 0, []), (result["status"], result["leak_count"], result["failures"]))

    def test_the_leak_scenarios_fail_when_the_library_posts_what_is_private(self):
        def nothing_private(text):
            return (text or "").strip(), ""

        with mock.patch.object(turn, "split_private", nothing_private):
            results = {name: kit.run_scenario(name, _reference(name)) for name in LEAK_SCENARIOS}
        failed = {name for name, result in results.items() if result["status"] == "fail"}
        # The marker after the agent's words is silence without split_private.
        self.assertEqual({"leak", "leak-markup", "final-leak", "final-leak-markup"}, failed)
        # The leak count names the machinery the library committed.
        leaked = " ".join(results["leak"]["failures"])
        self.assertIn("a committed post names Nunchi's machinery", leaked)
        self.assertIn("<think>", leaked)
        self.assertIn("<nunchi_wake", leaked)
        self.assertEqual(1, results["leak"]["leak_count"])

    def test_the_trailing_marker_scenario_fails_when_it_is_not_silence(self):
        with mock.patch.object(turn, "_ends_with_silence", lambda text, taught: False):
            result = kit.run_scenario("final-trailing-silence", _reference("final-trailing-silence"))
        self.assertEqual("fail", result["status"])
        self.assertIn("expected silence", result["failures"][0])
        # The marker it posted is machinery, and the leak count says so.
        self.assertTrue(any("[SILENT]" in failure for failure in result["failures"]), result["failures"])

    def test_the_detector_is_what_counts_committed_machinery(self):
        def nothing_private(text):
            return (text or "").strip(), ""

        with mock.patch.object(turn, "split_private", nothing_private), mock.patch.object(
            kit, "machinery_in", lambda text, ids=(): []
        ):
            result = kit.run_scenario("leak", _reference("leak"))
        # The scenario's own check still fails, but nothing counts the machinery.
        self.assertEqual("fail", result["status"])
        self.assertEqual(0, result["leak_count"])
        self.assertNotIn("machinery", " ".join(result["failures"]))
        # The turn's request ids are internal: a post that names one is a leak.
        played = kit.Played(
            dispatched=[{"kind": "message", "text": "See request req-1234."}], shown=[], ids={"req-1234"}
        )
        self.assertEqual(
            (["a committed post names Nunchi's machinery ['req-1234']: 'See request req-1234.'"], []),
            kit.leaks("post", played),
        )

    def test_whatever_else_the_harness_shows_is_a_leak(self):
        for name in ("post", "final-deliver", "harness-failure", "final-harness-failure", "final-leak"):
            with self.subTest(name):
                result = kit.run_scenario(name, _ShowsMore(kit.SCENARIOS[name].posting))
                self.assertEqual("fail", result["status"])
                self.assertEqual(2, result["leak_count"])
                self.assertIn("the room got typing, which the library never committed", result["failures"])
                self.assertIn(
                    "the room got a message: '⚠️ Something went wrong.', which the library never committed",
                    result["failures"],
                )

    def test_a_declared_known_gap_reads_gap_never_pass(self):
        typing = kit.KnownGap("the harness types on every run (documented)", scenarios=("post",), kind="typing")
        notice = kit.KnownGap(
            "the harness's notice (documented)", scenarios=("post",), kind="message", text="went wrong"
        )
        result = kit.run_scenario("post", _ShowsMore("tools", gaps=(typing, notice)))
        self.assertEqual(("gap", 2, []), (result["status"], result["leak_count"], result["failures"]))
        self.assertEqual(
            ["typing: the harness types on every run (documented)",
             "a message: '⚠️ Something went wrong.': the harness's notice (documented)"],
            result["gaps"],
        )
        table = kit.parity_table([result])
        self.assertIn("| post: one post goes to the room, and the tool call says so | gap |", table)
        self.assertTrue(table.endswith("| 2 (2 known gaps) |"), table)
        with mock.patch("builtins.print"):
            self.assertEqual(0, kit.main(["--integration", f"{__name__}:_gapped"]))
        # A gap covers only what it names, where it names: anything else still fails.
        result = kit.run_scenario("post", _ShowsMore("tools", gaps=(typing,)))
        self.assertEqual(("fail", 2), (result["status"], result["leak_count"]))
        self.assertEqual(["typing: the harness types on every run (documented)"], result["gaps"])
        result = kit.run_scenario("one-action", _ShowsMore("tools", gaps=(typing, notice)))
        self.assertEqual("fail", result["status"])
        # A harness that shows only what it committed passes, its gaps unused.
        self.assertEqual("pass", kit.run_scenario("post", kit.ReferenceIntegration("tools"))["status"])

    def test_a_harness_that_posts_what_it_was_told_twice_leaks_the_second(self):
        class PostsTwice(kit.ReferenceIntegration):
            def visible(self):
                return [*super().visible(), *super().visible()]

        result = kit.run_scenario("final-deliver", PostsTwice("final-answer"))
        self.assertEqual(("fail", 1), (result["status"], result["leak_count"]))
        self.assertIn("the room got a message: 'On it.', which the library never committed", result["failures"])

    def test_without_visible_the_leak_count_is_not_applicable(self):
        class Unseen(kit.ReferenceIntegration):
            visible = None

        results = [kit.run_scenario(name, Unseen("tools")) for name in ("post", "leak")]
        self.assertEqual([("pass", "n/a"), ("pass", "n/a")], [(r["status"], r["leak_count"]) for r in results])
        self.assertTrue(kit.parity_table(results).endswith("| n/a |"))

    def test_the_failure_scenarios_need_a_surface_that_can_fail_the_model(self):
        class NoFailure(kit.ReferenceIntegration):
            model_failure = False

        for name in FAILURE_SCENARIOS:
            with self.subTest(name):
                self.assertEqual("n/a", kit.run_scenario(name, NoFailure(kit.SCENARIOS[name].posting))["status"])

    def test_the_failure_scenarios_catch_a_failure_read_as_silence_or_left_open(self):
        # The harness reports the failed run as a good end: the turn is silence.
        def as_success(self, turn_id):
            self.participant.end_turn(turn_id=None, ok=True, detail="scripted end", note="API Error: 400")

        with mock.patch.object(kit._DirectSurface, "fail", as_success):
            results = {name: kit.run_scenario(name, _reference(name)) for name in FAILURE_SCENARIOS}
        for name, result in results.items():
            self.assertEqual("fail", result["status"], name)
            self.assertIn("must end as a failure", result["failures"][0])
        # The harness never reports the end: the turn waits for the library's deadline.
        with mock.patch.object(kit._DirectSurface, "fail", lambda self, turn_id: None):
            result = kit.run_scenario("harness-failure", _reference("harness-failure"), timeout=2)
        self.assertEqual("fail", result["status"])
        self.assertIn("deadline", " ".join(result["failures"]))
        # Claude Code: a gate that reads only the result's subtype takes the
        # API error for the agent's last words.
        def subtype_only(message):
            return {"ok": message.get("subtype") == "success", "detail": "success", "note": message.get("result")}

        with mock.patch.object(claude_code_conformance, "turn_ending", subtype_only):
            result = kit.run_scenario("harness-failure", ClaudeCodeKitIntegration())
        self.assertEqual("fail", result["status"])
        self.assertIn("must end as a failure", " ".join(result["failures"]))
        self.assertEqual("pass", kit.run_scenario("harness-failure", ClaudeCodeKitIntegration())["status"])


def _gapped():
    typing = kit.KnownGap("documented", scenarios=tuple(kit.SCENARIOS), kind="typing")
    notice = kit.KnownGap("documented", scenarios=tuple(kit.SCENARIOS), kind="message", text="went wrong")
    return [_ShowsMore("tools", gaps=(typing, notice))]


if __name__ == "__main__":
    unittest.main()
