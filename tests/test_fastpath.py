"""Deterministic fast-path tests — all run OFFLINE with no provider key.

The fast-path short-circuits before any provider call, so the short-circuit
cases need no network and no key. The escalation cases prove the opposite: with
no provider env set, falling through to the classifier raises the
provider-required ValidationError, which is our evidence that the fast-path did
NOT short-circuit.
"""

import unittest
from unittest.mock import patch

from tests.provider_helpers import provider_env
from nunchi import evaluate
from nunchi.errors import ValidationError

AGENT_ID = "nunchi-vigil"
AGENT_MENTION_ID = "111111111111111111"

# Empty environment: no provider key, no model, no test-result injection, and no
# fastpath opt-out. Short-circuits resolve without any of these; escalation
# raises because the classifier requires a model/key.
_OFFLINE_ENV: dict[str, str] = {}


def _request(*, trigger, context=None, agent=None, request_id="req-fastpath"):
    envelope = {
        "request_id": request_id,
        "trigger": trigger,
        "agent": agent if agent is not None else {"id": AGENT_ID, "mention_id": AGENT_MENTION_ID},
    }
    if context is not None:
        envelope["context"] = context
    return envelope


class FastPathShortCircuitTests(unittest.TestCase):
    def test_mention_to_another_id_passes_via_fastpath(self):
        request = _request(trigger={"id": "t-elsewhere", "content": "hey <@999> can you take this?"})
        with patch.dict("os.environ", _OFFLINE_ENV, clear=True):
            result = evaluate(request)

        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["classifier"], "product")
        self.assertEqual(result["classifier_provider"], "fastpath")
        self.assertNotIn("classifier_model", result)
        self.assertEqual(result["confidences"], {"PASS": 1.0, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.0})
        self.assertEqual(result["context_checked"], ["trigger:t-elsewhere"])
        self.assertTrue(result["reasons"])
        self.assertEqual(result["request_id"], "req-fastpath")

    def test_self_echo_by_author_passes_via_fastpath(self):
        request = _request(
            trigger={"id": "t-self", "author": AGENT_ID, "content": "Posting my status update."},
        )
        with patch.dict("os.environ", _OFFLINE_ENV, clear=True):
            result = evaluate(request)

        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["classifier_provider"], "fastpath")
        self.assertEqual(result["context_checked"], ["trigger:t-self"])

    def test_self_echo_by_content_match_passes_via_fastpath(self):
        request = _request(
            trigger={"id": "t-echo", "author": "discord-relay", "content": "  Build is green on main.  "},
            context=[
                {"id": "ctx-mine", "author": AGENT_ID, "content": "Build is green on main."},
                {"id": "ctx-other", "author": "peer", "content": "Thanks for the update."},
            ],
        )
        with patch.dict("os.environ", _OFFLINE_ENV, clear=True):
            result = evaluate(request)

        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["classifier_provider"], "fastpath")
        self.assertEqual(result["context_checked"], ["trigger:t-echo", "context:ctx-mine"])

    def test_mention_including_this_agent_escalates(self):
        # Mentions another id AND this agent's mention_id -> addressing is for us;
        # not certain -> escalate. With no provider env, escalation raises.
        request = _request(
            trigger={"id": "t-us", "content": f"hey <@999> and <@{AGENT_MENTION_ID}> please sync"},
        )
        with patch.dict("os.environ", _OFFLINE_ENV, clear=True):
            with self.assertRaises(ValidationError):
                evaluate(request)

    def test_ambiguous_no_mention_escalates(self):
        # Plain room-addressable question, no mention, not self -> not certain.
        request = _request(trigger={"id": "t-q", "content": "What is the rollout plan for next week?"})
        with patch.dict("os.environ", _OFFLINE_ENV, clear=True):
            with self.assertRaises(ValidationError):
                evaluate(request)

    def test_no_agent_cannot_determine_addressing_escalates(self):
        # Mention present but agent unknown -> cannot decide addressing -> escalate.
        request = _request(trigger={"id": "t-noagent", "content": "hey <@999> ping"}, agent={})
        with patch.dict("os.environ", _OFFLINE_ENV, clear=True):
            with self.assertRaises(ValidationError):
                evaluate(request)


class FastPathAliasTests(unittest.TestCase):
    """agent.aliases joins the identity bundle for both fast-path rules.

    Tonight's live failure class: a runner whose configured mention_id was
    the display name ("vigil") PASSed a direct <@snowflake> mention because
    the snowflake matched none of its known identities. With the snowflake
    (or any other identity) listed in aliases, the mention-aimed-elsewhere
    short-circuit must NOT fire.
    """

    ALIAS_SNOWFLAKE = "222222222222222222"

    def _agent(self, aliases):
        return {"id": AGENT_ID, "mention_id": AGENT_MENTION_ID, "aliases": aliases}

    def test_mention_of_our_alias_snowflake_does_not_shortcut(self):
        # The mention token is one of OUR aliases -> addressed to us -> must
        # escalate to the classifier (which raises offline), never PASS.
        request = _request(
            trigger={"id": "t-alias-mention", "content": f"hey <@{self.ALIAS_SNOWFLAKE}> please review"},
            agent=self._agent(["Vigil", self.ALIAS_SNOWFLAKE]),
        )
        with patch.dict("os.environ", _OFFLINE_ENV, clear=True):
            with self.assertRaises(ValidationError):
                evaluate(request)

    def test_mention_elsewhere_still_passes_with_aliases_present(self):
        # Aliases present but the mentioned id is foreign -> short-circuit intact.
        request = _request(
            trigger={"id": "t-foreign", "content": "hey <@999> can you take this?"},
            agent=self._agent(["Vigil", self.ALIAS_SNOWFLAKE]),
        )
        with patch.dict("os.environ", _OFFLINE_ENV, clear=True):
            result = evaluate(request)

        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["classifier_provider"], "fastpath")

    def test_self_echo_by_alias_author_passes_via_fastpath(self):
        # A relay may report the author under the agent's display/profile name.
        request = _request(
            trigger={"id": "t-alias-self", "author": "Aether", "content": "Posting my status update."},
            agent=self._agent(["Aether"]),
        )
        with patch.dict("os.environ", _OFFLINE_ENV, clear=True):
            result = evaluate(request)

        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["classifier_provider"], "fastpath")
        self.assertEqual(result["context_checked"], ["trigger:t-alias-self"])

    def test_self_echo_by_alias_context_content_match_passes_via_fastpath(self):
        request = _request(
            trigger={"id": "t-alias-echo", "author": "discord-relay", "content": "Build is green on main."},
            context=[{"id": "ctx-alias-mine", "author": "Aether", "content": "Build is green on main."}],
            agent=self._agent(["Aether"]),
        )
        with patch.dict("os.environ", _OFFLINE_ENV, clear=True):
            result = evaluate(request)

        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["classifier_provider"], "fastpath")
        self.assertEqual(result["context_checked"], ["trigger:t-alias-echo", "context:ctx-alias-mine"])

    def test_author_matching_mention_id_without_aliases_still_escalates(self):
        # Backward-compat guard: without aliases, self-echo compares the author
        # against agent.id ALONE (mention_id never joined that set); behavior
        # must stay identical to pre-alias releases.
        request = _request(
            trigger={"id": "t-mention-author", "author": AGENT_MENTION_ID, "content": "status update"},
        )
        with patch.dict("os.environ", _OFFLINE_ENV, clear=True):
            with self.assertRaises(ValidationError):
                evaluate(request)


class FastPathDisabledTests(unittest.TestCase):
    def test_test_result_injection_bypasses_fastpath(self):
        # A would-be fast-path envelope (mention elsewhere) MUST yield the injected
        # SPEAK, proving injection mode disables the fast-path entirely.
        request = _request(trigger={"id": "t-inject", "content": "hey <@999> handle this"})
        env = provider_env("SPEAK", checked=["trigger:t-inject"])
        with patch.dict("os.environ", env, clear=True):
            result = evaluate(request)

        self.assertEqual(result["verdict"], "SPEAK")
        self.assertEqual(result["classifier"], "product")
        self.assertNotEqual(result.get("classifier_provider"), "fastpath")

    def test_fastpath_disabled_flag_escalates(self):
        # NUNCHI_FASTPATH=0 opts out: the same mention-elsewhere envelope now
        # escalates to the classifier (which raises with no provider env).
        request = _request(trigger={"id": "t-off", "content": "hey <@999> handle this"})
        with patch.dict("os.environ", {"NUNCHI_FASTPATH": "0"}, clear=True):
            with self.assertRaises(ValidationError):
                evaluate(request)


if __name__ == "__main__":
    unittest.main()
