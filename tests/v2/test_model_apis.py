"""Attention through the Messages and Responses APIs (#94 step 8, #87).

Both routes send the core's prompt, observation text and answer schema in
their API's request shape, and hand the reply to the core's decoder. A local
HTTP double stands in for the provider.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
import unittest
from unittest import mock

from nunchi.adapters.model_apis import (
    ATTENTION_KINDS,
    MESSAGES_KIND,
    RESPONSES_KIND,
    MessagesAttentionModel,
    ResponsesAttentionModel,
    portable_schema,
)
from nunchi.attention import AttentionError, attention_judgment_schema, attention_model_from_config
from nunchi.attention_questions import answers_leaning
from nunchi.errors import ValidationError
from tests.v2.test_shared_foundation import foundation, message

PROJECTION = {"trigger_event_id": "e1", "unattended_event_ids": ["e0"]}


def judgment() -> dict:
    answers = answers_leaning("WAKE")
    answers["notes"] = []
    return answers


class _Server:
    def __init__(self, test: unittest.TestCase, reply: dict) -> None:
        self.seen: list = []
        seen = self.seen

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers["Content-Length"])
                # Header names are case-insensitive; compare them in lower case.
                headers = {key.lower(): value for key, value in self.headers.items()}
                seen.append((self.path, headers, json.loads(self.rfile.read(length))))
                payload = json.dumps(reply).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        test.addCleanup(server.server_close)
        test.addCleanup(server.shutdown)
        self.base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"


def messages_reply(text: str, stop: str = "end_turn") -> dict:
    return {
        "type": "message",
        "model": "a-model",
        "stop_reason": stop,
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def responses_reply(text: str, status: str = "completed") -> dict:
    return {
        "object": "response",
        "model": "a-model",
        "status": status,
        "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]},
        ],
        "usage": {"input_tokens": 10, "output_tokens": 5, "output_tokens_details": {"reasoning_tokens": 2}},
    }


class PortableSchemaTests(unittest.TestCase):
    def test_bounds_go_and_every_property_is_required(self) -> None:
        schema = portable_schema(attention_judgment_schema(unattended=True))
        text = json.dumps(schema)
        for keyword in ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "uniqueItems"):
            self.assertNotIn(f'"{keyword}"', text)
        self.assertEqual(sorted(schema["properties"]), sorted(schema["required"]))
        self.assertIn("notes", schema["required"])
        self.assertIn("calls_for_participant", schema["required"])
        note = schema["properties"]["notes"]["items"]
        self.assertEqual(["note", "evidence_event_ids"], note["required"])
        # The core's own schema keeps its bounds.
        self.assertIn("minimum", json.dumps(attention_judgment_schema()))


class MessagesRouteTests(unittest.TestCase):
    def test_request_shape_and_reply(self) -> None:
        server = _Server(self, messages_reply(json.dumps(judgment())))
        model = MessagesAttentionModel(
            model="a-model", api_key="secret", base_url=server.base_url, effort="low"
        )
        result = model.judge(instructions="judge", projection=PROJECTION, timeout_seconds=5)
        self.assertEqual(judgment(), result)
        path, headers, body = server.seen[0]
        self.assertEqual("/v1/messages", path)
        self.assertEqual("secret", headers["x-api-key"])
        self.assertNotIn("authorization", headers)
        self.assertEqual("2023-06-01", headers["anthropic-version"])
        self.assertEqual("judge", body["system"])
        self.assertEqual("user", body["messages"][0]["role"])
        self.assertEqual("json_schema", body["output_config"]["format"]["type"])
        self.assertIn("calls_for_participant", body["output_config"]["format"]["schema"]["required"])
        self.assertEqual("low", body["output_config"]["effort"])
        self.assertEqual(4096, body["max_tokens"])
        self.assertNotIn("temperature", body)
        self.assertEqual(5, model.last_response["usage"]["output_tokens"])

    def test_a_router_takes_the_key_as_a_bearer_token(self) -> None:
        server = _Server(self, messages_reply(json.dumps(judgment())))
        model = MessagesAttentionModel(
            model="a-model", api_key="secret", base_url=server.base_url, auth="bearer", temperature=0
        )
        model.judge(instructions="judge", projection=PROJECTION, timeout_seconds=5)
        _, headers, body = server.seen[0]
        self.assertEqual("Bearer secret", headers["authorization"])
        self.assertNotIn("x-api-key", headers)
        self.assertEqual(0, body["temperature"])

    def test_a_cut_or_refused_reply_is_a_provider_failure(self) -> None:
        for stop in ("max_tokens", "refusal"):
            with self.subTest(stop=stop):
                server = _Server(self, messages_reply('{"conversation": 0.9', stop))
                model = MessagesAttentionModel(model="m", api_key="k", base_url=server.base_url)
                with self.assertRaisesRegex(AttentionError, stop):
                    model.judge(instructions="judge", projection=PROJECTION, timeout_seconds=5)

    def test_a_reply_without_text_is_a_provider_failure(self) -> None:
        server = _Server(self, {"stop_reason": "end_turn", "content": [{"type": "thinking", "thinking": ""}]})
        model = MessagesAttentionModel(model="m", api_key="k", base_url=server.base_url)
        with self.assertRaisesRegex(AttentionError, "no text"):
            model.judge(instructions="judge", projection=PROJECTION, timeout_seconds=5)


class ResponsesRouteTests(unittest.TestCase):
    def test_request_shape_and_reply(self) -> None:
        server = _Server(self, responses_reply(json.dumps(judgment())))
        model = ResponsesAttentionModel(
            model="a-model", api_key="secret", base_url=server.base_url, effort="low", temperature=0
        )
        result = model.judge(instructions="judge", projection=PROJECTION, timeout_seconds=5)
        self.assertEqual(judgment(), result)
        path, headers, body = server.seen[0]
        self.assertEqual("/v1/responses", path)
        self.assertEqual("Bearer secret", headers["authorization"])
        self.assertEqual("judge", body["instructions"])
        self.assertEqual("user", body["input"][0]["role"])
        fmt = body["text"]["format"]
        self.assertEqual(("json_schema", True), (fmt["type"], fmt["strict"]))
        self.assertIn("notes", fmt["schema"]["required"])
        self.assertEqual({"effort": "low"}, body["reasoning"])
        self.assertFalse(body["store"])
        self.assertEqual(0, body["temperature"])

    def test_an_incomplete_or_refused_reply_is_a_provider_failure(self) -> None:
        cases = (
            (responses_reply("{", status="incomplete"), "incomplete"),
            (
                {
                    "status": "completed",
                    "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}],
                },
                "refused",
            ),
            ({"status": "completed", "output": []}, "no output text"),
        )
        for reply, detail in cases:
            with self.subTest(detail=detail):
                server = _Server(self, reply)
                model = ResponsesAttentionModel(model="m", api_key="k", base_url=server.base_url)
                with self.assertRaisesRegex(AttentionError, detail):
                    model.judge(instructions="judge", projection=PROJECTION, timeout_seconds=5)

    def test_extra_body_cannot_override_the_request(self) -> None:
        for field in ("input", "text", "store", "instructions"):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    ResponsesAttentionModel(model="m", api_key="k", base_url="https://x", extra_body={field: 1})
        with self.assertRaises(ValidationError):
            MessagesAttentionModel(model="m", api_key="k", base_url="https://x", extra_body={"output_config": {}})


class ConfigurationTests(unittest.TestCase):
    def test_kinds_build_from_trusted_config_with_an_explicit_endpoint(self) -> None:
        self.assertEqual({"decisions-api", MESSAGES_KIND, RESPONSES_KIND}, set(ATTENTION_KINDS))
        with mock.patch.dict(os.environ, {"KEY": "secret"}):
            messages = attention_model_from_config(
                {"kind": MESSAGES_KIND, "model": "m", "base_url": "https://x/v1", "api_key_env": "KEY", "auth": "bearer"},
                host_kinds=ATTENTION_KINDS,
            )
            responses = attention_model_from_config(
                {"kind": RESPONSES_KIND, "model": "m", "base_url": "https://x/v1", "api_key_env": "KEY"},
                host_kinds=ATTENTION_KINDS,
            )
            self.assertIsInstance(messages, MessagesAttentionModel)
            self.assertEqual(("https://x/v1/messages", MESSAGES_KIND), (messages._url, messages.provider))
            self.assertIsInstance(responses, ResponsesAttentionModel)
            for bad in (
                {"kind": RESPONSES_KIND, "model": "m", "api_key_env": "KEY"},
                {"kind": RESPONSES_KIND, "model": "m", "base_url": "https://x", "api_key_env": "KEY", "seed": 1},
                {"kind": MESSAGES_KIND, "model": "m", "base_url": "https://x", "api_key_env": "KEY", "auth": "cookie"},
                {"kind": MESSAGES_KIND, "model": "m", "base_url": "https://x", "api_key_env": "ABSENT"},
                {"kind": MESSAGES_KIND, "model": "m", "base_url": "https://x", "api_key_env": "KEY", "effort": "huge"},
            ):
                with self.subTest(config=bad):
                    with self.assertRaises(ValidationError):
                        attention_model_from_config(bad, host_kinds=ATTENTION_KINDS)

    def test_the_engine_judges_through_a_route_like_any_other(self) -> None:
        for model_class, reply in (
            (MessagesAttentionModel, messages_reply(json.dumps(judgment()))),
            (ResponsesAttentionModel, responses_reply("```json\n" + json.dumps(judgment()) + "\n```")),
        ):
            with self.subTest(route=model_class.kind):
                server = _Server(self, reply)
                model = model_class(model="m", api_key="k", base_url=server.base_url)
                pipeline, _, _, _ = foundation(model=model)
                outcome = pipeline.handle_delivery(
                    delivery_id="d-route",
                    event=message("e-route"),
                    actors={"human:zoe": {"kind": "human"}},
                )
                opportunity = outcome.opportunities[0]
                self.assertEqual(("ok", "WAKE"), (opportunity.decision_status, opportunity.effective_disposition))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
