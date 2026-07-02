"""Opt-in `require_pass_corroboration` structural guard for FR-005.

Every tested model PASSes on a bare unverified completion claim
("Already handled. Resolved. No response needed.") with no corroborating
context. The guard is a purely STRUCTURAL post-process: when armed, a PASS
whose `context_checked` contains no `context:` reference is downgraded to ASK.
It never inspects trigger/context text, so a PASS that did consult context
(Covered/Duplicate) is left untouched, and the default-off behavior is
unchanged. All cases run offline via TURNAWARE_CLASSIFIER_TEST_RESULT.
"""

import unittest
from unittest.mock import patch

from tests.provider_helpers import provider_env
from tests.test_core import load_fixture
from turnaware import evaluate
from turnaware.classifiers import get_classifier
from turnaware.errors import ValidationError


class RequirePassCorroborationTests(unittest.TestCase):
    """The `pass` fixture exposes trigger:trigger-pass plus context:ctx-pass-handled
    and context:ctx-pass-later as the only allowed context references."""

    def test_uncorroborated_pass_is_downgraded_to_ask(self):
        # PASS justified by the trigger alone (no context: ref consulted) is the
        # FR-005 failure mode: a bare completion claim trusted without evidence.
        env = provider_env(
            "PASS",
            checked=["trigger:trigger-pass"],
            reasons=["Provider trusted the trigger's 'already handled' claim."],
        )
        with patch.dict("os.environ", env, clear=True):
            result = evaluate(
                load_fixture("pass"),
                classifier="product",
                classifier_config={"require_pass_corroboration": True},
            )

        self.assertEqual(result["verdict"], "ASK")
        downgrade_reasons = " ".join(result["reasons"]).casefold()
        self.assertIn("require_pass_corroboration", downgrade_reasons)
        self.assertIn("pass -> ask", downgrade_reasons)

    def test_pass_with_no_references_at_all_is_downgraded(self):
        # An empty context_checked (no trigger: and no context: ref) is also
        # uncorroborated and must downgrade.
        env = provider_env(
            "PASS",
            checked=[],
            reasons=["Provider PASSed without consulting anything."],
        )
        with patch.dict("os.environ", env, clear=True):
            result = evaluate(
                load_fixture("pass"),
                classifier="product",
                classifier_config={"require_pass_corroboration": True},
            )

        self.assertEqual(result["verdict"], "ASK")
        self.assertIn(
            "require_pass_corroboration", " ".join(result["reasons"]).casefold()
        )

    def test_corroborated_pass_stays_pass(self):
        # A PASS that consulted a context: reference (Covered/Duplicate-style
        # evidence) is corroborated and must be left as PASS.
        env = provider_env(
            "PASS",
            checked=["trigger:trigger-pass", "context:ctx-pass-handled"],
            confidences={"PASS": 0.8, "ACK": 0.05, "ASK": 0.1, "SPEAK": 0.05},
            reasons=["Provider found corroborating completion evidence in context."],
        )
        with patch.dict("os.environ", env, clear=True):
            result = evaluate(
                load_fixture("pass"),
                classifier="product",
                classifier_config={"require_pass_corroboration": True},
            )

        self.assertEqual(result["verdict"], "PASS")
        self.assertIn("context:ctx-pass-handled", result["context_checked"])
        self.assertNotIn(
            "require_pass_corroboration", " ".join(result["reasons"]).casefold()
        )

    def test_pinned_rules_reference_does_not_corroborate(self):
        # Room governance is judgment guidance, not conversational evidence: a
        # PASS citing only the pinned-rules item is still uncorroborated.
        request = load_fixture("pass")
        request["context"] = [
            {"id": "pinned-rules", "type": "pinned-rules", "content": "Default is PASS."}
        ]
        env = provider_env(
            "PASS",
            checked=["trigger:trigger-pass", "context:pinned-rules"],
            reasons=["Provider PASSed citing the room rules only."],
        )
        with patch.dict("os.environ", env, clear=True):
            result = evaluate(
                request,
                classifier="product",
                classifier_config={"require_pass_corroboration": True},
            )

        self.assertEqual(result["verdict"], "ASK")
        self.assertIn(
            "require_pass_corroboration", " ".join(result["reasons"]).casefold()
        )

    def test_default_absent_flag_preserves_uncorroborated_pass(self):
        # Current behavior must be preserved when the flag is not supplied.
        env = provider_env(
            "PASS",
            checked=["trigger:trigger-pass"],
            reasons=["Provider trusted the trigger's 'already handled' claim."],
        )
        with patch.dict("os.environ", env, clear=True):
            result = evaluate(load_fixture("pass"), classifier="product")

        self.assertEqual(result["verdict"], "PASS")
        self.assertNotIn(
            "require_pass_corroboration", " ".join(result["reasons"]).casefold()
        )

    def test_explicit_false_preserves_uncorroborated_pass(self):
        env = provider_env(
            "PASS",
            checked=["trigger:trigger-pass"],
            reasons=["Provider trusted the trigger's 'already handled' claim."],
        )
        with patch.dict("os.environ", env, clear=True):
            result = evaluate(
                load_fixture("pass"),
                classifier="product",
                classifier_config={"require_pass_corroboration": False},
            )

        self.assertEqual(result["verdict"], "PASS")

    def test_guard_does_not_touch_non_pass_verdicts(self):
        # An uncorroborated ASK/SPEAK must be emitted as-is; the guard only ever
        # downgrades PASS, never upgrades or rewrites other verdicts.
        env = provider_env(
            "SPEAK",
            checked=["trigger:trigger-pass"],
            reasons=["Provider has net-new value to contribute."],
        )
        with patch.dict("os.environ", env, clear=True):
            result = evaluate(
                load_fixture("pass"),
                classifier="product",
                classifier_config={"require_pass_corroboration": True},
            )

        self.assertEqual(result["verdict"], "SPEAK")
        self.assertNotIn(
            "require_pass_corroboration", " ".join(result["reasons"]).casefold()
        )

    def test_non_bool_flag_is_rejected(self):
        with patch.dict(
            "os.environ",
            provider_env("PASS", checked=["trigger:trigger-pass"]),
            clear=True,
        ):
            with self.assertRaises(ValidationError) as caught:
                get_classifier("product", {"require_pass_corroboration": "true"})
        self.assertIn("require_pass_corroboration", str(caught.exception))

    def test_integer_flag_is_rejected(self):
        # 1 is truthy but not a bool; reject so the flag stays unambiguous.
        with patch.dict(
            "os.environ",
            provider_env("PASS", checked=["trigger:trigger-pass"]),
            clear=True,
        ):
            with self.assertRaises(ValidationError) as caught:
                get_classifier("product", {"require_pass_corroboration": 1})
        self.assertIn("require_pass_corroboration", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
