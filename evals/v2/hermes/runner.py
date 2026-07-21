from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from nunchi.policy import load_operator_policy


ROOT = Path(__file__).resolve().parents[3]
SCENES = Path(__file__).with_name("scenes.jsonl")
PLUGIN_DIR = ROOT / "integrations" / "hermes" / "nunchi-gate"
EXPECTED_HERMES_VERSION = "0.19.0"
EXPECTED_HERMES_COMMIT = "f657840e06e03b9552cf2d28175a1e4e4af0210b"


def _load_module(name: str, path: Path):
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


v2 = _load_module("nunchi_hermes_v2_runtime", PLUGIN_DIR / "v2_runtime.py")
v2_plugin = _load_module("nunchi_hermes_v2_plugin", PLUGIN_DIR / "v2_plugin.py")


class _Platform:
    def __init__(self, value: str):
        self.value = value


class _Gateway:
    def __init__(self, adapter: Any):
        self.adapter = adapter

    def _adapter_for_source(self, source: Any):
        return self.adapter


def _native(event_id: str, *, author: str = "discord:user:1001", mentions=()):
    return {
        "delivery_id": event_id,
        "disposition": "candidate-event",
        "authorized": True,
        "event": {
            "id": event_id,
            "type": "message",
            "author_id": author,
            "text": "hello room",
            "mentioned_actor_ids": list(mentions),
            "mentions_room": False,
        },
        "actors": {author: {"kind": "human", "display_name": "SharedName"}},
    }


def _hermes_event(event_id: str = "10") -> Any:
    source = SimpleNamespace(
        profile="default", platform=_Platform("discord"), chat_id="42",
        thread_id=None, parent_chat_id=None, user_id="1001",
        user_name="Zoe", is_bot=False,
    )
    raw = SimpleNamespace(
        id=int(event_id), content="hello room",
        author=SimpleNamespace(id=1001, display_name="Zoe", bot=False),
        mentions=[], role_mentions=[], mention_everyone=False, reference=None,
        created_at=datetime(2026, 7, 20, 19, 0, tzinfo=timezone.utc),
    )
    return SimpleNamespace(
        source=source, message_id=event_id, text="hello room",
        raw_message=raw, internal=False,
    )


def _policy_document(
    continuity_scope_id: str,
    *,
    participant_id: str = "resident",
    preattention: bool = True,
    error_action: str = "WAKE",
):
    return {
        "schema_version": 2,
        "source": "operator:hermes-offline-eval",
        "attention": {
            "participant_id": participant_id,
            "preattention_enabled": preattention,
            "social_suppression_enabled": True,
            "attention_max_events": 50,
            "attention_max_bytes": 65536,
            "participant_max_events": 50,
            "participant_max_bytes": 65536,
            "fetch_max_events": 20,
            "fetch_max_bytes": 32768,
            "error_action": error_action,
            "transition_defer_margin": 0.12,
            "transition_defer_margin_source": "operator:hermes-offline-eval",
        },
        "recoverability": {
            "participant_id": participant_id,
            "continuity_scope_id": continuity_scope_id,
            "eligible": True,
        },
        "classifier": {
            "provider": "openai-compatible",
            "endpoint": "https://offline.invalid/v1/chat/completions",
            "model": "participant-shaped-offline-stub",
            "api_key": "offline-placeholder-not-a-credential",
            "timeout_seconds": 1,
            "max_retries": 0,
        },
        "authorization": {
            "decision_ttl_seconds": 30,
            "approval_ttl_seconds": 300,
            "grants": [],
        },
        "receipt_sink": {
            "type": "exclusive-json-file",
            "directory": "/tmp/nunchi-hermes-offline-receipts",
            "source": "operator:hermes-offline-eval",
        },
    }


def _write_policy(directory: Path, continuity_scope_id: str, **overrides: Any) -> Path:
    document = _policy_document(continuity_scope_id, **overrides)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    receipt_dir = directory / "receipts"
    receipt_dir.mkdir(mode=0o700)
    document["receipt_sink"]["directory"] = str(receipt_dir)
    path = directory / "policy.json"
    path.write_text(json.dumps(document, sort_keys=True))
    os.chmod(path, 0o600)
    return path


def _metadata() -> dict[str, dict[str, Any]]:
    rows = {}
    for line in SCENES.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["hm_case_id"]] = row
    return rows


def _result(case_id: str, assertions: dict[str, Any], metadata: dict[str, dict[str, Any]]):
    passed = all(value is True for value in assertions.values())
    base = copy.deepcopy(metadata[case_id])
    base.update({
        "result": "PASS" if passed else "FAIL",
        "assertions": assertions,
    })
    return base


def _hm01(metadata):
    controller = v2_plugin.HermesV2Controller(participant_id="resident")
    key_a = v2.BindingKey("profile-a", "discord", "discord:user:9001", "discord:channel:42")
    key_b = v2.BindingKey("profile-b", "discord", "discord:user:9002", "discord:channel:42")
    a = controller.registry_for("profile-a-participant").get_or_create(key_a)
    b = controller.registry_for("profile-b-participant").get_or_create(key_b)
    authored_by_a = _native("discord:message:1", author="discord:user:9001")
    accepted_a = a.accept(authored_by_a)
    accepted_b = b.accept(authored_by_a)
    controller.tickets.issue(
        event_id="discord:message:2",
        session_key="agent:profile-a:discord:42",
        packet={
            "trigger_event_id": "discord:message:2",
            "participant_id": "profile-a-participant",
        },
    )
    controller.tickets.issue(
        event_id="discord:message:2",
        session_key="agent:profile-b:discord:42",
        packet={
            "trigger_event_id": "discord:message:2",
            "participant_id": "profile-b-participant",
        },
    )
    ticket_a = controller.tickets.consume_dispatch(
        "discord:message:2", "agent:profile-a:discord:42"
    )
    ticket_b = controller.tickets.consume_dispatch(
        "discord:message:2", "agent:profile-b:discord:42"
    )
    return _result("HM-01", {
        "same_loose_name_does_not_define_self": accepted_a.observation_disposition == "self-retained-no-wake",
        "other_exact_actor_remains_external": accepted_b.observation_disposition == "observed",
        "profile_participant_state_is_distinct": (
            a is not b
            and a.observation.participant_id == "profile-a-participant"
            and b.observation.participant_id == "profile-b-participant"
        ),
        "same_event_tickets_are_profile_session_scoped": (
            ticket_a is not None
            and ticket_b is not None
            and ticket_a.packet["participant_id"] == "profile-a-participant"
            and ticket_b.packet["participant_id"] == "profile-b-participant"
        ),
        "self_event_creates_no_opportunity": accepted_a.opportunity is None,
        "external_event_can_create_opportunity": accepted_b.opportunity is not None,
    }, metadata)


def _route_case(
    transport: Callable[..., Any] | None,
    *,
    preattention: bool = True,
    error_action: str = "WAKE",
    participant_action: str = "message",
):
    event = _hermes_event()
    gateway = _Gateway(
        SimpleNamespace(_client=SimpleNamespace(user=SimpleNamespace(id=9001)))
    )
    key = v2.resolve_binding_key(event, gateway)
    controller = v2_plugin.HermesV2Controller(participant_id="resident")
    receipts: list[dict[str, Any]] = []
    participant_invocations = 0
    tool_next_calls = 0
    tool_denied = False
    with tempfile.TemporaryDirectory() as raw:
        path = _write_policy(
            Path(raw), key.continuity_scope_id,
            preattention=preattention, error_action=error_action,
        )
        result = controller.process_delivery(
            event=event,
            gateway=gateway,
            session_key="agent:default:discord:42",
            participant_id="resident",
            policy_loader=lambda: load_operator_policy(path),
            receipt_sink=receipts.append,
            classifier_transport=transport,
        )
        if result.status == "wake":
            ticket = controller.tickets.consume_dispatch(
                "discord:message:10", "agent:default:discord:42"
            )
            participant_invocations += 1

            def next_tool(arguments):
                nonlocal tool_next_calls
                tool_next_calls += 1
                return {"escaped": True}

            tool_token = controller.bind_tool_session(
                "agent:default:discord:42"
            )
            try:
                try:
                    controller.tool_execution(
                        tool_name="terminal",
                        arguments={"command": "printf forbidden"},
                        next_call=next_tool,
                    )
                except v2.HermesV2BoundaryError:
                    tool_denied = True
            finally:
                controller.reset_tool_session(tool_token)
            content = "direct participant contribution" if participant_action == "message" else None
            controller.complete_participant_turn(
                "agent:default:discord:42", content
            )
            if content is not None:
                controller.complete_transport(
                    "agent:default:discord:42", delivery="sent"
                )
        else:
            ticket = None
    return result.evaluation, receipts, {
        "participant_invocations": participant_invocations,
        "ticket": ticket,
        "tool_denied": tool_denied,
        "tool_next_calls": tool_next_calls,
        "stages": [receipt["stage"] for receipt in receipts],
        "participant_action": participant_action,
    }


def _hm02(metadata):
    calls = {"suppress": 0, "wake": 0, "defer": 0, "margin": 0, "bypass": 0, "error": 0}

    def answer(name, payload):
        def transport(projection, config):
            calls[name] += 1
            if isinstance(payload, BaseException):
                raise payload
            row = copy.deepcopy(payload)
            row.setdefault("evidence_event_ids", [projection["trigger_event_id"]])
            return row
        return transport

    suppress, _, suppress_metrics = _route_case(answer("suppress", {
        "disposition": "SUPPRESS",
        "reasons": ["no contribution"],
        "legacy_verdict_confidences": {"PASS": 0.99, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.01},
    }))
    wake, _, wake_metrics = _route_case(answer("wake", {
        "disposition": "WAKE", "reasons": ["contribute"]
    }))
    defer, defer_receipts, defer_metrics = _route_case(answer("defer", {
        "disposition": "DEFER", "reasons": ["uncertain"]
    }), participant_action="silence")
    margin, _, margin_metrics = _route_case(answer("margin", {
        "disposition": "SUPPRESS",
        "reasons": ["transition margin"],
        "legacy_verdict_confidences": {"PASS": 0.55, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.45},
    }))
    bypass, bypass_receipts, bypass_metrics = _route_case(
        answer("bypass", {"disposition": "WAKE", "reasons": ["must not run"]}),
        preattention=False,
        participant_action="silence",
    )
    error, _, error_metrics = _route_case(
        answer("error", RuntimeError("offline classifier failure"))
    )
    sources = {
        "wake": wake.packet["attention"]["source"],
        "defer": defer.packet["attention"]["source"],
        "margin": margin.packet["attention"]["source"],
        "bypass": bypass.packet["attention"]["source"],
        "error": error.packet["attention"]["source"],
    }
    return _result("HM-02", {
        "suppress_invokes_zero_turns": (
            suppress.status == "suppressed"
            and suppress.packet is None
            and suppress_metrics["participant_invocations"] == 0
            and suppress_metrics["stages"] == ["observation", "attention"]
        ),
        "wake_closes_message_turn_and_transport": (
            sources["wake"] == "WAKE"
            and wake_metrics["participant_invocations"] == 1
            and wake_metrics["stages"]
            == ["observation", "attention", "participant-host", "transport"]
        ),
        "classifier_defer_can_end_in_silence": (
            sources["defer"] == "DEFER"
            and defer_metrics["stages"]
            == ["observation", "attention", "participant-host"]
            and defer_receipts[-1]["body"]["outcome"] == "silent"
        ),
        "margin_defer_invokes_one_turn": (
            sources["margin"] == "DEFER"
            and margin_metrics["participant_invocations"] == 1
        ),
        "bypass_invokes_one_silent_turn_without_classifier": (
            sources["bypass"] == "PREATTENTION_BYPASS"
            and calls["bypass"] == 0
            and bypass_metrics["participant_invocations"] == 1
            and bypass_receipts[-1]["body"]["outcome"] == "silent"
        ),
        "error_fallback_invokes_and_closes_one_turn": (
            sources["error"] == "ERROR_FALLBACK"
            and error_metrics["stages"][-2:] == ["participant-host", "transport"]
        ),
        "ticketed_tools_fail_closed_on_every_wake_route": all(
            metrics["tool_denied"] and metrics["tool_next_calls"] == 0
            for metrics in (
                wake_metrics, defer_metrics, margin_metrics,
                bypass_metrics, error_metrics,
            )
        ),
        "one_call_per_attention_opportunity": calls == {"suppress": 1, "wake": 1, "defer": 1, "margin": 1, "bypass": 0, "error": 1},
    }, metadata)


def _hm03(metadata):
    key = v2.BindingKey("default", "discord", "discord:user:9001", "discord:channel:42")
    first = v2.BindingState(key=key, participant_id="resident")
    accepted = first.accept(_native("discord:message:20"))
    receipts = []
    with tempfile.TemporaryDirectory() as directory:
        policy_path = _write_policy(Path(directory), key.continuity_scope_id)
        evaluation = v2_plugin.HermesV2Controller(
            participant_id="resident"
        ).evaluate_opportunity(
            binding=first,
            opportunity=accepted.opportunity,
            policy_loader=lambda: load_operator_policy(policy_path),
            receipt_sink=receipts.append,
            classifier_transport=lambda projection, classifier: {
                "disposition": "SUPPRESS",
                "reasons": ["no contribution is useful"],
                "evidence_event_ids": [projection["trigger_event_id"]],
                "legacy_verdict_confidences": {
                    "PASS": 0.99, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.01,
                },
            },
        )
        context = first.export_context()
    restarted = v2.BindingState(key=key, participant_id="resident")
    restarted.restore_context(context)
    restored_ids = [row["event"]["id"] for row in restarted.export_context()]
    return _result("HM-03", {
        "classifier_suppress_is_exercised": (
            evaluation.status == "suppressed"
            and evaluation.decision["effective_disposition"] == "SUPPRESS"
            and [row["stage"] for row in receipts] == ["observation", "attention"]
        ),
        "earlier_event_remains_observable": restored_ids == ["discord:message:20"],
        "suppression_completes_scheduler_work": first.scheduler.snapshot() == (),
        "restart_has_no_scheduler_work": restarted.scheduler.snapshot() == (),
        "restart_gap_is_honest": restarted.observation.has_restart_gap is True,
        "continuity_is_session_only": restarted.observation.continuity == "session-only",
    }, metadata)


def _hm04(metadata):
    controller = v2_plugin.HermesV2Controller(participant_id="resident")
    key_a = v2.BindingKey("profile-a", "discord", "discord:user:9001", "discord:channel:77")
    key_b = v2.BindingKey("profile-b", "discord", "discord:user:9002", "discord:channel:77")
    a = controller.registry_for("participant-a").get_or_create(key_a)
    b = controller.registry_for("participant-b").get_or_create(key_b)
    human_a = _native(
        "discord:message:30", author="discord:user:1001",
        mentions=("discord:user:9002",),
    )
    human_b = _native(
        "discord:message:31", author="discord:user:1002",
        mentions=("discord:user:9001",),
    )
    for native in (human_a, human_b):
        a.accept_context(native)
        b.accept_context(native)
    candidate = _native(
        "discord:message:32", author="discord:user:1001",
        mentions=("discord:user:9002",),
    )
    aa = a.accept(candidate)
    bb = b.accept(candidate)
    receipts_a, receipts_b = [], []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path_a = _write_policy(
            root / "a", key_a.continuity_scope_id,
            participant_id="participant-a",
        )
        path_b = _write_policy(
            root / "b", key_b.continuity_scope_id,
            participant_id="participant-b",
        )
        decision_a = controller.evaluate_opportunity(
            binding=a,
            opportunity=aa.opportunity,
            policy_loader=lambda: load_operator_policy(path_a),
            receipt_sink=receipts_a.append,
            classifier_transport=lambda projection, classifier: {
                "disposition": "SUPPRESS",
                "reasons": ["participant a has no useful contribution"],
                "evidence_event_ids": [projection["trigger_event_id"]],
                "legacy_verdict_confidences": {
                    "PASS": 0.99, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.01,
                },
            },
        )
        decision_b = controller.evaluate_opportunity(
            binding=b,
            opportunity=bb.opportunity,
            policy_loader=lambda: load_operator_policy(path_b),
            receipt_sink=receipts_b.append,
            classifier_transport=lambda projection, classifier: {
                "disposition": "WAKE",
                "reasons": ["participant b is directly addressed"],
                "evidence_event_ids": [projection["trigger_event_id"]],
            },
        )
    return _result("HM-04", {
        "two_humans_are_retained_for_two_participants": all(
            {"discord:user:1001", "discord:user:1002"}
            <= {row["event"]["author_id"] for row in state.export_context()}
            for state in (a, b)
        ),
        "participant_specific_decisions_are_exercised": (
            decision_a.status == "suppressed"
            and decision_b.status == "wake"
            and decision_b.packet["self"]["participant_id"] == "participant-b"
        ),
        "direct_mention_remains_exact": (
            b.export_context()[-1]["event"]["mentioned_actor_ids"]
            == ["discord:user:9002"]
        ),
        "room_and_participant_state_are_not_shared": (
            a.observation is not b.observation
            and a.observation.participant_id == "participant-a"
            and b.observation.participant_id == "participant-b"
        ),
        "attention_receipts_are_participant_local": (
            receipts_a[-1]["body"]["effective_disposition"] == "SUPPRESS"
            and receipts_b[-1]["body"]["effective_disposition"] == "WAKE"
        ),
        "scene_is_labelled_synthetic": metadata["HM-04"]["evidence_grade"] == "deterministic-synthetic-not-live",
    }, metadata)


def _hm05(metadata):
    source = SimpleNamespace(
        profile="default", platform=_Platform("telegram"), chat_id="-10042",
        thread_id="7", user_id="1001", user_name="Zoe", is_bot=False,
    )
    event = SimpleNamespace(
        source=source,
        message_id="55",
        text="OtherAgent thoughts?",
        reply_to_message_id="54",
        timestamp=datetime(2026, 7, 20, 19, 5, tzinfo=timezone.utc),
        internal=False,
        raw_message=SimpleNamespace(
            message_id=55,
            date=datetime(2026, 7, 20, 19, 5, tzinfo=timezone.utc),
            chat=SimpleNamespace(id=-10042, type="supergroup", title="Shared"),
            from_user=SimpleNamespace(
                id=1001, is_bot=False, first_name="Zoe", username="zoe"
            ),
            text="OtherAgent thoughts?",
            message_thread_id=7,
            entities=[SimpleNamespace(
                type="text_mention", offset=0, length=10,
                user=SimpleNamespace(id=2002, is_bot=True, first_name="OtherAgent"),
            )],
            reply_to_message=SimpleNamespace(message_id=54),
        ),
        platform_update_id=700,
    )
    adapter = SimpleNamespace(_bot=SimpleNamespace(id=9001))
    key = v2.resolve_binding_key(event, _Gateway(adapter))
    projected = v2.project_native_event(event, key)
    native_update = v2._telegram_update(event)
    equivalent = v2.project_native_event(
        SimpleNamespace(
            source=source,
            message_id="55",
            text="OtherAgent thoughts?",
            raw_message=native_update,
            internal=False,
        ),
        key,
    )
    absent = v2.project_native_event(
        SimpleNamespace(
            source=source,
            message_id="56",
            text="plain text",
            platform_update_id=701,
            internal=False,
            raw_message=SimpleNamespace(
                message_id=56,
                date=None,
                chat=SimpleNamespace(id=-10042),
                from_user=SimpleNamespace(id=1001, is_bot=False),
                text="plain text",
                entities=[],
                reply_to_message=None,
            ),
        ),
        key,
    )
    return _result("HM-05", {
        "native_bot_id_binds_self": key.self_actor_id == "telegram:user:9001",
        "topic_is_part_of_room_scope": key.room_scope_id == "telegram:chat:-10042:topic:7",
        "native_message_id_is_preserved": projected["event"]["id"] == "telegram:message:-10042:55",
        "ptb_text_mention_is_preserved": projected["event"]["mentioned_actor_ids"] == ["telegram:user:2002"],
        "ptb_reply_is_preserved": projected["event"]["reply_to_event_id"] == "telegram:message:-10042:54",
        "ptb_datetime_is_preserved": projected["event"]["timestamp"] == "2026-07-20T19:05:00Z",
        "ptb_object_and_native_dict_normalize_equivalently": equivalent == projected,
        "unavailable_facts_remain_absent": (
            absent["event"]["mentioned_actor_ids"] == []
            and "reply_to_event_id" not in absent["event"]
            and "timestamp" not in absent["event"]
        ),
        "scene_is_labelled_synthetic": metadata["HM-05"]["evidence_grade"] == "deterministic-synthetic-not-live",
    }, metadata)


def _hm06(metadata, hermes_source: Path):
    pyproject = tomllib.loads((hermes_source / "pyproject.toml").read_text())
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=hermes_source,
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    gateway = (hermes_source / "gateway" / "run.py").read_text()
    authorization = (hermes_source / "gateway" / "authz_mixin.py").read_text()
    base = (hermes_source / "gateway" / "platforms" / "base.py").read_text()
    discord = (hermes_source / "plugins" / "platforms" / "discord" / "adapter.py").read_text()
    telegram = (hermes_source / "plugins" / "platforms" / "telegram" / "adapter.py").read_text()
    middleware = (hermes_source / "hermes_cli" / "middleware.py").read_text()
    manifest = (PLUGIN_DIR / "plugin.yaml").read_text()
    candidate_plugin = (PLUGIN_DIR / "v2_plugin.py").read_text()
    probe_code = (
        "import importlib.util,sys; from pathlib import Path; "
        f"root=Path({str(ROOT)!r}); "
        "sys.path.insert(0,str(root)); sys.path.insert(0,str(root/'src')); "
        "path=root/'integrations/hermes/nunchi-gate/v2_plugin.py'; "
        "spec=importlib.util.spec_from_file_location('nunchi_v2_hm06_probe',path); "
        "module=importlib.util.module_from_spec(spec); "
        "sys.modules[spec.name]=module; spec.loader.exec_module(module); "
        "module.configure(config_loader=lambda event,gateway:{},participant_id='probe'); "
        "ctx=type('C',(),{'register_hook':lambda self,n,c:None,"
        "'register_middleware':lambda self,n,c:None})(); module.register(ctx); "
        "print('installed-register-pass')"
    )
    probe = subprocess.run(
        [str(hermes_source / "venv/bin/python"), "-c", probe_code],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return _result("HM-06", {
        "installed_version_is_pinned": pyproject["project"]["version"] == EXPECTED_HERMES_VERSION,
        "installed_commit_is_pinned": commit == EXPECTED_HERMES_COMMIT,
        "whole_turn_seam_exists": "async def _handle_message_with_agent(" in gateway,
        "busy_admission_seam_exists": "def set_busy_session_handler(" in base,
        "whole_adapter_process_seam_exists": "async def _process_message_background(" in base,
        "terminal_output_seams_exist": all(
            token in base for token in (
                "async def _send_with_retry(",
                "async def send_multiple_images(",
                "async def send_clarify(",
                "async def send_private_notice(",
                "async def send_voice(",
                "async def send_video(",
                "async def send_document(",
            )
        ),
        "authorization_seam_exists": "def _is_user_authorized(" in authorization,
        "discord_raw_dispatch_boundary_exists": "async def on_message(" in discord,
        "discord_control_authorization_boundary_exists": all(
            token in discord for token in (
                "def _evaluate_slash_authorization(",
                "async def _check_slash_authorization(",
            )
        ),
        "telegram_ptb_message_boundary_exists": (
            "effective_message" in telegram
            and "def _enqueue_text_event(" in telegram
        ),
        "effective_session_runtime_and_normalization_seams_exist": all(
            token in gateway for token in (
                "def _resolve_session_agent_runtime(",
                "def _normalize_source_for_session_key(",
            )
        ),
        "tool_execution_middleware_exists": "def run_tool_execution_middleware(" in middleware,
        "candidate_wraps_busy_process_output_and_raw_discord": all(
            token in candidate_plugin for token in (
                "set_busy_session_handler",
                "_process_message_background",
                "assert_terminal_output_allowed",
                "install_discord_control_guard",
                "install_discord_raw_observer",
                "_gateway_authorizes_event",
                "_DeliveryCancellation",
                "discard_pending=True",
                "install_telegram_exact_text",
                "_nunchi_v2_raw_content",
                "_DISCORD_NO_AUTO_THREAD",
                "attest_participant_turn",
                "_resolve_session_agent_runtime",
                "send_draft",
                "send_clarify",
                "send_private_notice",
                "_host_effect_runtime_supported",
            )
        ),
        "candidate_registers_required_wrappers_against_installed_classes": (
            probe.returncode == 0 and "installed-register-pass" in probe.stdout
        ),
        "plugin_declares_v2_hook": "- pre_llm_call" in manifest,
        "plugin_declares_action_middleware": "- tool_execution" in manifest,
    }, metadata)


def run_all(*, hermes_source: Path) -> list[dict[str, Any]]:
    metadata = _metadata()
    return [
        _hm01(metadata),
        _hm02(metadata),
        _hm03(metadata),
        _hm04(metadata),
        _hm05(metadata),
        _hm06(metadata, Path(hermes_source)),
    ]


def write_results(path: Path, *, hermes_source: Path) -> list[dict[str, Any]]:
    rows = run_all(hermes_source=hermes_source)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic Hermes V2 HM-01 through HM-06 scenes")
    parser.add_argument("--hermes-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)
    rows = write_results(args.output, hermes_source=args.hermes_source)
    failed = [row["hm_case_id"] for row in rows if row["result"] != "PASS"]
    for row in rows:
        print(f"{row['hm_case_id']} {row['result']} {row['scene_id']}")
    if args.require_complete and (len(rows) != 6 or failed):
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
