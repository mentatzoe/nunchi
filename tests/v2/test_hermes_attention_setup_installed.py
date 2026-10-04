"""Explicit dashboard setup -> stock PluginLlm -> native normal-turn probes.

Requires the unchanged t_44229f49 normal-turn harness beside this file and an
installed wheel, not the Nunchi source tree. Network boundaries are loopback
model/Discord doubles, not live-provider or live-room acceptance.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

_REQUIRED = os.environ.get("NUNCHI_REQUIRE_HERMES_NORMAL_TURN") == "1"
if _REQUIRED:
    from tests.v2.test_hermes_normal_turn import _Base, _deliver_and_settle
    from tests.v2 import hermes_normal_turn_support as sup
else:
    _Base = unittest.TestCase


@unittest.skipUnless(_REQUIRED, "requires installed stock Hermes normal-turn harness")
class InstalledAttentionSetupTests(_Base):
    enable_nunchi = True
    trust_nunchi_llm = False

    def _load_nunchi(self, *, timeout_seconds: float) -> None:
        self._save_dashboard_configuration(timeout_seconds=timeout_seconds)
        self.loaded = sup.load_nunchi_via_plugin_manager()
        self.assertIsNone(self.loaded["state"]["error"], self.loaded["state"])

    def _save_dashboard_configuration(self, *, timeout_seconds: float) -> None:
        from nunchi.integrations.hermes_dashboard_store import (
            default_config_paths, read_dashboard_snapshot, write_config_document,
        )
        from nunchi.integrations.hermes_dashboard_api import _config_response
        yaml = sup.host_yaml()

        self.assertNotIn("entries", yaml.safe_load((self.home / "config.yaml").read_text())["plugins"])
        # Use the existing fixture only to obtain the closed room document;
        # the real profile starts without fixture-written trust or room files.
        with tempfile.TemporaryDirectory() as temporary:
            config, _ = sup.write_nunchi_config(
                Path(temporary), room_id=str(self.room), bot_user_id=999,
                attention_model="attention-probe-model", timeout_seconds=timeout_seconds,
            )
            document = json.loads(config.read_text())
        document["state_directory"] = str(default_config_paths("default", hermes_home=self.home).state_directory)
        env = {"HERMES_HOME": str(self.home)}
        before = read_dashboard_snapshot("default", environ=env)
        saved = write_config_document("default", document=document,
                                      expected_revision=before.revision, environ=env)
        response = _config_response("default", environ=env)
        self.assertTrue(response["attention_trust"]["ready"])
        self.assertFalse(response["attention_trust"]["runtime_verified"])
        self.assertEqual("attention-probe-model", saved.config.rooms[0].attention_model.model)

    def test_setup_attention_wakes_and_native_participant_delivers(self):
        self.server.script(self.attend("WAKE"), {"content": "setup-attention-ok"})
        self.assertTrue(_deliver_and_settle(self.host, self.human("hello")))
        calls = self.attention_calls()
        self.assertEqual(1, len(calls))
        self.assertEqual("attention-probe-model", calls[0]["model"])
        self.assertEqual(1, len(self.model_turns()))
        self.assertEqual("probe-model", self.model_turns()[0]["model"])
        self.assertIn("setup-attention-ok", self.deliveries())
        attention = [r["body"] for r in self.receipts() if r.get("stage") == "attention"][-1]
        self.assertNotIn("error", attention)
        self.assertEqual("WAKE", attention["classifier_disposition"])
        self.assertEqual("custom", attention["classifier"]["provider"])
        self.assertEqual("attention-probe-model", attention["classifier"]["model"])
        self.assertTrue(any(r.get("stage") == "transport" and r["body"].get("delivery") == "sent" for r in self.receipts()))

    def test_setup_attention_suppresses_without_error_fallback_or_participant(self):
        self.attend("SUPPRESS")
        self.assertTrue(_deliver_and_settle(self.host, self.human("quiet room")))
        self.assertEqual(1, len(self.attention_calls()))
        self.assertEqual([], self.model_turns())
        self.assertEqual([], self.deliveries())
        attention = [r["body"] for r in self.receipts() if r.get("stage") == "attention"][-1]
        self.assertEqual("SUPPRESS", attention["effective_disposition"])
        self.assertNotIn("error", attention)

    def test_revoked_stock_trust_is_not_regranted_by_runtime(self):
        path = self.home / "config.yaml"
        document = json.loads(path.read_text())
        document["plugins"]["entries"]["nunchi"]["llm"]["allow_model_override"] = False
        raw = json.dumps(document).encode()
        path.write_bytes(raw)
        self.server.script({"content": "explicit-error-fallback"})
        self.assertTrue(_deliver_and_settle(self.host, self.human("hello")))
        self.assertEqual([], self.attention_calls())
        attention = [r["body"] for r in self.receipts() if r.get("stage") == "attention"][-1]
        self.assertEqual("host-permission-denied", attention["error"]["code"])
        self.assertIn("allow_model_override", attention["error"]["detail"])
        self.assertNotIn("classifier_disposition", attention)
        # Stock runner construction normalizes YAML/adds its own defaults;
        # the invariant is that Nunchi never changes/regrants revoked trust.
        yaml = sup.host_yaml()
        after = yaml.safe_load(path.read_text())
        self.assertEqual(document["plugins"]["entries"]["nunchi"]["llm"],
                         after["plugins"]["entries"]["nunchi"]["llm"])


@unittest.skipUnless(_REQUIRED, "requires installed stock Hermes normal-turn harness")
class InstalledAttentionServiceTests(_Base):
    """Stock attention service proof independent of plugin-loader health.

    This is not a substitute for the separate native entry-point probe.
    Only the test constructs the stock service; production uses ctx.llm.
    """

    def test_default_deny_then_operator_save_then_exact_model_then_revoke(self):
        from agent.plugin_llm import PluginLlm
        from nunchi.attention import (
            AttentionModelSelection, HostAttentionPermissionError,
            HostStructuredAttentionModel,
        )
        yaml = sup.host_yaml()

        model = HostStructuredAttentionModel(
            PluginLlm(plugin_id="nunchi"),
            AttentionModelSelection(provider="custom", model="attention-probe-model"),
        )
        arguments = {"instructions": "Judge SUPPRESS, ACK, WAKE or DEFER.",
                     "projection": {"event_id": "test-event"}, "timeout_seconds": 10}
        with self.assertRaises(HostAttentionPermissionError):
            model.judge(**arguments)
        self.assertEqual([], self.attention_calls())
        InstalledAttentionSetupTests._save_dashboard_configuration(self, timeout_seconds=20)
        self.server.script({"content": sup.attention_judgment("SUPPRESS", "test-event")})
        result = model.judge(**arguments)
        self.assertEqual("SUPPRESS", result["disposition"])
        self.assertEqual(1, len(self.attention_calls()))
        self.assertEqual("attention-probe-model", self.attention_calls()[0]["model"])
        path = self.home / "config.yaml"
        document = yaml.safe_load(path.read_text())
        document["plugins"]["entries"]["nunchi"]["llm"]["allow_provider_override"] = False
        raw = json.dumps(document).encode()
        path.write_bytes(raw)
        with self.assertRaises(HostAttentionPermissionError):
            model.judge(**arguments)
        self.assertEqual(1, len(self.attention_calls()))
        self.assertEqual(raw, path.read_bytes())
