"""Finite persistence stalls at ACK lifecycle boundaries; real JSONL writes."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import patch

from nunchi.ack import AckJournal, AckPolicy
from nunchi.integrations import hermes_ack as ack
from nunchi.integrations.hermes_v2 import _wrap_stock_effect_methods
from nunchi.participant import ConversationOpportunityScheduler
from nunchi.receipts import ReceiptJournal
from tests.v2.test_hermes_ack import _Channel, _Message, _decision, _seed, _wake


class PersistenceBoundaryTests(unittest.TestCase):
    def setup_dispatch(self, directory, *, writer=os.write, budget: float = 3):
        effects = []

        class Adapter:
            def __init__(self):
                self._client = SimpleNamespace(user=SimpleNamespace(id=999))

            async def _add_reaction(self, message, emoji):
                effects.append((message.id, emoji))
                return True

        _wrap_stock_effect_methods(Adapter)
        adapter = Adapter()
        event = SimpleNamespace(raw_message=_Message(7, _Channel("42", allow=True)))
        cap = ack.discord_reaction_capability(
            adapter, event, room_id="42", actor_id="discord:actor:999",
        )
        scheduler = ConversationOpportunityScheduler("persistence-boundary")
        token = scheduler.offer("discord:message:7")
        journal = AckJournal(Path(directory) / "ack.jsonl")
        receipts = ReceiptJournal(Path(directory) / "receipts.jsonl", writer=writer)
        _seed(receipts, "req-boundary", cap.permissions_revision)
        kwargs: dict[str, Any] = dict(
            adapter=adapter, event=event, platform="discord", room_id="42",
            actor_id="discord:actor:999", policy=AckPolicy(enabled=True), journal=journal,
            receipts=receipts, wake=_wake(), request={"request_id": "req-boundary"},
            decision=_decision(cap.permissions_revision), token=token,
            deadline=time.monotonic() + budget, lifecycle_id=scheduler.lifecycle_id,
            scheduler=scheduler,
        )
        return kwargs, effects

    def assert_closed(self, receipts, delivery):
        stream = receipts.records("req-boundary")
        self.assertEqual(
            ["observation", "attention", "participant-host", "transport"],
            [row["stage"] for row in stream],
        )
        self.assertEqual(delivery, stream[-1]["body"]["delivery"])

    def test_handoff_cancellation_observes_writer_once_and_closes(self):
        async def scenario():
            entered, release = threading.Event(), threading.Event()
            writes = []

            def writer(fd, payload):
                stage = json.loads(payload)["stage"]
                writes.append(stage)
                if stage == "participant-host":
                    entered.set()
                    if not release.wait(5):
                        raise OSError("test release timed out")
                return os.write(fd, payload)

            with tempfile.TemporaryDirectory() as directory:
                kwargs, effects = self.setup_dispatch(directory, writer=writer)
                parent = asyncio.create_task(ack.dispatch_attention_ack(**kwargs))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                    parent.cancel("original-cancellation")
                    await asyncio.sleep(.02)
                    parent.cancel("second-cancellation")
                    release.set()
                    with self.assertRaises(asyncio.CancelledError) as caught:
                        await parent
                    self.assertEqual(("original-cancellation",), caught.exception.args)
                    self.assertTrue(await ack.drain_ack_ownership(3))
                    self.assertEqual([], effects)
                    self.assert_closed(kwargs["receipts"], "failed")
                    self.assertEqual("failed", kwargs["journal"].records()[-1]["delivery"])
                    self.assertEqual(1, writes.count("participant-host"))
                    self.assertEqual(1, writes.count("transport"))
                finally:
                    release.set()
                    await ack.drain_ack_ownership(3)

        asyncio.run(scenario())

    def test_reservation_write_cancellation_closes_without_dispatch(self):
        self.cancel_reservation(after_commit=False)

    def test_reservation_completion_cancellation_closes_without_dispatch(self):
        self.cancel_reservation(after_commit=True)

    def cancel_reservation(self, *, after_commit):
        async def scenario():
            entered, release = threading.Event(), threading.Event()
            with tempfile.TemporaryDirectory() as directory:
                kwargs, effects = self.setup_dispatch(directory)
                journal = kwargs["journal"]
                real_reserve, real_write = journal.reserve, os.write

                def pause():
                    entered.set()
                    if not release.wait(5):
                        raise OSError("test release timed out")

                def reserve(*args, **kw):
                    result = real_reserve(*args, **kw)
                    if after_commit:
                        pause()
                    return result

                def writer(fd, payload):
                    result = real_write(fd, payload)
                    if not after_commit and json.loads(payload).get("state") == "reserved":
                        pause()
                    return result

                try:
                    with patch.object(journal, "reserve", reserve), patch("os.write", writer):
                        parent = asyncio.create_task(ack.dispatch_attention_ack(**kwargs))
                        self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                        parent.cancel("original-cancellation")
                        await asyncio.sleep(.02)
                        parent.cancel("second-cancellation")
                        release.set()
                        with self.assertRaises(asyncio.CancelledError) as caught:
                            await parent
                        self.assertEqual(("original-cancellation",), caught.exception.args)
                        self.assertTrue(await ack.drain_ack_ownership(3))
                    self.assertEqual([], effects)
                    self.assert_closed(kwargs["receipts"], "failed")
                    self.assertEqual("failed", journal.records()[-1]["delivery"])
                finally:
                    release.set()
                    await ack.drain_ack_ownership(3)

        asyncio.run(scenario())

    def test_transport_cancellation_finishes_the_same_receipt(self):
        async def scenario():
            entered, release = threading.Event(), threading.Event()
            writes = []

            def writer(fd, payload):
                stage = json.loads(payload)["stage"]
                writes.append(stage)
                if stage == "transport":
                    entered.set()
                    if not release.wait(5):
                        raise OSError("test release timed out")
                return os.write(fd, payload)

            with tempfile.TemporaryDirectory() as directory:
                kwargs, effects = self.setup_dispatch(directory, writer=writer)
                parent = asyncio.create_task(ack.dispatch_attention_ack(**kwargs))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                    parent.cancel("original-cancellation")
                    await asyncio.sleep(.02)
                    parent.cancel("second-cancellation")
                    release.set()
                    with self.assertRaises(asyncio.CancelledError) as caught:
                        await parent
                    self.assertEqual(("original-cancellation",), caught.exception.args)
                    self.assertTrue(await ack.drain_ack_ownership(3))
                    self.assertEqual([(7, "👂")], effects)
                    self.assert_closed(kwargs["receipts"], "sent")
                    self.assertEqual(1, writes.count("transport"))
                    self.assertEqual("sent", kwargs["journal"].records()[-1]["delivery"])
                finally:
                    release.set()
                    await ack.drain_ack_ownership(3)

        asyncio.run(scenario())

    def test_settlement_commit_is_observed_before_slow_return(self):
        async def scenario():
            entered, release = threading.Event(), threading.Event()
            with tempfile.TemporaryDirectory() as directory:
                kwargs, effects = self.setup_dispatch(directory, budget=.2)
                journal = kwargs["journal"]
                real_settle = journal.settle

                def slow_return(*args, **kw):
                    result = real_settle(*args, **kw)
                    entered.set()
                    if not release.wait(4):
                        raise OSError("test release timed out")
                    return result

                try:
                    with patch.object(journal, "settle", slow_return):
                        parent = asyncio.create_task(ack.dispatch_attention_ack(**kwargs))
                        self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                        result = await asyncio.wait_for(asyncio.shield(parent), 1)
                        self.assertEqual("sent", result.delivery)
                        self.assert_closed(kwargs["receipts"], "sent")
                        self.assertEqual([(7, "👂")], effects)
                finally:
                    release.set()
                    self.assertTrue(await ack.drain_ack_ownership(3))

        asyncio.run(scenario())

    def test_late_settlement_open_does_not_upgrade_unknown(self):
        self.late_settlement("open")

    def test_late_settlement_write_does_not_upgrade_unknown(self):
        self.late_settlement("write")

    def test_late_settlement_fsync_does_not_upgrade_unknown(self):
        self.late_settlement("fsync")

    def test_cancelled_settlement_write_does_not_claim_sent(self):
        self.late_settlement("write", cancel=True)

    def late_settlement(self, mode, *, cancel=False):
        async def scenario():
            entered, release = threading.Event(), threading.Event()
            real_open, real_write, real_sync = os.open, os.write, os.fsync
            settlement_fd = None
            stalled = False

            def pause():
                nonlocal stalled
                if stalled:
                    return
                stalled = True
                entered.set()
                if not release.wait(6):
                    raise OSError("test release timed out")

            def slow_write(fd, payload):
                # Return from a real write late, not from a fake persistence call.
                result = real_write(fd, payload)
                if mode == "write" and fd == settlement_fd:
                    pause()
                return result

            def slow_sync(fd):
                real_sync(fd)
                if mode == "fsync" and fd == settlement_fd:
                    pause()

            with tempfile.TemporaryDirectory() as directory:
                kwargs, effects = self.setup_dispatch(directory, budget=3 if cancel else .2)
                opens = 0

                def slow_open(path, flags, *args, **kw):
                    nonlocal opens, settlement_fd
                    is_append = Path(path) == kwargs["journal"].path and flags & os.O_APPEND
                    if is_append:
                        opens += 1
                        if mode == "open" and opens == 2:
                            pause()
                    fd = real_open(path, flags, *args, **kw)
                    if is_append and opens == 2:
                        settlement_fd = fd
                    return fd

                try:
                    with patch("os.open", slow_open), patch("os.write", slow_write), patch("os.fsync", slow_sync):
                        parent = asyncio.create_task(ack.dispatch_attention_ack(**kwargs))
                        self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                        if cancel:
                            parent.cancel("original-cancellation")
                            await asyncio.sleep(.02)
                            parent.cancel("second-cancellation")
                            release.set()
                            with self.assertRaises(asyncio.CancelledError) as caught:
                                await parent
                            self.assertEqual(("original-cancellation",), caught.exception.args)
                        else:
                            result = await asyncio.wait_for(asyncio.shield(parent), 1)
                            self.assertEqual("unknown", result.delivery)
                            await asyncio.sleep(max(0, kwargs["deadline"] + 2.1 - time.monotonic()))
                            self.assertFalse(ack.ack_effects_quiescent())
                        self.assert_closed(kwargs["receipts"], "unknown")
                        release.set()
                        self.assertTrue(await ack.drain_ack_ownership(3))
                    self.assertEqual([(7, "👂")], effects)
                    rows = AckJournal(kwargs["journal"].path).records()
                    self.assertNotIn("sent", [row.get("delivery") for row in rows])
                finally:
                    release.set()
                    await ack.drain_ack_ownership(3)

        asyncio.run(scenario())
