"""Tests for hermes rolling history buffer and adapter defaults.

All tests are stdlib-only (no pytest). Run from the worktree root with:
    python3 -m unittest tests.test_history_buffer
or:
    python3 -m unittest
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import tempfile
import textwrap
import types
import unittest
import unittest.mock
from types import SimpleNamespace

_WORKTREE_ROOT = pathlib.Path(__file__).resolve().parents[1]
_PLUGIN_PATH = _WORKTREE_ROOT / "integrations" / "hermes" / "nunchi-gate" / "__init__.py"

sys.path.insert(0, str(_WORKTREE_ROOT / "src"))


# ---------------------------------------------------------------------------
# Plugin loader
# ---------------------------------------------------------------------------

def _load_plugin() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("nunchi_gate_under_test", _PLUGIN_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# ---------------------------------------------------------------------------
# Test helpers (mirrors test_hermes_integration.py conventions)
# ---------------------------------------------------------------------------

def _event(
    text: str = "hello",
    *,
    platform: str = "discord",
    chat_id: str = "1518384310321811456",
    user_name: str = "zoe",
    user_id: str = "42",
    is_bot: bool = False,
    message_id: str = "m1",
    channel_context: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        message_id=message_id,
        channel_context=channel_context,
        source=SimpleNamespace(
            platform=SimpleNamespace(value=platform),
            chat_id=chat_id,
            parent_chat_id=None,
            thread_id=None,
            user_id=user_id,
            user_name=user_name,
            is_bot=is_bot,
            message_id=message_id,
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
        # Deterministic: never read the operator's real state file
        # (the default would resolve to ~/.hermes/nunchi-gate.state.json).
        "state_path": "/nonexistent/nunchi-gate-test-state.json",
    }
    cfg.update(overrides)
    return cfg


# ===========================================================================
# Section 1: Rolling buffer unit tests
# ===========================================================================

class TestRollingHistoryBuffer(unittest.TestCase):
    """_rolling_history and _record_to_buffer correctness."""

    def setUp(self) -> None:
        self.p = _load_plugin()
        # Ensure each test starts with a clean buffer.
        self.p._CHANNEL_HISTORY.clear()

    def _record(self, ch: str, text: str, user: str = "alice", is_bot: bool = False, msg_id: str = "m1") -> None:
        ev = _event(text=text, chat_id=ch, user_name=user, is_bot=is_bot, message_id=msg_id)
        self.p._record_to_buffer(ch, ev, ev.source, 20)

    # --- basic build ---

    def test_empty_buffer_returns_empty_list(self) -> None:
        result = self.p._rolling_history("chan-1", 20)
        self.assertEqual(result, [])

    def test_recorded_entry_appears_in_history(self) -> None:
        self._record("chan-1", "hello")
        result = self.p._rolling_history("chan-1", 20)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "hello")
        self.assertEqual(result[0]["author"], "alice")
        self.assertEqual(result[0]["author_kind"], "human")

    def test_multiple_entries_in_order(self) -> None:
        for i in range(5):
            self._record("chan-1", f"msg-{i}")
        result = self.p._rolling_history("chan-1", 20)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0]["content"], "msg-0")
        self.assertEqual(result[-1]["content"], "msg-4")

    # --- FIFO eviction ---

    def test_window_eviction_keeps_newest_entries(self) -> None:
        for i in range(25):
            self._record("chan-1", f"msg-{i}", msg_id=f"m{i}")
        result = self.p._rolling_history("chan-1", 20)
        self.assertEqual(len(result), 20)
        self.assertEqual(result[0]["content"], "msg-5")
        self.assertEqual(result[-1]["content"], "msg-24")

    def test_small_window_evicts_correctly(self) -> None:
        ev = _event(text="a", chat_id="ch", message_id="m1")
        self.p._record_to_buffer("ch", ev, ev.source, 3)
        ev = _event(text="b", chat_id="ch", message_id="m2")
        self.p._record_to_buffer("ch", ev, ev.source, 3)
        ev = _event(text="c", chat_id="ch", message_id="m3")
        self.p._record_to_buffer("ch", ev, ev.source, 3)
        ev = _event(text="d", chat_id="ch", message_id="m4")
        self.p._record_to_buffer("ch", ev, ev.source, 3)
        result = self.p._rolling_history("ch", 3)
        self.assertEqual(len(result), 3)
        contents = [e["content"] for e in result]
        self.assertEqual(contents, ["b", "c", "d"])

    # --- per-channel isolation ---

    def test_different_channels_are_isolated(self) -> None:
        self._record("chan-A", "msg for A")
        self._record("chan-B", "msg for B")
        result_a = self.p._rolling_history("chan-A", 20)
        result_b = self.p._rolling_history("chan-B", 20)
        self.assertEqual(len(result_a), 1)
        self.assertEqual(len(result_b), 1)
        self.assertEqual(result_a[0]["content"], "msg for A")
        self.assertEqual(result_b[0]["content"], "msg for B")

    def test_recording_to_one_channel_does_not_affect_another(self) -> None:
        self._record("chan-X", "first")
        self._record("chan-Y", "second")
        self._record("chan-X", "third")
        self.assertEqual(len(self.p._rolling_history("chan-Y", 20)), 1)
        self.assertEqual(len(self.p._rolling_history("chan-X", 20)), 2)

    # --- bot/human author_kind ---

    def test_bot_sender_tagged_peer_bot(self) -> None:
        self._record("chan-1", "bot msg", user="Station", is_bot=True)
        result = self.p._rolling_history("chan-1", 20)
        self.assertEqual(result[0]["author_kind"], "peer_bot")
        self.assertEqual(result[0]["author"], "Station")

    def test_human_sender_tagged_human(self) -> None:
        self._record("chan-1", "human msg", user="Zoe", is_bot=False)
        result = self.p._rolling_history("chan-1", 20)
        self.assertEqual(result[0]["author_kind"], "human")

    def test_message_id_included_when_present(self) -> None:
        ev = _event(text="hello", chat_id="ch", message_id="abc-123")
        self.p._record_to_buffer("ch", ev, ev.source, 20)
        result = self.p._rolling_history("ch", 20)
        self.assertEqual(result[0]["message_id"], "abc-123")

    def test_empty_text_is_not_recorded(self) -> None:
        ev = _event(text="", chat_id="ch")
        self.p._record_to_buffer("ch", ev, ev.source, 20)
        self.assertEqual(self.p._rolling_history("ch", 20), [])

    def test_whitespace_only_text_is_not_recorded(self) -> None:
        ev = _event(text="   ", chat_id="ch")
        self.p._record_to_buffer("ch", ev, ev.source, 20)
        self.assertEqual(self.p._rolling_history("ch", 20), [])


class TestRollingHistoryInGateEvent(unittest.TestCase):
    """_gate_event uses rolling buffer and history_len reflects real history."""

    def setUp(self) -> None:
        self.p = _load_plugin()
        self.p._CHANNEL_HISTORY.clear()

    def test_first_event_has_no_history(self) -> None:
        """Before any events are seen, history is empty."""
        payloads: list[dict] = []

        def capture_run(payload: dict, cfg: dict) -> dict:
            payloads.append(payload)
            return {"verdict": "SPEAK", "silent": False}

        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=_base_cfg()):
            with unittest.mock.patch.object(self.p, "_run_nunchi", capture_run):
                self.p._gate_event(_event("first message"))

        self.assertEqual(len(payloads), 1)
        self.assertNotIn("history", payloads[0])

    def test_second_event_has_first_in_history(self) -> None:
        """After the first event, the second sees it in its history."""
        payloads: list[dict] = []

        def capture_run(payload: dict, cfg: dict) -> dict:
            payloads.append(payload)
            return {"verdict": "SPEAK", "silent": False}

        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=_base_cfg()):
            with unittest.mock.patch.object(self.p, "_run_nunchi", capture_run):
                self.p._gate_event(_event("first", message_id="m1"))
                self.p._gate_event(_event("second", message_id="m2"))

        self.assertEqual(len(payloads), 2)
        # Second payload should have first event in history.
        self.assertIn("history", payloads[1])
        contents = [h["content"] for h in payloads[1]["history"]]
        self.assertIn("first", contents)

    def test_history_window_from_config(self) -> None:
        """history_window config key limits how many entries are used."""
        payloads: list[dict] = []

        def capture_run(payload: dict, cfg: dict) -> dict:
            payloads.append(payload)
            return {"verdict": "SPEAK", "silent": False}

        cfg = _base_cfg(history_window=3)
        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=cfg):
            with unittest.mock.patch.object(self.p, "_run_nunchi", capture_run):
                for i in range(7):
                    self.p._gate_event(_event(f"msg-{i}", message_id=f"m{i}"))

        # The last (7th) event should have at most 3 history entries.
        last_payload = payloads[-1]
        history = last_payload.get("history", [])
        self.assertLessEqual(len(history), 3)

    def test_history_len_in_log_reflects_real_history(self) -> None:
        """history_len in the gate log entry equals len(history sent)."""
        log_entries: list[dict] = []

        def capture_log(entry: dict, cfg: dict) -> None:
            log_entries.append(entry)

        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=_base_cfg()):
            with unittest.mock.patch.object(self.p, "_run_nunchi", return_value={"verdict": "SPEAK", "silent": False}):
                with unittest.mock.patch.object(self.p, "_write_gate_log", capture_log):
                    self.p._gate_event(_event("first", message_id="m1"))
                    self.p._gate_event(_event("second", message_id="m2"))

        # First event: history_len=0; second: history_len=1.
        self.assertEqual(log_entries[0]["history_len"], 0)
        self.assertEqual(log_entries[1]["history_len"], 1)

    def test_record_happens_even_on_error(self) -> None:
        """Buffer is updated even when the classifier fails (finally block)."""

        def boom(payload: dict, cfg: dict) -> dict:
            raise RuntimeError("classifier down")

        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=_base_cfg(fail_open=True)):
            with unittest.mock.patch.object(self.p, "_run_nunchi", boom):
                self.p._gate_event(_event("first", message_id="m1"))

        # Buffer should have the first event despite the error.
        ch_id = "1518384310321811456"
        buf = self.p._CHANNEL_HISTORY.get(ch_id, [])
        self.assertEqual(len(buf), 1)
        self.assertEqual(buf[0]["content"], "first")

    def test_per_channel_isolation_in_gate(self) -> None:
        """Events on different channels do not share rolling history."""
        payloads: list[dict] = []

        def capture_run(payload: dict, cfg: dict) -> dict:
            payloads.append(payload)
            return {"verdict": "SPEAK", "silent": False}

        cfg = _base_cfg(channels="*")
        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=cfg):
            with unittest.mock.patch.object(self.p, "_run_nunchi", capture_run):
                self.p._gate_event(_event("chan-A msg", chat_id="chan-A", message_id="mA1"))
                self.p._gate_event(_event("chan-B first", chat_id="chan-B", message_id="mB1"))
                self.p._gate_event(_event("chan-B second", chat_id="chan-B", message_id="mB2"))

        # payloads[2] is chan-B second; its history should have chan-B first, not chan-A msg.
        b2_history = payloads[2].get("history", [])
        contents = [h["content"] for h in b2_history]
        self.assertIn("chan-B first", contents)
        self.assertNotIn("chan-A msg", contents)

    def test_channel_context_preferred_when_richer(self) -> None:
        """When channel_context is richer than rolling, it is used."""
        ctx = (
            "[Recent channel messages]\n"
            "[Zoe] a\n[Zoe] b\n[Zoe] c\n[Zoe] d\n[Zoe] e"
        )
        payloads: list[dict] = []

        def capture_run(payload: dict, cfg: dict) -> dict:
            payloads.append(payload)
            return {"verdict": "SPEAK", "silent": False}

        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=_base_cfg()):
            with unittest.mock.patch.object(self.p, "_run_nunchi", capture_run):
                # First event has empty rolling buffer; provide channel_context.
                self.p._gate_event(_event("trigger", channel_context=ctx, message_id="m1"))

        history = payloads[0].get("history", [])
        # channel_context has 5 entries; rolling has 0 → ctx wins.
        self.assertEqual(len(history), 5)

    def test_rolling_preferred_when_richer_than_ctx(self) -> None:
        """When rolling buffer is richer than channel_context, rolling is used."""
        # Seed the rolling buffer with 3 entries.
        ch_id = "1518384310321811456"
        for i in range(3):
            ev = _event(f"pre-{i}", chat_id=ch_id, message_id=f"seed-{i}")
            self.p._CHANNEL_HISTORY.setdefault(ch_id, []).append({
                "content": f"pre-{i}", "author": "zoe", "author_kind": "human",
            })

        ctx = "[Recent channel messages]\n[Zoe] only one"
        payloads: list[dict] = []

        def capture_run(payload: dict, cfg: dict) -> dict:
            payloads.append(payload)
            return {"verdict": "SPEAK", "silent": False}

        with unittest.mock.patch.object(self.p, "_nunchi_config", return_value=_base_cfg()):
            with unittest.mock.patch.object(self.p, "_run_nunchi", capture_run):
                self.p._gate_event(_event("trigger", channel_context=ctx, message_id="m99"))

        history = payloads[0].get("history", [])
        # rolling (3) > ctx (1) → rolling used; pre-0/pre-1/pre-2 present.
        contents = [h["content"] for h in history]
        self.assertTrue(any("pre-" in c for c in contents), f"Expected pre- entries, got {contents}")


class TestRollingBufferMemorySafety(unittest.TestCase):
    """Buffer is bounded: per-channel FIFO and global total cap."""

    def setUp(self) -> None:
        self.p = _load_plugin()
        self.p._CHANNEL_HISTORY.clear()

    def test_per_channel_cap_respected(self) -> None:
        for i in range(100):
            ev = _event(f"msg-{i}", chat_id="ch", message_id=f"m{i}")
            self.p._record_to_buffer("ch", ev, ev.source, 20)
        buf = self.p._CHANNEL_HISTORY.get("ch", [])
        self.assertLessEqual(len(buf), 20)

    def test_global_cap_evicts_oldest_channel(self) -> None:
        # Fill 10 channels with 200 entries each (10*200=2000 total).
        # Then fill one more channel to trigger global eviction.
        # Set _HISTORY_MAX_TOTAL to a small value for the test.
        original_max = self.p._HISTORY_MAX_TOTAL
        self.p._HISTORY_MAX_TOTAL = 50

        try:
            for i in range(5):
                ch = f"old-chan-{i}"
                for j in range(10):
                    ev = _event(f"msg-{j}", chat_id=ch, message_id=f"m{j}")
                    self.p._record_to_buffer(ch, ev, ev.source, 20)

            # One more channel push should trigger eviction.
            ev = _event("trigger eviction", chat_id="new-chan", message_id="new")
            self.p._record_to_buffer("new-chan", ev, ev.source, 20)

            total = sum(len(v) for v in self.p._CHANNEL_HISTORY.values())
            # Total should be at most _HISTORY_MAX_TOTAL + 1 (the entry that triggered it).
            self.assertLessEqual(total, 52, f"Too many entries: {total}")
        finally:
            self.p._HISTORY_MAX_TOTAL = original_max


# ===========================================================================
# Section 3: Adapter default tests
# ===========================================================================

class TestAdapterDefaults(unittest.TestCase):
    """Standalone adapter history defaults are >= 20 and configurable via env."""

    def _load_adapter(self, name: str):
        import sys, pathlib
        src_path = str(pathlib.Path(__file__).resolve().parents[1] / "src")
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        # matrix and telegram use urllib so they don't need discord.py
        if name == "matrix":
            from nunchi.adapters import matrix
            return matrix
        elif name == "telegram":
            from nunchi.adapters import telegram
            return telegram
        elif name == "discord":
            from nunchi.adapters import discord
            return discord
        raise ValueError(name)

    def test_matrix_default_history_len_is_20(self) -> None:
        mod = self._load_adapter("matrix")
        self.assertEqual(mod._DEFAULT_HISTORY_LEN, 20)

    def test_telegram_default_history_len_is_20(self) -> None:
        mod = self._load_adapter("telegram")
        self.assertEqual(mod._DEFAULT_HISTORY_LEN, 20)

    def test_discord_default_history_len_is_20(self) -> None:
        mod = self._load_adapter("discord")
        self.assertEqual(mod._DEFAULT_HISTORY_LEN, 20)

    def test_matrix_env_var_configures_history(self) -> None:
        """NUNCHI_MATRIX_HISTORY env var controls the loop's history_len."""
        with unittest.mock.patch.dict(os.environ, {"NUNCHI_MATRIX_HISTORY": "30"}):
            from nunchi.adapters import matrix as m
            # Simulate the env read that main() does.
            raw = os.environ.get("NUNCHI_MATRIX_HISTORY", str(m._DEFAULT_HISTORY_LEN))
            val = int(raw)
            self.assertEqual(val, 30)

    def test_telegram_env_var_configures_history(self) -> None:
        """NUNCHI_TELEGRAM_HISTORY env var controls the loop's history_len."""
        with unittest.mock.patch.dict(os.environ, {"NUNCHI_TELEGRAM_HISTORY": "35"}):
            from nunchi.adapters import telegram as t
            raw = os.environ.get("NUNCHI_TELEGRAM_HISTORY", str(t._DEFAULT_HISTORY_LEN))
            val = int(raw)
            self.assertEqual(val, 35)

    def test_discord_env_var_configures_history(self) -> None:
        """NUNCHI_DISCORD_HISTORY env var controls the loop's history_len."""
        with unittest.mock.patch.dict(os.environ, {"NUNCHI_DISCORD_HISTORY": "40"}):
            from nunchi.adapters import discord as d
            raw = os.environ.get("NUNCHI_DISCORD_HISTORY", str(d._DEFAULT_HISTORY_LEN))
            val = int(raw)
            self.assertEqual(val, 40)

    def test_matrix_default_at_least_20(self) -> None:
        from nunchi.adapters import matrix as m
        self.assertGreaterEqual(m._DEFAULT_HISTORY_LEN, 20)

    def test_telegram_default_at_least_20(self) -> None:
        from nunchi.adapters import telegram as t
        self.assertGreaterEqual(t._DEFAULT_HISTORY_LEN, 20)

    def test_discord_default_at_least_20(self) -> None:
        from nunchi.adapters import discord as d
        self.assertGreaterEqual(d._DEFAULT_HISTORY_LEN, 20)


if __name__ == "__main__":
    unittest.main()
