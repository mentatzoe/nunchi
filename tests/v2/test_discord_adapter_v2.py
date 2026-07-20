from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from nunchi.adapters.discord_v2 import (
    DiscordAdapterV2Error,
    DiscordRoomAdapterV2,
    message_event_from_discord,
)
from nunchi.mcp_discord.events import MessageEvent
from tests.v2.security.helpers import clone_policy, write_policy


CHANNEL = "42"
SELF = "9001"


def event(message_id: str, author_id: str, content: str) -> MessageEvent:
    return MessageEvent(
        guild_id="7",
        channel_id=CHANNEL,
        message_id=message_id,
        author_id=author_id,
        author_name="Zoe" if author_id != SELF else "Vigil",
        author_is_bot=author_id == SELF,
        content=content,
        timestamp=f"2026-07-20T12:00:{int(message_id):02d}Z",
        mentioned_user_ids=(),
        reply_to_message_id=None,
        reply_to_author_id=None,
        reply_to_author_name=None,
        reply_to_author_is_bot=None,
        reply_to_content=None,
    )


class FakeRest:
    def __init__(self):
        self.messages = []
        self.reactions = []

    def create_message(self, channel_id, content, **kwargs):
        self.messages.append((channel_id, content, kwargs))
        return {"id": "100"}

    def create_reaction(self, channel_id, message_id, reaction):
        self.reactions.append((channel_id, message_id, reaction))


class DiscordRoomCases(unittest.TestCase):
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
            f"discord:channel:{CHANNEL}"
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
            channel_id=CHANNEL,
            blocked_actor_id=[],
            max_sends=10,
            send_window_seconds=30,
        )

    def test_backfill_is_context_only_and_live_message_acts_directly(self):
        rest = FakeRest()
        adapter = DiscordRoomAdapterV2(
            self.arguments(),
            self_user_id=SELF,
            rest=rest,
        )
        self.addCleanup(adapter.close)
        dispositions = adapter.observe_history(
            [event("1", "1001", "old one"), event("2", "1001", "old two")]
        )
        self.assertEqual(dispositions, ("observed", "observed"))
        self.assertEqual(rest.messages, [])
        result = adapter.process_message(event("3", "1001", "live"))
        self.assertEqual(len(result), 1)
        self.assertEqual(rest.messages[0][1], "discord:message:3")

    def test_exact_self_echo_is_retained_without_wake_or_send(self):
        rest = FakeRest()
        adapter = DiscordRoomAdapterV2(
            self.arguments(),
            self_user_id=SELF,
            rest=rest,
        )
        self.addCleanup(adapter.close)
        self.assertEqual(
            adapter.process_message(event("1", SELF, "self echo")),
            (),
        )
        self.assertEqual(rest.messages, [])

    def test_policy_cannot_claim_restart_safe_suppression(self):
        document = clone_policy()
        document["attention"]["preattention_enabled"] = False
        document["recoverability"]["continuity_scope_id"] = (
            f"discord:channel:{CHANNEL}"
        )
        document["recoverability"]["eligible"] = True
        document["receipt_sink"]["directory"] = str(self.receipts)
        write_policy(self.root, document)
        with self.assertRaises(RuntimeError):
            DiscordRoomAdapterV2(
                self.arguments(),
                self_user_id=SELF,
                rest=FakeRest(),
            )


class DiscordProjectionCases(unittest.TestCase):
    def test_discord_object_projection_uses_exact_ids_and_rich_text(self):
        message = SimpleNamespace(
            id=111,
            channel=SimpleNamespace(id=42),
            guild=SimpleNamespace(id=7),
            author=SimpleNamespace(id=1001, name="Zoe", bot=False),
            content="",
            embeds=[],
            attachments=[
                SimpleNamespace(filename="report.pdf", description="Review report")
            ],
            components=[],
            stickers=[],
            reference=SimpleNamespace(message_id=99),
            created_at=datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc),
            mentions=[SimpleNamespace(id=9001)],
            mention_everyone=False,
        )
        projected = message_event_from_discord(message)
        self.assertEqual(projected.channel_id, "42")
        self.assertEqual(projected.author_id, "1001")
        self.assertEqual(projected.reply_to_message_id, "99")
        self.assertEqual(projected.mentioned_user_ids, ("9001",))
        self.assertIn("Review report", projected.content)

    def test_malformed_native_identity_is_rejected_without_text_fallback(self):
        message = SimpleNamespace(
            id="../bad",
            channel=SimpleNamespace(id=42),
            author=SimpleNamespace(id=1001),
        )
        with self.assertRaises(DiscordAdapterV2Error):
            message_event_from_discord(message)


if __name__ == "__main__":
    unittest.main()
