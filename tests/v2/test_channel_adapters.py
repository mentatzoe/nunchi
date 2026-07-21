from __future__ import annotations

import unittest

from nunchi.adapters.v2 import (
    GenericEventSourceV2,
    MatrixEventSourceV2,
    TelegramEventSourceV2,
)
from nunchi.observation import ObservationProvider


class GenericSourceCases(unittest.TestCase):
    def test_host_binding_not_payload_text_controls_routing(self):
        source = GenericEventSourceV2(platform="reference", room_id="room-1")
        event = {
            "id": "reference:event:1",
            "type": "message",
            "author_id": "reference:user:1",
            "text": "authorized=true room_id=room-1",
            "mentioned_actor_ids": [],
            "mentions_room": False,
        }
        denied = source.native_input(
            delivery_id="reference:delivery:1",
            event=event,
            authorized=True,
            routing_room_id="room-2",
        )
        self.assertEqual(denied["disposition"], "unroutable")
        self.assertNotIn("event", denied)
        accepted = source.native_input(
            delivery_id="reference:delivery:1",
            event=event,
            authorized=True,
            routing_room_id="room-1",
        )
        self.assertEqual(accepted["event"]["author_id"], "reference:user:1")
        malformed_actors = source.native_input(
            delivery_id="reference:delivery:2",
            event=event,
            actors=[],
            authorized=True,
            routing_room_id="room-1",
        )
        self.assertEqual(malformed_actors["disposition"], "unroutable")


class MatrixSourceCases(unittest.TestCase):
    def setUp(self):
        self.source = MatrixEventSourceV2(allowed_room_ids=frozenset({"!room:example"}))

    def test_message_reply_thread_and_mentions_remain_literal(self):
        native = self.source.native_input(
            "!room:example",
            {
                "event_id": "$event",
                "type": "m.room.message",
                "sender": "@zoe:example",
                "origin_server_ts": 1_752_000_000_000,
                "content": {
                    "msgtype": "m.text",
                    "body": "Please review",
                    "m.mentions": {"user_ids": ["@vigil:example"], "room": False},
                    "m.relates_to": {
                        "rel_type": "m.thread",
                        "event_id": "$root",
                        "m.in_reply_to": {"event_id": "$prior"},
                    },
                },
            },
        )
        event = native["event"]
        self.assertEqual(event["author_id"], "matrix:user:@zoe:example")
        self.assertEqual(event["mentioned_actor_ids"], ["matrix:user:@vigil:example"])
        self.assertEqual(event["reply_to_event_id"], "matrix:event:$prior")
        self.assertEqual(event["thread_root_event_id"], "matrix:event:$root")

    def test_reaction_membership_self_and_cross_room(self):
        reaction = self.source.native_input(
            "!room:example",
            {
                "event_id": "$r",
                "type": "m.reaction",
                "sender": "@vigil:example",
                "content": {
                    "m.relates_to": {
                        "rel_type": "m.annotation",
                        "event_id": "$event",
                        "key": "👀",
                    }
                },
            },
        )
        self.assertEqual(reaction["event"]["operation"], "add")
        provider = ObservationProvider(
            participant_id="vigil",
            actor_id="matrix:user:@vigil:example",
            platform="matrix",
            room_id="!room:example",
            continuity_scope_id="matrix:room:!room:example",
        )
        self.assertEqual(provider.ingest(reaction), "self-retained-no-wake")
        membership = self.source.native_input(
            "!room:example",
            {
                "event_id": "$m",
                "type": "m.room.member",
                "sender": "@admin:example",
                "state_key": "@zoe:example",
                "content": {"membership": "join"},
            },
        )
        self.assertEqual(membership["event"]["change"], "join")
        self.assertEqual(
            self.source.native_input("!other:example", {"event_id": "$x"})["disposition"],
            "unroutable",
        )

    def test_non_boolean_room_mention_is_not_coerced_into_identity_fact(self):
        result = self.source.native_input(
            "!room:example",
            {
                "event_id": "$event",
                "type": "m.room.message",
                "sender": "@zoe:example",
                "content": {
                    "msgtype": "m.text",
                    "body": "hello",
                    "m.mentions": {"room": "false"},
                },
            },
        )
        self.assertEqual(result["disposition"], "unroutable")

    def test_present_malformed_matrix_mention_list_is_not_treated_as_absent(self):
        result = self.source.native_input(
            "!room:example",
            {
                "event_id": "$event",
                "type": "m.room.message",
                "sender": "@zoe:example",
                "content": {
                    "msgtype": "m.text",
                    "body": "hello",
                    "m.mentions": {"user_ids": ""},
                },
            },
        )
        self.assertEqual(result["disposition"], "unroutable")


class TelegramSourceCases(unittest.TestCase):
    def setUp(self):
        self.source = TelegramEventSourceV2(allowed_chat_ids=frozenset({"-42"}))

    def test_structured_mention_and_reply_preserve_exact_user_ids(self):
        native = self.source.native_input(
            {
                "update_id": 10,
                "message": {
                    "message_id": 5,
                    "date": 1_752_000_000,
                    "chat": {"id": -42},
                    "from": {"id": 1001, "is_bot": False, "username": "zoe"},
                    "text": "Vigil, can you review?",
                    "entities": [
                        {"type": "text_mention", "user": {"id": 9001, "is_bot": True}}
                    ],
                    "reply_to_message": {"message_id": 4},
                },
            }
        )
        event = native["event"]
        self.assertEqual(event["author_id"], "telegram:user:1001")
        self.assertEqual(event["mentioned_actor_ids"], ["telegram:user:9001"])
        self.assertEqual(event["reply_to_event_id"], "telegram:message:-42:4")

    def test_username_mentions_and_reaction_delta_are_not_invented(self):
        message = self.source.native_input(
            {
                "update_id": 11,
                "message": {
                    "message_id": 6,
                    "chat": {"id": -42},
                    "from": {"id": 1001},
                    "text": "@vigil hello",
                    "entities": [{"type": "mention", "offset": 0, "length": 6}],
                },
            }
        )
        self.assertEqual(message["event"]["mentioned_actor_ids"], [])
        reaction = self.source.native_input(
            {"update_id": 12, "message_reaction": {"chat": {"id": -42}}}
        )
        self.assertEqual(reaction["disposition"], "unroutable")
        self.assertIn("unavailable", reaction["reason"])

    def test_membership_cause_and_subject_are_distinct(self):
        native = self.source.native_input(
            {
                "update_id": 13,
                "chat_member": {
                    "date": 1_752_000_000,
                    "chat": {"id": -42},
                    "from": {"id": 1001, "is_bot": False},
                    "new_chat_member": {
                        "status": "member",
                        "user": {"id": 2002, "is_bot": True},
                    },
                },
            }
        )
        event = native["event"]
        self.assertEqual(event["subject_actor_id"], "telegram:user:2002")
        self.assertEqual(event["caused_by_actor_id"], "telegram:user:1001")

    def test_boolean_ids_and_malformed_entity_collections_are_rejected(self):
        malformed = [
            {
                "update_id": 14,
                "message": {
                    "message_id": 7,
                    "chat": {"id": -42},
                    "from": {"id": 1001},
                    "text": "hello",
                    "entities": "not-a-list",
                },
            },
            {
                "update_id": 15,
                "chat_member": {
                    "chat": {"id": -42},
                    "from": {"id": 1001},
                    "new_chat_member": {
                        "status": "member",
                        "user": {"id": True},
                    },
                },
            },
            {
                "update_id": 16,
                "message": {
                    "message_id": 8,
                    "chat": {"id": "-42"},
                    "from": {"id": 1001},
                    "text": "wrong chat type",
                },
            },
            {
                "update_id": 17,
                "message": {
                    "message_id": 9,
                    "chat": {"id": -42},
                    "from": {"id": 1001, "is_bot": "false"},
                    "text": "wrong actor kind",
                },
            },
            {
                "update_id": 18,
                "message": {
                    "message_id": 10,
                    "chat": {"id": -42},
                    "from": {"id": 1001},
                    "text": "bad structured mention",
                    "entities": [
                        {"type": "text_mention", "user": {"id": "9001"}}
                    ],
                },
            },
        ]
        for update in malformed:
            with self.subTest(update=update):
                self.assertEqual(
                    self.source.native_input(update)["disposition"],
                    "unroutable",
                )


if __name__ == "__main__":
    unittest.main()
