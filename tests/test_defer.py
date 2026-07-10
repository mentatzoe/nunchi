"""DEFER v1: gate abstention on an uncertain PASS — the participant's reply stands.

The gate must not veto a socially plausible turn it cannot confidently silence,
and it must not consult a second classifier to do so (DEFER is abstention, not a
model router). These are the deterministic contract tests; whether the
uncertainty threshold improves room behaviour is the eval arm's job (DEFER_EVAL.md).

Scope note: this module is the *outbound* case (the participant has already
composed), so it proves "DEFER → participant may speak" (the reply stands). The
paired "DEFER → participant may choose silence" belongs to the *inbound* path
(admit/wake with uncertainty; the woken agent may decline) — not this module.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import textwrap
import unittest

_HOOK_DIR = pathlib.Path(__file__).resolve().parents[1] / "integrations" / "claude-code"
sys.path.insert(0, str(_HOOK_DIR))

import nunchi_defer as defer  # noqa: E402

from tests.test_claude_code_hook import (  # noqa: E402
    _hook_input,
    _make_transcript,
    _run_hook,
    _user_channel_entry,
)


def _directive(verdict, pass_c=0.0, speak=0.0, ack=0.0, ask=0.0):
    return {
        "verdict": verdict,
        "confidences": {"PASS": pass_c, "ACK": ack, "ASK": ask, "SPEAK": speak},
        "reasons": ["x"],
    }


class IsUncertain(unittest.TestCase):
    def test_pass_with_close_alternative_is_uncertain(self):
        self.assertTrue(defer.is_uncertain(_directive("PASS", pass_c=0.45, speak=0.40), 0.25))

    def test_confident_pass_is_not_uncertain(self):
        self.assertFalse(defer.is_uncertain(_directive("PASS", pass_c=0.92, speak=0.03), 0.25))

    def test_non_pass_is_never_uncertain(self):
        self.assertFalse(defer.is_uncertain(_directive("SPEAK", speak=0.4, pass_c=0.35), 0.25))

    def test_missing_confidences_is_not_uncertain(self):
        self.assertFalse(defer.is_uncertain({"verdict": "PASS"}, 0.25))


class Resolve(unittest.TestCase):
    def test_disabled_passes_cheap_through(self):
        d = _directive("PASS", pass_c=0.45, speak=0.40)
        out, meta = defer.resolve(d, enabled=False, margin=0.25)
        self.assertIs(out, d)
        self.assertFalse(meta["defer_triggered"])

    def test_confident_pass_is_not_deferred(self):
        d = _directive("PASS", pass_c=0.92, speak=0.03)
        out, meta = defer.resolve(d, enabled=True, margin=0.25)
        self.assertEqual(out["verdict"], "PASS")
        self.assertFalse(meta["defer_triggered"])

    def test_uncertain_pass_abstains_never_forced_pass(self):
        d = _directive("PASS", pass_c=0.45, speak=0.40)
        out, meta = defer.resolve(d, enabled=True, margin=0.25)
        self.assertTrue(meta["defer_triggered"])
        self.assertEqual(meta["resolution"], "abstain-return-to-participant")
        self.assertNotEqual(out["verdict"], "PASS",
                            "DEFER abstains from suppression — it must not leave a PASS")
        # No second classifier in the live path: nothing records a frontier verdict.
        self.assertNotIn("frontier_verdict", meta)


def _flat_pass_gate() -> str:
    """Stub nunchi-channel returning an uncertain (flat) PASS — no model routing
    anywhere in the path."""
    directive = {
        "verdict": "PASS", "silent": True,
        "confidences": {"PASS": 0.45, "SPEAK": 0.40, "ACK": 0.05, "ASK": 0.10},
        "reasons": ["ambiguous — not sure this is mine"],
    }
    stub = textwrap.dedent(
        f"""\
        #!/usr/bin/env python3
        import sys
        sys.stdin.read()
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
    return wpath


class DeferWired(unittest.TestCase):
    """End-to-end: DEFER on → an uncertain PASS abstains and the participant's
    composed reply is allowed; DEFER off → the cheap PASS stands. No model call."""

    def _run(self, defer_on: bool, log_path: str | None = None):
        wrapper = _flat_pass_gate()
        transcript = _make_transcript([
            _user_channel_entry(chat_id="c1", message_id="A", user="zoe",
                                body="How's everyone doing tonight?", ts="2026-07-10T03:09:00Z")
        ])
        env = {"NUNCHI_CHANNEL_BIN": wrapper, "NUNCHI_HOOK_FAIL_POLICY": "closed"}
        if defer_on:
            env["NUNCHI_DEFER"] = "1"
        if log_path:
            env["NUNCHI_HOOK_LOG"] = log_path
        return _run_hook(_hook_input(chat_id="c1", text="I'm good, Zoe.",
                                     transcript_path=transcript, session_id="s1"),
                         env_overrides=env)

    def test_defer_on_abstains_uncertain_pass_to_allow(self):
        rc, out, err = self._run(defer_on=True)
        self.assertIn('"permissionDecision": "allow"', out,
                      "an uncertain PASS should abstain — the participant's composed reply stands")

    def test_defer_off_lets_cheap_pass_stand(self):
        rc, out, err = self._run(defer_on=False)
        self.assertIn('"permissionDecision": "deny"', out,
                      "without DEFER the cheap PASS stands — proving DEFER is what changed it")

    def test_defer_abstention_is_recorded_for_offline_eval(self):
        """DEFER_EVAL.md needs recorded cases: the receipt must capture that the
        gate abstained and what the cheap gate *would* have suppressed."""
        log_fd, log_path = tempfile.mkstemp(suffix=".jsonl")
        os.close(log_fd)
        self._run(defer_on=True, log_path=log_path)
        lines = [ln for ln in pathlib.Path(log_path).read_text().splitlines() if ln.strip()]
        rec = json.loads(lines[-1])
        self.assertIn("defer", rec, "an abstention must be recorded for the offline evaluator")
        self.assertEqual(rec["defer"]["resolution"], "abstain-return-to-participant")
        self.assertEqual(rec["defer"]["cheap_verdict"], "PASS",
                         "the receipt must preserve what the cheap gate would have done")


if __name__ == "__main__":
    unittest.main()
