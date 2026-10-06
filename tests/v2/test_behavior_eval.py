"""The behavioral evaluation harness works offline (#86).

These tests prove plumbing only: scenes load, moments reach the production
attention path, grades follow the rules in `evals/behavior/score.py`, and a
run never writes its key. Whether models read the room is measured by live
runs, not here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from evals.behavior import litmus, run
from evals.behavior.scene import (
    SceneError,
    load_participants,
    load_scenes,
    parse_offset,
    parse_scene,
)
from evals.behavior.score import cell, grade, visible_result
from nunchi.attention_questions import answers_leaning
from nunchi.observation import ObservationLimits


PARTICIPANTS = load_participants()


def judgment(disposition, *, evidence=(), suppress_margin=True, reading=None):
    """Typed answers for one disposition; the model's note cites ``evidence``."""

    result = answers_leaning(disposition, close=not suppress_margin)
    if evidence:
        result["notes"] = [
            {"note": reading or f"fixture {disposition}", "evidence_event_ids": list(evidence)}
        ]
    return result


class FixedModel:
    """Returns one judgment and keeps every projection it saw."""

    name = "participant-attention"
    provider = "fixture"

    def __init__(self, disposition, *, evidence=(), model_id="fixture/model", reading=None):
        self.disposition = disposition
        self.evidence = evidence
        self.model_id = model_id
        self.reading = reading
        self.projections = []

    def judge(self, *, instructions, projection, timeout_seconds):
        self.projections.append(projection)
        evidence = [item for item in self.evidence if item in {event["id"] for event in projection["events"]}]
        return judgment(
            self.disposition,
            evidence=evidence or [projection["trigger_event_id"]],
            reading=self.reading,
        )


def scene_by_id(scene_id):
    return next(scene for scene in load_scenes() if scene.id == scene_id)


def minimal(**changes):
    raw = {
        "id": "minimal",
        "title": "Minimal",
        "source": "test",
        "review": "draft",
        "platform": "discord",
        "participants": ["vigil"],
        "actors": {"zoe": {"display_name": "Zoe", "kind": "human"}},
        "events": [
            {"id": "m1", "author": "zoe", "at": "-1m", "text": "Hi"},
            {"id": "m2", "author": "zoe", "at": "0s", "text": "Vigil?", "mentions": ["vigil"]},
        ],
        "moments": [{"event": "m2", "step1": "pass", "fitting": ["speak"]}],
    }
    raw.update(changes)
    return raw


class SceneFileTests(unittest.TestCase):
    def test_every_committed_scene_loads(self):
        scenes = load_scenes()
        ids = {scene.id for scene in scenes}
        for expected in (
            "story-across-messages",
            "answered-by-someone-else",
            "addressee-first",
            "two-agents-one-question",
            "quiet-for-hours",
            "did-you-see",
            "bot-status-report",
            "mention-in-busy-room",
        ):
            self.assertIn(expected, ids)
        self.assertEqual(57, sum(1 for scene in scenes if scene.id.startswith("litmus-")))

    def test_every_fact_to_notice_is_inside_the_observation_window(self):
        # A fact older than the window never reaches attention or the agent,
        # so a moment that asks for it measures nothing.
        limit = ObservationLimits().snapshot_age_seconds
        for scene in load_scenes():
            offsets = {event["id"]: parse_offset(event["at"]) for event in scene.events if event.get("at")}
            for moment in scene.moments:
                if moment.event not in offsets:
                    continue
                for fact in moment.notice:
                    for event_id in fact.get("events", ()):
                        if event_id in offsets:
                            with self.subTest(scene=scene.id, event=event_id):
                                self.assertLess(offsets[event_id] - offsets[moment.event], limit)

    def test_offsets(self):
        self.assertEqual(0, parse_offset("0s"))
        self.assertEqual(90, parse_offset("-90s"))
        self.assertEqual(7 * 3600, parse_offset("-7h"))
        for bad in ("5m", "-5", "soon", "-1w"):
            with self.subTest(bad=bad), self.assertRaises(SceneError):
                parse_offset(bad)

    def test_malformed_scenes_are_rejected(self):
        cases = {
            "unknown move": {"moments": [{"event": "m2", "step1": "pass", "fitting": ["reply"]}]},
            "fits and misses": {
                "moments": [
                    {
                        "event": "m2",
                        "step1": "pass",
                        "fitting": ["speak"],
                        "misses": [{"move": "speak", "why": "x"}],
                    }
                ]
            },
            "event and pause": {
                "moments": [
                    {"event": "m2", "pause_after": "m2", "pause": "5m", "step1": "pass", "fitting": ["speak"]}
                ]
            },
            "pointer to nothing": {
                "moments": [
                    {
                        "event": "m2",
                        "step1": "pass",
                        "fitting": ["speak"],
                        "notice": [{"fact": "x", "events": ["m9"]}],
                    }
                ]
            },
            "reply forward": {
                "events": [
                    {"id": "m1", "author": "zoe", "text": "Hi", "reply_to": "m2"},
                    {"id": "m2", "author": "zoe", "text": "Vigil?"},
                ]
            },
            "unknown author": {
                "events": [{"id": "m2", "author": "nobody", "text": "Hi"}],
            },
            "together alone": {"together": ["not-all-quiet"]},
        }
        for label, changes in cases.items():
            with self.subTest(label), self.assertRaises(SceneError):
                parse_scene(minimal(**changes), participants=PARTICIPANTS)


class GradeTests(unittest.TestCase):
    def setUp(self):
        self.story_end = scene_by_id("story-across-messages").moments[2]
        self.status = scene_by_id("bot-status-report").moments[0]

    def test_quiet_where_a_turn_is_owed_is_a_miss_and_an_over_suppress(self):
        self.assertEqual(
            {"visible": "miss", "step1": "over-suppress"},
            grade(self.story_end, "stay_quiet"),
        )

    def test_woken_is_the_agents_call(self):
        self.assertEqual({"visible": "agent-decides", "step1": "ok"}, grade(self.story_end, "woken"))
        self.assertEqual({"visible": "agent-decides", "step1": "over-wake"}, grade(self.status, "woken"))

    def test_mhm_at_a_status_line_is_a_miss(self):
        self.assertEqual({"visible": "miss", "step1": "over-wake"}, grade(self.status, "mhm"))

    def test_quiet_at_a_status_line_fits(self):
        self.assertEqual({"visible": "fits", "step1": "ok"}, grade(self.status, "stay_quiet"))

    def test_unlisted_moves_are_flagged_not_failed(self):
        answered = scene_by_id("addressee-first").moments[0]
        self.assertEqual("fits", grade(answered, "stay_quiet")["visible"])
        self.assertEqual("unlisted", grade(answered, "mhm")["visible"])

    def test_visible_result(self):
        ok = {"status": "ok"}
        self.assertEqual("stay_quiet", visible_result({**ok, "effective_disposition": "SUPPRESS"}))
        self.assertEqual("mhm", visible_result({**ok, "effective_disposition": "ACK"}))
        self.assertEqual("woken", visible_result({**ok, "effective_disposition": "DEFER"}))
        self.assertEqual("woken", visible_result({"status": "error"}))
        self.assertEqual("stay_quiet", visible_result({"status": "error", "wake_action": "NO_WAKE"}))
        self.assertEqual("stay_quiet", visible_result(None, transport_self=True))
        self.assertEqual("unsupported", visible_result(None))

    def test_cell(self):
        records = [
            {"result": "stay_quiet", "grade": {"visible": "miss"}},
            {"result": "woken", "grade": {"visible": "agent-decides"}, "provider_error": True},
            {"result": "woken", "grade": {"visible": "agent-decides"}},
        ]
        self.assertEqual("QEW!", cell(records))


class JudgeMomentTests(unittest.TestCase):
    def judge(self, scene_id, moment, disposition, *, ack="agent", **kwargs):
        model = FixedModel(disposition, **kwargs)
        scene = scene_by_id(scene_id)
        job = run.Job(scene, moment, scene.participants[0], "fixture/model", 0)
        record = run.judge_moment(job, lambda _: model, timeout_seconds=5, ack=ack)
        return record, model

    def test_suppress_at_the_end_of_the_story_is_a_miss(self):
        record, model = self.judge("story-across-messages", 2, "SUPPRESS")
        self.assertEqual("stay_quiet", record["result"])
        self.assertEqual("miss", record["grade"]["visible"])
        self.assertEqual(["s1", "s2", "s3", "s4", "s5"], [event["id"] for event in model.projections[0]["events"]])

    def test_a_moment_sees_only_what_had_happened(self):
        _, model = self.judge("story-across-messages", 0, "ACK")
        self.assertEqual(["s1", "s2"], [event["id"] for event in model.projections[0]["events"]])

    def test_nunchis_own_ack_goes_through_the_capability_and_counts_as_mhm(self):
        record, _ = self.judge("story-across-messages", 0, "ACK", ack="nunchi")
        self.assertEqual(("mhm", "nunchi"), (record["result"], record["by"]))
        self.assertEqual("ACK", record["decision"]["effective_disposition"])
        self.assertEqual("fits", record["grade"]["visible"])

    def test_by_default_an_ack_is_the_agents_turn(self):
        record, _ = self.judge("story-across-messages", 0, "ACK")
        self.assertEqual(("woken", "DEFER"), (record["result"], record["decision"]["effective_disposition"]))
        self.assertEqual("policy-defer", record["decision"]["routing_audit"]["valve"])

    def test_late_judgment_sees_the_answer(self):
        _, model = self.judge("answered-by-someone-else", 0, "WAKE")
        projection = model.projections[0]
        self.assertEqual("q1", projection["trigger_event_id"])
        self.assertEqual(["q1", "a1"], [event["id"] for event in projection["events"]])

    def test_scene_ends_now_and_keeps_its_pauses(self):
        _, model = self.judge("quiet-for-hours", 0, "WAKE")
        times = {
            event["id"]: datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
            for event in model.projections[0]["events"]
        }
        self.assertLess(abs(datetime.now(timezone.utc) - times["m1"]), timedelta(minutes=1))
        self.assertEqual(timedelta(hours=7), times["m1"] - times["n3"])

    def test_pause_moments_are_not_supported_today(self):
        record, model = self.judge("addressee-first", 1, "WAKE")
        self.assertEqual("unsupported", record["result"])
        self.assertEqual([], model.projections)

    def test_own_event_never_reaches_the_model(self):
        record, model = self.judge("litmus-a-self-echo-alias-author", 0, "WAKE")
        self.assertEqual("stay_quiet", record["result"])
        self.assertEqual({"visible": "fits", "step1": "ok"}, record["grade"])
        self.assertEqual([], model.projections)

    def test_cited_facts_follow_the_models_evidence(self):
        # The judgment always cites the judged message (m1, in the first
        # fact); the model's note cites n2 (the second).
        record, _ = self.judge("quiet-for-hours", 0, "WAKE", evidence=("n2",))
        self.assertEqual([True, True], record["cited"])
        self.assertEqual(["m1", "n2"], record["decision"]["evidence_event_ids"])

    def test_provider_failure_wakes_and_is_recorded(self):
        class Broken(FixedModel):
            def judge(self, **kwargs):
                raise RuntimeError("boom")

        scene = scene_by_id("bot-status-report")
        job = run.Job(scene, 0, "vigil", "broken/model", 0)
        record = run.judge_moment(job, lambda _: Broken("WAKE"), timeout_seconds=5)
        self.assertTrue(record["provider_error"])
        self.assertEqual("woken", record["result"])
        self.assertIn("boom", record["error"])


class FakeAgent:
    """Plays the woken agent's turn with a fixed act and keeps what it was given."""

    def __init__(self, act):
        self.act = act
        self.turns = []

    def run_protocol(self, *, wake, opportunity, expand, cancel):
        self.turns.append((wake, opportunity))
        return self.act(wake)


def speaks(wake):
    return {"kind": "message", "origin_event_id": wake["trigger_event_id"], "text": "Here's what I'd do."}


def stays_silent(wake):
    return None


def reacts(wake):
    return {
        "kind": "reaction",
        "origin_event_id": wake["trigger_event_id"],
        "target_event_id": wake["trigger_event_id"],
        "reaction": "👍",
        "operation": "add",
    }


def fails(wake):
    raise RuntimeError("agent provider HTTP 429")


class AgentTurnTests(unittest.TestCase):
    """A model plays the woken agent through Nunchi's own host and transport."""

    def judge(self, scene_id, moment, disposition, act, *, reading=None, agent=None, **kwargs):
        agent = agent or FakeAgent(act)
        scene = scene_by_id(scene_id)
        job = run.Job(scene, moment, scene.participants[0], "fixture/model", 0)
        record = run.judge_moment(
            job,
            lambda _: FixedModel(disposition, reading=reading),
            timeout_seconds=5,
            agent_factory=lambda profile: agent,
            **kwargs,
        )
        return record, agent

    def test_speaking_at_the_end_of_the_story_fits(self):
        record, agent = self.judge("story-across-messages", 2, "WAKE", speaks)
        self.assertEqual(("speak", "agent"), (record["result"], record["by"]))
        self.assertEqual({"visible": "fits", "step1": "ok"}, record["grade"])
        wake, opportunity = agent.turns[0]
        self.assertEqual("s5", wake["trigger_event_id"])
        self.assertEqual(["message", "reply", "reaction"], opportunity["permissions"]["ordinary_actions"])

    def test_speaking_mid_story_is_a_miss_and_silence_fits(self):
        spoke, _ = self.judge("story-across-messages", 0, "WAKE", speaks)
        self.assertEqual("miss", spoke["grade"]["visible"])
        quiet, _ = self.judge("story-across-messages", 0, "WAKE", stays_silent)
        self.assertEqual(("stay_quiet", "agent"), (quiet["result"], quiet["by"]))
        self.assertEqual({"visible": "fits", "step1": "ok"}, quiet["grade"])

    def test_the_agents_own_reaction_is_its_mhm(self):
        record, _ = self.judge("story-across-messages", 0, "WAKE", reacts)
        self.assertEqual(("mhm", "agent"), (record["result"], record["by"]))
        self.assertEqual("fits", record["grade"]["visible"])

    def test_nunchis_own_ack_never_reaches_the_agent(self):
        record, agent = self.judge("story-across-messages", 0, "ACK", speaks, ack="nunchi")
        self.assertEqual(("mhm", "nunchi"), (record["result"], record["by"]))
        self.assertEqual([], agent.turns)
        self.assertNotIn("agent", record)

    def test_suppression_never_reaches_the_agent(self):
        record, agent = self.judge("story-across-messages", 2, "SUPPRESS", speaks)
        self.assertEqual(("stay_quiet", "attention"), (record["result"], record["by"]))
        self.assertEqual({"visible": "miss", "step1": "over-suppress"}, record["grade"])
        self.assertEqual([], agent.turns)

    def test_a_failed_agent_turn_is_an_error(self):
        record, _ = self.judge("story-across-messages", 2, "WAKE", fails)
        self.assertTrue(record["provider_error"])
        self.assertEqual("woken", record["result"])
        self.assertIn("HTTP 429", record["agent"]["error"])

    def test_waiting_is_satisfied_by_staying_quiet(self):
        record, _ = self.judge("addressee-first", 0, "WAKE", stays_silent)
        self.assertEqual("fits", record["grade"]["visible"])

    def test_the_record_says_how_the_agent_got_its_turn(self):
        record, _ = self.judge("story-across-messages", 2, "WAKE", speaks, reading="Zoe has finished her story")
        # The model's note, then the kinds of response that could fit.
        self.assertEqual({"source": "WAKE", "reading_items": 2}, record["agent"]["attention"])
        self.assertEqual("WAKE", run.turn_source(record))

    def test_a_paired_turn_is_played_again_without_the_reading_and_never_sent(self):
        def speaks_only_with_a_reading(wake):
            return speaks(wake) if wake["attention"].get("advice") else None

        record, agent = self.judge(
            "story-across-messages",
            2,
            "WAKE",
            speaks_only_with_a_reading,
            reading="Zoe has finished her story and asked for the next step",
            paired=True,
        )
        self.assertEqual(("speak", "agent", "fits"), (record["result"], record["by"], record["grade"]["visible"]))
        self.assertEqual(2, len(agent.turns))
        with_reading, without_reading = (wake for wake, _ in agent.turns)
        self.assertIn("advice", with_reading["attention"])
        self.assertEqual({"source": "WAKE"}, without_reading["attention"])
        self.assertEqual(with_reading["events"], without_reading["events"])
        unread = record["agent"]["without_reading"]
        self.assertEqual(("stay_quiet", "miss"), (unread["move"], unread["grade"]))
        self.assertIsNone(unread["action"])

    def test_a_turn_without_a_reading_is_not_paired(self):
        record, agent = self.judge("story-across-messages", 2, "WAKE", speaks, paired=True, reading_items=0)
        self.assertEqual(1, len(agent.turns))
        self.assertNotIn("without_reading", record["agent"])

    def test_a_failed_paired_turn_never_changes_the_real_one(self):
        class FailsSecondTime(FakeAgent):
            def run_protocol(self, *, wake, opportunity, expand, cancel):
                if self.turns:
                    raise RuntimeError("agent provider HTTP 429")
                return super().run_protocol(wake=wake, opportunity=opportunity, expand=expand, cancel=cancel)

        record, _ = self.judge(
            "story-across-messages", 2, "WAKE", speaks, reading="finished", paired=True, agent=FailsSecondTime(speaks)
        )
        self.assertEqual(("speak", "agent"), (record["result"], record["by"]))
        self.assertFalse(record["provider_error"])
        self.assertIn("HTTP 429", record["agent"]["without_reading"]["error"])

    def test_a_reply_the_protocol_rejects_is_kept(self):
        reply = '{"kind": "silence"}\n{"kind": "silence"}'
        payload = json.dumps({"choices": [{"message": {"content": reply}}]}).encode()

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        scene = scene_by_id("story-across-messages")
        job = run.Job(scene, 2, scene.participants[0], "fixture/model", 0)
        agents = run.openai_compatible_agent_factory(api_key="k", base_url=run.DEFAULT_BASE_URL, model="fixture/agent")
        with mock.patch("urllib.request.urlopen", lambda request, timeout: Response(payload)):
            record = run.judge_moment(
                job, lambda _: FixedModel("WAKE"), timeout_seconds=5, agent_factory=agents
            )
        self.assertTrue(record["provider_error"])
        self.assertIn("not valid JSON", record["agent"]["error"])
        self.assertEqual(reply, record["agent"]["raw_reply"])

    def test_the_agent_sends_its_own_mhm_when_nunchi_does_not(self):
        record, agent = self.judge("story-across-messages", 0, "ACK", reacts, ack="agent")
        self.assertEqual(("mhm", "agent", "fits"), (record["result"], record["by"], record["grade"]["visible"]))
        self.assertEqual(1, len(agent.turns))
        self.assertEqual("DEFER", record["agent"]["attention"]["source"])
        self.assertEqual("ACK widened to DEFER (policy-defer)", run.turn_source(record))

    def test_a_message_that_arrives_mid_turn_is_seen_by_looking_again(self):
        class LooksAgain(FakeAgent):
            def run_protocol(self, *, wake, opportunity, expand, cancel):
                self.turns.append((wake, opportunity))
                page = expand(direction="new", max_events=12, max_bytes=16_384)
                self.shown = [event["id"] for event in page["events"]]
                return None if self.shown else speaks(wake)

        agent = LooksAgain(None)
        record, _ = self.judge("never-mind-while-composing", 0, "WAKE", None, agent=agent)
        wake, _ = agent.turns[0]
        self.assertNotIn("n1", [event["id"] for event in wake["events"]])
        self.assertEqual(["n1"], agent.shown)
        self.assertEqual(1, record["agent"]["looked_again"])
        self.assertEqual(("stay_quiet", "fits"), (record["result"], record["grade"]["visible"]))

    def test_the_paired_play_gets_its_own_view_of_the_turn(self):
        # The second play must see what the first play saw, including the
        # message that arrived mid-turn, or the pair measures the view, not
        # the reading.
        class ReadsAll(FakeAgent):
            def run_protocol(self, *, wake, opportunity, expand, cancel):
                self.turns.append((wake, opportunity))
                history = expand(direction="before", max_events=12, max_bytes=16_384)
                new = expand(direction="new", max_events=12, max_bytes=16_384)
                self.shown.append(
                    ([event["id"] for event in history["events"]], [event["id"] for event in new["events"]])
                )
                return None if new["events"] else speaks(wake)

        agent = ReadsAll(None)
        agent.shown = []
        record, _ = self.judge(
            "never-mind-while-composing", 0, "WAKE", None, reading="Zoe asked Vigil directly", paired=True, agent=agent
        )
        self.assertEqual(2, len(agent.turns))
        self.assertEqual(agent.shown[0], agent.shown[1])
        self.assertEqual(["n1"], agent.shown[1][1])
        self.assertEqual(("stay_quiet", "fits"), (record["agent"]["without_reading"]["move"], record["agent"]["without_reading"]["grade"]))

    def test_context_requests_are_recorded(self):
        class Looks(FakeAgent):
            def run_protocol(self, *, wake, opportunity, expand, cancel):
                try:
                    expand(direction="before", max_events=5, max_bytes=4096)
                except Exception:
                    pass
                return None

        record, _ = self.judge("story-across-messages", 2, "WAKE", None, agent=Looks(None))
        (entry,) = record["agent"]["expansions"]
        self.assertEqual("with reading", entry["arm"])
        self.assertEqual("before", entry["request"]["direction"])
        # Today a short room has nothing more to fetch, so the request fails;
        # either way the record keeps what the agent asked and what it got.
        self.assertTrue("error" in entry or "events" in entry)


class RunTests(unittest.TestCase):
    def test_collective_silence_is_reported(self):
        scene = scene_by_id("two-agents-one-question")
        records = [
            {"scene": scene.id, "moment": 0, "model": "m", "run": 0, "result": "stay_quiet"},
            {"scene": scene.id, "moment": 0, "model": "m", "run": 0, "result": "stay_quiet"},
            {"scene": scene.id, "moment": 0, "model": "m", "run": 1, "result": "stay_quiet"},
            {"scene": scene.id, "moment": 0, "model": "m", "run": 1, "result": "woken"},
        ]
        self.assertEqual(
            [{"scene": scene.id, "moment": 0, "model": "m", "run": 0, "kind": "collective silence"}],
            run.together_findings([scene], records),
        )

    def test_a_pile_on_is_reported(self):
        scene = scene_by_id("two-agents-one-question")
        records = [
            {"scene": scene.id, "moment": 0, "model": "m", "run": 0, "result": "speak"},
            {"scene": scene.id, "moment": 0, "model": "m", "run": 0, "result": "speak"},
            {"scene": scene.id, "moment": 0, "model": "m", "run": 1, "result": "speak"},
            {"scene": scene.id, "moment": 0, "model": "m", "run": 1, "result": "stay_quiet"},
        ]
        self.assertEqual(
            [{"scene": scene.id, "moment": 0, "model": "m", "run": 0, "kind": "pile-on"}],
            run.together_findings([scene], records),
        )

    def test_scene_selection(self):
        scenes = load_scenes()
        self.assertEqual(10, len(run.select_scenes(scenes, "behavior")))
        self.assertEqual(57, len(run.select_scenes(scenes, "litmus")))
        self.assertEqual(5, len(run.select_scenes(scenes, "tool-chrome")))
        self.assertEqual(["did-you-see"], [scene.id for scene in run.select_scenes(scenes, "did-you-see")])

    def test_a_run_writes_its_record_and_never_its_key(self):
        secret = "sk-or-test-" + "x" * 40
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ, {"NUNCHI_OPENROUTER": secret}
        ), mock.patch.object(
            run, "openai_compatible_factory", return_value=lambda model_id: FixedModel("SUPPRESS", model_id=model_id)
        ):
            with mock.patch("sys.stdout"):
                code = run.main(
                    [
                        "--models", "a/model,b/model",
                        "--runs", "2",
                        "--scenes", "bot-status-report,story-across-messages",
                        "--out", directory,
                    ]
                )
            files = {path.name: path.read_text(encoding="utf-8") for path in Path(directory).iterdir()}
        self.assertEqual(0, code)
        self.assertNotIn("## Provider errors", files["summary.md"])
        self.assertEqual({"results.jsonl", "run.json", "summary.md"}, set(files))
        for name, text in files.items():
            self.assertNotIn(secret, text, name)
        meta = json.loads(files["run.json"])
        self.assertEqual(["a/model", "b/model"], meta["models"])
        self.assertEqual("NUNCHI_OPENROUTER", meta["key_env"])
        self.assertEqual(16, meta["calls"])
        records = [json.loads(line) for line in files["results.jsonl"].splitlines()]
        self.assertEqual(16, len(records))
        self.assertIn("| `a/model` | 8 |", files["summary.md"])
        self.assertIn("story-across-messages", files["summary.md"])

    def test_provider_errors_fail_the_run_and_lead_the_summary(self):
        class Broken(FixedModel):
            def judge(self, **kwargs):
                raise RuntimeError("HTTP 402 insufficient credits")

        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ, {"NUNCHI_OPENROUTER": "k"}
        ), mock.patch.object(
            run, "openai_compatible_factory", return_value=lambda model_id: Broken("WAKE", model_id=model_id)
        ), mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            code = run.main(["--models", "a/model", "--runs", "1", "--scenes", "bot-status-report", "--out", directory])
            summary = (Path(directory) / "summary.md").read_text(encoding="utf-8")
        self.assertEqual(1, code)
        self.assertLess(summary.index("## Provider errors"), summary.index("## Per model"))
        self.assertIn("1 of 1 runs had a failed attention or agent call", summary)
        self.assertIn("HTTP 402 insufficient credits", summary)

    def test_a_rejected_reply_is_kept_with_its_reason(self):
        class OutOfRange(FixedModel):
            def judge(self, *, instructions, projection, timeout_seconds):
                reply = judgment("WAKE")
                reply["conversation"] = 1.5
                return reply

        scene = scene_by_id("bot-status-report")
        job = run.Job(scene, 0, "vigil", "bad/model", 0)
        record = run.judge_moment(job, lambda _: OutOfRange("WAKE"), timeout_seconds=5)
        self.assertTrue(record["provider_error"])
        self.assertEqual(1.5, record["raw_reply"]["conversation"])
        self.assertEqual("model answer conversation must be a probability within [0, 1]", record["invalid_reason"])
        summary = run.summarize(
            [scene], ["bad/model"], [record], [],
            {
                "started_at": "s", "finished_at": "f", "git_sha": "x", "git_dirty": False,
                "nunchi_version": "v", "runs": 1, "temperature": 0, "base_url": "u",
                "calls": 1, "provider_errors": 1, "command": "c",
            },
        )
        self.assertIn("invalid reply: model answer conversation must be a probability within [0, 1]", summary)

    def test_calls_to_one_model_are_capped(self):
        import threading
        import time as clock

        lock = threading.Lock()
        active = {}
        peak = {}

        class Slow(FixedModel):
            def judge(self, **kwargs):
                with lock:
                    active[self.model_id] = active.get(self.model_id, 0) + 1
                    peak[self.model_id] = max(peak.get(self.model_id, 0), active[self.model_id])
                clock.sleep(0.05)
                with lock:
                    active[self.model_id] -= 1
                return super().judge(**kwargs)

        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ, {"NUNCHI_OPENROUTER": "k"}
        ), mock.patch.object(
            run, "openai_compatible_factory", return_value=lambda model_id: Slow("WAKE", model_id=model_id)
        ), mock.patch("sys.stdout"):
            code = run.main([
                "--models", "a/model,b/model", "--runs", "3", "--scenes", "behavior",
                "--workers", "8", "--per-model", "2", "--out", directory,
            ])
            meta = json.loads((Path(directory) / "run.json").read_text())
        self.assertEqual(0, code)
        self.assertEqual(2, meta["per_model"])
        self.assertEqual({"a/model": 2, "b/model": 2}, peak)

    def test_a_paired_run_reports_the_reading_and_who_nods(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("sys.stdout"):
                code = run.main(
                    [
                        "--dry-run",
                        "--agent-model", "x",
                        "--paired",
                        "--ack", "agent",
                        "--scenes", "story-across-messages",
                        "--runs", "1",
                        "--out", directory,
                    ]
                )
            summary = (Path(directory) / "summary.md").read_text(encoding="utf-8")
            meta = json.loads((Path(directory) / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(0, code)
        self.assertEqual(("agent", True), (meta["ack"], meta["paired"]))
        self.assertIn("- Mhm: the agent's own", summary)
        self.assertIn("## What the agent saw", summary)
        self.assertIn("| WAKE | 3 | 1 / 1 | 2 / 2 | 3 / 3 | 0 |", summary)

    def test_the_reading_length_reaches_attention_and_the_record(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("sys.stdout"):
                code = run.main(
                    ["--dry-run", "--scenes", "story-across-messages", "--runs", "1",
                     "--reading-items", "1", "--reading-chars", "80", "--out", directory]
                )
            summary = (Path(directory) / "summary.md").read_text(encoding="utf-8")
            meta = json.loads((Path(directory) / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(0, code)
        self.assertEqual((1, 80), (meta["reading_items"], meta["reading_chars"]))
        self.assertIn("- Reading: up to 1 note of up to 80 characters", summary)
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            run.main(["--dry-run", "--reading-items", "5"])

    def test_pairing_needs_an_agent(self):
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            run.main(["--dry-run", "--paired"])

    def test_a_dry_run_can_simulate_the_agent(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("sys.stdout"):
            code = run.main([
                "--dry-run", "--runs", "1", "--scenes", "two-agents-one-question",
                "--agent-model", "any", "--out", directory,
            ])
            meta = json.loads((Path(directory) / "run.json").read_text())
            summary = (Path(directory) / "summary.md").read_text()
        self.assertEqual(0, code)
        self.assertEqual(run.DRY_RUN_AGENT, meta["agent_model"])
        self.assertIn("pile-on: two-agents-one-question", summary)

    def test_a_live_run_needs_the_key(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                run.main(["--scenes", "bot-status-report", "--out", "unused"])


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeProvider:
    """An OpenRouter-shaped endpoint for attention and the agent, with usage.

    Attention gets typed answers; the agent stays silent. Every reply reports
    tokens, cost and the provider that served it.
    """

    def __init__(self, disposition="WAKE"):
        self.disposition = disposition
        self.bodies = []

    def __call__(self, request, timeout):
        body = json.loads(request.data)
        self.bodies.append(body)
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        if "answer typed questions about the judged message" in system:
            content = json.dumps(answers_leaning(self.disposition))
            usage = {
                "prompt_tokens": 1200,
                "completion_tokens": 300,
                "completion_tokens_details": {"reasoning_tokens": 220},
                "cost": 0.0004,
            }
        else:
            turn = json.loads(user)["participant_turn"]
            content = json.dumps(
                {"protocol": turn["protocol"], "binding": turn["binding"], "action": {"kind": "silence"}}
            )
            usage = {"prompt_tokens": 3000, "completion_tokens": 40, "cost": 0.0031}
        payload = {
            "model": body["model"] + "-20260901",
            "provider": "FixtureCloud",
            "choices": [{"message": {"content": content}}],
            "usage": usage,
        }
        return Response(json.dumps(payload).encode())


class UsageTests(unittest.TestCase):
    """Cost and tokens per call, and a reasoning effort per model (#86)."""

    def test_a_model_label_may_carry_a_reasoning_effort(self):
        self.assertEqual(("deepseek/deepseek-v4.1-flash", None), run.model_spec("deepseek/deepseek-v4.1-flash"))
        self.assertEqual(("deepseek/deepseek-v4.1-flash", "low"), run.model_spec("deepseek/deepseek-v4.1-flash@low"))
        for bad in ("a/model@fast", "@low", "typesafe/jev-1.13@low"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                run.model_spec(bad)
        with mock.patch.dict(os.environ, {"NUNCHI_OPENROUTER": "k"}), mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                run.main(["--models", "a/model@fast", "--scenes", "bot-status-report"])

    def test_the_request_asks_for_cost_and_the_effort(self):
        provider = FakeProvider()
        factory = run.openai_compatible_factory(api_key="k", base_url=run.DEFAULT_BASE_URL, temperature=0)
        scene = scene_by_id("bot-status-report")
        with mock.patch("urllib.request.urlopen", provider):
            run.judge_moment(run.Job(scene, 0, "vigil", "x/model@low", 0), factory, timeout_seconds=5)
            run.judge_moment(run.Job(scene, 0, "vigil", "x/model", 0), factory, timeout_seconds=5)
        with_effort, default = provider.bodies
        self.assertEqual("x/model", with_effort["model"])
        self.assertEqual({"effort": "low"}, with_effort["reasoning"])
        self.assertEqual({"include": True}, with_effort["usage"])
        self.assertNotIn("reasoning", default)
        other = run.openai_compatible_factory(api_key="k", base_url="http://localhost:1/v1", temperature=0)
        with mock.patch("urllib.request.urlopen", provider):
            run.judge_moment(run.Job(scene, 0, "vigil", "x/model@high", 0), other, timeout_seconds=5)
        self.assertEqual("high", provider.bodies[-1]["reasoning_effort"])
        self.assertNotIn("usage", provider.bodies[-1])
        # Reasoning off, for models that take only on/off or a token budget.
        with mock.patch("urllib.request.urlopen", provider):
            run.judge_moment(run.Job(scene, 0, "vigil", "x/model@off", 0), factory, timeout_seconds=5)
            run.judge_moment(run.Job(scene, 0, "vigil", "x/model@off", 0), other, timeout_seconds=5)
        self.assertEqual({"enabled": False}, provider.bodies[-2]["reasoning"])
        self.assertEqual("none", provider.bodies[-1]["reasoning_effort"])

    def test_attention_and_agent_usage_are_recorded(self):
        provider = FakeProvider("WAKE")
        factory = run.openai_compatible_factory(api_key="k", base_url=run.DEFAULT_BASE_URL, temperature=0)
        agents = run.openai_compatible_agent_factory(api_key="k", base_url=run.DEFAULT_BASE_URL, model="fixture/agent")
        scene = scene_by_id("story-across-messages")
        job = run.Job(scene, 2, scene.participants[0], "x/model@low", 0)
        with mock.patch("urllib.request.urlopen", provider):
            record = run.judge_moment(job, factory, timeout_seconds=5, agent_factory=agents, paired=True)
        self.assertEqual(
            {
                "model": "x/model-20260901",
                "provider": "FixtureCloud",
                "prompt_tokens": 1200,
                "completion_tokens": 300,
                "reasoning_tokens": 220,
                "cost": 0.0004,
            },
            record["attention_usage"],
        )
        self.assertEqual(
            {"calls": 1, "prompt_tokens": 3000, "completion_tokens": 40, "cost": 0.0031, "providers": ["FixtureCloud"]},
            record["agent"]["usage"],
        )
        self.assertEqual(0.0031, record["agent"]["without_reading"]["usage"]["cost"])
        self.assertEqual({"include": True}, provider.bodies[1]["usage"])
        # The agent caps its output, so the provider never reserves its whole limit.
        self.assertEqual(run.AGENT_MAX_TOKENS, provider.bodies[1]["max_tokens"])

        summary = run.summarize(
            [scene], ["x/model@low"], [record], [],
            {
                "started_at": "s", "finished_at": "f", "git_sha": "x", "git_dirty": False,
                "nunchi_version": "v", "runs": 1, "temperature": 0, "base_url": "u",
                "calls": 1, "provider_errors": 0, "command": "c",
            },
        )
        self.assertIn(
            "| `x/model@low` | 1/1 | 1200 / 300 / 220 | $0.0004 | $0.0031 | $0.0035 | $0.0031 | FixtureCloud (1) |",
            summary,
        )
        self.assertIn("Reported cost of the whole run: $0.0066", summary)

    def test_a_typed_decision_reports_its_usage_too(self):
        self.assertEqual(
            {"model": "typesafe/jev-1.13-20260917", "prompt_tokens": 1191, "completion_tokens": 166, "cost": 5e-05},
            run.call_usage(
                {
                    "model": "typesafe/jev-1.13-20260917",
                    "answers": {},
                    "usage": {"cost": 5e-05, "input_tokens": 1191, "output_tokens": 166},
                }
            ),
        )
        self.assertEqual({}, run.call_usage(None))

    def test_attentions_own_top_move_is_graded_without_an_agent(self):
        # Model selection runs attention alone; the route's own most likely
        # move is graded as if the agent followed it. Waiting shows nothing
        # yet, so it is graded like staying quiet.
        scene = scene_by_id("story-across-messages")
        job = run.Job(scene, 2, scene.participants[0], "fixture/model", 0)
        woke = run.judge_moment(job, lambda _: FixedModel("WAKE"), timeout_seconds=5)
        self.assertEqual({"move": "speak", "grade": "fits"}, woke["top_move"])
        early = run.judge_moment(run.Job(scene, 0, scene.participants[0], "fixture/model", 0), lambda _: FixedModel("WAKE"), timeout_seconds=5)
        self.assertEqual("miss", early["top_move"]["grade"])
        summary = run.summarize(
            [scene], ["fixture/model"], [woke, early], [],
            {
                "started_at": "s", "finished_at": "f", "git_sha": "x", "git_dirty": False,
                "nunchi_version": "v", "runs": 1, "temperature": 0, "base_url": "u",
                "calls": 2, "provider_errors": 0, "command": "c",
            },
        )
        self.assertIn("| 1 / 1 of 2 |", summary)

    def test_no_usage_means_no_cost_section(self):
        scene = scene_by_id("bot-status-report")
        record = run.judge_moment(run.Job(scene, 0, "vigil", "fixture/model", 0), lambda _: FixedModel("WAKE"), timeout_seconds=5)
        summary = run.summarize(
            [scene], ["fixture/model"], [record], [],
            {
                "started_at": "s", "finished_at": "f", "git_sha": "x", "git_dirty": False,
                "nunchi_version": "v", "runs": 1, "temperature": 0, "base_url": "u",
                "calls": 1, "provider_errors": 0, "command": "c",
            },
        )
        self.assertNotIn("## Cost and tokens", summary)


class LitmusConversionTests(unittest.TestCase):
    def convert(self, category, name):
        fixture = json.loads((litmus.FIXTURES / category / f"{name}.json").read_text())
        meta = json.loads((litmus.FIXTURES / category / f"{name}.meta.json").read_text())
        scene = litmus.convert(category, fixture, meta, snowflakes=litmus._known_snowflakes())
        parse_scene(scene, participants=PARTICIPANTS)
        return scene

    def test_a_mention_of_another_agent_still_passes_step1(self):
        scene = self.convert("discord", "d-mention-recipient-unaddressed")
        self.assertEqual(["castor"], scene["events"][-1]["mentions"])
        self.assertEqual("pass", scene["moments"][0]["step1"])
        self.assertEqual(["stay_quiet"], scene["moments"][0]["fitting"])

    def test_an_expected_turn_makes_quiet_and_a_nod_misses(self):
        scene = self.convert("addressing", "a-mention-snowflake-direct")
        self.assertEqual(["vigil"], scene["events"][-1]["mentions"])
        moment = scene["moments"][0]
        self.assertEqual(["speak"], moment["fitting"])
        self.assertEqual({"stay_quiet", "mhm"}, {miss["move"] for miss in moment["misses"]})

    def test_a_v1_ask_is_speaking(self):
        # Zoe, 2026-10-05: ASK is too specific; speaking covers asking.
        scene = self.convert("multica", "m-baseline-ask-ambiguous")
        self.assertEqual(["speak"], scene["moments"][0]["fitting"])
        with self.assertRaises(SceneError):
            parse_scene(
                minimal(moments=[{"event": "m2", "step1": "pass", "fitting": ["ask"]}]),
                participants=PARTICIPANTS,
            )

    def test_own_echo_under_an_alias_is_the_participant(self):
        scene = self.convert("addressing", "a-self-echo-alias-author")
        self.assertEqual("vigil", scene["events"][-1]["author"])
        self.assertEqual("suppress", scene["moments"][0]["step1"])

    def test_contract_fixtures_are_not_behavior(self):
        self.assertIn("contract", litmus.SKIP)


if __name__ == "__main__":
    unittest.main()
