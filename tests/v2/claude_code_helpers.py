"""Shared fixtures for the Claude Code V2 integration tests.

The integration module lives at ``integrations/claude-code/nunchi_claude_v2.py``
(a hyphenated, non-package path), so it loads through ``importlib``. Policy
documents reuse the canonical security-helper shape rebound to the Claude
participant and room. All state, receipts, and sidecar files live inside the
test's temporary directory; nothing touches the operator's real ``~/.claude``.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Callable

from tests.v2.security.helpers import policy_document

CHANNEL_ID = "1000000000000000001"
SELF_USER_ID = "1000000000000000002"
HUMAN_ID = "1000000000000000003"
PEER_BOT_ID = "1000000000000000004"
OTHER_HUMAN_ID = "1000000000000000005"
PARTICIPANT_ID = "claude-station"

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "integrations"
    / "claude-code"
    / "nunchi_claude_v2.py"
)


def load_gate_module():
    import sys

    if "nunchi_claude_v2" in sys.modules:
        return sys.modules["nunchi_claude_v2"]
    spec = importlib.util.spec_from_file_location("nunchi_claude_v2", _MODULE_PATH)
    assert spec is not None and spec.loader is not None, f"missing {_MODULE_PATH}"
    module = importlib.util.module_from_spec(spec)
    # Register before exec: dataclass processing resolves cls.__module__
    # through sys.modules while the module body runs.
    sys.modules["nunchi_claude_v2"] = module
    spec.loader.exec_module(module)
    return module


def claude_policy_document(tmp: Path, **attention_overrides: Any) -> dict[str, Any]:
    document = policy_document()
    document["attention"]["participant_id"] = PARTICIPANT_ID
    document["attention"].update(attention_overrides)
    document["recoverability"] = {
        "participant_id": PARTICIPANT_ID,
        "continuity_scope_id": f"discord:channel:{CHANNEL_ID}",
        "eligible": True,
    }
    receipts = tmp / "receipts"
    receipts.mkdir(mode=0o700, exist_ok=True)
    document["receipt_sink"] = {
        "type": "exclusive-json-file",
        "directory": str(receipts),
        "source": "operator:test-receipts",
    }
    return document


def write_claude_policy(tmp: Path, document: dict[str, Any] | None = None) -> Path:
    path = tmp / "policy.json"
    path.write_text(
        json.dumps(document if document is not None else claude_policy_document(tmp)),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def make_environ(tmp: Path, *, policy_path: Path | None = None, **overrides: str) -> dict[str, str]:
    environ = {
        "NUNCHI_CLAUDE_V2_POLICY": str(policy_path or write_claude_policy(tmp)),
        "NUNCHI_CLAUDE_V2_STATE_DIR": str(tmp / "state"),
        "NUNCHI_CLAUDE_V2_CHANNEL_ID": CHANNEL_ID,
        "NUNCHI_CLAUDE_V2_SELF_USER_ID": SELF_USER_ID,
        "NUNCHI_CLAUDE_V2_PARTICIPANT_ID": PARTICIPANT_ID,
        "NUNCHI_CLAUDE_V2_PARTICIPANT_NAME": "Station",
        "NUNCHI_CLAUDE_V2_SIDECAR": str(tmp / "native-events.jsonl"),
    }
    environ.update(overrides)
    return environ


def sidecar_row(
    *,
    message_id: str,
    author_id: str = HUMAN_ID,
    username: str = "zoe",
    bot: bool = False,
    content: str = "hello room",
    timestamp: str = "2026-07-20T12:00:00Z",
    mention_user_ids: tuple[str, ...] = (),
    mention_everyone: bool = False,
    reply_to_message_id: str | None = None,
    channel_id: str = CHANNEL_ID,
    guild_id: str | None = "2000000000000000001",
) -> dict[str, Any]:
    return {
        "v": 1,
        "delivered_at": timestamp,
        "guild_id": guild_id,
        "channel_id": channel_id,
        "message_id": message_id,
        "author": {"id": author_id, "username": username, "bot": bot},
        "content": content,
        "timestamp": timestamp,
        "mention_user_ids": list(mention_user_ids),
        "mention_everyone": mention_everyone,
        "reply_to_message_id": reply_to_message_id,
    }


def append_sidecar(environ: dict[str, str], *rows: dict[str, Any]) -> None:
    path = Path(environ["NUNCHI_CLAUDE_V2_SIDECAR"])
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    # The hardened reader requires an owner-only regular file; the transport
    # writes 0600, so the fixture matches that contract.
    path.chmod(0o600)


def self_sidecar_row(
    *,
    message_id: str,
    content: str = "on it — checking the red scenes",
    timestamp: str = "2026-07-20T12:05:00Z",
) -> dict[str, Any]:
    """A self-authored native-fact record (retained context, never a wake)."""
    return sidecar_row(
        message_id=message_id,
        author_id=SELF_USER_ID,
        username="station",
        bot=True,
        content=content,
        timestamp=timestamp,
    )


def channel_prompt(
    *,
    message_id: str,
    user: str = "zoe",
    body: str = "hello room",
    chat_id: str = CHANNEL_ID,
    ts: str = "2026-07-20T12:00:00Z",
) -> str:
    return (
        f'<channel source="plugin:discord:discord" chat_id="{chat_id}" message_id="{message_id}"'
        f' user="{user}" ts="{ts}">{body}</channel>'
    )


def prompt_payload(prompt: str, *, session_id: str = "sess-1") -> dict[str, Any]:
    return {
        "session_id": session_id,
        "transcript_path": "",
        "hook_event_name": "UserPromptSubmit",
        "prompt": prompt,
        "cwd": "/tmp",
    }


class CountingTransport:
    """Deterministic classifier seam that records projections and counts calls."""

    def __init__(self, judgment_factory: Callable[[dict[str, Any]], dict[str, Any]]):
        self.judgment_factory = judgment_factory
        self.calls: list[dict[str, Any]] = []

    def __call__(self, projection: dict[str, Any], _config: Any) -> dict[str, Any]:
        self.calls.append(copy.deepcopy(projection))
        return self.judgment_factory(projection)

    @property
    def call_count(self) -> int:
        return len(self.calls)


def wake_judgment(projection: dict[str, Any]) -> dict[str, Any]:
    return {
        "disposition": "WAKE",
        "reasons": ["the room is addressing this participant"],
        "evidence_event_ids": [projection["trigger_event_id"]],
    }


def defer_judgment(projection: dict[str, Any]) -> dict[str, Any]:
    return {
        "disposition": "DEFER",
        "reasons": ["conversational meaning is uncertain"],
        "evidence_event_ids": [projection["trigger_event_id"]],
    }


def suppress_judgment(projection: dict[str, Any]) -> dict[str, Any]:
    """A confident suppression: gap 0.9-0.05 clears the 0.12 test margin."""
    return {
        "disposition": "SUPPRESS",
        "reasons": ["another participant is clearly addressed"],
        "evidence_event_ids": [projection["trigger_event_id"]],
        "legacy_verdict_confidences": {
            "PASS": 0.9,
            "ACK": 0.05,
            "ASK": 0.03,
            "SPEAK": 0.02,
        },
    }


def margin_suppress_judgment(projection: dict[str, Any]) -> dict[str, Any]:
    """An ambivalent suppression: gap 0.5-0.45 sits inside the 0.12 margin."""
    return {
        "disposition": "SUPPRESS",
        "reasons": ["probably not this participant's turn"],
        "evidence_event_ids": [projection["trigger_event_id"]],
        "legacy_verdict_confidences": {
            "PASS": 0.5,
            "ACK": 0.45,
            "ASK": 0.03,
            "SPEAK": 0.02,
        },
    }


def failing_transport(_projection: dict[str, Any], _config: Any) -> dict[str, Any]:
    raise TimeoutError("classifier provider timed out")


def read_receipts(tmp: Path) -> list[dict[str, Any]]:
    receipts_dir = tmp / "receipts"
    records: list[dict[str, Any]] = []
    if not receipts_dir.is_dir():
        return records
    for path in sorted(receipts_dir.iterdir()):
        if path.suffix != ".jsonl" or not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def receipts_for(tmp: Path, request_id: str) -> dict[str, dict[str, Any]]:
    by_stage: dict[str, dict[str, Any]] = {}
    for record in read_receipts(tmp):
        if record.get("request_id") == request_id:
            assert record["stage"] not in by_stage, "duplicate receipt stage"
            by_stage[record["stage"]] = record
    return by_stage


def wake_request_id(decision_output: dict[str, Any] | None) -> str:
    """Extract the request_id from an allow-with-context hook output."""
    assert decision_output is not None
    context = decision_output["hookSpecificOutput"]["additionalContext"]
    marker = "request_id="
    start = context.index(marker) + len(marker)
    return context[start:].split()[0].strip()


def wake_packet_from_context(decision_output: dict[str, Any] | None) -> dict[str, Any]:
    assert decision_output is not None
    context = decision_output["hookSpecificOutput"]["additionalContext"]
    brace = context.index("{")
    return json.loads(context[brace:])


def stop_packet_from_reason(decision_output: dict[str, Any] | None) -> dict[str, Any]:
    assert decision_output is not None
    reason = decision_output["reason"]
    brace = reason.index("{")
    return json.loads(reason[brace:])
