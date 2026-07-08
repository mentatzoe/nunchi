"""Tests for the shared per-channel send backstop (amplification-loops guard).

The backstop is a sliding-window cap on outbound sends, ported from the MCP
Discord transport's ``SendBackstop``. It is shared by the matrix, telegram,
and discord reference adapters via ``nunchi.adapters._backstop``.

All tests are offline and deterministic: the clock is injected.

Run with:
    python3 -m unittest tests.test_send_backstop
"""

from __future__ import annotations

import pathlib
import sys
import unittest

# Ensure src is on the path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from nunchi.adapters._backstop import (
    DEFAULT_MAX_SENDS,
    DEFAULT_WINDOW_SECONDS,
    SendBackstop,
    backstop_from_env,
)


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


# --------------------------------------------------------------------------- #
# SendBackstop core behavior
# --------------------------------------------------------------------------- #


class TestSendBackstop(unittest.TestCase):
    def test_default_on_with_reference_defaults(self):
        """A bare SendBackstop() is active with 5 sends per 10 seconds."""
        backstop = SendBackstop()
        self.assertEqual(backstop.max_sends, 5)
        self.assertEqual(backstop.window_seconds, 10.0)
        self.assertEqual(DEFAULT_MAX_SENDS, 5)
        self.assertEqual(DEFAULT_WINDOW_SECONDS, 10.0)

    def test_allows_up_to_max_sends(self):
        clock = _FakeClock()
        backstop = SendBackstop(3, 10.0, clock=clock)
        for _ in range(3):
            self.assertEqual(backstop.try_acquire("chan"), 0.0)

    def test_denies_over_cap_with_positive_wait(self):
        clock = _FakeClock()
        backstop = SendBackstop(2, 10.0, clock=clock)
        backstop.try_acquire("chan")
        backstop.try_acquire("chan")
        wait = backstop.try_acquire("chan")
        self.assertGreater(wait, 0.0)
        self.assertAlmostEqual(wait, 10.0)

    def test_window_slides(self):
        """Old sends fall out of the window; capacity comes back over time."""
        clock = _FakeClock()
        backstop = SendBackstop(2, 10.0, clock=clock)
        self.assertEqual(backstop.try_acquire("chan"), 0.0)   # t=0
        clock.now = 5.0
        self.assertEqual(backstop.try_acquire("chan"), 0.0)   # t=5
        self.assertGreater(backstop.try_acquire("chan"), 0.0)  # cap hit
        clock.now = 10.5  # t=0 send has aged out
        self.assertEqual(backstop.try_acquire("chan"), 0.0)
        # Window now holds t=5 and t=10.5 — cap hit again until t=15
        self.assertGreater(backstop.try_acquire("chan"), 0.0)

    def test_wait_hint_is_time_until_oldest_send_expires(self):
        clock = _FakeClock()
        backstop = SendBackstop(1, 10.0, clock=clock)
        backstop.try_acquire("chan")  # t=0
        clock.now = 4.0
        self.assertAlmostEqual(backstop.try_acquire("chan"), 6.0)

    def test_per_channel_isolation(self):
        """Exhausting one channel's window never affects another channel."""
        clock = _FakeClock()
        backstop = SendBackstop(1, 10.0, clock=clock)
        self.assertEqual(backstop.try_acquire("chan-a"), 0.0)
        self.assertGreater(backstop.try_acquire("chan-a"), 0.0)
        self.assertEqual(backstop.try_acquire("chan-b"), 0.0)

    def test_zero_max_sends_disables_sends(self):
        clock = _FakeClock()
        backstop = SendBackstop(0, 10.0, clock=clock)
        self.assertEqual(backstop.try_acquire("chan"), 10.0)

    def test_channel_id_coerced_to_str(self):
        """Int and str forms of the same channel id share one window."""
        clock = _FakeClock()
        backstop = SendBackstop(1, 10.0, clock=clock)
        self.assertEqual(backstop.try_acquire(123), 0.0)
        self.assertGreater(backstop.try_acquire("123"), 0.0)


# --------------------------------------------------------------------------- #
# Env-var knobs (operator-only)
# --------------------------------------------------------------------------- #


class TestBackstopFromEnv(unittest.TestCase):
    def test_defaults_when_env_unset(self):
        backstop = backstop_from_env("NUNCHI_MATRIX", environ={})
        self.assertEqual(backstop.max_sends, DEFAULT_MAX_SENDS)
        self.assertEqual(backstop.window_seconds, DEFAULT_WINDOW_SECONDS)

    def test_knobs_parsed_from_env(self):
        env = {
            "NUNCHI_TELEGRAM_BACKSTOP_MAX_SENDS": "2",
            "NUNCHI_TELEGRAM_BACKSTOP_WINDOW_SECONDS": "3.5",
        }
        backstop = backstop_from_env("NUNCHI_TELEGRAM", environ=env)
        self.assertEqual(backstop.max_sends, 2)
        self.assertEqual(backstop.window_seconds, 3.5)

    def test_prefix_scopes_the_lookup(self):
        env = {"NUNCHI_MATRIX_BACKSTOP_MAX_SENDS": "1"}
        backstop = backstop_from_env("NUNCHI_DISCORD", environ=env)
        self.assertEqual(backstop.max_sends, DEFAULT_MAX_SENDS)

    def test_malformed_values_fall_back_to_defaults(self):
        env = {
            "NUNCHI_DISCORD_BACKSTOP_MAX_SENDS": "many",
            "NUNCHI_DISCORD_BACKSTOP_WINDOW_SECONDS": "soon",
        }
        backstop = backstop_from_env("NUNCHI_DISCORD", environ=env)
        self.assertEqual(backstop.max_sends, DEFAULT_MAX_SENDS)
        self.assertEqual(backstop.window_seconds, DEFAULT_WINDOW_SECONDS)


if __name__ == "__main__":
    unittest.main()
