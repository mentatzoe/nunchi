"""Tests for the channel-local admission adapter.

Mapping and routing are tested offline with a stub classifier (the gate accepts
an injected ``evaluate_fn``); the real core path is exercised via the
deterministic fixture provider (`TURNAWARE_CLASSIFIER_TEST_RESULT`). Nothing
here touches a live provider.
"""

import io
import json
import os
import pathlib
import re
import unittest
from unittest import mock

from turnaware.adapters import channel
from turnaware.adapters.channel import (
    SILENT_PASS_SENTINEL,
    ChannelMessage,
    build_request,
    gate,
)
from turnaware.errors import TurnAwareError, ValidationError

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "turnaware"


def _stub(verdict, *, reasons=("stub",), checked=()):
    payload = {
        "verdict": verdict,
        "classifier": "product",
        "classifier_model": "stub-model",
        "confidences": {v: (0.7 if v == verdict else 0.1) for v in ("PASS", "ACK", "ASK", "SPEAK")},
        "context_checked": list(checked),
        "reasons": list(reasons),
        "request_id": "req-1",
    }
    return lambda request: payload


class BuildRequestTests(unittest.TestCase):
    def test_maps_trigger_history_and_identity(self):
        req = build_request(
            ChannelMessage(content="dalgos, summarize the change", author="zoe",
                           author_kind="human", message_id="m-100"),
            [
                ChannelMessage(content="rules updated", author="vigil",
                               author_kind="peer_bot", message_id="m-98"),
                ChannelMessage(content="I read the doc", author="dalgos",
                               author_kind="self", message_id="m-99"),
            ],
            agent_id="dalgos",
            agent_role="peer",
            surface={"type": "discord", "channel_id": "c-1"},
        )
        self.assertEqual(req["trigger"]["id"], "m-100")
        self.assertEqual(req["trigger"]["content"], "dalgos, summarize the change")
        self.assertEqual(req["agent"], {"id": "dalgos", "role": "peer"})
        self.assertEqual(req["surface"]["type"], "discord")
        self.assertEqual(req["request_id"], "m-100")
        # transcript roles are normalized for the suppressor / directive rubric
        self.assertEqual(req["context"][0]["type"], "peer")
        self.assertEqual(req["context"][1]["type"], "self")

    def test_self_role_inferred_when_author_matches_agent(self):
        req = build_request(
            {"content": "ping", "id": "t-1"},
            [{"content": "my earlier turn", "author": "dalgos", "id": "h-1"}],
            agent_id="dalgos",
        )
        self.assertEqual(req["context"][0]["type"], "self")

    def test_agent_mention_id_threaded_into_envelope(self):
        # The addressing rule needs the agent's @mention handle to tell whether
        # an @mention targets this agent; the adapter must pass it through.
        req = build_request(
            {"content": "hi <@123>", "id": "t-1"}, [],
            agent_id="dalgos", agent_mention_id="999",
        )
        self.assertEqual(req["agent"]["mention_id"], "999")

    def test_pinned_rules_injected_as_context(self):
        req = build_request(
            {"content": "hi", "id": "t-1"},
            [],
            agent_id="dalgos",
            pinned_rules="Default is PASS. Speak only with net-new value.",
        )
        self.assertEqual(req["context"][0]["id"], "pinned-rules")
        self.assertEqual(req["context"][0]["type"], "pinned-rules")

    def test_empty_trigger_content_rejected(self):
        with self.assertRaises(ValidationError):
            build_request({"content": "   ", "id": "t"}, [], agent_id="d")


class GateRoutingTests(unittest.TestCase):
    def test_pass_is_silent_and_emits_sentinel(self):
        r = gate({"content": "peer chatter", "id": "t-1"}, [], agent_id="d",
                 evaluate_fn=_stub("PASS"))
        self.assertTrue(r.silent)
        self.assertEqual(r.sentinel, SILENT_PASS_SENTINEL)
        self.assertEqual(r.emit(), SILENT_PASS_SENTINEL)

    def test_speak_is_not_silent_and_emits_nothing(self):
        r = gate({"content": "implement X", "id": "t-1"}, [], agent_id="d",
                 evaluate_fn=_stub("SPEAK"))
        self.assertFalse(r.silent)
        self.assertIsNone(r.sentinel)
        self.assertEqual(r.emit(), "")
        self.assertIn("participant turn", r.run_shape)

    def test_run_shapes_present_for_all_verdicts(self):
        for v in ("PASS", "ACK", "ASK", "SPEAK"):
            r = gate({"content": "x", "id": "t"}, [], agent_id="d", evaluate_fn=_stub(v))
            self.assertEqual(r.verdict, v)
            self.assertTrue(r.run_shape)

    def test_result_carries_no_reply_prose_fields(self):
        r = gate({"content": "x", "id": "t"}, [], agent_id="d", evaluate_fn=_stub("SPEAK"))
        for forbidden in ("message", "reply", "draft", "content"):
            self.assertNotIn(forbidden, r.__dict__)


class FailPolicyTests(unittest.TestCase):
    def _boom(self, request):
        raise TurnAwareError("provider down")

    def test_fail_open_degrades_to_speak(self):
        r = gate({"content": "x", "id": "t"}, [], agent_id="d",
                 fail_policy="open", evaluate_fn=self._boom)
        self.assertEqual(r.verdict, "SPEAK")
        self.assertFalse(r.silent)
        self.assertTrue(r.degraded)
        self.assertIn("provider down", r.error)

    def test_fail_closed_degrades_to_pass_silent(self):
        r = gate({"content": "x", "id": "t"}, [], agent_id="d",
                 fail_policy="closed", evaluate_fn=self._boom)
        self.assertEqual(r.verdict, "PASS")
        self.assertTrue(r.silent)
        self.assertEqual(r.sentinel, SILENT_PASS_SENTINEL)
        self.assertTrue(r.degraded)

    def test_fail_raise_propagates(self):
        with self.assertRaises(TurnAwareError):
            gate({"content": "x", "id": "t"}, [], agent_id="d",
                 fail_policy="raise", evaluate_fn=self._boom)


class RealCorePathTests(unittest.TestCase):
    """Exercise the real evaluate() via the deterministic fixture provider."""

    def _inject(self, verdict, checked):
        payload = {
            "verdict": verdict,
            "confidences": {v: (0.8 if v == verdict else 0.05) for v in ("PASS", "ACK", "ASK", "SPEAK")},
            "context_checked": list(checked),
            "reasons": [f"fixture provider chose {verdict}"],
        }
        return mock.patch.dict(os.environ, {"TURNAWARE_CLASSIFIER_TEST_RESULT": json.dumps(payload)})

    def test_real_gate_pass_emits_sentinel(self):
        with self._inject("PASS", checked=["trigger:t-1"]):
            r = gate({"content": "already handled", "id": "t-1"}, [], agent_id="dalgos")
        self.assertTrue(r.silent)
        self.assertEqual(r.emit(), SILENT_PASS_SENTINEL)
        self.assertEqual(r.classifier_model, "turnaware-test-fixture-provider")

    def test_real_gate_speak_routes_through(self):
        with self._inject("SPEAK", checked=["trigger:t-1"]):
            r = gate({"content": "dalgos, implement the MVP", "id": "t-1"}, [], agent_id="dalgos")
        self.assertEqual(r.verdict, "SPEAK")
        self.assertFalse(r.silent)


class CliTests(unittest.TestCase):
    def _run(self, payload):
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), \
                mock.patch("sys.stdout", buf_out), mock.patch("sys.stderr", buf_err):
            code = channel.main([])
        return code, buf_out.getvalue(), buf_err.getvalue()

    def test_cli_pass_prints_sentinel(self):
        payload = {
            "trigger": {"content": "peer noise", "id": "t-1"},
            "history": [],
            "agent": {"id": "dalgos"},
            "fail_policy": "open",
        }
        with mock.patch("turnaware.adapters.channel.evaluate", _stub("PASS")):
            code, out, _ = self._run(payload)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), SILENT_PASS_SENTINEL)

    def test_cli_speak_prints_json_directive(self):
        payload = {
            "trigger": {"content": "implement X", "id": "t-1"},
            "agent": {"id": "dalgos", "role": "peer"},
        }
        with mock.patch("turnaware.adapters.channel.evaluate", _stub("SPEAK")):
            code, out, _ = self._run(payload)
        self.assertEqual(code, 0)
        directive = json.loads(out)
        self.assertEqual(directive["verdict"], "SPEAK")
        self.assertIn("run_shape", directive)
        self.assertNotIn("CC_CONNECT_SILENT_PASS", out)

    def test_cli_missing_agent_id_is_error(self):
        code, _, err = self._run({"trigger": {"content": "x", "id": "t"}})
        self.assertEqual(code, 2)
        self.assertIn("agent.id", err)


class BoundaryEnforcementTests(unittest.TestCase):
    """The core must never depend on the adapter tier (constitution III/VI)."""

    CORE_MODULES = ["core.py", "classifiers.py", "models.py", "schema.py", "errors.py", "cli.py"]

    def test_no_core_module_imports_adapters(self):
        offenders = []
        for name in self.CORE_MODULES:
            text = (SRC / name).read_text()
            if re.search(r"^\s*(from|import)\s+.*adapters", text, re.MULTILINE):
                offenders.append(name)
        self.assertEqual(offenders, [], f"core modules import the adapter tier: {offenders}")


if __name__ == "__main__":
    unittest.main()
