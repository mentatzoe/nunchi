"""DEFER v1 mechanism: escalate an uncertain PASS, never force PASS on failure.

These are the deterministic contract tests for the routing logic. Whether the
uncertainty *threshold* improves real room behaviour is the eval arm's job
(DEFER_EVAL.md), not something asserted here.
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
        # PASS 0.45 vs SPEAK 0.40 → margin 0.05 < 0.25 → ambiguous suppression
        self.assertTrue(defer.is_uncertain(_directive("PASS", pass_c=0.45, speak=0.40), 0.25))

    def test_confident_pass_is_not_uncertain(self):
        self.assertFalse(defer.is_uncertain(_directive("PASS", pass_c=0.92, speak=0.03), 0.25))

    def test_non_pass_is_never_uncertain(self):
        self.assertFalse(defer.is_uncertain(_directive("SPEAK", speak=0.4, pass_c=0.35), 0.25))

    def test_missing_confidences_is_not_uncertain(self):
        self.assertFalse(defer.is_uncertain({"verdict": "PASS"}, 0.25))


class Resolve(unittest.TestCase):
    def _boom(self, *_):
        raise RuntimeError("frontier down")

    def test_disabled_when_no_model_passes_cheap_through(self):
        d = _directive("PASS", pass_c=0.45, speak=0.40)
        out, meta = defer.resolve(d, self._boom, model="", margin=0.25)
        self.assertIs(out, d)
        self.assertFalse(meta["defer_triggered"])

    def test_confident_pass_is_not_escalated(self):
        called = []
        d = _directive("PASS", pass_c=0.92, speak=0.03)
        out, meta = defer.resolve(d, lambda m: called.append(m) or _directive("SPEAK"),
                                  model="frontier", margin=0.25)
        self.assertEqual(out["verdict"], "PASS")
        self.assertFalse(meta["defer_triggered"])
        self.assertEqual(called, [], "must not pay frontier cost on a confident turn")

    def test_uncertain_pass_escalates_and_uses_frontier_verdict(self):
        d = _directive("PASS", pass_c=0.45, speak=0.40)
        out, meta = defer.resolve(d, lambda m: _directive("SPEAK", speak=0.8),
                                  model="frontier", margin=0.25)
        self.assertTrue(meta["defer_triggered"])
        self.assertEqual(meta["frontier_verdict"], "SPEAK")
        self.assertEqual(out["verdict"], "SPEAK")

    def test_frontier_failure_fails_open_never_forced_pass(self):
        d = _directive("PASS", pass_c=0.45, speak=0.40)
        out, meta = defer.resolve(d, self._boom, model="frontier", margin=0.25)
        self.assertNotEqual(out["verdict"], "PASS", "provider failure must not become a silent PASS")
        self.assertEqual(meta["fallback"], "fail-open")
        self.assertIn("defer_error", meta)

    def test_frontier_garbage_also_fails_open(self):
        d = _directive("PASS", pass_c=0.45, speak=0.40)
        out, meta = defer.resolve(d, lambda m: {"nonsense": True}, model="frontier", margin=0.25)
        self.assertNotEqual(out["verdict"], "PASS")
        self.assertEqual(meta["fallback"], "fail-open")


def _model_aware_gate(cheap: dict, frontier: dict, frontier_model: str) -> str:
    """Stub nunchi-channel: returns *frontier* when NUNCHI_CLASSIFIER_MODEL is
    *frontier_model* (the escalation re-run), else *cheap*."""
    stub = textwrap.dedent(
        f"""\
        #!/usr/bin/env python3
        import sys, os
        sys.stdin.read()
        model = os.environ.get("NUNCHI_CLASSIFIER_MODEL", "")
        print({json.dumps(json.dumps(frontier))} if model == {frontier_model!r}
              else {json.dumps(json.dumps(cheap))})
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
    """End-to-end through the outbound hook: an uncertain PASS escalates and is
    allowed; with DEFER off the same cheap PASS stands."""

    _CHEAP_FLAT_PASS = {
        "verdict": "PASS", "silent": True,
        "confidences": {"PASS": 0.45, "SPEAK": 0.40, "ACK": 0.05, "ASK": 0.10},
        "reasons": ["ambiguous — not sure this is mine"],
    }
    _FRONTIER_SPEAK = {
        "verdict": "SPEAK", "silent": False,
        "confidences": {"PASS": 0.10, "SPEAK": 0.80, "ACK": 0.05, "ASK": 0.05},
        "reasons": ["on a second read this is addressed to the agent"],
    }

    def _run(self, defer_model: str):
        wrapper = _model_aware_gate(self._CHEAP_FLAT_PASS, self._FRONTIER_SPEAK, "frontier-x")
        transcript = _make_transcript([
            _user_channel_entry(chat_id="c1", message_id="A", user="zoe",
                                body="How's everyone doing tonight?", ts="2026-07-10T03:09:00Z")
        ])
        env = {"NUNCHI_CHANNEL_BIN": wrapper, "NUNCHI_HOOK_FAIL_POLICY": "closed",
               "NUNCHI_CLASSIFIER_MODEL": "cheap-x"}
        if defer_model:
            env["NUNCHI_DEFER_MODEL"] = defer_model
        return _run_hook(_hook_input(chat_id="c1", text="I'm good, Zoe.",
                                     transcript_path=transcript, session_id="s1"),
                         env_overrides=env)

    def test_defer_enabled_escalates_uncertain_pass_to_allow(self):
        rc, out, err = self._run(defer_model="frontier-x")
        self.assertIn('"permissionDecision": "allow"', out,
                      "an uncertain PASS should escalate to the frontier SPEAK and be allowed")

    def test_defer_disabled_lets_the_cheap_pass_stand(self):
        rc, out, err = self._run(defer_model="")  # no NUNCHI_DEFER_MODEL
        self.assertIn('"permissionDecision": "deny"', out,
                      "without DEFER the cheap PASS stands — proving DEFER is what changed it")


if __name__ == "__main__":
    unittest.main()
