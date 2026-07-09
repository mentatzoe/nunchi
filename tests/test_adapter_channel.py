"""Tests for the channel-local admission adapter.

Mapping and routing are tested offline with a stub classifier (the gate accepts
an injected ``evaluate_fn``); the real core path is exercised via the
deterministic fixture provider (`NUNCHI_CLASSIFIER_TEST_RESULT`). Nothing
here touches a live provider.
"""

import io
import json
import os
import pathlib
import re
import unittest
from unittest import mock

from nunchi.adapters import channel
from nunchi.adapters.channel import (
    SILENT_PASS_SENTINEL,
    ChannelMessage,
    build_request,
    gate,
)
from nunchi.errors import NunchiError, ValidationError

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "nunchi"


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

    def test_agent_aliases_threaded_into_envelope(self):
        # One bot carries several identities (display name, secondary handle,
        # mention snowflake); the envelope must carry the full bundle.
        req = build_request(
            {"content": "Vigil, take a look", "id": "t-1"}, [],
            agent_id="vigil", agent_mention_id="111",
            agent_aliases=["Vigil", "Codex", "222222222222222222"],
        )
        self.assertEqual(
            req["agent"],
            {"id": "vigil", "mention_id": "111",
             "aliases": ["Vigil", "Codex", "222222222222222222"]},
        )

    def test_agent_aliases_deduped_against_id_and_mention_id(self):
        req = build_request(
            {"content": "ping", "id": "t-1"}, [],
            agent_id="vigil", agent_mention_id="111",
            agent_aliases=["vigil", "111", "Vigil", "Vigil", "  ", "Codex"],
        )
        self.assertEqual(req["agent"]["aliases"], ["Vigil", "Codex"])

    def test_no_aliases_envelope_identical_to_pre_alias_shape(self):
        # Backward compat: the alias knob absent (or empty) must produce
        # exactly the request the adapter built before aliases existed.
        baseline = build_request(
            {"content": "hi <@123>", "id": "t-1"}, [],
            agent_id="dalgos", agent_mention_id="999",
        )
        for absent in (None, []):
            with self.subTest(agent_aliases=absent):
                req = build_request(
                    {"content": "hi <@123>", "id": "t-1"}, [],
                    agent_id="dalgos", agent_mention_id="999", agent_aliases=absent,
                )
                self.assertEqual(req, baseline)
        self.assertEqual(baseline["agent"], {"id": "dalgos", "mention_id": "999"})
        self.assertNotIn("aliases", baseline["agent"])

    def test_non_string_alias_rejected(self):
        with self.assertRaises(ValidationError):
            build_request(
                {"content": "ping", "id": "t-1"}, [],
                agent_id="vigil", agent_aliases=["Vigil", 42],
            )
        with self.assertRaises(ValidationError):
            build_request(
                {"content": "ping", "id": "t-1"}, [],
                agent_id="vigil", agent_aliases="Vigil,Codex",
            )

    def test_self_role_inferred_when_author_matches_alias(self):
        # A relay may report the agent's own line under its display name.
        req = build_request(
            {"content": "ping", "id": "t-1"},
            [{"content": "my earlier turn", "author": "Aether", "id": "h-1"}],
            agent_id="vigil", agent_aliases=["Aether"],
        )
        self.assertEqual(req["context"][0]["type"], "self")

    def test_parse_alias_csv_cleans_and_dedupes(self):
        self.assertEqual(
            channel.parse_alias_csv(" Vigil, Codex ,,Vigil , 222 "),
            ["Vigil", "Codex", "222"],
        )
        self.assertEqual(channel.parse_alias_csv(None), [])
        self.assertEqual(channel.parse_alias_csv(""), [])


class GateRoutingTests(unittest.TestCase):
    def test_pass_is_silent_transport_neutral(self):
        r = gate({"content": "peer chatter", "id": "t-1"}, [], agent_id="d",
                 evaluate_fn=_stub("PASS"))
        self.assertTrue(r.silent)
        self.assertEqual(r.verdict, "PASS")
        # cc-connect helper is opt-in, not the primary signal
        self.assertEqual(r.cc_connect_sentinel(), SILENT_PASS_SENTINEL)

    def test_speak_is_not_silent(self):
        r = gate({"content": "implement X", "id": "t-1"}, [], agent_id="d",
                 evaluate_fn=_stub("SPEAK"))
        self.assertFalse(r.silent)
        self.assertEqual(r.cc_connect_sentinel(), "")
        self.assertIn("participant turn", r.run_shape)

    def test_silent_token_is_generic(self):
        # Any transport supplies its own token; cc-connect is just one value.
        r = gate({"content": "x", "id": "t"}, [], agent_id="d", evaluate_fn=_stub("PASS"))
        self.assertEqual(r.silent_token("SLACK_SUPPRESS"), "SLACK_SUPPRESS")
        self.assertEqual(r.cc_connect_sentinel(), SILENT_PASS_SENTINEL)
        s = gate({"content": "x", "id": "t"}, [], agent_id="d", evaluate_fn=_stub("SPEAK"))
        self.assertEqual(s.silent_token("SLACK_SUPPRESS"), "")

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
        raise NunchiError("provider down")

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
        self.assertEqual(r.cc_connect_sentinel(), SILENT_PASS_SENTINEL)
        self.assertTrue(r.degraded)

    def test_fail_raise_propagates(self):
        with self.assertRaises(NunchiError):
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
        return mock.patch.dict(
            os.environ,
            {
                "NUNCHI_CLASSIFIER_TEST_RESULT": json.dumps(payload),
                "NUNCHI_CLASSIFIER_MODEL": "nunchi-test-fixture-provider",
            },
        )

    def test_real_gate_pass_is_silent(self):
        with self._inject("PASS", checked=["trigger:t-1"]):
            r = gate({"content": "already handled", "id": "t-1"}, [], agent_id="dalgos")
        self.assertTrue(r.silent)
        self.assertEqual(r.cc_connect_sentinel(), SILENT_PASS_SENTINEL)
        self.assertEqual(r.classifier_model, "nunchi-test-fixture-provider")

    def test_real_gate_speak_routes_through(self):
        with self._inject("SPEAK", checked=["trigger:t-1"]):
            r = gate({"content": "dalgos, implement the MVP", "id": "t-1"}, [], agent_id="dalgos")
        self.assertEqual(r.verdict, "SPEAK")
        self.assertFalse(r.silent)


class CliTests(unittest.TestCase):
    def _run(self, payload, argv=None):
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), \
                mock.patch("sys.stdout", buf_out), mock.patch("sys.stderr", buf_err):
            code = channel.main(argv or [])
        return code, buf_out.getvalue(), buf_err.getvalue()

    def test_cli_default_pass_is_transport_neutral_json(self):
        # Default output carries no cc-connect coupling: a JSON directive the
        # host acts on via silent/verdict.
        payload = {"trigger": {"content": "peer noise", "id": "t-1"},
                   "history": [], "agent": {"id": "dalgos"}, "fail_policy": "open"}
        with mock.patch("nunchi.adapters.channel.evaluate", _stub("PASS")):
            code, out, _ = self._run(payload)
        self.assertEqual(code, 0)
        directive = json.loads(out)
        self.assertEqual(directive["verdict"], "PASS")
        self.assertTrue(directive["silent"])
        self.assertNotIn("CC_CONNECT_SILENT_PASS", out)

    def test_cli_cc_connect_format_prints_sentinel_on_pass(self):
        payload = {"trigger": {"content": "peer noise", "id": "t-1"},
                   "history": [], "agent": {"id": "dalgos"}}
        with mock.patch("nunchi.adapters.channel.evaluate", _stub("PASS")):
            code, out, _ = self._run(payload, argv=["--format", "cc-connect"])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), SILENT_PASS_SENTINEL)

    def test_cli_custom_silent_token_on_pass(self):
        # Generic: any platform's suppression token, no cc-connect involved.
        payload = {"trigger": {"content": "peer noise", "id": "t-1"},
                   "history": [], "agent": {"id": "dalgos"}}
        with mock.patch("nunchi.adapters.channel.evaluate", _stub("PASS")):
            code, out, _ = self._run(payload, argv=["--silent-token", "<<HUSH>>"])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "<<HUSH>>")

    def test_cli_silent_token_ignored_when_not_silent(self):
        payload = {"trigger": {"content": "implement X", "id": "t-1"},
                   "agent": {"id": "dalgos"}}
        with mock.patch("nunchi.adapters.channel.evaluate", _stub("SPEAK")):
            code, out, _ = self._run(payload, argv=["--silent-token", "<<HUSH>>"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["verdict"], "SPEAK")

    def test_cli_speak_prints_json_directive(self):
        payload = {
            "trigger": {"content": "implement X", "id": "t-1"},
            "agent": {"id": "dalgos", "role": "peer"},
        }
        with mock.patch("nunchi.adapters.channel.evaluate", _stub("SPEAK")):
            code, out, _ = self._run(payload)
        self.assertEqual(code, 0)
        directive = json.loads(out)
        self.assertEqual(directive["verdict"], "SPEAK")
        self.assertFalse(directive["silent"])
        self.assertIn("run_shape", directive)
        self.assertNotIn("CC_CONNECT_SILENT_PASS", out)

    def test_cli_missing_agent_id_is_error(self):
        code, _, err = self._run({"trigger": {"content": "x", "id": "t"}})
        self.assertEqual(code, 2)
        self.assertIn("agent.id", err)

    def test_cli_agent_aliases_reach_the_core_request(self):
        captured = {}

        def _capture(request):
            captured.update(request)
            return _stub("SPEAK")(request)

        payload = {
            "trigger": {"content": "Codex, status?", "id": "t-1"},
            "agent": {"id": "vigil", "mention_id": "111", "aliases": ["Vigil", "Codex"]},
        }
        with mock.patch("nunchi.adapters.channel.evaluate", _capture):
            code, out, _ = self._run(payload)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["verdict"], "SPEAK")
        self.assertEqual(captured["agent"]["aliases"], ["Vigil", "Codex"])

    def test_cli_invalid_aliases_is_error(self):
        payload = {
            "trigger": {"content": "x", "id": "t"},
            "agent": {"id": "vigil", "aliases": "Vigil,Codex"},
        }
        code, _, err = self._run(payload)
        self.assertEqual(code, 2)
        self.assertIn("aliases", err)


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
