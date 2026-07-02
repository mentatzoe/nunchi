"""Stdlib unittest suite for integrations/hermes/nunchi-gate/state.py.

Run from the worktree root with:
    python3 -m unittest tests/test_hermes_state.py

state.py is loaded via importlib so it can live outside a package without
any sys.path surgery.
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import time
import types
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------

_WORKTREE_ROOT = Path(__file__).resolve().parents[1]
_STATE_PATH = _WORKTREE_ROOT / "integrations" / "hermes" / "nunchi-gate" / "state.py"


def _load_state_module() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("nunchi_gate_state_under_test", _STATE_PATH)
    assert spec is not None and spec.loader is not None, f"Could not find state.py at {_STATE_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# ---------------------------------------------------------------------------
# TestFilterOverridable — whitelist enforcement
# ---------------------------------------------------------------------------

class TestFilterOverridable(unittest.TestCase):
    """filter_overridable drops keys outside OVERRIDABLE_KEYS."""

    def setUp(self) -> None:
        self.m = _load_state_module()

    def test_keeps_overridable_keys(self) -> None:
        result = self.m.filter_overridable({
            "enabled": True,
            "senders": "humans",
            "allow_from": ["alice"],
            "verbosity": "debug",
            "fail_open": False,
            "model": "test-model",
            "pinned_rules_file": "/tmp/rules.md",
        })
        self.assertEqual(set(result.keys()), set(self.m.OVERRIDABLE_KEYS))

    def test_drops_binary(self) -> None:
        result = self.m.filter_overridable({"binary": "/evil/path", "enabled": True})
        self.assertNotIn("binary", result)
        self.assertIn("enabled", result)

    def test_drops_agent_id(self) -> None:
        result = self.m.filter_overridable({"agent_id": "evil-bot", "senders": "all"})
        self.assertNotIn("agent_id", result)

    def test_drops_mention_id(self) -> None:
        result = self.m.filter_overridable({"mention_id": "12345", "verbosity": "minimal"})
        self.assertNotIn("mention_id", result)

    def test_drops_timeout_seconds(self) -> None:
        result = self.m.filter_overridable({"timeout_seconds": 0.001})
        self.assertNotIn("timeout_seconds", result)

    def test_drops_log_path(self) -> None:
        result = self.m.filter_overridable({"log_path": "/evil/log.jsonl"})
        self.assertNotIn("log_path", result)

    def test_drops_state_path(self) -> None:
        result = self.m.filter_overridable({"state_path": "/evil/state.json"})
        self.assertNotIn("state_path", result)

    def test_empty_input_returns_empty(self) -> None:
        self.assertEqual(self.m.filter_overridable({}), {})

    def test_returns_shallow_copy(self) -> None:
        d = {"enabled": True}
        result = self.m.filter_overridable(d)
        result["enabled"] = False
        self.assertTrue(d["enabled"], "original dict must not be mutated")


# ---------------------------------------------------------------------------
# TestLoadState — file loading and mtime cache
# ---------------------------------------------------------------------------

class TestLoadState(unittest.TestCase):
    """load_state: absent/malformed files return {} and don't crash; cache works."""

    def setUp(self) -> None:
        self.m = _load_state_module()
        # Clear module-level cache between tests.
        self.m._STATE_CACHE.clear()

    def test_absent_file_returns_empty(self) -> None:
        p = Path("/nonexistent/never-created.json")
        result = self.m.load_state(p)
        self.assertEqual(result, {})

    def test_empty_file_returns_empty(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("")
            tmp = f.name
        try:
            result = self.m.load_state(Path(tmp))
            self.assertEqual(result, {})
        finally:
            os.unlink(tmp)

    def test_malformed_json_returns_empty_no_crash(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{this is not valid json")
            tmp = f.name
        try:
            result = self.m.load_state(Path(tmp))
            self.assertEqual(result, {})
        finally:
            os.unlink(tmp)

    def test_non_object_json_returns_empty(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([1, 2, 3], f)
            tmp = f.name
        try:
            result = self.m.load_state(Path(tmp))
            self.assertEqual(result, {})
        finally:
            os.unlink(tmp)

    def test_valid_state_file_is_loaded(self) -> None:
        state = {"global": {"enabled": True}, "channels": {}, "updated_at": "2026-01-01"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(state, f)
            tmp = f.name
        try:
            result = self.m.load_state(Path(tmp))
            self.assertEqual(result["global"], {"enabled": True})
        finally:
            os.unlink(tmp)

    def test_mtime_cache_hit_avoids_reread(self) -> None:
        """Second load with same mtime returns cached value."""
        state = {"global": {"senders": "all"}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(state, f)
            tmp = f.name
        try:
            p = Path(tmp)
            # First read
            r1 = self.m.load_state(p)
            self.assertEqual(r1["global"]["senders"], "all")

            # Overwrite without changing mtime — cache should return old value.
            stat = os.stat(tmp)
            with open(tmp, "w") as f2:
                json.dump({"global": {"senders": "humans"}}, f2)
            os.utime(tmp, (stat.st_atime, stat.st_mtime))  # restore mtime
            r2 = self.m.load_state(p)
            self.assertEqual(r2["global"]["senders"], "all", "cache should hit")
        finally:
            os.unlink(tmp)

    def test_mtime_change_invalidates_cache(self) -> None:
        """New mtime triggers a fresh read."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"global": {"senders": "all"}}, f)
            tmp = f.name
        try:
            p = Path(tmp)
            self.m.load_state(p)  # seed cache
            with open(tmp, "w") as f2:
                json.dump({"global": {"senders": "allowlist"}}, f2)
            future = os.stat(tmp).st_mtime + 1.0
            os.utime(tmp, (future, future))
            r = self.m.load_state(p)
            self.assertEqual(r["global"]["senders"], "allowlist")
        finally:
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# TestSaveState — atomic write + cache invalidation
# ---------------------------------------------------------------------------

class TestSaveState(unittest.TestCase):
    """save_state: stamps timestamps, writes atomically, invalidates cache."""

    def setUp(self) -> None:
        self.m = _load_state_module()
        self.m._STATE_CACHE.clear()

    def test_save_creates_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "state.json"
            self.m.save_state(p, {"global": {"enabled": True}}, updated_by="slash")
            self.assertTrue(p.exists())
            data = json.loads(p.read_text())
            self.assertEqual(data["global"]["enabled"], True)

    def test_save_stamps_updated_at_and_updated_by(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "state.json"
            self.m.save_state(p, {}, updated_by="dashboard")
            data = json.loads(p.read_text())
            self.assertIn("updated_at", data)
            self.assertEqual(data["updated_by"], "dashboard")

    def test_save_invalidates_mtime_cache(self) -> None:
        """After save_state, the next load_state reads from disk, not cache."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "state.json"
            # Seed cache with old content.
            self.m.save_state(p, {"global": {"senders": "all"}}, updated_by="slash")
            r1 = self.m.load_state(p)
            self.assertEqual(r1["global"]["senders"], "all")

            # Save new content.
            self.m.save_state(p, {"global": {"senders": "humans"}}, updated_by="slash")
            r2 = self.m.load_state(p)
            self.assertEqual(r2["global"]["senders"], "humans")

    def test_atomic_save_uses_tmp_then_rename(self) -> None:
        """No partial files left after save (we verify via no leftover .tmp files)."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "state.json"
            self.m.save_state(p, {"global": {}}, updated_by="slash")
            tmp_files = list(Path(tmp).glob(".nunchi-state-*.tmp"))
            self.assertEqual(tmp_files, [], "no temp files should remain after successful save")

    def test_save_creates_parent_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "a" / "b" / "state.json"
            self.m.save_state(nested, {}, updated_by="slash")
            self.assertTrue(nested.exists())


# ---------------------------------------------------------------------------
# TestMergeEffective — layering + state-introduced channels
# ---------------------------------------------------------------------------

def _passthrough(cfg, cids):
    """Simple resolve_fn that always returns cfg (every channel matches)."""
    return cfg


def _none_resolver(cfg, cids):
    """Resolve_fn that returns None (channel not configured in config.yaml)."""
    return None


class TestMergeEffective(unittest.TestCase):
    """merge_effective: layering precedence and state-introduced channels."""

    def setUp(self) -> None:
        self.m = _load_state_module()

    def _merge(self, baseline, state, cids, resolve_fn=_passthrough):
        return self.m.merge_effective(
            baseline, state, cids,
            _resolve_channel_config=resolve_fn,
        )

    # --- Basic layering: baseline < global < channel ---

    def test_empty_state_returns_resolve_fn_result(self) -> None:
        baseline = {"senders": "all", "verbosity": "normal"}
        result = self._merge(baseline, {}, {"chan1"})
        self.assertEqual(result["senders"], "all")

    def test_global_overlay_overrides_baseline(self) -> None:
        baseline = {"senders": "all", "verbosity": "normal"}
        state = {"global": {"senders": "humans"}}
        result = self._merge(baseline, state, {"chan1"})
        self.assertEqual(result["senders"], "humans")
        self.assertEqual(result["verbosity"], "normal")  # baseline value unchanged

    def test_channel_overlay_overrides_global(self) -> None:
        baseline = {"senders": "all", "verbosity": "normal"}
        state = {
            "global": {"senders": "humans", "verbosity": "minimal"},
            "channels": {"chan1": {"verbosity": "debug"}},
        }
        result = self._merge(baseline, state, {"chan1"})
        self.assertEqual(result["senders"], "humans")   # from global
        self.assertEqual(result["verbosity"], "debug")  # from channel — wins over global

    def test_channel_overlay_overrides_baseline(self) -> None:
        baseline = {"senders": "all"}
        state = {"channels": {"chan1": {"senders": "allowlist"}}}
        result = self._merge(baseline, state, {"chan1"})
        self.assertEqual(result["senders"], "allowlist")

    # --- Whitelist enforcement in state overlays ---

    def test_global_overlay_whitelist_enforced(self) -> None:
        """Non-overridable keys in state["global"] are silently dropped."""
        baseline = {"binary": "/usr/bin/nunchi-channel", "agent_id": "bot"}
        state = {"global": {"binary": "/evil/binary", "agent_id": "imposter", "senders": "all"}}
        result = self._merge(baseline, state, {"chan1"})
        self.assertEqual(result.get("binary"), "/usr/bin/nunchi-channel")
        self.assertEqual(result.get("agent_id"), "bot")
        self.assertEqual(result.get("senders"), "all")

    def test_channel_overlay_whitelist_enforced(self) -> None:
        baseline = {"log_path": "/safe/log.jsonl"}
        state = {"channels": {"chan1": {"log_path": "/evil/log.jsonl", "enabled": True}}}
        result = self._merge(baseline, state, {"chan1"})
        self.assertEqual(result.get("log_path"), "/safe/log.jsonl")
        self.assertTrue(result.get("enabled"))

    # --- resolve_fn returning None ---

    def test_resolve_fn_none_and_no_state_entry_returns_none(self) -> None:
        result = self._merge({"senders": "all"}, {}, {"chan1"}, resolve_fn=_none_resolver)
        self.assertIsNone(result)

    # --- State-introduced channels ---

    def test_state_introduced_channel_with_enabled_true(self) -> None:
        """Channel not in config.yaml but state["channels"][id] with enabled:true is gated."""
        baseline = {"senders": "all", "verbosity": "normal"}
        state = {"channels": {"new-chan": {"enabled": True, "verbosity": "debug"}}}
        result = self._merge(baseline, state, {"new-chan"}, resolve_fn=_none_resolver)
        self.assertIsNotNone(result)
        self.assertTrue(result["enabled"])
        self.assertEqual(result["verbosity"], "debug")

    def test_state_introduced_channel_inherits_global_overrides(self) -> None:
        """State-introduced channel includes global overrides from the patched baseline."""
        baseline = {"senders": "all"}
        state = {
            "global": {"senders": "humans"},
            "channels": {"new-chan": {"enabled": True}},
        }
        result = self._merge(baseline, state, {"new-chan"}, resolve_fn=_none_resolver)
        self.assertIsNotNone(result)
        self.assertEqual(result["senders"], "humans")  # from global

    def test_state_entry_without_explicit_enabled_true_does_not_introduce(self) -> None:
        """An entry in state["channels"] without enabled:true does NOT gate when baseline=None."""
        baseline = {}
        state = {"channels": {"chan1": {"senders": "humans"}}}
        result = self._merge(baseline, state, {"chan1"}, resolve_fn=_none_resolver)
        self.assertIsNone(result)

    # --- State-disabled channels ---

    def test_state_enabled_false_suppresses_baseline_channel(self) -> None:
        """state["channels"][id] with enabled:false disables a baseline-gated channel."""
        baseline = {"senders": "all"}
        state = {"channels": {"chan1": {"enabled": False}}}
        # _passthrough resolver returns cfg (baseline matches)
        result = self._merge(baseline, state, {"chan1"}, resolve_fn=_passthrough)
        self.assertIsNone(result)

    def test_state_enabled_true_does_not_suppress_baseline_channel(self) -> None:
        baseline = {"senders": "all"}
        state = {"channels": {"chan1": {"enabled": True}}}
        result = self._merge(baseline, state, {"chan1"}, resolve_fn=_passthrough)
        self.assertIsNotNone(result)

    def test_no_state_entry_for_channel_returns_resolve_fn_result(self) -> None:
        """When state has no entry for the channel, resolve_fn result flows through."""
        baseline = {"senders": "all"}
        state = {"channels": {"other-chan": {"enabled": True, "senders": "humans"}}}
        result = self._merge(baseline, state, {"chan1"}, resolve_fn=_passthrough)
        # chan1 has no state entry → resolve_fn result used as-is
        self.assertEqual(result, baseline)

    # --- No _resolve_channel_config (isolated test mode) ---

    def test_no_resolve_fn_uses_patched_baseline_directly(self) -> None:
        baseline = {"senders": "all"}
        state = {"global": {"senders": "humans"}}
        result = self.m.merge_effective(baseline, state, {"chan1"})
        self.assertEqual(result["senders"], "humans")

    def test_no_resolve_fn_none_if_no_match_skipped(self) -> None:
        """Without a resolve_fn, the global-patched baseline is always returned (no None)."""
        baseline = {"senders": "all"}
        result = self.m.merge_effective(baseline, {}, {"chan1"})
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
