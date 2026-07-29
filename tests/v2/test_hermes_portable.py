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

from nunchi.attention import (
    AttentionModelSelection,
    AttentionPolicy,
    HostStructuredAttentionModel,
    ParticipantProfile,
    participant_attention_prompt,
)
from nunchi.integrations import hermes_v2
from nunchi.observation import ObservationLimits, ParticipantBinding


class FakeValue:
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
        self.platform = FakeValue(platform)
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
    def __init__(self, content: str) -> None:
        self.content = content
        self.mentions: list[FakeDiscordUser] = []
        self.mention_everyone = False
        self.author = FakeDiscordUser("100")
        self.reactions: list[tuple[object, ...]] = []

    async def add_reaction(self, reaction: str) -> None:
        self.reactions.append(("add", reaction))

    async def remove_reaction(self, reaction: str, user: object) -> None:
        self.reactions.append(("remove", reaction, user))


class FakeEvent:
    def __init__(
        self,
        *,
        text: str = "hello",
        message_id: str = "500",
        source: FakeSource | None = None,
    ) -> None:
        self.text = text
        self.source = source or FakeSource()
        self.message_id = message_id
        self.message_type = FakeValue("text")
        self.raw_message = FakeRawDiscordMessage(text)
        self.media_urls: list[str] = []
        self.media_types: list[str] = []
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
        self._client = types.SimpleNamespace(
            user=FakeDiscordUser("999", name="nunchi", bot=True)
        )


class FakeStructuredResult:
    def __init__(
        self,
        parsed: dict,
        *,
        provider: str = "test-provider",
        model: str = "test-model",
    ) -> None:
        self.output_parsed = parsed
        self.parsed = parsed
        self.provider = provider
        self.model = model


class FakeLlm:
    def __init__(self, results: list[dict | BaseException]) -> None:
        self.results = list(results)
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def complete_structured(self, **kwargs):
        with self._lock:
            self.calls.append(kwargs)
            result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return FakeStructuredResult(
            result,
            provider=kwargs["provider"],
            model=kwargs["model"],
        )


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


def judgment(
    disposition: str,
    event_id: str,
    *,
    pass_confidence: float = 0.01,
) -> dict:
    return {
        "disposition": disposition,
        "reasons": ["test decision"],
        "evidence_event_ids": [event_id],
        "legacy_verdict_confidences": {
            "PASS": pass_confidence,
            "ACK": 0.01,
            "ASK": 0.08,
            "SPEAK": 0.9 if pass_confidence < 0.5 else 0.01,
        },
    }


def room_config(
    root: Path,
    *,
    llm: FakeLlm,
    attention: AttentionPolicy | None = None,
    platform: str = "discord",
) -> tuple[hermes_v2.HermesPluginConfig, FakeCtx]:
    actor_id = f"{platform}:actor:999"
    profile = ParticipantProfile(
        profile_id="profile",
        participant_id="participant",
        actor_id=actor_id,
        instructions="Be useful and concise.",
        provenance="test",
        sha256="a" * 64,
    )
    room = hermes_v2.HermesRoomConfig(
        binding=ParticipantBinding(
            participant_id="participant",
            actor_id=actor_id,
            platform=platform,
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
        attention_model=AttentionModelSelection(
            provider="test-provider",
            model="test-model",
        ),
        limits=ObservationLimits(),
        participant_timeout_seconds=2,
        participant_max_expansions=1,
    )
    return (
        hermes_v2.HermesPluginConfig(
            hermes_profile="default",
            state_directory=root,
            rooms=(room,),
            provenance={"path": "/test/config.json", "sha256": "b" * 64},
        ),
        FakeCtx(llm),
    )


class HermesPortableTests(unittest.TestCase):
    def setUp(self) -> None:
        hermes_v2._SHIM_OWNER = None
        hermes_v2._ORIGINAL_BASE_HANDLE = None

    def plugin(
        self,
        root: Path,
        llm: FakeLlm,
        *,
        attention: AttentionPolicy | None = None,
    ) -> tuple[hermes_v2.NunchiHermesV2Plugin, FakeCtx]:
        config, ctx = room_config(root, llm=llm, attention=attention)
        return (
            hermes_v2.NunchiHermesV2Plugin(
                config=config,
                ctx=ctx,
                hermes_version="0.19.0",
                mode="process-local-gate",
            ),
            ctx,
        )

    def test_module_import_does_not_require_hermes(self):
        source = inspect.getsource(hermes_v2)
        before_runtime_shims = source.split(
            "def _active_discord_adapter_class",
            maxsplit=1,
        )[0]
        self.assertNotIn("import gateway.", before_runtime_shims)
        self.assertNotIn("import hermes_cli", before_runtime_shims)

    def test_integration_reuses_only_the_shared_attention_model(self):
        source = inspect.getsource(hermes_v2)
        self.assertIn("HostStructuredAttentionModel", source)
        self.assertNotIn("HostStructuredParticipant(", source)
        for copied_owner in (
            "class HermesAttentionModel",
            "class HermesParticipant",
            "_ATTENTION_SCHEMA",
            "_PARTICIPANT_SCHEMA",
            "def participant_attention_prompt",
            "def participant_turn_prompt",
        ):
            self.assertNotIn(copied_owner, source)

    def test_attention_prompt_and_model_are_shared_core_inputs(self):
        llm = FakeLlm([judgment("WAKE", "discord:message:500")])
        profile = ParticipantProfile(
            profile_id="profile",
            participant_id="participant",
            actor_id="discord:actor:999",
            instructions="Be useful and concise.",
            provenance="test",
            sha256="a" * 64,
        )
        model = HostStructuredAttentionModel(
            llm,
            AttentionModelSelection(
                provider="test-provider",
                model="test-model",
            ),
        )
        model.judge(
            instructions=participant_attention_prompt(profile),
            projection={"events": []},
            timeout_seconds=2,
        )
        self.assertEqual("test-provider", llm.calls[0]["provider"])
        self.assertEqual("test-model", llm.calls[0]["model"])
        self.assertIn(
            "Uncertainty must return DEFER, never SUPPRESS",
            llm.calls[0]["instructions"],
        )

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

    def test_generic_platform_uses_native_identity_and_mentions(self):
        adapter = types.SimpleNamespace(
            nunchi_self_identity=lambda: {"id": "999", "name": "bot"}
        )
        self.assertEqual(("999", "bot"), hermes_v2._self_identity(adapter, "matrix"))
        event = FakeEvent(source=FakeSource(platform="matrix"))
        event.mentioned_user_ids = ["999"]
        event.mentions_room = False
        binding = ParticipantBinding(
            participant_id="participant",
            actor_id="matrix:actor:999",
            platform="matrix",
            room_id="42",
            continuity_scope_id="room-42",
        )
        canonical, _ = hermes_v2.normalize_message_event(
            event,
            source=event.source,
            binding=binding,
            self_native_id="999",
            self_username="bot",
        )
        self.assertEqual(["matrix:actor:999"], canonical["mentioned_actor_ids"])

    def test_unknown_generic_mentions_fail_closed(self):
        event = FakeEvent(source=FakeSource(platform="matrix"))
        binding = ParticipantBinding(
            participant_id="participant",
            actor_id="matrix:actor:999",
            platform="matrix",
            room_id="42",
            continuity_scope_id="room-42",
        )
        with self.assertRaisesRegex(Exception, "stable native mention"):
            hermes_v2.normalize_message_event(
                event,
                source=event.source,
                binding=binding,
                self_native_id="999",
                self_username="bot",
            )

    def test_missing_generic_adapter_facts_wake_stock_without_suppression(self):
        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(
                Path(temporary),
                llm=FakeLlm([]),
                platform="matrix",
            )
            plugin = hermes_v2.NunchiHermesV2Plugin(
                config=config,
                ctx=ctx,
                hermes_version="0.19.0",
                mode="process-local-gate",
            )
            stock = mock.AsyncMock()
            asyncio.run(
                plugin.gate_ingress(
                    adapter=types.SimpleNamespace(),
                    event=FakeEvent(source=FakeSource(platform="matrix")),
                    stock_handle=stock,
                )
            )
            stock.assert_awaited_once()
            self.assertEqual([], ctx.llm.calls)

    def test_self_binding_mismatch_wakes_stock_without_suppression(self):
        with tempfile.TemporaryDirectory() as temporary:
            plugin, ctx = self.plugin(Path(temporary), FakeLlm([]))
            adapter = FakeAdapter()
            adapter._client.user = FakeDiscordUser("998", name="other", bot=True)
            stock = mock.AsyncMock()
            asyncio.run(
                plugin.gate_ingress(
                    adapter=adapter,
                    event=FakeEvent(),
                    stock_handle=stock,
                )
            )
            stock.assert_awaited_once()
            self.assertEqual([], ctx.llm.calls)

    def test_wake_calls_stock_hermes_once_and_no_participant_model(self):
        llm = FakeLlm([judgment("WAKE", "discord:message:500")])
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), llm)
            calls: list[str] = []

            async def stock(adapter, event):
                del adapter
                calls.append(event.message_id)

            handled = asyncio.run(
                plugin.gate_ingress(
                    adapter=FakeAdapter(),
                    event=FakeEvent(),
                    stock_handle=stock,
                )
            )
            self.assertTrue(handled)
            self.assertEqual(["500"], calls)
            self.assertEqual(1, len(llm.calls))
            self.assertEqual(
                participant_attention_prompt(
                    plugin.config.rooms[0].profile
                ),
                llm.calls[0]["instructions"],
            )

    def test_suppress_is_silent_before_stock_hermes(self):
        llm = FakeLlm(
            [judgment("SUPPRESS", "discord:message:500", pass_confidence=0.9)]
        )
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), llm)
            stock = mock.AsyncMock()
            asyncio.run(
                plugin.gate_ingress(
                    adapter=FakeAdapter(),
                    event=FakeEvent(),
                    stock_handle=stock,
                )
            )
            stock.assert_not_awaited()
            self.assertEqual(1, len(llm.calls))

    def test_defer_bypass_and_error_wake_use_stock_hermes(self):
        cases = (
            (
                AttentionPolicy(
                    suppression_enabled=True,
                    suppression_recovery_verified=True,
                ),
                [judgment("DEFER", "discord:message:500")],
            ),
            (
                AttentionPolicy(preattention_enabled=False),
                [],
            ),
            (
                AttentionPolicy(error_action="WAKE"),
                [RuntimeError("offline")],
            ),
        )
        for policy, results in cases:
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as temporary:
                plugin, _ = self.plugin(
                    Path(temporary),
                    FakeLlm(results),
                    attention=policy,
                )
                stock = mock.AsyncMock()
                asyncio.run(
                    plugin.gate_ingress(
                        adapter=FakeAdapter(),
                        event=FakeEvent(),
                        stock_handle=stock,
                    )
                )
                stock.assert_awaited_once()

    def test_error_no_wake_is_silent(self):
        llm = FakeLlm([RuntimeError("offline")])
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                llm,
                attention=AttentionPolicy(error_action="NO_WAKE"),
            )
            stock = mock.AsyncMock()
            asyncio.run(
                plugin.gate_ingress(
                    adapter=FakeAdapter(),
                    event=FakeEvent(),
                    stock_handle=stock,
                )
            )
            stock.assert_not_awaited()

    def test_busy_room_retains_only_newest_pending_stock_turn(self):
        entered = threading.Event()
        release = threading.Event()

        class BlockingLlm(FakeLlm):
            def complete_structured(self, **kwargs):
                with self._lock:
                    self.calls.append(kwargs)
                    index = len(self.calls)
                if index == 1:
                    entered.set()
                    release.wait(2)
                projection = json.loads(kwargs["input"][0]["text"])["observation"]
                return FakeStructuredResult(
                    judgment("WAKE", projection["trigger_event_id"])
                )

        llm = BlockingLlm([])
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), llm)
            adapter = FakeAdapter()
            stock_calls: list[str] = []

            async def stock(_adapter, event):
                stock_calls.append(event.message_id)

            async def run() -> None:
                first = FakeEvent(message_id="500")
                active = asyncio.create_task(
                    plugin.gate_ingress(
                        adapter=adapter,
                        event=first,
                        stock_handle=stock,
                    )
                )
                self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                await plugin.gate_ingress(
                    adapter=adapter,
                    event=FakeEvent(message_id="501"),
                    stock_handle=stock,
                )
                newest = FakeEvent(message_id="502")
                await plugin.gate_ingress(
                    adapter=adapter,
                    event=newest,
                    stock_handle=stock,
                )
                release.set()
                await active
                runtime = plugin._rooms[("discord", "42")]
                trace = runtime.stock_trace(first)
                self.assertIsNotNone(trace)
                trace.assistant_observed = True
                trace.assistant_response = "first response"
                trace.delivery_attempted = True
                trace.delivery_succeeded = True
                trace.processing_outcome = "SUCCESS"
                await plugin.complete_stock_turn(
                    adapter=adapter,
                    event=first,
                    stock_handle=stock,
                )

            try:
                asyncio.run(run())
            finally:
                release.set()
            self.assertEqual(["500", "502"], stock_calls)
            self.assertEqual(2, len(llm.calls))

    def test_stock_settlement_writes_truthful_host_and_transport_receipts(self):
        llm = FakeLlm([judgment("WAKE", "discord:message:500")])
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), llm)
            adapter = FakeAdapter()
            event = FakeEvent()
            stock = mock.AsyncMock()

            async def run() -> None:
                await plugin.gate_ingress(
                    adapter=adapter,
                    event=event,
                    stock_handle=stock,
                )
                runtime = plugin._rooms[("discord", "42")]
                trace = runtime.stock_trace(event)
                self.assertIsNotNone(trace)
                trace.assistant_observed = True
                trace.assistant_response = "hello"
                trace.delivery_attempted = True
                trace.delivery_succeeded = True
                trace.delivery_detail = "discord-message-1"
                trace.processing_outcome = "SUCCESS"
                await plugin.complete_stock_turn(
                    adapter=adapter,
                    event=event,
                    stock_handle=stock,
                )

            asyncio.run(run())
            records = plugin._rooms[("discord", "42")].receipts.all_records()
            self.assertEqual(
                ["observation", "attention", "participant-host", "transport"],
                [record["stage"] for record in records],
            )
            self.assertEqual("sent", records[2]["body"]["outcome"])
            self.assertEqual("sent", records[3]["body"]["delivery"])

    def test_stock_silence_has_no_transport_receipt(self):
        llm = FakeLlm([judgment("WAKE", "discord:message:500")])
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), llm)
            event = FakeEvent()

            async def run() -> None:
                await plugin.gate_ingress(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
                runtime = plugin._rooms[("discord", "42")]
                trace = runtime.stock_trace(event)
                trace.assistant_observed = True
                trace.assistant_response = ""
                trace.processing_outcome = "SUCCESS"
                await plugin.complete_stock_turn(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )

            asyncio.run(run())
            records = plugin._rooms[("discord", "42")].receipts.all_records()
            self.assertEqual(
                ["observation", "attention", "participant-host"],
                [record["stage"] for record in records],
            )
            self.assertEqual("silent", records[-1]["body"]["outcome"])

    def test_cancellation_settles_active_turn_and_discards_pending(self):
        llm = FakeLlm(
            [
                judgment("WAKE", "discord:message:500"),
                judgment("WAKE", "discord:message:501"),
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), llm)
            adapter = FakeAdapter()
            active = FakeEvent(message_id="500")
            stock = mock.AsyncMock()

            async def run() -> None:
                await plugin.gate_ingress(
                    adapter=adapter,
                    event=active,
                    stock_handle=stock,
                )
                await plugin.gate_ingress(
                    adapter=adapter,
                    event=FakeEvent(message_id="501"),
                    stock_handle=stock,
                )
                await plugin.gateway_session_cancel(
                    route=active.source,
                    reason="stop",
                )
                runtime = plugin._rooms[("discord", "42")]
                trace = runtime.stock_trace(active)
                trace.processing_outcome = "CANCELLED"
                await plugin.complete_stock_turn(
                    adapter=adapter,
                    event=active,
                    stock_handle=stock,
                )

            asyncio.run(run())
            self.assertEqual(1, stock.await_count)
            self.assertEqual(1, len(llm.calls))
            records = plugin._rooms[("discord", "42")].receipts.all_records()
            self.assertEqual("unknown", records[-2]["body"]["outcome"])
            self.assertEqual("failed", records[-1]["body"]["delivery"])

    def test_restart_replay_is_observed_without_attention_or_stock_turn(self):
        llm = FakeLlm([])
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), llm)
            event = FakeEvent()
            event._hermes_startup_restore_replay = True
            stock = mock.AsyncMock()
            asyncio.run(
                plugin.gate_ingress(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=stock,
                )
            )
            stock.assert_not_awaited()
            self.assertEqual([], llm.calls)

    def test_ingress_shim_suppresses_before_stock_and_passes_commands(self):
        class Runner:
            def __init__(self) -> None:
                self.authorized = True

            def _is_user_authorized(self, source):
                del source
                return self.authorized

        class BasePlatformAdapter:
            def __init__(self) -> None:
                self.gateway_runner = Runner()
                self._client = types.SimpleNamespace(
                    user=FakeDiscordUser("999", name="nunchi", bot=True)
                )
                self.stock: list[str] = []

            async def handle_message(self, event):
                self.stock.append(event.text)

        modules = {
            "gateway": types.ModuleType("gateway"),
            "gateway.platforms": types.ModuleType("gateway.platforms"),
            "gateway.platforms.base": types.ModuleType("gateway.platforms.base"),
        }
        modules["gateway.platforms.base"].BasePlatformAdapter = BasePlatformAdapter
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm(
                    [judgment("SUPPRESS", "discord:message:500", pass_confidence=0.9)]
                ),
            )
            with mock.patch.dict(sys.modules, modules):
                hermes_v2._install_claimed_ingress_shim(plugin)
            adapter = BasePlatformAdapter()
            asyncio.run(adapter.handle_message(FakeEvent()))
            asyncio.run(adapter.handle_message(FakeEvent(text="/status")))
            adapter.gateway_runner.authorized = False
            asyncio.run(adapter.handle_message(FakeEvent(text="unauthorized")))
            self.assertEqual(["/status", "unauthorized"], adapter.stock)

    def test_stock_lifecycle_shim_preserves_processing_hooks_and_send(self):
        class Outcome:
            name = "SUCCESS"

        class Runner:
            def _is_user_authorized(self, source):
                del source
                return True

        class BasePlatformAdapter:
            def __init__(self, plugin) -> None:
                self.plugin = plugin
                self.gateway_runner = Runner()
                self._client = types.SimpleNamespace(
                    user=FakeDiscordUser("999", name="nunchi", bot=True)
                )
                self.processing: list[str] = []
                self.nunchi_context = None

            async def handle_message(self, event):
                await self._process_message_background(event, "session")

            async def _process_message_background(self, event, session_key):
                del session_key
                await self._run_processing_hook("on_processing_start", event)
                self.nunchi_context = self.plugin.pre_llm_call()
                self.plugin.post_llm_call(assistant_response="stock response")
                await self._send_with_retry("42", "stock response")
                await self._run_processing_hook(
                    "on_processing_complete",
                    event,
                    Outcome(),
                )

            async def _run_processing_hook(self, hook_name, *args, **kwargs):
                del args, kwargs
                self.processing.append(hook_name)

            async def _send_with_retry(self, *args, **kwargs):
                del args, kwargs
                return FakeSendResult(True, message_id="sent-1")

        modules = {
            "gateway": types.ModuleType("gateway"),
            "gateway.platforms": types.ModuleType("gateway.platforms"),
            "gateway.platforms.base": types.ModuleType("gateway.platforms.base"),
        }
        modules["gateway.platforms.base"].BasePlatformAdapter = BasePlatformAdapter
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm([judgment("WAKE", "discord:message:500")]),
            )
            with mock.patch.dict(sys.modules, modules):
                hermes_v2._install_claimed_ingress_shim(plugin)
                hermes_v2._install_stock_lifecycle_shim(plugin)
            adapter = BasePlatformAdapter(plugin)
            asyncio.run(adapter.handle_message(FakeEvent()))
            self.assertEqual(
                ["on_processing_start", "on_processing_complete"],
                adapter.processing,
            )
            self.assertIn(
                "discord:message:500",
                adapter.nunchi_context["context"],
            )
            records = plugin._rooms[("discord", "42")].receipts.all_records()
            self.assertEqual("sent", records[-1]["body"]["delivery"])

    def test_runner_result_shim_observes_stock_response_and_silence(self):
        class Runner:
            async def _handle_message(self, event):
                return event.result

        modules = {
            "gateway": types.ModuleType("gateway"),
            "gateway.run": types.ModuleType("gateway.run"),
        }
        modules["gateway.run"].GatewayRunner = Runner
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm([judgment("WAKE", "discord:message:500")]),
            )
            event = FakeEvent()
            event.result = ""

            async def run() -> None:
                await plugin.gate_ingress(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
                runtime = plugin._rooms[("discord", "42")]
                trace = runtime.stock_trace(event)
                token = hermes_v2._ACTIVE_STOCK_TURN.set(trace)
                try:
                    with mock.patch.dict(sys.modules, modules):
                        hermes_v2._install_runner_result_shim(plugin)
                    self.assertEqual("", await Runner()._handle_message(event))
                finally:
                    hermes_v2._ACTIVE_STOCK_TURN.reset(token)
                self.assertTrue(trace.assistant_observed)
                self.assertEqual("", trace.assistant_response)

            asyncio.run(run())

    def test_register_uses_process_local_gate_and_post_llm_observer(self):
        class Runner:
            def _is_user_authorized(self, source):
                del source
                return True

            async def _handle_message(self, event):
                del event
                return ""

            async def stop(self, *args, **kwargs):
                del args, kwargs

        class BasePlatformAdapter:
            async def handle_message(self, event):
                del event

            async def _process_message_background(self, event, session_key):
                del event, session_key

            async def _run_processing_hook(self, hook_name, *args, **kwargs):
                del hook_name, args, kwargs

            async def _send_with_retry(self, *args, **kwargs):
                del args, kwargs

        modules = {
            "gateway": types.ModuleType("gateway"),
            "gateway.platforms": types.ModuleType("gateway.platforms"),
            "gateway.platforms.base": types.ModuleType("gateway.platforms.base"),
            "gateway.run": types.ModuleType("gateway.run"),
        }
        modules["gateway.platforms.base"].BasePlatformAdapter = BasePlatformAdapter
        modules["gateway.run"].GatewayRunner = Runner
        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(Path(temporary), llm=FakeLlm([]))
            with (
                mock.patch.dict(sys.modules, modules),
                mock.patch.object(
                    hermes_v2,
                    "_hermes_version",
                    return_value="0.19.0",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_discord_room_admission_shim",
                ),
            ):
                plugin = hermes_v2.register(
                    ctx,
                    config_loader=lambda _: config,
                    dashboard_installer=lambda: None,
                )
            self.assertEqual("process-local-gate", plugin.mode)
            self.assertEqual({"pre_llm_call", "post_llm_call"}, set(ctx.hooks))
            self.assertIn("nunchi", ctx.commands)
            self.assertEqual(
                "stock-hermes",
                plugin.probe()["participant_execution"],
            )

    def test_versions_before_019_fail_with_a_supported_option(self):
        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(Path(temporary), llm=FakeLlm([]))
            with mock.patch.object(
                hermes_v2,
                "_hermes_version",
                return_value="0.18.9",
            ):
                with self.assertRaisesRegex(Exception, "0.19.0 or newer"):
                    hermes_v2.register(
                        ctx,
                        config_loader=lambda _: config,
                        dashboard_installer=lambda: None,
                    )

    def test_unknown_runtime_shape_names_upgrade_or_supported_build(self):
        with self.assertRaisesRegex(
            Exception,
            "Stock Hermes can continue without Nunchi",
        ):
            hermes_v2._require_signature(
                lambda other: None,
                required=("self", "event"),
                label="test ingress",
            )

    def test_pinned_config_rejects_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            document = {
                "schema_version": 2,
                "hermes_profile": "default",
                "state_directory": str(state),
                "rooms": [
                    {
                        "binding": {
                            "participant_id": "participant",
                            "actor_id": "matrix:actor:999",
                            "platform": "matrix",
                            "room_id": "42",
                            "continuity_scope_id": "room-42",
                            "provenance": "test",
                        },
                        "profile": {
                            "document": {
                                "profile_id": "profile",
                                "participant_id": "participant",
                                "actor_id": "matrix:actor:999",
                                "instructions": "Be useful.",
                                "provenance": "test",
                            }
                        },
                        "attention": {
                            "policy": {},
                            "model": {"provider": "test", "model": "small"},
                        },
                        "limits": {},
                        "participant": {
                            "timeout_seconds": 2,
                            "max_expansions": 1,
                        },
                    }
                ],
            }
            path = root / "config.json"
            raw = json.dumps(document).encode()
            path.write_bytes(raw)
            path.chmod(0o600)
            digest = hashlib.sha256(raw).hexdigest()
            loaded = hermes_v2.load_pinned_config(
                path,
                expected_sha256=digest,
                hermes_profile="default",
            )
            self.assertEqual("matrix", loaded.rooms[0].binding.platform)
            path.write_text("{}")
            with self.assertRaisesRegex(Exception, "pinned digest"):
                hermes_v2.load_pinned_config(
                    path,
                    expected_sha256=digest,
                    hermes_profile="default",
                )

    def test_package_has_entry_point_without_hermes_dependency(self):
        pyproject = (
            Path(__file__).resolve().parents[2] / "pyproject.toml"
        ).read_text()
        self.assertIn('nunchi = "nunchi.integrations.hermes_v2"', pyproject)
        dependencies = pyproject.split("dependencies = [", 1)[1].split("]", 1)[0]
        self.assertNotIn("hermes-agent", dependencies)


if __name__ == "__main__":
    unittest.main()
