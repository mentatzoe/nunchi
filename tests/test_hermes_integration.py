"""Stdlib unittest suite for integrations/hermes/nunchi-gate.

Run from the worktree root with:
    python3 -m unittest tests/test_hermes_integration.py

The plugin module is loaded via importlib so it can live outside the nunchi
package without any sys.path surgery.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

# ---------------------------------------------------------------------------
# Plugin loader
# ---------------------------------------------------------------------------

_WORKTREE_ROOT = Path(__file__).resolve().parents[1]
_PLUGIN_PATH = _WORKTREE_ROOT / "integrations" / "hermes" / "nunchi-gate" / "__init__.py"


def _load_plugin() -> types.ModuleType:
    """Return a freshly loaded module object for the nunchi-gate plugin."""
    spec = importlib.util.spec_from_file_location("nunchi_gate_under_test", _PLUGIN_PATH)
    assert spec is not None and spec.loader is not None, f"Could not find plugin at {_PLUGIN_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _event(
    text: str = "hello",
    *,
    platform: str = "discord",
    chat_id: str = "1518384310321811456",
    user_name: str = "zoe",
    is_bot: bool = False,
    channel_context: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        message_id="m1",
        channel_context=channel_context,
        source=SimpleNamespace(
            platform=SimpleNamespace(value=platform),
            chat_id=chat_id,
            parent_chat_id=None,
            thread_id=None,
            user_id="42",
            user_name=user_name,
            is_bot=is_bot,
            message_id="m1",
        ),
    )


def _base_cfg(**overrides: object) -> dict:
    cfg: dict = {
        "enabled": True,
        "platforms": "discord",
        "channels": "1518384310321811456",
        "agent_id": "aleph",
        "bypass_commands": True,
        "fail_open": True,
        "log_path": "",
    }
    cfg.update(overrides)
    return cfg


def _make_completed(stdout: str = '{"verdict":"SPEAK","silent":false}', returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


# ---------------------------------------------------------------------------
# Ported tests (translated from pytest to unittest.TestCase)
# ---------------------------------------------------------------------------

class TestPayloadBuilding(unittest.TestCase):
    """_build_payload correctness."""

    def setUp(self) -> None:
        self.p = _load_plugin()

    def test_carries_addressing_signals(self) -> None:
        cfg = _base_cfg(mention_id="1496355876234199040")
        payload = self.p._build_payload(_event("ping"), cfg)
        self.assertEqual(
            payload["trigger"],
            {"content": "ping", "message_id": "m1", "author": "zoe", "author_kind": "human"},
        )
        self.assertEqual(payload["agent"], {"id": "aleph", "mention_id": "1496355876234199040"})
        self.assertNotIn("history", payload)

    def test_tags_bot_authors_as_peers(self) -> None:
        payload = self.p._build_payload(_event("hi", user_name="Station", is_bot=True), _base_cfg())
        self.assertEqual(payload["trigger"]["author_kind"], "peer_bot")


class TestChannelContextParsing(unittest.TestCase):
    """_parse_channel_context history building."""

    def setUp(self) -> None:
        self.p = _load_plugin()

    def test_builds_history(self) -> None:
        ctx = (
            "[Recent channel messages]\n"
            "[Zoe] hello all\n"
            "[Station [bot]] hi zoe\n"
            "[Aleph [bot]] earlier self turn"
        )
        history = self.p._parse_channel_context(_event(channel_context=ctx), "aleph")
        self.assertEqual(
            history,
            [
                {"content": "hello all", "author": "Zoe", "author_kind": "human"},
                {"content": "hi zoe", "author": "Station", "author_kind": "peer_bot"},
                {"content": "earlier self turn", "author": "Aleph", "author_kind": "self"},
            ],
        )

    def test_self_detection_is_case_insensitive(self) -> None:
        ctx = "[ALEPH [bot]] my message"
        history = self.p._parse_channel_context(_event(channel_context=ctx), "aleph")
        self.assertEqual(history[0]["author_kind"], "self")

    def test_empty_context_returns_empty_list(self) -> None:
        history = self.p._parse_channel_context(_event(), "aleph")
        self.assertEqual(history, [])


class TestGateRouting(unittest.TestCase):
    """_gate_event routing via mocked _nunchi_config and _run_nunchi."""

    def setUp(self) -> None:
        self.p = _load_plugin()

    def test_out_of_scope_channel_does_not_call_nunchi(self) -> None:
        called = False

        def fake_run(payload: dict, cfg: dict) -> dict:
            nonlocal called
            called = True
            return {"verdict": "PASS"}

        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=_base_cfg()):
            with unittest.mock.patch.object(self.p, "_run_nunchi", fake_run):
                result = self.p._gate_event(_event(chat_id="not-the-smoke-channel"))

        self.assertIsNone(result)
        self.assertFalse(called)

    def test_slash_command_bypasses_gate(self) -> None:
        def fake_run(payload: dict, cfg: dict) -> dict:
            raise AssertionError("slash commands must not call nunchi-channel")

        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=_base_cfg()):
            with unittest.mock.patch.object(self.p, "_run_nunchi", fake_run):
                result = self.p._gate_event(_event("/status"))

        self.assertIsNone(result)

    def test_pass_verdict_skips_hermes_reply(self) -> None:
        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=_base_cfg()):
            with unittest.mock.patch.object(
                self.p, "_run_nunchi", return_value={"verdict": "PASS", "silent": True}
            ):
                result = self.p._gate_event(_event("not for you"))

        self.assertEqual(result, {"action": "skip", "reason": "nunchi:PASS"})

    def test_speak_verdict_allows_normal_dispatch(self) -> None:
        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=_base_cfg()):
            with unittest.mock.patch.object(
                self.p, "_run_nunchi", return_value={"verdict": "SPEAK", "silent": False}
            ):
                result = self.p._gate_event(_event("aleph?"))

        self.assertIsNone(result)

    def test_error_fail_open_allows_normal_dispatch(self) -> None:
        def boom(payload: dict, cfg: dict) -> dict:
            raise RuntimeError("classifier unavailable")

        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=_base_cfg(fail_open=True)):
            with unittest.mock.patch.object(self.p, "_run_nunchi", boom):
                result = self.p._gate_event(_event("aleph?"))

        self.assertIsNone(result)

    def test_error_fail_closed_skips(self) -> None:
        def boom(payload: dict, cfg: dict) -> dict:
            raise RuntimeError("classifier unavailable")

        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=_base_cfg(fail_open=False)):
            with unittest.mock.patch.object(self.p, "_run_nunchi", boom):
                result = self.p._gate_event(_event("aleph?"))

        self.assertEqual(result, {"action": "skip", "reason": "nunchi:error"})


class TestLogging(unittest.TestCase):
    """_write_gate_log behaviour."""

    def setUp(self) -> None:
        self.p = _load_plugin()

    def test_blank_log_path_disables_logging(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            default_log = Path(tmp) / "default.jsonl"
            old_default = self.p._DEFAULT_LOG_PATH
            self.p._DEFAULT_LOG_PATH = str(default_log)
            try:
                self.p._write_gate_log({"event": "unit-test"}, {"log_path": ""})
                self.assertFalse(default_log.exists())
            finally:
                self.p._DEFAULT_LOG_PATH = old_default

    def test_false_log_path_disables_logging(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            default_log = Path(tmp) / "default.jsonl"
            old_default = self.p._DEFAULT_LOG_PATH
            self.p._DEFAULT_LOG_PATH = str(default_log)
            try:
                self.p._write_gate_log({"event": "unit-test"}, {"log_path": "false"})
                self.assertFalse(default_log.exists())
            finally:
                self.p._DEFAULT_LOG_PATH = old_default

    def test_log_path_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "gate.jsonl"
            self.p._write_gate_log({"verdict": "PASS", "ts": 1.0}, {"log_path": str(log_file)})
            self.assertTrue(log_file.exists())
            data = json.loads(log_file.read_text())
            self.assertEqual(data["verdict"], "PASS")


# ---------------------------------------------------------------------------
# New tests: legacy config fallback, model env, pinned_rules_file, wildcards
# ---------------------------------------------------------------------------

class TestLegacyConfigFallback(unittest.TestCase):
    """Legacy 'turnaware:' config block is accepted with a deprecation warning."""

    def setUp(self) -> None:
        self.p = _load_plugin()

    def test_nunchi_block_takes_precedence(self) -> None:
        cfg_data = {
            "nunchi": {"enabled": True, "channels": "abc"},
            "turnaware": {"enabled": False, "channels": "xyz"},
        }
        with unittest.mock.patch.object(self.p, "_load_config", return_value=cfg_data):
            result = self.p._nunchi_config()
        self.assertEqual(result, {"enabled": True, "channels": "abc"})

    def test_turnaware_fallback_used_when_nunchi_absent(self) -> None:
        cfg_data = {"turnaware": {"enabled": True, "channels": "legacy-chan"}}
        with unittest.mock.patch.object(self.p, "_load_config", return_value=cfg_data):
            with self.assertLogs(level="WARNING") as log_ctx:
                result = self.p._nunchi_config()
        self.assertEqual(result, {"enabled": True, "channels": "legacy-chan"})
        self.assertTrue(
            any("deprecated" in msg.lower() for msg in log_ctx.output),
            f"Expected deprecation warning in {log_ctx.output}",
        )

    def test_empty_config_returns_empty_dict(self) -> None:
        with unittest.mock.patch.object(self.p, "_load_config", return_value={}):
            result = self.p._nunchi_config()
        self.assertEqual(result, {})

    def test_legacy_fallback_gates_correctly(self) -> None:
        """End-to-end: legacy turnaware: config block actually gates events."""
        cfg_data = {
            "turnaware": {
                "enabled": True,
                "platforms": "discord",
                "channels": "1518384310321811456",
                "agent_id": "aleph",
                "bypass_commands": True,
                "fail_open": True,
                "log_path": "",
            }
        }

        def fake_load_config() -> dict:
            return cfg_data

        with unittest.mock.patch.object(self.p, "_load_config", fake_load_config):
            with unittest.mock.patch.object(
                self.p, "_run_nunchi", return_value={"verdict": "PASS", "silent": True}
            ):
                # Suppress the deprecation warning that would come from _nunchi_config
                with unittest.mock.patch.object(
                    self.p, "_load_config", fake_load_config
                ):
                    with self.assertLogs(level="WARNING"):
                        result = self.p._gate_event(_event("hello"))

        self.assertEqual(result, {"action": "skip", "reason": "nunchi:PASS"})


class TestModelEnvExport(unittest.TestCase):
    """'model' config key is exported as NUNCHI_CLASSIFIER_MODEL into subprocess env."""

    def setUp(self) -> None:
        self.p = _load_plugin()

    def test_model_key_exported(self) -> None:
        captured: dict[str, str] = {}

        def fake_run(cmd: list, **kwargs: object) -> subprocess.CompletedProcess:
            captured.update(kwargs.get("env") or {})  # type: ignore[arg-type]
            return _make_completed('{"verdict":"SPEAK","silent":false}')

        cfg = _base_cfg(model="anthropic/claude-opus-4-5")
        with unittest.mock.patch("subprocess.run", fake_run):
            self.p._run_nunchi({"trigger": {"content": "hi"}}, cfg)

        self.assertEqual(captured.get("NUNCHI_CLASSIFIER_MODEL"), "anthropic/claude-opus-4-5")

    def test_no_model_key_does_not_force_env(self) -> None:
        """When 'model' is absent, the plugin does not inject NUNCHI_CLASSIFIER_MODEL.

        We use a hermetic env (clear=True) and no-op dotenv loader so the
        real ~/.hermes/.env cannot inject the key during the assertion.
        """
        captured: dict[str, str] = {}

        def fake_run(cmd: list, **kwargs: object) -> subprocess.CompletedProcess:
            captured.update(kwargs.get("env") or {})  # type: ignore[arg-type]
            return _make_completed('{"verdict":"SPEAK","silent":false}')

        cfg = _base_cfg()  # no 'model' key
        # Hermetic: clear inherited env and stub out the .env file loader so
        # only what the plugin explicitly injects can appear in captured.
        with unittest.mock.patch.object(self.p, "_load_dotenv_into", lambda e: None):
            with unittest.mock.patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=True):
                with unittest.mock.patch("subprocess.run", fake_run):
                    self.p._run_nunchi({"trigger": {"content": "hi"}}, cfg)

        self.assertNotIn("NUNCHI_CLASSIFIER_MODEL", captured)

    def test_model_key_overrides_existing_env(self) -> None:
        """Config 'model' overrides an inherited NUNCHI_CLASSIFIER_MODEL value."""
        captured: dict[str, str] = {}

        def fake_run(cmd: list, **kwargs: object) -> subprocess.CompletedProcess:
            captured.update(kwargs.get("env") or {})  # type: ignore[arg-type]
            return _make_completed('{"verdict":"SPEAK","silent":false}')

        cfg = _base_cfg(model="openai/gpt-4o")
        with unittest.mock.patch.dict(os.environ, {"NUNCHI_CLASSIFIER_MODEL": "old-model"}):
            with unittest.mock.patch("subprocess.run", fake_run):
                self.p._run_nunchi({"trigger": {"content": "hi"}}, cfg)

        self.assertEqual(captured.get("NUNCHI_CLASSIFIER_MODEL"), "openai/gpt-4o")


class TestPinnedRulesFile(unittest.TestCase):
    """'pinned_rules_file' content is read, cached, and included in the payload."""

    def setUp(self) -> None:
        self.p = _load_plugin()
        # Clear the module-level cache between tests
        self.p._PINNED_RULES_CACHE.clear()

    def test_file_content_lands_in_payload(self) -> None:
        rules = "Rule 1: be concise.\nRule 2: stay on topic."
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(rules)
            tmp = f.name
        try:
            cfg = _base_cfg(pinned_rules_file=tmp)
            payload = self.p._build_payload(_event("ping"), cfg)
            self.assertEqual(payload["pinned_rules"], rules)
        finally:
            os.unlink(tmp)

    def test_missing_file_does_not_add_key(self) -> None:
        cfg = _base_cfg(pinned_rules_file="/nonexistent/path/rules.md")
        payload = self.p._build_payload(_event("ping"), cfg)
        self.assertNotIn("pinned_rules", payload)

    def test_mtime_cache_hit_avoids_reread(self) -> None:
        rules = "Original rules."
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(rules)
            tmp = f.name
        try:
            cfg = _base_cfg(pinned_rules_file=tmp)
            # First read
            payload1 = self.p._build_payload(_event("a"), cfg)
            self.assertEqual(payload1["pinned_rules"], rules)
            # Overwrite file but keep same path in cache — without touching mtime
            # the cache should still return the old content
            stat = os.stat(tmp)
            with open(tmp, "w") as f2:
                f2.write("New rules.")
            os.utime(tmp, (stat.st_atime, stat.st_mtime))  # restore original mtime
            payload2 = self.p._build_payload(_event("b"), cfg)
            self.assertEqual(payload2["pinned_rules"], rules, "Cache should have been hit")
        finally:
            os.unlink(tmp)

    def test_mtime_change_triggers_reread(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("v1")
            tmp = f.name
        try:
            cfg = _base_cfg(pinned_rules_file=tmp)
            # Seed cache
            self.p._build_payload(_event("a"), cfg)
            # Update file with a future mtime
            with open(tmp, "w") as f2:
                f2.write("v2")
            future = os.stat(tmp).st_mtime + 1.0
            os.utime(tmp, (future, future))
            payload = self.p._build_payload(_event("b"), cfg)
            self.assertEqual(payload["pinned_rules"], "v2")
        finally:
            os.unlink(tmp)

    def test_pinned_rules_string_takes_precedence_over_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("File rules.")
            tmp = f.name
        try:
            cfg = _base_cfg(pinned_rules="Inline rules.", pinned_rules_file=tmp)
            payload = self.p._build_payload(_event("ping"), cfg)
            self.assertEqual(payload["pinned_rules"], "Inline rules.")
        finally:
            os.unlink(tmp)


class TestPlatformChannelWildcards(unittest.TestCase):
    """platforms='*' and channels='*' wildcard gating."""

    def setUp(self) -> None:
        self.p = _load_plugin()

    def test_platforms_wildcard_gates_any_platform(self) -> None:
        with unittest.mock.patch.object(
            self.p, "_nunchi_config", return_value=_base_cfg(platforms="*", channels="*")
        ):
            with unittest.mock.patch.object(
                self.p, "_run_nunchi", return_value={"verdict": "SPEAK", "silent": False}
            ):
                result = self.p._gate_event(_event(platform="slack"))
        self.assertIsNone(result)

    def test_platforms_wildcard_gates_unknown_platform(self) -> None:
        with unittest.mock.patch.object(
            self.p, "_nunchi_config", return_value=_base_cfg(platforms="*", channels="*")
        ):
            with unittest.mock.patch.object(
                self.p, "_run_nunchi", return_value={"verdict": "PASS", "silent": True}
            ):
                result = self.p._gate_event(_event(platform="matrix"))
        self.assertEqual(result, {"action": "skip", "reason": "nunchi:PASS"})

    def test_channels_wildcard_gates_any_channel(self) -> None:
        with unittest.mock.patch.object(
            self.p, "_nunchi_config", return_value=_base_cfg(channels="*")
        ):
            with unittest.mock.patch.object(
                self.p, "_run_nunchi", return_value={"verdict": "PASS", "silent": True}
            ):
                result = self.p._gate_event(_event(chat_id="random-channel-99"))
        self.assertEqual(result, {"action": "skip", "reason": "nunchi:PASS"})

    def test_channels_not_wildcard_rejects_unknown_channel(self) -> None:
        """Without '*', an unlisted channel passes through unscoped."""
        with unittest.mock.patch.object(
            self.p, "_nunchi_config", return_value=_base_cfg(channels="specific-chan")
        ):
            called = False

            def fake_run(payload: dict, cfg: dict) -> dict:
                nonlocal called
                called = True
                return {"verdict": "PASS"}

            with unittest.mock.patch.object(self.p, "_run_nunchi", fake_run):
                result = self.p._gate_event(_event(chat_id="other-chan"))

        self.assertIsNone(result)
        self.assertFalse(called)

    def test_platforms_list_gates_matched_platform(self) -> None:
        with unittest.mock.patch.object(
            self.p,
            "_nunchi_config",
            return_value=_base_cfg(platforms=["discord", "slack"], channels="*"),
        ):
            with unittest.mock.patch.object(
                self.p, "_run_nunchi", return_value={"verdict": "SPEAK", "silent": False}
            ):
                result = self.p._gate_event(_event(platform="slack"))
        self.assertIsNone(result)

    def test_platforms_list_rejects_unmatched_platform(self) -> None:
        with unittest.mock.patch.object(
            self.p,
            "_nunchi_config",
            return_value=_base_cfg(platforms=["discord", "slack"], channels="*"),
        ):
            called = False

            def fake_run(payload: dict, cfg: dict) -> dict:
                nonlocal called
                called = True
                return {"verdict": "SPEAK"}

            with unittest.mock.patch.object(self.p, "_run_nunchi", fake_run):
                result = self.p._gate_event(_event(platform="matrix"))

        self.assertIsNone(result)
        self.assertFalse(called)


class TestRegisterHook(unittest.TestCase):
    """register() wires the pre_gateway_dispatch hook."""

    def test_register_calls_hook_registration(self) -> None:
        p = _load_plugin()
        registered: dict[str, object] = {}

        class FakeCtx:
            def register_hook(self, name: str, fn: object) -> None:
                registered[name] = fn

        p.register(FakeCtx())
        self.assertIn("pre_gateway_dispatch", registered)
        self.assertIs(registered["pre_gateway_dispatch"], p._gate_event)


# ---------------------------------------------------------------------------
# Feature 1: Per-channel configuration via resolve_channel_config()
# ---------------------------------------------------------------------------

class TestResolveChannelConfig(unittest.TestCase):
    """resolve_channel_config() pure function — legacy and map forms."""

    def setUp(self) -> None:
        self.p = _load_plugin()

    # --- Legacy form (CSV / list) stays exactly as before ---

    def test_legacy_csv_matches_listed_channel(self) -> None:
        cfg = _base_cfg(channels="1518384310321811456,other-chan")
        result = self.p.resolve_channel_config(cfg, {"1518384310321811456"})
        self.assertIs(result, cfg)

    def test_legacy_csv_no_match_returns_none(self) -> None:
        cfg = _base_cfg(channels="1518384310321811456")
        result = self.p.resolve_channel_config(cfg, {"unknown-chan"})
        self.assertIsNone(result)

    def test_legacy_list_matches_listed_channel(self) -> None:
        cfg = _base_cfg(channels=["1518384310321811456", "other-chan"])
        result = self.p.resolve_channel_config(cfg, {"other-chan"})
        self.assertIs(result, cfg)

    def test_legacy_wildcard_matches_any_channel(self) -> None:
        cfg = _base_cfg(channels="*")
        result = self.p.resolve_channel_config(cfg, {"any-random-channel"})
        self.assertIs(result, cfg)

    def test_legacy_empty_channels_returns_none(self) -> None:
        cfg = _base_cfg(channels="")
        result = self.p.resolve_channel_config(cfg, {"1518384310321811456"})
        self.assertIsNone(result)

    # --- Map form ---

    def test_map_exact_channel_match_returns_merged_config(self) -> None:
        cfg = _base_cfg(channels={"1518384310321811456": {"senders": "humans"}, "chan2": {}})
        result = self.p.resolve_channel_config(cfg, {"1518384310321811456"})
        self.assertIsNotNone(result)
        self.assertEqual(result["senders"], "humans")  # from per-channel
        self.assertEqual(result["agent_id"], "aleph")  # inherited from global

    def test_map_wildcard_used_when_no_exact_match(self) -> None:
        cfg = _base_cfg(channels={"*": {"verbosity": "minimal"}})
        result = self.p.resolve_channel_config(cfg, {"some-other-chan"})
        self.assertIsNotNone(result)
        self.assertEqual(result["verbosity"], "minimal")

    def test_map_exact_match_preferred_over_wildcard(self) -> None:
        cfg = _base_cfg(channels={
            "exact-chan": {"verbosity": "debug"},
            "*": {"verbosity": "minimal"},
        })
        result = self.p.resolve_channel_config(cfg, {"exact-chan"})
        self.assertIsNotNone(result)
        self.assertEqual(result["verbosity"], "debug")

    def test_map_no_match_no_wildcard_returns_none(self) -> None:
        cfg = _base_cfg(channels={"chan1": {}, "chan2": {}})
        result = self.p.resolve_channel_config(cfg, {"unknown-chan"})
        self.assertIsNone(result)

    def test_map_enabled_false_returns_none(self) -> None:
        cfg = _base_cfg(channels={"1518384310321811456": {"enabled": False}})
        result = self.p.resolve_channel_config(cfg, {"1518384310321811456"})
        self.assertIsNone(result)

    def test_map_enabled_true_explicitly_still_gates(self) -> None:
        cfg = _base_cfg(channels={"1518384310321811456": {"enabled": True}})
        result = self.p.resolve_channel_config(cfg, {"1518384310321811456"})
        self.assertIsNotNone(result)

    def test_map_per_channel_falls_back_to_global_for_absent_keys(self) -> None:
        """Per-channel entry without 'model' inherits the global model."""
        cfg = _base_cfg(model="global-model", channels={"chan1": {"senders": "humans"}})
        result = self.p.resolve_channel_config(cfg, {"chan1"})
        self.assertIsNotNone(result)
        self.assertEqual(result["senders"], "humans")    # per-channel
        self.assertEqual(result["model"], "global-model")  # global fallback

    def test_map_per_channel_model_overrides_global_model(self) -> None:
        cfg = _base_cfg(model="global-model", channels={"chan1": {"model": "per-chan-model"}})
        result = self.p.resolve_channel_config(cfg, {"chan1"})
        self.assertIsNotNone(result)
        self.assertEqual(result["model"], "per-chan-model")

    def test_map_per_channel_fail_open_overrides_global(self) -> None:
        cfg = _base_cfg(fail_open=True, channels={"chan1": {"fail_open": False}})
        result = self.p.resolve_channel_config(cfg, {"chan1"})
        self.assertIsNotNone(result)
        self.assertFalse(result["fail_open"])

    def test_map_disabled_channel_is_not_gated_end_to_end(self) -> None:
        """An enabled:false map entry makes _gate_event return None without classifier."""
        cfg = _base_cfg(channels={"1518384310321811456": {"enabled": False}})
        called = False

        def fake_run(payload: dict, c: dict) -> dict:
            nonlocal called
            called = True
            return {"verdict": "PASS"}

        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=cfg):
            with unittest.mock.patch.object(self.p, "_run_nunchi", fake_run):
                result = self.p._gate_event(_event())

        self.assertIsNone(result)
        self.assertFalse(called)


# ---------------------------------------------------------------------------
# Feature 2: Sender policy
# ---------------------------------------------------------------------------

class TestSenderPolicy(unittest.TestCase):
    """senders: all / humans / allowlist policy enforcement."""

    def setUp(self) -> None:
        self.p = _load_plugin()

    def test_senders_all_calls_classifier_for_bot(self) -> None:
        """Default senders=all routes bot messages through the classifier."""
        called = []

        def capture_run(payload: dict, cfg: dict) -> dict:
            called.append(1)
            return {"verdict": "SPEAK", "silent": False}

        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=_base_cfg(senders="all")):
            with unittest.mock.patch.object(self.p, "_run_nunchi", capture_run):
                result = self.p._gate_event(_event(is_bot=True))

        self.assertTrue(len(called) > 0, "classifier should have been called")
        self.assertIsNone(result)

    def test_senders_humans_drops_bot_without_subprocess_call(self) -> None:
        """senders=humans drops bot-authored messages and never invokes subprocess."""
        with unittest.mock.patch.object(
            self.p, "_nunchi_config", return_value=_base_cfg(senders="humans")
        ):
            with unittest.mock.patch("subprocess.run") as mock_subproc:
                result = self.p._gate_event(_event(is_bot=True))

        mock_subproc.assert_not_called()
        self.assertEqual(result, {"action": "skip", "reason": "nunchi:sender-policy"})

    def test_senders_humans_passes_human_to_classifier(self) -> None:
        """senders=humans allows human messages through to the classifier."""
        with unittest.mock.patch.object(
            self.p, "_nunchi_config", return_value=_base_cfg(senders="humans")
        ):
            with unittest.mock.patch.object(
                self.p, "_run_nunchi",
                return_value={"verdict": "SPEAK", "silent": False},
            ):
                result = self.p._gate_event(_event(is_bot=False))

        self.assertIsNone(result)

    def test_senders_allowlist_by_name_case_insensitive(self) -> None:
        """allowlist: user_name match is case-insensitive; matched sender reaches classifier."""
        cfg = _base_cfg(senders="allowlist", allow_from=["Zoe", "alice"])
        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=cfg):
            with unittest.mock.patch.object(
                self.p, "_run_nunchi",
                return_value={"verdict": "SPEAK", "silent": False},
            ):
                # _event default: user_name="zoe" (lowercase); "Zoe" in allow_from
                result = self.p._gate_event(_event(user_name="zoe"))

        self.assertIsNone(result)

    def test_senders_allowlist_by_user_id(self) -> None:
        """allowlist: user_id match allows the sender through."""
        cfg = _base_cfg(senders="allowlist", allow_from=["42"])  # user_id="42" in _event()
        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=cfg):
            with unittest.mock.patch.object(
                self.p, "_run_nunchi",
                return_value={"verdict": "SPEAK", "silent": False},
            ):
                result = self.p._gate_event(_event())  # default user_id="42"

        self.assertIsNone(result)

    def test_senders_allowlist_drops_unlisted_sender_without_subprocess(self) -> None:
        """allowlist: sender absent from allow_from is dropped; subprocess never called."""
        cfg = _base_cfg(senders="allowlist", allow_from=["alice", "bob"])
        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=cfg):
            with unittest.mock.patch("subprocess.run") as mock_subproc:
                # default _event: user_name="zoe", user_id="42" — neither in allowlist
                result = self.p._gate_event(_event())

        mock_subproc.assert_not_called()
        self.assertEqual(result, {"action": "skip", "reason": "nunchi:sender-policy"})

    def test_sender_policy_drop_writes_receipt_with_skip_sender_policy(self) -> None:
        """A sender-policy drop always writes a log entry with action skip-sender-policy."""
        log_entries: list[dict] = []

        def capture_log(entry: dict, cfg: dict) -> None:
            log_entries.append(entry)

        with unittest.mock.patch.object(
            self.p, "_nunchi_config", return_value=_base_cfg(senders="humans")
        ):
            with unittest.mock.patch.object(self.p, "_write_gate_log", capture_log):
                result = self.p._gate_event(_event(is_bot=True))

        self.assertEqual(result, {"action": "skip", "reason": "nunchi:sender-policy"})
        self.assertEqual(len(log_entries), 1)
        self.assertEqual(log_entries[0]["action"], "skip-sender-policy")

    def test_sender_policy_drop_receipt_has_no_verdict_field(self) -> None:
        """Sender-policy drops do not include a classifier verdict in the log."""
        log_entries: list[dict] = []

        def capture_log(entry: dict, cfg: dict) -> None:
            log_entries.append(entry)

        with unittest.mock.patch.object(
            self.p, "_nunchi_config", return_value=_base_cfg(senders="allowlist", allow_from=["bob"])
        ):
            with unittest.mock.patch.object(self.p, "_write_gate_log", capture_log):
                result = self.p._gate_event(_event(user_name="zoe"))  # not in allowlist

        self.assertEqual(result, {"action": "skip", "reason": "nunchi:sender-policy"})
        self.assertNotIn("verdict", log_entries[0])

    def test_per_channel_senders_policy_via_map_form(self) -> None:
        """Per-channel senders=humans in map form applies to that channel only."""
        cfg = _base_cfg(
            senders="all",  # global default: allow bots through
            channels={"1518384310321811456": {"senders": "humans"}},  # per-channel: humans only
        )
        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=cfg):
            with unittest.mock.patch("subprocess.run") as mock_subproc:
                result = self.p._gate_event(_event(is_bot=True))

        mock_subproc.assert_not_called()
        self.assertEqual(result, {"action": "skip", "reason": "nunchi:sender-policy"})


# ---------------------------------------------------------------------------
# Feature 2: Per-channel model exported to subprocess over global model
# ---------------------------------------------------------------------------

class TestPerChannelModel(unittest.TestCase):
    """Per-channel model key is exported to subprocess over global model."""

    def setUp(self) -> None:
        self.p = _load_plugin()

    def test_per_channel_model_overrides_global_in_subprocess_env(self) -> None:
        """Map-form per-channel model wins over global model in NUNCHI_CLASSIFIER_MODEL."""
        captured: dict[str, str] = {}

        def fake_subproc(cmd: list, **kwargs: object) -> subprocess.CompletedProcess:
            captured.update(kwargs.get("env") or {})  # type: ignore[arg-type]
            return _make_completed('{"verdict":"SPEAK","silent":false}')

        cfg = _base_cfg(
            model="global-model",
            channels={"1518384310321811456": {"model": "per-channel-model"}},
        )
        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=cfg):
            with unittest.mock.patch("subprocess.run", fake_subproc):
                self.p._gate_event(_event())

        self.assertEqual(captured.get("NUNCHI_CLASSIFIER_MODEL"), "per-channel-model")


# ---------------------------------------------------------------------------
# Feature 3: Verbosity levels + confidences
# ---------------------------------------------------------------------------

class TestVerbosityLevels(unittest.TestCase):
    """Log field selection controlled by the verbosity key."""

    def setUp(self) -> None:
        self.p = _load_plugin()

    def _run_gate_capture_log(
        self,
        verbosity: str,
        directive: dict | None = None,
    ) -> dict:
        """Run _gate_event with the given verbosity; return the captured log entry."""
        if directive is None:
            directive = {
                "verdict": "PASS",
                "silent": True,
                "classifier_model": "test-model",
                "reasons": ["r1", "r2", "r3", "r4"],
                "confidences": {"PASS": 0.85, "SPEAK": 0.10, "ACK": 0.05},
            }
        log_entries: list[dict] = []

        def capture_log(entry: dict, cfg: dict) -> None:
            log_entries.append(entry)

        cfg = _base_cfg(verbosity=verbosity)
        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=cfg):
            with unittest.mock.patch.object(self.p, "_run_nunchi", return_value=directive):
                with unittest.mock.patch.object(self.p, "_write_gate_log", capture_log):
                    self.p._gate_event(_event())

        self.assertEqual(len(log_entries), 1, f"Expected 1 log entry, got {len(log_entries)}")
        return log_entries[0]

    # --- minimal ---

    def test_minimal_contains_required_base_fields(self) -> None:
        entry = self._run_gate_capture_log("minimal")
        for field in ("ts", "platform", "channel_ids", "message_id", "verdict", "silent", "action", "elapsed_ms"):
            self.assertIn(field, entry, f"minimal log must contain '{field}'")

    def test_minimal_omits_reasons_and_confidences(self) -> None:
        entry = self._run_gate_capture_log("minimal")
        self.assertNotIn("reasons", entry)
        self.assertNotIn("confidences", entry)

    def test_minimal_omits_author_and_history_fields(self) -> None:
        entry = self._run_gate_capture_log("minimal")
        self.assertNotIn("trigger_author", entry)
        self.assertNotIn("trigger_author_kind", entry)
        self.assertNotIn("history_len", entry)
        self.assertNotIn("classifier_model", entry)

    def test_minimal_omits_payload_and_directive(self) -> None:
        entry = self._run_gate_capture_log("minimal")
        self.assertNotIn("payload", entry)
        self.assertNotIn("directive", entry)

    # --- normal (default) ---

    def test_normal_includes_confidences_from_directive(self) -> None:
        entry = self._run_gate_capture_log("normal")
        self.assertIn("confidences", entry)
        self.assertEqual(entry["confidences"], {"PASS": 0.85, "SPEAK": 0.10, "ACK": 0.05})

    def test_normal_includes_reasons_truncated_to_3(self) -> None:
        entry = self._run_gate_capture_log("normal")
        self.assertIn("reasons", entry)
        self.assertEqual(entry["reasons"], ["r1", "r2", "r3"])  # 4 in directive, capped at 3

    def test_normal_includes_trigger_author_and_history_metadata(self) -> None:
        entry = self._run_gate_capture_log("normal")
        self.assertIn("trigger_author", entry)
        self.assertIn("trigger_author_kind", entry)
        self.assertIn("history_len", entry)
        self.assertIn("classifier_model", entry)

    def test_normal_omits_payload_and_directive(self) -> None:
        entry = self._run_gate_capture_log("normal")
        self.assertNotIn("payload", entry)
        self.assertNotIn("directive", entry)

    def test_normal_omits_confidences_when_absent_from_directive(self) -> None:
        """confidences is only logged when the directive actually contains it."""
        directive = {"verdict": "SPEAK", "silent": False, "reasons": []}
        entry = self._run_gate_capture_log("normal", directive)
        self.assertNotIn("confidences", entry)

    def test_default_verbosity_is_normal(self) -> None:
        """When verbosity is unset, the log matches normal behaviour."""
        log_entries: list[dict] = []

        def capture_log(entry: dict, cfg: dict) -> None:
            log_entries.append(entry)

        # _base_cfg has no verbosity key → defaults to "normal"
        cfg = _base_cfg()
        directive = {
            "verdict": "PASS",
            "silent": True,
            "confidences": {"PASS": 0.9},
        }
        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=cfg):
            with unittest.mock.patch.object(self.p, "_run_nunchi", return_value=directive):
                with unittest.mock.patch.object(self.p, "_write_gate_log", capture_log):
                    self.p._gate_event(_event())

        self.assertEqual(len(log_entries), 1)
        self.assertIn("confidences", log_entries[0])

    # --- debug ---

    def test_debug_includes_payload_sent_to_nunchi(self) -> None:
        entry = self._run_gate_capture_log("debug")
        self.assertIn("payload", entry)
        self.assertIsInstance(entry["payload"], dict)
        self.assertIn("trigger", entry["payload"])

    def test_debug_includes_complete_directive(self) -> None:
        entry = self._run_gate_capture_log("debug")
        self.assertIn("directive", entry)
        self.assertIn("verdict", entry["directive"])

    def test_debug_includes_confidences(self) -> None:
        entry = self._run_gate_capture_log("debug")
        self.assertIn("confidences", entry)

    def test_debug_includes_trigger_author_and_history_metadata(self) -> None:
        entry = self._run_gate_capture_log("debug")
        self.assertIn("trigger_author", entry)
        self.assertIn("history_len", entry)

    # --- per-channel verbosity via map form ---

    def test_per_channel_verbosity_via_map_form(self) -> None:
        """verbosity set in per-channel map entry controls the log for that channel."""
        log_entries: list[dict] = []

        def capture_log(entry: dict, cfg: dict) -> None:
            log_entries.append(entry)

        cfg = _base_cfg(
            verbosity="debug",  # global says debug
            channels={"1518384310321811456": {"verbosity": "minimal"}},  # per-channel says minimal
        )
        directive = {
            "verdict": "PASS",
            "silent": True,
            "confidences": {"PASS": 0.9},
        }
        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=cfg):
            with unittest.mock.patch.object(self.p, "_run_nunchi", return_value=directive):
                with unittest.mock.patch.object(self.p, "_write_gate_log", capture_log):
                    self.p._gate_event(_event())

        self.assertEqual(len(log_entries), 1)
        entry = log_entries[0]
        # minimal: must not have reasons/confidences/payload/directive
        self.assertNotIn("confidences", entry)
        self.assertNotIn("reasons", entry)
        self.assertNotIn("payload", entry)


if __name__ == "__main__":
    unittest.main()
