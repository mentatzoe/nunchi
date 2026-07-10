"""Causal-permit binding: the fix for the outbound trigger re-bind false-PASS.

Fixture zero is the live miss (2026-07-10 03:09): an operator invitation A is
admitted, the agent composes a reply for A, a peer line B lands during
composition, and the outbound gate — reverse-scanning for the newest inbound —
judges B ("not addressed to me") and kills the reply as a false PASS. The fix
binds the send to A (the permit origin) while still showing the classifier the
post-origin tail B, so a genuinely drifted thread can still correctly PASS.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import textwrap
import time
import unittest

_HOOK_DIR = pathlib.Path(__file__).resolve().parents[1] / "integrations" / "claude-code"
sys.path.insert(0, str(_HOOK_DIR))

import nunchi_causal_permit as permit  # noqa: E402

from tests.test_claude_code_hook import (  # noqa: E402
    _hook_input,
    _make_speak_directive,
    _make_transcript,
    _run_hook,
    _user_channel_entry,
)


class PermitStoreTests(unittest.TestCase):
    """The permit is a session-scoped, TTL-bounded, newest-wins correlation
    record — not a durable service queue."""

    def setUp(self) -> None:
        self.dir = pathlib.Path(tempfile.mkdtemp())

    def _write(self, session, chat, mid, now):
        permit.write_permit(session, chat, mid, "author", "ts", directory=self.dir, now=now)

    def test_write_then_read_within_ttl(self):
        self._write("s1", "c1", "A", now=100.0)
        p = permit.read_permit("s1", "c1", directory=self.dir, now=150.0, ttl=300.0)
        self.assertIsNotNone(p)
        self.assertEqual(p["origin_message_id"], "A")

    def test_never_crosses_session_boundary(self):
        self._write("s1", "c1", "A", now=100.0)
        self.assertIsNone(permit.read_permit("s2", "c1", directory=self.dir, now=101.0, ttl=300.0))

    def test_expires_past_ttl_no_necro(self):
        self._write("s1", "c1", "A", now=100.0)
        self.assertIsNone(permit.read_permit("s1", "c1", directory=self.dir, now=100.0 + 301, ttl=300.0))

    def test_newest_admit_supersedes_not_fifo(self):
        self._write("s1", "c1", "A", now=100.0)
        self._write("s1", "c1", "C", now=110.0)  # a later admit in the same turn/chat
        p = permit.read_permit("s1", "c1", directory=self.dir, now=120.0, ttl=300.0)
        self.assertEqual(p["origin_message_id"], "C")

    def test_clear_closes_it(self):
        self._write("s1", "c1", "A", now=100.0)
        permit.clear_permit("s1", "c1", directory=self.dir)
        self.assertIsNone(permit.read_permit("s1", "c1", directory=self.dir, now=101.0, ttl=300.0))

    def test_missing_file_is_none_not_crash(self):
        self.assertIsNone(permit.read_permit("s1", "c1", directory=self.dir, now=1.0))

    def test_distinct_keys_coexist_no_clobber(self):
        # A shared read-modify-write map loses one permit when two writers start
        # from the same store (Aleph's two-writer repro). Per-(session,chat)
        # files cannot clobber unrelated records.
        self._write("s1", "c1", "A", now=100.0)
        self._write("s2", "c2", "B", now=100.0)
        self.assertEqual(
            permit.read_permit("s1", "c1", directory=self.dir, now=101.0)["origin_message_id"], "A")
        self.assertEqual(
            permit.read_permit("s2", "c2", directory=self.dir, now=101.0)["origin_message_id"], "B")

    def test_same_key_is_last_write_wins_not_newest_timestamp(self):
        # KNOWN LIMITATION (Vigil): per-key files stop cross-key clobber, but
        # same-key resolution is last-WRITE-wins (rename order), NOT
        # newest-by-timestamp. A truly concurrent *older* admit that renames last
        # would win. Closing it needs one file per admission + sequence-select.
        self._write("s1", "c1", "C", now=200.0)  # newer by timestamp
        self._write("s1", "c1", "A", now=100.0)  # older, but written last
        p = permit.read_permit("s1", "c1", directory=self.dir, now=300.0, ttl=1000.0)
        self.assertEqual(p["origin_message_id"], "A",
                         "same-key resolution is last-write-wins, not newest-timestamp — the known race")


def _capturing_gate(directive: dict) -> tuple[str, str]:
    """A nunchi-channel stub that records the payload it receives, then emits
    *directive*. Returns (wrapper_path, capture_path)."""
    cfd, capture = tempfile.mkstemp(suffix=".json")
    os.close(cfd)
    stub = textwrap.dedent(
        f"""\
        #!/usr/bin/env python3
        import sys
        data = sys.stdin.read()
        with open({capture!r}, "w") as fh:
            fh.write(data)
        print({json.dumps(json.dumps(directive))})
        sys.exit(0)
        """
    )
    sfd, spath = tempfile.mkstemp(suffix=".py")
    with os.fdopen(sfd, "w") as fh:
        fh.write(stub)
    wfd, wpath = tempfile.mkstemp(suffix=".sh")
    with os.fdopen(wfd, "w") as fh:
        fh.write(f'#!/bin/sh\n{sys.executable} {spath} "$@"\n')
    os.chmod(wpath, 0o755)
    return wpath, capture


class FixtureZero(unittest.TestCase):
    """The live A→B re-bind miss, and the contrast proving the permit fixes it."""

    def _transcript_A_then_B(self):
        a = _user_channel_entry(
            chat_id="c1", message_id="A", user="zoe",
            body="How's everyone doing tonight?", ts="2026-07-10T03:09:00Z",
        )
        b = _user_channel_entry(
            chat_id="c1", message_id="B", user="Aleph",
            body="I'm good: present, clear-headed.", ts="2026-07-10T03:10:22Z",
        )
        return _make_transcript([a, b])

    def _run(self, transcript, permit_path):
        wrapper, capture = _capturing_gate(_make_speak_directive())
        rc, out, err = _run_hook(
            _hook_input(chat_id="c1", text="I'm good, Zoe.",
                        transcript_path=transcript, session_id="sess-abc"),
            env_overrides={"NUNCHI_CHANNEL_BIN": wrapper,
                           "NUNCHI_PERMIT_DIR": str(permit_path)},
        )
        return json.loads(pathlib.Path(capture).read_text())

    def test_binds_to_origin_A_not_newest_peer_B(self):
        """FIXTURE ZERO: with a permit for A, the outbound gate judges A, not B,
        and the classifier still sees B as the post-origin tail."""
        pp = pathlib.Path(tempfile.mkdtemp())
        permit.write_permit("sess-abc", "c1", "A", "zoe", "2026-07-10T03:09:00Z",
                            directory=pp, now=time.time())  # admit-time; default 300s TTL covers this ms test
        payload = self._run(self._transcript_A_then_B(), pp)
        self.assertEqual(payload["trigger"]["message_id"], "A",
                         "must bind to the invitation A, not the newest peer line B")
        hist_ids = [m["message_id"] for m in payload["history"]]
        self.assertIn("B", hist_ids,
                      "the post-origin tail B must be visible so the classifier can judge liveness")

    def test_legacy_without_permit_reproduces_the_bug(self):
        """No permit → legacy newest-inbound scan → binds to B (the bug). This
        is what made my 'how's everyone' reply die as a false PASS."""
        pp = pathlib.Path(tempfile.mkdtemp())  # empty: no permit
        payload = self._run(self._transcript_A_then_B(), pp)
        self.assertEqual(payload["trigger"]["message_id"], "B",
                         "without a permit the legacy scan binds to the newest inbound — the defect")

    def test_permit_from_another_session_does_not_bind(self):
        """A permit for a *different* session must not rebind this turn (no
        cross-session necro); it falls back to legacy."""
        pp = pathlib.Path(tempfile.mkdtemp())
        permit.write_permit("OTHER-session", "c1", "A", directory=pp, now=time.time())
        payload = self._run(self._transcript_A_then_B(), pp)
        self.assertEqual(payload["trigger"]["message_id"], "B",
                         "another session's permit must not bind this turn")

    def test_permit_is_consumed_one_shot(self):
        """The permit is consumed on the first outbound decision, so an unrelated
        later send falls to legacy — not a 300s retargeting lease."""
        pp = pathlib.Path(tempfile.mkdtemp())
        permit.write_permit("sess-abc", "c1", "A", directory=pp, now=time.time())
        transcript = self._transcript_A_then_B()
        first = self._run(transcript, pp)
        self.assertEqual(first["trigger"]["message_id"], "A", "first decision binds A")
        self.assertIsNone(permit.read_permit("sess-abc", "c1", directory=pp),
                          "permit must be consumed after the first decision")
        second = self._run(transcript, pp)
        self.assertEqual(second["trigger"]["message_id"], "B",
                         "a second, unrelated decision falls to legacy — no retargeting lease")

    def _receipt_for(self, permit_path):
        """Run the hook with a redirected receipt log; return the last record."""
        wrapper, _capture = _capturing_gate(_make_speak_directive())
        log_fd, log_path = tempfile.mkstemp(suffix=".jsonl")
        os.close(log_fd)
        _run_hook(
            _hook_input(chat_id="c1", text="I'm good, Zoe.",
                        transcript_path=self._transcript_A_then_B(), session_id="sess-abc"),
            env_overrides={"NUNCHI_CHANNEL_BIN": wrapper,
                           "NUNCHI_PERMIT_DIR": str(permit_path),
                           "NUNCHI_HOOK_LOG": log_path},
        )
        lines = [ln for ln in pathlib.Path(log_path).read_text().splitlines() if ln.strip()]
        return json.loads(lines[-1])

    def test_receipt_records_causal_binding_provenance(self):
        """The receipt must make the binding legible to the eval arm: a
        permit-bound decision records bound_via=causal-permit and permit_consumed."""
        pp = pathlib.Path(tempfile.mkdtemp())
        permit.write_permit("sess-abc", "c1", "A", directory=pp, now=time.time())
        rec = self._receipt_for(pp)
        self.assertEqual(rec["bound_via"], "causal-permit")
        self.assertTrue(rec["permit_consumed"])
        self.assertEqual(rec["trigger_message_id"], "A")

    def test_receipt_records_legacy_binding_provenance(self):
        """No permit → the receipt records bound_via=legacy-scan, not consumed."""
        rec = self._receipt_for(pathlib.Path(tempfile.mkdtemp()))  # empty: no permit
        self.assertEqual(rec["bound_via"], "legacy-scan")
        self.assertFalse(rec["permit_consumed"])
        self.assertEqual(rec["trigger_message_id"], "B")

    @unittest.expectedFailure
    def test_retry_after_consume_rebinds_origin_UNSUPPORTED(self):
        """UNSUPPORTED, made legible (Vigil): the causal contract is *not* carried
        through a transport retry. The permit is one-shot — consumed on the first
        outbound decision — so if Claude Code retries that same send, the retry has
        no permit and falls to legacy newest-inbound (binds B). This asserts the
        turn's *intended* origin A and is marked expectedFailure so the gap reads
        as a known limitation, not a solved case. Closing it needs a retry
        correlation token distinct from the one-shot permit."""
        pp = pathlib.Path(tempfile.mkdtemp())
        permit.write_permit("sess-abc", "c1", "A", directory=pp, now=time.time())
        transcript = self._transcript_A_then_B()
        self._run(transcript, pp)              # first decision consumes the permit
        retry = self._run(transcript, pp)      # a retry of the *same* send
        self.assertEqual(retry["trigger"]["message_id"], "A",
                         "retry causality is unsupported — this is expected to fail")


if __name__ == "__main__":
    unittest.main()
