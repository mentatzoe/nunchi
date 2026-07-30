from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
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
from nunchi.errors import ValidationError
from nunchi.integrations import hermes_v2
from nunchi.observation import (
    ObservationLimits,
    ParticipantBinding,
    SnapshotUnavailable,
)


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
    raw_response: object | None = None


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


def fake_profile_from_session_key(session_key: str | None) -> str | None:
    if not session_key:
        return None
    parts = str(session_key).split(":")
    if len(parts) < 2 or parts[0] != "agent":
        return None
    return "default" if parts[1] == "main" else parts[1]


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
    timeout_seconds: float = 2,
    hermes_profile: str = "default",
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
        participant_timeout_seconds=timeout_seconds,
        participant_max_expansions=1,
    )
    return (
        hermes_v2.HermesPluginConfig(
            hermes_profile=hermes_profile,
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
        timeout_seconds: float = 2,
        hermes_profile: str = "default",
    ) -> tuple[hermes_v2.NunchiHermesV2Plugin, FakeCtx]:
        config, ctx = room_config(
            root,
            llm=llm,
            attention=attention,
            timeout_seconds=timeout_seconds,
            hermes_profile=hermes_profile,
        )
        ctx.profile_name = hermes_profile
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

    def test_integration_reuses_shared_attention_and_opportunity_core(self):
        source = inspect.getsource(hermes_v2)
        self.assertIn("HostStructuredAttentionModel", source)
        self.assertIn("prepare_opportunity(", source)
        self.assertIn("participant_host_receipt_body(", source)
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

    def test_snapshot_reconstruction_uses_shared_error_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            llm = FakeLlm([])
            plugin, _ = self.plugin(Path(temporary), llm)
            runtime = plugin._rooms[("discord", "42")]
            original = runtime.observation.build_snapshot
            calls = 0

            def transient_snapshot(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise SnapshotUnavailable("transient snapshot fault")
                return original(*args, **kwargs)

            stock = mock.AsyncMock()
            event = FakeEvent()
            with mock.patch.object(
                runtime.observation,
                "build_snapshot",
                side_effect=transient_snapshot,
            ):
                asyncio.run(
                    plugin.gate_ingress(
                        adapter=FakeAdapter(),
                        event=event,
                        stock_handle=stock,
                    )
                )

            stock.assert_awaited_once()
            self.assertEqual([], llm.calls)
            trace = runtime.stock_trace(event)
            self.assertEqual("ERROR_FALLBACK", trace.wake["attention"]["source"])
            records = runtime.receipts.records(trace.request_id)
            self.assertEqual(
                "snapshot-reconstructed",
                records[1]["body"]["error"]["code"],
            )

    def test_unrecoverable_snapshot_is_explicit_and_effect_free(self):
        with tempfile.TemporaryDirectory() as temporary:
            llm = FakeLlm([])
            plugin, _ = self.plugin(Path(temporary), llm)
            runtime = plugin._rooms[("discord", "42")]
            stock = mock.AsyncMock()
            event = FakeEvent()
            with mock.patch.object(
                runtime.observation,
                "build_snapshot",
                side_effect=SnapshotUnavailable("unrecoverable snapshot"),
            ) as build_snapshot:
                asyncio.run(
                    plugin.gate_ingress(
                        adapter=FakeAdapter(),
                        event=event,
                        stock_handle=stock,
                    )
                )

            self.assertEqual(2, build_snapshot.call_count)
            stock.assert_not_awaited()
            self.assertEqual([], llm.calls)
            self.assertIn(
                "after one reconstruction attempt",
                event._nunchi_v2_operational_error,
            )
            probe = plugin.probe()
            self.assertIn(
                "after one reconstruction attempt",
                probe["rooms"][0]["last_operational_error"]["detail"],
            )
            self.assertEqual(
                "continuity-gap",
                runtime.observation.delivery_audits()[-1].outcome,
            )

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
                self.assertEqual(
                    [
                        "discord:message:500",
                        "discord:message:501",
                        "discord:message:502",
                    ],
                    [item["id"] for item in trace.wake["events"]],
                )
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
                stream = runtime.receipts.records(trace.request_id)
                host_receipt = next(
                    record
                    for record in stream
                    if record["stage"] == "participant-host"
                )
                self.assertEqual(
                    [item["id"] for item in trace.wake["events"]],
                    host_receipt["body"]["delivered_event_ids"],
                )
                self.assertEqual(
                    len(
                        json.dumps(
                            {
                                "actors": trace.wake["actors"],
                                "events": trace.wake["events"],
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                        ).encode()
                    ),
                    host_receipt["body"]["packet_byte_count"],
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
                trace.delivery_success_detail = "discord-message-1"
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
            self.assertEqual("unknown", records[2]["body"]["outcome"])
            self.assertFalse(records[2]["body"]["invoked"])
            self.assertEqual("sent", records[3]["body"]["delivery"])

    def test_partial_multi_send_failure_settles_unknown_not_sent(self):
        llm = FakeLlm([judgment("WAKE", "discord:message:500")])
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), llm)
            runtime = plugin._rooms[("discord", "42")]
            event = FakeEvent()

            async def run() -> None:
                await plugin.gate_ingress(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
                trace = runtime.stock_trace(event)
                trace.assistant_observed = True
                trace.assistant_response = "two sends"
                runtime.observe_stock_delivery(
                    trace,
                    result=FakeSendResult(True, message_id="first"),
                )
                runtime.observe_stock_delivery(
                    trace,
                    error=RuntimeError("second send failed"),
                )
                trace.processing_outcome = "FAILURE"
                await plugin.complete_stock_turn(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )

            asyncio.run(run())
            transport = runtime.receipts.all_records()[-1]["body"]
            self.assertEqual("unknown", transport["delivery"])
            self.assertEqual("second send failed", transport["detail"])

    def test_failed_reserved_send_settles_unknown_without_zero_dispatch_proof(self):
        llm = FakeLlm([judgment("WAKE", "discord:message:500")])
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), llm)
            runtime = plugin._rooms[("discord", "42")]
            event = FakeEvent()

            async def run() -> None:
                await plugin.gate_ingress(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
                trace = runtime.stock_trace(event)
                trace.assistant_observed = True
                trace.assistant_response = "possibly partial response"
                trace.native_effect_count = 1
                runtime.observe_stock_delivery(
                    trace,
                    error=RuntimeError("Hermes reported send failure"),
                )
                trace.processing_outcome = "FAILURE"
                await plugin.complete_stock_turn(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )

            asyncio.run(run())
            transport = runtime.receipts.all_records()[-1]["body"]
            self.assertEqual("unknown", transport["delivery"])
            self.assertEqual(
                "Hermes reported send failure",
                transport["detail"],
            )

    def test_success_with_partial_delivery_metadata_settles_unknown(self):
        partial_results = (
            FakeSendResult(
                True,
                message_id="forum-starter",
                raw_response={
                    "warnings": ["forum follow-up chunk failed"],
                },
            ),
            FakeSendResult(
                True,
                message_id="overflow-first",
                raw_response={
                    "partial_overflow": True,
                    "delivered_chunks": 1,
                    "total_chunks": 3,
                },
            ),
            FakeSendResult(
                False,
                message_id="telegram-first",
                error="overflow_continuation_failed",
                raw_response={
                    "delivered_prefix": "already visible",
                },
            ),
        )
        for result in partial_results:
            with self.subTest(raw_response=result.raw_response):
                llm = FakeLlm([judgment("WAKE", "discord:message:500")])
                with tempfile.TemporaryDirectory() as temporary:
                    plugin, _ = self.plugin(Path(temporary), llm)
                    runtime = plugin._rooms[("discord", "42")]
                    event = FakeEvent()

                    async def run() -> None:
                        await plugin.gate_ingress(
                            adapter=FakeAdapter(),
                            event=event,
                            stock_handle=mock.AsyncMock(),
                        )
                        trace = runtime.stock_trace(event)
                        trace.assistant_observed = True
                        trace.assistant_response = "partial response"
                        runtime.observe_stock_delivery(trace, result=result)
                        trace.processing_outcome = (
                            "SUCCESS" if result.success else "FAILURE"
                        )
                        await plugin.complete_stock_turn(
                            adapter=FakeAdapter(),
                            event=event,
                            stock_handle=mock.AsyncMock(),
                        )

                    asyncio.run(run())
                    transport = runtime.receipts.all_records()[-1]["body"]
                    self.assertEqual("unknown", transport["delivery"])
                    self.assertTrue(transport.get("detail"))

    def test_nested_effect_block_before_terminal_send_is_not_a_commit(self):
        class DelegatingAdapter:
            def __init__(self) -> None:
                self.outer_started = asyncio.Event()
                self.release_outer = asyncio.Event()
                self.native_effects: list[str] = []
                self.platform = FakeValue("discord")
                setattr(
                    self,
                    hermes_v2._ADAPTER_PROFILE_ATTRIBUTE,
                    "default",
                )

            def nunchi_self_identity(self):
                return {"id": "999", "username": "nunchi"}

            async def _send_with_retry(
                self,
                chat_id,
                content,
            ) -> FakeSendResult:
                self.outer_started.set()
                await self.release_outer.wait()
                return await self.send(chat_id, content)

            async def send(self, chat_id, content) -> FakeSendResult:
                del chat_id, content
                self.native_effects.append("send")
                return FakeSendResult(True, message_id="should-not-send")

        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm([judgment("WAKE", "discord:message:500")]),
            )
            runtime = plugin._rooms[("discord", "42")]
            event = FakeEvent()
            adapter = DelegatingAdapter()
            hermes_v2._SHIM_OWNER = plugin
            hermes_v2._wrap_stock_effect_methods(DelegatingAdapter)

            async def run() -> None:
                await plugin.gate_ingress(
                    adapter=adapter,
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
                trace = runtime.stock_trace(event)
                trace.participant_invoked = True
                trace.assistant_observed = True
                trace.assistant_response = "response"
                context_token = hermes_v2._ACTIVE_STOCK_TURN.set(trace)
                try:
                    effect = asyncio.create_task(
                        adapter._send_with_retry("42", "response")
                    )
                    await adapter.outer_started.wait()
                    runtime.cancel()
                    adapter.release_outer.set()
                    with self.assertRaises(hermes_v2._StockEffectBlocked):
                        await effect
                finally:
                    hermes_v2._ACTIVE_STOCK_TURN.reset(context_token)
                self.assertEqual(0, trace.native_effect_count)
                trace.processing_outcome = "CANCELLED"
                await plugin.complete_stock_turn(
                    adapter=adapter,
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )

            asyncio.run(run())
            self.assertEqual([], adapter.native_effects)
            transport = runtime.receipts.all_records()[-1]["body"]
            self.assertEqual("failed", transport["delivery"])

    def test_nested_effect_counts_only_the_terminal_commit(self):
        class DelegatingAdapter:
            def __init__(self) -> None:
                self.native_effects: list[str] = []
                self.platform = FakeValue("discord")
                setattr(
                    self,
                    hermes_v2._ADAPTER_PROFILE_ATTRIBUTE,
                    "default",
                )

            def nunchi_self_identity(self):
                return {"id": "999", "username": "nunchi"}

            async def _send_with_retry(
                self,
                chat_id,
                content,
            ) -> FakeSendResult:
                return await self.send(chat_id, content)

            async def send(self, chat_id, content) -> FakeSendResult:
                del chat_id, content
                self.native_effects.append("send")
                return FakeSendResult(True, message_id="sent")

        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm([judgment("WAKE", "discord:message:500")]),
            )
            runtime = plugin._rooms[("discord", "42")]
            event = FakeEvent()
            adapter = DelegatingAdapter()
            hermes_v2._SHIM_OWNER = plugin
            hermes_v2._wrap_stock_effect_methods(DelegatingAdapter)

            async def run() -> None:
                await plugin.gate_ingress(
                    adapter=adapter,
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
                trace = runtime.stock_trace(event)
                trace.participant_invoked = True
                trace.assistant_observed = True
                trace.assistant_response = "response"
                context_token = hermes_v2._ACTIVE_STOCK_TURN.set(trace)
                try:
                    result = await adapter._send_with_retry("42", "response")
                finally:
                    hermes_v2._ACTIVE_STOCK_TURN.reset(context_token)
                self.assertTrue(result.success)
                self.assertEqual(1, trace.native_effect_count)

            asyncio.run(run())
            self.assertEqual(["send"], adapter.native_effects)

    def test_same_name_fallback_delegation_is_platform_specific(self):
        discord = types.SimpleNamespace(platform=FakeValue("discord"))
        telegram = types.SimpleNamespace(platform=FakeValue("telegram"))

        for method in ("send_document", "send_image_file", "send_video"):
            self.assertTrue(
                hermes_v2._delegates_stock_effect(
                    discord,
                    outer=method,
                    inner=method,
                )
            )
        for method in (
            "send_voice",
            "send_image",
            "send_animation",
            "send_multiple_images",
        ):
            self.assertFalse(
                hermes_v2._delegates_stock_effect(
                    discord,
                    outer=method,
                    inner=method,
                )
            )
        for method in (
            "send_voice",
            "send_multiple_images",
            "send_image_file",
            "send_document",
            "send_video",
            "send_image",
        ):
            self.assertTrue(
                hermes_v2._delegates_stock_effect(
                    telegram,
                    outer=method,
                    inner=method,
                )
            )
        self.assertFalse(
            hermes_v2._delegates_stock_effect(
                telegram,
                outer="send_animation",
                inner="send_animation",
            )
        )

    def test_telegram_raw_helpers_leave_delivery_truth_to_outer_result(self):
        class TelegramLikeAdapter:
            def __init__(self) -> None:
                self.native_effects: list[str] = []
                self.platform = FakeValue("discord")
                setattr(
                    self,
                    hermes_v2._ADAPTER_PROFILE_ATTRIBUTE,
                    "default",
                )

            def nunchi_self_identity(self):
                return {"id": "999", "username": "nunchi"}

            async def send_image(
                self,
                chat_id,
                image_url,
                metadata=None,
            ) -> FakeSendResult:
                del image_url
                raw = await self._send_with_dm_topic_reply_anchor_retry(
                    object(),
                    {"chat_id": chat_id},
                    metadata,
                    None,
                    "image",
                )
                return FakeSendResult(True, message_id=str(raw.message_id))

            async def _send_with_dm_topic_reply_anchor_retry(
                self,
                send_fn,
                send_kwargs,
                metadata,
                reply_to_message_id,
                media_label,
                reset_media=None,
            ):
                del (
                    send_fn,
                    send_kwargs,
                    metadata,
                    reply_to_message_id,
                    media_label,
                    reset_media,
                )
                self.native_effects.append("media")
                return types.SimpleNamespace(message_id=101)

            async def send_update_prompt(
                self,
                chat_id,
                prompt,
                metadata=None,
            ) -> FakeSendResult:
                del prompt, metadata
                raw = await self._send_message_with_thread_fallback(
                    chat_id=chat_id
                )
                return FakeSendResult(True, message_id=str(raw.message_id))

            async def _send_message_with_thread_fallback(self, **kwargs):
                del kwargs
                self.native_effects.append("control")
                return types.SimpleNamespace(message_id=102)

        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm([judgment("WAKE", "discord:message:500")]),
            )
            runtime = plugin._rooms[("discord", "42")]
            event = FakeEvent()
            adapter = TelegramLikeAdapter()
            hermes_v2._wrap_stock_effect_methods(TelegramLikeAdapter)

            async def run() -> None:
                await plugin.gate_ingress(
                    adapter=adapter,
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
                trace = runtime.stock_trace(event)
                trace.participant_invoked = True
                trace.assistant_observed = True
                trace.assistant_response = "response"
                context_token = hermes_v2._ACTIVE_STOCK_TURN.set(trace)
                try:
                    self.assertTrue(
                        (await adapter.send_image("42", "https://image")).success
                    )
                    self.assertTrue(
                        (await adapter.send_update_prompt("42", "prompt")).success
                    )
                finally:
                    hermes_v2._ACTIVE_STOCK_TURN.reset(context_token)
                trace.processing_outcome = "SUCCESS"
                await plugin.complete_stock_turn(
                    adapter=adapter,
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )

            asyncio.run(run())
            self.assertEqual(["media", "control"], adapter.native_effects)
            transport = runtime.receipts.all_records()[-1]["body"]
            self.assertEqual("sent", transport["delivery"])
            self.assertEqual("102", transport["detail"])

    def test_post_delivery_typing_block_does_not_erase_message_commit(self):
        class TelegramLikeAdapter:
            def __init__(self) -> None:
                self.message_sent = asyncio.Event()
                self.release_typing = asyncio.Event()
                self.native_effects: list[str] = []
                self.platform = FakeValue("discord")
                setattr(
                    self,
                    hermes_v2._ADAPTER_PROFILE_ATTRIBUTE,
                    "default",
                )

            def nunchi_self_identity(self):
                return {"id": "999", "username": "nunchi"}

            async def send(
                self,
                chat_id,
                content,
                metadata=None,
            ) -> FakeSendResult:
                del content
                self.native_effects.append("send")
                self.message_sent.set()
                await self.release_typing.wait()
                await self.send_typing(chat_id, metadata=metadata)
                return FakeSendResult(True, message_id="sent")

            async def send_typing(self, chat_id, metadata=None) -> None:
                del chat_id, metadata
                self.native_effects.append("typing")

        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm([judgment("WAKE", "discord:message:500")]),
            )
            runtime = plugin._rooms[("discord", "42")]
            event = FakeEvent()
            adapter = TelegramLikeAdapter()
            hermes_v2._wrap_stock_effect_methods(TelegramLikeAdapter)

            async def run() -> None:
                await plugin.gate_ingress(
                    adapter=adapter,
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
                trace = runtime.stock_trace(event)
                trace.participant_invoked = True
                trace.assistant_observed = True
                trace.assistant_response = "response"
                context_token = hermes_v2._ACTIVE_STOCK_TURN.set(trace)
                try:
                    effect = asyncio.create_task(
                        adapter.send("42", "response")
                    )
                    await adapter.message_sent.wait()
                    runtime.cancel()
                    adapter.release_typing.set()
                    with self.assertRaises(hermes_v2._StockEffectBlocked):
                        await effect
                finally:
                    hermes_v2._ACTIVE_STOCK_TURN.reset(context_token)
                self.assertEqual(1, trace.native_effect_count)
                trace.processing_outcome = "CANCELLED"
                await plugin.complete_stock_turn(
                    adapter=adapter,
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )

            asyncio.run(run())
            self.assertEqual(["send"], adapter.native_effects)
            transport = runtime.receipts.all_records()[-1]["body"]
            self.assertEqual("unknown", transport["delivery"])

    def test_prepare_stock_effect_cancels_after_releasing_trace_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm([judgment("WAKE", "discord:message:500")]),
            )
            runtime = plugin._rooms[("discord", "42")]
            event = FakeEvent()

            async def admit() -> None:
                await plugin.gate_ingress(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )

            asyncio.run(admit())
            trace = runtime.stock_trace(event)
            trace.deadline = time.monotonic() - 1
            original_cancel = runtime.cancel
            worker_finished = threading.Event()
            worker: threading.Thread | None = None

            def checked_cancel() -> None:
                nonlocal worker

                def acquire_trace() -> None:
                    with trace.lock:
                        worker_finished.set()

                worker = threading.Thread(target=acquire_trace, daemon=True)
                worker.start()
                self.assertTrue(worker_finished.wait(0.5))
                original_cancel()

            with (
                mock.patch.object(runtime, "cancel", side_effect=checked_cancel),
                self.assertRaises(hermes_v2._StockEffectBlocked),
            ):
                runtime.prepare_stock_effect(trace, effect="send")
            self.assertIsNotNone(worker)
            worker.join(timeout=0.5)
            self.assertFalse(worker.is_alive())

    def test_committed_unacknowledged_send_settles_unknown_after_cancel(self):
        llm = FakeLlm([judgment("WAKE", "discord:message:500")])
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), llm)
            runtime = plugin._rooms[("discord", "42")]
            event = FakeEvent()

            async def run() -> None:
                await plugin.gate_ingress(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
                trace = runtime.stock_trace(event)
                trace.assistant_observed = True
                trace.assistant_response = "committed response"
                trace.native_effect_count = 1
                runtime.cancel()
                trace.processing_outcome = "CANCELLED"
                await plugin.complete_stock_turn(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )

            asyncio.run(run())
            transport = runtime.receipts.all_records()[-1]["body"]
            self.assertEqual("unknown", transport["delivery"])
            self.assertIn("transport result", transport["detail"])

    def test_stock_silence_has_no_transport_receipt(self):
        class SilentAdapter(FakeAdapter):
            def __init__(self) -> None:
                super().__init__()
                self.effects: list[str] = []

            async def send_typing(self, *args, **kwargs):
                del args, kwargs
                self.effects.append("typing")

            async def send(self, *args, **kwargs):
                del args, kwargs
                self.effects.append("message")
                return FakeSendResult(True, message_id="unexpected")

        llm = FakeLlm([judgment("WAKE", "discord:message:500")])
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), llm)
            event = FakeEvent()
            adapter = SilentAdapter()
            hermes_v2._wrap_stock_effect_methods(SilentAdapter)

            async def run() -> None:
                await plugin.gate_ingress(
                    adapter=adapter,
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
                runtime = plugin._rooms[("discord", "42")]
                trace = runtime.stock_trace(event)
                trace.participant_invoked = True
                context_token = hermes_v2._ACTIVE_STOCK_TURN.set(trace)
                try:
                    self.assertFalse(await adapter.send_typing("42"))
                    trace.assistant_observed = True
                    trace.assistant_response = ""
                    result = await adapter.send("42", "")
                    self.assertFalse(result.success)
                finally:
                    hermes_v2._ACTIVE_STOCK_TURN.reset(context_token)
                trace.processing_outcome = "SUCCESS"
                await plugin.complete_stock_turn(
                    adapter=adapter,
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
            self.assertEqual([], adapter.effects)

    def test_stock_reaction_waits_for_participant_invocation(self):
        class ReactionAdapter(FakeAdapter):
            def __init__(self) -> None:
                super().__init__()
                self.reactions: list[str] = []

            async def _add_reaction(self, message, emoji: str) -> None:
                del message
                self.reactions.append(emoji)

        llm = FakeLlm([judgment("WAKE", "discord:message:500")])
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), llm)
            event = FakeEvent()
            adapter = ReactionAdapter()
            hermes_v2._wrap_stock_effect_methods(ReactionAdapter)

            async def run() -> None:
                await plugin.gate_ingress(
                    adapter=adapter,
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
                runtime = plugin._rooms[("discord", "42")]
                trace = runtime.stock_trace(event)
                message = types.SimpleNamespace(
                    channel=types.SimpleNamespace(id="42")
                )
                context_token = hermes_v2._ACTIVE_STOCK_TURN.set(trace)
                try:
                    self.assertFalse(
                        await adapter._add_reaction(message, "👀")
                    )
                    self.assertEqual(0, trace.native_effect_count)
                    self.assertEqual(
                        ["observation", "attention"],
                        [
                            record["stage"]
                            for record in runtime.receipts.all_records()
                        ],
                    )
                    trace.participant_invoked = True
                    self.assertIsNone(
                        await adapter._add_reaction(message, "✅")
                    )
                finally:
                    hermes_v2._ACTIVE_STOCK_TURN.reset(context_token)
                self.assertEqual(1, trace.native_effect_count)

            asyncio.run(run())
            self.assertEqual(["✅"], adapter.reactions)
            records = plugin._rooms[("discord", "42")].receipts.all_records()
            self.assertEqual(
                ["observation", "attention", "participant-host"],
                [record["stage"] for record in records],
            )
            self.assertEqual("unknown", records[-1]["body"]["outcome"])
            self.assertTrue(records[-1]["body"]["invoked"])

    def test_stock_output_waits_for_participant_invocation(self):
        class OutputAdapter(FakeAdapter):
            def __init__(self) -> None:
                super().__init__()
                self.messages: list[str] = []

            async def send(self, chat_id, content):
                del chat_id
                self.messages.append(content)
                return FakeSendResult(True, message_id="sent")

        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm([judgment("WAKE", "discord:message:500")]),
            )
            runtime = plugin._rooms[("discord", "42")]
            event = FakeEvent()
            adapter = OutputAdapter()
            hermes_v2._wrap_stock_effect_methods(OutputAdapter)

            async def run() -> None:
                await plugin.gate_ingress(
                    adapter=adapter,
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
                trace = runtime.stock_trace(event)
                context_token = hermes_v2._ACTIVE_STOCK_TURN.set(trace)
                try:
                    blocked = await adapter.send("42", "premature")
                    self.assertFalse(blocked.success)
                    self.assertEqual(0, trace.native_effect_count)
                    self.assertEqual(
                        ["observation", "attention"],
                        [
                            record["stage"]
                            for record in runtime.receipts.all_records()
                        ],
                    )
                    trace.participant_invoked = True
                    delivered = await adapter.send("42", "participant")
                    self.assertTrue(delivered.success)
                finally:
                    hermes_v2._ACTIVE_STOCK_TURN.reset(context_token)

            asyncio.run(run())
            self.assertEqual(["participant"], adapter.messages)
            host = runtime.receipts.all_records()[-1]
            self.assertEqual("participant-host", host["stage"])
            self.assertTrue(host["body"]["invoked"])

    def test_stock_typing_stays_disabled_after_participant_response(self):
        class TypingAdapter(FakeAdapter):
            def __init__(self) -> None:
                super().__init__()
                self.typing_targets: list[str] = []

            async def send_typing(self, chat_id, metadata=None):
                del metadata
                self.typing_targets.append(str(chat_id))

        llm = FakeLlm([judgment("WAKE", "discord:message:500")])
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), llm)
            event = FakeEvent()
            adapter = TypingAdapter()
            hermes_v2._wrap_stock_effect_methods(TypingAdapter)

            async def run() -> None:
                await plugin.gate_ingress(
                    adapter=adapter,
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
                runtime = plugin._rooms[("discord", "42")]
                trace = runtime.stock_trace(event)
                trace.participant_invoked = True
                trace.assistant_observed = True
                trace.assistant_response = "response"
                context_token = hermes_v2._ACTIVE_STOCK_TURN.set(trace)
                try:
                    self.assertFalse(await adapter.send_typing("42"))
                finally:
                    hermes_v2._ACTIVE_STOCK_TURN.reset(context_token)
                await adapter.send_typing("77")

            asyncio.run(run())
            self.assertEqual(["77"], adapter.typing_targets)
            self.assertEqual(
                "disabled-configured-turns",
                plugin.probe()["stock_typing"],
            )

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

    def test_shutdown_settles_active_turn_and_invalidates_late_effects(self):
        class Adapter(FakeAdapter):
            def __init__(self) -> None:
                super().__init__()
                self.effects: list[str] = []

            async def send(self, chat_id, content):
                del chat_id, content
                self.effects.append("send")
                return FakeSendResult(True, message_id="late")

        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm([judgment("WAKE", "discord:message:500")]),
            )
            runtime = plugin._rooms[("discord", "42")]
            event = FakeEvent()
            adapter = Adapter()
            hermes_v2._wrap_stock_effect_methods(Adapter)

            async def admit() -> None:
                await plugin.gate_ingress(
                    adapter=adapter,
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )

            asyncio.run(admit())
            trace = runtime.stock_trace(event)
            trace.participant_invoked = True
            self.assertTrue(runtime.shutdown(0))
            self.assertIsNone(runtime.stock_trace(event))
            records = runtime.receipts.all_records()
            self.assertEqual(
                ["observation", "attention", "participant-host", "transport"],
                [record["stage"] for record in records],
            )
            self.assertTrue(records[-2]["body"]["invoked"])
            self.assertEqual("failed", records[-1]["body"]["delivery"])

            async def late_effect() -> None:
                token = hermes_v2._ACTIVE_STOCK_TURN.set(trace)
                try:
                    with self.assertRaises(hermes_v2._StockEffectBlocked):
                        await adapter.send("42", "late")
                finally:
                    hermes_v2._ACTIVE_STOCK_TURN.reset(token)

            asyncio.run(late_effect())
            self.assertEqual([], adapter.effects)

    def test_shutdown_returns_false_for_cancellation_ignoring_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm([judgment("WAKE", "discord:message:500")]),
            )
            runtime = plugin._rooms[("discord", "42")]
            event = FakeEvent()

            async def run() -> None:
                await plugin.gate_ingress(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
                trace = runtime.stock_trace(event)
                trace.participant_invoked = True
                started = asyncio.Event()
                release = asyncio.Event()

                async def ignoring_child() -> None:
                    started.set()
                    try:
                        await release.wait()
                    except asyncio.CancelledError:
                        await release.wait()

                async def execute() -> None:
                    self.assertTrue(runtime.begin_stock_processing(trace))
                    try:
                        await hermes_v2._run_stock_process_with_deadline(
                            runtime,
                            trace,
                            ignoring_child(),
                        )
                    finally:
                        runtime.finish_stock_processing(trace)

                task = asyncio.create_task(execute())
                await started.wait()
                settled = await asyncio.to_thread(runtime.shutdown, 0.01)
                self.assertFalse(settled)
                self.assertIsNone(runtime.stock_trace(event))
                self.assertEqual(
                    [
                        "observation",
                        "attention",
                        "participant-host",
                        "transport",
                    ],
                    [
                        record["stage"]
                        for record in runtime.receipts.all_records()
                    ],
                )
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                await asyncio.sleep(0)
                self.assertTrue(await asyncio.to_thread(runtime.shutdown, 0.1))

            asyncio.run(run())

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

    def test_discord_recovered_dispatch_marks_post_start_event_non_live(self):
        stock = mock.AsyncMock()
        holder: dict[str, object] = {}

        class DiscordAdapter:
            def __init__(self):
                self._client = types.SimpleNamespace(
                    user=FakeDiscordUser("999", name="nunchi", bot=True)
                )
                self.gateway_runner = Runner()

            def _discord_message_admission(self, message, *, claim):
                del message, claim
                return True, True

            def _discord_free_response_channels(self):
                return set()

            async def _dispatch_discord_message(self, message):
                del message

            async def _dispatch_recovered_message(self, message):
                del message
                event = FakeEvent()
                event.timestamp = datetime.now(timezone.utc)
                await holder["plugin"].gate_ingress(
                    adapter=self,
                    event=event,
                    stock_handle=stock,
                )

            def _missed_message_backfill_enabled(self):
                return False

            def _missed_message_backfill_channels(self):
                return set()

        class Runner:
            def __init__(self):
                self.config = types.SimpleNamespace(multiplex_profiles=False)

            def _is_user_authorized(self, source):
                del source
                return True

            def _configure_profile_adapter(
                self,
                adapter,
                profile_name,
                platform,
            ):
                del adapter, profile_name, platform

            async def _connect_adapter_with_timeout(
                self,
                adapter,
                platform,
                *,
                is_reconnect=False,
            ):
                del adapter, platform, is_reconnect
                return True

            def _active_profile_name(self):
                return "default"

        gateway = types.ModuleType("gateway")
        run_module = types.ModuleType("gateway.run")
        run_module.GatewayRunner = Runner
        gateway.run = run_module
        llm = FakeLlm([])
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), llm)
            holder["plugin"] = plugin
            with (
                mock.patch.dict(
                    sys.modules,
                    {"gateway": gateway, "gateway.run": run_module},
                ),
                mock.patch.object(
                    hermes_v2,
                    "_active_discord_adapter_class",
                    return_value=DiscordAdapter,
                ),
            ):
                hermes_v2._install_discord_room_admission_shim(plugin)
            adapter = DiscordAdapter()
            message = types.SimpleNamespace(
                channel=types.SimpleNamespace(id="42"),
                author=FakeDiscordUser("100", bot=True),
            )
            asyncio.run(adapter._dispatch_recovered_message(message))
            runtime = plugin._rooms[("discord", "42")]

        self.assertEqual([], llm.calls)
        self.assertEqual([], stock.await_args_list)
        self.assertEqual(
            ["discord:message:500"],
            [event["id"] for event in runtime.observation.retained_events()],
        )

    def test_discord_raw_exemptions_are_bound_to_exact_profile_adapter(self):
        class DiscordAdapter:
            def __init__(self):
                self._client = types.SimpleNamespace(
                    user=FakeDiscordUser("999", name="nunchi", bot=True)
                )
                self.gateway_runner = None
                self.recovery_during_connect = None

            def _discord_message_admission(self, message, *, claim):
                return (not bool(message.author.bot), claim)

            def _discord_free_response_channels(self):
                return set()

            async def _dispatch_discord_message(self, message):
                del message

            async def _dispatch_recovered_message(self, message):
                del message

            def _missed_message_backfill_enabled(self):
                return False

            def _missed_message_backfill_channels(self):
                return set()

            async def connect(self, *, is_reconnect=False):
                del is_reconnect
                self.recovery_during_connect = (
                    self._missed_message_backfill_enabled(),
                    self._missed_message_backfill_channels(),
                )
                return True

        class Runner:
            def __init__(self, configured, other):
                del configured, other
                self.config = types.SimpleNamespace(multiplex_profiles=True)
                self.adapters = {}
                self._profile_adapters = {}

            def _active_profile_name(self):
                return "default"

            def _is_user_authorized(self, source):
                del source
                return False

            def _configure_profile_adapter(
                self,
                adapter,
                profile_name,
                platform,
            ):
                del adapter, profile_name, platform

            async def _connect_adapter_with_timeout(
                self,
                adapter,
                platform,
                *,
                is_reconnect=False,
            ):
                del platform
                return await adapter.connect(is_reconnect=is_reconnect)

        gateway = types.ModuleType("gateway")
        run_module = types.ModuleType("gateway.run")
        run_module.GatewayRunner = Runner
        gateway.run = run_module
        configured = DiscordAdapter()
        other = DiscordAdapter()
        runner = Runner(configured, other)
        configured.gateway_runner = runner
        other.gateway_runner = runner
        message = types.SimpleNamespace(
            channel=types.SimpleNamespace(id="42"),
            author=FakeDiscordUser("100", bot=True),
        )

        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm([]),
                hermes_profile="fiction-writer",
            )
            with (
                mock.patch.dict(
                    sys.modules,
                    {"gateway": gateway, "gateway.run": run_module},
                ),
                mock.patch.object(
                    hermes_v2,
                    "_active_discord_adapter_class",
                    return_value=DiscordAdapter,
                ),
            ):
                hermes_v2._install_discord_room_admission_shim(plugin)
            runner._configure_profile_adapter(
                configured,
                "fiction-writer",
                "discord",
            )
            runner._configure_profile_adapter(other, "other", "discord")
            asyncio.run(
                runner._connect_adapter_with_timeout(
                    configured,
                    FakeValue("discord"),
                )
            )
            asyncio.run(
                runner._connect_adapter_with_timeout(
                    other,
                    FakeValue("discord"),
                )
            )

        self.assertEqual((True, {"42"}), configured.recovery_during_connect)
        self.assertEqual((False, set()), other.recovery_during_connect)
        self.assertEqual(
            (True, True),
            configured._discord_message_admission(message, claim=True),
        )
        self.assertEqual(
            (False, True),
            other._discord_message_admission(message, claim=True),
        )
        self.assertTrue(configured._missed_message_backfill_enabled())
        self.assertFalse(other._missed_message_backfill_enabled())
        self.assertEqual(
            {"42"},
            configured._missed_message_backfill_channels(),
        )
        self.assertEqual(set(), other._missed_message_backfill_channels())

    def test_discord_thread_guard_blocks_configured_channel_and_parent_only(self):
        class Response:
            def __init__(self) -> None:
                self.messages: list[tuple[str, bool]] = []

            async def send_message(
                self,
                content: str,
                *,
                ephemeral: bool,
            ) -> None:
                self.messages.append((content, ephemeral))

        class DiscordAdapter:
            def __init__(self, *, profile: str = "default") -> None:
                setattr(
                    self,
                    hermes_v2._ADAPTER_PROFILE_ATTRIBUTE,
                    profile,
                )
                self.created: list[str] = []
                self.authorized: list[str] = []

            async def _check_slash_authorization(
                self,
                interaction,
                command_text,
            ):
                del interaction
                self.authorized.append(command_text)
                return True

            async def _handle_thread_create_slash(self, interaction):
                self.created.append(str(interaction.channel_id))
                return "created"

        def interaction(
            channel_id: str,
            *,
            parent_id: str | None = None,
        ) -> object:
            parent = (
                types.SimpleNamespace(id=parent_id)
                if parent_id is not None
                else None
            )
            return types.SimpleNamespace(
                channel_id=channel_id,
                channel=types.SimpleNamespace(
                    id=channel_id,
                    parent_id=parent_id,
                    parent=parent,
                ),
                response=Response(),
            )

        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), FakeLlm([]))
            with mock.patch.object(
                hermes_v2,
                "_active_discord_adapter_class",
                return_value=DiscordAdapter,
            ):
                hermes_v2._install_discord_thread_guard(plugin)

            configured = DiscordAdapter()
            other_profile = DiscordAdapter(profile="other")
            configured_room = interaction("42")
            configured_child = interaction("77", parent_id="42")

            async def run() -> None:
                self.assertIsNone(
                    await configured._handle_thread_create_slash(
                        configured_room
                    )
                )
                self.assertIsNone(
                    await configured._handle_thread_create_slash(
                        configured_child
                    )
                )
                self.assertEqual(
                    "created",
                    await configured._handle_thread_create_slash(
                        interaction("77")
                    ),
                )
                self.assertEqual(
                    "created",
                    await other_profile._handle_thread_create_slash(
                        interaction("42")
                    ),
                )

            asyncio.run(run())
            self.assertEqual(["77"], configured.created)
            self.assertEqual(["42"], other_profile.created)
            self.assertEqual(["/thread", "/thread"], configured.authorized)
            self.assertEqual(
                [("/thread is unavailable in this Nunchi room.", True)],
                configured_room.response.messages,
            )
            self.assertEqual(
                [("/thread is unavailable in this Nunchi room.", True)],
                configured_child.response.messages,
            )
            runtime = plugin._rooms[("discord", "42")]
            self.assertIn(
                "Discord /thread",
                runtime._last_operational_error["detail"],
            )

    def test_discord_slash_guard_refuses_derived_command_before_defer(self):
        class Response:
            def __init__(self) -> None:
                self.deferred = 0
                self.messages: list[tuple[str, bool]] = []

            async def defer(self, *, ephemeral: bool) -> None:
                self.deferred += 1
                self.messages.append(("deferred", ephemeral))

            async def send_message(
                self,
                content: str,
                *,
                ephemeral: bool,
            ) -> None:
                self.messages.append((content, ephemeral))

        class DiscordAdapter:
            def __init__(self, *, profile: str = "default") -> None:
                setattr(
                    self,
                    hermes_v2._ADAPTER_PROFILE_ATTRIBUTE,
                    profile,
                )
                self.authorized: list[str] = []
                self.dispatched: list[str] = []

            async def _check_slash_authorization(
                self,
                interaction,
                command_text,
            ):
                del interaction
                self.authorized.append(command_text)
                return True

            async def _run_simple_slash(
                self,
                interaction,
                command_text,
                followup_msg=None,
            ):
                del followup_msg
                await interaction.response.defer(ephemeral=True)
                self.dispatched.append(command_text)

        def interaction(
            channel_id: str,
            *,
            parent_id: str | None = None,
        ) -> object:
            return types.SimpleNamespace(
                channel_id=channel_id,
                channel=types.SimpleNamespace(
                    id=channel_id,
                    parent_id=parent_id,
                ),
                response=Response(),
            )

        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), FakeLlm([]))
            with mock.patch.object(
                hermes_v2,
                "_active_discord_adapter_class",
                return_value=DiscordAdapter,
            ):
                hermes_v2._install_discord_slash_guard(plugin)

            configured = DiscordAdapter()
            other_profile = DiscordAdapter(profile="other")
            refused = interaction("42")
            allowed = interaction("42")
            unconfigured = interaction("77")
            child = interaction("77", parent_id="42")
            other = interaction("42")

            async def run() -> None:
                await configured._run_simple_slash(refused, "/retry")
                await configured._run_simple_slash(allowed, "/status")
                await configured._run_simple_slash(
                    unconfigured,
                    "/background task",
                )
                await configured._run_simple_slash(child, "/queue task")
                await other_profile._run_simple_slash(other, "/steer task")

            asyncio.run(run())
            self.assertEqual(0, refused.response.deferred)
            self.assertEqual(
                [("/retry is unavailable in this Nunchi room.", True)],
                refused.response.messages,
            )
            self.assertEqual(
                ["/status", "/background task", "/queue task"],
                configured.dispatched,
            )
            self.assertEqual(["/steer task"], other_profile.dispatched)
            self.assertEqual(1, allowed.response.deferred)
            self.assertEqual(1, unconfigured.response.deferred)
            self.assertEqual(1, child.response.deferred)
            self.assertEqual(1, other.response.deferred)
            self.assertEqual(["/retry"], configured.authorized)

    def test_discord_voice_guard_stops_configured_input_before_stock(self):
        class DiscordAdapter:
            def __init__(
                self,
                *,
                profile: str = "default",
            ) -> None:
                setattr(
                    self,
                    hermes_v2._ADAPTER_PROFILE_ATTRIBUTE,
                    profile,
                )
                self._voice_text_channels = {1: "42", 2: "77"}
                self.processed: list[tuple[int, int, bytes]] = []

            async def _process_voice_input(
                self,
                guild_id,
                user_id,
                pcm_data,
            ):
                self.processed.append((guild_id, user_id, pcm_data))
                return "transcribed"

        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), FakeLlm([]))
            with mock.patch.object(
                hermes_v2,
                "_active_discord_adapter_class",
                return_value=DiscordAdapter,
            ):
                hermes_v2._install_voice_transcript_guard(plugin)

            configured = DiscordAdapter()
            other_profile = DiscordAdapter(profile="other")

            async def run() -> None:
                self.assertIsNone(
                    await configured._process_voice_input(1, 100, b"blocked")
                )
                self.assertEqual(
                    "transcribed",
                    await configured._process_voice_input(
                        2,
                        100,
                        b"unconfigured",
                    ),
                )
                self.assertEqual(
                    "transcribed",
                    await other_profile._process_voice_input(
                        1,
                        100,
                        b"other-profile",
                    ),
                )

            asyncio.run(run())
            self.assertEqual(
                [(2, 100, b"unconfigured")],
                configured.processed,
            )
            self.assertEqual(
                [(1, 100, b"other-profile")],
                other_profile.processed,
            )
            runtime = plugin._rooms[("discord", "42")]
            self.assertIn(
                "before transcription",
                runtime._last_operational_error["detail"],
            )

    def test_handoff_guard_blocks_configured_homes_before_original(self):
        class Platform:
            def __new__(cls, value):
                if value not in {"discord", "telegram"}:
                    raise ValueError(value)
                return value

        class Adapter:
            def __init__(
                self,
                platform: str,
                *,
                profile: str = "default",
            ) -> None:
                self.platform = FakeValue(platform)
                setattr(
                    self,
                    hermes_v2._ADAPTER_PROFILE_ATTRIBUTE,
                    profile,
                )

        class Runner:
            def __init__(
                self,
                *,
                discord_home: str = "42",
                telegram_home: str = "42",
                profile: str = "default",
            ) -> None:
                self.adapters = {
                    "discord": Adapter("discord", profile=profile),
                    "telegram": Adapter("telegram", profile=profile),
                }
                homes = {
                    "discord": types.SimpleNamespace(
                        chat_id=discord_home,
                        thread_id=None,
                    ),
                    "telegram": types.SimpleNamespace(
                        chat_id=telegram_home,
                        thread_id=None,
                    ),
                }
                self.config = types.SimpleNamespace(
                    get_home_channel=lambda platform: homes[platform],
                )
                self.processed: list[str] = []

            async def _process_handoff(self, row):
                self.processed.append(row["handoff_platform"])
                return "created"

        gateway = types.ModuleType("gateway")
        config_module = types.ModuleType("gateway.config")
        run_module = types.ModuleType("gateway.run")
        config_module.Platform = Platform
        run_module.GatewayRunner = Runner
        gateway.config = config_module
        gateway.run = run_module
        modules = {
            "gateway": gateway,
            "gateway.config": config_module,
            "gateway.run": run_module,
        }

        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(
                Path(temporary),
                llm=FakeLlm([]),
            )
            discord_room = config.rooms[0]
            telegram_room = replace(
                discord_room,
                binding=replace(
                    discord_room.binding,
                    actor_id="telegram:actor:999",
                    platform="telegram",
                    room_id="42",
                    continuity_scope_id="telegram-room-42",
                ),
                profile=replace(
                    discord_room.profile,
                    actor_id="telegram:actor:999",
                ),
            )
            plugin = hermes_v2.NunchiHermesV2Plugin(
                config=replace(
                    config,
                    rooms=(discord_room, telegram_room),
                ),
                ctx=ctx,
                hermes_version="0.19.0",
                mode="process-local-gate",
            )
            with mock.patch.dict(sys.modules, modules):
                hermes_v2._install_handoff_route_guard(plugin)

            configured = Runner()
            unconfigured = Runner(discord_home="77", telegram_home="77")
            other_profile = Runner(profile="other")

            async def run() -> None:
                for platform in ("discord", "telegram"):
                    with self.assertRaises(hermes_v2._StockEffectBlocked):
                        await configured._process_handoff(
                            {"handoff_platform": platform}
                        )
                    self.assertEqual(
                        "created",
                        await unconfigured._process_handoff(
                            {"handoff_platform": platform}
                        ),
                    )
                    self.assertEqual(
                        "created",
                        await other_profile._process_handoff(
                            {"handoff_platform": platform}
                        ),
                    )

            asyncio.run(run())
            self.assertEqual([], configured.processed)
            self.assertEqual(
                ["discord", "telegram"],
                unconfigured.processed,
            )
            self.assertEqual(
                ["discord", "telegram"],
                other_profile.processed,
            )
            for platform in ("discord", "telegram"):
                runtime = plugin._rooms[(platform, "42")]
                self.assertIn(
                    "before thread creation or session mutation",
                    runtime._last_operational_error["detail"],
                )

    def test_naive_native_timestamp_is_treated_as_unknown_not_compared(self):
        llm = FakeLlm([judgment("WAKE", "discord:message:500")])
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), llm)
            event = FakeEvent()
            event.timestamp = datetime.now().isoformat()
            asyncio.run(
                plugin.gate_ingress(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
            )
            self.assertEqual(1, len(llm.calls))
            retained = plugin._rooms[
                ("discord", "42")
            ].observation.retained_events()
            self.assertNotIn("timestamp", retained[0])

    def test_naive_datetime_is_not_assigned_a_timezone(self):
        event = FakeEvent()
        event.timestamp = datetime(2026, 7, 29, 12, 0, 0)
        binding = ParticipantBinding(
            participant_id="participant",
            actor_id="discord:actor:999",
            platform="discord",
            room_id="42",
            continuity_scope_id="room-42",
        )
        canonical, _ = hermes_v2.normalize_message_event(
            event,
            source=event.source,
            binding=binding,
            self_native_id="999",
            self_username="nunchi",
        )
        self.assertNotIn("timestamp", canonical)

    def test_ingress_shim_suppresses_before_stock_and_passes_lifecycle_controls(self):
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
            asyncio.run(adapter.handle_message(FakeEvent(text="/stop")))
            adapter.gateway_runner.authorized = False
            asyncio.run(adapter.handle_message(FakeEvent(text="unauthorized")))
            self.assertEqual(["/stop", "unauthorized"], adapter.stock)

    def test_configured_internal_ingress_fails_closed_and_records_gap(self):
        class Runner:
            def _is_user_authorized(self, source):
                del source
                raise AssertionError("internal events must fail closed first")

        class BasePlatformAdapter:
            def __init__(self) -> None:
                self.gateway_runner = Runner()
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
            plugin, _ = self.plugin(Path(temporary), FakeLlm([]))
            with mock.patch.dict(sys.modules, modules):
                hermes_v2._install_claimed_ingress_shim(plugin)
            adapter = BasePlatformAdapter()
            configured = FakeEvent(text="resume participant")
            configured.internal = True
            unconfigured = FakeEvent(
                text="stock internal",
                source=FakeSource(chat_id="77"),
            )
            unconfigured.internal = True

            asyncio.run(adapter.handle_message(configured))
            asyncio.run(adapter.handle_message(unconfigured))

            self.assertEqual(["stock internal"], adapter.stock)
            runtime = plugin._rooms[("discord", "42")]
            self.assertIn(
                "internal participant event",
                runtime._last_operational_error["detail"],
            )
            self.assertEqual(
                "continuity-gap",
                runtime.observation.delivery_audits()[-1].outcome,
            )

    def test_participant_and_unknown_commands_use_the_normal_gate(self):
        class Runner:
            def _is_user_authorized(self, source):
                del source
                return True

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
        commands = ("/undo 2", "/unknown")
        with tempfile.TemporaryDirectory() as temporary:
            plugin, ctx = self.plugin(
                Path(temporary),
                FakeLlm(
                    [
                        judgment(
                            "SUPPRESS",
                            f"discord:message:{message_id}",
                            pass_confidence=0.9,
                        )
                        for message_id in range(500, 500 + len(commands))
                    ]
                )
            )
            with mock.patch.dict(sys.modules, modules):
                hermes_v2._install_claimed_ingress_shim(plugin)
            adapter = BasePlatformAdapter()

            for offset, text in enumerate(commands):
                with self.subTest(text=text):
                    asyncio.run(
                        adapter.handle_message(
                            FakeEvent(
                                text=text,
                                message_id=str(500 + offset),
                            )
                        )
                    )

            self.assertEqual([], adapter.stock)
            self.assertEqual(len(commands), len(ctx.llm.calls))

    def test_derived_participant_commands_fail_closed_explicitly(self):
        class Runner:
            def _is_user_authorized(self, source):
                del source
                return True

        class BasePlatformAdapter:
            def __init__(self) -> None:
                self.gateway_runner = Runner()
                self.stock: list[str] = []

            async def handle_message(self, event):
                self.stock.append(event.text)

        modules = {
            "gateway": types.ModuleType("gateway"),
            "gateway.platforms": types.ModuleType("gateway.platforms"),
            "gateway.platforms.base": types.ModuleType("gateway.platforms.base"),
        }
        modules["gateway.platforms.base"].BasePlatformAdapter = BasePlatformAdapter
        commands = ("/background task", "/goal task", "/queue task", "/retry", "/steer task")
        with tempfile.TemporaryDirectory() as temporary:
            plugin, ctx = self.plugin(Path(temporary), FakeLlm([]))
            with mock.patch.dict(sys.modules, modules):
                hermes_v2._install_claimed_ingress_shim(plugin)
            adapter = BasePlatformAdapter()

            for offset, text in enumerate(commands):
                asyncio.run(
                    adapter.handle_message(
                        FakeEvent(
                            text=text,
                            message_id=str(500 + offset),
                        )
                    )
                )

            self.assertEqual([], adapter.stock)
            self.assertEqual([], ctx.llm.calls)
            runtime = plugin._rooms[("discord", "42")]
            self.assertIn(
                "/steer",
                runtime._last_operational_error["detail"],
            )
            self.assertEqual(
                ["background", "goal", "queue", "retry", "steer"],
                plugin.probe()["unsupported_configured_commands"],
            )
            self.assertEqual(
                len(commands),
                sum(
                    audit.outcome == "continuity-gap"
                    for audit in runtime.observation.delivery_audits()
                )
                - 1,
            )

    def test_woken_participant_command_reaches_stock_only_inside_the_gate(self):
        class Runner:
            def _is_user_authorized(self, source):
                del source
                return True

        class BasePlatformAdapter:
            def __init__(self) -> None:
                self.gateway_runner = Runner()
                self._client = types.SimpleNamespace(
                    user=FakeDiscordUser("999", name="nunchi", bot=True)
                )
                self.stock: list[tuple[str, bool]] = []

            async def handle_message(self, event):
                self.stock.append(
                    (
                        event.text,
                        hermes_v2._CONFIGURED_ROUTE_CONTEXT.get(),
                    )
                )

        modules = {
            "gateway": types.ModuleType("gateway"),
            "gateway.platforms": types.ModuleType("gateway.platforms"),
            "gateway.platforms.base": types.ModuleType("gateway.platforms.base"),
        }
        modules["gateway.platforms.base"].BasePlatformAdapter = BasePlatformAdapter
        with tempfile.TemporaryDirectory() as temporary:
            plugin, ctx = self.plugin(
                Path(temporary),
                FakeLlm([judgment("WAKE", "discord:message:500")]),
            )
            with mock.patch.dict(sys.modules, modules):
                hermes_v2._install_claimed_ingress_shim(plugin)
            adapter = BasePlatformAdapter()

            asyncio.run(adapter.handle_message(FakeEvent(text="/undo 2")))

            self.assertEqual([("/undo 2", True)], adapter.stock)
            self.assertEqual(1, len(ctx.llm.calls))

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
                hermes_v2._ACTIVE_STOCK_TURN.get().participant_invoked = True
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
            self.assertEqual("unknown", records[-2]["body"]["outcome"])
            self.assertEqual("sent", records[-1]["body"]["delivery"])

    def test_stock_lifecycle_rejects_unbound_derived_event_and_clears_unconfigured_trace(self):
        class Runner:
            def _is_user_authorized(self, source):
                del source
                return True

        class BasePlatformAdapter:
            def __init__(self) -> None:
                self.gateway_runner = Runner()
                self.observed: list[tuple[str, object | None]] = []

            async def handle_message(self, event):
                return await self._process_message_background(event, "session")

            async def _process_message_background(self, event, session_key):
                del session_key
                self.observed.append(
                    (event.text, hermes_v2._ACTIVE_STOCK_TURN.get())
                )

            async def _run_processing_hook(self, hook_name, *args, **kwargs):
                del hook_name, args, kwargs

            async def _send_with_retry(self, *args, **kwargs):
                del args, kwargs
                return FakeSendResult(True, message_id="unused")

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
            admitted = FakeEvent()
            asyncio.run(
                plugin.gate_ingress(
                    adapter=FakeAdapter(),
                    event=admitted,
                    stock_handle=mock.AsyncMock(),
                )
            )
            runtime = plugin._rooms[("discord", "42")]
            trace = runtime.stock_trace(admitted)
            derived = FakeEvent(
                text="derived retry prompt",
                message_id="501",
            )
            unconfigured = FakeEvent(
                text="unconfigured work",
                source=FakeSource(chat_id="77"),
            )
            adapter = BasePlatformAdapter()

            async def run() -> None:
                token = hermes_v2._ACTIVE_STOCK_TURN.set(trace)
                try:
                    with self.assertRaises(hermes_v2._StockEffectBlocked):
                        await adapter._process_message_background(
                            derived,
                            "session",
                        )
                    await adapter._process_message_background(
                        unconfigured,
                        "session",
                    )
                finally:
                    hermes_v2._ACTIVE_STOCK_TURN.reset(token)

            asyncio.run(run())
            self.assertEqual([("unconfigured work", None)], adapter.observed)
            self.assertIn(
                "derived Hermes participant work",
                runtime._last_operational_error["detail"],
            )

    def test_stock_effect_inventory_includes_direct_output_paths(self):
        for name in (
            "_send_with_retry",
            "send",
            "send_draft",
            "send_multiple_images",
            "send_typing",
            "stop_typing",
            "play_tts",
            "play_in_voice_channel",
            "play_ack_in_voice",
            "join_voice_channel",
            "leave_voice_channel",
            "create_handoff_thread",
            "edit_message",
            "delete_message",
            "_add_reaction",
            "_remove_reaction",
            "_set_reaction",
            "_clear_reactions",
        ):
            with self.subTest(name=name):
                self.assertTrue(hermes_v2._is_stock_effect_method(name))

    def test_out_of_band_effect_guard_blocks_only_configured_targets_and_profile(self):
        native: list[tuple[str, str, str]] = []

        class Adapter:
            def __init__(self, *, profile: str = "default") -> None:
                self.platform = FakeValue("discord")
                setattr(
                    self,
                    hermes_v2._ADAPTER_PROFILE_ATTRIBUTE,
                    profile,
                )

            async def send(
                self,
                chat_id,
                content,
                reply_to=None,
                metadata=None,
            ):
                del content, reply_to, metadata
                native.append(
                    (
                        "send",
                        getattr(
                            self,
                            hermes_v2._ADAPTER_PROFILE_ATTRIBUTE,
                        ),
                        str(chat_id),
                    )
                )
                return FakeSendResult(True, message_id="sent")

            async def send_draft(
                self,
                chat_id,
                draft_id,
                content,
                metadata=None,
            ):
                del draft_id, content, metadata
                native.append(
                    (
                        "draft",
                        getattr(self, hermes_v2._ADAPTER_PROFILE_ATTRIBUTE),
                        str(chat_id),
                    )
                )
                return FakeSendResult(True, message_id="draft")

            async def send_image(
                self,
                chat_id,
                image_url,
                caption=None,
                metadata=None,
            ):
                del image_url, caption, metadata
                native.append(
                    (
                        "image",
                        getattr(self, hermes_v2._ADAPTER_PROFILE_ATTRIBUTE),
                        str(chat_id),
                    )
                )
                return FakeSendResult(True, message_id="image")

            async def edit_message(
                self,
                chat_id,
                message_id,
                content,
            ):
                del message_id, content
                native.append(
                    (
                        "edit",
                        getattr(self, hermes_v2._ADAPTER_PROFILE_ATTRIBUTE),
                        str(chat_id),
                    )
                )
                return FakeSendResult(True, message_id="edited")

            async def _add_reaction(self, message, emoji):
                del emoji
                target = str(message.channel.id)
                native.append(
                    (
                        "reaction",
                        getattr(self, hermes_v2._ADAPTER_PROFILE_ATTRIBUTE),
                        target,
                    )
                )
                return True

            async def _send_file_attachment(
                self,
                chat_id,
                file_path,
            ):
                del file_path
                native.append(
                    (
                        "media",
                        getattr(self, hermes_v2._ADAPTER_PROFILE_ATTRIBUTE),
                        str(chat_id),
                    )
                )
                return FakeSendResult(True, message_id="media")

            async def _edit_overflow_split(
                self,
                channel,
                message,
                message_id,
                content,
            ):
                del message, message_id, content
                native.append(
                    (
                        "overflow-edit",
                        getattr(self, hermes_v2._ADAPTER_PROFILE_ATTRIBUTE),
                        str(channel.id),
                    )
                )
                return FakeSendResult(True, message_id="overflow")

        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), FakeLlm([]))
            hermes_v2._SHIM_OWNER = plugin
            hermes_v2._wrap_stock_effect_methods(Adapter)
            configured = Adapter()
            other_profile = Adapter(profile="other")
            ambiguous_platform = Adapter()
            del ambiguous_platform.platform
            configured_message = types.SimpleNamespace(
                channel=types.SimpleNamespace(id="42")
            )
            stock_message = types.SimpleNamespace(
                channel=types.SimpleNamespace(id="77")
            )
            runtime = plugin._rooms[("discord", "42")]

            async def run() -> None:
                with self.assertRaises(hermes_v2._StockEffectBlocked):
                    await configured.send("42", "blocked")
                with self.assertRaises(hermes_v2._StockEffectBlocked):
                    await configured.send(
                        "1",
                        "blocked thread",
                        metadata={"thread_id": "42"},
                    )
                with self.assertRaises(hermes_v2._StockEffectBlocked):
                    await ambiguous_platform.send(
                        "77",
                        "target cannot be proven unconfigured",
                    )
                blocked_calls = (
                    lambda: configured.send_draft("42", 1, "draft"),
                    lambda: configured.send_image("42", "https://image"),
                    lambda: configured.edit_message("42", "1", "edit"),
                    lambda: configured._add_reaction(
                        configured_message,
                        "👀",
                    ),
                    lambda: configured._send_file_attachment(
                        "42",
                        "/tmp/file",
                    ),
                    lambda: configured._edit_overflow_split(
                        configured_message.channel,
                        object(),
                        "1",
                        "overflow",
                    ),
                )
                for call in blocked_calls:
                    with self.assertRaises(hermes_v2._StockEffectBlocked):
                        await call()
                await configured.send("77", "stock room")
                await configured.send_draft("77", 1, "stock draft")
                await configured.send_image("77", "https://stock-image")
                await configured.edit_message("77", "1", "stock edit")
                await configured._add_reaction(stock_message, "✅")
                await configured._send_file_attachment("77", "/tmp/stock")
                await configured._edit_overflow_split(
                    stock_message.channel,
                    object(),
                    "1",
                    "stock overflow",
                )
                await other_profile.send("42", "stock profile")
                control_authorization = (
                    hermes_v2._StockControlAuthorization.begin(
                        "stop",
                        runtime,
                        configured,
                        object(),
                    )
                )
                control = hermes_v2._AUTHORIZED_STOCK_CONTROL.set(
                    control_authorization
                )
                try:
                    with self.assertRaises(hermes_v2._StockEffectBlocked):
                        await configured.send(
                            "77",
                            "cross-route control acknowledgement",
                        )
                    await configured.send("42", "control acknowledgement")
                    release = asyncio.Event()

                    async def stale_child() -> None:
                        await release.wait()
                        await configured.send("42", "stale control")

                    child = asyncio.create_task(stale_child())
                finally:
                    control_authorization.close_parent()
                    hermes_v2._AUTHORIZED_STOCK_CONTROL.reset(control)
                release.set()
                with self.assertRaises(hermes_v2._StockEffectBlocked):
                    await child

            asyncio.run(run())
            self.assertEqual(
                [
                    ("send", "default", "77"),
                    ("draft", "default", "77"),
                    ("image", "default", "77"),
                    ("edit", "default", "77"),
                    ("reaction", "default", "77"),
                    ("media", "default", "77"),
                    ("overflow-edit", "default", "77"),
                    ("send", "other", "42"),
                    ("send", "default", "42"),
                ],
                native,
            )
            self.assertIn(
                "out-of-band Hermes",
                runtime._last_operational_error["detail"],
            )

    def test_active_effects_are_bound_to_exact_discord_and_telegram_room(self):
        cases = (
            (
                "discord",
                "42",
                FakeSource(platform="discord", chat_id="42"),
                ("42", {}),
                ("77", {}),
            ),
            (
                "telegram",
                "42:topic:9",
                FakeSource(platform="telegram", chat_id="42"),
                ("42", {"metadata": {"thread_id": "9"}}),
                ("42", {"metadata": {"thread_id": "10"}}),
            ),
        )
        for platform, room_id, source, exact, cross_route in cases:
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temporary:
                native: list[tuple[str, dict]] = []

                class Adapter:
                    def __init__(
                        self,
                        *,
                        profile: str = "default",
                        adapter_platform: str = platform,
                    ) -> None:
                        self.platform = FakeValue(adapter_platform)
                        setattr(
                            self,
                            hermes_v2._ADAPTER_PROFILE_ATTRIBUTE,
                            profile,
                        )
                        self.gateway_runner = None

                    def nunchi_self_identity(self):
                        return {"id": "999", "username": "nunchi"}

                    async def send(
                        self,
                        chat_id,
                        content,
                        metadata=None,
                    ):
                        del content
                        native.append((str(chat_id), dict(metadata or {})))
                        return FakeSendResult(True, message_id="sent")

                config, ctx = room_config(
                    Path(temporary),
                    llm=FakeLlm(
                        [judgment("WAKE", f"{platform}:message:500")]
                    ),
                    platform=platform,
                )
                configured_room = replace(
                    config.rooms[0],
                    binding=replace(
                        config.rooms[0].binding,
                        room_id=room_id,
                    ),
                )
                plugin = hermes_v2.NunchiHermesV2Plugin(
                    config=replace(config, rooms=(configured_room,)),
                    ctx=ctx,
                    hermes_version="0.19.0",
                    mode="process-local-gate",
                )
                hermes_v2._SHIM_OWNER = plugin
                adapter = Adapter()
                replacement = Adapter()
                wrong_profile = Adapter(profile="other")
                wrong_platform = Adapter(
                    adapter_platform=(
                        "telegram" if platform == "discord" else "discord"
                    )
                )
                runner = types.SimpleNamespace(
                    config=types.SimpleNamespace(multiplex_profiles=False),
                    adapters={platform: replacement},
                )
                for candidate in (
                    adapter,
                    replacement,
                    wrong_profile,
                    wrong_platform,
                ):
                    candidate.gateway_runner = runner
                if platform == "telegram":
                    source.thread_id = "9"
                event = FakeEvent(source=source)
                event.mentioned_user_ids = []
                event.mentions_room = False
                asyncio.run(
                    plugin.gate_ingress(
                        adapter=adapter,
                        event=event,
                        stock_handle=mock.AsyncMock(),
                    )
                )
                runtime = plugin._rooms[(platform, room_id)]
                trace = runtime.stock_trace(event)
                self.assertIsNotNone(trace)
                trace.participant_invoked = True
                trace.assistant_observed = True
                trace.assistant_response = "response"

                async def run() -> None:
                    context = hermes_v2._ACTIVE_STOCK_TURN.set(trace)
                    try:
                        with self.assertRaises(hermes_v2._StockEffectBlocked):
                            await adapter.send(
                                cross_route[0],
                                "cross-route",
                                **cross_route[1],
                            )
                        runner.adapters = {platform: wrong_profile}
                        with self.assertRaises(hermes_v2._StockEffectBlocked):
                            await wrong_profile.send(
                                exact[0],
                                "wrong-profile replacement",
                                **exact[1],
                            )
                        runner.adapters = {platform: wrong_platform}
                        with self.assertRaises(hermes_v2._StockEffectBlocked):
                            await wrong_platform.send(
                                exact[0],
                                "wrong-platform replacement",
                                **exact[1],
                            )
                        self.assertEqual(0, trace.native_effect_count)
                        runner.adapters = {platform: replacement}
                        await replacement.send(
                            exact[0],
                            "exact-route replacement",
                            **exact[1],
                        )
                    finally:
                        hermes_v2._ACTIVE_STOCK_TURN.reset(context)

                asyncio.run(run())
                self.assertEqual(
                    [(exact[0], dict(exact[1].get("metadata") or {}))],
                    native,
                )
                self.assertEqual(1, trace.native_effect_count)

    def test_out_of_band_telegram_nested_routes_resolve_exact_topics(self):
        native: list[tuple[str, str, str]] = []

        class Adapter:
            def __init__(self) -> None:
                self.platform = FakeValue("telegram")
                setattr(
                    self,
                    hermes_v2._ADAPTER_PROFILE_ATTRIBUTE,
                    "default",
                )

            async def _send_with_dm_topic_reply_anchor_retry(
                self,
                send_fn,
                send_kwargs,
                metadata,
                reply_to_message_id,
                media_label,
                reset_media=None,
            ):
                del (
                    send_fn,
                    metadata,
                    reply_to_message_id,
                    media_label,
                    reset_media,
                )
                native.append(
                    (
                        "media",
                        str(send_kwargs["chat_id"]),
                        str(send_kwargs["message_thread_id"]),
                    )
                )
                return object()

            async def rename_dm_topic(self, chat_id, thread_id, name):
                del name
                native.append(("rename", str(chat_id), str(thread_id)))

        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(
                Path(temporary),
                llm=FakeLlm([]),
                platform="telegram",
            )
            room = replace(
                config.rooms[0],
                binding=replace(
                    config.rooms[0].binding,
                    room_id="42:topic:9",
                ),
            )
            plugin = hermes_v2.NunchiHermesV2Plugin(
                config=replace(config, rooms=(room,)),
                ctx=ctx,
                hermes_version="0.19.0",
                mode="process-local-gate",
            )
            hermes_v2._SHIM_OWNER = plugin
            hermes_v2._wrap_stock_effect_methods(Adapter)
            adapter = Adapter()

            async def invoke(chat_id: str, thread_id: int) -> None:
                await adapter._send_with_dm_topic_reply_anchor_retry(
                    object(),
                    {
                        "chat_id": chat_id,
                        "message_thread_id": thread_id,
                    },
                    None,
                    None,
                    "image",
                )
                await adapter.rename_dm_topic(chat_id, thread_id, "topic")

            async def run() -> None:
                with self.assertRaises(hermes_v2._StockEffectBlocked):
                    await adapter._send_with_dm_topic_reply_anchor_retry(
                        object(),
                        {"chat_id": "42", "message_thread_id": 9},
                        None,
                        None,
                        "image",
                    )
                with self.assertRaises(hermes_v2._StockEffectBlocked):
                    await adapter.rename_dm_topic("42", 9, "configured")
                await invoke("77", 11)

            asyncio.run(run())
            self.assertEqual(
                [("media", "77", "11"), ("rename", "77", "11")],
                native,
            )

    def test_receipt_failure_blocks_direct_draft_before_native_effect(self):
        class Runner:
            def _is_user_authorized(self, source):
                del source
                return True

        class BasePlatformAdapter:
            def __init__(self) -> None:
                self.gateway_runner = Runner()
                self._client = types.SimpleNamespace(
                    user=FakeDiscordUser("999", name="nunchi", bot=True)
                )
                self.native_effects: list[str] = []

            async def handle_message(self, event):
                await self._process_message_background(event, "session")

            async def _process_message_background(self, event, session_key):
                del session_key
                hermes_v2._ACTIVE_STOCK_TURN.get().participant_invoked = True
                await self.send_draft("42", "direct draft")

            async def _run_processing_hook(self, hook_name, *args, **kwargs):
                del hook_name, args, kwargs

            async def _send_with_retry(self, *args, **kwargs):
                del args, kwargs
                raise AssertionError("_send_with_retry must not be used")

            async def send_draft(self, *args, **kwargs):
                del args, kwargs
                self.native_effects.append("draft")
                return FakeSendResult(True, message_id="draft-1")

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
            runtime = plugin._rooms[("discord", "42")]
            original_append = runtime.receipts.append
            failed = False

            def append(record, *, writer):
                nonlocal failed
                if record["stage"] == "participant-host" and not failed:
                    failed = True
                    raise OSError("fsync failed")
                return original_append(record, writer=writer)

            with mock.patch.dict(sys.modules, modules):
                hermes_v2._install_claimed_ingress_shim(plugin)
                hermes_v2._install_stock_lifecycle_shim(plugin)
            adapter = BasePlatformAdapter()
            with (
                mock.patch.object(runtime.receipts, "append", side_effect=append),
                self.assertRaises(asyncio.CancelledError),
            ):
                asyncio.run(adapter.handle_message(FakeEvent()))
            self.assertEqual([], adapter.native_effects)
            records = runtime.receipts.all_records()
            self.assertEqual("unknown", records[-2]["body"]["outcome"])
            self.assertEqual("failed", records[-1]["body"]["delivery"])

    def test_native_effect_commit_orders_cancellation(self):
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm([judgment("WAKE", "discord:message:500")]),
            )
            runtime = plugin._rooms[("discord", "42")]
            event = FakeEvent()
            native: list[str] = []

            async def before_commit() -> None:
                await plugin.gate_ingress(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
                trace = runtime.stock_trace(event)
                runtime.cancel()
                with self.assertRaises(hermes_v2._StockEffectBlocked):
                    runtime.commit_stock_effect(
                        trace,
                        effect="send",
                        operation=lambda: asyncio.sleep(
                            0,
                            result=native.append("too-late"),
                        ),
                    )

            asyncio.run(before_commit())
            self.assertEqual([], native)

        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm([judgment("WAKE", "discord:message:500")]),
            )
            runtime = plugin._rooms[("discord", "42")]
            event = FakeEvent()
            native = []

            async def after_commit() -> None:
                await plugin.gate_ingress(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
                trace = runtime.stock_trace(event)

                async def send() -> FakeSendResult:
                    native.append("sent")
                    return FakeSendResult(True, message_id="committed")

                task = runtime.commit_stock_effect(
                    trace,
                    effect="send",
                    operation=send,
                )
                runtime.cancel()
                await task
                trace.assistant_observed = True
                trace.assistant_response = "response"
                trace.processing_outcome = "CANCELLED"
                await plugin.complete_stock_turn(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )

            asyncio.run(after_commit())
            self.assertEqual(["sent"], native)
            self.assertEqual(
                "unknown",
                runtime.receipts.all_records()[-1]["body"]["delivery"],
            )

    def test_absolute_deadline_blocks_cancellation_ignoring_late_draft(self):
        class SlowLlm(FakeLlm):
            def complete_structured(self, **kwargs):
                time.sleep(0.03)
                return super().complete_structured(**kwargs)

        class Runner:
            def _is_user_authorized(self, source):
                del source
                return True

        class BasePlatformAdapter:
            def __init__(self) -> None:
                self.gateway_runner = Runner()
                self._client = types.SimpleNamespace(
                    user=FakeDiscordUser("999", name="nunchi", bot=True)
                )
                self.native_effects: list[str] = []
                self.late_effect_blocked = False

            async def handle_message(self, event):
                await self._process_message_background(event, "session")

            async def _process_message_background(self, event, session_key):
                del event, session_key
                hermes_v2._ACTIVE_STOCK_TURN.get().participant_invoked = True
                try:
                    await asyncio.sleep(0.04)
                except asyncio.CancelledError:
                    # Model the upstream task ignoring cancellation and trying
                    # to emit anyway. The final native boundary must still win.
                    pass
                try:
                    await self.send_draft("42", "late draft")
                except hermes_v2._StockEffectBlocked:
                    self.late_effect_blocked = True

            async def _run_processing_hook(self, hook_name, *args, **kwargs):
                del hook_name, args, kwargs

            async def _send_with_retry(self, *args, **kwargs):
                del args, kwargs
                raise AssertionError("_send_with_retry must not be used")

            async def send_draft(self, *args, **kwargs):
                del args, kwargs
                self.native_effects.append("draft")
                return FakeSendResult(True, message_id="late-draft")

        modules = {
            "gateway": types.ModuleType("gateway"),
            "gateway.platforms": types.ModuleType("gateway.platforms"),
            "gateway.platforms.base": types.ModuleType("gateway.platforms.base"),
        }
        modules["gateway.platforms.base"].BasePlatformAdapter = BasePlatformAdapter
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                SlowLlm([judgment("WAKE", "discord:message:500")]),
                timeout_seconds=0.05,
            )
            with mock.patch.dict(sys.modules, modules):
                hermes_v2._install_claimed_ingress_shim(plugin)
                hermes_v2._install_stock_lifecycle_shim(plugin)
            adapter = BasePlatformAdapter()

            async def run() -> None:
                try:
                    await adapter.handle_message(FakeEvent())
                except asyncio.CancelledError:
                    pass
                await asyncio.sleep(0.08)

            asyncio.run(run())
            self.assertTrue(adapter.late_effect_blocked)
            self.assertEqual([], adapter.native_effects)
            records = plugin._rooms[("discord", "42")].receipts.all_records()
            self.assertEqual("unknown", records[-2]["body"]["outcome"])
            self.assertEqual("failed", records[-1]["body"]["delivery"])

    def test_tool_execution_boundary_fails_closed_before_dispatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm([judgment("WAKE", "discord:message:500")]),
            )
            event = FakeEvent()
            asyncio.run(
                plugin.gate_ingress(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
            )
            runtime = plugin._rooms[("discord", "42")]
            trace = runtime.stock_trace(event)
            context_token = hermes_v2._ACTIVE_STOCK_TURN.set(trace)
            middleware = types.ModuleType("hermes_cli.middleware")
            middleware.run_llm_execution_middleware = (
                lambda request, next_call, **context: next_call(request)
            )
            middleware.run_tool_execution_middleware = (
                lambda tool_name, args, next_call, **context: next_call(args)
            )
            hermes_cli = types.ModuleType("hermes_cli")
            hermes_cli.middleware = middleware
            try:
                hook_result = plugin.pre_tool_call(tool_name="terminal")
                self.assertEqual("block", hook_result["action"])
                with mock.patch.dict(
                    sys.modules,
                    {
                        "hermes_cli": hermes_cli,
                        "hermes_cli.middleware": middleware,
                    },
                ):
                    hermes_v2._install_execution_boundary_shim(plugin)
                result = middleware.run_tool_execution_middleware(
                    "terminal",
                    {"command": "pwd"},
                    lambda args: {"ok": args["command"]},
                )
            finally:
                hermes_v2._ACTIVE_STOCK_TURN.reset(context_token)
            self.assertIn("no final-effect hook", json.loads(result)["error"])
            records = runtime.receipts.all_records()
            self.assertEqual("attention", records[-1]["stage"])

    def test_execution_boundary_blocks_after_middleware_delay(self):
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm([judgment("WAKE", "discord:message:500")]),
                timeout_seconds=0.03,
            )
            event = FakeEvent()
            asyncio.run(
                plugin.gate_ingress(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
            )
            runtime = plugin._rooms[("discord", "42")]
            trace = runtime.stock_trace(event)
            native_calls: list[str] = []
            middleware = types.ModuleType("hermes_cli.middleware")

            def run_llm(request, next_call, **context):
                del context
                time.sleep(0.04)
                return next_call(request)

            def run_tool(tool_name, args, next_call, **context):
                del tool_name, context
                time.sleep(0.04)
                return next_call(args)

            middleware.run_llm_execution_middleware = run_llm
            middleware.run_tool_execution_middleware = run_tool
            hermes_cli = types.ModuleType("hermes_cli")
            hermes_cli.middleware = middleware
            with mock.patch.dict(
                sys.modules,
                {
                    "hermes_cli": hermes_cli,
                    "hermes_cli.middleware": middleware,
                },
            ):
                hermes_v2._install_execution_boundary_shim(plugin)
            context_token = hermes_v2._ACTIVE_STOCK_TURN.set(trace)
            try:
                result = middleware.run_tool_execution_middleware(
                    "terminal",
                    {"command": "mutate"},
                    lambda args: native_calls.append(args["command"]),
                )
            finally:
                hermes_v2._ACTIVE_STOCK_TURN.reset(context_token)
            self.assertIn("error", json.loads(result))
            self.assertEqual([], native_calls)

    def test_model_execution_boundary_blocks_provider_after_deadline(self):
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm([judgment("WAKE", "discord:message:500")]),
                timeout_seconds=0.03,
            )
            event = FakeEvent()
            asyncio.run(
                plugin.gate_ingress(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )
            )
            runtime = plugin._rooms[("discord", "42")]
            trace = runtime.stock_trace(event)
            provider_calls: list[str] = []
            middleware = types.ModuleType("hermes_cli.middleware")

            def run_llm(request, next_call, **context):
                del context
                time.sleep(0.04)
                return next_call(request)

            middleware.run_llm_execution_middleware = run_llm
            middleware.run_tool_execution_middleware = (
                lambda tool_name, args, next_call, **context: next_call(args)
            )
            hermes_cli = types.ModuleType("hermes_cli")
            hermes_cli.middleware = middleware
            with mock.patch.dict(
                sys.modules,
                {
                    "hermes_cli": hermes_cli,
                    "hermes_cli.middleware": middleware,
                },
            ):
                hermes_v2._install_execution_boundary_shim(plugin)
            context_token = hermes_v2._ACTIVE_STOCK_TURN.set(trace)
            try:
                result = middleware.run_llm_execution_middleware(
                    {"model": "test"},
                    lambda request: provider_calls.append(request["model"]),
                )
            finally:
                hermes_v2._ACTIVE_STOCK_TURN.reset(context_token)
            self.assertIsNone(result)
            self.assertEqual([], provider_calls)

    def test_auto_title_is_disabled_only_for_configured_turns(self):
        calls: list[str] = []
        title_generator = types.ModuleType("agent.title_generator")

        def maybe_auto_title(
            session_db,
            session_id,
            user_message,
            assistant_response,
            conversation_history,
            **kwargs,
        ):
            del session_db, user_message, assistant_response
            del conversation_history, kwargs
            calls.append(session_id)

        title_generator.maybe_auto_title = maybe_auto_title
        agent = types.ModuleType("agent")
        agent.title_generator = title_generator
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), FakeLlm([]))
            with mock.patch.dict(
                sys.modules,
                {
                    "agent": agent,
                    "agent.title_generator": title_generator,
                },
            ):
                hermes_v2._install_auto_title_shim(plugin)
            title_generator.maybe_auto_title(None, "stock", "u", "a", [])
            trace_token = hermes_v2._ACTIVE_STOCK_TURN.set(object())
            try:
                title_generator.maybe_auto_title(
                    None,
                    "configured",
                    "u",
                    "a",
                    [],
                )
            finally:
                hermes_v2._ACTIVE_STOCK_TURN.reset(trace_token)
        self.assertEqual(["stock"], calls)

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

    def test_runner_result_shim_maps_exact_eos_marker_to_silence(self):
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
                FakeLlm([judgment("DEFER", "discord:message:500")]),
            )
            event = FakeEvent()
            event.result = "<|eos|>"

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

                trace.processing_outcome = "SUCCESS"
                await plugin.complete_stock_turn(
                    adapter=FakeAdapter(),
                    event=event,
                    stock_handle=mock.AsyncMock(),
                )

            asyncio.run(run())
            records = plugin._rooms[
                ("discord", "42")
            ].receipts.all_records()
            self.assertEqual(
                ["observation", "attention", "participant-host"],
                [record["stage"] for record in records],
            )
            self.assertEqual("silent", records[-1]["body"]["outcome"])

    def test_stock_silence_marker_is_exact_not_a_substring_filter(self):
        self.assertEqual(
            "The token `<|eos|>` is documentation.",
            hermes_v2._stock_participant_response(
                "The token `<|eos|>` is documentation."
            ),
        )
        self.assertEqual(
            "",
            hermes_v2._stock_participant_response("  <|eos|>\n"),
        )

    def test_stock_stream_silence_filter_is_active_turn_only(self):
        response_filters = types.ModuleType("gateway.response_filters")
        stream_consumer = types.ModuleType("gateway.stream_consumer")
        exec(
            """
def is_intentional_silence_response(response):
    return response == "NO_REPLY"

def is_intentional_silence_agent_result(agent_result, response):
    return not agent_result.get("failed") and is_intentional_silence_response(response)

def is_partial_silence_marker(text):
    return text in {"N", "NO", "NO_REPLY"}
""",
            response_filters.__dict__,
        )
        original_response = (
            response_filters.is_intentional_silence_response
        )
        original_partial = response_filters.is_partial_silence_marker
        stream_consumer._is_intentional_silence_response = original_response
        stream_consumer._is_partial_silence_marker = original_partial

        class GatewayStreamConsumer:
            async def run(self):
                return (
                    stream_consumer._is_intentional_silence_response(""),
                    stream_consumer._is_partial_silence_marker(""),
                )

        stream_consumer.GatewayStreamConsumer = GatewayStreamConsumer
        gateway = types.ModuleType("gateway")
        gateway.response_filters = response_filters
        gateway.stream_consumer = stream_consumer
        modules = {
            "gateway": gateway,
            "gateway.response_filters": response_filters,
            "gateway.stream_consumer": stream_consumer,
        }

        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), FakeLlm([]))
            patches = []
            transaction = hermes_v2._PATCH_TRANSACTION.set(patches)
            try:
                with mock.patch.dict(sys.modules, modules):
                    hermes_v2._install_stock_silence_filter_shim(plugin)
                    hermes_v2._install_stock_silence_filter_shim(plugin)
            finally:
                hermes_v2._PATCH_TRANSACTION.reset(transaction)
            self.assertEqual(3, len(patches))

            self.assertFalse(
                stream_consumer._is_intentional_silence_response("<|eos|>")
            )
            self.assertFalse(
                stream_consumer._is_partial_silence_marker("<|e")
            )
            self.assertTrue(
                stream_consumer._is_intentional_silence_response("NO_REPLY")
            )

            async def split_stream() -> list[str]:
                native_calls: list[str] = []
                accumulated = ""
                for delta in ("<", "|e", "os", "|>"):
                    accumulated += delta
                    if not stream_consumer._is_partial_silence_marker(
                        accumulated
                    ):
                        native_calls.append(accumulated)
                if not stream_consumer._is_intentional_silence_response(
                    accumulated
                ):
                    native_calls.append(accumulated)
                return native_calls

            async def inherited_context() -> list[str]:
                token = hermes_v2._ACTIVE_STOCK_TURN.set(object())
                try:
                    task = asyncio.create_task(split_stream())
                finally:
                    hermes_v2._ACTIVE_STOCK_TURN.reset(token)
                return await task

            self.assertEqual([], asyncio.run(inherited_context()))
            token = hermes_v2._ACTIVE_STOCK_TURN.set(object())
            try:
                self.assertTrue(
                    response_filters.is_intentional_silence_agent_result(
                        {"failed": False},
                        "<|eos|>",
                    )
                )
                self.assertFalse(
                    response_filters.is_intentional_silence_agent_result(
                        {"failed": True},
                        "<|eos|>",
                    )
                )
                tts_calls: list[str] = []
                native_calls: list[str] = []
                response = "<|eos|>"
                if response_filters.is_intentional_silence_agent_result(
                    {"failed": False},
                    response,
                ):
                    response = ""
                if response:
                    tts_calls.append(response)
                    native_calls.append(response)
                self.assertEqual("", response)
                self.assertEqual([], tts_calls)
                self.assertEqual([], native_calls)
                self.assertFalse(
                    stream_consumer._is_intentional_silence_response(
                        "The token `<|eos|>` is documentation."
                    )
                )
                self.assertTrue(
                    stream_consumer._is_intentional_silence_response(
                        "NO_REPLY"
                    )
                )
            finally:
                hermes_v2._ACTIVE_STOCK_TURN.reset(token)
            hermes_v2._rollback_shim_attributes(patches)
            self.assertIs(
                original_response,
                response_filters.is_intentional_silence_response,
            )
            self.assertIs(
                original_response,
                stream_consumer._is_intentional_silence_response,
            )
            self.assertIs(
                original_partial,
                stream_consumer._is_partial_silence_marker,
            )
            original_response.__nunchi_stock_silence__ = True
            try:
                with (
                    mock.patch.dict(sys.modules, modules),
                    self.assertRaisesRegex(
                        ValidationError,
                        "streaming silence filter state",
                    ),
                ):
                    hermes_v2._install_stock_silence_filter_shim(plugin)
            finally:
                del original_response.__nunchi_stock_silence__

    def test_stock_stream_silence_filter_fails_closed_on_moved_calls(self):
        response_filters = types.ModuleType("gateway.response_filters")
        stream_consumer = types.ModuleType("gateway.stream_consumer")
        exec(
            """
def is_intentional_silence_response(response):
    return False

def is_intentional_silence_agent_result(agent_result, response):
    return is_intentional_silence_response(response)

def is_partial_silence_marker(text):
    return False
""",
            response_filters.__dict__,
        )
        stream_consumer._is_intentional_silence_response = (
            response_filters.is_intentional_silence_response
        )
        stream_consumer._is_partial_silence_marker = (
            response_filters.is_partial_silence_marker
        )

        class GatewayStreamConsumer:
            async def run(self):
                return None

        stream_consumer.GatewayStreamConsumer = GatewayStreamConsumer
        gateway = types.ModuleType("gateway")
        gateway.response_filters = response_filters
        gateway.stream_consumer = stream_consumer
        modules = {
            "gateway": gateway,
            "gateway.response_filters": response_filters,
            "gateway.stream_consumer": stream_consumer,
        }
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), FakeLlm([]))
            with (
                mock.patch.dict(sys.modules, modules),
                self.assertRaisesRegex(
                    ValidationError,
                    "streaming silence call sites",
                ),
            ):
                hermes_v2._install_stock_silence_filter_shim(plugin)

    def test_stock_streaming_tts_falls_back_before_active_turn_output(self):
        native_calls: list[str] = []
        tts_module = types.ModuleType("gateway.streaming_tts_consumer")

        class StreamingTTSConsumer:
            @property
            def active(self):
                return True

            def start(self):
                native_calls.append("streaming-tts-start")

        tts_module.StreamingTTSConsumer = StreamingTTSConsumer
        run_module = types.ModuleType("gateway.run")
        run_module.StreamingTTSConsumer = StreamingTTSConsumer
        exec(
            """
class GatewayRunner:
    async def _run_agent_inner(self, message, source, message_type=None):
        del self, message, source, message_type
        consumer = StreamingTTSConsumer()
        if consumer.active:
            consumer.start()
""",
            run_module.__dict__,
        )
        GatewayRunner = run_module.GatewayRunner
        gateway = types.ModuleType("gateway")
        gateway.run = run_module
        gateway.streaming_tts_consumer = tts_module
        modules = {
            "gateway": gateway,
            "gateway.run": run_module,
            "gateway.streaming_tts_consumer": tts_module,
        }
        original_active = StreamingTTSConsumer.active
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), FakeLlm([]))
            patches = []
            transaction = hermes_v2._PATCH_TRANSACTION.set(patches)
            try:
                with mock.patch.dict(sys.modules, modules):
                    hermes_v2._install_stock_streaming_tts_guard(plugin)
                    hermes_v2._install_stock_streaming_tts_guard(plugin)
            finally:
                hermes_v2._PATCH_TRANSACTION.reset(transaction)

            consumer = StreamingTTSConsumer()
            self.assertTrue(consumer.active)
            consumer.start()
            self.assertEqual(["streaming-tts-start"], native_calls)
            native_calls.clear()

            async def active_turn() -> None:
                token = hermes_v2._ACTIVE_STOCK_TURN.set(object())
                try:
                    await GatewayRunner()._run_agent_inner(
                        "message",
                        object(),
                        "voice",
                    )
                finally:
                    hermes_v2._ACTIVE_STOCK_TURN.reset(token)

            asyncio.run(active_turn())
            self.assertEqual([], native_calls)
            self.assertEqual(1, len(patches))
            hermes_v2._rollback_shim_attributes(patches)
            self.assertIs(original_active, StreamingTTSConsumer.active)

    def test_stock_streaming_tts_guard_is_noop_for_hermes_019_shape(self):
        run_module = types.ModuleType("gateway.run")
        exec(
            """
class GatewayRunner:
    async def _run_agent_inner(self, message, source):
        del self, message, source
        return {}
""",
            run_module.__dict__,
        )
        gateway = types.ModuleType("gateway")
        gateway.run = run_module
        modules = {
            "gateway": gateway,
            "gateway.run": run_module,
        }
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), FakeLlm([]))
            patches = []
            transaction = hermes_v2._PATCH_TRANSACTION.set(patches)
            try:
                with mock.patch.dict(sys.modules, modules):
                    hermes_v2._install_stock_streaming_tts_guard(plugin)
            finally:
                hermes_v2._PATCH_TRANSACTION.reset(transaction)
            self.assertEqual([], patches)

    def test_failed_or_cancelled_eos_turn_is_not_participant_silence(self):
        for processing_outcome in ("FAILURE", "CANCELLED"):
            with (
                self.subTest(processing_outcome=processing_outcome),
                tempfile.TemporaryDirectory() as temporary,
            ):
                plugin, _ = self.plugin(
                    Path(temporary),
                    FakeLlm([judgment("DEFER", "discord:message:500")]),
                )
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
                    trace.assistant_response = (
                        hermes_v2._stock_participant_response("<|eos|>")
                    )
                    trace.processing_outcome = processing_outcome
                    await plugin.complete_stock_turn(
                        adapter=FakeAdapter(),
                        event=event,
                        stock_handle=mock.AsyncMock(),
                    )

                asyncio.run(run())
                records = plugin._rooms[
                    ("discord", "42")
                ].receipts.all_records()
                self.assertEqual(
                    [
                        "observation",
                        "attention",
                        "participant-host",
                        "transport",
                    ],
                    [record["stage"] for record in records],
                )
                self.assertEqual("unknown", records[-2]["body"]["outcome"])
                self.assertEqual("failed", records[-1]["body"]["delivery"])

    def test_runner_shim_blocks_direct_handoff_without_matching_trace(self):
        calls: list[str] = []

        class Runner:
            async def _handle_message(self, event):
                calls.append(event.text)
                return "participant output"

        modules = {
            "gateway": types.ModuleType("gateway"),
            "gateway.run": types.ModuleType("gateway.run"),
        }
        modules["gateway.run"].GatewayRunner = Runner
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), FakeLlm([]))
            with mock.patch.dict(sys.modules, modules):
                hermes_v2._install_runner_result_shim(plugin)
            handoff = FakeEvent(text="Continue this handed-off task")
            handoff.internal = True
            unconfigured = FakeEvent(
                text="stock route",
                source=FakeSource(chat_id="77"),
            )

            async def run() -> None:
                with self.assertRaises(hermes_v2._StockEffectBlocked):
                    await Runner()._handle_message(handoff)
                self.assertEqual(
                    "participant output",
                    await Runner()._handle_message(unconfigured),
                )

            asyncio.run(run())
            self.assertEqual(["stock route"], calls)
            runtime = plugin._rooms[("discord", "42")]
            self.assertIn(
                "no matching active Nunchi opportunity",
                runtime._last_operational_error["detail"],
            )
            self.assertEqual(
                "continuity-gap",
                runtime.observation.delivery_audits()[-1].outcome,
            )

    def test_runner_shim_allows_only_ingress_authorized_lifecycle_control(self):
        class GatewayRunner:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def _is_user_authorized(self, source):
                del source
                return True

            async def _handle_message(self, event):
                self.calls.append(event.text)
                return "stopped"

        class BasePlatformAdapter:
            def __init__(self) -> None:
                self.gateway_runner = GatewayRunner()

            async def handle_message(self, event):
                return await self.gateway_runner._handle_message(event)

        modules = {
            "gateway": types.ModuleType("gateway"),
            "gateway.platforms": types.ModuleType("gateway.platforms"),
            "gateway.platforms.base": types.ModuleType("gateway.platforms.base"),
            "gateway.run": types.ModuleType("gateway.run"),
        }
        modules["gateway.platforms.base"].BasePlatformAdapter = BasePlatformAdapter
        modules["gateway.run"].GatewayRunner = GatewayRunner
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), FakeLlm([]))
            with mock.patch.dict(sys.modules, modules):
                hermes_v2._install_claimed_ingress_shim(plugin)
                hermes_v2._install_runner_result_shim(plugin)
            adapter = BasePlatformAdapter()
            stop = FakeEvent(text="/stop")

            async def run() -> None:
                self.assertEqual("stopped", await adapter.handle_message(stop))
                with self.assertRaises(hermes_v2._StockEffectBlocked):
                    await adapter.gateway_runner._handle_message(stop)

            asyncio.run(run())
            self.assertEqual(["/stop"], adapter.gateway_runner.calls)

    def test_restart_replay_shim_blocks_only_configured_delivery_obligations(self):
        class SessionEntry:
            __annotations__ = {
                "session_key": str,
                "origin": object,
                "resume_pending": bool,
            }

        class SessionStore:
            _profile_from_session_key = staticmethod(
                fake_profile_from_session_key
            )

            def _ensure_loaded_locked(self):
                return None

            def clear_resume_pending(self, session_key):
                del session_key
                return False

        class Runner:
            def _schedule_resume_pending_sessions(self, platform=None):
                del platform
                return 0

        rows = [
            {
                "obligation_id": "configured",
                "session_key": "agent:main:discord:group:42",
                "platform": "discord",
                "chat_id": "42",
                "thread_id": None,
                "content": "stale configured reply",
            },
            {
                "obligation_id": "stock",
                "session_key": "agent:main:discord:group:84",
                "platform": "discord",
                "chat_id": "84",
                "thread_id": None,
                "content": "stock reply",
            },
            {
                "obligation_id": "other-profile",
                "session_key": "agent:other:discord:group:42",
                "platform": "discord",
                "chat_id": "42",
                "thread_id": None,
                "content": "other profile reply",
            },
        ]
        transitions: list[tuple[str, str, str]] = []
        delivery_ledger = types.ModuleType("gateway.delivery_ledger")
        delivery_ledger.ledger_enabled = lambda config=None: True

        def sweep_recoverable(now=None, *, deliverable_platforms=None):
            del now, deliverable_platforms
            return [dict(row) for row in rows]

        def update_state(obligation_id, state, error=""):
            transitions.append((obligation_id, state, error))

        delivery_ledger.sweep_recoverable = sweep_recoverable
        delivery_ledger._update_state = update_state
        gateway = types.ModuleType("gateway")
        config_module = types.ModuleType("gateway.config")
        run_module = types.ModuleType("gateway.run")
        session_module = types.ModuleType("gateway.session")
        config_module.load_gateway_config = lambda: types.SimpleNamespace(
            multiplex_profiles=False
        )
        run_module.GatewayRunner = Runner
        session_module.SessionEntry = SessionEntry
        session_module.SessionStore = SessionStore
        gateway.delivery_ledger = delivery_ledger
        gateway.config = config_module
        modules = {
            "gateway": gateway,
            "gateway.config": config_module,
            "gateway.delivery_ledger": delivery_ledger,
            "gateway.run": run_module,
            "gateway.session": session_module,
        }

        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm([]),
                hermes_profile="fiction-writer",
            )
            with mock.patch.dict(sys.modules, modules):
                hermes_v2._install_restart_replay_shim(plugin)
                self.assertTrue(delivery_ledger.ledger_enabled())

                configured_ledger_values: list[bool] = []

                async def stock_handle(adapter, event):
                    del adapter, event
                    configured_ledger_values.append(
                        delivery_ledger.ledger_enabled()
                    )

                asyncio.run(
                    plugin.gate_ingress(
                        adapter=types.SimpleNamespace(),
                        event=FakeEvent(
                            source=FakeSource(profile="fiction-writer")
                        ),
                        stock_handle=stock_handle,
                    )
                )
                recoverable = delivery_ledger.sweep_recoverable(
                    None,
                    deliverable_platforms={"discord"},
                )

        self.assertEqual([False], configured_ledger_values)
        self.assertEqual(
            ["stock", "other-profile"],
            [row["obligation_id"] for row in recoverable],
        )
        self.assertEqual(
            [
                (
                    "configured",
                    "abandoned",
                    "Nunchi routes do not replay output after restart",
                )
            ],
            transitions,
        )

    def test_restart_replay_shim_clears_only_configured_auto_resume(self):
        class SessionEntry:
            __annotations__ = {
                "session_key": str,
                "origin": object,
                "resume_pending": bool,
            }

            def __init__(self, session_key, origin):
                self.session_key = session_key
                self.origin = origin
                self.resume_pending = True
                self.resume_reason = "restart_timeout"

        class SessionStore:
            _profile_from_session_key = staticmethod(
                fake_profile_from_session_key
            )

            def __init__(self, entries):
                self._entries = {
                    entry.session_key: entry
                    for entry in entries
                }
                self._lock = threading.Lock()
                self.config = types.SimpleNamespace(multiplex_profiles=False)
                self.cleared: list[str] = []

            def _ensure_loaded_locked(self):
                return None

            def clear_resume_pending(self, session_key):
                entry = self._entries.get(session_key)
                if entry is None or not entry.resume_pending:
                    return False
                entry.resume_pending = False
                entry.resume_reason = None
                self.cleared.append(session_key)
                return True

        class Runner:
            def __init__(self, entries):
                self.session_store = SessionStore(entries)
                self.scheduled: list[str] = []

            def _schedule_resume_pending_sessions(self, platform=None):
                del platform
                self.scheduled = [
                    entry.session_key
                    for entry in self.session_store._entries.values()
                    if entry.resume_pending
                ]
                return len(self.scheduled)

        delivery_ledger = types.ModuleType("gateway.delivery_ledger")
        delivery_ledger.ledger_enabled = lambda config=None: True
        delivery_ledger.sweep_recoverable = (
            lambda now=None, *, deliverable_platforms=None: []
        )
        delivery_ledger._update_state = (
            lambda obligation_id, state, error="": None
        )
        gateway = types.ModuleType("gateway")
        config_module = types.ModuleType("gateway.config")
        run_module = types.ModuleType("gateway.run")
        session_module = types.ModuleType("gateway.session")
        config_module.load_gateway_config = lambda: types.SimpleNamespace(
            multiplex_profiles=False
        )
        run_module.GatewayRunner = Runner
        session_module.SessionEntry = SessionEntry
        session_module.SessionStore = SessionStore
        gateway.delivery_ledger = delivery_ledger
        gateway.config = config_module
        modules = {
            "gateway": gateway,
            "gateway.config": config_module,
            "gateway.delivery_ledger": delivery_ledger,
            "gateway.run": run_module,
            "gateway.session": session_module,
        }

        configured = SessionEntry(
            "agent:main:discord:group:42",
            FakeSource(chat_id="42", profile="fiction-writer"),
        )
        stock = SessionEntry(
            "agent:main:discord:group:84",
            FakeSource(chat_id="84", profile="fiction-writer"),
        )
        other_profile = SessionEntry(
            "agent:other:discord:group:42",
            FakeSource(chat_id="42", profile="other"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(
                Path(temporary),
                FakeLlm([]),
                hermes_profile="fiction-writer",
            )
            with mock.patch.dict(sys.modules, modules):
                hermes_v2._install_restart_replay_shim(plugin)
                runner = Runner([configured, stock, other_profile])
                scheduled = runner._schedule_resume_pending_sessions()

        self.assertEqual(2, scheduled)
        self.assertEqual(
            ["agent:main:discord:group:42"],
            runner.session_store.cleared,
        )
        self.assertFalse(configured.resume_pending)
        self.assertTrue(stock.resume_pending)
        self.assertTrue(other_profile.resume_pending)
        self.assertEqual(
            [
                "agent:main:discord:group:84",
                "agent:other:discord:group:42",
            ],
            runner.scheduled,
        )

    def test_restart_replay_shim_fails_closed_on_unknown_ledger_row(self):
        class SessionEntry:
            __annotations__ = {
                "session_key": str,
                "origin": object,
                "resume_pending": bool,
            }

        class SessionStore:
            _profile_from_session_key = staticmethod(
                fake_profile_from_session_key
            )

            def _ensure_loaded_locked(self):
                return None

            def clear_resume_pending(self, session_key):
                del session_key
                return False

        class Runner:
            def _schedule_resume_pending_sessions(self, platform=None):
                del platform
                return 0

        delivery_ledger = types.ModuleType("gateway.delivery_ledger")
        delivery_ledger.ledger_enabled = lambda config=None: True
        delivery_ledger.sweep_recoverable = (
            lambda now=None, *, deliverable_platforms=None: [
                {
                    "obligation_id": "unknown",
                    "platform": "discord",
                    "chat_id": "42",
                }
            ]
        )
        delivery_ledger._update_state = (
            lambda obligation_id, state, error="": None
        )
        gateway = types.ModuleType("gateway")
        config_module = types.ModuleType("gateway.config")
        run_module = types.ModuleType("gateway.run")
        session_module = types.ModuleType("gateway.session")
        config_module.load_gateway_config = lambda: types.SimpleNamespace(
            multiplex_profiles=False
        )
        run_module.GatewayRunner = Runner
        session_module.SessionEntry = SessionEntry
        session_module.SessionStore = SessionStore
        gateway.delivery_ledger = delivery_ledger
        gateway.config = config_module
        modules = {
            "gateway": gateway,
            "gateway.config": config_module,
            "gateway.delivery_ledger": delivery_ledger,
            "gateway.run": run_module,
            "gateway.session": session_module,
        }

        with tempfile.TemporaryDirectory() as temporary:
            plugin, _ = self.plugin(Path(temporary), FakeLlm([]))
            with mock.patch.dict(sys.modules, modules):
                hermes_v2._install_restart_replay_shim(plugin)
                with self.assertRaisesRegex(
                    Exception,
                    "Stock Hermes can continue without Nunchi",
                ):
                    delivery_ledger.sweep_recoverable(
                        None,
                        deliverable_platforms={"discord"},
                    )

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
                mock.patch.object(
                    hermes_v2,
                    "_install_discord_thread_guard",
                ) as discord_thread_guard,
                mock.patch.object(
                    hermes_v2,
                    "_install_discord_slash_guard",
                ) as discord_slash_guard,
                mock.patch.object(
                    hermes_v2,
                    "_install_restart_replay_shim",
                ) as restart_replay_shim,
                mock.patch.object(
                    hermes_v2,
                    "_install_execution_boundary_shim",
                ) as execution_boundary_shim,
                mock.patch.object(
                    hermes_v2,
                    "_install_auto_title_shim",
                ) as auto_title_shim,
                mock.patch.object(
                    hermes_v2,
                    "_install_stock_silence_filter_shim",
                ) as silence_filter_shim,
                mock.patch.object(
                    hermes_v2,
                    "_install_stock_streaming_tts_guard",
                ) as streaming_tts_guard,
                mock.patch.object(
                    hermes_v2,
                    "_install_handoff_route_guard",
                ) as handoff_route_guard,
                mock.patch.object(
                    hermes_v2,
                    "_install_voice_transcript_guard",
                ) as voice_transcript_guard,
            ):
                plugin = hermes_v2.register(
                    ctx,
                    config_loader=lambda _: config,
                    dashboard_installer=lambda: None,
                )
            restart_replay_shim.assert_called_once_with(plugin)
            execution_boundary_shim.assert_called_once_with(plugin)
            auto_title_shim.assert_called_once_with(plugin)
            silence_filter_shim.assert_called_once_with(plugin)
            streaming_tts_guard.assert_called_once_with(plugin)
            discord_thread_guard.assert_called_once_with(plugin)
            discord_slash_guard.assert_called_once_with(plugin)
            handoff_route_guard.assert_called_once_with(plugin)
            voice_transcript_guard.assert_called_once_with(plugin)
            self.assertEqual("process-local-gate", plugin.mode)
            self.assertEqual(
                {"pre_tool_call", "pre_llm_call", "post_llm_call"},
                set(ctx.hooks),
            )
            self.assertIn("nunchi", ctx.commands)
            self.assertEqual(
                "stock-hermes-with-nunchi-guards",
                plugin.probe()["participant_execution"],
            )
            self.assertFalse(plugin.probe()["complete_v2_lifecycle"])
            self.assertEqual(
                "blocked-configured-routes",
                plugin.probe()["tool_execution"],
            )

    def test_register_installs_dashboard_and_stays_dormant_before_setup(self):
        with tempfile.TemporaryDirectory() as temporary:
            installed: list[bool] = []
            ctx = FakeCtx(FakeLlm([]))
            ctx.profile_name = "fiction-writer"
            with (
                mock.patch.dict(
                    os.environ,
                    {"HERMES_HOME": temporary},
                    clear=True,
                ),
                mock.patch.object(
                    hermes_v2,
                    "_hermes_version",
                    return_value="0.19.0",
                ),
            ):
                result = hermes_v2.register(
                    ctx,
                    dashboard_installer=lambda: installed.append(True),
                )

            self.assertEqual([True], installed)
            self.assertIsNone(result)
            self.assertEqual({}, ctx.hooks)
            self.assertIn("nunchi", ctx.commands)
            status = json.loads(ctx.commands["nunchi"]("probe"))
            self.assertFalse(status["active"])
            self.assertTrue(status["setup_required"])
            self.assertTrue(status["stock_hermes_available"])

    def test_register_preserves_dashboard_repair_guidance(self):
        from nunchi.integrations import hermes_dashboard_install

        ctx = FakeCtx(FakeLlm([]))
        ctx.profile_name = "fiction-writer"
        detail = (
            "Hermes did not persist Nunchi in the machine dashboard profile. "
            "Have the Hermes administrator add `nunchi` to plugins.enabled, "
            "or run the dashboard with --isolated for this profile."
        )
        with (
            mock.patch.object(
                hermes_v2,
                "_hermes_version",
                return_value="0.19.0",
            ),
            mock.patch.object(
                hermes_dashboard_install,
                "install_dashboard_for_profile",
                side_effect=hermes_dashboard_install.DashboardInstallError(
                    detail
                ),
            ),
        ):
            with self.assertRaisesRegex(
                ValidationError,
                "administrator.*--isolated",
            ) as raised:
                hermes_v2.register(ctx)

        self.assertNotIn(
            "nunchi-hermes-dashboard install",
            str(raised.exception),
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

    def test_unverified_future_release_fails_with_supported_alternatives(self):
        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(Path(temporary), llm=FakeLlm([]))
            with mock.patch.object(
                hermes_v2,
                "_hermes_version",
                return_value="0.20.0",
            ):
                with self.assertRaisesRegex(
                    Exception,
                    "update Nunchi.*or use Hermes 0.19.0",
                ):
                    hermes_v2.register(
                        ctx,
                        config_loader=lambda _: config,
                        dashboard_installer=lambda: None,
                    )

    def test_register_rolls_back_process_patches_when_a_shape_fails(self):
        class Target:
            value = "stock"

        def install_first(plugin):
            del plugin
            hermes_v2._set_shim_attribute(Target, "value", "patched")
            hermes_v2._SHIM_OWNER = object()
            hermes_v2._ORIGINAL_BASE_HANDLE = lambda adapter, event: None

        def fail_later(plugin):
            del plugin
            raise hermes_v2.ValidationError("incompatible restart shape")

        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(Path(temporary), llm=FakeLlm([]))
            with (
                mock.patch.object(
                    hermes_v2,
                    "_hermes_version",
                    return_value="0.19.0",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_discord_room_admission_shim",
                    side_effect=install_first,
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_discord_thread_guard",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_discord_slash_guard",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_telegram_batch_identity_shim",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_claimed_ingress_shim",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_stock_lifecycle_shim",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_execution_boundary_shim",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_auto_title_shim",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_stock_silence_filter_shim",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_stock_streaming_tts_guard",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_runner_result_shim",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_handoff_route_guard",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_voice_transcript_guard",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_restart_replay_shim",
                    side_effect=fail_later,
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_gateway_shutdown_shim",
                ),
            ):
                with self.assertRaisesRegex(
                    Exception,
                    "incompatible restart shape",
                ):
                    hermes_v2.register(
                        ctx,
                        config_loader=lambda _: config,
                        dashboard_installer=lambda: None,
                    )
            self.assertEqual("stock", Target.value)
            self.assertIsNone(hermes_v2._SHIM_OWNER)
            self.assertIsNone(hermes_v2._ORIGINAL_BASE_HANDLE)
            self.assertEqual({}, ctx.hooks)
            self.assertEqual({}, ctx.commands)

    def test_register_rolls_back_patches_and_registries_on_hook_failure(self):
        class Target:
            value = "stock"

        def install_first(plugin):
            del plugin
            hermes_v2._set_shim_attribute(Target, "value", "patched")
            hermes_v2._SHIM_OWNER = object()

        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(Path(temporary), llm=FakeLlm([]))
            original_register_hook = ctx.register_hook

            def fail_after_registration(name, callback):
                original_register_hook(name, callback)
                raise RuntimeError("hook registry failed")

            ctx.register_hook = fail_after_registration
            with (
                mock.patch.object(
                    hermes_v2,
                    "_hermes_version",
                    return_value="0.19.0",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_discord_room_admission_shim",
                    side_effect=install_first,
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_discord_thread_guard",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_discord_slash_guard",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_telegram_batch_identity_shim",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_claimed_ingress_shim",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_stock_lifecycle_shim",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_execution_boundary_shim",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_auto_title_shim",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_stock_silence_filter_shim",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_stock_streaming_tts_guard",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_runner_result_shim",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_handoff_route_guard",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_voice_transcript_guard",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_restart_replay_shim",
                ),
                mock.patch.object(
                    hermes_v2,
                    "_install_gateway_shutdown_shim",
                ),
            ):
                with self.assertRaisesRegex(Exception, "hook registry failed"):
                    hermes_v2.register(
                        ctx,
                        config_loader=lambda _: config,
                        dashboard_installer=lambda: None,
                    )
            self.assertEqual("stock", Target.value)
            self.assertIsNone(hermes_v2._SHIM_OWNER)
            self.assertEqual({}, ctx.hooks)
            self.assertEqual({}, ctx.commands)

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
                            "actor_id": "discord:actor:999",
                            "platform": "discord",
                            "room_id": "42",
                            "continuity_scope_id": "room-42",
                            "provenance": "test",
                        },
                        "profile": {
                            "document": {
                                "profile_id": "profile",
                                "participant_id": "participant",
                                "actor_id": "discord:actor:999",
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
            self.assertEqual("discord", loaded.rooms[0].binding.platform)
            path.write_text("{}")
            with self.assertRaisesRegex(Exception, "pinned digest"):
                hermes_v2.load_pinned_config(
                    path,
                    expected_sha256=digest,
                    hermes_profile="default",
                )

    def test_config_rejects_unsupported_hermes_platform(self):
        room = {
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
            "participant": {"timeout_seconds": 2, "max_expansions": 1},
        }
        with self.assertRaisesRegex(
            Exception,
            "Stock Hermes can continue on the unsupported platform",
        ):
            hermes_v2._load_room(room, index=0)

    def test_package_has_entry_point_without_hermes_dependency(self):
        pyproject = (
            Path(__file__).resolve().parents[2] / "pyproject.toml"
        ).read_text()
        self.assertIn('nunchi = "nunchi.integrations.hermes_v2"', pyproject)
        dependencies = pyproject.split("dependencies = [", 1)[1].split("]", 1)[0]
        self.assertNotIn("hermes-agent", dependencies)


if __name__ == "__main__":
    unittest.main()
