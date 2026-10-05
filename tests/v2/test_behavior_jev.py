"""The Jev prototype route in the behavior suite works offline (#94, step 4).

These tests prove the request Nunchi sends to the Decisions API and how Jev's
typed answers become today's attention judgment. Whether Jev reads the room
well is measured by live behavior runs, not here.
"""

from __future__ import annotations

import io
import json
import unittest
from unittest import mock
import urllib.error

from evals.behavior import jev, run
from evals.behavior.scene import load_scenes
from nunchi.attention import AttentionError, _validate_model_judgment


def projection():
    return {
        "self": {"participant_id": "vigil", "actor_id": "vigil", "names": ["Vigil"]},
        "room": {"platform": "discord", "id": "r", "kind": "group"},
        "actors": {
            "zoe": {"display_name": "Zoe", "kind": "human"},
            "vigil": {"display_name": "Vigil", "kind": "bot"},
        },
        "events": [
            {"id": "v1", "type": "message", "author_id": "vigil", "text": "I rewrote the backoff."},
            {
                "id": "q1",
                "type": "message",
                "author_id": "zoe",
                "text": "Vigil, does it cap at 30 seconds?",
                "mentioned_actor_ids": ["vigil"],
                "mentions_room": False,
                "timestamp": "2026-10-05T11:00:00.000Z",
            },
        ],
        "trigger_event_id": "q1",
        "coverage": {"has_more_before": False},
    }


def answers(move, *, addressee="participant", answered=0.1, mid_thought=0.1, adds=0.8, conversation=0.95):
    probabilities = dict.fromkeys(jev.MOVES, 0.0)
    probabilities.update(move)
    return {
        "conversation": {"type": "noul", "noul": conversation},
        "addressee": {
            "type": "choice",
            "choice": addressee,
            "confidence": 0.8,
            "probabilities": {addressee: 0.86},
        },
        "answered": {"type": "noul", "noul": answered},
        "mid_thought": {"type": "noul", "noul": mid_thought},
        "adds_something": {"type": "noul", "noul": adds},
        "move": {
            "type": "choice",
            "choice": max(probabilities, key=probabilities.get),
            "confidence": 0.7,
            "probabilities": probabilities,
        },
    }


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Endpoint:
    """Stands in for the Decisions API and keeps every request."""

    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        if isinstance(self.payload, Exception):
            raise self.payload
        return FakeResponse(json.dumps(self.payload).encode())


class Profile:
    instructions = "Answer on security and implementation correctness."


class JevRequestTests(unittest.TestCase):
    def judge(self, payload):
        endpoint = Endpoint(payload)
        model = jev.JevAttentionModel(model="typesafe/jev-1.13", api_key="sk-test")
        model.bind_profile(Profile())
        with mock.patch("urllib.request.urlopen", endpoint):
            judgment = model.judge(instructions="LLM prompt, ignored", projection=projection(), timeout_seconds=7)
        return judgment, endpoint, model

    def test_the_request_asks_typed_questions_about_the_conversation(self):
        _, endpoint, _ = self.judge({"model": "typesafe/jev-1.13-x", "answers": answers({"speak": 0.9})})
        (request, timeout), = endpoint.requests
        self.assertEqual(jev.DEFAULT_DECISIONS_URL, request.full_url)
        self.assertEqual("Bearer sk-test", request.get_header("Authorization"))
        self.assertEqual(7, timeout)
        body = json.loads(request.data)
        self.assertEqual("typesafe/jev-1.13", body["model"])
        self.assertEqual(
            {"conversation", "addressee", "answered", "mid_thought", "adds_something", "move"},
            set(body["questions"]),
        )
        self.assertEqual(set(jev.MOVES), set(body["questions"]["move"]["criteria"]))
        state = body["state"]
        self.assertEqual("Answer on security and implementation correctness.", state["participant"]["instructions"])
        self.assertEqual("q1", state["judged_message_id"])
        own, question = state["conversation"]
        self.assertTrue(own["from_participant"])
        self.assertEqual(("Zoe", ["Vigil"]), (question["from"], question["mentions"]))
        self.assertNotIn("LLM prompt", json.dumps(body))

    def test_speaking_wakes_with_a_reading_built_from_the_answers(self):
        judgment, _, model = self.judge({"answers": answers({"speak": 0.7, "wait": 0.2, "mhm": 0.1})})
        _validate_model_judgment(judgment, event_ids={"v1", "q1"})
        self.assertEqual("WAKE", judgment["disposition"])
        self.assertEqual({"PASS": 0.2, "ACK": 0.1, "ASK": 0.0, "SPEAK": 0.7}, judgment["legacy_verdict_confidences"])
        notes = [item["note"] for item in judgment["attention_advice"]]
        self.assertTrue(notes[0].startswith("The judged message is addressed to you (Jev: 0.86)"))
        self.assertIn("You may know something useful that nobody has said yet (Jev: 0.80).", notes)
        self.assertEqual(
            "Kinds of response that could fit, by Jev's probability: speak 0.70, wait 0.20, a quick mhm 0.10, stay quiet 0.00.",
            notes[-1],
        )
        self.assertTrue(all(item["evidence_event_ids"] == ["q1"] for item in judgment["attention_advice"]))
        self.assertIsNotNone(model.last_response)

    def test_waiting_suppresses_and_says_why(self):
        judgment, _, _ = self.judge(
            {"answers": answers({"wait": 0.6, "speak": 0.3, "stay_quiet": 0.1}, addressee="someone_else", answered=0.7, mid_thought=0.8, adds=0.2)}
        )
        self.assertEqual("SUPPRESS", judgment["disposition"])
        self.assertAlmostEqual(0.7, judgment["legacy_verdict_confidences"]["PASS"])
        notes = [item["note"] for item in judgment["attention_advice"]]
        self.assertEqual(4, len(notes))
        self.assertIn("addressed to someone else", notes[0])
        self.assertIn("already answered", notes[1])
        self.assertIn("mid-thought", notes[2])

    def test_a_tie_pays_attention(self):
        judgment, _, _ = self.judge({"answers": answers({"speak": 0.5, "stay_quiet": 0.5})})
        self.assertEqual("WAKE", judgment["disposition"])

    def test_provider_failures_are_attention_errors(self):
        error = urllib.error.HTTPError(jev.DEFAULT_DECISIONS_URL, 429, "busy", {}, io.BytesIO(b"{}"))
        with self.assertRaisesRegex(AttentionError, "HTTP 429"):
            self.judge(error)
        with self.assertRaisesRegex(AttentionError, "no answers"):
            self.judge({"error": "nope"})


class JevInTheRunnerTests(unittest.TestCase):
    def test_typesafe_models_go_to_jev(self):
        factory = run.openai_compatible_factory(api_key="k", base_url=run.DEFAULT_BASE_URL, temperature=0)
        self.assertIsInstance(factory("typesafe/jev-1.13"), jev.JevAttentionModel)
        self.assertIsInstance(factory("~typesafe/jev-latest"), jev.JevAttentionModel)
        self.assertNotIsInstance(factory("google/gemini-3.8-flash"), jev.JevAttentionModel)
        self.assertIn("typesafe/jev-1.13", run.DEFAULT_MODELS)

    def test_a_moment_judged_by_jev_records_its_answers(self):
        scene = next(scene for scene in load_scenes() if scene.id == "story-across-messages")
        endpoint = Endpoint(
            {"model": "typesafe/jev-1.13-20260917", "answers": answers({"wait": 0.8, "speak": 0.2}, mid_thought=0.9), "usage": {"cost": 0.00002}}
        )
        factory = run.openai_compatible_factory(api_key="k", base_url=run.DEFAULT_BASE_URL, temperature=0)
        with mock.patch("urllib.request.urlopen", endpoint):
            record = run.judge_moment(run.Job(scene, 0, "vigil", "typesafe/jev-1.13", 0), factory, timeout_seconds=5)
        self.assertEqual("stay_quiet", record["result"])
        self.assertEqual("fits", record["grade"]["visible"])
        self.assertEqual("typesafe/jev-1.13-20260917", record["model_response"]["model"])
        state = json.loads(endpoint.requests[0][0].data)["state"]
        self.assertEqual(scene.profiles["vigil"]["instructions"], state["participant"]["instructions"])

    def test_a_shorter_reading_keeps_the_fitting_moves(self):
        scene = next(scene for scene in load_scenes() if scene.id == "story-across-messages")
        endpoint = Endpoint({"answers": answers({"speak": 0.9, "wait": 0.1}, answered=0.8, mid_thought=0.8)})
        factory = run.openai_compatible_factory(api_key="k", base_url=run.DEFAULT_BASE_URL, temperature=0)
        with mock.patch("urllib.request.urlopen", endpoint):
            record = run.judge_moment(
                run.Job(scene, 2, "vigil", "typesafe/jev-1.13", 0),
                factory,
                timeout_seconds=5,
                reading_items=2,
                reading_chars=120,
            )
        notes = [item["note"] for item in record["decision"]["attention_advice"]]
        self.assertEqual(2, len(notes))
        self.assertTrue(notes[-1].startswith("Kinds of response that could fit"))
        self.assertTrue(all(len(note) <= 120 for note in notes))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
