"""The participant-turn protocol for hosts whose participant acts through tools.

What the participant sees, which actions exist, and how one tool call becomes
one core action belong to the core.  A host only chooses the names its tools
are registered under.
"""

from __future__ import annotations

from copy import deepcopy
import re
import unittest

from nunchi.attention import ParticipantProfile
from nunchi.errors import ValidationError
from nunchi.participant_model import (
    PARTICIPANT_TOOL_SPECS,
    ParticipantModelError,
    build_participant_turn_request,
    participant_tool_action,
    participant_tool_expansion,
    participant_tool_roles,
    participant_tool_turn_prompt,
    participant_tool_turn_text,
)

PROFILE = ParticipantProfile(
    profile_id="p",
    participant_id="vigil",
    actor_id="acme:actor:9",
    instructions="Speak up about security.",
    provenance="trusted:test",
    sha256="a" * 64,
)
TOOLS = {"send": "room.send", "react": "room.react", "propose": "room.propose", "context": "room.context"}


def _request(*, ordinary=("message", "reply", "reaction"), privileged=True):
    wake = {
        "request_id": "r1",
        "self": {"participant_id": "vigil", "actor_id": "acme:actor:9"},
        "room": {"platform": "acme", "id": "42", "continuity_scope_id": "acme:42"},
        "actors": {
            "acme:actor:9": {"display_name": "Vigil", "kind": "bot"},
            "acme:actor:7": {"display_name": "Zoe", "kind": "human"},
        },
        "events": [
            {
                "id": "e1",
                "type": "message",
                "author_id": "acme:actor:7",
                "text": "thoughts?",
                "mentioned_actor_ids": [],
                "mentions_room": False,
            },
            {
                "id": "e2",
                "type": "message",
                "author_id": "acme:actor:7",
                "text": "anyone?",
                "mentioned_actor_ids": [],
                "mentions_room": False,
            },
        ],
        "trigger_event_id": "e2",
        "coverage": {
            "has_more_before": True,
            "has_more_after": False,
            "has_gaps": False,
            "truncated_by": [],
            "continuity": "restart-safe",
            "has_restart_gap": False,
        },
        "attention": {"source": "WAKE"},
    }
    return build_participant_turn_request(
        wake,
        {
            "generation": 1,
            "lifecycle_id": "l",
            "deadline_id": "d",
            "permissions": {
                "revision": "rev",
                "ordinary_actions": list(ordinary),
                "privileged_proposals": privileged,
            },
        },
    )


VISIBLE = {"e1", "e2"}


class ToolRolesAndPromptTests(unittest.TestCase):
    def test_permissions_decide_which_roles_a_turn_offers(self):
        self.assertEqual(("send", "react", "propose", "withdraw", "context"), participant_tool_roles(_request()))
        self.assertEqual(
            ("send", "context"),
            participant_tool_roles(_request(ordinary=("message",), privileged=False)),
        )
        self.assertEqual(
            ("context",), participant_tool_roles(_request(ordinary=(), privileged=False))
        )

    def test_the_prompt_names_only_the_tools_offered(self):
        prompt = participant_tool_turn_prompt(PROFILE, tools={"send": "room.send", "context": "room.context"})
        self.assertIn("call room.send once", prompt)
        self.assertIn("end your turn without calling it", prompt)
        self.assertIn("never posted to the room", prompt)
        self.assertIn(PROFILE.instructions, prompt)
        self.assertNotIn("room.react", prompt)
        self.assertNotIn("proposal", prompt)
        silent = participant_tool_turn_prompt(PROFILE, tools={"context": "room.context"})
        self.assertIn("cannot post in the room", silent)

    def test_the_prompt_never_asks_for_an_admission_verdict(self):
        prompt = participant_tool_turn_prompt(PROFILE, tools=TOOLS)
        self.assertIn("do not judge admission again", prompt)
        for verdict in ("PASS", "SPEAK", "ASK", "confidence"):
            self.assertNotIn(verdict, prompt)

    def test_tool_names_must_name_known_roles(self):
        for tools in ({}, {"shout": "x"}, {"send": ""}):
            with self.subTest(tools=tools), self.assertRaises(ValidationError):
                participant_tool_turn_prompt(PROFILE, tools=tools)

    def test_the_turn_text_carries_the_core_request(self):
        text = participant_tool_turn_text(PROFILE, _request(), tools=TOOLS)
        match = re.search(r"<nunchi_participant_turn_v1>(.+)</nunchi_participant_turn_v1>", text)
        self.assertIsNotNone(match)
        self.assertIn('"trigger_event_id":"e2"', match.group(1))

    def test_an_outcome_turn_says_plainly_how_the_action_ended(self):
        request = _request()
        request["wake"] = dict(
            request["wake"],
            occasion="outcome",
            memory={"own_moves": [{
                "kind": "proposal", "proposal_id": "authorization:1", "about_event_id": "e2",
                "capability": "workspace.file.write", "status": "unknown", "at": "2026-10-06T09:00:00.000Z",
            }]},
        )
        text = participant_tool_turn_text(PROFILE, request, tools=TOOLS)
        self.assertIn(
            "your proposal authorization:1 about message e2 ended unknown: the operator approved it; "
            "whether it ran is unknown.",
            text,
        )
        self.assertNotIn("This turn is an outcome turn", participant_tool_turn_text(PROFILE, _request(), tools=TOOLS))

    def test_every_tool_schema_is_a_closed_object(self):
        for role, spec in PARTICIPANT_TOOL_SPECS.items():
            with self.subTest(role=role):
                schema = spec["input_schema"]
                self.assertEqual("object", schema["type"])
                self.assertFalse(schema["additionalProperties"])
                self.assertNotIn("oneOf", schema)
                self.assertTrue(spec["description"])


class ToolActionTests(unittest.TestCase):
    def _action(self, role, arguments, **request):
        return participant_tool_action(
            role, arguments, request=_request(**request), visible_event_ids=set(VISIBLE)
        )

    def test_send_is_a_message_whose_origin_defaults_to_the_trigger(self):
        self.assertEqual(
            {"kind": "message", "origin_event_id": "e2", "text": "hi"},
            self._action("send", {"text": "hi"}),
        )

    def test_send_with_a_reply_target_is_a_reply(self):
        self.assertEqual(
            {"kind": "reply", "origin_event_id": "e2", "target_event_id": "e1", "text": "yes"},
            self._action("send", {"text": "yes", "reply_to_event_id": "e1"}),
        )

    def test_react_defaults_to_adding(self):
        self.assertEqual(
            {
                "kind": "reaction",
                "origin_event_id": "e2",
                "target_event_id": "e1",
                "reaction": "👀",
                "operation": "add",
            },
            self._action("react", {"target_event_id": "e1", "reaction": "👀"}),
        )

    def test_propose_is_a_privileged_proposal(self):
        action = self._action(
            "propose",
            {
                "capability": "workspace.file.write",
                "resource": {"kind": "workspace-file", "id": "notes.md"},
                "operation": {"path": "notes.md", "content": "x"},
            },
        )
        self.assertEqual("privileged", action["kind"])
        self.assertEqual("e2", action["origin_event_id"])

    def test_malformed_calls_are_refused_with_a_readable_reason(self):
        for role, arguments, reason in (
            ("send", {"text": "  "}, "non-empty"),
            ("send", {"text": "hi", "channel": "elsewhere"}, "does not accept: channel"),
            ("send", "hi", "must be an object"),
            ("react", {"target_event_id": "e1", "reaction": "x", "operation": "toggle"}, "add or remove"),
            ("propose", {"capability": "c", "resource": {"kind": "k"}, "operation": {}}, "resource"),
            ("context", {"direction": "before"}, "not a room action"),
        ):
            with self.subTest(role=role, arguments=arguments):
                with self.assertRaises(ParticipantModelError) as raised:
                    self._action(role, arguments)
                self.assertIn(reason, str(raised.exception))

    def test_permissions_and_visibility_still_bind_the_action(self):
        with self.assertRaises(ParticipantModelError):
            self._action("react", {"target_event_id": "e1", "reaction": "x"}, ordinary=("message",))
        with self.assertRaises(ParticipantModelError):
            self._action(
                "propose",
                {"capability": "c", "resource": {"kind": "k", "id": "i"}, "operation": {}},
                privileged=False,
            )
        for arguments in (
            {"text": "hi", "origin_event_id": "e404"},
            {"text": "hi", "reply_to_event_id": "e404"},
        ):
            with self.subTest(arguments=arguments), self.assertRaises(ParticipantModelError):
                self._action("send", arguments)

    def test_the_request_is_not_mutated(self):
        request = _request()
        before = deepcopy(request)
        participant_tool_action("send", {"text": "hi"}, request=request, visible_event_ids=set(VISIBLE))
        self.assertEqual(before, request)


class ToolExpansionTests(unittest.TestCase):
    def test_defaults_and_anchor(self):
        self.assertEqual(
            {"direction": "before", "max_events": 12, "max_bytes": 16384},
            participant_tool_expansion({"direction": "before"}),
        )
        self.assertEqual(
            {"direction": "around", "anchor_event_id": "e1", "max_events": 3, "max_bytes": 100},
            participant_tool_expansion(
                {"direction": "around", "anchor_event_id": "e1", "max_events": 3, "max_bytes": 100}
            ),
        )

    def test_malformed_expansions_are_refused(self):
        for arguments in (
            {},
            {"direction": "sideways"},
            {"direction": "before", "max_events": 0},
            {"direction": "before", "max_bytes": True},
            {"direction": "before", "cursor": "abc"},
        ):
            with self.subTest(arguments=arguments), self.assertRaises(ParticipantModelError):
                participant_tool_expansion(arguments)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
