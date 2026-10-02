"""Current stock event-bearing delivery helpers keep the exact effect boundary."""
import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from nunchi.integrations import hermes_v2 as hv
from tests.v2.test_hermes_portable import (
    FakeEvent, FakeSource, FakeValue, FakeLlm, FakeSendResult, judgment, room_config,
)


class EventEffectTargetTests(unittest.TestCase):
    def test_final_helpers_allow_only_current_exact_room_and_thread(self):
        for platform, room, thread in (("discord", "42", None), ("telegram", "42:topic:9", "9")):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as tmp:
                native = []

                class Adapter:
                    def __init__(self):
                        self.platform = FakeValue(platform)
                        setattr(self, hv._ADAPTER_PROFILE_ATTRIBUTE, "default")

                    def nunchi_self_identity(self):
                        return {"id": "999", "username": "nunchi"}

                    async def _send_final_text(self, event, session_key, text_content, metadata,
                                               is_ephemeral_response, ephemeral_ttl, record_delivery):
                        result, _ = await self.send_final_ledgered(
                            event, session_key, text_content, metadata, reply_to=None)
                        record_delivery(result)

                    async def send_final_ledgered(self, event, session_key, text_content, metadata,
                                                 *, reply_to, is_ephemeral_response=False):
                        return await self._send_with_retry(event.source.chat_id, text_content,
                                                           metadata=metadata), self

                    async def _send_with_retry(self, chat_id, content, metadata=None):
                        return await self.send(chat_id, content, metadata=metadata)

                    async def send(self, chat_id, content, metadata=None):
                        native.append((chat_id, content, metadata))
                        return FakeSendResult(True, message_id="delivered")

                config, ctx = room_config(Path(tmp), llm=FakeLlm([judgment("WAKE", f"{platform}:message:500")]), platform=platform)
                configured = replace(config.rooms[0], binding=replace(config.rooms[0].binding, room_id=room))
                plugin = hv.NunchiHermesV2Plugin(config=replace(config, rooms=(configured,)), ctx=ctx,
                                               hermes_version="0.21.5", mode="process-local-gate")
                self.addCleanup(setattr, hv, "_SHIM_OWNER", None)
                hv._SHIM_OWNER = plugin
                adapter = Adapter()
                source = FakeSource(platform=platform)
                source.thread_id = thread
                event = FakeEvent(source=source)
                metadata = {"thread_id": thread} if thread else None
                asyncio.run(plugin.gate_ingress(adapter=adapter, event=event, stock_handle=mock.AsyncMock()))
                trace = plugin._rooms[(platform, room)].stock_trace(event)
                trace.participant_invoked = True
                trace.assistant_observed = True
                trace.assistant_response = "reply"
                received = []

                async def send(candidate=event, target_metadata=metadata):
                    await adapter._send_final_text(candidate, "session", "reply", target_metadata,
                                                   False, 0, received.append)

                async def run():
                    with self.assertRaises(hv._StockEffectBlocked):
                        await send()  # no active opportunity, even with an exact event
                    token = hv._ACTIVE_STOCK_TURN.set(trace)
                    try:
                        wrong_room = FakeEvent(source=FakeSource(platform=platform, chat_id="77"))
                        wrong_platform = FakeEvent(source=FakeSource(platform="other"))
                        for candidate, md in ((wrong_room, metadata), (wrong_platform, metadata),
                                              (event, {"thread_id": "10"}), (object(), metadata)):
                            with self.subTest(candidate=candidate, metadata=md):
                                with self.assertRaises(hv._StockEffectBlocked):
                                    await send(candidate, md)
                        if thread:
                            with self.assertRaises(hv._StockEffectBlocked):
                                await send(event, None)
                        self.assertEqual([], native)
                        await send()
                        self.assertEqual(1, trace.native_effect_count, "wrappers delegate one native effect")
                        trace.token.cancel_event.set()
                        with self.assertRaises(hv._StockEffectBlocked):
                            await send()
                    finally:
                        hv._ACTIVE_STOCK_TURN.reset(token)

                asyncio.run(run())
                self.assertEqual([("42", "reply", metadata)], native)
                self.assertEqual(1, len(received))
                self.assertTrue(received[0].success)
