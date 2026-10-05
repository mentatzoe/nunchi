"""Hermes attention ACK: authenticated capability, one native reaction, no participant."""

from __future__ import annotations

import asyncio
import fcntl
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from nunchi.ack import AckJournal, AckPolicy
from nunchi.integrations import hermes_ack
from nunchi.integrations.hermes_ack import (
    AckAuthorityClosed,
    AckEffectPermit,
    ack_effects_quiescent,
    claim_ack_effect,
    discord_reaction_capability,
    dispatch_attention_ack,
    drain_ack_ownership,
    probe_reaction_capability,
    telegram_reaction_capability,
)
from nunchi.integrations.hermes_v2 import (
    _CONFIGURED_ROUTE_CONTEXT,
    _RoomRuntime,
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
                    "policy_provenance": AckPolicy(enabled=True).provenance,
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
            "policy_provenance": AckPolicy(enabled=True).provenance,
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
                policy=AckPolicy(enabled=True),
                journal=journal,
                receipts=receipts,
                wake=_wake(),
                request={"request_id": "req-1"},
                decision=_decision(capability.permissions_revision),
                token=token,
                deadline=time.monotonic() + 2,
                lifecycle_id=scheduler.lifecycle_id,
                scheduler=scheduler,
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
                policy=AckPolicy(enabled=True),
                journal=AckJournal(directory / "ack.jsonl"),
                receipts=receipts,
                wake=_wake(),
                request={"request_id": "req-2"},
                decision=_decision(capability.permissions_revision),
                token=replay,
                deadline=time.monotonic() + 2,
                lifecycle_id=restarted.lifecycle_id,
                scheduler=restarted,
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
                    policy=AckPolicy(enabled=True),
                    journal=AckJournal(Path(directory) / "ack.jsonl"),
                    receipts=receipts,
                    wake=_wake(),
                    request={"request_id": "req-change"},
                    decision=_decision(first.permissions_revision),
                    token=token,
                    deadline=time.monotonic() + 2,
                    lifecycle_id=scheduler.lifecycle_id,
                    scheduler=scheduler,
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
                        policy=AckPolicy(enabled=True),
                        journal=AckJournal(Path(directory) / "ack.jsonl"),
                        receipts=receipts,
                        wake=_wake(),
                        request={"request_id": "req-cancel"},
                        decision=_decision(capability.permissions_revision),
                        token=token,
                        deadline=time.monotonic() + 2,
                        lifecycle_id=scheduler.lifecycle_id,
                        scheduler=scheduler,
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
                    policy=AckPolicy(enabled=True),
                    journal=AckJournal(Path(directory) / "ack.jsonl"),
                    receipts=receipts,
                    wake=_wake(),
                    request={"request_id": "req-late"},
                    decision=_decision(capability.permissions_revision),
                    token=token,
                    deadline=time.monotonic() + 0.05,
                    lifecycle_id=scheduler.lifecycle_id,
                    scheduler=scheduler,
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
        scheduler = ConversationOpportunityScheduler("permit")
        opportunity = scheduler.offer("discord:message:7")
        assert opportunity is not None
        permit = AckEffectPermit(
            adapter=adapter,
            method="_add_reaction",
            emoji="👂",
            room_id="42",
            native_message_id="7",
            message=message,
            scheduler=scheduler,
            token=opportunity,
            deadline=time.monotonic() + 5,
        )
        context = hermes_ack._ACK_EFFECT_PERMIT.set(permit)
        route = _CONFIGURED_ROUTE_CONTEXT.set(True)
        try:
            asyncio.run(adapter._add_reaction(message, "👂"))
            with self.assertRaises(AckAuthorityClosed):
                asyncio.run(adapter._add_reaction(message, "👂"))
            with self.assertRaises(AckAuthorityClosed):
                asyncio.run(adapter._add_reaction(other, "👂"))
            with self.assertRaises(AckAuthorityClosed):
                asyncio.run(adapter.send("42", "not an ack"))
        finally:
            hermes_ack._ACK_EFFECT_PERMIT.reset(context)
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


class CommitBoundaryTests(unittest.TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def _adapter(self, reaction):
        class Adapter:
            def __init__(self) -> None:
                self.calls: list[tuple] = []
                self._client = SimpleNamespace(user=SimpleNamespace(id=999))

            async def _add_reaction(self, message, emoji):
                return await reaction(self, message, emoji)

        _wrap_stock_effect_methods(Adapter)
        return Adapter()

    async def _dispatch(self, adapter, scheduler, token, deadline, directory, request_id):
        dispatch, journal = self._prepare_dispatch(
            adapter, scheduler, token, directory, request_id
        )
        return await dispatch(deadline), journal

    def _prepare_dispatch(
        self, adapter, scheduler, token, directory, request_id,
        *, room_id="42", message_id=7,
    ):
        # Synchronous receipt seeding is fixture setup, not ACK dispatch latency.
        event = SimpleNamespace(raw_message=_Message(message_id, _Channel(room_id, allow=True)))
        capability = discord_reaction_capability(
            adapter, event, room_id=room_id, actor_id="discord:actor:999",
        )
        receipts = ReceiptJournal(Path(directory) / "receipts.jsonl")
        journal = AckJournal(Path(directory) / "ack.jsonl")
        _seed(receipts, request_id, capability.permissions_revision)
        wake = _wake(f"discord:message:{message_id}")
        wake["room"]["id"] = room_id
        wake["room"]["continuity_scope_id"] = f"discord-room-{room_id}"

        async def dispatch(deadline):
            route = _CONFIGURED_ROUTE_CONTEXT.set(True)
            try:
                return await dispatch_attention_ack(
                    adapter=adapter,
                    event=event,
                    platform="discord",
                    room_id=room_id,
                    actor_id="discord:actor:999",
                    policy=AckPolicy(enabled=True),
                    journal=journal,
                    receipts=receipts,
                    wake=wake,
                    request={"request_id": request_id},
                    decision=_decision(capability.permissions_revision),
                    token=token,
                    deadline=deadline,
                    lifecycle_id=scheduler.lifecycle_id,
                    scheduler=scheduler,
                )
            finally:
                _CONFIGURED_ROUTE_CONTEXT.reset(route)

        return dispatch, journal

    def _observe_journal_call(self, journal, method):
        """Signal actual worker entry/return without replacing persistence."""
        entered = asyncio.Event()
        returned = threading.Event()
        loop = asyncio.get_running_loop()
        original = getattr(journal, method)

        def observed(*args, **kwargs):
            loop.call_soon_threadsafe(entered.set)
            try:
                return original(*args, **kwargs)
            finally:
                returned.set()

        setattr(journal, method, observed)
        return entered, returned

    async def _assert_wait_progress(self, entered, returned):
        began = time.monotonic()
        await asyncio.wait_for(entered.wait(), 0.5)
        await asyncio.sleep(0)  # a loop turn after the real journal call starts
        self.assertLess(time.monotonic() - began, 0.5)
        self.assertFalse(returned.is_set(), "journal call blocked the event loop")

    def test_cancel_before_native_entry_makes_zero_calls(self) -> None:
        async def scenario() -> None:
            calls: list[tuple] = []

            async def reaction(_self, message, emoji):
                calls.append((message.id, emoji))
                return True

            adapter = self._adapter(reaction)
            scheduler = ConversationOpportunityScheduler("cancel-before")
            token = scheduler.offer("discord:message:7")
            assert token is not None
            with tempfile.TemporaryDirectory() as directory:
                asyncio.get_running_loop().call_soon(scheduler.cancel)
                result, _journal = await self._dispatch(
                    adapter,
                    scheduler,
                    token,
                    time.monotonic() + 2,
                    directory,
                    "req-cancel-before",
                )
            self.assertEqual([], calls)
            self.assertEqual("failed", result.delivery)
            self.assertNotEqual("sent", result.delivery)

        self._run(scenario())

    def test_expiry_before_native_entry_makes_zero_calls(self) -> None:
        async def scenario() -> None:
            calls: list[tuple] = []

            async def reaction(_self, message, emoji):
                calls.append((message.id, emoji))
                return True

            adapter = self._adapter(reaction)
            scheduler = ConversationOpportunityScheduler("expiry-before")
            token = scheduler.offer("discord:message:7")
            assert token is not None
            deadline = time.monotonic() + 0.15
            with tempfile.TemporaryDirectory() as directory:
                asyncio.get_running_loop().call_soon(time.sleep, 0.3)
                result, _journal = await self._dispatch(
                    adapter,
                    scheduler,
                    token,
                    deadline,
                    directory,
                    "req-expiry-before",
                )
            self.assertEqual([], calls)
            self.assertNotEqual("sent", result.delivery)
            self.assertTrue(time.monotonic() >= deadline)

        self._run(scenario())

    def test_stale_permit_fails_closed_without_route_context(self) -> None:
        async def reaction(adapter, message, emoji):
            adapter.calls.append((message.id, emoji))
            return True

        adapter = self._adapter(reaction)
        scheduler = ConversationOpportunityScheduler("stale")
        token = scheduler.offer("discord:message:7")
        assert token is not None
        message = _Message(7, _Channel("42", allow=True))
        permit = AckEffectPermit(
            adapter=adapter,
            method="_add_reaction",
            emoji="👂",
            room_id="42",
            native_message_id="7",
            message=message,
            scheduler=scheduler,
            token=token,
            deadline=time.monotonic() - 1,
        )
        context = hermes_ack._ACK_EFFECT_PERMIT.set(permit)
        try:
            with self.assertRaises(AckAuthorityClosed):
                self._run(adapter._add_reaction(message, "👂"))
        finally:
            hermes_ack._ACK_EFFECT_PERMIT.reset(context)
        self.assertEqual([], adapter.calls)

    def test_cancel_ordered_before_effect_commit_prevents_it(self) -> None:
        scheduler = ConversationOpportunityScheduler("order")
        token = scheduler.offer("discord:message:7")
        assert token is not None
        entered = threading.Event()
        release = threading.Event()

        def hold_then_cancel() -> None:
            with scheduler._lock:
                entered.set()
                release.wait()
                scheduler.cancel()

        holder = threading.Thread(target=hold_then_cancel)
        holder.start()
        entered.wait()
        outcome: list[bool] = []

        def try_commit() -> None:
            outcome.append(
                scheduler.authorize_effect_commit(
                    token,
                    deadline=time.monotonic() + 5,
                )
            )

        worker = threading.Thread(target=try_commit)
        worker.start()
        time.sleep(0.02)
        release.set()
        holder.join()
        worker.join()
        self.assertEqual([False], outcome)

    def test_parent_cancel_stops_cooperative_child_and_owns_resistant_child(self) -> None:
        async def scenario() -> None:
            calls: list[tuple] = []
            entered = asyncio.Event()
            release = asyncio.Event()
            child: list[asyncio.Task] = []

            async def reaction(_self, message, emoji):
                child.append(asyncio.current_task())
                entered.set()
                await release.wait()
                calls.append((message.id, emoji))
                return True

            adapter = self._adapter(reaction)
            scheduler = ConversationOpportunityScheduler("parent-cancel")
            token = scheduler.offer("discord:message:7")
            assert token is not None
            with tempfile.TemporaryDirectory() as directory:
                task = asyncio.create_task(
                    self._dispatch(
                        adapter,
                        scheduler,
                        token,
                        time.monotonic() + 2,
                        directory,
                        "req-parent-cancel",
                    )
                )
                await entered.wait()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                self.assertTrue(child[0].done())
                self.assertEqual([], calls)
                await asyncio.sleep(max(0, 0.05))
                self.assertTrue(child[0].done())
                self.assertEqual([], calls)
                self.assertTrue(await drain_ack_ownership())

            resistant_calls: list[tuple] = []
            resistant_entered = asyncio.Event()
            resistant_release = asyncio.Event()
            resistant_child: list[asyncio.Task] = []

            async def resistant(_self, message, emoji):
                resistant_child.append(asyncio.current_task())
                resistant_entered.set()
                while not resistant_release.is_set():
                    try:
                        await asyncio.sleep(0.01)
                    except asyncio.CancelledError:
                        pass
                resistant_calls.append((message.id, emoji))
                return True

            resistant_adapter = self._adapter(resistant)
            resistant_scheduler = ConversationOpportunityScheduler("resistant")
            resistant_token = resistant_scheduler.offer("discord:message:7")
            assert resistant_token is not None
            runtime = SimpleNamespace(
                cancel=lambda: None,
                _settlement_changed=threading.Condition(),
                _active_trace=None,
                _processing_traces=set(),
                _detached_stock_tasks=set(),
            )
            with tempfile.TemporaryDirectory() as directory:
                owner = asyncio.create_task(
                    self._dispatch(
                        resistant_adapter,
                        resistant_scheduler,
                        resistant_token,
                        time.monotonic() + 0.2,
                        directory,
                        "req-resistant",
                    )
                )
                await resistant_entered.wait()
                owner.cancel()
                try:
                    await owner
                except asyncio.CancelledError:
                    pass
                await asyncio.sleep(0.25)
                self.assertFalse(resistant_child[0].done())
                self.assertFalse(ack_effects_quiescent())
                self.assertFalse(_RoomRuntime.shutdown(runtime, 0.05))
                resistant_release.set()
                await resistant_child[0]
                self.assertTrue(await drain_ack_ownership())
                self.assertTrue(ack_effects_quiescent())
                self.assertTrue(_RoomRuntime.shutdown(runtime, 0.2))
            self.assertEqual([(7, "👂")], resistant_calls)

        self._run(scenario())

    def test_reservation_contention_stays_responsive_and_does_not_duplicate(self) -> None:
        async def scenario() -> None:
            calls: list[tuple] = []

            async def reaction(_self, message, emoji):
                calls.append((message.id, emoji))
                return True

            async def other_reaction(_self, message, emoji):
                return True

            adapter = self._adapter(reaction)
            scheduler = ConversationOpportunityScheduler("reserve-contention")
            token = scheduler.offer("discord:message:7")
            assert token is not None
            other_adapter = self._adapter(other_reaction)
            other_scheduler = ConversationOpportunityScheduler("other-room")
            other_token = other_scheduler.offer("discord:message:8")
            assert other_token is not None
            with tempfile.TemporaryDirectory() as directory:
                dispatch, journal = self._prepare_dispatch(
                    adapter, scheduler, token, directory, "req-reserve"
                )
                other_dir = Path(directory) / "other"
                other_dir.mkdir()
                other_dispatch, _ = self._prepare_dispatch(
                    other_adapter, other_scheduler, other_token, other_dir,
                    "req-other", room_id="99", message_id=8,
                )
                entered, returned = self._observe_journal_call(journal, "reserve")
                lock_path = Path(directory) / ".ack.jsonl.lock"
                fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
                fcntl.flock(fd, fcntl.LOCK_EX)
                start = time.monotonic()
                pending = asyncio.create_task(dispatch(start + 0.15))
                try:
                    await self._assert_wait_progress(entered, returned)
                    other_start = time.monotonic()
                    other_result = await asyncio.wait_for(
                        other_dispatch(other_start + 1), 0.2
                    )
                    self.assertLess(time.monotonic() - other_start, 0.2)
                    self.assertEqual("sent", other_result.delivery)
                    result = await asyncio.wait_for(pending, 0.35)
                    self.assertLess(time.monotonic() - start, 0.35)
                    self.assertEqual([], calls)
                    self.assertEqual("failed", result.delivery)
                    # The real lock remains held through other-room progress
                    # AND deadline refusal, not an arbitrary sleep in a holder.
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)
                    await asyncio.gather(pending, return_exceptions=True)
                    self.assertTrue(await drain_ack_ownership(3))
                replay_scheduler = ConversationOpportunityScheduler("replay")
                replay = replay_scheduler.offer("discord:message:7")
                assert replay is not None
                replay_result, _replay_journal = await self._dispatch(
                    adapter,
                    replay_scheduler,
                    replay,
                    time.monotonic() + 1,
                    directory,
                    "req-replay",
                )
                self.assertEqual([], calls)
                self.assertEqual("unknown", replay_result.delivery)
                self.assertIn("duplicate", replay_result.detail)
                self.assertNotEqual("sent", journal.records()[-1]["delivery"])

        self._run(scenario())

    def test_reservation_wait_expiry_keeps_cleanup_owned(self) -> None:
        async def scenario() -> None:
            calls = []
            release_error = threading.Event()
            expired = threading.Event()

            async def reaction(_self, message, emoji):
                calls.append((message.id, emoji))
                return True

            adapter = self._adapter(reaction)
            scheduler = ConversationOpportunityScheduler("delayed-reserve-error")
            token = scheduler.offer("discord:message:7")
            assert token is not None
            with tempfile.TemporaryDirectory() as directory:
                dispatch, journal = self._prepare_dispatch(
                    adapter, scheduler, token, directory, "req-delayed-error"
                )
                original = journal.reserve

                def delayed_error(*args, **kwargs):
                    try:
                        return original(*args, **kwargs)
                    except hermes_ack.PersistenceError:
                        # Hold the worker between real lock timeout and error
                        # publication. Event.wait in the async observer must
                        # expire normally (False), not finish the reservation.
                        expired.set()
                        release_error.wait(2)
                        raise

                journal.reserve = delayed_error
                fd = os.open(Path(directory) / ".ack.jsonl.lock", os.O_CREAT | os.O_RDWR, 0o600)
                fcntl.flock(fd, fcntl.LOCK_EX)
                try:
                    start = time.monotonic()
                    wait_for = asyncio.wait_for

                    async def delayed_observer_timeout(awaitable, timeout):
                        # Select the legal ordering where threading.Event.wait
                        # returns False before asyncio's fallback timer fires.
                        # Do not alter the journal or dispatch deadline.
                        if timeout < 0.3:
                            timeout += 0.2
                        return await wait_for(awaitable, timeout)

                    with mock.patch.object(asyncio, "wait_for", delayed_observer_timeout):
                        result = await asyncio.wait_for(dispatch(start + 0.15), 0.35)
                    self.assertLess(time.monotonic() - start, 0.35)
                    self.assertEqual([], calls)
                    self.assertEqual("failed", result.delivery)
                    self.assertFalse(ack_effects_quiescent(), "reservation cleanup lost ownership")
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)
                    release_error.set()
                    self.assertTrue(await drain_ack_ownership(3))
                self.assertTrue(expired.is_set())
                self.assertEqual("failed", journal.records()[-1]["delivery"])
                replay_scheduler = ConversationOpportunityScheduler("delayed-error-replay")
                replay = replay_scheduler.offer("discord:message:7")
                assert replay is not None
                replay_result, _ = await self._dispatch(
                    adapter, replay_scheduler, replay, time.monotonic() + 1,
                    directory, "req-delayed-error-replay",
                )
                self.assertEqual([], calls)
                self.assertEqual("unknown", replay_result.delivery)
                self.assertIn("duplicate", replay_result.detail)

        self._run(scenario())

    def test_published_reservation_error_keeps_cleanup_on_timeout_or_cancel(self) -> None:
        async def scenario(mode) -> None:
            binding = {
                "request_id": "req-published-error", "participant_id": "participant",
                "actor_id": "discord:actor:999", "platform": "discord", "room_id": "42",
                "continuity_scope_id": "discord-room-42", "target_event_id": "discord:message:7",
                "reaction": "👂", "operation": "add", "opportunity_generation": 1,
                "lifecycle_id": "published-error", "deadline_id": "deadline", "permissions_revision": "test",
            }
            to_thread = asyncio.to_thread
            wait_for = asyncio.wait_for

            async def interrupted_observer(fn, _remaining):
                # Let the real worker publish its lock-timeout error first,
                # then select timeout/cancellation before delivery to its owner.
                self.assertTrue(await to_thread(fn, 1))
                if mode == "timeout":
                    raise TimeoutError
                raise asyncio.CancelledError

            async def observer_timer(awaitable, _timeout):
                return await wait_for(awaitable, 1)

            with tempfile.TemporaryDirectory() as directory:
                journal = AckJournal(Path(directory) / "ack.jsonl")
                fd = os.open(Path(directory) / ".ack.jsonl.lock", os.O_CREAT | os.O_RDWR, 0o600)
                fcntl.flock(fd, fcntl.LOCK_EX)
                try:
                    with (
                        mock.patch.object(asyncio, "to_thread", interrupted_observer),
                        mock.patch.object(asyncio, "wait_for", observer_timer),
                    ):
                        operation = hermes_ack._reserve_before_dispatch(
                            journal, binding, deadline=time.monotonic() + 0.05
                        )
                        if mode == "timeout":
                            self.assertEqual((None, "refused"), await operation)
                        else:
                            with self.assertRaises(asyncio.CancelledError):
                                await operation
                    self.assertFalse(ack_effects_quiescent())
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)
                    self.assertTrue(await drain_ack_ownership(3))
                self.assertEqual("failed", journal.records()[-1]["delivery"])
                self.assertFalse(AckJournal(journal.path).reserve(binding)[1])

        for mode in ("timeout", "cancel"):
            with self.subTest(mode=mode):
                self._run(scenario(mode))

    def test_settlement_contention_stays_responsive_and_does_not_duplicate(self) -> None:
        async def scenario() -> None:
            calls: list[tuple] = []

            async def reaction(_self, message, emoji):
                calls.append((message.id, emoji))
                # Reservation is durable before the native callback. Acquire
                # synchronously here so settlement must contend, without a race
                # between a sleeping test thread and the real journal worker.
                fcntl.flock(fd, fcntl.LOCK_EX)
                return True

            adapter = self._adapter(reaction)
            scheduler = ConversationOpportunityScheduler("settle-contention")
            token = scheduler.offer("discord:message:7")
            assert token is not None
            with tempfile.TemporaryDirectory() as directory:
                dispatch, journal = self._prepare_dispatch(
                    adapter, scheduler, token, directory, "req-settle"
                )
                entered, returned = self._observe_journal_call(journal, "settle")
                fd = os.open(Path(directory) / ".ack.jsonl.lock", os.O_CREAT | os.O_RDWR, 0o600)
                start = time.monotonic()
                pending = asyncio.create_task(dispatch(start + 2))
                try:
                    await self._assert_wait_progress(entered, returned)
                    self.assertFalse(pending.done())
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)
                    result = await asyncio.wait_for(pending, 2.5)
                    self.assertTrue(await drain_ack_ownership(3))
                self.assertLess(time.monotonic() - start, 2)
                self.assertEqual([(7, "👂")], calls)
                self.assertEqual("sent", result.delivery)
                replay_scheduler = ConversationOpportunityScheduler("settle-replay")
                replay = replay_scheduler.offer("discord:message:7")
                assert replay is not None
                replay_adapter = self._adapter(reaction)
                replay_result, _journal = await self._dispatch(
                    replay_adapter,
                    replay_scheduler,
                    replay,
                    time.monotonic() + 1,
                    directory,
                    "req-settle-replay",
                )
                self.assertEqual([(7, "👂")], calls)
                self.assertEqual("unknown", replay_result.delivery)
                self.assertEqual("sent", journal.records()[-1]["delivery"])

        self._run(scenario())

    def test_rlock_contention_bounds_writers_and_does_not_record_sent(self) -> None:
        async def scenario() -> None:
            calls: list[tuple] = []
            release = threading.Event()
            acquired = threading.Event()

            async def reaction(_self, message, emoji):
                calls.append((message.id, emoji))

                def hold() -> None:
                    with journal._lock:
                        acquired.set()
                        release.wait(8)

                threading.Thread(target=hold).start()
                self.assertTrue(acquired.wait(1))
                return True

            adapter = self._adapter(reaction)
            scheduler = ConversationOpportunityScheduler("settle-rlock")
            token = scheduler.offer("discord:message:7")
            assert token is not None
            with tempfile.TemporaryDirectory() as directory:
                journal = AckJournal(Path(directory) / "ack.jsonl")
                receipts = ReceiptJournal(Path(directory) / "receipts.jsonl")
                event = SimpleNamespace(raw_message=_Message(7, _Channel("42", allow=True)))
                capability = discord_reaction_capability(
                    adapter,
                    event,
                    room_id="42",
                    actor_id="discord:actor:999",
                )
                _seed(receipts, "req-rlock", capability.permissions_revision)
                entered, returned = self._observe_journal_call(journal, "settle")
                start = time.monotonic()
                deadline = start + 0.35
                progress = asyncio.create_task(self._assert_wait_progress(entered, returned))
                route = _CONFIGURED_ROUTE_CONTEXT.set(True)
                try:
                    result = await dispatch_attention_ack(
                        adapter=adapter,
                        event=event,
                        platform="discord",
                        room_id="42",
                        actor_id="discord:actor:999",
                        policy=AckPolicy(enabled=True),
                        journal=journal,
                        receipts=receipts,
                        wake=_wake(),
                        request={"request_id": "req-rlock"},
                        decision=_decision(capability.permissions_revision),
                        token=token,
                        deadline=deadline,
                        lifecycle_id=scheduler.lifecycle_id,
                        scheduler=scheduler,
                    )
                finally:
                    _CONFIGURED_ROUTE_CONTEXT.reset(route)
                await progress
                self.assertLess(time.monotonic() - start, 0.7)
                self.assertEqual([(7, "👂")], calls)
                self.assertEqual("unknown", result.delivery)
                # Await owned-future delivery rather than assuming a sleeping
                # timer runs after every executor callback. The writer's absolute
                # cleanup deadline is unchanged; allow a bounded half-second
                # for the loop to observe completion, with the lock still held.
                cleanup_observed_by = deadline + 2.5
                self.assertTrue(await drain_ack_ownership(
                    max(0, cleanup_observed_by - time.monotonic())
                ))
                self.assertLess(time.monotonic(), cleanup_observed_by)
                self.assertTrue(ack_effects_quiescent())
                raw_before = (Path(directory) / "ack.jsonl").read_text(encoding="utf-8")
                self.assertNotIn('"delivery":"sent"', raw_before)
                release.set()
                await asyncio.sleep(0.05)
                raw_after = (Path(directory) / "ack.jsonl").read_text(encoding="utf-8")
                self.assertEqual(raw_before, raw_after)
                self.assertNotIn('"delivery":"sent"', raw_after)
                stages = [record["stage"] for record in receipts.records("req-rlock")]
                self.assertEqual(
                    ["observation", "attention", "participant-host", "transport"],
                    stages,
                )
                self.assertEqual("unknown", receipts.records("req-rlock")[-1]["body"]["delivery"])
                replay_scheduler = ConversationOpportunityScheduler("rlock-replay")
                replay = replay_scheduler.offer("discord:message:7")
                assert replay is not None
                replay_result, _replay_journal = await self._dispatch(
                    self._adapter(reaction),
                    replay_scheduler,
                    replay,
                    time.monotonic() + 1,
                    directory,
                    "req-rlock-replay",
                )
                self.assertEqual([(7, "👂")], calls)
                self.assertEqual("unknown", replay_result.delivery)
                self.assertIn("duplicate", replay_result.detail)

        self._run(scenario())

    def test_cancelled_dispatch_closes_transport_receipt(self) -> None:
        async def once(mode: str, repeats: int) -> None:
            calls: list[tuple] = []
            entered = asyncio.Event()
            release = asyncio.Event()
            child: list[asyncio.Task] = []

            async def reaction(_self, message, emoji):
                child.append(asyncio.current_task())
                entered.set()
                if mode == "cooperative":
                    await release.wait()
                else:
                    while not release.is_set():
                        try:
                            await release.wait()
                        except asyncio.CancelledError:
                            pass
                calls.append((message.id, emoji))
                return True

            adapter = self._adapter(reaction)
            scheduler = ConversationOpportunityScheduler(f"{mode}-{repeats}")
            token = scheduler.offer("discord:message:7")
            assert token is not None
            with tempfile.TemporaryDirectory() as directory:
                task = asyncio.create_task(
                    self._dispatch(
                        adapter,
                        scheduler,
                        token,
                        time.monotonic() + 2,
                        directory,
                        "req-cancel-receipt",
                    )
                )
                await entered.wait()
                for _ in range(repeats):
                    task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                release.set()
                self.assertTrue(await drain_ack_ownership(3))
                receipts = ReceiptJournal(Path(directory) / "receipts.jsonl")
                journal = AckJournal(Path(directory) / "ack.jsonl")
                self.assertEqual(
                    ["observation", "attention", "participant-host", "transport"],
                    [record["stage"] for record in receipts.records("req-cancel-receipt")],
                )
                self.assertEqual(
                    "unknown",
                    receipts.records("req-cancel-receipt")[-1]["body"]["delivery"],
                )
                deliveries = [
                    record.get("delivery")
                    for record in journal.records()
                    if record.get("state") == "settled"
                ]
                self.assertEqual(["unknown"], deliveries)
                self.assertNotIn("sent", deliveries)
                if mode == "cooperative":
                    self.assertEqual([], calls)
                    self.assertTrue(child[0].done())
                else:
                    self.assertFalse(child[0].cancelled() and child[0].done() and calls)
                    self.assertLessEqual(len(calls), 1)

        async def scenario() -> None:
            await once("cooperative", 1)
            await once("cooperative", 2)
            await once("resistant", 1)
            await once("resistant", 2)

        self._run(scenario())


class PermitContextTests(unittest.TestCase):
    def test_invalid_permit_fails_closed_without_route_context(self) -> None:
        class Adapter:
            def __init__(self) -> None:
                self.calls: list[tuple] = []

            async def _add_reaction(self, message, emoji):
                self.calls.append(("reaction", message.id, emoji))
                return True

            async def send(self, chat_id, content, reply_to=None, metadata=None):
                self.calls.append(("send", chat_id, content))
                return True

        _wrap_stock_effect_methods(Adapter)
        adapter = Adapter()
        other_adapter = Adapter()
        message = _Message(7, _Channel("42", allow=True))
        other = _Message(8, _Channel("99", allow=True))
        scheduler = ConversationOpportunityScheduler("invalid-permit")
        token = scheduler.offer("discord:message:7")
        assert token is not None
        permit = AckEffectPermit(
            adapter=adapter,
            method="_add_reaction",
            emoji="👂",
            room_id="42",
            native_message_id="7",
            message=message,
            scheduler=scheduler,
            token=token,
            deadline=time.monotonic() + 5,
        )
        context = hermes_ack._ACK_EFFECT_PERMIT.set(permit)
        try:
            asyncio.run(adapter._add_reaction(message, "👂"))
            for call in (
                lambda: adapter._add_reaction(message, "👂"),
                lambda: adapter._add_reaction(other, "👂"),
                lambda: adapter._add_reaction(message, "👍"),
                lambda: other_adapter._add_reaction(message, "👂"),
                lambda: adapter.send("42", "not an ack"),
            ):
                with self.assertRaises(AckAuthorityClosed):
                    asyncio.run(call())
        finally:
            hermes_ack._ACK_EFFECT_PERMIT.reset(context)
        self.assertEqual([("reaction", 7, "👂")], adapter.calls)
        self.assertEqual([], other_adapter.calls)
        self.assertTrue(permit.consumed)

    def test_ordinary_traffic_without_permit_still_falls_through(self) -> None:
        class Adapter:
            def __init__(self) -> None:
                self.calls: list[tuple] = []

            async def _add_reaction(self, message, emoji):
                self.calls.append((message.id, emoji))
                return True

            async def send(self, chat_id, content, reply_to=None, metadata=None):
                self.calls.append(("send", content))
                return True

        _wrap_stock_effect_methods(Adapter)
        adapter = Adapter()
        message = _Message(7, _Channel("42", allow=True))
        asyncio.run(adapter._add_reaction(message, "👂"))
        asyncio.run(adapter.send("42", "ordinary"))
        self.assertEqual([(7, "👂"), ("send", "ordinary")], adapter.calls)
        route = _CONFIGURED_ROUTE_CONTEXT.set(True)
        try:
            with self.assertRaises(_StockEffectBlocked):
                asyncio.run(adapter._add_reaction(message, "👍"))
        finally:
            _CONFIGURED_ROUTE_CONTEXT.reset(route)
        self.assertEqual([(7, "👂"), ("send", "ordinary")], adapter.calls)


if __name__ == "__main__":
    unittest.main()
