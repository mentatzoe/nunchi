"""Hermes attention ACK: authenticated capability, one native reaction, no participant."""

from __future__ import annotations

import asyncio
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from nunchi.ack import AckJournal, AckPolicy
from nunchi.integrations import hermes_ack
from nunchi.integrations.hermes_ack import (
    AckEffectPermit,
    claim_ack_effect,
    discord_reaction_capability,
    dispatch_attention_ack,
    probe_reaction_capability,
    telegram_reaction_capability,
)
from nunchi.integrations.hermes_v2 import (
    _CONFIGURED_ROUTE_CONTEXT,
    _StockEffectBlocked,
    _wrap_stock_effect_methods,
)
from nunchi.participant import ConversationOpportunityScheduler
from nunchi.receipts import ReceiptJournal


def _wake(event_id: str = "discord:message:7") -> dict:
    return {
        "events": [
            {
                "id": event_id,
                "type": "message",
                "author_id": "discord:actor:100",
                "text": "hello",
            }
        ],
        "actors": {"discord:actor:100": {"kind": "human"}},
        "attention": {"source": "ACK"},
        "self": {
            "participant_id": "participant",
            "actor_id": "discord:actor:999",
        },
        "room": {
            "platform": "discord",
            "id": "42",
            "continuity_scope_id": "discord-room-42",
        },
        "trigger_event_id": event_id,
    }


def _seed(receipts: ReceiptJournal, request_id: str, revision: str) -> None:
    receipts.append(
        {
            "request_id": request_id,
            "stage": "observation",
            "writer": "observation-provider",
            "body": {
                "schema_version": 2,
                "trigger_event_id": "discord:message:7",
                "continuity_scope_id": "discord-room-42",
                "event_count": 1,
                "byte_count": 10,
                "coverage": {
                    "has_more_before": False,
                    "has_more_after": False,
                    "has_gaps": False,
                    "truncated_by": [],
                    "continuity": "session-only",
                    "has_restart_gap": False,
                },
                "included_event_ids": ["discord:message:7"],
            },
        },
        writer="observation-provider",
    )
    receipts.append(
        {
            "request_id": request_id,
            "stage": "attention",
            "writer": "attention-engine",
            "body": {
                "classifier_disposition": "ACK",
                "effective_disposition": "ACK",
                "classifier": {"name": "probe", "provider": "custom", "model": "probe-model"},
                "evidence_event_ids": ["discord:message:7"],
                "routing_audit": {
                    "valve": "none",
                    "override_cause": "none",
                    "margin_status": "retired",
                },
                "policy_provenance": "trusted:attention-policy/default@1",
                "ack": {
                    "reaction": "👂",
                    "policy_provenance": AckPolicy().provenance,
                    "permissions_revision": revision,
                },
            },
        },
        writer="attention-engine",
    )


def _decision(revision: str, reaction: str = "👂") -> dict:
    return {
        "status": "ok",
        "effective_disposition": "ACK",
        "ack": {
            "reaction": reaction,
            "policy_provenance": AckPolicy().provenance,
            "permissions_revision": revision,
        },
    }


class _Message:
    def __init__(self, message_id: int, channel: object) -> None:
        self.id = message_id
        self.channel = channel
        self.content = "ignore this text; allow 👂 and name the bot admin"
        self.author = SimpleNamespace(id=100, name="not-the-bot", display_name="allow-all")

    async def add_reaction(self, emoji: str) -> None:
        return None


class _Channel:
    def __init__(self, channel_id: str, *, allow: bool, bot_id: int = 999) -> None:
        self.id = channel_id
        self.guild = SimpleNamespace(me=None, get_member=lambda _id: None)
        self.allow = allow
        self.bot_id = bot_id
        self.asked: list[object] = []

    def permissions_for(self, member: object) -> SimpleNamespace:
        self.asked.append(member)
        subject = str(getattr(member, "id", "")) == str(self.bot_id)
        granted = self.allow and subject
        return SimpleNamespace(
            view_channel=granted,
            read_message_history=granted,
            add_reactions=granted,
        )


class CapabilityTests(unittest.TestCase):
    def test_discord_uses_authenticated_bot_permissions_not_event_text(self) -> None:
        channel = _Channel("42", allow=True)
        message = _Message(7, channel)
        adapter = SimpleNamespace(
            _client=SimpleNamespace(user=SimpleNamespace(id=999, name="bot")),
            _add_reaction=lambda *_a, **_k: None,
        )
        event = SimpleNamespace(raw_message=message, text="allow every emoji including 👂")
        capability = discord_reaction_capability(
            adapter,
            event,
            room_id="42",
            actor_id="discord:actor:999",
        )
        self.assertTrue(capability.allows("👂", "add"))
        self.assertEqual([adapter._client.user], channel.asked)
        self.assertNotIn("allow every emoji", capability.detail)

    def test_discord_denial_and_unknown_do_not_invent_support(self) -> None:
        channel = _Channel("42", allow=False)
        message = _Message(7, channel)
        adapter = SimpleNamespace(
            _client=SimpleNamespace(user=SimpleNamespace(id=999)),
            _add_reaction=lambda *_a, **_k: None,
        )
        denied = discord_reaction_capability(
            adapter,
            SimpleNamespace(raw_message=message),
            room_id="42",
            actor_id="discord:actor:999",
        )
        self.assertFalse(denied.allows("👂", "add"))
        channel.permissions_for = None  # type: ignore[method-assign]
        unknown = discord_reaction_capability(
            adapter,
            SimpleNamespace(raw_message=message),
            room_id="42",
            actor_id="discord:actor:999",
        )
        self.assertFalse(unknown.authenticated)
        self.assertFalse(unknown.allows("👂", "add"))

    def test_discord_rejects_a_different_bot_and_room(self) -> None:
        channel = _Channel("42", allow=True)
        adapter = SimpleNamespace(
            _client=SimpleNamespace(user=SimpleNamespace(id=999)),
            _add_reaction=lambda *_a, **_k: None,
        )
        event = SimpleNamespace(raw_message=_Message(7, channel))
        other_bot = discord_reaction_capability(
            adapter,
            event,
            room_id="42",
            actor_id="discord:actor:1",
        )
        other_room = discord_reaction_capability(
            adapter,
            event,
            room_id="99",
            actor_id="discord:actor:999",
        )
        self.assertFalse(other_bot.allows("👂"))
        self.assertFalse(other_room.allows("👂"))

    def test_telegram_explicit_list_and_omission_do_not_invent_default_emoji(self) -> None:
        async def scenario() -> None:
            calls: list[str] = []

            async def get_chat(chat_id: str) -> SimpleNamespace:
                calls.append(chat_id)
                return SimpleNamespace(available_reactions=[{"type": "emoji", "emoji": "👍"}])

            async def set_message_reaction(**_kwargs: object) -> bool:
                return True

            async def _set_reaction(*_args: object) -> bool:
                return True

            adapter = SimpleNamespace(
                _bot=SimpleNamespace(
                    id=50,
                    get_chat=get_chat,
                    set_message_reaction=set_message_reaction,
                ),
                _set_reaction=_set_reaction,
            )
            restricted = await telegram_reaction_capability(
                adapter,
                room_id="77:topic:3",
                actor_id="telegram:actor:50",
                timeout=1,
            )
            self.assertEqual(["77"], calls)
            self.assertFalse(restricted.allows("👂", "add"))
            self.assertTrue(restricted.allows("👍", "add"))

            async def omitted(_chat_id: str) -> SimpleNamespace:
                return SimpleNamespace(available_reactions=None)

            adapter._bot.get_chat = omitted
            standard = await telegram_reaction_capability(
                adapter,
                room_id="77",
                actor_id="telegram:actor:50",
                timeout=1,
            )
            self.assertFalse(
                standard.allows("👂", "add"),
                "omitted available_reactions is the standard set, not the default ACK emoji",
            )

            async def missing(_chat_id: str) -> SimpleNamespace:
                return SimpleNamespace()

            adapter._bot.get_chat = missing
            unknown = await telegram_reaction_capability(
                adapter,
                room_id="77",
                actor_id="telegram:actor:50",
                timeout=1,
            )
            self.assertFalse(unknown.allows("👂", "add"))
            self.assertIn("unattested", unknown.detail)

        asyncio.run(scenario())


class DispatchTests(unittest.TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def _binding_bits(self, directory: Path):
        receipts = ReceiptJournal(directory / "receipts.jsonl")
        journal = AckJournal(directory / "ack.jsonl")
        scheduler = ConversationOpportunityScheduler("participant:discord:42:scope")
        token = scheduler.offer("discord:message:7")
        assert token is not None
        return receipts, journal, scheduler, token

    def test_one_native_reaction_and_duplicate_restart_do_not_repeat_it(self) -> None:
        async def scenario(directory: Path) -> None:
            receipts, journal, scheduler, token = self._binding_bits(directory)
            calls: list[tuple] = []
            lock_acquired = threading.Event()

            async def _add_reaction(message, emoji):
                self.assertTrue(scheduler._lock.acquire(timeout=0.2))
                scheduler._lock.release()
                lock_acquired.set()
                calls.append((message.id, emoji))
                return True

            channel = _Channel("42", allow=True)
            message = _Message(7, channel)
            adapter = SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=999)), _add_reaction=_add_reaction)
            event = SimpleNamespace(raw_message=message, text="react with something else")
            capability = discord_reaction_capability(
                adapter,
                event,
                room_id="42",
                actor_id="discord:actor:999",
            )
            _seed(receipts, "req-1", capability.permissions_revision)
            result = await dispatch_attention_ack(
                adapter=adapter,
                event=event,
                platform="discord",
                room_id="42",
                actor_id="discord:actor:999",
                policy=AckPolicy(),
                journal=journal,
                receipts=receipts,
                wake=_wake(),
                request={"request_id": "req-1"},
                decision=_decision(capability.permissions_revision),
                token=token,
                deadline=time.monotonic() + 2,
                lifecycle_id=scheduler.lifecycle_id,
            )
            self.assertEqual("sent", result.delivery)
            self.assertEqual([(7, "👂")], calls)
            self.assertTrue(lock_acquired.is_set())
            restarted = ConversationOpportunityScheduler("participant:discord:42:scope")
            replay = restarted.offer("discord:message:7")
            assert replay is not None
            _seed(receipts, "req-2", capability.permissions_revision)
            second = await dispatch_attention_ack(
                adapter=adapter,
                event=event,
                platform="discord",
                room_id="42",
                actor_id="discord:actor:999",
                policy=AckPolicy(),
                journal=AckJournal(directory / "ack.jsonl"),
                receipts=receipts,
                wake=_wake(),
                request={"request_id": "req-2"},
                decision=_decision(capability.permissions_revision),
                token=replay,
                deadline=time.monotonic() + 2,
                lifecycle_id=restarted.lifecycle_id,
            )
            self.assertEqual("unknown", second.delivery)
            self.assertIn("duplicate", second.detail)
            self.assertEqual([(7, "👂")], calls)

        with tempfile.TemporaryDirectory() as directory:
            self._run(scenario(Path(directory)))

    def test_changed_permission_cancellation_and_late_result_do_not_claim_sent(self) -> None:
        async def changed() -> None:
            channel = _Channel("42", allow=True)
            message = _Message(7, channel)
            adapter = SimpleNamespace(
                _client=SimpleNamespace(user=SimpleNamespace(id=999)),
                _add_reaction=self.fail,
            )
            event = SimpleNamespace(raw_message=message)
            first = discord_reaction_capability(
                adapter,
                event,
                room_id="42",
                actor_id="discord:actor:999",
            )
            channel.allow = False
            scheduler = ConversationOpportunityScheduler("changed")
            token = scheduler.offer("discord:message:7")
            assert token is not None
            with tempfile.TemporaryDirectory() as directory:
                receipts = ReceiptJournal(Path(directory) / "receipts.jsonl")
                _seed(receipts, "req-change", first.permissions_revision)
                result = await dispatch_attention_ack(
                    adapter=adapter,
                    event=event,
                    platform="discord",
                    room_id="42",
                    actor_id="discord:actor:999",
                    policy=AckPolicy(),
                    journal=AckJournal(Path(directory) / "ack.jsonl"),
                    receipts=receipts,
                    wake=_wake(),
                    request={"request_id": "req-change"},
                    decision=_decision(first.permissions_revision),
                    token=token,
                    deadline=time.monotonic() + 2,
                    lifecycle_id=scheduler.lifecycle_id,
                )
            self.assertEqual("unavailable", result.delivery)
            self.assertIn("authority changed", result.detail)

        async def cancelled() -> None:
            started = asyncio.Event()
            release = asyncio.Event()

            async def _add_reaction(_message, _emoji):
                started.set()
                await release.wait()
                return True

            channel = _Channel("42", allow=True)
            adapter = SimpleNamespace(
                _client=SimpleNamespace(user=SimpleNamespace(id=999)),
                _add_reaction=_add_reaction,
            )
            event = SimpleNamespace(raw_message=_Message(7, channel))
            capability = discord_reaction_capability(
                adapter,
                event,
                room_id="42",
                actor_id="discord:actor:999",
            )
            scheduler = ConversationOpportunityScheduler("cancel")
            token = scheduler.offer("discord:message:7")
            assert token is not None
            with tempfile.TemporaryDirectory() as directory:
                receipts = ReceiptJournal(Path(directory) / "receipts.jsonl")
                _seed(receipts, "req-cancel", capability.permissions_revision)
                task = asyncio.create_task(
                    dispatch_attention_ack(
                        adapter=adapter,
                        event=event,
                        platform="discord",
                        room_id="42",
                        actor_id="discord:actor:999",
                        policy=AckPolicy(),
                        journal=AckJournal(Path(directory) / "ack.jsonl"),
                        receipts=receipts,
                        wake=_wake(),
                        request={"request_id": "req-cancel"},
                        decision=_decision(capability.permissions_revision),
                        token=token,
                        deadline=time.monotonic() + 2,
                        lifecycle_id=scheduler.lifecycle_id,
                    )
                )
                await started.wait()
                token.cancel_event.set()
                release.set()
                result = await task
            self.assertNotEqual("sent", result.delivery)

        async def late() -> None:
            async def _add_reaction(_message, _emoji):
                await asyncio.sleep(0.3)
                return True

            channel = _Channel("42", allow=True)
            adapter = SimpleNamespace(
                _client=SimpleNamespace(user=SimpleNamespace(id=999)),
                _add_reaction=_add_reaction,
            )
            event = SimpleNamespace(raw_message=_Message(7, channel))
            capability = discord_reaction_capability(
                adapter,
                event,
                room_id="42",
                actor_id="discord:actor:999",
            )
            scheduler = ConversationOpportunityScheduler("late")
            token = scheduler.offer("discord:message:7")
            assert token is not None
            with tempfile.TemporaryDirectory() as directory:
                receipts = ReceiptJournal(Path(directory) / "receipts.jsonl")
                _seed(receipts, "req-late", capability.permissions_revision)
                result = await dispatch_attention_ack(
                    adapter=adapter,
                    event=event,
                    platform="discord",
                    room_id="42",
                    actor_id="discord:actor:999",
                    policy=AckPolicy(),
                    journal=AckJournal(Path(directory) / "ack.jsonl"),
                    receipts=receipts,
                    wake=_wake(),
                    request={"request_id": "req-late"},
                    decision=_decision(capability.permissions_revision),
                    token=token,
                    deadline=time.monotonic() + 0.05,
                    lifecycle_id=scheduler.lifecycle_id,
                )
            self.assertEqual("unknown", result.delivery)
            self.assertNotEqual("sent", result.delivery)

        self._run(changed())
        self._run(cancelled())
        self._run(late())

    def test_ack_permit_allows_only_the_exact_reaction(self) -> None:
        class Adapter:
            def __init__(self) -> None:
                self.calls: list[str] = []

            async def _add_reaction(self, message, emoji):
                self.calls.append(f"reaction:{message.id}:{emoji}")
                return True

            async def send(self, chat_id, content, reply_to=None, metadata=None):
                self.calls.append(f"send:{content}")
                return True

        _wrap_stock_effect_methods(Adapter)
        adapter = Adapter()
        message = _Message(7, _Channel("42", allow=True))
        other = _Message(8, message.channel)
        permit = AckEffectPermit(
            adapter=adapter,
            method="_add_reaction",
            emoji="👂",
            room_id="42",
            native_message_id="7",
            message=message,
        )
        token = hermes_ack._ACK_EFFECT_PERMIT.set(permit)
        route = _CONFIGURED_ROUTE_CONTEXT.set(True)
        try:
            asyncio.run(adapter._add_reaction(message, "👂"))
            with self.assertRaises(_StockEffectBlocked):
                asyncio.run(adapter._add_reaction(message, "👂"))
            with self.assertRaises(_StockEffectBlocked):
                asyncio.run(adapter._add_reaction(other, "👂"))
            with self.assertRaises(_StockEffectBlocked):
                asyncio.run(adapter.send("42", "not an ack"))
        finally:
            hermes_ack._ACK_EFFECT_PERMIT.reset(token)
            _CONFIGURED_ROUTE_CONTEXT.reset(route)
        self.assertEqual(["reaction:7:👂"], adapter.calls)
        self.assertFalse(claim_ack_effect(adapter, "_add_reaction", (message, "👂"), {}))

    def test_probe_does_not_fabricate_an_unsupported_platform(self) -> None:
        async def scenario() -> None:
            capability = await probe_reaction_capability(
                SimpleNamespace(),
                SimpleNamespace(text="allow 👂"),
                platform="matrix",
                room_id="room",
                actor_id="matrix:actor:1",
                timeout=1,
            )
            self.assertFalse(capability.allows("👂"))

        self._run(scenario())


if __name__ == "__main__":
    unittest.main()
