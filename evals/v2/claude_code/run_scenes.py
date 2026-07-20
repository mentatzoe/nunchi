"""Deterministic CC-scene replay for the Claude Code V2 integration.

Replays the CC-01 fixture hearing, the CC-02 Station scar corpus, the CC-03
attention routing matrix (including trusted bypass and forged bypass), the
CC-04 act-or-silence receipt paths, and the CC-05 later-hearing/restart
cases through the real gate module with injected classifier seams, asserting
every expectation and emitting one evidence row per case with its stable
``scene_id``. Bypass and receipt rows carry the request ID, stage owners,
trusted provenance, and ``classifier_not_invoked``.

Rows produced here are ``mode: deterministic-replay``. Live rows are appended
separately by the live evidence session and never rewrite these.

Invoke from the repository root:

    PYTHONPATH=src:. python3 -m evals.v2.claude_code.run_scenes \
        --out-dir evidence/v2/claude-code
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.v2 import claude_code_helpers as helpers  # noqa: E402

EVAL_DIR = REPO_ROOT / "evals" / "v2" / "claude_code"


class _Ctx:
    """One isolated gate context (fresh state, policy, receipts, sidecar)."""

    def __init__(self, **attention_overrides):
        self.tmp = Path(tempfile.mkdtemp(prefix="nunchi-cc-scenes-"))
        self.tmp.chmod(0o700)
        self.module = helpers.load_gate_module()
        document = helpers.claude_policy_document(self.tmp, **attention_overrides)
        self.environ = helpers.make_environ(
            self.tmp, policy_path=helpers.write_claude_policy(self.tmp, document)
        )
        self._ts = 0

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def next_ts(self) -> str:
        self._ts += 1
        return f"2026-07-20T12:{self._ts // 60:02d}:{self._ts % 60:02d}Z"

    def deliver(self, transport, *, message_id, session_id="sess-e1", **row_kwargs):
        ts = row_kwargs.pop("ts", None) or self.next_ts()
        helpers.append_sidecar(
            self.environ,
            helpers.sidecar_row(message_id=message_id, timestamp=ts, **row_kwargs),
        )
        payload = helpers.prompt_payload(
            helpers.channel_prompt(
                message_id=message_id,
                body=row_kwargs.get("content", "hello room"),
                ts=ts,
            ),
            session_id=session_id,
        )
        return self.module.handle_user_prompt_submit(
            payload, self.environ, classifier_transport=transport
        )

    def stop(self, transport, *, session_id="sess-e1"):
        return self.module.handle_stop(
            {"session_id": session_id}, self.environ, classifier_transport=transport
        )

    def post_tool(self, tool_input, *, tool_name="mcp__discord__reply", ok=True, session_id="sess-e1"):
        return self.module.handle_post_tool(
            {
                "session_id": session_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_response": {"ok": True} if ok else {"isError": True},
            },
            self.environ,
        )

    def stages(self, request_id):
        return helpers.receipts_for(self.tmp, request_id)


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise AssertionError(detail)


def _load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def cc01_rows() -> list[dict]:
    fixtures = json.loads(
        (
            REPO_ROOT / "tests" / "fixtures" / "v2" / "claude_code" / "native_events.json"
        ).read_text(encoding="utf-8")
    )
    ctx = _Ctx()
    try:
        row = fixtures["allowlisted_bot_message"]["sidecar"]
        transport = helpers.CountingTransport(helpers.wake_judgment)
        helpers.append_sidecar(ctx.environ, row)
        decision = ctx.module.handle_user_prompt_submit(
            helpers.prompt_payload(
                helpers.channel_prompt(
                    message_id=row["message_id"],
                    user=row["author"]["username"],
                    body=row["content"],
                    ts=row["timestamp"],
                )
            ),
            ctx.environ,
            classifier_transport=transport,
        )
        packet = helpers.wake_packet_from_context(decision.output)
        trigger = next(
            event for event in packet["events"] if event["id"] == packet["trigger_event_id"]
        )
        author = f"discord:user:{row['author']['id']}"
        _require(trigger["author_id"] == author, "bot author identity was not exact")
        _require(trigger["text"] == row["content"], "bot content was not literal")
        _require(
            packet["actors"][author]["kind"] == "bot",
            "bot actor kind was not preserved",
        )
        request_id = helpers.wake_request_id(decision.output)
        return [
            {
                "scene_id": "CC-01",
                "s_ids": ["S01", "S02"],
                "case": "allowlisted-bot-message-heard-with-exact-native-facts",
                "mode": "deterministic-replay",
                "request_id": request_id,
                "classifier_calls": transport.call_count,
                "trigger_author": author,
                "delivery": "hook-injected fixture; live reactive rows are appended by the live session",
                "result": "PASS",
            }
        ]
    finally:
        ctx.close()


def cc02_rows() -> list[dict]:
    rows = []
    scars = [
        row
        for row in _load_jsonl(EVAL_DIR / "scenes.jsonl")
        if row.get("scene_id") == "CC-02" and "scar" in row
    ]
    _require(len(scars) >= 5, "Station scar corpus is incomplete")
    for index, scene in enumerate(scars):
        ctx = _Ctx()
        try:
            transport = helpers.CountingTransport(helpers.wake_judgment)
            decision = ctx.deliver(
                transport,
                message_id=f"61000000000000000{index:02d}",
                author_id=scene["author_id"],
                bot=scene["author_kind"] == "bot",
                content=scene["body"],
                mention_user_ids=tuple(scene.get("mention_user_ids", ())),
            )
            _require(decision.output is not None, "scar produced no hook output")
            _require(
                "hookSpecificOutput" in decision.output,
                f"scar {scene['scar']} was deterministically silenced",
            )
            _require(transport.call_count == 1, "scar did not make one classifier call")
            projection = transport.calls[0]
            trigger = next(
                event
                for event in projection["events"]
                if event["id"] == projection["trigger_event_id"]
            )
            _require(trigger["text"] == scene["body"], "scar facts were not literal")
            rows.append(
                {
                    "scene_id": "CC-02",
                    "s_ids": scene["s_ids"],
                    "case": f"station-scar-{scene['scar']}",
                    "mode": "deterministic-replay",
                    "request_id": helpers.wake_request_id(decision.output),
                    "classifier_calls": transport.call_count,
                    "deterministic_suppressor": "none",
                    "result": "PASS",
                }
            )
        finally:
            ctx.close()
    return rows


def cc03_rows() -> list[dict]:
    rows = []

    # Ordinary WAKE: one engine invocation, one logical classifier call.
    ctx = _Ctx()
    try:
        transport = helpers.CountingTransport(helpers.wake_judgment)
        decision = ctx.deliver(transport, message_id="6200000000000000001")
        request_id = helpers.wake_request_id(decision.output)
        stages = ctx.stages(request_id)
        _require(transport.call_count == 1, "WAKE did not make one classifier call")
        _require(
            set(stages) == {"observation", "attention"},
            "pre-turn stages were not observation+attention",
        )
        rows.append(
            {
                "scene_id": "CC-03",
                "s_ids": ["S06"],
                "case": "ordinary-wake-one-engine-invocation-one-classifier-call",
                "mode": "deterministic-replay",
                "request_id": request_id,
                "classifier_calls": transport.call_count,
                "stage_owner": {s: stages[s]["writer"] for s in sorted(stages)},
                "result": "PASS",
            }
        )
    finally:
        ctx.close()

    # Effective SUPPRESS stops only the wake; the event stays retained.
    ctx = _Ctx()
    try:
        transport = helpers.CountingTransport(helpers.suppress_judgment)
        decision = ctx.deliver(transport, message_id="6200000000000000002")
        _require(decision.output.get("decision") == "block", "SUPPRESS did not stop the turn")
        _require(transport.call_count == 1, "SUPPRESS did not come from one model call")
        later = helpers.CountingTransport(helpers.wake_judgment)
        wake = ctx.deliver(later, message_id="6200000000000000003")
        packet = helpers.wake_packet_from_context(wake.output)
        _require(
            "discord:message:6200000000000000002"
            in [event["id"] for event in packet["events"]],
            "suppressed event was not retained for later hearing",
        )
        rows.append(
            {
                "scene_id": "CC-03",
                "s_ids": ["S05"],
                "case": "effective-suppress-stops-wake-and-retains-event",
                "mode": "deterministic-replay",
                "classifier_calls": transport.call_count,
                "result": "PASS",
            }
        )
    finally:
        ctx.close()

    # Classifier-DEFER vs margin-DEFER: distinct valves, both wake.
    for case, factory, valve in (
        ("classifier-defer-widens", helpers.defer_judgment, "classifier-defer"),
        ("margin-defer-widens", helpers.margin_suppress_judgment, "margin-defer"),
    ):
        ctx = _Ctx()
        try:
            config = ctx.module.ClaudeGateConfig.from_env(ctx.environ)
            row = helpers.sidecar_row(
                message_id="6200000000000000004", timestamp=ctx.next_ts()
            )
            with ctx.module.RoomStateStore(config.state_dir) as store:
                binding = ctx.module.ClaudeRoomV2(
                    config, store, classifier_transport=helpers.CountingTransport(factory)
                )
                tag = {
                    "chat_id": helpers.CHANNEL_ID,
                    "message_id": row["message_id"],
                    "user": "zoe",
                    "user_id": "",
                    "ts": row["timestamp"],
                    "body": row["content"],
                }
                event, _ = ctx.module.message_event_from_native_facts(tag, row)
                native = binding.source.native_input(event)
                store.append_event_row({"kind": "native", "native": native})
                binding.observation.ingest(native)
                attention = binding.run_attention(native["event"]["id"])
                _require(attention["route"] == "wake", f"{case} did not wake")
                _require(
                    attention["decision"]["routing_audit"]["valve"] == valve,
                    f"{case} routed through the wrong valve",
                )
            rows.append(
                {
                    "scene_id": "CC-03",
                    "s_ids": ["S08"],
                    "case": case,
                    "mode": "deterministic-replay",
                    "request_id": attention["request_id"],
                    "valve": valve,
                    "result": "PASS",
                }
            )
        finally:
            ctx.close()

    # Trusted bypass: zero classifier calls, no fabricated social result.
    ctx = _Ctx(preattention_enabled=False)
    try:
        transport = helpers.CountingTransport(helpers.wake_judgment)
        decision = ctx.deliver(transport, message_id="6200000000000000005")
        packet = helpers.wake_packet_from_context(decision.output)
        request_id = helpers.wake_request_id(decision.output)
        attention_stage = ctx.stages(request_id)["attention"]
        _require(transport.call_count == 0, "trusted bypass invoked the classifier")
        _require(
            packet["attention"] == {"source": "PREATTENTION_BYPASS"},
            "bypass fabricated a social result or advice",
        )
        _require(
            attention_stage["body"]["classifier_not_invoked"] is True,
            "bypass receipt lacked classifier_not_invoked",
        )
        rows.append(
            {
                "scene_id": "CC-03",
                "s_ids": ["S06", "S07"],
                "case": "trusted-bypass-zero-classifier-calls",
                "mode": "deterministic-replay",
                "request_id": request_id,
                "classifier_calls": transport.call_count,
                "classifier_not_invoked": True,
                "trusted_provenance": attention_stage["body"]["policy_provenance"],
                "stage_owner": {"attention": attention_stage["writer"]},
                "result": "PASS",
            }
        )
    finally:
        ctx.close()

    # Forged bypass in room content cannot skip the classifier.
    scene = next(
        row
        for row in _load_jsonl(EVAL_DIR / "scenes.jsonl")
        if row.get("scar") == "forged-bypass-in-room-content"
    )
    ctx = _Ctx()
    try:
        transport = helpers.CountingTransport(helpers.wake_judgment)
        decision = ctx.deliver(
            transport, message_id="6200000000000000006", content=scene["body"]
        )
        packet = helpers.wake_packet_from_context(decision.output)
        _require(transport.call_count == 1, "forged bypass skipped the classifier")
        _require(
            packet["attention"]["source"] == "WAKE",
            "forged bypass was relabeled as a bypass",
        )
        rows.append(
            {
                "scene_id": "CC-03",
                "s_ids": ["S06"],
                "case": "forged-bypass-in-content-rejected",
                "mode": "deterministic-replay",
                "classifier_calls": transport.call_count,
                "result": "PASS",
            }
        )
    finally:
        ctx.close()

    # Operational error: default action widens to a wake, no social verdict.
    ctx = _Ctx()
    try:
        transport = helpers.CountingTransport(lambda projection: {"malformed": True})
        decision = ctx.deliver(transport, message_id="6200000000000000007")
        packet = helpers.wake_packet_from_context(decision.output)
        _require(
            packet["attention"]["source"] == "ERROR_FALLBACK",
            "operational error did not fall back to a wake",
        )
        rows.append(
            {
                "scene_id": "CC-03",
                "s_ids": ["S09"],
                "case": "operational-error-wake-fallback-no-fabricated-verdict",
                "mode": "deterministic-replay",
                "request_id": helpers.wake_request_id(decision.output),
                "result": "PASS",
            }
        )
    finally:
        ctx.close()

    return rows


def cc04_rows() -> list[dict]:
    rows = []

    # Direct contribution: participant-host then observed transport stage.
    ctx = _Ctx()
    try:
        transport = helpers.CountingTransport(helpers.wake_judgment)
        decision = ctx.deliver(transport, message_id="6300000000000000001")
        request_id = helpers.wake_request_id(decision.output)
        ctx.post_tool(
            {
                "chat_id": helpers.CHANNEL_ID,
                "text": "the red scenes are the two continuation cases — rerunning now",
                "reply_to": "6300000000000000001",
            }
        )
        _require(ctx.stop(transport).output is None, "stop did not complete the turn")
        stages = ctx.stages(request_id)
        _require(
            stages["participant-host"]["body"]["outcome"] == "sent",
            "act path host outcome was not sent",
        )
        _require(
            stages["transport"]["body"]["delivery"] == "sent",
            "observed delivery was not attested",
        )
        rows.append(
            {
                "scene_id": "CC-04",
                "s_ids": ["S07", "S10"],
                "case": "direct-contribution-message",
                "mode": "deterministic-replay",
                "request_id": request_id,
                "stage_owner": {s: stages[s]["writer"] for s in sorted(stages)},
                "send_time_social_calls": 0,
                "result": "PASS",
            }
        )
    finally:
        ctx.close()

    # Silence: a valid outcome; no transport stage is fabricated.
    ctx = _Ctx()
    try:
        transport = helpers.CountingTransport(helpers.wake_judgment)
        decision = ctx.deliver(transport, message_id="6300000000000000002")
        request_id = helpers.wake_request_id(decision.output)
        _require(ctx.stop(transport).output is None, "stop did not complete the turn")
        stages = ctx.stages(request_id)
        _require(
            stages["participant-host"]["body"]["outcome"] == "silent",
            "silent outcome was not recorded",
        )
        _require("transport" not in stages, "silence fabricated a transport stage")
        rows.append(
            {
                "scene_id": "CC-04",
                "s_ids": ["S07"],
                "case": "silence-is-a-valid-outcome",
                "mode": "deterministic-replay",
                "request_id": request_id,
                "stage_owner": {s: stages[s]["writer"] for s in sorted(stages)},
                "result": "PASS",
            }
        )
    finally:
        ctx.close()

    # Meta-answer grading is post-hoc evaluation, never a runtime filter.
    grading = [
        row
        for row in _load_jsonl(EVAL_DIR / "scenes.jsonl")
        if row.get("kind") == "meta-answer-grading"
    ]
    meta = next(row for row in grading if row["grade"] == "meta-answer")
    ctx = _Ctx()
    try:
        transport = helpers.CountingTransport(helpers.wake_judgment)
        decision = ctx.deliver(transport, message_id="6300000000000000003")
        request_id = helpers.wake_request_id(decision.output)
        ctx.post_tool({"chat_id": helpers.CHANNEL_ID, "text": meta["sent_text"]})
        ctx.stop(transport)
        stages = ctx.stages(request_id)
        _require(
            stages["participant-host"]["body"]["outcome"] == "sent",
            "runtime filtered or relabeled a meta-answer-shaped send",
        )
        rows.append(
            {
                "scene_id": "CC-04",
                "s_ids": ["S07", "S10"],
                "case": "meta-answer-graded-post-hoc-only",
                "mode": "deterministic-replay",
                "request_id": request_id,
                "post_hoc_grade": meta["grade"],
                "runtime_prose_filter": "none",
                "result": "PASS",
            }
        )
    finally:
        ctx.close()

    return rows


def cc05_rows() -> list[dict]:
    rows = []
    corpus = {row["case"]: row for row in _load_jsonl(EVAL_DIR / "recovery.jsonl")}

    # Burst coalescing: one fresh successor anchored at the newest event.
    ctx = _Ctx()
    try:
        transport = helpers.CountingTransport(helpers.wake_judgment)
        ctx.deliver(transport, message_id="6400000000000000001")
        _require(
            ctx.deliver(transport, message_id="6400000000000000002").output["decision"]
            == "block",
            "burst event was not coalesced",
        )
        _require(
            ctx.deliver(transport, message_id="6400000000000000003").output["decision"]
            == "block",
            "burst event was not coalesced",
        )
        stop_transport = helpers.CountingTransport(helpers.wake_judgment)
        successor = ctx.stop(stop_transport)
        packet = helpers.stop_packet_from_reason(successor.output)
        _require(
            packet["trigger_event_id"] == "discord:message:6400000000000000003",
            "successor was not anchored at the newest event",
        )
        _require(stop_transport.call_count == 1, "successor made extra classifier calls")
        rows.append(
            {
                "scene_id": "CC-05",
                "s_ids": corpus["burst-coalesces-to-one-fresh-successor"]["s_ids"],
                "case": "burst-coalesces-to-one-fresh-successor",
                "mode": "deterministic-replay",
                "request_id": packet["request_id"],
                "classifier_calls": stop_transport.call_count,
                "result": "PASS",
            }
        )
    finally:
        ctx.close()

    # Restart: pending anchors drop, retained context survives.
    ctx = _Ctx()
    try:
        transport = helpers.CountingTransport(helpers.wake_judgment)
        ctx.deliver(transport, message_id="6400000000000000004")
        ctx.deliver(transport, message_id="6400000000000000005")  # pending
        restart = helpers.CountingTransport(helpers.wake_judgment)
        decision = ctx.deliver(
            restart, message_id="6400000000000000006", session_id="sess-e2"
        )
        packet = helpers.wake_packet_from_context(decision.output)
        _require(
            packet["trigger_event_id"] == "discord:message:6400000000000000006",
            "restart resurrected a dead pending anchor",
        )
        event_ids = [event["id"] for event in packet["events"]]
        _require(
            "discord:message:6400000000000000004" in event_ids
            and "discord:message:6400000000000000005" in event_ids,
            "restart lost retained context",
        )
        _require(
            ctx.stop(restart, session_id="sess-e2").output is None,
            "restart fabricated a backlog turn",
        )
        rows.append(
            {
                "scene_id": "CC-05",
                "s_ids": ["S15", "S17"],
                "case": "restart-drops-pending-and-retains-context",
                "mode": "deterministic-replay",
                "request_id": packet["request_id"],
                "result": "PASS",
            }
        )
    finally:
        ctx.close()

    # Cold wake: honestly unsupported; recorded as a limitation, not replayed.
    rows.append(
        {
            "scene_id": "CC-05",
            "s_ids": corpus["cold-wake-honestly-unsupported"]["s_ids"],
            "case": "cold-wake-honestly-unsupported",
            "mode": "declared-limitation",
            "detail": corpus["cold-wake-honestly-unsupported"]["expectation"],
            "result": "DECLARED",
        }
    )
    return rows


# Committed evidence rows carry only deterministic semantic results. Run-
# variable identifiers (request IDs) and provenance digests (which embed the
# per-run temp-dir policy path) are stripped so the JSONL is reproducible
# byte-for-byte and `git diff --check` stays clean. Their presence is asserted
# at run time inside the scene bodies; only their run-specific VALUE is dropped.
_RUN_VARIABLE_KEYS = ("request_id", "trusted_provenance")


def _reproducible(row: dict[str, Any]) -> dict[str, Any]:
    out = {key: value for key, value in row.items() if key not in _RUN_VARIABLE_KEYS}
    if "trusted_provenance" in row:
        # Keep the deterministic fact (a trusted provenance was present and
        # bound to the receipt) without the run-variable digest value.
        out["trusted_provenance_present"] = True
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_scenes")
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    hearing_rows = cc01_rows()
    scene_rows = cc02_rows() + cc03_rows() + cc04_rows() + cc05_rows()
    if args.out_dir is not None:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        with (args.out_dir / "reactive-bot-hearing.jsonl").open("w", encoding="utf-8") as f:
            for row in hearing_rows:
                f.write(
                    json.dumps(_reproducible(row), ensure_ascii=False, sort_keys=True) + "\n"
                )
        with (args.out_dir / "scene-results.jsonl").open("w", encoding="utf-8") as f:
            for row in scene_rows:
                f.write(
                    json.dumps(_reproducible(row), ensure_ascii=False, sort_keys=True) + "\n"
                )
    total = len(hearing_rows) + len(scene_rows)
    passed = sum(1 for row in hearing_rows + scene_rows if row["result"] == "PASS")
    declared = sum(1 for row in hearing_rows + scene_rows if row["result"] == "DECLARED")
    print(f"cc-scenes: {total} rows, {passed} PASS, {declared} declared limitations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
