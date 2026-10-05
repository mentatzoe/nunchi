"""The behavioral evaluation harness works offline (#86).

These tests prove plumbing only: scenes load, moments reach the production
attention path, grades follow the rules in `evals/behavior/score.py`, and a
run never writes its key. Whether models read the room is measured by live
runs, not here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


PARTICIPANTS = load_participants()


def judgment(disposition, *, evidence=(), suppress_margin=True):
    confidences = {"PASS": 0.0, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.0}
    if disposition == "SUPPRESS":
        confidences["PASS"] = 1.0 if suppress_margin else 0.5
    elif disposition == "ACK":
        confidences["ACK"] = 1.0
    else:
        confidences["SPEAK"] = 1.0
    return {
        "disposition": disposition,
        "reasons": [f"fixture {disposition}"],
        "evidence_event_ids": list(evidence),
        "legacy_verdict_confidences": confidences,
    }


class FixedModel:
    """Returns one judgment and keeps every projection it saw."""

    name = "participant-attention"
    provider = "fixture"

    def __init__(self, disposition, *, evidence=(), model_id="fixture/model"):
        self.disposition = disposition
        self.evidence = evidence
        self.model_id = model_id
        self.projections = []

    def judge(self, *, instructions, projection, timeout_seconds):
        self.projections.append(projection)
        evidence = [item for item in self.evidence if item in {event["id"] for event in projection["events"]}]
        return judgment(self.disposition, evidence=evidence or [projection["trigger_event_id"]])


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
        "moments": [{"event": "m2", "step1": "pass", "fitting": ["contribute"]}],
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
                        "fitting": ["contribute"],
                        "misses": [{"move": "contribute", "why": "x"}],
                    }
                ]
            },
            "event and pause": {
                "moments": [
                    {"event": "m2", "pause_after": "m2", "pause": "5m", "step1": "pass", "fitting": ["contribute"]}
                ]
            },
            "pointer to nothing": {
                "moments": [
                    {
                        "event": "m2",
                        "step1": "pass",
                        "fitting": ["contribute"],
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
    def judge(self, scene_id, moment, disposition, **kwargs):
        model = FixedModel(disposition, **kwargs)
        scene = scene_by_id(scene_id)
        job = run.Job(scene, moment, scene.participants[0], "fixture/model", 0)
        record = run.judge_moment(job, lambda _: model, timeout_seconds=5)
        return record, model

    def test_suppress_at_the_end_of_the_story_is_a_miss(self):
        record, model = self.judge("story-across-messages", 2, "SUPPRESS")
        self.assertEqual("stay_quiet", record["result"])
        self.assertEqual("miss", record["grade"]["visible"])
        self.assertEqual(["s1", "s2", "s3", "s4", "s5"], [event["id"] for event in model.projections[0]["events"]])

    def test_a_moment_sees_only_what_had_happened(self):
        _, model = self.judge("story-across-messages", 0, "ACK")
        self.assertEqual(["s1", "s2"], [event["id"] for event in model.projections[0]["events"]])

    def test_ack_goes_through_the_capability_and_counts_as_mhm(self):
        record, _ = self.judge("story-across-messages", 0, "ACK")
        self.assertEqual("mhm", record["result"])
        self.assertEqual("ACK", record["decision"]["effective_disposition"])
        self.assertEqual("fits", record["grade"]["visible"])

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
        record, _ = self.judge("quiet-for-hours", 0, "WAKE", evidence=("n2",))
        self.assertEqual([False, True], record["cited"])

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
            [{"scene": scene.id, "moment": 0, "model": "m", "run": 0}],
            run.together_findings([scene], records),
        )

    def test_scene_selection(self):
        scenes = load_scenes()
        self.assertEqual(8, len(run.select_scenes(scenes, "behavior")))
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
        self.assertIn("1 of 1 calls failed", summary)
        self.assertIn("HTTP 402 insufficient credits", summary)

    def test_a_rejected_reply_is_kept_with_its_reason(self):
        class Uncited(FixedModel):
            def judge(self, *, instructions, projection, timeout_seconds):
                reply = judgment("WAKE", evidence=["not-in-the-snapshot"])
                return reply

        scene = scene_by_id("bot-status-report")
        job = run.Job(scene, 0, "vigil", "bad/model", 0)
        record = run.judge_moment(job, lambda _: Uncited("WAKE"), timeout_seconds=5)
        self.assertTrue(record["provider_error"])
        self.assertEqual(["not-in-the-snapshot"], record["raw_reply"]["evidence_event_ids"])
        self.assertEqual("model evidence must cite only supplied event IDs", record["invalid_reason"])
        summary = run.summarize(
            [scene], ["bad/model"], [record], [],
            {
                "started_at": "s", "finished_at": "f", "git_sha": "x", "git_dirty": False,
                "nunchi_version": "v", "runs": 1, "temperature": 0, "base_url": "u",
                "calls": 1, "provider_errors": 1, "command": "c",
            },
        )
        self.assertIn("invalid reply: model evidence must cite only supplied event IDs", summary)

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

    def test_a_live_run_needs_the_key(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                run.main(["--scenes", "bot-status-report", "--out", "unused"])


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
        self.assertEqual(["contribute"], moment["fitting"])
        self.assertEqual({"stay_quiet", "mhm"}, {miss["move"] for miss in moment["misses"]})

    def test_own_echo_under_an_alias_is_the_participant(self):
        scene = self.convert("addressing", "a-self-echo-alias-author")
        self.assertEqual("vigil", scene["events"][-1]["author"])
        self.assertEqual("suppress", scene["moments"][0]["step1"])

    def test_contract_fixtures_are_not_behavior(self):
        self.assertIn("contract", litmus.SKIP)


if __name__ == "__main__":
    unittest.main()
