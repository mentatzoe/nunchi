"""The typed-decision attention route works offline (#94, step 4).

These tests prove the request the adapter sends to a Decisions API endpoint,
how the typed answers come back in the core's shape, and that the engine
decides and writes the reading from them exactly as it does for a chat model.
Whether a typed decision model reads the room well is measured by live
behavior runs, not here.
"""

from __future__ import annotations

import io
import json
import os
import unittest
from unittest import mock
import urllib.error

from evals.behavior import run
from evals.behavior.scene import load_scenes
from nunchi.adapters import decisions_api
from nunchi.adapters.decisions_api import ATTENTION_KINDS, DecisionsAttentionModel
from nunchi.attention import AttentionError, attention_model_from_config
from nunchi.attention_questions import (
    MOVES,
    answer_candidates,
    attention_questions,
    attention_state,
    response_candidates,
)
from tests.v2.test_shared_foundation import foundation, message


def projection():
    return {
        "self": {"participant_id": "vigil", "actor_id": "vigil", "names": ["Vigil"]},
        "room": {"platform": "discord", "id": "r", "kind": "group"},
        "actors": {
            "zoe": {"display_name": "Zoe", "kind": "human"},
            "castor": {"display_name": "Castor", "kind": "bot"},
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
            {"id": "a1", "type": "message", "author_id": "castor", "text": "Yes, 30 s, see retry.py."},
        ],
        "trigger_event_id": "q1",
        "coverage": {"has_more_before": False},
    }


def questions():
    asked = attention_questions("Vigil")
    asked["answered_by"]["candidates"] = answer_candidates(projection())
    asked["responds_to"]["candidates"] = response_candidates(projection())
    return asked


def answers(
    move,
    *,
    addressee="participant",
    asks=0.9,
    answered=0.1,
    answered_by="none",
    responds_to="none",
    mid_thought=0.1,
    adds=0.8,
    conversation=0.95,
):
    probabilities = dict.fromkeys(MOVES, 0.0)
    probabilities.update(move)
    return {
        "conversation": {"type": "noul", "noul": conversation},
        "addressee": {
            "type": "choice",
            "choice": addressee,
            "confidence": 0.8,
            "probabilities": {addressee: 0.86, **({"nobody": 0.14} if addressee != "nobody" else {"room": 0.14})},
        },
        "asks": {"type": "noul", "noul": asks},
        "answered": {"type": "noul", "noul": answered},
        "answered_by": {"type": "choice", "choice": answered_by, "confidence": 0.9, "probabilities": {answered_by: 0.9}},
        "responds_to": {"type": "choice", "choice": responds_to, "confidence": 0.9, "probabilities": {responds_to: 0.9}},
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


class RequestTests(unittest.TestCase):
    def answer(self, payload):
        endpoint = Endpoint(payload)
        model = DecisionsAttentionModel(model="typesafe/jev-1.13", api_key="sk-test")
        with mock.patch("urllib.request.urlopen", endpoint):
            result = model.answer(
                questions=questions(),
                state=attention_state(projection(), "Answer on security and implementation correctness."),
                timeout_seconds=7,
            )
        return result, endpoint, model

    def test_the_request_asks_the_core_questions_about_the_state(self):
        _, endpoint, _ = self.answer({"answers": answers({"speak": 0.9})})
        (request, timeout), = endpoint.requests
        self.assertEqual(decisions_api.DEFAULT_URL, request.full_url)
        self.assertEqual("Bearer sk-test", request.get_header("Authorization"))
        self.assertEqual(7, timeout)
        body = json.loads(request.data)
        self.assertEqual("typesafe/jev-1.13", body["model"])
        asked = body["questions"]
        self.assertEqual(list(attention_questions("Vigil")), list(asked))
        self.assertEqual("noul", asked["conversation"]["type"])
        self.assertEqual({"true", "false"}, set(asked["conversation"]["criteria"]))
        self.assertEqual(set(MOVES), set(asked["move"]["criteria"]))
        # The pointer question offers the messages others wrote, and none.
        self.assertEqual({"message_1", "none"}, set(asked["answered_by"]["criteria"]))
        self.assertIn("Message a1 from Castor", asked["answered_by"]["criteria"]["message_1"])
        # What the judged message responds to may be the participant's own
        # earlier message; only messages before it are offered.
        self.assertEqual({"message_1", "none"}, set(asked["responds_to"]["criteria"]))
        self.assertIn("Message v1 from Vigil", asked["responds_to"]["criteria"]["message_1"])
        self.assertIn("no earlier", asked["responds_to"]["criteria"]["none"])
        state = body["state"]
        self.assertEqual("Answer on security and implementation correctness.", state["participant"]["instructions"])
        self.assertEqual("q1", state["judged_message_id"])
        own = state["conversation"][0]
        self.assertTrue(own["from_participant"])

    def test_answers_come_back_in_the_core_shape(self):
        result, _, model = self.answer(
            {
                "answers": answers(
                    {"speak": 0.7, "wait": 0.2, "mhm": 0.1},
                    answered=0.8,
                    answered_by="message_1",
                    responds_to="message_1",
                )
            }
        )
        self.assertEqual(0.95, result["conversation"])
        self.assertEqual(0.9, result["asks"])
        self.assertEqual("v1", result["responds_to"])
        self.assertEqual({"participant": 0.86, "room": 0.0, "someone_else": 0.0, "nobody": 0.14}, result["addressee"])
        self.assertEqual("a1", result["answered_by"])
        self.assertEqual({"speak": 0.7, "mhm": 0.1, "wait": 0.2, "stay_quiet": 0.0}, result["move"])
        self.assertIsNotNone(model.last_response)
        result, _, _ = self.answer({"answers": answers({"speak": 0.9})})
        self.assertIsNone(result["answered_by"])
        self.assertIsNone(result["responds_to"])

    def test_a_pointer_question_without_candidates_is_not_asked(self):
        asked = attention_questions("Vigil")
        asked["answered_by"]["candidates"] = []
        request, pointers = decisions_api.decisions_questions(asked, attention_state(projection(), "x"))
        self.assertNotIn("answered_by", request)
        self.assertEqual({}, pointers)

    def test_provider_failures_are_attention_errors(self):
        error = urllib.error.HTTPError(decisions_api.DEFAULT_URL, 429, "busy", {}, io.BytesIO(b"{}"))
        with self.assertRaisesRegex(AttentionError, "HTTP 429"):
            self.answer(error)
        with self.assertRaisesRegex(AttentionError, "no answers"):
            self.answer({"error": "nope"})
        incomplete = answers({"speak": 1.0})
        del incomplete["mid_thought"]
        with self.assertRaisesRegex(AttentionError, "no answer to mid_thought"):
            self.answer({"answers": incomplete})


class EngineTests(unittest.TestCase):
    def test_the_engine_decides_and_reads_the_room_from_typed_answers(self):
        endpoint = Endpoint({"answers": answers({"wait": 0.6, "speak": 0.3, "stay_quiet": 0.1}, addressee="someone_else")})
        wakes = []
        pipeline, _, _, _ = foundation(
            model=DecisionsAttentionModel(model="typesafe/jev-1.13", api_key="sk-test"),
            participant=lambda **turn: wakes.append(turn["wake"]) or None,
        )
        with mock.patch("urllib.request.urlopen", endpoint):
            outcome = pipeline.handle_delivery(
                delivery_id="d1",
                event=message("e1", text="Castor, could you look at this?"),
                actors={"human:zoe": {"kind": "human"}},
            )
        # Waiting is the agent's own call: step 1 never suppresses a message
        # just because it was addressed to someone else.
        self.assertEqual("DEFER", outcome.opportunities[0].effective_disposition)
        reading = [item["note"] for item in wakes[0]["attention"]["advice"]]
        self.assertEqual(
            "The judged message is addressed to someone else, and it asks for something (0.86; asks 0.90).",
            reading[0],
        )
        self.assertTrue(reading[-1].startswith("Kinds of response that could fit, most likely first: wait 0.60"))
        body = json.loads(endpoint.requests[0][0].data)
        self.assertNotIn("instructions", body)

    def test_the_kind_is_configurable(self):
        with mock.patch.dict(os.environ, {"NUNCHI_ATTENTION_API_KEY": "sk-test"}):
            model = attention_model_from_config(
                {"kind": "decisions-api", "model": "typesafe/jev-1.13"},
                host_kinds=ATTENTION_KINDS,
            )
        self.assertIsInstance(model, DecisionsAttentionModel)
        self.assertEqual(("decisions-api", "typesafe/jev-1.13"), (model.provider, model.model_id))
        with self.assertRaisesRegex(Exception, "unexpected fields"):
            DecisionsAttentionModel.from_trusted_config({"model": "m", "base_url": "x"})


class RunnerTests(unittest.TestCase):
    def test_typesafe_models_go_to_the_typed_route(self):
        factory = run.openai_compatible_factory(api_key="k", base_url=run.DEFAULT_BASE_URL, temperature=0)
        self.assertIsInstance(factory("typesafe/jev-1.13"), DecisionsAttentionModel)
        self.assertIsInstance(factory("~typesafe/jev-latest"), DecisionsAttentionModel)
        self.assertNotIsInstance(factory("google/gemini-3.8-flash"), DecisionsAttentionModel)
        self.assertIn("typesafe/jev-1.13", run.DEFAULT_MODELS)

    def test_a_moment_judged_by_a_typed_model_records_its_answers(self):
        scene = next(scene for scene in load_scenes() if scene.id == "story-across-messages")
        endpoint = Endpoint(
            {"model": "typesafe/jev-1.13-20260917", "answers": answers({"wait": 0.8, "speak": 0.2}, mid_thought=0.9), "usage": {"cost": 0.00002}}
        )
        factory = run.openai_compatible_factory(api_key="k", base_url=run.DEFAULT_BASE_URL, temperature=0)
        with mock.patch("urllib.request.urlopen", endpoint):
            record = run.judge_moment(run.Job(scene, 0, "vigil", "typesafe/jev-1.13", 0), factory, timeout_seconds=5)
        self.assertEqual("DEFER", record["decision"]["effective_disposition"])
        self.assertEqual("typesafe/jev-1.13-20260917", record["model_response"]["model"])
        self.assertEqual(0.9, record["decision"]["answers"]["mid_thought"])
        state = json.loads(endpoint.requests[0][0].data)["state"]
        self.assertEqual(scene.profiles["vigil"]["instructions"], state["participant"]["instructions"])

    def test_a_shorter_reading_keeps_the_kinds_of_response(self):
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
