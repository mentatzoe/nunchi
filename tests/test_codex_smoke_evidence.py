"""Tests for Codex live-smoke evidence summarization."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "integrations" / "codex" / "summarize_vigil_smoke.py"


class TestVigilSmokeEvidenceSummary(unittest.TestCase):
    def test_writes_markdown_when_wake_and_outbound_hook_are_present(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            log = tmp / "receipts.jsonl"
            out = tmp / "evidence.md"
            records = [
                {
                    "ts": "2026-07-09T15:00:00+00:00",
                    "channel": "1522258711047831653",
                    "message_id": "m-pass",
                    "author": "Station",
                    "verdict": "PASS",
                    "action": "pass-suppressed",
                    "history_len": 4,
                },
                {
                    "ts": "2026-07-09T15:01:00+00:00",
                    "channel": "1522258711047831653",
                    "message_id": "m-trigger",
                    "author": "decisionparalysis",
                    "verdict": "SPEAK",
                    "action": "wake-ok",
                    "history_len": 5,
                    "wake_exit": 0,
                },
                {
                    "ts": "2026-07-09T15:01:12+00:00",
                    "direction": "hook-outbound",
                    "channel": "1522258711047831653",
                    "trigger_message_id": "m-trigger",
                    "verdict": "SPEAK",
                    "action": "allow-speak",
                    "history_len": 5,
                },
            ]
            log.write_text("\n".join(json.dumps(r) for r in records) + "\n")

            result = subprocess.run(
                [
                    sys.executable,
                    str(_SCRIPT),
                    "--log",
                    str(log),
                    "--out",
                    str(out),
                    "--channel",
                    "1522258711047831653",
                    "--reply-message-id",
                    "m-reply",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            text = out.read_text(encoding="utf-8")
            self.assertIn("successful", text)
            self.assertIn("wake-ok", text)
            self.assertIn("allow-speak", text)
            self.assertIn("m-trigger", text)
            self.assertIn("m-reply", text)
            self.assertNotIn("content", text.lower())

    def test_trigger_filter_ignores_busy_room_wake_without_matching_allow(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            log = tmp / "receipts.jsonl"
            out = tmp / "evidence.md"
            records = [
                {
                    "ts": "2026-07-09T15:00:00+00:00",
                    "channel": "1522258711047831653",
                    "message_id": "m-other",
                    "verdict": "SPEAK",
                    "action": "wake-ok",
                    "wake_exit": 0,
                },
                {
                    "ts": "2026-07-09T15:00:10+00:00",
                    "direction": "hook-outbound",
                    "channel": "1522258711047831653",
                    "trigger_message_id": "m-other",
                    "verdict": "PASS",
                    "action": "deny-pass",
                },
                {
                    "ts": "2026-07-09T15:01:00+00:00",
                    "channel": "1522258711047831653",
                    "message_id": "m-target",
                    "verdict": "SPEAK",
                    "action": "wake-ok",
                    "wake_exit": 0,
                },
                {
                    "ts": "2026-07-09T15:01:12+00:00",
                    "direction": "hook-outbound",
                    "channel": "1522258711047831653",
                    "trigger_message_id": "m-target",
                    "verdict": "SPEAK",
                    "action": "allow-speak",
                },
            ]
            log.write_text("\n".join(json.dumps(r) for r in records) + "\n")

            result = subprocess.run(
                [
                    sys.executable,
                    str(_SCRIPT),
                    "--log",
                    str(log),
                    "--out",
                    str(out),
                    "--channel",
                    "1522258711047831653",
                    "--trigger-message-id",
                    "m-target",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            text = out.read_text(encoding="utf-8")
            self.assertIn("m-target", text)
            self.assertNotIn("m-other", text)

    def test_fails_when_outbound_hook_allow_is_missing(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            log = tmp / "receipts.jsonl"
            log.write_text(
                json.dumps(
                    {
                        "ts": "2026-07-09T15:01:00+00:00",
                        "channel": "1522258711047831653",
                        "message_id": "m-trigger",
                        "verdict": "SPEAK",
                        "action": "wake-ok",
                        "wake_exit": 0,
                    }
                )
                + "\n"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(_SCRIPT),
                    "--log",
                    str(log),
                    "--channel",
                    "1522258711047831653",
                ],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("outbound hook allow", result.stderr)


if __name__ == "__main__":
    unittest.main()
