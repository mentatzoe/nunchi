"""DEFER: the wake-time gate abstains on an uncertain PASS.

The corrected shape (Zoe's; team-confirmed): when the small fast gate is about
to silence an *ambiguous* bid, it declines to judge and hands the turn to the
agent's OWN model — the context is forwarded to the bigger model that already
holds the room, and that model may reply or choose silence. There is no second
classifier, no model routing, no side state: just an abstention noted in-band.

Both halves are proven here:
  * "may speak"  — an uncertain PASS does not block; the turn reaches the agent.
  * "may choose silence" — the abstention note explicitly leaves silence open,
    and nothing in the hook output manufactures or demands a reply
    (admission never carries reply prose — FORBIDDEN_REPLY_FIELDS discipline).
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile
import unittest

from tests.test_claude_code_prompt_gate import (
    _channel_prompt,
    _gate_stub_env,
    _hook_input,
    _run_hook,
)


def _uncertain_pass_directive() -> dict:
    """A PASS the gate cannot stand behind: SPEAK is within any sane margin."""
    return {
        "verdict": "PASS",
        "silent": True,
        "run_shape": "Stay silent. Post nothing to the channel for this turn.",
        "reasons": ["ambiguous — could be an open invitation"],
        "confidences": {"PASS": 0.45, "ACK": 0.05, "ASK": 0.10, "SPEAK": 0.40},
        "context_checked": [],
        "request_id": "req-defer",
        "classifier_model": "stub",
        "degraded": False,
    }


def _confident_pass_directive() -> dict:
    return {
        "verdict": "PASS",
        "silent": True,
        "run_shape": "Stay silent. Post nothing to the channel for this turn.",
        "reasons": ["clearly addressed to someone else"],
        "confidences": {"PASS": 0.92, "ACK": 0.03, "ASK": 0.02, "SPEAK": 0.03},
        "context_checked": [],
        "request_id": "req-conf",
        "classifier_model": "stub",
        "degraded": False,
    }


class DeferOnUncertainPass(unittest.TestCase):
    def _run(self, directive: dict, extra_env: dict | None = None):
        prompt = _channel_prompt(chat_id="c1", message_id="mA", user="zoe",
                                 body="How's everyone doing tonight?")
        stub_path, env = _gate_stub_env(directive)
        env["NUNCHI_HOOK_LOG"] = "/dev/null"
        if extra_env:
            env.update(extra_env)
        rc, out, err = _run_hook(_hook_input(prompt=prompt), env_overrides=env)
        os.unlink(stub_path)
        return rc, out

    def test_uncertain_pass_defers_not_blocks(self):
        """MAY SPEAK: the gate abstains — the turn reaches the agent's own model."""
        rc, out = self._run(_uncertain_pass_directive())
        self.assertEqual(rc, 0)
        parsed = json.loads(out)
        self.assertNotIn("decision", parsed, "an uncertain PASS must not block")
        note = parsed["hookSpecificOutput"]["additionalContext"]
        self.assertIn("abstains", note)

    def test_defer_note_leaves_silence_open_and_carries_no_reply(self):
        """MAY CHOOSE SILENCE: the note says silence is fine, and admission
        carries no reply prose — the gate transfers judgment, it does not
        manufacture a turn."""
        rc, out = self._run(_uncertain_pass_directive())
        note = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("silent", note.lower())
        low = note.lower()
        for demand in ("you must reply", "you should reply", "respond now"):
            self.assertNotIn(demand, low)

    def test_confident_pass_still_blocks(self):
        """DEFER is not a hole: a PASS the gate can stand behind still silences."""
        rc, out = self._run(_confident_pass_directive())
        parsed = json.loads(out)
        self.assertEqual(parsed.get("decision"), "block")

    def test_kill_switch_restores_hard_pass(self):
        """NUNCHI_DEFER=off → every PASS blocks, uncertainty ignored."""
        rc, out = self._run(_uncertain_pass_directive(), {"NUNCHI_DEFER": "off"})
        parsed = json.loads(out)
        self.assertEqual(parsed.get("decision"), "block")

    def test_margin_env_is_respected(self):
        """A tiny margin makes the same 0.45/0.40 PASS read as confident."""
        rc, out = self._run(_uncertain_pass_directive(), {"NUNCHI_DEFER_MARGIN": "0.01"})
        parsed = json.loads(out)
        self.assertEqual(parsed.get("decision"), "block")

    def test_missing_confidences_read_as_confident(self):
        """A degraded classifier (no confidences) must not widen what gets
        through: PASS without confidences blocks as before."""
        directive = _uncertain_pass_directive()
        del directive["confidences"]
        rc, out = self._run(directive)
        parsed = json.loads(out)
        self.assertEqual(parsed.get("decision"), "block")

    def _last_receipt(self, directive: dict, extra_env: dict | None = None) -> dict:
        fd, log_path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        env = {"NUNCHI_HOOK_LOG": log_path}
        if extra_env:
            env.update(extra_env)
        self._run(directive, env)
        lines = [ln for ln in pathlib.Path(log_path).read_text().splitlines() if ln.strip()]
        os.unlink(log_path)
        return json.loads(lines[-1])

    def test_defer_is_recorded_for_the_eval_arm(self):
        """Each abstention is a receipt row carrying everything the offline
        margin sweep needs: the full confidence vector, the effective margin,
        DEFER state, and the classifier identity. A defer receipt without its
        numbers cannot be swept (Aleph's blocking finding #1)."""
        rec = self._last_receipt(_uncertain_pass_directive())
        self.assertEqual(rec["action"], "defer-uncertain-pass")
        self.assertEqual(rec["verdict"], "PASS")
        self.assertEqual(
            rec["confidences"],
            {"PASS": 0.45, "ACK": 0.05, "ASK": 0.10, "SPEAK": 0.40},
            "the COMPLETE confidence vector must be receipted",
        )
        self.assertEqual(rec["defer_margin"], 0.25)
        self.assertTrue(rec["defer_enabled"])
        self.assertEqual(rec["request_id"], "req-defer")
        self.assertEqual(rec["classifier_model"], "stub")
        self.assertTrue(rec.get("envelope_sha256"),
                        "the envelope fingerprint ties the receipt to what was judged")

    def test_block_receipt_also_carries_confidences(self):
        """Hard blocks carry the same numbers, so smaller-than-deployed margins
        can be swept over observed blocks. (Larger margins still need a
        participant replay — the model never woke; see DEFER_EVAL.md.)"""
        rec = self._last_receipt(_confident_pass_directive())
        self.assertEqual(rec["action"], "block-pass")
        self.assertIn("confidences", rec)
        self.assertIn("defer_margin", rec)
        self.assertEqual(rec["request_id"], "req-conf")

    def test_exact_boundary_defers_inclusive(self):
        """Docs say "within this margin" — inclusive. PASS 0.50 vs SPEAK 0.25
        at margin 0.25 sits exactly on the boundary and must defer."""
        d = _uncertain_pass_directive()
        d["confidences"] = {"PASS": 0.50, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.25}
        rc, out = self._run(d)
        self.assertNotIn("decision", json.loads(out))

    def test_partial_confidence_map_blocks(self):
        """A map missing a verdict key is malformed evidence, not uncertainty."""
        d = _uncertain_pass_directive()
        d["confidences"] = {"PASS": 0.45, "SPEAK": 0.40}  # ACK/ASK missing
        rc, out = self._run(d)
        self.assertEqual(json.loads(out).get("decision"), "block")

    def test_non_finite_confidence_blocks(self):
        d = _uncertain_pass_directive()
        d["confidences"] = {"PASS": float("nan"), "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.4}
        rc, out = self._run(d)
        self.assertEqual(json.loads(out).get("decision"), "block")

    def test_degenerate_margins_fall_back_to_default(self):
        """inf (defer-everything), nan and negatives (defer-nothing) are
        operator error → default 0.25 applies, so this uncertain PASS defers."""
        for bad in ("inf", "nan", "-1", "2.0"):
            with self.subTest(margin=bad):
                rc, out = self._run(_uncertain_pass_directive(),
                                    {"NUNCHI_DEFER_MARGIN": bad})
                self.assertNotIn("decision", json.loads(out),
                                 f"margin {bad!r} must fall back to the sane default")

    def test_defer_note_carries_the_same_anchor_as_admits(self):
        """The path most dependent on the agent's judgment gets the same
        message/author anchor an ordinary admission carries."""
        rc, out = self._run(_uncertain_pass_directive())
        note = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("mA", note)
        self.assertIn("zoe", note)

    def test_uncertain_non_pass_is_untouched(self):
        """Uncertainty only matters when the gate would SILENCE: a wobbly SPEAK
        admits normally."""
        directive = _uncertain_pass_directive()
        directive["verdict"] = "SPEAK"
        directive["silent"] = False
        rc, out = self._run(directive)
        parsed = json.loads(out)
        self.assertNotIn("decision", parsed)
        self.assertIn("admitted", parsed["hookSpecificOutput"]["additionalContext"])


if __name__ == "__main__":
    unittest.main()
