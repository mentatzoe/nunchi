from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

from nunchi.attention import AttentionPolicy, ParticipantProfile
from nunchi.integrations import hermes_v2
from nunchi.observation import ObservationLimits, ParticipantBinding


class FakePlatform:
    def __init__(self, value: str) -> None:
        self.value = value


class FakeSource:
    def __init__(
        self,
        *,
        platform: str = "discord",
        chat_id: str = "42",
        user_id: str = "100",
        profile: str = "default",
    ) -> None:
        self.platform = FakePlatform(platform)
        self.chat_id = chat_id
        self.thread_id = None
        self.user_id = user_id
        self.user_name = "person"
        self.chat_type = "group"
        self.profile = profile


class FakeDiscordUser:
    def __init__(self, user_id: str, *, name: str = "bot", bot: bool = False) -> None:
        self.id = int(user_id)
        self.name = name
        self.bot = bot


class FakeRawDiscordMessage:
    def __init__(self, *, content: str = "hello") -> None:
        self.content = content
        self.mentions = []
        self.mention_everyone = False
        self.author = FakeDiscordUser("100")
        self.reactions = []

    async def add_reaction(self, reaction: str) -> None:
        self.reactions.append(("add", reaction))

    async def remove_reaction(self, reaction: str, user: object) -> None:
        self.reactions.append(("remove", reaction, user))


class FakeEvent:
    def __init__(self, *, text: str = "hello", source: FakeSource | None = None) -> None:
        self.text = text
        self.source = source or FakeSource()
        self.message_id = "500"
        self.message_type = FakePlatform("text")
        self.raw_message = FakeRawDiscordMessage(content=text)
        self.media_urls = []
        self.media_types = []
        self.reply_to_message_id = None
        self.timestamp = datetime.now(timezone.utc)
        self.internal = False

    def get_command(self) -> str | None:
        if not self.text.startswith("/"):
            return None
        return self.text[1:].split(maxsplit=1)[0].lower()


@dataclass
class FakeSendResult:
    success: bool
    message_id: str | None = None
    error: str | None = None


class FakeAdapter:
    def __init__(self) -> None:
        user = FakeDiscordUser("999", name="nunchi")
        self._client = types.SimpleNamespace(user=user)
        self.sent: list[dict[str, object]] = []

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        metadata: dict | None = None,
    ) -> FakeSendResult:
        self.sent.append(
            {
                "chat_id": chat_id,
                "content": content,
                "reply_to": reply_to,
                "metadata": metadata,
            }
        )
        return FakeSendResult(True, "700")


class FakeTelegramAdapter:
    def __init__(self) -> None:
        self._bot = types.SimpleNamespace(id=999, username="nunchi")
        self.sent: list[dict[str, object]] = []
        self.reactions: list[tuple[str, str, str]] = []

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        metadata: dict | None = None,
    ) -> FakeSendResult:
        self.sent.append(
            {
                "chat_id": chat_id,
                "content": content,
                "reply_to": reply_to,
                "metadata": metadata,
            }
        )
        return FakeSendResult(True, "701")

    async def _set_reaction(
        self,
        chat_id: str,
        message_id: str,
        reaction: str,
    ) -> bool:
        self.reactions.append((chat_id, message_id, reaction))
        return True

    async def _clear_reactions(self, chat_id: str, message_id: str) -> bool:
        self.reactions.append((chat_id, message_id, ""))
        return True


class FakeStructuredResult:
    def __init__(self, parsed: dict) -> None:
        self.parsed = parsed
        self.provider = "test-provider"
        self.model = "test-model"


class FakeLlm:
    def __init__(self, results: list[dict | BaseException]) -> None:
        self.results = list(results)
        self.calls: list[dict] = []

    def complete_structured(self, **kwargs):
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return FakeStructuredResult(result)


class FakeCtx:
    def __init__(self, llm: FakeLlm) -> None:
        self.llm = llm
        self.profile_name = "default"
        self.hooks: dict[str, object] = {}
        self.commands: dict[str, object] = {}

    def register_hook(self, name: str, callback) -> None:
        self.hooks[name] = callback

    def register_command(self, name: str, callback, **kwargs) -> None:
        del kwargs
        self.commands[name] = callback


def room_config(
    root: Path,
    *,
    llm: FakeLlm,
    attention: AttentionPolicy | None = None,
) -> tuple[hermes_v2.HermesPluginConfig, FakeCtx]:
    profile = ParticipantProfile(
        profile_id="profile",
        participant_id="participant",
        actor_id="discord:actor:999",
        instructions="Be useful and concise.",
        provenance="test",
        sha256="a" * 64,
    )
    room = hermes_v2.HermesRoomConfig(
        binding=ParticipantBinding(
            participant_id="participant",
            actor_id="discord:actor:999",
            platform="discord",
            room_id="42",
            continuity_scope_id="room-42",
            names=("Nunchi",),
            provenance="test",
        ),
        profile=profile,
        attention=attention
        or AttentionPolicy(
            suppression_enabled=True,
            suppression_recovery_verified=True,
        ),
        limits=ObservationLimits(),
        participant_timeout_seconds=2,
        participant_max_expansions=1,
    )
    config = hermes_v2.HermesPluginConfig(
        hermes_profile="default",
        state_directory=root,
        rooms=(room,),
        provenance={"path": "/test/config.json", "sha256": "b" * 64},
    )
    return config, FakeCtx(llm)


class HermesPortableTests(unittest.TestCase):
    def setUp(self) -> None:
        hermes_v2._SHIM_OWNER = None

    def test_module_import_does_not_require_hermes(self):
        source = inspect.getsource(hermes_v2)
        self.assertNotIn("import gateway.", source.split("def _install_compatibility_shim")[0])
        self.assertNotIn("import hermes_cli", source)

    def test_normalizes_attested_discord_identity_and_mentions(self):
        event = FakeEvent(text="<@999> hello")
        event.raw_message.mentions = [FakeDiscordUser("999")]
        binding = ParticipantBinding(
            participant_id="participant",
            actor_id="discord:actor:999",
            platform="discord",
            room_id="42",
            continuity_scope_id="room-42",
        )
        canonical, actors = hermes_v2.normalize_message_event(
            event,
            source=event.source,
            binding=binding,
            self_native_id="999",
            self_username="nunchi",
        )
        self.assertEqual("discord:message:500", canonical["id"])
        self.assertEqual(["discord:actor:999"], canonical["mentioned_actor_ids"])
        self.assertIn("discord:actor:100", actors)
        self.assertIn("discord:actor:999", actors)

    def test_exact_self_mismatch_fails_closed(self):
        binding = ParticipantBinding(
            participant_id="participant",
            actor_id="discord:actor:998",
            platform="discord",
            room_id="42",
            continuity_scope_id="room-42",
        )
        with self.assertRaisesRegex(Exception, "exact self"):
            hermes_v2.normalize_message_event(
                FakeEvent(),
                source=FakeSource(),
                binding=binding,
                self_native_id="999",
                self_username="nunchi",
            )

    def test_telegram_topic_uses_stock_identity_route_and_delivery(self):
        source = FakeSource(
            platform="telegram",
            chat_id="-10042",
            user_id="100",
        )
        source.thread_id = "7"
        event = FakeEvent(text="@nunchi hello", source=source)
        event.raw_message = types.SimpleNamespace(
            text=event.text,
            caption=None,
            entities=(
                types.SimpleNamespace(
                    type="mention",
                    offset=0,
                    length=len("@nunchi"),
                ),
            ),
        )
        binding = ParticipantBinding(
            participant_id="participant",
            actor_id="telegram:actor:999",
            platform="telegram",
            room_id="-10042:topic:7",
            continuity_scope_id="telegram-topic-7",
        )
        canonical, _ = hermes_v2.normalize_message_event(
            event,
            source=source,
            binding=binding,
            self_native_id="999",
            self_username="nunchi",
        )
        self.assertEqual(
            ["telegram:actor:999"],
            canonical["mentioned_actor_ids"],
        )
        adapter = FakeTelegramAdapter()
        self.assertEqual(("999", "nunchi"), hermes_v2._self_identity(adapter, "telegram"))
        delivery = hermes_v2.Hermes019Delivery(
            adapter=adapter,
            event=event,
            source=source,
            profile="default",
            self_native_id="999",
        )
        receipt = asyncio.run(delivery.reply("hello back"))
        self.assertEqual("sent", receipt.status)
        self.assertEqual("-10042:topic:7", receipt.room_id)
        self.assertEqual("-10042", adapter.sent[0]["chat_id"])
        self.assertEqual("7", adapter.sent[0]["metadata"]["thread_id"])

    def test_full_v2_turn_uses_stock_adapter_for_delivery(self):
        llm = FakeLlm(
            [
                {
                    "disposition": "WAKE",
                    "reasons": ["direct request"],
                    "evidence_event_ids": ["discord:message:500"],
                    "legacy_verdict_confidences": {
                        "PASS": 0.01,
                        "ACK": 0.01,
                        "ASK": 0.08,
                        "SPEAK": 0.9,
                    },
                },
                {
                    "kind": "message",
                    "origin_event_id": "discord:message:500",
                    "text": "hello back",
                },
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(Path(temporary), llm=llm)
            plugin = hermes_v2.NunchiHermesV2Plugin(
                config=config,
                ctx=ctx,
                hermes_version="0.19.0",
                mode="runtime-monkeypatch",
            )
            adapter = FakeAdapter()
            event = FakeEvent()
            delivery = hermes_v2.Hermes019Delivery(
                adapter=adapter,
                event=event,
                source=event.source,
                profile="default",
                self_native_id="999",
            )

            async def run():
                handled = await plugin.handle(
                    event=event,
                    source=event.source,
                    delivery=delivery,
                    self_native_id="999",
                    self_username="nunchi",
                )
                self.assertTrue(handled)

            asyncio.run(run())
            self.assertEqual(2, len(llm.calls))
            self.assertEqual("hello back", adapter.sent[0]["content"])
            self.assertTrue(adapter.sent[0]["metadata"]["notify"])

    def test_suppression_does_not_run_participant_or_send(self):
        llm = FakeLlm(
            [
                {
                    "disposition": "SUPPRESS",
                    "reasons": ["not addressed"],
                    "evidence_event_ids": ["discord:message:500"],
                    "legacy_verdict_confidences": {
                        "PASS": 0.9,
                        "ACK": 0.05,
                        "ASK": 0.03,
                        "SPEAK": 0.02,
                    },
                }
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(Path(temporary), llm=llm)
            plugin = hermes_v2.NunchiHermesV2Plugin(
                config=config,
                ctx=ctx,
                hermes_version="0.19.0",
                mode="runtime-monkeypatch",
            )
            adapter = FakeAdapter()
            event = FakeEvent()
            delivery = hermes_v2.Hermes019Delivery(
                adapter=adapter,
                event=event,
                source=event.source,
                profile="default",
                self_native_id="999",
            )
            asyncio.run(
                plugin.handle(
                    event=event,
                    source=event.source,
                    delivery=delivery,
                    self_native_id="999",
                    self_username="nunchi",
                )
            )
            self.assertEqual(1, len(llm.calls))
            self.assertEqual([], adapter.sent)

    def test_remaining_attention_lifecycle_paths_reach_the_shared_host(self):
        suppress_vector = {
            "PASS": 0.9,
            "ACK": 0.04,
            "ASK": 0.03,
            "SPEAK": 0.03,
        }
        near_margin_vector = {
            "PASS": 0.35,
            "ACK": 0.22,
            "ASK": 0.21,
            "SPEAK": 0.22,
        }
        cases = (
            (
                "classifier-defer",
                AttentionPolicy(),
                [
                    {
                        "disposition": "DEFER",
                        "reasons": ["uncertain"],
                        "evidence_event_ids": ["discord:message:500"],
                        "legacy_verdict_confidences": suppress_vector,
                    },
                    {"kind": "silence"},
                ],
                2,
            ),
            (
                "margin-defer",
                AttentionPolicy(effective_margin=0.2),
                [
                    {
                        "disposition": "SUPPRESS",
                        "reasons": ["near boundary"],
                        "evidence_event_ids": ["discord:message:500"],
                        "legacy_verdict_confidences": near_margin_vector,
                    },
                    {"kind": "silence"},
                ],
                2,
            ),
            (
                "recoverability-defer",
                AttentionPolicy(suppression_recovery_verified=False),
                [
                    {
                        "disposition": "SUPPRESS",
                        "reasons": ["not addressed"],
                        "evidence_event_ids": ["discord:message:500"],
                        "legacy_verdict_confidences": suppress_vector,
                    },
                    {"kind": "silence"},
                ],
                2,
            ),
            (
                "bypass",
                AttentionPolicy(preattention_enabled=False),
                [{"kind": "silence"}],
                1,
            ),
            (
                "error-fallback",
                AttentionPolicy(error_action="WAKE"),
                [RuntimeError("provider offline"), {"kind": "silence"}],
                2,
            ),
            (
                "error-no-wake",
                AttentionPolicy(error_action="NO_WAKE"),
                [RuntimeError("provider offline")],
                1,
            ),
        )
        for label, policy, results, expected_calls in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                llm = FakeLlm(results)
                config, ctx = room_config(
                    Path(temporary),
                    llm=llm,
                    attention=policy,
                )
                plugin = hermes_v2.NunchiHermesV2Plugin(
                    config=config,
                    ctx=ctx,
                    hermes_version="0.19.0",
                    mode="runtime-monkeypatch",
                )
                adapter = FakeAdapter()
                event = FakeEvent()
                delivery = hermes_v2.Hermes019Delivery(
                    adapter=adapter,
                    event=event,
                    source=event.source,
                    profile="default",
                    self_native_id="999",
                )
                asyncio.run(
                    plugin.handle(
                        event=event,
                        source=event.source,
                        delivery=delivery,
                        self_native_id="999",
                        self_username="nunchi",
                    )
                )
                self.assertEqual(expected_calls, len(llm.calls))
                self.assertEqual([], adapter.sent)

    def test_self_and_unconstructable_deliveries_never_call_a_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            llm = FakeLlm([])
            config, ctx = room_config(Path(temporary), llm=llm)
            plugin = hermes_v2.NunchiHermesV2Plugin(
                config=config,
                ctx=ctx,
                hermes_version="0.19.0",
                mode="runtime-monkeypatch",
            )
            adapter = FakeAdapter()
            self_event = FakeEvent(source=FakeSource(user_id="999"))
            media_event = FakeEvent()
            media_event.media_urls = ["https://example.invalid/file"]

            async def run() -> None:
                for event in (self_event, media_event):
                    delivery = hermes_v2.Hermes019Delivery(
                        adapter=adapter,
                        event=event,
                        source=event.source,
                        profile="default",
                        self_native_id="999",
                    )
                    self.assertTrue(
                        await plugin.handle(
                            event=event,
                            source=event.source,
                            delivery=delivery,
                            self_native_id="999",
                            self_username="nunchi",
                        )
                    )

            asyncio.run(run())
            self.assertEqual([], llm.calls)
            self.assertEqual([], adapter.sent)

    def test_cancellation_closes_a_late_attention_result(self):
        entered = threading.Event()
        release = threading.Event()

        class BlockingLlm(FakeLlm):
            def complete_structured(self, **kwargs):
                self.calls.append(kwargs)
                entered.set()
                release.wait(2)
                return FakeStructuredResult(
                    {
                        "disposition": "WAKE",
                        "reasons": ["late result"],
                        "evidence_event_ids": ["discord:message:500"],
                        "legacy_verdict_confidences": {
                            "PASS": 0.01,
                            "ACK": 0.01,
                            "ASK": 0.08,
                            "SPEAK": 0.9,
                        },
                    }
                )

        with tempfile.TemporaryDirectory() as temporary:
            llm = BlockingLlm([])
            config, ctx = room_config(Path(temporary), llm=llm)
            plugin = hermes_v2.NunchiHermesV2Plugin(
                config=config,
                ctx=ctx,
                hermes_version="0.19.0",
                mode="runtime-monkeypatch",
            )
            adapter = FakeAdapter()
            event = FakeEvent()
            delivery = hermes_v2.Hermes019Delivery(
                adapter=adapter,
                event=event,
                source=event.source,
                profile="default",
                self_native_id="999",
            )

            async def run() -> None:
                task = asyncio.create_task(
                    plugin.handle(
                        event=event,
                        source=event.source,
                        delivery=delivery,
                        self_native_id="999",
                        self_username="nunchi",
                    )
                )
                self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                await plugin.gateway_session_cancel(
                    route=event.source,
                    reason="cancelled",
                )
                release.set()
                await task

            try:
                asyncio.run(run())
            finally:
                release.set()
            self.assertEqual(1, len(llm.calls))
            self.assertEqual([], adapter.sent)

    def test_busy_room_keeps_only_the_newest_pending_opportunity(self):
        entered = threading.Event()
        release = threading.Event()
        result = {
            "disposition": "SUPPRESS",
            "reasons": ["not addressed"],
            "evidence_event_ids": [],
            "legacy_verdict_confidences": {
                "PASS": 0.9,
                "ACK": 0.04,
                "ASK": 0.03,
                "SPEAK": 0.03,
            },
        }

        class FirstCallBlocks(FakeLlm):
            def complete_structured(self, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 1:
                    entered.set()
                    release.wait(2)
                parsed = dict(result)
                projection = json.loads(kwargs["input"][0]["text"])["observation"]
                parsed["evidence_event_ids"] = [projection["trigger_event_id"]]
                return FakeStructuredResult(parsed)

        with tempfile.TemporaryDirectory() as temporary:
            llm = FirstCallBlocks([])
            config, ctx = room_config(Path(temporary), llm=llm)
            plugin = hermes_v2.NunchiHermesV2Plugin(
                config=config,
                ctx=ctx,
                hermes_version="0.19.0",
                mode="runtime-monkeypatch",
            )
            adapter = FakeAdapter()
            first = FakeEvent(text="first")
            second = FakeEvent(text="second")
            second.message_id = "501"

            async def handle(event: FakeEvent) -> None:
                await plugin.handle(
                    event=event,
                    source=event.source,
                    delivery=hermes_v2.Hermes019Delivery(
                        adapter=adapter,
                        event=event,
                        source=event.source,
                        profile="default",
                        self_native_id="999",
                    ),
                    self_native_id="999",
                    self_username="nunchi",
                )

            async def run() -> None:
                active = asyncio.create_task(handle(first))
                self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                pending = asyncio.create_task(handle(second))
                await asyncio.sleep(0)
                release.set()
                await asyncio.gather(active, pending)

            try:
                asyncio.run(run())
            finally:
                release.set()
            self.assertEqual(2, len(llm.calls))
            triggers = [
                json.loads(call["input"][0]["text"])["observation"]["trigger_event_id"]
                for call in llm.calls
            ]
            self.assertEqual(
                ["discord:message:500", "discord:message:501"],
                triggers,
            )
            self.assertEqual([], adapter.sent)

    def test_restart_backfill_is_observed_without_waking(self):
        llm = FakeLlm([])
        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(Path(temporary), llm=llm)
            plugin = hermes_v2.NunchiHermesV2Plugin(
                config=config,
                ctx=ctx,
                hermes_version="0.19.0",
                mode="runtime-monkeypatch",
            )
            adapter = FakeAdapter()
            event = FakeEvent()
            event.timestamp = "2026-01-01T00:00:00Z"
            delivery = hermes_v2.Hermes019Delivery(
                adapter=adapter,
                event=event,
                source=event.source,
                profile="default",
                self_native_id="999",
            )
            asyncio.run(
                plugin.handle(
                    event=event,
                    source=event.source,
                    delivery=delivery,
                    self_native_id="999",
                    self_username="nunchi",
                )
            )
            runtime = plugin._rooms[("discord", "42")]
            self.assertEqual([], llm.calls)
            self.assertEqual([], adapter.sent)
            self.assertTrue(
                any(
                    audit.outcome == "continuity-gap"
                    for audit in runtime.observation.delivery_audits()
                )
            )

    def test_shim_passes_unauthorized_and_commands_to_stock_runner(self):
        class GatewayRunner:
            calls = []

            def __init__(self):
                self.authorized = False
                self.adapter = FakeAdapter()
                self.inbound_notes = 0
                self.pre_dispatch_calls = 0
                self.skip_dispatch = False

            async def _handle_message(self, event):
                self.calls.append(event.text)
                return "stock"

            async def stop(self, *, restart=False):
                self.calls.append(f"stop:{restart}")

            def _is_user_authorized(self, source):
                del source
                return self.authorized

            def _adapter_for_source(self, source):
                del source
                return self.adapter

            def _scale_to_zero_note_real_inbound(self):
                self.inbound_notes += 1

            def _run_pre_gateway_dispatch(self, event):
                del event
                self.pre_dispatch_calls += 1
                return self.skip_dispatch

        fake_gateway = types.ModuleType("gateway")
        fake_run = types.ModuleType("gateway.run")
        fake_run.GatewayRunner = GatewayRunner
        original_gateway = sys.modules.get("gateway")
        original_run = sys.modules.get("gateway.run")
        sys.modules["gateway"] = fake_gateway
        sys.modules["gateway.run"] = fake_run
        try:
            llm = FakeLlm([])
            with tempfile.TemporaryDirectory() as temporary:
                config, ctx = room_config(Path(temporary), llm=llm)
                plugin = hermes_v2.NunchiHermesV2Plugin(
                    config=config,
                    ctx=ctx,
                    hermes_version="0.19.0",
                    mode="runtime-monkeypatch",
                )
                hermes_v2._install_compatibility_shim(plugin)
                runner = GatewayRunner()
                result = asyncio.run(runner._handle_message(FakeEvent()))
                self.assertEqual("stock", result)
                runner.authorized = True
                result = asyncio.run(runner._handle_message(FakeEvent(text="/status")))
                self.assertEqual("stock", result)
                self.assertEqual(["hello", "/status"], runner.calls)
                result = asyncio.run(runner._handle_message(FakeEvent(text="claimed")))
                self.assertIsNone(result)
                self.assertEqual(
                    ["hello", "/status"],
                    runner.calls,
                    "a claimed Nunchi failure must not start a second stock turn",
                )
                self.assertEqual(1, runner.inbound_notes)
                self.assertEqual(1, runner.pre_dispatch_calls)
                runner.skip_dispatch = True
                result = asyncio.run(runner._handle_message(FakeEvent(text="blocked")))
                self.assertIsNone(result)
                self.assertEqual(["hello", "/status"], runner.calls)
                self.assertEqual(2, runner.inbound_notes)
                self.assertEqual(2, runner.pre_dispatch_calls)
                runner._startup_restore_in_progress = True
                result = asyncio.run(runner._handle_message(FakeEvent(text="restore")))
                self.assertEqual("stock", result)
                self.assertEqual(["hello", "/status", "restore"], runner.calls)
                runner._startup_restore_in_progress = False
                runner.skip_dispatch = False
                plugin.handle = mock.AsyncMock(return_value=True)
                first = FakeEvent(text="first")
                first.message_id = "501"
                second = FakeEvent(text="second")
                second.message_id = "502"
                batch = FakeEvent(text="first\nsecond")
                setattr(
                    batch,
                    hermes_v2._NATIVE_BATCH_EVENTS_ATTRIBUTE,
                    (first, second),
                )
                result = asyncio.run(runner._handle_message(batch))
                self.assertIsNone(result)
                self.assertEqual(2, plugin.handle.await_count)
                self.assertEqual(
                    ["501", "502"],
                    [
                        call.kwargs["event"].message_id
                        for call in plugin.handle.await_args_list
                    ],
                )
        finally:
            hermes_v2._SHIM_OWNER = None
            if original_gateway is None:
                sys.modules.pop("gateway", None)
            else:
                sys.modules["gateway"] = original_gateway
            if original_run is None:
                sys.modules.pop("gateway.run", None)
            else:
                sys.modules["gateway.run"] = original_run

    def test_telegram_batch_shim_retains_each_native_event(self):
        class TelegramAdapter:
            def __init__(self):
                self._pending_text_batches = {}

            def _should_drop_delayed_delivery(self):
                return False

            def _text_batch_key(self, event):
                del event
                return "room"

            def _enqueue_text_event(self, event):
                existing = self._pending_text_batches.get("room")
                if existing is None:
                    self._pending_text_batches["room"] = event
                else:
                    existing.text = f"{existing.text}\n{event.text}"
                    existing.media_urls.extend(event.media_urls)
                    existing.media_types.extend(event.media_types)

        fake_plugins = types.ModuleType("plugins")
        fake_platforms = types.ModuleType("plugins.platforms")
        fake_telegram = types.ModuleType("plugins.platforms.telegram")
        fake_adapter = types.ModuleType("plugins.platforms.telegram.adapter")
        fake_adapter.TelegramAdapter = TelegramAdapter
        owner = types.SimpleNamespace(
            _rooms={("telegram", "42"): object()},
            claims=lambda source: source is not None,
        )
        hermes_v2._SHIM_OWNER = owner
        try:
            with mock.patch.dict(
                sys.modules,
                {
                    "plugins": fake_plugins,
                    "plugins.platforms": fake_platforms,
                    "plugins.platforms.telegram": fake_telegram,
                    "plugins.platforms.telegram.adapter": fake_adapter,
                },
            ):
                hermes_v2._install_telegram_batch_identity_shim(owner)
                adapter = TelegramAdapter()
                first = FakeEvent(
                    text="first",
                    source=FakeSource(platform="telegram"),
                )
                first.message_id = "501"
                second = FakeEvent(
                    text="second",
                    source=FakeSource(platform="telegram"),
                )
                second.message_id = "502"
                adapter._enqueue_text_event(first)
                adapter._enqueue_text_event(second)
                batch = adapter._pending_text_batches["room"]
                retained = getattr(
                    batch,
                    hermes_v2._NATIVE_BATCH_EVENTS_ATTRIBUTE,
                )
                self.assertEqual("first\nsecond", batch.text)
                self.assertEqual(
                    [("501", "first"), ("502", "second")],
                    [(event.message_id, event.text) for event in retained],
                )
        finally:
            hermes_v2._SHIM_OWNER = None

    def test_native_hooks_are_preferred_when_present(self):
        llm = FakeLlm([])
        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(Path(temporary), llm=llm)
            ctx.participant_host_api_version = 2
            ctx.gateway_message_hook_api_version = 2
            fake_gateway = types.ModuleType("gateway")
            fake_hooks = types.ModuleType("gateway.message_hooks")

            @dataclass
            class GatewayMessageRoute:
                self_actor_id: str

            fake_hooks.GatewayMessageRoute = GatewayMessageRoute
            dashboard_home = Path(temporary) / "hermes-home"
            with (
                mock.patch.dict(
                    sys.modules,
                    {
                        "gateway": fake_gateway,
                        "gateway.message_hooks": fake_hooks,
                    },
                ),
                mock.patch.object(
                    hermes_v2, "_hermes_version", return_value="0.19.0"
                ),
                mock.patch.dict(
                    "os.environ",
                    {"HERMES_HOME": str(dashboard_home)},
                    clear=False,
                ),
            ):
                plugin = hermes_v2.register(ctx, config_loader=lambda _: config)
            self.assertEqual("native-v2-hooks", plugin.mode)
            self.assertEqual(
                {"gateway_message", "gateway_session_cancel", "gateway_shutdown"},
                set(ctx.hooks),
            )
            self.assertIn("nunchi", ctx.commands)
            manifest = (
                dashboard_home
                / "plugins"
                / "nunchi-dashboard"
                / "dashboard"
                / "manifest.json"
            )
            self.assertEqual(
                "nunchi",
                json.loads(manifest.read_text(encoding="utf-8"))["name"],
            )

    def test_current_native_route_without_self_identity_uses_checked_shim(self):
        llm = FakeLlm([])
        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(Path(temporary), llm=llm)
            ctx.participant_host_api_version = 2
            ctx.gateway_message_hook_api_version = 2
            fake_gateway = types.ModuleType("gateway")
            fake_hooks = types.ModuleType("gateway.message_hooks")

            @dataclass
            class GatewayMessageRoute:
                chat_id: str

            fake_hooks.GatewayMessageRoute = GatewayMessageRoute
            with mock.patch.dict(
                sys.modules,
                {
                    "gateway": fake_gateway,
                    "gateway.message_hooks": fake_hooks,
                },
            ):
                self.assertFalse(hermes_v2._native_api_available(ctx))

    def test_versions_before_019_fail_before_configuration(self):
        ctx = FakeCtx(FakeLlm([]))
        with (
            mock.patch.object(hermes_v2, "_hermes_version", return_value="0.18.9"),
            self.assertRaisesRegex(Exception, "0.19.0 or newer"),
        ):
            hermes_v2.register(
                ctx,
                config_loader=lambda _: self.fail("configuration must not load"),
            )

    def test_unknown_runner_shape_fails_activation(self):
        class GatewayRunner:
            async def _handle_message(self):
                return None

            async def stop(self, *, restart=False):
                del restart

            def _is_user_authorized(self, source):
                del source
                return True

            def _adapter_for_source(self, source):
                del source
                return FakeAdapter()

        fake_gateway = types.ModuleType("gateway")
        fake_run = types.ModuleType("gateway.run")
        fake_run.GatewayRunner = GatewayRunner
        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(Path(temporary), llm=FakeLlm([]))
            plugin = hermes_v2.NunchiHermesV2Plugin(
                config=config,
                ctx=ctx,
                hermes_version="future",
                mode="runtime-monkeypatch",
            )
            original_gateway = sys.modules.get("gateway")
            original_run = sys.modules.get("gateway.run")
            sys.modules["gateway"] = fake_gateway
            sys.modules["gateway.run"] = fake_run
            hermes_v2._SHIM_OWNER = None
            try:
                with self.assertRaisesRegex(Exception, "message handler shape"):
                    hermes_v2._install_compatibility_shim(plugin)
            finally:
                hermes_v2._SHIM_OWNER = None
                if original_gateway is None:
                    sys.modules.pop("gateway", None)
                else:
                    sys.modules["gateway"] = original_gateway
                if original_run is None:
                    sys.modules.pop("gateway.run", None)
                else:
                    sys.modules["gateway.run"] = original_run

    def test_pinned_config_rejects_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile_path = root / "profile.json"
            profile_data = {
                "profile_id": "profile",
                "participant_id": "participant",
                "actor_id": "discord:actor:999",
                "instructions": "Be useful.",
                "provenance": "test",
            }
            profile_path.write_text(json.dumps(profile_data))
            profile_path.chmod(0o600)
            profile_sha = hashlib.sha256(profile_path.read_bytes()).hexdigest()
            config_path = root / "config.json"
            config_data = {
                "schema_version": 2,
                "hermes_profile": "default",
                "state_directory": str(root / "state"),
                "rooms": [
                    {
                        "binding": {
                            "participant_id": "participant",
                            "actor_id": "discord:actor:999",
                            "platform": "discord",
                            "room_id": "42",
                            "continuity_scope_id": "room-42",
                            "provenance": "test",
                        },
                        "profile": {
                            "path": str(profile_path),
                            "sha256": profile_sha,
                        },
                        "attention": {"policy": {}},
                        "limits": {},
                        "participant": {"timeout_seconds": 2},
                    }
                ],
            }
            config_path.write_text(json.dumps(config_data))
            config_path.chmod(0o600)
            digest = hashlib.sha256(config_path.read_bytes()).hexdigest()
            loaded = hermes_v2.load_pinned_config(
                config_path,
                expected_sha256=digest,
                hermes_profile="default",
            )
            self.assertEqual("42", loaded.rooms[0].binding.room_id)
            config_path.write_text(json.dumps({**config_data, "rooms": []}))
            with self.assertRaisesRegex(Exception, "pinned digest"):
                hermes_v2.load_pinned_config(
                    config_path,
                    expected_sha256=digest,
                    hermes_profile="default",
                )

    def test_state_directory_must_be_absolute_and_private(self):
        with self.assertRaisesRegex(Exception, "path must be absolute"):
            hermes_v2._prepare_private_directory(
                Path("relative-state"),
                "Hermes V2 state directory",
            )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state"
            hermes_v2._prepare_private_directory(
                path,
                "Hermes V2 state directory",
            )
            self.assertEqual(0, path.stat().st_mode & 0o077)
            config, ctx = room_config(path, llm=FakeLlm([]))
            hermes_v2.NunchiHermesV2Plugin(
                config=config,
                ctx=ctx,
                hermes_version="0.19.0",
                mode="runtime-monkeypatch",
            )
            room_directories = [entry for entry in path.iterdir() if entry.is_dir()]
            self.assertEqual(1, len(room_directories))
            self.assertEqual(0, room_directories[0].stat().st_mode & 0o077)

    def test_package_has_entry_point_without_hermes_dependency(self):
        pyproject = Path("pyproject.toml").read_text()
        self.assertIn('[project.entry-points."hermes_agent.plugins"]', pyproject)
        self.assertIn('nunchi = "nunchi.integrations.hermes_v2"', pyproject)
        dependencies = pyproject.split("dependencies = [", 1)[1].split("]", 1)[0]
        self.assertNotIn("hermes", dependencies.lower())


if __name__ == "__main__":
    unittest.main()
