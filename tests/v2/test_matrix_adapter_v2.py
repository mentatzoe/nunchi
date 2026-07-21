from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from pathlib import Path

from nunchi.adapters.matrix_v2 import (
    MatrixActionSinkV2,
    MatrixClientV2,
    MatrixRoomAdapterV2,
    MatrixV2Error,
)
from nunchi.mcp_discord.ratelimit import SendBackstop
from tests.v2.security.helpers import clone_policy, write_policy


ROOM = "!room:example.test"
SELF = "@vigil:example.test"


def message(event_id: str, sender: str, body: str, timestamp: int) -> dict:
    return {
        "event_id": event_id,
        "type": "m.room.message",
        "sender": sender,
        "origin_server_ts": timestamp,
        "content": {"msgtype": "m.text", "body": body},
    }


def sync(cursor: str, events: list[dict]) -> dict:
    return {
        "next_batch": cursor,
        "rooms": {"join": {ROOM: {"timeline": {"events": events}}}},
    }


class FakeMatrixClient:
    def __init__(self, batches):
        self.batches = list(batches)
        self.sync_calls = []
        self.actions = []
        self.order = []

    def whoami(self):
        return SELF

    def sync(self, since, *, timeout_ms):
        self.sync_calls.append((since, timeout_ms))
        return self.batches.pop(0)

    def send_message(
        self,
        room_id,
        transaction_id,
        content,
        *,
        reply_to_event_id,
        mention_user_ids,
    ):
        self.order.append("send")
        self.actions.append(
            (
                "message",
                room_id,
                transaction_id,
                content,
                reply_to_event_id,
                mention_user_ids,
            )
        )
        return "$sent"

    def send_reaction(
        self,
        room_id,
        transaction_id,
        target_event_id,
        reaction,
    ):
        self.actions.append(
            (
                "reaction",
                room_id,
                transaction_id,
                target_event_id,
                reaction,
            )
        )
        return "$reaction"


class MatrixActionCases(unittest.TestCase):
    def test_exact_reply_mentions_reaction_and_transport_receipts(self):
        client = FakeMatrixClient([])
        receipts = []
        sink = MatrixActionSinkV2(
            room_id=ROOM,
            client=client,
            backstop=SendBackstop(10, 30),
            receipt_sink=receipts.append,
        )
        sink(
            "req-1",
            {
                "kind": "message",
                "content": "hello",
                "reply_to_event_id": "matrix:event:$parent",
                "mention_actor_ids": [
                    "matrix:user:@zoe:example.test",
                    "matrix:user:@zoe:example.test",
                ],
            },
        )
        sink(
            "req-2",
            {
                "kind": "reaction",
                "target_event_id": "matrix:event:$parent",
                "reaction": "👍",
            },
        )
        self.assertEqual(client.actions[0][4], "$parent")
        self.assertEqual(client.actions[0][5], ("@zoe:example.test",))
        self.assertEqual(client.actions[1][3:], ("$parent", "👍"))
        self.assertEqual(
            [(item["request_id"], item["body"]["delivery"]) for item in receipts],
            [("req-1", "sent"), ("req-2", "sent")],
        )
        with self.assertRaises(MatrixV2Error):
            sink("req-1", {"kind": "message", "content": "again"})

    def test_malformed_cross_platform_identity_fails_before_api_effect(self):
        client = FakeMatrixClient([])
        receipts = []
        sink = MatrixActionSinkV2(
            room_id=ROOM,
            client=client,
            backstop=SendBackstop(10, 30),
            receipt_sink=receipts.append,
        )
        with self.assertRaises(MatrixV2Error):
            sink(
                "req-1",
                {
                    "kind": "message",
                    "content": "hello",
                    "mention_actor_ids": ["discord:user:42"],
                },
            )
        self.assertEqual(client.actions, [])
        self.assertEqual(receipts[0]["body"]["delivery"], "failed")

    def test_lost_api_response_records_unknown_not_failed(self):
        class LostResponseClient(FakeMatrixClient):
            def send_message(self, *args, **kwargs):
                super().send_message(*args, **kwargs)
                raise OSError("response lost after dispatch")

        client = LostResponseClient([])
        receipts = []
        sink = MatrixActionSinkV2(
            room_id=ROOM,
            client=client,
            backstop=SendBackstop(10, 30),
            receipt_sink=receipts.append,
        )
        with self.assertRaises(MatrixV2Error):
            sink("req-unknown", {"kind": "message", "content": "once"})
        self.assertEqual(client.actions[0][3], "once")
        self.assertEqual(receipts[-1]["body"]["delivery"], "unknown")
        self.assertEqual(
            receipts[-1]["body"]["detail"],
            "matrix-api-outcome-unknown",
        )


class MatrixRoomCases(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.root.chmod(0o700)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir(mode=0o700)
        self.receipts = self.root / "receipts"
        self.receipts.mkdir(mode=0o700)
        document = clone_policy()
        document["attention"]["preattention_enabled"] = False
        document["recoverability"]["continuity_scope_id"] = f"matrix:room:{ROOM}"
        document["recoverability"]["eligible"] = False
        document["receipt_sink"]["directory"] = str(self.receipts)
        self.policy = write_policy(self.root, document)

    def arguments(self):
        program = (
            "import json,sys; p=json.load(sys.stdin); "
            "print(json.dumps({'kind':'message','content':p['trigger_event_id']}))"
        )
        return argparse.Namespace(
            policy=self.policy,
            participant_id="vigil",
            participant_name="Vigil",
            participant_workspace=self.workspace,
            participant_timeout=30,
            participant_env=[],
            silent_participant=False,
            participant_command=[sys.executable, "-c", program],
            room_id=ROOM,
            state=self.root / "matrix-state.json",
            sync_timeout_ms=1000,
            max_sends=10,
            send_window_seconds=30,
        )

    def test_initial_batch_is_context_only_then_live_batch_coalesces_to_newest(self):
        client = FakeMatrixClient(
            [
                sync(
                    "s1",
                    [
                        message("$e1", "@zoe:example.test", "one", 1000),
                        message("$e2", "@zoe:example.test", "two", 2000),
                    ],
                ),
                sync(
                    "s2",
                    [
                        message("$e3", "@zoe:example.test", "three", 3000),
                        message("$e4", "@zoe:example.test", "four", 4000),
                    ],
                ),
            ]
        )
        adapter = MatrixRoomAdapterV2(
            self.arguments(),
            client=client,
            self_user_id=SELF,
        )
        self.addCleanup(adapter.close)
        first = adapter.poll_once()
        second = adapter.poll_once()
        self.assertEqual(first["mode"], "initial-context")
        self.assertEqual(first["results"], ())
        self.assertEqual(second["mode"], "live")
        self.assertEqual(len(second["results"]), 1)
        self.assertEqual(client.actions[0][3], "matrix:event:$e4")
        self.assertEqual(client.sync_calls, [(None, 1000), ("s1", 1000)])

    def test_checkpoint_is_persisted_before_participant_transport_effect(self):
        state = self.arguments().state
        seed = FakeMatrixClient([sync("s1", [])])
        initial = MatrixRoomAdapterV2(
            self.arguments(),
            client=seed,
            self_user_id=SELF,
        )
        initial.poll_once()
        initial.close()
        client = FakeMatrixClient(
            [
                sync(
                    "s2",
                    [message("$e2", "@zoe:example.test", "two", 2000)],
                )
            ]
        )
        arguments = self.arguments()
        arguments.state = state
        adapter = MatrixRoomAdapterV2(
            arguments,
            client=client,
            self_user_id=SELF,
        )
        self.addCleanup(adapter.close)
        original_save = adapter.cursor.save

        def save(value):
            client.order.append("checkpoint")
            original_save(value)

        adapter.cursor.save = save
        adapter.poll_once()
        self.assertEqual(client.order, ["checkpoint", "send"])


class MatrixClientCases(unittest.TestCase):
    def test_https_is_required_unless_operator_explicitly_allows_http(self):
        with self.assertRaises(MatrixV2Error):
            MatrixClientV2("http://matrix.example.test", "secret", room_id=ROOM)
        with self.assertRaises(MatrixV2Error):
            MatrixClientV2(
                "http://matrix.example.test",
                "secret",
                room_id=ROOM,
                allow_insecure_http=True,
            )
        client = MatrixClientV2(
            "http://127.0.0.1:8008",
            "secret",
            room_id=ROOM,
            allow_insecure_http=True,
            http=lambda *_args: (200, b'{"user_id":"@vigil:example.test"}'),
        )
        self.assertEqual(client.whoami(), SELF)

    def test_malformed_or_ambiguous_homeserver_is_rejected(self):
        for value, flag in (
            ("http://127.0.0.1:bad", True),
            ("http://localhost.example.test:8008", True),
            ("https://matrix.example.test\n", False),
            (123, False),
        ):
            with self.subTest(value=value):
                with self.assertRaises(MatrixV2Error):
                    MatrixClientV2(
                        value,
                        "secret",
                        room_id=ROOM,
                        allow_insecure_http=flag,
                    )

    def test_http_credential_is_bounded_visible_ascii(self):
        for token in ("secret\nheader", "snowman-☃", "x" * 4097, 123):
            with self.subTest(token=token):
                with self.assertRaises(MatrixV2Error):
                    MatrixClientV2(
                        "https://matrix.example.test",
                        token,
                        room_id=ROOM,
                    )

    def test_duplicate_or_nonfinite_server_json_is_rejected(self):
        for payload in (b'{"user_id":"a","user_id":"b"}', b'{"x":NaN}'):
            with self.subTest(payload=payload):
                client = MatrixClientV2(
                    "https://matrix.example.test",
                    "secret",
                    room_id=ROOM,
                    http=lambda *_args, payload=payload: (200, payload),
                )
                with self.assertRaises(MatrixV2Error):
                    client.whoami()


if __name__ == "__main__":
    unittest.main()
