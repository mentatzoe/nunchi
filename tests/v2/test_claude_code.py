"""Deterministic conformance tests for the Claude Code V2 integration.

Covers slice 070's CC-01 through CC-05 deterministic surfaces: reactive
allowlisted hearing with exact native facts, the Station regression scars,
one canonical attention invocation per ordinary opportunity with zero
classifier calls on trusted bypass, freshness coalescing, later hearing and
restart semantics, the direct act-or-silence participant turn without any
send-time social judgment, immutable singly-attested receipt stages, and the
deterministic privileged-action guard. Everything runs offline: the
classifier seam is an injected callable and all state lives in temp dirs.
"""

from __future__ import annotations

import json
import re
import stat
import tempfile
import unittest
from pathlib import Path

from tests.v2.claude_code_helpers import (
    CHANNEL_ID,
    HUMAN_ID,
    OTHER_HUMAN_ID,
    PARTICIPANT_ID,
    PEER_BOT_ID,
    SELF_USER_ID,
    CountingTransport,
    append_sidecar,
    channel_prompt,
    claude_policy_document,
    defer_judgment,
    load_gate_module,
    make_environ,
    margin_suppress_judgment,
    prompt_payload,
    read_receipts,
    receipts_for,
    sidecar_row,
    stop_packet_from_reason,
    suppress_judgment,
    wake_judgment,
    wake_packet_from_context,
    wake_request_id,
    write_claude_policy,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INTEGRATION_DIR = _REPO_ROOT / "integrations" / "claude-code"
_MODULE_SOURCE = (_INTEGRATION_DIR / "nunchi_claude_v2.py").read_text(encoding="utf-8")
_EVAL_DIR = _REPO_ROOT / "evals" / "v2" / "claude_code"
_FIXTURES = json.loads(
    (
        _REPO_ROOT / "tests" / "fixtures" / "v2" / "claude_code" / "native_events.json"
    ).read_text(encoding="utf-8")
)


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


class _GateCase(unittest.TestCase):
    """Temp-dir harness driving the hook handlers in-process."""

    def setUp(self) -> None:
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp(prefix="nunchi-claude-v2-"))
        self.tmp.chmod(0o700)
        self.addCleanup(self._cleanup)
        self.module = load_gate_module()
        self.environ = make_environ(self.tmp)
        self._ts = 0

    def _cleanup(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def next_ts(self) -> str:
        self._ts += 1
        return f"2026-07-20T12:{self._ts // 60:02d}:{self._ts % 60:02d}Z"

    def deliver(
        self,
        transport,
        *,
        message_id: str,
        author_id: str = HUMAN_ID,
        username: str = "zoe",
        bot: bool = False,
        body: str = "hello room",
        mention_user_ids: tuple[str, ...] = (),
        reply_to_message_id: str | None = None,
        session_id: str = "sess-1",
        with_sidecar: bool = True,
    ):
        ts = self.next_ts()
        if with_sidecar:
            append_sidecar(
                self.environ,
                sidecar_row(
                    message_id=message_id,
                    author_id=author_id,
                    username=username,
                    bot=bot,
                    content=body,
                    timestamp=ts,
                    mention_user_ids=mention_user_ids,
                    reply_to_message_id=reply_to_message_id,
                ),
            )
        payload = prompt_payload(
            channel_prompt(message_id=message_id, user=username, body=body, ts=ts),
            session_id=session_id,
        )
        return self.module.handle_user_prompt_submit(
            payload, self.environ, classifier_transport=transport
        )

    def stop(self, transport, *, session_id: str = "sess-1"):
        return self.module.handle_stop(
            {"session_id": session_id}, self.environ, classifier_transport=transport
        )

    def post_tool(
        self,
        *,
        tool_name: str = "mcp__discord__reply",
        tool_input: dict | None = None,
        tool_response: dict | None = None,
        session_id: str = "sess-1",
    ):
        return self.module.handle_post_tool(
            {
                "session_id": session_id,
                "tool_name": tool_name,
                "tool_input": tool_input
                or {"chat_id": CHANNEL_ID, "text": "the sweep looks fixable"},
                "tool_response": tool_response if tool_response is not None else {"ok": True},
            },
            self.environ,
        )

    def pre_tool(
        self,
        *,
        tool_name: str,
        tool_input: dict | None = None,
        session_id: str = "sess-1",
    ):
        return self.module.handle_pre_tool(
            {
                "session_id": session_id,
                "tool_name": tool_name,
                "tool_input": tool_input or {},
            },
            self.environ,
        )

    def assert_blocked(self, decision) -> None:
        self.assertIsNotNone(decision.output)
        self.assertEqual(decision.output.get("decision"), "block")
        self.assertEqual(decision.output.get("reason"), "")

    def assert_woken(self, decision) -> dict:
        self.assertIsNotNone(decision.output)
        self.assertIn("hookSpecificOutput", decision.output)
        return wake_packet_from_context(decision.output)


# ---------------------------------------------------------------------------
# T001 — canonical contract, no V1 bridge, trusted bypass, receipt ownership
# ---------------------------------------------------------------------------


class CanonicalContractCases(_GateCase):
    def test_v1_gate_and_compatibility_bridge_are_absent(self) -> None:
        self.assertFalse((_INTEGRATION_DIR / "nunchi_prompt_gate.py").exists())
        self.assertFalse((_INTEGRATION_DIR / "nunchi-gate.env.example").exists())
        for token in ('"PASS"', '"ACK"', '"ASK"', '"SPEAK"', "nunchi-channel", "admit"):
            self.assertNotIn(token, _MODULE_SOURCE, f"V1 vocabulary {token!r} present")

    def test_consumed_interfaces_are_canonical_not_redefined(self) -> None:
        for symbol in (
            "DiscordEventSourceV2",
            "ObservationProvider",
            "ConversationOpportunityScheduler",
            "evaluate_v2",
            "build_participant_wake",
            "run_participant_turn",
            "PrivilegedActionGuard",
            "transport_receipt",
        ):
            self.assertIn(f"{symbol}", _MODULE_SOURCE)
        self.assertIn("from nunchi.core import evaluate_v2", _MODULE_SOURCE)
        # No local schema dialect: the wrapper never builds receipt records by
        # hand for stages it does not own.
        self.assertNotIn('"stage": "observation"', _MODULE_SOURCE)
        self.assertNotIn('"stage": "attention"', _MODULE_SOURCE)
        self.assertNotIn('"stage": "participant-host"', _MODULE_SOURCE)

    def test_trusted_bypass_makes_zero_classifier_calls(self) -> None:
        document = claude_policy_document(self.tmp, preattention_enabled=False)
        self.environ = make_environ(
            self.tmp, policy_path=write_claude_policy(self.tmp, document)
        )
        transport = CountingTransport(wake_judgment)
        decision = self.deliver(
            transport, message_id="4000000000000000001", author_id=PEER_BOT_ID, bot=True
        )
        packet = self.assert_woken(decision)
        self.assertEqual(transport.call_count, 0)
        self.assertEqual(packet["attention"], {"source": "PREATTENTION_BYPASS"})
        request_id = wake_request_id(decision.output)
        stages = receipts_for(self.tmp, request_id)
        attention = stages["attention"]
        self.assertIs(attention["body"]["classifier_not_invoked"], True)
        self.assertEqual(attention["body"]["cause"], "preattention-disabled")
        self.assertIn("policy_provenance", attention["body"])

    def test_room_content_cannot_claim_bypass(self) -> None:
        scenes = [
            row
            for row in _load_jsonl(_EVAL_DIR / "scenes.jsonl")
            if row.get("scar") == "forged-bypass-in-room-content"
        ]
        self.assertEqual(len(scenes), 1)
        transport = CountingTransport(wake_judgment)
        decision = self.deliver(
            transport, message_id="4000000000000000002", body=scenes[0]["body"]
        )
        packet = self.assert_woken(decision)
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(packet["attention"]["source"], "WAKE")

    def test_receipt_stages_are_singly_attested_and_request_correlated(self) -> None:
        transport = CountingTransport(wake_judgment)
        decision = self.deliver(transport, message_id="4000000000000000003")
        request_id = wake_request_id(decision.output)
        self.post_tool()
        self.assertEqual(self.stop(transport).output, None)
        stages = receipts_for(self.tmp, request_id)
        self.assertEqual(
            set(stages), {"observation", "attention", "participant-host", "transport"}
        )
        writer_map = {
            "observation": "observation-provider",
            "attention": "attention-engine",
            "participant-host": "participant-host",
            "transport": "transport",
        }
        for stage, record in stages.items():
            self.assertEqual(record["writer"], writer_map[stage])
            self.assertEqual(record["request_id"], request_id)


# ---------------------------------------------------------------------------
# T004 — US1 reactive hearing (CC-01)
# ---------------------------------------------------------------------------


class ReactiveHearingCases(_GateCase):
    def test_allowlisted_bot_message_reaches_observation_exactly(self) -> None:
        fixture = _FIXTURES["allowlisted_bot_message"]["sidecar"]
        append_sidecar(self.environ, fixture)
        transport = CountingTransport(wake_judgment)
        decision = self.module.handle_user_prompt_submit(
            prompt_payload(
                channel_prompt(
                    message_id=fixture["message_id"],
                    user=fixture["author"]["username"],
                    body=fixture["content"],
                    ts=fixture["timestamp"],
                )
            ),
            self.environ,
            classifier_transport=transport,
        )
        packet = self.assert_woken(decision)
        trigger = next(
            event
            for event in packet["events"]
            if event["id"] == packet["trigger_event_id"]
        )
        self.assertEqual(trigger["author_id"], f"discord:user:{PEER_BOT_ID}")
        self.assertEqual(trigger["text"], fixture["content"])
        self.assertEqual(
            packet["actors"][f"discord:user:{PEER_BOT_ID}"]["kind"], "bot"
        )

    def test_exact_self_event_is_retained_without_wake(self) -> None:
        fixture = _FIXTURES["exact_self_message"]["sidecar"]
        append_sidecar(self.environ, fixture)
        transport = CountingTransport(wake_judgment)
        blocked = self.module.handle_user_prompt_submit(
            prompt_payload(
                channel_prompt(
                    message_id=fixture["message_id"],
                    user=fixture["author"]["username"],
                    body=fixture["content"],
                    ts=fixture["timestamp"],
                )
            ),
            self.environ,
            classifier_transport=transport,
        )
        self.assert_blocked(blocked)
        self.assertEqual(transport.call_count, 0)
        # The fixture carries a fixed timestamp; later synthetic events must
        # stay in native order for the bounded snapshot.
        self._ts = 600
        decision = self.deliver(transport, message_id="4000000000000000010")
        packet = self.assert_woken(decision)
        self.assertIn(
            f"discord:message:{fixture['message_id']}",
            [event["id"] for event in packet["events"]],
        )

    def test_native_reply_and_mentions_are_preserved(self) -> None:
        upstream = _FIXTURES["allowlisted_bot_message"]["sidecar"]
        relation = _FIXTURES["native_relations_message"]["sidecar"]
        append_sidecar(self.environ, upstream, relation)
        transport = CountingTransport(wake_judgment)
        self.module.handle_user_prompt_submit(
            prompt_payload(
                channel_prompt(
                    message_id=upstream["message_id"],
                    user=upstream["author"]["username"],
                    body=upstream["content"],
                    ts=upstream["timestamp"],
                )
            ),
            self.environ,
            classifier_transport=CountingTransport(suppress_judgment),
        )
        decision = self.module.handle_user_prompt_submit(
            prompt_payload(
                channel_prompt(
                    message_id=relation["message_id"],
                    user=relation["author"]["username"],
                    body=relation["content"],
                    ts=relation["timestamp"],
                )
            ),
            self.environ,
            classifier_transport=transport,
        )
        packet = self.assert_woken(decision)
        trigger = next(
            event
            for event in packet["events"]
            if event["id"] == packet["trigger_event_id"]
        )
        self.assertEqual(
            trigger["reply_to_event_id"],
            f"discord:message:{upstream['message_id']}",
        )
        self.assertEqual(
            trigger["mentioned_actor_ids"], [f"discord:user:{SELF_USER_ID}"]
        )

    def test_missing_sidecar_record_is_unroutable_and_fail_closed(self) -> None:
        transport = CountingTransport(wake_judgment)
        decision = self.deliver(
            transport, message_id="4000000000000000011", with_sidecar=False
        )
        self.assert_blocked(decision)
        self.assertEqual(transport.call_count, 0)
        self.assertTrue(
            any("unroutable" in line for line in decision.diagnostics),
            decision.diagnostics,
        )

    def test_duplicate_delivery_never_spends_a_second_judgment(self) -> None:
        transport = CountingTransport(wake_judgment)
        first = self.deliver(transport, message_id="4000000000000000012")
        self.assert_woken(first)
        self.post_tool()
        self.stop(transport)
        payload = prompt_payload(
            channel_prompt(
                message_id="4000000000000000012",
                body="hello room",
                ts="2026-07-20T12:00:01Z",
            )
        )
        second = self.module.handle_user_prompt_submit(
            payload, self.environ, classifier_transport=transport
        )
        self.assert_blocked(second)
        self.assertEqual(transport.call_count, 1)

    def test_operator_prompts_and_foreign_rooms_pass_untouched(self) -> None:
        transport = CountingTransport(wake_judgment)
        plain = self.module.handle_user_prompt_submit(
            prompt_payload("run the unit suite"),
            self.environ,
            classifier_transport=transport,
        )
        self.assertIsNone(plain.output)
        foreign = self.module.handle_user_prompt_submit(
            prompt_payload(
                channel_prompt(message_id="1", chat_id="9999999999999999999")
            ),
            self.environ,
            classifier_transport=transport,
        )
        self.assertIsNone(foreign.output)
        self.assertEqual(transport.call_count, 0)

    def test_reactive_surface_has_no_polling_loop(self) -> None:
        for token in ("urllib", "socket", "requests.get", "poll("):
            self.assertNotIn(token, _MODULE_SOURCE)
        settings = self.module._SETTINGS_TEMPLATE
        for event in ("UserPromptSubmit", "Stop", "PreToolUse", "PostToolUse"):
            self.assertIn(event, settings)

    def test_transport_patch_provenance_is_pinned_and_fail_closed(self) -> None:
        patch_dir = _INTEGRATION_DIR / "transport-patch"
        patch_one = (patch_dir / "0001-allow-bot-messages-allowfrom.patch").read_text(
            encoding="utf-8"
        )
        patch_two = (patch_dir / "0002-native-fact-sidecar.patch").read_text(
            encoding="utf-8"
        )
        script = (patch_dir / "apply-transport-patch.sh").read_text(encoding="utf-8")
        self.assertIn("msg.author.id === client.user?.id", patch_one)
        self.assertIn("-  if (msg.author.bot) return", patch_one)
        self.assertIn("nunchi-native-events.jsonl", patch_two)
        self.assertIn("reply_to_message_id", patch_two)
        self.assertRegex(script, r"BASE_SHA256=\"[0-9a-f]{64}\"")
        self.assertRegex(script, r"PATCHED_SHA256=\"[0-9a-f]{64}\"")
        self.assertIn("fail closed", script)


# ---------------------------------------------------------------------------
# T008 — US2 attention routing (CC-02, CC-03) and later hearing (CC-05)
# ---------------------------------------------------------------------------


class AttentionRoutingCases(_GateCase):
    def _scar_scenes(self) -> list[dict]:
        return [
            row
            for row in _load_jsonl(_EVAL_DIR / "scenes.jsonl")
            if "scar" in row and row["scene_id"] == "CC-02"
        ]

    def test_station_scars_reach_the_classifier_verbatim(self) -> None:
        scenes = self._scar_scenes()
        self.assertGreaterEqual(len(scenes), 5)
        for index, scene in enumerate(scenes):
            with self.subTest(scar=scene["scar"]):
                case = _GateCase()
                case.setUp()
                try:
                    transport = CountingTransport(wake_judgment)
                    decision = case.deliver(
                        transport,
                        message_id=f"41000000000000000{index:02d}",
                        author_id=scene["author_id"],
                        bot=scene["author_kind"] == "bot",
                        body=scene["body"],
                        mention_user_ids=tuple(scene.get("mention_user_ids", ())),
                    )
                    case.assert_woken(decision)
                    # Exactly one judgment, and the model saw the literal facts.
                    case.assertEqual(transport.call_count, 1)
                    projection = transport.calls[0]
                    trigger = next(
                        event
                        for event in projection["events"]
                        if event["id"] == projection["trigger_event_id"]
                    )
                    case.assertEqual(trigger["text"], scene["body"])
                    expected_mentions = [
                        f"discord:user:{value}"
                        for value in scene.get("mention_user_ids", ())
                    ]
                    case.assertEqual(trigger["mentioned_actor_ids"], expected_mentions)
                finally:
                    case._cleanup()

    def test_only_the_model_judgment_suppresses_a_scar(self) -> None:
        scene = self._scar_scenes()[0]
        transport = CountingTransport(suppress_judgment)
        decision = self.deliver(
            transport,
            message_id="4200000000000000001",
            author_id=scene["author_id"],
            body=scene["body"],
            mention_user_ids=tuple(scene.get("mention_user_ids", ())),
        )
        self.assert_blocked(decision)
        self.assertEqual(transport.call_count, 1)
        receipts = read_receipts(self.tmp)
        stages = {record["stage"] for record in receipts}
        self.assertIn("attention", stages)
        self.assertNotIn("participant-host", stages)

    def test_classifier_defer_and_margin_defer_route_distinctly(self) -> None:
        config = self.module.ClaudeGateConfig.from_env(self.environ)
        row = sidecar_row(message_id="4300000000000000001", timestamp=self.next_ts())
        append_sidecar(self.environ, row)
        with self.module.RoomStateStore(config.state_dir) as store:
            binding = self.module.ClaudeRoomV2(
                config, store, classifier_transport=CountingTransport(defer_judgment)
            )
            tag = {
                "chat_id": CHANNEL_ID,
                "message_id": row["message_id"],
                "user": "zoe",
                "user_id": "",
                "ts": row["timestamp"],
                "body": row["content"],
            }
            event, _ = self.module.message_event_from_native_facts(tag, row)
            native = binding.source.native_input(event)
            store.append_event_row({"kind": "native", "native": native})
            binding.observation.ingest(native)
            classifier = binding.run_attention(native["event"]["id"])
            self.assertEqual(classifier["route"], "wake")
            self.assertEqual(
                classifier["decision"]["routing_audit"]["valve"], "classifier-defer"
            )
            self.assertEqual(classifier["decision"]["effective_disposition"], "DEFER")

        with self.module.RoomStateStore(config.state_dir) as store:
            binding = self.module.ClaudeRoomV2(
                config,
                store,
                classifier_transport=CountingTransport(margin_suppress_judgment),
            )
            row2 = sidecar_row(
                message_id="4300000000000000002", timestamp=self.next_ts()
            )
            tag2 = dict(
                chat_id=CHANNEL_ID,
                message_id=row2["message_id"],
                user="zoe",
                user_id="",
                ts=row2["timestamp"],
                body=row2["content"],
            )
            event2, _ = self.module.message_event_from_native_facts(tag2, row2)
            native2 = binding.source.native_input(event2)
            store.append_event_row({"kind": "native", "native": native2})
            binding.observation.ingest(native2)
            margin = binding.run_attention(native2["event"]["id"])
            self.assertEqual(margin["route"], "wake")
            self.assertEqual(
                margin["decision"]["routing_audit"]["valve"], "margin-defer"
            )
            self.assertEqual(
                margin["decision"]["classifier_disposition"], "SUPPRESS"
            )
            self.assertEqual(margin["decision"]["effective_disposition"], "DEFER")

    def test_wake_carries_only_cited_advice(self) -> None:
        def wake_with_advice(projection):
            judgment = wake_judgment(projection)
            judgment["attention_advice"] = [
                {
                    "note": "the room addressed this participant directly",
                    "evidence_event_ids": [projection["trigger_event_id"]],
                }
            ]
            return judgment

        transport = CountingTransport(wake_with_advice)
        decision = self.deliver(transport, message_id="4400000000000000001")
        packet = self.assert_woken(decision)
        self.assertEqual(packet["attention"]["source"], "WAKE")
        self.assertEqual(
            packet["attention"]["evidence_event_ids"],
            ["discord:message:4400000000000000001"],
        )

    def test_operational_error_fabricates_no_social_result(self) -> None:
        transport = CountingTransport(lambda projection: {"malformed": True})
        decision = self.deliver(transport, message_id="4500000000000000001")
        packet = self.assert_woken(decision)
        self.assertEqual(packet["attention"]["source"], "ERROR_FALLBACK")
        request_id = wake_request_id(decision.output)
        attention = receipts_for(self.tmp, request_id)["attention"]
        self.assertNotIn("classifier_not_invoked", attention["body"])
        self.assertIn("error", json.dumps(attention["body"]))

    def test_no_wake_error_policy_blocks_without_social_verdict(self) -> None:
        document = claude_policy_document(self.tmp, error_action="NO_WAKE")
        self.environ = make_environ(
            self.tmp, policy_path=write_claude_policy(self.tmp, document)
        )
        transport = CountingTransport(lambda projection: {"malformed": True})
        decision = self.deliver(transport, message_id="4500000000000000002")
        self.assert_blocked(decision)
        records = read_receipts(self.tmp)
        host = [r for r in records if r["stage"] == "participant-host"]
        self.assertEqual(len(host), 1)
        self.assertIs(host[0]["body"]["invoked"], False)
        self.assertEqual(host[0]["body"]["outcome"], "unknown")

    def test_suppressed_event_remains_hearable_later(self) -> None:
        cases = {row["case"] for row in _load_jsonl(_EVAL_DIR / "recovery.jsonl")}
        self.assertIn("later-hearing-after-suppression", cases)
        suppressor = CountingTransport(suppress_judgment)
        blocked = self.deliver(suppressor, message_id="4600000000000000001")
        self.assert_blocked(blocked)
        waker = CountingTransport(wake_judgment)
        decision = self.deliver(waker, message_id="4600000000000000002")
        packet = self.assert_woken(decision)
        self.assertIn(
            "discord:message:4600000000000000001",
            [event["id"] for event in packet["events"]],
        )


# ---------------------------------------------------------------------------
# I-040C — freshness coalescing and restart semantics (CC-05)
# ---------------------------------------------------------------------------


class CoalescingAndRestartCases(_GateCase):
    def test_burst_coalesces_to_one_fresh_successor(self) -> None:
        transport = CountingTransport(wake_judgment)
        first = self.deliver(transport, message_id="4700000000000000001")
        self.assert_woken(first)
        second = self.deliver(transport, message_id="4700000000000000002", body="more")
        self.assert_blocked(second)
        third = self.deliver(transport, message_id="4700000000000000003", body="newest")
        self.assert_blocked(third)
        self.assertEqual(transport.call_count, 1)

        stop_transport = CountingTransport(wake_judgment)
        stop_decision = self.stop(stop_transport)
        self.assertIsNotNone(stop_decision.output)
        self.assertEqual(stop_decision.output["decision"], "block")
        packet = stop_packet_from_reason(stop_decision.output)
        # One successor, anchored at the NEWEST event, with a fresh snapshot
        # containing every intervening event as context.
        self.assertEqual(
            packet["trigger_event_id"], "discord:message:4700000000000000003"
        )
        event_ids = [event["id"] for event in packet["events"]]
        self.assertIn("discord:message:4700000000000000001", event_ids)
        self.assertIn("discord:message:4700000000000000002", event_ids)
        self.assertEqual(stop_transport.call_count, 1)

        final = self.stop(stop_transport)
        self.assertIsNone(final.output)

    def test_restart_drops_pending_anchor_but_retains_context(self) -> None:
        rows = {row["case"] for row in _load_jsonl(_EVAL_DIR / "recovery.jsonl")}
        self.assertIn("restart-drops-pending-anchor", rows)
        self.assertIn("restart-retains-context", rows)
        transport = CountingTransport(wake_judgment)
        self.assert_woken(self.deliver(transport, message_id="4800000000000000001"))
        pending = self.deliver(
            transport, message_id="4800000000000000002", body="pending anchor"
        )
        self.assert_blocked(pending)

        restart_transport = CountingTransport(wake_judgment)
        decision = self.deliver(
            restart_transport,
            message_id="4800000000000000003",
            body="after restart",
            session_id="sess-2",
        )
        packet = self.assert_woken(decision)
        # The new session's opportunity anchors at ITS event; the dead
        # session's pending anchor never becomes a wake.
        self.assertEqual(
            packet["trigger_event_id"], "discord:message:4800000000000000003"
        )
        event_ids = [event["id"] for event in packet["events"]]
        self.assertIn("discord:message:4800000000000000001", event_ids)
        self.assertIn("discord:message:4800000000000000002", event_ids)
        stop_decision = self.stop(restart_transport, session_id="sess-2")
        self.assertIsNone(stop_decision.output)
        # The prior session's abandoned turn gained no fabricated receipts.
        host_receipts = [
            record
            for record in read_receipts(self.tmp)
            if record["stage"] == "participant-host"
        ]
        self.assertEqual(len(host_receipts), 1)


# ---------------------------------------------------------------------------
# T013 — US3 direct act-or-silence (CC-04)
# ---------------------------------------------------------------------------


class ParticipantTurnCases(_GateCase):
    def test_act_path_records_host_and_transport_stages(self) -> None:
        transport = CountingTransport(wake_judgment)
        decision = self.deliver(transport, message_id="4900000000000000001")
        request_id = wake_request_id(decision.output)
        self.post_tool(
            tool_input={
                "chat_id": CHANNEL_ID,
                "text": "the deploy failed because the schema drifted — rerun with --repair",
                "reply_to": "4900000000000000001",
            }
        )
        self.assertIsNone(self.stop(transport).output)
        stages = receipts_for(self.tmp, request_id)
        host = stages["participant-host"]
        self.assertIs(host["body"]["invoked"], True)
        self.assertEqual(host["body"]["outcome"], "sent")
        transport_stage = stages["transport"]
        self.assertEqual(transport_stage["body"]["delivery"], "sent")
        detail = json.loads(transport_stage["body"]["detail"])
        self.assertEqual(detail["surface"], "claude-code-native-tool")
        self.assertEqual(detail["observed_actions"], 1)

    def test_silence_is_a_valid_outcome_with_no_transport_stage(self) -> None:
        transport = CountingTransport(wake_judgment)
        decision = self.deliver(transport, message_id="4900000000000000002")
        request_id = wake_request_id(decision.output)
        self.assertIsNone(self.stop(transport).output)
        stages = receipts_for(self.tmp, request_id)
        self.assertEqual(stages["participant-host"]["body"]["outcome"], "silent")
        self.assertNotIn("transport", stages)

    def test_reaction_contribution_is_recorded(self) -> None:
        transport = CountingTransport(wake_judgment)
        decision = self.deliver(transport, message_id="4900000000000000003")
        request_id = wake_request_id(decision.output)
        self.post_tool(
            tool_name="mcp__discord__react",
            tool_input={
                "chat_id": CHANNEL_ID,
                "message_id": "4900000000000000003",
                "emoji": "👀",
            },
        )
        self.assertIsNone(self.stop(transport).output)
        stages = receipts_for(self.tmp, request_id)
        self.assertEqual(stages["participant-host"]["body"]["outcome"], "sent")
        self.assertEqual(stages["transport"]["body"]["delivery"], "sent")

    def test_failed_native_delivery_is_recorded_honestly(self) -> None:
        transport = CountingTransport(wake_judgment)
        decision = self.deliver(transport, message_id="4900000000000000004")
        request_id = wake_request_id(decision.output)
        self.post_tool(tool_response={"isError": True})
        self.assertIsNone(self.stop(transport).output)
        stages = receipts_for(self.tmp, request_id)
        self.assertEqual(stages["transport"]["body"]["delivery"], "failed")

    def test_no_send_time_social_gate_and_no_prose_filter(self) -> None:
        transport = CountingTransport(wake_judgment)
        self.assert_woken(self.deliver(transport, message_id="4900000000000000005"))
        gate = self.pre_tool(
            tool_name="mcp__discord__reply",
            tool_input={"chat_id": CHANNEL_ID, "text": "any text"},
        )
        self.assertIsNone(gate.output)
        self.assertEqual(gate.exit_code, 0)
        # A meta-answer-shaped sentence is recorded verbatim: grading is a
        # post-hoc evaluation concern (scenes corpus), never a runtime filter.
        grading_rows = [
            row
            for row in _load_jsonl(_EVAL_DIR / "scenes.jsonl")
            if row.get("kind") == "meta-answer-grading"
        ]
        self.assertGreaterEqual(len(grading_rows), 3)
        meta_text = next(
            row["sent_text"] for row in grading_rows if row["grade"] == "meta-answer"
        )
        self.post_tool(tool_input={"chat_id": CHANNEL_ID, "text": meta_text})
        self.assertIsNone(self.stop(transport).output)
        records = read_receipts(self.tmp)
        host = [r for r in records if r["stage"] == "participant-host"]
        self.assertEqual(host[0]["body"]["outcome"], "sent")

    def test_wake_instruction_is_room_directed_not_admission_shaped(self) -> None:
        transport = CountingTransport(wake_judgment)
        decision = self.deliver(transport, message_id="4900000000000000006")
        context = decision.output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Silence is a valid outcome", context)
        self.assertIn("untrusted room content", context)
        self.assertIn("anchor, not an obligation", context)
        self.assertNotIn("report whether", context)


# ---------------------------------------------------------------------------
# I-040B — deterministic privileged-action authorization (S18)
# ---------------------------------------------------------------------------


class ActionGuardCases(_GateCase):
    def _configure_guard(self, grants: list[dict]) -> None:
        tools_path = self.tmp / "tools.json"
        tools_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "privileged": [
                        {
                            "tool_pattern": "^Bash$",
                            "capability": "workspace.shell.exec",
                            "impact": "mutation",
                            "resource_kind": "shell-command",
                            "resource_id_input_key": "command",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        document = claude_policy_document(self.tmp)
        document["authorization"]["grants"] = grants
        self.environ = make_environ(
            self.tmp,
            policy_path=write_claude_policy(self.tmp, document),
            NUNCHI_CLAUDE_V2_TOOLS=str(tools_path),
        )

    def _grant(self, actor_id: str, *, execution: str = "direct") -> dict:
        grant = {
            "grant_id": "grant-shell",
            "actor_id": actor_id,
            "capability": "workspace.shell.exec",
            "scope": {
                "platform": "discord",
                "room_id": CHANNEL_ID,
                "participant_id": PARTICIPANT_ID,
                "resource": {"kind": "shell-command", "id": "ls -la"},
            },
            "impact": "mutation",
            "execution": execution,
            "status": "active",
            "expires_at": "2030-01-01T00:00:00Z",
        }
        if execution == "approval":
            grant["allowed_approver_actor_ids"] = [f"discord:user:{OTHER_HUMAN_ID}"]
        return grant

    def _wake_room_turn(self) -> None:
        transport = CountingTransport(wake_judgment)
        decision = self.deliver(transport, message_id="5000000000000000001")
        self.assert_woken(decision)

    def test_grant_bound_to_transport_attested_requester_allows(self) -> None:
        self._configure_guard([self._grant(f"discord:user:{HUMAN_ID}")])
        self._wake_room_turn()
        decision = self.pre_tool(tool_name="Bash", tool_input={"command": "ls -la"})
        self.assertIsNone(decision.output)
        self.assertEqual(decision.exit_code, 0)
        audits = [
            path
            for path in (self.tmp / "receipts").iterdir()
            if path.name.startswith("authorization-")
        ]
        self.assertEqual(len(audits), 1)
        record = json.loads(audits[0].read_text(encoding="utf-8"))
        self.assertEqual(record["decision"], "ALLOW")
        self.assertEqual(
            record["derived_requester_actor_id"], f"discord:user:{HUMAN_ID}"
        )

    def test_grant_for_a_different_actor_denies(self) -> None:
        self._configure_guard([self._grant(f"discord:user:{OTHER_HUMAN_ID}")])
        self._wake_room_turn()
        decision = self.pre_tool(tool_name="Bash", tool_input={"command": "ls -la"})
        self.assertIsNotNone(decision.output)
        reason = decision.output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("DENY", reason)

    def test_approval_bound_grant_defers_to_authenticated_approval(self) -> None:
        self._configure_guard(
            [self._grant(f"discord:user:{HUMAN_ID}", execution="approval")]
        )
        self._wake_room_turn()
        decision = self.pre_tool(tool_name="Bash", tool_input={"command": "ls -la"})
        self.assertIsNotNone(decision.output)
        reason = decision.output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("APPROVAL_REQUIRED", reason)

    def test_unprivileged_and_unconfigured_paths_are_reported_not_gated(self) -> None:
        self._configure_guard([self._grant(f"discord:user:{HUMAN_ID}")])
        self._wake_room_turn()
        read_decision = self.pre_tool(tool_name="Read", tool_input={"file_path": "/x"})
        self.assertIsNone(read_decision.output)
        # Without a tools map the guard enforces nothing; the packet reports
        # that state as unenforced rather than claiming safety.
        bare = make_environ(self.tmp, policy_path=Path(self.environ["NUNCHI_CLAUDE_V2_POLICY"]))
        unenforced = self.module.handle_pre_tool(
            {"session_id": "sess-1", "tool_name": "Bash", "tool_input": {"command": "rm -rf /"}},
            bare,
        )
        self.assertIsNone(unenforced.output)

    def test_guard_fails_closed_on_internal_error(self) -> None:
        self._configure_guard([self._grant(f"discord:user:{HUMAN_ID}")])
        self._wake_room_turn()
        state_dir = Path(self.environ["NUNCHI_CLAUDE_V2_STATE_DIR"])
        # Corrupt the state root: replace the directory with a file so the
        # store cannot open. The configured guard must deny, not pass.
        import shutil

        shutil.rmtree(state_dir)
        state_dir.write_text("not a directory", encoding="utf-8")
        decision = self.pre_tool(tool_name="Bash", tool_input={"command": "ls -la"})
        self.assertEqual(decision.exit_code, 2)

    def test_guard_scope_only_covers_room_caused_turns(self) -> None:
        self._configure_guard([self._grant(f"discord:user:{HUMAN_ID}")])
        decision = self.pre_tool(
            tool_name="Bash", tool_input={"command": "ls -la"}, session_id="operator"
        )
        self.assertIsNone(decision.output)
        self.assertEqual(decision.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
