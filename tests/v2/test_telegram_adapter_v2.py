from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from pathlib import Path

from nunchi.adapters.telegram_v2 import (
    TelegramActionSinkV2,
    TelegramChatAdapterV2,
    TelegramClientV2,
    TelegramV2Error,
)
from nunchi.mcp_discord.ratelimit import SendBackstop
from tests.v2.security.helpers import clone_policy, write_policy


CHAT = "-10042"
SELF = {"id": 9001, "is_bot": True, "username": "vigil"}


def update(update_id: int, message_id: int, text: str, date: int) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "date": date,
            "chat": {"id": int(CHAT), "type": "supergroup"},
            "from": {"id": 1001, "is_bot": False, "first_name": "Zoe"},
            "text": text,
        },
    }


class FakeTelegramClient:
    def __init__(self, batches):
        self.batches = list(batches)
        self.polls = []
        self.actions = []
        self.order = []

    def get_me(self):
        return dict(SELF)

    def get_updates(self, offset, *, timeout_seconds, limit):
        self.polls.append((offset, timeout_seconds, limit))
        return self.batches.pop(0)

    def send_message(self, chat_id, content, *, reply_to_message_id):
        self.order.append("send")
        self.actions.append(("message", chat_id, content, reply_to_message_id))
        return 500

    def set_reaction(self, chat_id, message_id, reaction):
        self.actions.append(("reaction", chat_id, message_id, reaction))


class TelegramActionCases(unittest.TestCase):
    def test_exact_reply_and_reaction_receive_transport_receipts(self):
        client = FakeTelegramClient([])
        receipts = []
        sink = TelegramActionSinkV2(
            chat_id=CHAT,
            client=client,
            backstop=SendBackstop(10, 30),
            receipt_sink=receipts.append,
        )
        sink(
            "req-1",
            {
                "kind": "message",
                "content": "hello",
                "reply_to_event_id": f"telegram:message:{CHAT}:12",
            },
        )
        sink(
            "req-2",
            {
                "kind": "reaction",
                "target_event_id": f"telegram:message:{CHAT}:12",
                "reaction": "👍",
            },
        )
        self.assertEqual(
            client.actions,
            [
                ("message", CHAT, "hello", 12),
                ("reaction", CHAT, 12, "👍"),
            ],
        )
        self.assertEqual(
            [receipt["body"]["delivery"] for receipt in receipts],
            ["sent", "sent"],
        )

    def test_cross_chat_reply_and_unrepresentable_exact_mention_fail_closed(self):
        for action in (
            {
                "kind": "message",
                "content": "hello",
                "reply_to_event_id": "telegram:message:other:12",
            },
            {
                "kind": "message",
                "content": "hello",
                "mention_actor_ids": ["telegram:user:1001"],
            },
        ):
            with self.subTest(action=action):
                client = FakeTelegramClient([])
                receipts = []
                sink = TelegramActionSinkV2(
                    chat_id=CHAT,
                    client=client,
                    backstop=SendBackstop(10, 30),
                    receipt_sink=receipts.append,
                )
                with self.assertRaises(TelegramV2Error):
                    sink("req-1", action)
                self.assertEqual(client.actions, [])
                self.assertEqual(receipts[0]["body"]["delivery"], "failed")

    def test_lost_api_response_records_unknown_not_failed(self):
        class LostResponseClient(FakeTelegramClient):
            def send_message(self, *args, **kwargs):
                super().send_message(*args, **kwargs)
                raise OSError("response lost after dispatch")

        client = LostResponseClient([])
        receipts = []
        sink = TelegramActionSinkV2(
            chat_id=CHAT,
            client=client,
            backstop=SendBackstop(10, 30),
            receipt_sink=receipts.append,
        )
        with self.assertRaises(TelegramV2Error):
            sink("req-unknown", {"kind": "message", "content": "once"})
        self.assertEqual(client.actions[0][2], "once")
        self.assertEqual(receipts[-1]["body"]["delivery"], "unknown")
        self.assertEqual(
            receipts[-1]["body"]["detail"],
            "telegram-api-outcome-unknown",
        )

    def test_malformed_success_response_records_unknown_not_sent(self):
        class MalformedResponseClient(FakeTelegramClient):
            def send_message(self, *args, **kwargs):
                super().send_message(*args, **kwargs)
                return True

        client = MalformedResponseClient([])
        receipts = []
        sink = TelegramActionSinkV2(
            chat_id=CHAT,
            client=client,
            backstop=SendBackstop(10, 30),
            receipt_sink=receipts.append,
        )
        with self.assertRaises(TelegramV2Error):
            sink("req-malformed", {"kind": "message", "content": "once"})
        self.assertEqual(client.actions[0][2], "once")
        self.assertEqual(receipts[-1]["body"]["delivery"], "unknown")

    def test_malformed_reaction_response_records_unknown_not_sent(self):
        class MalformedResponseClient(FakeTelegramClient):
            def set_reaction(self, *args, **kwargs):
                super().set_reaction(*args, **kwargs)
                return False

        client = MalformedResponseClient([])
        receipts = []
        sink = TelegramActionSinkV2(
            chat_id=CHAT,
            client=client,
            backstop=SendBackstop(10, 30),
            receipt_sink=receipts.append,
        )
        with self.assertRaises(TelegramV2Error):
            sink(
                "req-malformed-reaction",
                {
                    "kind": "reaction",
                    "target_event_id": f"telegram:message:{CHAT}:12",
                    "reaction": "👍",
                },
            )
        self.assertEqual(client.actions[0], ("reaction", CHAT, 12, "👍"))
        self.assertEqual(receipts[-1]["body"]["delivery"], "unknown")


class TelegramChatCases(unittest.TestCase):
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
        document["recoverability"]["continuity_scope_id"] = (
            f"telegram:chat:{CHAT}"
        )
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
            chat_id=CHAT,
            state=self.root / "telegram-state.json",
            poll_timeout_seconds=20,
            max_sends=10,
            send_window_seconds=30,
        )

    def test_self_identity_must_be_an_exact_bot_attestation(self):
        for identity in (
            {"id": 9001, "is_bot": False},
            {"id": 9001, "is_bot": "true"},
            {"id": "9001", "is_bot": True},
        ):
            with self.subTest(identity=identity):
                with self.assertRaises(TelegramV2Error):
                    TelegramChatAdapterV2(
                        self.arguments(),
                        client=FakeTelegramClient([]),
                        self_user=identity,
                    )

    def test_initial_tail_is_context_only_then_live_batch_uses_newest_update(self):
        client = FakeTelegramClient(
            [
                [update(2, 12, "last old message", 1000)],
                [
                    update(3, 13, "new one", 2000),
                    update(4, 14, "new two", 3000),
                ],
            ]
        )
        adapter = TelegramChatAdapterV2(
            self.arguments(),
            client=client,
            self_user=SELF,
        )
        self.addCleanup(adapter.close)
        first = adapter.poll_once()
        second = adapter.poll_once()
        self.assertEqual(first["mode"], "initial-context")
        self.assertEqual(first["results"], ())
        self.assertEqual(second["mode"], "live")
        self.assertEqual(len(second["results"]), 1)
        self.assertEqual(
            client.actions[0][2],
            f"telegram:message:{CHAT}:14",
        )
        self.assertEqual(client.polls, [(-1, 0, 1), (3, 20, 100)])

    def test_empty_initial_checkpoint_makes_next_message_live(self):
        client = FakeTelegramClient(
            [[], [update(1, 10, "first live", 1000)]]
        )
        adapter = TelegramChatAdapterV2(
            self.arguments(),
            client=client,
            self_user=SELF,
        )
        self.addCleanup(adapter.close)
        self.assertEqual(adapter.poll_once()["mode"], "initial-context")
        second = adapter.poll_once()
        self.assertEqual(second["mode"], "live")
        self.assertEqual(len(second["results"]), 1)
        self.assertEqual(client.polls[1][0], 0)

    def test_checkpoint_precedes_participant_transport_effect(self):
        seed = FakeTelegramClient([[]])
        initial = TelegramChatAdapterV2(
            self.arguments(),
            client=seed,
            self_user=SELF,
        )
        initial.poll_once()
        initial.close()
        client = FakeTelegramClient([[update(1, 10, "live", 1000)]])
        adapter = TelegramChatAdapterV2(
            self.arguments(),
            client=client,
            self_user=SELF,
        )
        self.addCleanup(adapter.close)
        original_save = adapter.cursor.save

        def save(value):
            client.order.append("checkpoint")
            original_save(value)

        adapter.cursor.save = save
        adapter.poll_once()
        self.assertEqual(client.order, ["checkpoint", "send"])


class TelegramClientCases(unittest.TestCase):
    def test_https_default_and_strict_server_json(self):
        with self.assertRaises(TelegramV2Error):
            TelegramClientV2("123:secret", api_base="http://api.example.test")
        with self.assertRaises(TelegramV2Error):
            TelegramClientV2(
                "123:secret",
                api_base="http://api.example.test",
                allow_insecure_http=True,
            )
        for payload in (
            b'{"ok":true,"result":{},"result":{}}',
            b'{"ok":true,"result":NaN}',
        ):
            with self.subTest(payload=payload):
                client = TelegramClientV2(
                    "123:secret",
                    http=lambda *_args, payload=payload: (200, payload),
                )
                with self.assertRaises(TelegramV2Error):
                    client.get_me()

    def test_plaintext_override_is_exact_loopback_only(self):
        client = TelegramClientV2(
            "123:secret",
            api_base="http://[::1]:8081",
            allow_insecure_http=True,
            http=lambda *_args: (
                200,
                b'{"ok":true,"result":{"id":9001,"is_bot":true}}',
            ),
        )
        self.assertEqual(client.get_me()["id"], 9001)
        for value in (
            "http://localhost.example.test:8081",
            "http://127.0.0.1:bad",
            "https://api.telegram.org\t",
        ):
            with self.subTest(value=value):
                with self.assertRaises(TelegramV2Error):
                    TelegramClientV2(
                        "123:secret",
                        api_base=value,
                        allow_insecure_http=True,
                    )

    def test_url_credential_is_bounded_visible_ascii(self):
        for token in ("123:secret\npath", "123:snowman-☃", "x" * 4097, 123):
            with self.subTest(token=token):
                with self.assertRaises(TelegramV2Error):
                    TelegramClientV2(token)

    def test_api_errors_never_echo_token(self):
        client = TelegramClientV2(
            "123:highly-secret",
            http=lambda *_args: (403, b'{"ok":false,"description":"no"}'),
        )
        with self.assertRaises(TelegramV2Error) as caught:
            client.get_me()
        self.assertNotIn("highly-secret", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
