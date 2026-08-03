"""Source-level proof for the Claude Code plugin-owned session seam (#43)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest

from nunchi.errors import ValidationError
from nunchi.integrations.claude_code_session import (
    FATAL,
    REBIND,
    SUPPORTED_CHANNEL_PLUGINS,
    UPDATE,
    WARN,
    ChannelEnvelopeError,
    SessionBindingError,
    SessionIdentity,
    SessionIdentityStore,
    channel_plugin_conformance,
    drift_report,
    parse_channel_envelope,
)


def _envelope_prompt(
    *,
    source: str = "discord",
    chat_id: str = "152",
    message_id: str = "900",
    user: str = "zoe",
    user_id: str = "42",
    ts: str = "2026-08-03T00:00:00.000Z",
    body: str = "does the gate hold?",
) -> str:
    return (
        f'<channel source="{source}" chat_id="{chat_id}" '
        f'message_id="{message_id}" user="{user}" user_id="{user_id}" '
        f'ts="{ts}">{body}</channel>'
    )


class ChannelEnvelopeTests(unittest.TestCase):
    def test_parses_the_real_channel_shape(self) -> None:
        envelope = parse_channel_envelope(_envelope_prompt())
        assert envelope is not None
        self.assertEqual(envelope.source, "discord")
        self.assertEqual(envelope.chat_id, "152")
        self.assertEqual(envelope.message_id, "900")
        self.assertEqual(envelope.user, "zoe")
        self.assertEqual(envelope.user_id, "42")
        self.assertEqual(envelope.body, "does the gate hold?")
        self.assertEqual(envelope.delivery_id, "discord:channel:152:900")

    def test_operator_prompt_is_not_an_envelope(self) -> None:
        self.assertIsNone(parse_channel_envelope("please run the tests"))
        self.assertIsNone(parse_channel_envelope(""))
        self.assertIsNone(parse_channel_envelope(None))

    def test_a_visible_opener_that_does_not_parse_is_fail_closed(self) -> None:
        # A truncated delivery must never be mistaken for operator text: that
        # would put an ungated room event in front of the model.
        for prompt in (
            '<channel source="discord" chat_id="152"',
            "<channel >",
            '<channel source="discord" chat_id="152" message_id="900">no close',
        ):
            with self.subTest(prompt=prompt):
                with self.assertRaises(ChannelEnvelopeError):
                    parse_channel_envelope(prompt)

    def test_repeated_attribute_is_ambiguity_not_data(self) -> None:
        prompt = (
            '<channel source="discord" chat_id="152" chat_id="999" '
            'message_id="900">hi</channel>'
        )
        with self.assertRaises(ChannelEnvelopeError):
            parse_channel_envelope(prompt)

    def test_missing_routing_attributes_are_refused(self) -> None:
        prompt = '<channel source="discord" user="zoe">hi</channel>'
        with self.assertRaises(ChannelEnvelopeError):
            parse_channel_envelope(prompt)

    def test_body_keeps_a_literal_closing_tag(self) -> None:
        # The attention stage has to judge exactly what the participant will
        # see; truncating at an inner literal would hide room content.
        body = "look at </channel> inside the text"
        envelope = parse_channel_envelope(_envelope_prompt(body=body))
        assert envelope is not None
        self.assertEqual(envelope.body, body)

    def test_attribute_boundaries_do_not_bind_lookalikes(self) -> None:
        prompt = (
            '<channel source="discord" not-chat_id="666" chat_id="152" '
            'message_id="900">hi</channel>'
        )
        envelope = parse_channel_envelope(prompt)
        assert envelope is not None
        self.assertEqual(envelope.chat_id, "152")

    def test_entities_in_attributes_are_unescaped(self) -> None:
        envelope = parse_channel_envelope(_envelope_prompt(user="a&amp;b"))
        assert envelope is not None
        self.assertEqual(envelope.user, "a&b")

    def test_channel_envelope_error_is_a_validation_error(self) -> None:
        self.assertTrue(issubclass(ChannelEnvelopeError, ValidationError))


class ChannelPluginConformanceTests(unittest.TestCase):
    def test_unverified_build_is_refused_not_assumed(self) -> None:
        with self.assertRaises(SessionBindingError):
            channel_plugin_conformance("discord", "0.0.5")
        with self.assertRaises(SessionBindingError):
            channel_plugin_conformance("telegram", "0.0.4")

    def test_official_discord_build_is_recorded_with_its_shortfalls(self) -> None:
        # Pinned findings against claude-plugins-official discord 0.0.4:
        # handleInbound calls sendTyping() (server.ts:950-951) and the
        # configured ack reaction (:956-957) before emitting
        # notifications/claude/channel (:988). Separately, the messageCreate
        # listener returns early for every bot-authored message (:908), before
        # handleInbound is reached. A gate in front of the session cannot undo
        # either, so neither may be silently assumed away.
        record = channel_plugin_conformance("discord", "0.0.4")
        self.assertEqual(record.key, ("discord", "0.0.4"))
        self.assertTrue(record.emits_before_gate)
        self.assertFalse(record.delivers_peer_agents)
        self.assertFalse(record.silence_complete)
        self.assertFalse(record.lifecycle_complete)
        shortfalls = record.shortfalls()
        self.assertEqual(len(shortfalls), 2)
        self.assertTrue(any("before Nunchi observes" in note for note in shortfalls))
        self.assertTrue(any("other agents" in note for note in shortfalls))
        # The pinned detail is a measured statement, so it must locate each
        # finding where a reviewer will actually find it.
        self.assertIn("950-951", record.detail)
        self.assertIn("messageCreate", record.detail)
        self.assertIn(":908", record.detail)

    def test_every_pinned_record_is_self_consistent(self) -> None:
        for key, record in SUPPORTED_CHANNEL_PLUGINS.items():
            with self.subTest(plugin=key):
                self.assertEqual(key, record.key)
                self.assertTrue(record.detail)
                self.assertEqual(
                    record.lifecycle_complete,
                    record.silence_complete and record.delivers_peer_agents,
                )
                self.assertEqual(bool(record.shortfalls()), not record.lifecycle_complete)


def _identity(**overrides: str) -> SessionIdentity:
    base = {
        "participant_id": "vigil",
        "actor_id": "discord:user:149",
        "platform": "discord",
        "room_id": "152",
        "continuity_scope_id": "discord:channel:152",
        "profile_sha256": "a" * 64,
        "config_sha256": "b" * 64,
        "channel_source": "discord",
        "claude_session_id": "11111111-1111-1111-1111-111111111111",
        "cwd": "/srv/room",
        "claude_version": "2.1.216",
        "claude_executable_path": "/usr/local/bin/claude",
        "channel_plugin": "discord",
        "channel_plugin_version": "0.0.4",
        "settings_sha256": "c" * 64,
        "account_identity": "zoe@example.test",
        "model": "claude-opus-5",
        "effort": "high",
        "permission_mode": "manual",
        "claude_entrypoint": "cli",
    }
    base.update(overrides)
    return SessionIdentity(**base)


class SessionIdentityTests(unittest.TestCase):
    def test_digest_covers_every_bound_fact(self) -> None:
        committed = _identity()
        for name in committed.document():
            with self.subTest(field=name):
                changed = _identity(**{name: "changed-value"})
                self.assertNotEqual(committed.sha256, changed.sha256)

    def test_digest_is_stable_for_identical_facts(self) -> None:
        self.assertEqual(_identity().sha256, _identity().sha256)

    def test_fatal_fields_name_a_different_participant_or_room(self) -> None:
        committed = _identity()
        for name in (
            "participant_id",
            "actor_id",
            "platform",
            "room_id",
            "continuity_scope_id",
            "profile_sha256",
            "config_sha256",
            "channel_source",
        ):
            with self.subTest(field=name):
                drift = committed.drift(_identity(**{name: "other"}))
                self.assertEqual(drift, {name: FATAL})
                self.assertEqual(SessionIdentity.severity(drift), FATAL)

    def test_rebind_update_and_warn_fields_are_classified(self) -> None:
        committed = _identity()
        expected = {
            "claude_session_id": REBIND,
            "cwd": REBIND,
            "claude_version": UPDATE,
            "claude_executable_path": UPDATE,
            "channel_plugin": UPDATE,
            "channel_plugin_version": UPDATE,
            "settings_sha256": UPDATE,
            "account_identity": WARN,
            "model": WARN,
            "effort": WARN,
            "permission_mode": WARN,
            "claude_entrypoint": WARN,
        }
        for name, klass in expected.items():
            with self.subTest(field=name):
                drift = committed.drift(_identity(**{name: "other"}))
                self.assertEqual(drift, {name: klass})
                self.assertEqual(SessionIdentity.severity(drift), klass)

    def test_no_drift_reports_nothing(self) -> None:
        self.assertEqual(_identity().drift(_identity()), {})
        self.assertIsNone(SessionIdentity.severity({}))

    def test_unobserved_optional_fact_is_not_drift(self) -> None:
        # A runtime that does not expose the account, model, or entrypoint must
        # not read as "the runtime changed"; only a present, different fact is.
        committed = _identity()
        observed = _identity(account_identity="", model="", claude_entrypoint="")
        self.assertEqual(committed.drift(observed), {})

    def test_severity_picks_the_most_severe_class(self) -> None:
        committed = _identity()
        observed = _identity(
            model="other", claude_version="2.9.9", claude_session_id="other"
        )
        drift = committed.drift(observed)
        self.assertEqual(SessionIdentity.severity(drift), REBIND)
        self.assertEqual(
            SessionIdentity.severity({**drift, "room_id": FATAL}), FATAL
        )


class DriftReportTests(unittest.TestCase):
    def test_non_fatal_report_offers_recovery_commands_that_exist(self) -> None:
        from nunchi.integrations.claude_code_session import ACCEPT_VERBS

        committed = _identity()
        observed = _identity(claude_version="2.1.219")
        report = drift_report(committed, observed, committed.drift(observed))
        self.assertIn("2.1.216", report)
        self.assertIn("2.1.219", report)
        self.assertIn("claude_version", report)
        self.assertIn("will not answer it", report)
        # Every command the menu prints has to be one the operator can
        # actually run: printing four words is not offering four paths.
        for verb in ACCEPT_VERBS:
            with self.subTest(verb=verb):
                self.assertIn(f"--accept {verb}", report)
        self.assertIn("--mode restricted-headless", report)

    def test_every_offered_accept_verb_is_accepted_by_the_parser(self) -> None:
        import contextlib
        import io

        from nunchi.integrations.claude_code_session import ACCEPT_VERBS, main

        for verb in ACCEPT_VERBS:
            with self.subTest(verb=verb):
                buffer = io.StringIO()
                with contextlib.redirect_stderr(buffer):
                    code = main(["--accept", verb])
                # It fails on the missing --config, never on the verb itself.
                self.assertNotEqual(code, 0)
                self.assertNotIn("unrecognized", buffer.getvalue())
                self.assertNotIn("invalid choice", buffer.getvalue())

    def test_fatal_report_refuses_and_offers_no_recovery_verb(self) -> None:
        committed = _identity()
        observed = _identity(room_id="999")
        report = drift_report(committed, observed, committed.drift(observed))
        self.assertIn("different participant or a different room", report)
        for verb in ("rebind", "update", "reset", "fallback"):
            self.assertNotIn(f"session-gate {verb}", report)


class SessionIdentityStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "session.json"
        self.store = SessionIdentityStore(self.path)

    def test_absent_state_loads_as_unbound(self) -> None:
        self.assertIsNone(self.store.load())

    def test_write_then_load_round_trips_exactly(self) -> None:
        identity = _identity()
        self.store.write(identity)
        self.assertEqual(self.store.load(), identity)

    def test_staged_identity_is_not_durable_until_committed(self) -> None:
        # A turn the host never accepts must leave no resumable state.
        self.store.stage(_identity())
        self.assertIsNone(self.store.load())
        self.store.discard()
        self.assertIsNone(self.store.commit())
        self.assertIsNone(self.store.load())

    def test_commit_persists_exactly_the_staged_identity(self) -> None:
        identity = _identity()
        self.store.stage(identity)
        self.assertEqual(self.store.commit(), identity)
        self.assertEqual(self.store.load(), identity)
        # A second commit has nothing staged and must not rewrite state.
        self.assertIsNone(self.store.commit())

    def test_state_file_is_owner_only(self) -> None:
        self.store.write(_identity())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_tampered_digest_is_refused(self) -> None:
        self.store.write(_identity())
        document = json.loads(self.path.read_text(encoding="utf-8"))
        document["identity"]["room_id"] = "999"
        self.path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaises(SessionBindingError):
            self.store.load()

    def test_foreign_shape_is_refused(self) -> None:
        for payload in (
            "{}",
            '{"schema_version": 2, "identity": {}, "identity_sha256": ""}',
            '{"schema_version": 3, "identity": {"room_id": "1"}, "identity_sha256": ""}',
            "not json",
        ):
            with self.subTest(payload=payload):
                self.path.write_text(payload, encoding="utf-8")
                with self.assertRaises(SessionBindingError):
                    self.store.load()


class FixtureModel:
    """A delegated attention model with a scripted disposition."""

    name = "fixture-session-attention"
    provider = "fixture"
    model_id = "fixture-v2"

    def __init__(self, disposition: str = "WAKE") -> None:
        self.disposition = disposition
        self.calls: list[dict] = []

    def judge(self, *, instructions, projection, timeout_seconds):
        del instructions, timeout_seconds
        self.calls.append(projection)
        return {
            "disposition": self.disposition,
            "reasons": ["fixture judgment"],
            "evidence_event_ids": [projection["trigger_event_id"]],
            "legacy_verdict_confidences": (
                {"PASS": 0.55, "ACK": 0.2, "ASK": 0.15, "SPEAK": 0.1}
                if self.disposition == "SUPPRESS"
                else {"PASS": 0.02, "ACK": 0.03, "ASK": 0.05, "SPEAK": 0.9}
            ),
        }


class GateHarness:
    """One gate wired to the real shared core, driven by hook events.

    Nothing about the shared core is faked: observation, attention, the
    scheduler, the participant host, and the receipt journal are the real
    classes, constructed exactly as a platform integration must construct
    them. Only the attention model's judgment and the session's own actions
    are scripted, because those are what a test has to control.
    """

    PROFILE = {
        "profile_id": "vigil-default",
        "participant_id": "vigil",
        "actor_id": "discord:user:149",
        "instructions": "Contribute when you can move the room forward.",
        "provenance": "trusted:test/vigil@1",
    }

    def __init__(self, root: Path, *, disposition: str = "WAKE") -> None:
        from nunchi.ack import AckJournal, AckPolicy
        from nunchi.attention import AttentionEngine, AttentionPolicy, ParticipantProfile
        from nunchi.observation import ObservationLimits, ObservationProvider, ParticipantBinding
        from nunchi.participant import ConversationOpportunityScheduler, ParticipantTurnHost
        from nunchi.receipts import ReceiptJournal
        from nunchi.integrations.claude_code_session import (
            ClaudeCodeSessionRuntime,
            EnvelopeFactResolver,
            NativeSessionParticipant,
            NativeSessionTransport,
            SessionIdentityStore,
            _TraceRegistry,
        )

        root.mkdir(parents=True, exist_ok=True)
        profile_path = root / "profile.json"
        payload = json.dumps(self.PROFILE).encode("utf-8")
        profile_path.write_bytes(payload)
        self.profile = ParticipantProfile.load(
            str(profile_path),
            expected_sha256=hashlib.sha256(payload).hexdigest(),
        )

        self.binding = ParticipantBinding(
            participant_id="vigil",
            actor_id="discord:user:149",
            platform="discord",
            room_id="152",
            continuity_scope_id="discord:channel:152",
        )
        self.model = FixtureModel(disposition)
        self.receipts = ReceiptJournal(root / "receipts.jsonl")
        self.observation = ObservationProvider(
            self.binding,
            limits=ObservationLimits(),
            receipts=self.receipts,
            persistence_path=root / "observations.jsonl",
            event_visibility={
                "message": "live-only",
                "reaction": "unavailable",
                "membership": "unavailable",
            },
        )
        self.scheduler = ConversationOpportunityScheduler("vigil:discord:channel:152")
        self.traces = _TraceRegistry()
        self.participant = NativeSessionParticipant(traces=self.traces)
        self.transport = NativeSessionTransport(
            traces=self.traces, acknowledgement_seconds=5.0
        )
        ack_policy = AckPolicy(enabled=False)
        self.host = ParticipantTurnHost(
            observation=self.observation,
            participant=self.participant,
            transport=self.transport,
            scheduler=self.scheduler,
            receipts=self.receipts,
            ack_policy=ack_policy,
            ack_journal=AckJournal(root / "acks.jsonl"),
            participant_timeout_seconds=10.0,
        )
        self.attention = AttentionEngine(
            profile=self.profile,
            model=self.model,
            policy=AttentionPolicy(),
            receipts=self.receipts,
            ack_policy=ack_policy,
            reaction_capability_provider=self.host.reaction_capability,
        )
        self.identity_store = SessionIdentityStore(root / "session.json")
        self.runtime = ClaudeCodeSessionRuntime(
            observation=self.observation,
            attention=self.attention,
            scheduler=self.scheduler,
            host=self.host,
            traces=self.traces,
            participant=self.participant,
            identity_store=self.identity_store,
            binding=self.binding,
            conformance=channel_plugin_conformance("discord", "0.0.4"),
            resolver=EnvelopeFactResolver(expected_source="discord", room_id="152"),
        )

    # -- hook drivers ------------------------------------------------------

    def submit(self, prompt: str, *, prompt_id: str = "p1", session: str = "s1"):
        return self.runtime.user_prompt_submit(
            {"prompt": prompt, "prompt_id": prompt_id, "session_id": session}
        )

    def deliver(self, *, message_id: str = "900", body: str = "hello", **kwargs):
        return self.submit(_envelope_prompt(message_id=message_id, body=body), **kwargs)

    def pre_tool(self, tool_name: str, tool_input: dict, *, prompt_id="p1", session="s1"):
        return self.runtime.pre_tool(
            {
                "tool_name": tool_name,
                "tool_input": tool_input,
                "prompt_id": prompt_id,
                "session_id": session,
            }
        )

    def post_tool(self, tool_name: str, response, *, prompt_id="p1", session="s1"):
        return self.runtime.post_tool(
            {
                "tool_name": tool_name,
                "tool_response": response,
                "prompt_id": prompt_id,
                "session_id": session,
            }
        )

    def stop(self, *, prompt_id="p1", session="s1"):
        return self.runtime.stop({"prompt_id": prompt_id, "session_id": session})

    # -- assertions --------------------------------------------------------

    def stages(self, request_id: str | None = None) -> list[str]:
        return [
            record["stage"]
            for record in self.receipts.all_records()
            if request_id is None or record["request_id"] == request_id
        ]

    def close(self) -> None:
        """Settle every parked turn so no worker outlives the test."""

        self.runtime.cancel("test teardown")
        self.runtime._join_workers(timeout=10.0)


class _GateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def harness(self, **kwargs) -> GateHarness:
        self._gates = getattr(self, "_gates", 0) + 1
        harness = GateHarness(self.root / f"gate-{self._gates}", **kwargs)
        self.addCleanup(harness.close)
        return harness


class SuppressTests(_GateTestCase):
    def test_suppress_blocks_before_any_model_request(self) -> None:
        harness = self.harness(disposition="SUPPRESS")
        decision = harness.deliver()
        self.assertEqual(decision.output["decision"], "block")
        self.assertEqual(decision.output["reason"], "")
        self.assertTrue(
            decision.output["hookSpecificOutput"]["suppressOriginalPrompt"]
        )

    def test_suppress_invokes_no_participant_and_dispatches_nothing(self) -> None:
        harness = self.harness(disposition="SUPPRESS")
        harness.deliver()
        self.assertEqual(harness.participant.invocation_count, 0)
        self.assertEqual(harness.transport.dispatch_count, 0)

    def test_suppress_writes_no_participant_host_receipt(self) -> None:
        # The judgment is recorded off-surface; what must not exist is any
        # record claiming the participant was given this turn.
        harness = self.harness(disposition="SUPPRESS")
        harness.deliver()
        stages = harness.stages()
        self.assertIn("observation", stages)
        self.assertIn("attention", stages)
        self.assertNotIn("participant-host", stages)
        self.assertNotIn("transport", stages)

    def test_suppressed_turn_denies_a_room_effect(self) -> None:
        # Layer two: even if something else reaches the send tool, there is no
        # admitted opportunity for it to belong to.
        harness = self.harness(disposition="SUPPRESS")
        harness.deliver()
        decision = harness.pre_tool(
            "mcp__plugin_discord_discord__reply", {"chat_id": "152", "text": "hi"}
        )
        self.assertEqual(
            decision.output["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        self.assertEqual(harness.transport.dispatch_count, 0)


class OperatorPromptTests(_GateTestCase):
    def test_operator_prompt_passes_through_ungated(self) -> None:
        harness = self.harness(disposition="SUPPRESS")
        decision = harness.submit("run the tests please")
        self.assertEqual(
            decision.output["hookSpecificOutput"]["additionalContext"], ""
        )
        self.assertNotIn("decision", decision.output)
        self.assertEqual(harness.model.calls, [])
        self.assertEqual(harness.stages(), [])

    def test_operator_turn_may_not_post_into_the_bound_room(self) -> None:
        harness = self.harness()
        harness.submit("run the tests please")
        decision = harness.pre_tool(
            "mcp__plugin_discord_discord__reply", {"chat_id": "152", "text": "hi"}
        )
        self.assertEqual(
            decision.output["hookSpecificOutput"]["permissionDecision"], "deny"
        )

    def test_non_room_tools_are_untouched(self) -> None:
        harness = self.harness()
        for tool in ("Bash", "Edit", "mcp__plugin_discord_discord__fetch_messages"):
            with self.subTest(tool=tool):
                self.assertIsNone(harness.pre_tool(tool, {}).output)


class WakeTests(_GateTestCase):
    def test_wake_admits_the_turn_and_appends_core_facts(self) -> None:
        harness = self.harness()
        decision = harness.deliver()
        self.assertNotIn("decision", decision.output)
        context = decision.output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("[nunchi-v2 participant wake] source=WAKE", context)
        self.assertIn("untrusted", context)
        self.assertIn("Silence is a valid outcome", context)

    def test_wake_context_carries_the_exact_core_packet(self) -> None:
        harness = self.harness()
        context = harness.deliver().output["hookSpecificOutput"]["additionalContext"]
        payload = json.loads(context[context.index("{") :])
        self.assertEqual(payload["attention"]["source"], "WAKE")
        self.assertEqual(payload["trigger_event_id"], "discord:message:900")
        self.assertEqual(payload["self"]["participant_id"], "vigil")
        self.assertEqual(payload["room"]["id"], "152")
        self.assertEqual(
            [event["id"] for event in payload["events"]], ["discord:message:900"]
        )

    def test_wake_does_not_rewrite_or_replace_the_prompt(self) -> None:
        # The session's own prompt, model, memory, tools and delivery path are
        # untouched: the only thing the gate adds is context.
        harness = self.harness()
        output = harness.deliver().output
        self.assertEqual(set(output), {"hookSpecificOutput"})
        self.assertEqual(
            set(output["hookSpecificOutput"]),
            {"hookEventName", "additionalContext"},
        )


class NativeDeliveryTests(_GateTestCase):
    def test_admitted_reply_is_released_and_attested(self) -> None:
        harness = self.harness()
        harness.deliver()
        released: dict = {}

        def send() -> None:
            released["decision"] = harness.pre_tool(
                "mcp__plugin_discord_discord__reply",
                {"chat_id": "152", "text": "on it"},
            )
            harness.post_tool(
                "mcp__plugin_discord_discord__reply",
                {"content": [{"type": "text", "text": "sent (id: 1234)"}]},
            )

        worker = threading.Thread(target=send)
        worker.start()
        worker.join(timeout=15)
        harness.stop()

        self.assertEqual(
            released["decision"].output["hookSpecificOutput"]["permissionDecision"],
            "allow",
        )
        self.assertEqual(harness.participant.invocation_count, 1)
        self.assertEqual(harness.transport.dispatch_count, 1)
        stages = harness.stages()
        self.assertIn("participant-host", stages)
        self.assertIn("transport", stages)

    def test_unattested_acknowledgement_is_unknown_never_synthetic_success(self) -> None:
        harness = self.harness()
        harness.deliver()

        def send() -> None:
            harness.pre_tool(
                "mcp__plugin_discord_discord__reply",
                {"chat_id": "152", "text": "on it"},
            )
            # An acknowledgement that names no native event: the send may or
            # may not have landed, which is exactly what `unknown` means.
            harness.post_tool(
                "mcp__plugin_discord_discord__reply",
                {"content": [{"type": "text", "text": "queued for delivery"}]},
            )

        worker = threading.Thread(target=send)
        worker.start()
        worker.join(timeout=15)
        harness.stop()

        transport = [
            record
            for record in harness.receipts.all_records()
            if record["stage"] == "transport"
        ]
        self.assertTrue(transport)
        self.assertEqual(transport[-1]["body"]["delivery"], "unknown")

    def test_second_room_action_in_one_turn_is_denied(self) -> None:
        harness = self.harness()
        harness.deliver()

        def send() -> None:
            harness.pre_tool(
                "mcp__plugin_discord_discord__reply",
                {"chat_id": "152", "text": "first"},
            )
            harness.post_tool(
                "mcp__plugin_discord_discord__reply",
                {"content": [{"type": "text", "text": "sent (id: 1)"}]},
            )

        worker = threading.Thread(target=send)
        worker.start()
        worker.join(timeout=15)

        second = harness.pre_tool(
            "mcp__plugin_discord_discord__reply",
            {"chat_id": "152", "text": "second"},
        )
        self.assertEqual(
            second.output["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        self.assertEqual(harness.transport.dispatch_count, 1)

    def test_cross_room_send_is_denied_within_an_admitted_turn(self) -> None:
        harness = self.harness()
        harness.deliver()
        decision = harness.pre_tool(
            "mcp__plugin_discord_discord__reply",
            {"chat_id": "999", "text": "elsewhere"},
        )
        self.assertEqual(
            decision.output["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        self.assertEqual(harness.transport.dispatch_count, 0)

    def test_unreadable_room_call_is_denied(self) -> None:
        harness = self.harness()
        harness.deliver()
        decision = harness.pre_tool(
            "mcp__plugin_discord_discord__reply", {"chat_id": "152"}
        )
        self.assertEqual(
            decision.output["hookSpecificOutput"]["permissionDecision"], "deny"
        )


class SilenceTests(_GateTestCase):
    def test_participant_silence_is_a_distinct_accepted_outcome(self) -> None:
        harness = self.harness()
        harness.deliver()
        harness.stop()
        host = [
            record
            for record in harness.receipts.all_records()
            if record["stage"] == "participant-host"
        ]
        self.assertTrue(host)
        self.assertEqual(host[-1]["body"]["outcome"], "silent")
        self.assertEqual(harness.transport.dispatch_count, 0)
        self.assertNotIn("transport", harness.stages())


class ConsecutiveTurnTests(_GateTestCase):
    """The lane must be released, or the room goes silent after one turn."""

    def _complete_turn(self, harness, message_id, prompt_id):
        decision = harness.deliver(message_id=message_id, prompt_id=prompt_id)
        admitted = not (decision.output or {}).get("decision")
        harness.stop(prompt_id=prompt_id)
        return admitted

    def test_every_delivery_is_judged_not_just_the_first(self) -> None:
        # Regression: the admitting branch used to return without completing
        # its scheduler token, so the lane stayed active forever and every
        # later room event was coalesced into a pending anchor that never
        # became work. That is permanent false suppression.
        harness = self.harness()
        for index, message_id in enumerate(("900", "901", "902")):
            with self.subTest(message_id=message_id):
                self.assertTrue(
                    self._complete_turn(harness, message_id, f"p{index}")
                )
        self.assertEqual(len(harness.model.calls), 3)
        self.assertEqual(harness.participant.invocation_count, 3)

    def test_the_lane_is_idle_between_turns(self) -> None:
        harness = self.harness()
        self._complete_turn(harness, "900", "p1")
        self.assertFalse(harness.scheduler.active)
        self.assertIsNone(harness.scheduler.pending_anchor)

    def test_a_silent_turn_also_releases_the_lane(self) -> None:
        harness = self.harness()
        harness.deliver(message_id="900", prompt_id="p1")
        harness.stop(prompt_id="p1")
        self.assertFalse(harness.scheduler.active)
        self.assertTrue(self._complete_turn(harness, "901", "p2"))

    def test_a_suppressed_delivery_does_not_wedge_the_lane(self) -> None:
        harness = self.harness(disposition="SUPPRESS")
        for index, message_id in enumerate(("900", "901", "902")):
            harness.deliver(message_id=message_id, prompt_id=f"p{index}")
        self.assertEqual(len(harness.model.calls), 3)

    def test_a_coalesced_delivery_is_promoted_by_stop(self) -> None:
        harness = self.harness()
        harness.deliver(message_id="900", prompt_id="p1")
        coalesced = harness.deliver(message_id="901", prompt_id="p1")
        # While a turn is active the newest anchor replaces the pending slot.
        self.assertEqual(coalesced.output["decision"], "block")
        self.assertEqual(harness.scheduler.pending_anchor, "discord:message:901")

        stop = harness.stop(prompt_id="p1")
        # Stop hands the session another turn carrying the successor's facts,
        # which is how "one replaceable newest event" becomes work.
        self.assertEqual(stop.output["decision"], "block")
        self.assertIn("[nunchi-v2 participant wake]", stop.output["reason"])
        self.assertIn("discord:message:901", stop.output["reason"])
        self.assertEqual(len(harness.model.calls), 2)

    def test_stop_with_nothing_pending_ends_the_turn(self) -> None:
        harness = self.harness()
        harness.deliver(message_id="900", prompt_id="p1")
        self.assertIsNone(harness.stop(prompt_id="p1").output)

    def test_finished_workers_do_not_accumulate(self) -> None:
        harness = self.harness()
        for index in range(4):
            self._complete_turn(harness, str(900 + index), f"p{index}")
        self.assertLessEqual(len(harness.runtime._workers), 1)


class IdentityCommitmentTests(_GateTestCase):
    """Continuity is durable only once the host attests it accepted the turn."""

    def test_an_accepted_silent_turn_commits_the_binding(self) -> None:
        harness = self.harness()
        self.assertIsNone(harness.identity_store.load())
        harness.deliver(message_id="900", prompt_id="p1")
        harness.stop(prompt_id="p1")
        committed = harness.identity_store.load()
        self.assertIsNotNone(committed)
        self.assertEqual(committed.room_id, "152")
        self.assertEqual(committed.claude_session_id, "s1")

    def test_an_accepted_sending_turn_commits_the_binding(self) -> None:
        harness = self.harness()
        harness.deliver(message_id="900", prompt_id="p1")

        def send() -> None:
            harness.pre_tool(
                "mcp__plugin_discord_discord__reply",
                {"chat_id": "152", "text": "on it"},
            )
            harness.post_tool(
                "mcp__plugin_discord_discord__reply",
                {"content": [{"type": "text", "text": "sent (id: 1234)"}]},
            )

        worker = threading.Thread(target=send)
        worker.start()
        worker.join(timeout=15)
        harness.stop(prompt_id="p1")
        self.assertIsNotNone(harness.identity_store.load())

    def test_a_suppressed_delivery_commits_nothing(self) -> None:
        harness = self.harness(disposition="SUPPRESS")
        harness.deliver(message_id="900", prompt_id="p1")
        harness.stop(prompt_id="p1")
        self.assertIsNone(harness.identity_store.load())

    def test_a_committed_binding_makes_the_drift_gate_live(self) -> None:
        # The whole point of committing: the *next* session is checked against
        # it without a test reaching in and writing the pin by hand.
        harness = self.harness()
        harness.deliver(message_id="900", prompt_id="p1", session="s1")
        harness.stop(prompt_id="p1", session="s1")
        # No test fixture reaches in: the running gate holds what it committed.
        self.assertIsNotNone(harness.runtime.committed_identity)

        drifted = harness.runtime.user_prompt_submit(
            {
                "prompt": _envelope_prompt(message_id="901"),
                "prompt_id": "p2",
                "session_id": "a-different-session",
            }
        )
        self.assertEqual(drifted.output["decision"], "block")
        self.assertIn("claude_session_id", drifted.output["reason"])
        self.assertIn("--accept rebind", drifted.output["reason"])

    def test_accepting_drift_clears_the_binding(self) -> None:
        harness = self.harness()
        harness.deliver(message_id="900", prompt_id="p1")
        harness.stop(prompt_id="p1")
        self.assertIsNotNone(harness.runtime.committed_identity)

        harness.runtime.accept_drift("rebind")
        self.assertIsNone(harness.runtime.committed_identity)
        self.assertIsNone(harness.identity_store.load())

    def test_unsupported_drift_verbs_are_refused(self) -> None:
        harness = self.harness()
        with self.assertRaises(ValidationError):
            harness.runtime.accept_drift("fallback")


class AcknowledgementParsingTests(unittest.TestCase):
    """What the channel plugin actually returns must read as what it means."""

    def setUp(self) -> None:
        from nunchi.integrations.claude_code_session import _native_result

        self.parse = _native_result

    def test_the_plugins_real_mcp_shape_is_a_confirmed_send(self) -> None:
        # server.ts returns {content: [{type: 'text', text: 'sent (id: N)'}]}.
        # Reading only bare strings reported every real send as `unknown`.
        result = self.parse(
            {"content": [{"type": "text", "text": "sent (id: 1234)"}]}, "discord"
        )
        self.assertEqual(result, {"event_id": "discord:message:1234"})

    def test_a_chunked_send_is_confirmed_by_the_ids_it_attests(self) -> None:
        result = self.parse(
            {"content": [{"type": "text", "text": "sent 3 parts (ids: 11, 12, 13)"}]},
            "discord",
        )
        self.assertEqual(result["event_id"], "discord:message:11")
        self.assertEqual(result["parts"], 3)

    def test_a_bare_string_acknowledgement_still_works(self) -> None:
        self.assertEqual(
            self.parse("sent (id: 7)", "discord"),
            {"event_id": "discord:message:7"},
        )

    def test_an_acknowledgement_attesting_no_id_is_not_a_send(self) -> None:
        for response in (
            "sent 2 parts",
            "reacted",
            "",
            {"content": [{"type": "text", "text": "queued"}]},
            {},
            None,
        ):
            with self.subTest(response=response):
                self.assertNotIn("event_id", self.parse(response, "discord"))

    def test_an_error_result_is_a_failure_not_an_unknown(self) -> None:
        result = self.parse(
            {"isError": True, "content": [{"type": "text", "text": "reply failed"}]},
            "discord",
        )
        self.assertTrue(result["failed"])
        self.assertIn("reply failed", result["detail"])


class SessionLifecycleTests(_GateTestCase):
    def test_resumed_session_records_a_gap_and_cancels(self) -> None:
        harness = self.harness()
        harness.deliver()
        harness.runtime.session_start({"source": "resume"})
        self.assertFalse(harness.scheduler.active)
        decision = harness.pre_tool(
            "mcp__plugin_discord_discord__reply",
            {"chat_id": "152", "text": "stale"},
        )
        self.assertEqual(
            decision.output["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        self.assertEqual(harness.transport.dispatch_count, 0)

    def test_fresh_session_start_is_not_a_gap(self) -> None:
        harness = self.harness()
        harness.runtime.session_start({"source": "startup"})
        self.assertEqual(harness.deliver().output.get("decision"), None)

    def test_session_end_cancels_work_in_flight(self) -> None:
        harness = self.harness()
        harness.deliver()
        harness.runtime.session_end({})
        self.assertFalse(harness.scheduler.active)
        self.assertEqual(harness.transport.dispatch_count, 0)


class CorrelationTests(_GateTestCase):
    def test_delivery_without_a_prompt_id_cannot_be_gated(self) -> None:
        harness = self.harness()
        decision = harness.runtime.user_prompt_submit(
            {"prompt": _envelope_prompt(), "session_id": "s1"}
        )
        self.assertEqual(decision.output["decision"], "block")
        self.assertEqual(harness.participant.invocation_count, 0)

    def test_a_foreign_session_may_not_resolve_another_turn(self) -> None:
        harness = self.harness()
        harness.deliver()
        decision = harness.pre_tool(
            "mcp__plugin_discord_discord__reply",
            {"chat_id": "152", "text": "hi"},
            session="other-session",
        )
        self.assertEqual(
            decision.output["hookSpecificOutput"]["permissionDecision"], "deny"
        )

    def test_foreign_room_delivery_is_not_observed(self) -> None:
        harness = self.harness()
        decision = harness.submit(_envelope_prompt(chat_id="999"))
        self.assertEqual(decision.output["decision"], "block")
        self.assertEqual(harness.model.calls, [])

    def test_delivery_without_an_exact_author_is_unroutable(self) -> None:
        harness = self.harness()
        decision = harness.submit(_envelope_prompt(user_id=""))
        self.assertEqual(decision.output["decision"], "block")
        self.assertEqual(harness.model.calls, [])


class IdentityDriftGateTests(_GateTestCase):
    def test_update_class_drift_blocks_with_the_recovery_menu(self) -> None:
        harness = self.harness()
        committed = harness.runtime.observed_identity(
            {"session_id": "s1", "claude_version": "2.1.216"}
        )
        harness.identity_store.write(committed)
        harness.runtime.committed_identity = committed
        decision = harness.runtime.user_prompt_submit(
            {
                "prompt": _envelope_prompt(),
                "prompt_id": "p1",
                "session_id": "s1",
                "claude_version": "2.9.9",
            }
        )
        self.assertEqual(decision.output["decision"], "block")
        self.assertIn("--accept rebind", decision.output["reason"])
        self.assertIn("--mode restricted-headless", decision.output["reason"])
        self.assertEqual(harness.model.calls, [])

    def test_warn_class_drift_does_not_block(self) -> None:
        harness = self.harness()
        committed = harness.runtime.observed_identity(
            {"session_id": "s1", "model": "claude-opus-5"}
        )
        harness.identity_store.write(committed)
        harness.runtime.committed_identity = committed
        decision = harness.runtime.user_prompt_submit(
            {
                "prompt": _envelope_prompt(),
                "prompt_id": "p1",
                "session_id": "s1",
                "model": "claude-sonnet-5",
            }
        )
        self.assertNotIn("decision", decision.output)

    def test_uncommitted_turn_leaves_no_resumable_identity(self) -> None:
        harness = self.harness(disposition="SUPPRESS")
        harness.deliver()
        harness.stop()
        self.assertIsNone(harness.identity_store.load())


class HookClientTests(unittest.TestCase):
    """The process boundary decides what a broken gate is allowed to do."""

    def setUp(self) -> None:
        from nunchi.integrations import claude_code_hook

        self.hook = claude_code_hook
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.missing = str(Path(self._tmp.name) / "absent.sock")

    def _run(self, event, payload, *, socket_path=None):
        environ = {}
        if socket_path is not None:
            environ[self.hook.SOCKET_ENVIRONMENT_VARIABLE] = socket_path
        return self.hook.run(event, payload, environ)

    def test_client_source_imports_nothing_from_nunchi(self) -> None:
        # This runs once per prompt and once per tool call inside the
        # operator's own session, so it is stdlib-only by construction: it
        # speaks to the gate over a socket rather than importing what the gate
        # owns. (Importing it still costs whatever `nunchi/__init__` costs,
        # because that runs for any submodule; that is a shared-core packaging
        # property, not something this module reaches for.)
        source = Path(self.hook.__file__).read_text(encoding="utf-8")
        offenders = [
            line
            for line in source.splitlines()
            if line.startswith(("import ", "from "))
            and ("nunchi" in line or line.startswith("from ."))
        ]
        self.assertEqual(offenders, [])

    def test_client_does_not_load_the_gate_or_its_owners(self) -> None:
        import subprocess
        import sys

        probe = (
            "import sys;"
            "import nunchi.integrations.claude_code_hook;"
            "print('\\n'.join(sorted("
            "m for m in sys.modules if m.startswith('nunchi'))))"
        )
        root = Path(__file__).resolve().parents[2]
        completed = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(root),
            env={**os.environ, "PYTHONPATH": str(root / "src")},
        )
        loaded = set(completed.stdout.split())
        self.assertIn("nunchi.integrations.claude_code_hook", loaded)
        for gate_owned in (
            "nunchi.integrations.claude_code_session",
            "nunchi.integrations.claude_code_v2",
            "nunchi.authorization",
        ):
            self.assertNotIn(gate_owned, loaded)

    def test_unconfigured_is_inert_for_every_event(self) -> None:
        for event in self.hook.HOOK_EVENTS:
            with self.subTest(event=event):
                code, out = self._run(event, {"prompt": _envelope_prompt()})
                self.assertEqual((code, out), (0, ""))

    def test_unreachable_gate_blocks_a_room_delivery(self) -> None:
        code, out = self._run(
            "user-prompt-submit",
            {"prompt": _envelope_prompt()},
            socket_path=self.missing,
        )
        self.assertEqual(code, 0)
        answer = json.loads(out)
        self.assertEqual(answer["decision"], "block")
        self.assertTrue(
            answer["hookSpecificOutput"]["suppressOriginalPrompt"]
        )

    def test_unreachable_gate_passes_an_operator_prompt(self) -> None:
        # There is nothing to gate, so a broken gate must not trap the operator
        # out of their own session.
        code, out = self._run(
            "user-prompt-submit",
            {"prompt": "run the tests"},
            socket_path=self.missing,
        )
        self.assertEqual((code, out), (0, ""))

    def test_unreachable_gate_denies_a_room_effect_call(self) -> None:
        for tool in (
            "mcp__plugin_discord_discord__reply",
            "mcp__plugin_discord_discord__react",
            "mcp__plugin_telegram_telegram__send",
        ):
            with self.subTest(tool=tool):
                code, out = self._run(
                    "pre-tool", {"tool_name": tool}, socket_path=self.missing
                )
                self.assertEqual(code, 0)
                self.assertEqual(
                    json.loads(out)["hookSpecificOutput"]["permissionDecision"],
                    "deny",
                )

    def test_unreachable_gate_does_not_disable_the_whole_session(self) -> None:
        # A dead gate must not take Bash, Read, and Edit offline: none of them
        # can reach the room, so denying them protects nothing and traps the
        # operator inside their own session.
        for tool in ("Bash", "Read", "Edit", "Task",
                     "mcp__plugin_discord_discord__fetch_messages"):
            with self.subTest(tool=tool):
                code, out = self._run(
                    "pre-tool", {"tool_name": tool}, socket_path=self.missing
                )
                self.assertEqual((code, out), (0, ""))

    def test_unreachable_gate_fails_open_for_reporting_events(self) -> None:
        for event in ("post-tool", "stop", "session-start", "session-end"):
            with self.subTest(event=event):
                code, out = self._run(event, {}, socket_path=self.missing)
                self.assertEqual((code, out), (0, ""))

    def test_truncated_envelope_is_treated_as_a_room_delivery(self) -> None:
        code, out = self._run(
            "user-prompt-submit",
            {"prompt": '<channel source="discord" chat_id="152"'},
            socket_path=self.missing,
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["decision"], "block")

    def test_strict_json_refuses_duplicate_keys_and_non_finite(self) -> None:
        with self.assertRaises(ValueError):
            self.hook._strict_json('{"a": 1, "a": 2}')
        with self.assertRaises(ValueError):
            self.hook._strict_json('{"a": NaN}')
        self.assertEqual(self.hook._strict_json('{"a": 1}'), {"a": 1})

    def test_answer_validation_accepts_only_the_owned_shapes(self) -> None:
        good_block = self.hook.blocked_prompt("why")
        good_context = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "facts",
            }
        }
        self.assertTrue(self.hook._is_prompt_answer(good_block))
        self.assertTrue(self.hook._is_prompt_answer(good_context))
        for bad in (
            {},
            {"decision": "allow"},
            {"decision": "block", "reason": ""},
            {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": ""}},
            {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit"}},
            {**good_context, "extra": 1},
        ):
            with self.subTest(bad=bad):
                self.assertFalse(self.hook._is_prompt_answer(bad))

        self.assertTrue(self.hook._is_tool_answer(self.hook.denied_tool("no")))
        for bad in (
            {},
            {"hookSpecificOutput": {"hookEventName": "PreToolUse"}},
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": "",
                }
            },
        ):
            with self.subTest(bad=bad):
                self.assertFalse(self.hook._is_tool_answer(bad))


class HookClientOverSocketTests(unittest.TestCase):
    """The client's contract against a real gate socket."""

    def setUp(self) -> None:
        import socket as socket_module

        from nunchi.integrations import claude_code_hook

        self.hook = claude_code_hook
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = str(Path(self._tmp.name) / "gate.sock")
        self.answers: list[str] = []
        self.requests: list[dict] = []

        self.server = socket_module.socket(
            socket_module.AF_UNIX, socket_module.SOCK_STREAM
        )
        self.server.bind(self.path)
        self.server.listen(4)
        self.addCleanup(self.server.close)

        def serve() -> None:
            while True:
                try:
                    connection, _ = self.server.accept()
                except OSError:
                    return
                with connection:
                    chunks = []
                    while True:
                        chunk = connection.recv(65536)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    try:
                        self.requests.append(
                            json.loads(b"".join(chunks).decode("utf-8"))
                        )
                    except ValueError:
                        self.requests.append({})
                    if self.answers:
                        connection.sendall(self.answers.pop(0).encode("utf-8"))

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()

    def _run(self, event, payload, environ=None):
        base = {self.hook.SOCKET_ENVIRONMENT_VARIABLE: self.path}
        base.update(environ or {})
        return self.hook.run(event, payload, base)

    def test_forwards_a_valid_answer_verbatim(self) -> None:
        answer = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "facts",
            }
        }
        self.answers.append(json.dumps({"status": "ok", "output": answer, "exit_code": 0}))
        code, out = self._run("user-prompt-submit", {"prompt": _envelope_prompt()})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), answer)

    def test_forwards_only_the_runtime_identity_environment(self) -> None:
        self.answers.append(json.dumps({"status": "ok", "output": None}))
        self._run(
            "stop",
            {},
            {
                "CLAUDE_PID": "42851",
                "CLAUDE_CODE_EXECPATH": "/opt/claude",
                "ANTHROPIC_API_KEY": "secret-must-not-travel",
                "NUNCHI_DISCORD_OUTPUT_KEY": "secret-must-not-travel",
            },
        )
        forwarded = self.requests[-1]["environment"]
        self.assertEqual(
            set(forwarded), {"CLAUDE_PID", "CLAUDE_CODE_EXECPATH"}
        )
        self.assertNotIn("ANTHROPIC_API_KEY", forwarded)
        self.assertNotIn("NUNCHI_DISCORD_OUTPUT_KEY", forwarded)

    def test_an_empty_answer_is_treated_as_a_crash(self) -> None:
        self.answers.append("")
        code, out = self._run("user-prompt-submit", {"prompt": _envelope_prompt()})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["decision"], "block")

    def test_a_duplicate_keyed_answer_is_treated_as_a_crash(self) -> None:
        self.answers.append(
            '{"status": "ok", "output": {"hookSpecificOutput": {"hookEventName": "PreToolUse",'
            ' "permissionDecision": "deny", "permissionDecision": "allow",'
            ' "permissionDecisionReason": ""}}}'
        )
        code, out = self._run(
            "pre-tool", {"tool_name": "mcp__plugin_discord_discord__reply"}
        )
        self.assertEqual(
            json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny"
        )

    def test_an_unsupported_decision_value_is_treated_as_a_crash(self) -> None:
        self.answers.append(
            json.dumps(
                {
                    "status": "ok",
                    "output": {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "ask",
                            "permissionDecisionReason": "",
                        }
                    }
                }
            )
        )
        code, out = self._run(
            "pre-tool", {"tool_name": "mcp__plugin_discord_discord__reply"}
        )
        self.assertEqual(
            json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny"
        )


class GateServerTests(_GateTestCase):
    """The hook client and the gate agree on one wire contract."""

    def _server(self, harness):
        from nunchi.integrations.claude_code_session import GateServer

        server = GateServer(harness.runtime, self.root / "sockets" / "gate.sock")
        server.start()
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.close)
        return server

    def _client(self, server, event, payload):
        from nunchi.integrations import claude_code_hook

        return claude_code_hook.run(
            event,
            payload,
            {claude_code_hook.SOCKET_ENVIRONMENT_VARIABLE: str(server.path)},
        )

    def test_socket_and_directory_are_owner_only(self) -> None:
        server = self._server(self.harness())
        self.assertEqual(server.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(server.path.parent.stat().st_mode & 0o777, 0o700)

    def test_suppress_reaches_the_client_as_a_block(self) -> None:
        harness = self.harness(disposition="SUPPRESS")
        server = self._server(harness)
        code, out = self._client(
            server,
            "user-prompt-submit",
            {"prompt": _envelope_prompt(), "prompt_id": "p1", "session_id": "s1"},
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["decision"], "block")
        self.assertEqual(harness.participant.invocation_count, 0)

    def test_wake_reaches_the_client_as_additional_context(self) -> None:
        harness = self.harness()
        server = self._server(harness)
        code, out = self._client(
            server,
            "user-prompt-submit",
            {"prompt": _envelope_prompt(), "prompt_id": "p1", "session_id": "s1"},
        )
        self.assertEqual(code, 0)
        answer = json.loads(out)
        self.assertNotIn("decision", answer)
        self.assertIn(
            "[nunchi-v2 participant wake]",
            answer["hookSpecificOutput"]["additionalContext"],
        )

    def test_a_gate_exception_is_answered_without_choosing_a_direction(self) -> None:
        # The gate reports "no answer"; the client's own fail direction decides
        # what that means for this event.
        harness = self.harness()
        server = self._server(harness)

        def explode(_payload):
            raise RuntimeError("gate fault")

        harness.runtime.user_prompt_submit = explode
        code, out = self._client(
            server,
            "user-prompt-submit",
            {"prompt": _envelope_prompt(), "prompt_id": "p1", "session_id": "s1"},
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["decision"], "block")

    def test_unknown_events_are_answered_with_no_output(self) -> None:
        server = self._server(self.harness())
        self.assertEqual(server.handle(b'{"event": "not-a-hook"}')["status"], "error")
        self.assertEqual(server.handle(b"not json")["status"], "error")
        self.assertEqual(server.handle(b"[]")["status"], "error")


class BuildAndProbeTests(_GateTestCase):
    """Configuration is pinned, and the probe states what is not guaranteed."""

    def _config(self, **overrides):
        profile = self.root / "profile.json"
        payload = json.dumps(GateHarness.PROFILE).encode("utf-8")
        profile.write_bytes(payload)
        config = {
            "schema_version": 2,
            "binding": {
                "participant_id": "vigil",
                "actor_id": "discord:user:149",
                "platform": "discord",
                "room_id": "152",
                "continuity_scope_id": "discord:channel:152",
            },
            "profile": {
                "path": str(profile),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
            "attention": {"policy": {"preattention_enabled": False}, "model": {}},
            "limits": {},
            "state_directory": str(self.root / "state"),
            "channel": {
                "source": "discord",
                "plugin": "discord",
                "plugin_version": "0.0.4",
            },
        }
        config.update(overrides)
        return config

    def test_builds_without_any_transport_credential(self) -> None:
        from nunchi.integrations.claude_code_session import build_runtime

        # The session's own channel plugin holds the channel credential. The
        # gate never needs one, which is why there is no transport block.
        runtime, socket_path = build_runtime(self._config())
        self.addCleanup(runtime.cancel, "test teardown")
        self.assertEqual(runtime.binding.room_id, "152")
        self.assertEqual(socket_path.name, "gate.sock")

    def test_unexpected_or_missing_config_fields_are_refused(self) -> None:
        from nunchi.integrations.claude_code_session import build_runtime

        with self.assertRaises(ValidationError):
            build_runtime({**self._config(), "transport": {}})
        incomplete = self._config()
        incomplete.pop("channel")
        with self.assertRaises(ValidationError):
            build_runtime(incomplete)
        with self.assertRaises(ValidationError):
            build_runtime({**self._config(), "schema_version": 1})

    def test_unverified_channel_plugin_refuses_to_build(self) -> None:
        from nunchi.integrations.claude_code_session import build_runtime

        with self.assertRaises(SessionBindingError):
            build_runtime(
                self._config(
                    channel={
                        "source": "discord",
                        "plugin": "discord",
                        "plugin_version": "9.9.9",
                    }
                )
            )

    def test_channel_source_must_match_the_binding_platform(self) -> None:
        from nunchi.integrations.claude_code_session import build_runtime

        with self.assertRaises(ValidationError):
            build_runtime(
                self._config(
                    channel={
                        "source": "telegram",
                        "plugin": "discord",
                        "plugin_version": "0.0.4",
                    }
                )
            )

    def test_configured_probe_reports_the_shortfalls_it_cannot_fix(self) -> None:
        from nunchi.integrations.claude_code_session import (
            build_runtime,
            probe_document,
        )

        runtime, _ = build_runtime(self._config())
        self.addCleanup(runtime.cancel, "test teardown")
        probe = probe_document(runtime)
        self.assertEqual(probe["mode"], "native-session")
        self.assertTrue(probe["participant_capabilities_preserved"])
        self.assertFalse(probe["send_time_social_judgment"])
        # The headline claim is honest: this surface is not a complete V2
        # lifecycle while the channel plugin emits before the gate.
        self.assertFalse(probe["complete_v2_lifecycle"])
        self.assertFalse(probe["silence_complete"])
        self.assertEqual(len(probe["shortfalls"]), 2)
        self.assertEqual(probe["native_fact_trust"], "envelope-only")
        # No privileged proposal can be constructed on this surface, so the
        # probe must not assert a capability the code cannot deliver.
        self.assertFalse(probe["privileged_actions_enabled"])
        self.assertFalse(probe["privileged_proposals_supported"])

    def test_an_authorization_block_is_refused_rather_than_ignored(self) -> None:
        from nunchi.integrations.claude_code_session import build_runtime

        with self.assertRaises(ValidationError):
            build_runtime(
                self._config(
                    authorization={
                        "policy_path": "/etc/nunchi/policy.json",
                        "policy_sha256": "d" * 64,
                    }
                )
            )

    def test_unconfigured_probe_is_honest_about_being_unconfigured(self) -> None:
        from nunchi.integrations.claude_code_session import probe_document

        probe = probe_document()
        self.assertFalse(probe["configured"])
        self.assertEqual(probe["mode"], "native-session")
        self.assertNotIn("complete_v2_lifecycle", probe)


class RestrictedFallbackTests(unittest.TestCase):
    """The headless participant survives, but only as a stated-cost fallback."""

    def setUp(self) -> None:
        from nunchi.integrations import claude_code_v2

        self.module = claude_code_v2

    def test_unconfigured_probe_names_the_mode_and_its_costs(self) -> None:
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(0, self.module.main(["--probe"]))
        probe = json.loads(buffer.getvalue())
        self.assertEqual(probe["mode"], "restricted-headless")
        self.assertEqual(probe["lost_capabilities"], list(self.module.LOST_CAPABILITIES))

    def test_lost_capabilities_name_the_substitution_plainly(self) -> None:
        joined = " ".join(self.module.LOST_CAPABILITIES)
        for expected in ("MCP servers", "skills", "CLAUDE.md", "memory", "not the session"):
            with self.subTest(expected=expected):
                self.assertIn(expected, joined)

    def test_running_the_fallback_requires_selecting_it(self) -> None:
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            code = self.module.main(
                ["--config", "/nonexistent.json", "--config-sha256", "a" * 64]
            )
        self.assertEqual(code, 3)
        message = buffer.getvalue()
        self.assertIn("restricted", message)
        self.assertIn("--mode restricted-headless", message)
        self.assertIn("nunchi-claude-code-session-gate", message)

    def test_selecting_the_fallback_gets_past_the_mode_check(self) -> None:
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            code = self.module.main(
                [
                    "--config",
                    "/nonexistent.json",
                    "--config-sha256",
                    "a" * 64,
                    "--mode",
                    "restricted-headless",
                ]
            )
        # It still fails, but on the missing config rather than on the mode:
        # the explicit selection was accepted.
        self.assertNotEqual(code, 0)
        self.assertNotIn("--mode restricted-headless", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
