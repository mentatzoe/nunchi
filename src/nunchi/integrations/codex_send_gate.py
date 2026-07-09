#!/usr/bin/env python3
"""Codex PreToolUse hook: gate outbound room sends through nunchi-channel.

This is the Codex/Vigil parity guard for speaking into the room. The room
runner gates wakes before Codex starts; this hook re-checks supported outbound
send tool calls immediately before the message leaves Codex.

Supported by default:
  - MCP tool names ending in ``send_message`` or ``reply_message`` with
    ``channel_id``/``content`` or ``chat_id``/``text`` arguments.
  - Obvious direct Discord send commands in Bash, including channel-message
    API calls and webhook API calls, are denied outright; use the
    Nunchi-controlled MCP transport instead.

The hook expects the runner wake prompt to include a ``<nunchi_context>`` JSON
block on the latest user turn. Matching send calls without current context, or
after a prior room send for the same context, are denied. Gate errors deny by
default; set ``NUNCHI_HOOK_FAIL_POLICY=open`` only for an explicit local drill.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_AGENT_ID = os.environ.get("NUNCHI_HOOK_AGENT_ID", "agent")
_MENTION_ID = os.environ.get("NUNCHI_HOOK_MENTION_ID")
_FAIL_POLICY = os.environ.get("NUNCHI_HOOK_FAIL_POLICY", "closed").strip().lower()


def _env_int(name: str, default: int) -> int:
    try:
        parsed = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


_TIMEOUT = _env_int("NUNCHI_HOOK_TIMEOUT", 30)
_LOG_PATH = Path(
    os.environ.get("NUNCHI_RUNNER_LOG")
    or os.environ.get("NUNCHI_HOOK_LOG")
    or str(Path.home() / ".nunchi" / "codex-runner-receipts.jsonl")
)
_CHANNEL_BIN: str | None = os.environ.get("NUNCHI_CHANNEL_BIN") or shutil.which(
    "nunchi-channel"
)

_TOOL_RE = re.compile(
    os.environ.get("NUNCHI_HOOK_TOOL_PATTERN", r"(?:^|__)(?:send_message|reply_message)$")
)
_COMMAND_RE = re.compile(
    os.environ.get(
        "NUNCHI_HOOK_COMMAND_PATTERN",
        r"(?:discord(?:app)?\.com/api/(?:.*/channels/.*/messages|webhooks/)|nunchi-discord)",
    ),
    re.IGNORECASE,
)
_CONTEXT_RE = re.compile(r"<nunchi_context>\s*(.*?)\s*</nunchi_context>", re.DOTALL)
_VERDICTS = frozenset({"PASS", "ACK", "ASK", "SPEAK"})
_ALLOW_ACTIONS = frozenset({"allow-speak", "allow-ack", "allow-ask", "allow-gate-error"})


def _parse_aliases(raw: str | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        text = part.strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


_ALIASES = _parse_aliases(os.environ.get("NUNCHI_HOOK_ALIASES"))


def _agent_payload() -> dict:
    agent: dict = {"id": _AGENT_ID}
    if _MENTION_ID:
        agent["mention_id"] = _MENTION_ID
    aliases = [a for a in _ALIASES if a != _AGENT_ID and a != _MENTION_ID]
    if aliases:
        agent["aliases"] = aliases
    return agent


def _allow_output() -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        }
    )


def _deny_output(reason: str) -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    )


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def _iter_transcript_items(transcript_path: str):
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                item = obj.get("payload") if isinstance(obj.get("payload"), dict) else obj
                if isinstance(item.get("message"), dict):
                    item = {**item["message"], **{k: v for k, v in item.items() if k != "message"}}
                yield item
    except OSError:
        return


def _iter_transcript_texts(transcript_path: str):
    for item in _iter_transcript_items(transcript_path):
        if item.get("role") == "user":
            yield _content_text(item.get("content", ""))


def _parse_contexts(text: str):
    for match in _CONTEXT_RE.finditer(text):
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            yield parsed


def _extract_room_context_with_index(transcript_path: str) -> tuple[dict | None, int | None]:
    """Return a room context only when it is on the latest user turn."""
    latest_user_index: int | None = None
    latest_context: dict | None = None
    latest_context_index: int | None = None
    if not transcript_path:
        return None, None
    for index, item in enumerate(_iter_transcript_items(transcript_path)):
        if item.get("role") != "user":
            continue
        latest_user_index = index
        contexts = list(_parse_contexts(_content_text(item.get("content", ""))))
        if contexts:
            latest_context = contexts[-1]
            latest_context_index = index
    if latest_user_index is None or latest_context_index != latest_user_index:
        return None, None
    return latest_context, latest_context_index


def _extract_room_context(transcript_path: str) -> dict | None:
    context, _ = _extract_room_context_with_index(transcript_path)
    return context


def _send_args_from_item(item: dict) -> dict | None:
    candidates = [item]
    if isinstance(item.get("content"), list):
        candidates.extend(c for c in item["content"] if isinstance(c, dict))
    for cand in candidates:
        name = cand.get("name", "")
        if not isinstance(name, str) or not _TOOL_RE.search(name):
            continue
        args = cand.get("arguments", cand.get("input", cand.get("tool_input")))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                continue
        if isinstance(args, dict):
            return args
    return None


def _has_prior_allowed_send_receipt(
    *,
    session_id: str,
    channel_id: str,
    trigger: dict | None,
) -> bool:
    """Whether this exact admitted context already had an outbound send allowed.

    Codex writes the current function_call to the transcript before PreToolUse
    runs, so transcript shape alone cannot distinguish "current in-flight send"
    from "a send that already left the room." The hook receipt is the durable
    permission boundary we control: only a prior allow for the same
    session/channel/trigger suppresses another send.
    """
    trigger_id = trigger.get("message_id") if trigger else None
    if not trigger_id:
        return False
    try:
        with open(_LOG_PATH, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    record = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if record.get("direction") != "hook-outbound":
                    continue
                if record.get("action") not in _ALLOW_ACTIONS:
                    continue
                if str(record.get("session_id") or "") != session_id:
                    continue
                if str(record.get("channel") or "") != channel_id:
                    continue
                if str(record.get("trigger_message_id") or "") != str(trigger_id):
                    continue
                return True
    except OSError:
        return False
    return False


def _send_candidate(tool_name: str, tool_input: Any) -> dict | None:
    if tool_name == "Bash" and isinstance(tool_input, dict):
        command = tool_input.get("command")
        if isinstance(command, str) and _COMMAND_RE.search(command):
            return {"direct_command": True, "channel_id": "", "content": ""}
        return None
    if not _TOOL_RE.search(tool_name):
        return None
    if not isinstance(tool_input, dict):
        return None
    channel_id = tool_input.get("channel_id") or tool_input.get("chat_id")
    content = tool_input.get("content") if "content" in tool_input else tool_input.get("text")
    if channel_id is None or content is None:
        return None
    return {
        "direct_command": False,
        "channel_id": str(channel_id),
        "content": str(content),
        "message_id": str(tool_input.get("message_id") or ""),
    }


def _message(value: Any) -> dict | None:
    if not isinstance(value, dict):
        return None
    content = value.get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    return {
        "content": content,
        "author": str(value.get("author") or "unknown"),
        "author_kind": str(value.get("author_kind") or "human"),
        "message_id": str(value.get("message_id") or ""),
    }


def _history(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    out: list[dict] = []
    for item in value:
        msg = _message(item)
        if msg is not None:
            out.append(msg)
    return out


def _build_payload(context: dict, channel_id: str) -> tuple[dict | None, str | None]:
    surface = context.get("surface") if isinstance(context.get("surface"), dict) else {}
    context_channel = str(surface.get("channel_id") or "")
    if context_channel and context_channel != channel_id:
        return None, "Nunchi room context is for a different channel"
    trigger = _message(context.get("trigger"))
    if trigger is None:
        return None, "Nunchi room context is missing a valid trigger"
    return (
        {
            "trigger": trigger,
            "history": _history(context.get("history")),
            "agent": _agent_payload(),
            "surface": {"type": "channel", "channel_id": channel_id},
            "fail_policy": "raise",
        },
        None,
    )


def _write_receipt(
    *,
    session_id: str,
    channel_id: str,
    trigger: dict | None,
    history_len: int,
    verdict: str | None,
    action: str,
    elapsed_ms: float,
    reasons: list[str] | None = None,
    error: str | None = None,
) -> None:
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        record: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "direction": "hook-outbound",
            "session_id": session_id,
            "channel": channel_id,
            "trigger_message_id": trigger.get("message_id") if trigger else None,
            "verdict": verdict,
            "action": action,
            "history_len": history_len,
            "elapsed_ms": round(elapsed_ms, 1),
            "reasons": (reasons or [])[:3],
        }
        if error:
            record["error"] = error
        with open(_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass


def _call_gate(payload: dict) -> tuple[dict | None, str | None]:
    if not _CHANNEL_BIN:
        return None, "nunchi-channel not found; check NUNCHI_CHANNEL_BIN or install nunchi"
    try:
        result = subprocess.run(
            [_CHANNEL_BIN],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return None, f"nunchi-channel timed out after {_TIMEOUT}s"
    except OSError as exc:
        return None, f"failed to run nunchi-channel: {exc}"
    if result.returncode != 0:
        return None, (result.stderr or "").strip() or f"nunchi-channel exited {result.returncode}"
    try:
        directive = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        return None, f"nunchi-channel returned invalid JSON: {exc}"
    if not isinstance(directive, dict):
        return None, "nunchi-channel returned a malformed directive"
    verdict = directive.get("verdict")
    if verdict not in _VERDICTS:
        return None, "nunchi-channel returned a malformed directive"
    if "silent" in directive and bool(directive.get("silent")) != (verdict == "PASS"):
        return None, "nunchi-channel returned a contradictory silent flag"
    return directive, None


def _deny_and_log(
    *,
    session_id: str,
    channel_id: str,
    trigger: dict | None,
    history_len: int,
    action: str,
    reason: str,
    t0: float,
    verdict: str | None = None,
    reasons: list[str] | None = None,
    error: str | None = None,
) -> None:
    _write_receipt(
        session_id=session_id,
        channel_id=channel_id,
        trigger=trigger,
        history_len=history_len,
        verdict=verdict,
        action=action,
        elapsed_ms=(time.monotonic() - t0) * 1000,
        reasons=reasons,
        error=error,
    )
    print(_deny_output(reason))
    sys.exit(0)


def _run_gate(session_id: str, transcript_path: str, candidate: dict) -> None:
    t0 = time.monotonic()
    channel_id = candidate["channel_id"]

    if candidate.get("direct_command"):
        _deny_and_log(
            session_id=session_id,
            channel_id=channel_id,
            trigger=None,
            history_len=0,
            action="deny-direct-send-path",
            reason=(
                "nunchi gate: direct Discord send commands are not a supported "
                "room-send path. Use the Nunchi Discord MCP send tool."
            ),
            t0=t0,
        )

    context, _context_index = _extract_room_context_with_index(transcript_path)
    if context is None:
        _deny_and_log(
            session_id=session_id,
            channel_id=channel_id,
            trigger=None,
            history_len=0,
            action="deny-untriggered",
            reason=(
                "nunchi gate: no current Nunchi room context is present for this send "
                "(no Nunchi room context on the latest user turn). "
                "Do not send this message; stay silent this turn."
            ),
            t0=t0,
        )
    payload, context_error = _build_payload(context, channel_id)
    if context_error is not None or payload is None:
        _deny_and_log(
            session_id=session_id,
            channel_id=channel_id,
            trigger=None,
            history_len=0,
            action="deny-context-error",
            reason=(
                f"nunchi gate: {context_error}. Do not send this message; "
                "stay silent this turn."
            ),
            t0=t0,
            error=context_error,
        )

    trigger = payload["trigger"]
    history_len = len(payload["history"])
    if _has_prior_allowed_send_receipt(
        session_id=session_id,
        channel_id=channel_id,
        trigger=trigger,
    ):
        _deny_and_log(
            session_id=session_id,
            channel_id=channel_id,
            trigger=trigger,
            history_len=history_len,
            action="deny-already-sent",
            reason=(
                "nunchi gate: this admitted room context already sent a room "
                "message. Do not send another message for the same turn."
            ),
            t0=t0,
        )

    directive, gate_error = _call_gate(payload)
    if gate_error is not None:
        if _FAIL_POLICY == "open":
            _write_receipt(
                session_id=session_id,
                channel_id=channel_id,
                trigger=trigger,
                history_len=history_len,
                verdict=None,
                action="allow-gate-error",
                elapsed_ms=(time.monotonic() - t0) * 1000,
                error=gate_error,
            )
            print(_allow_output())
            sys.exit(0)
        _deny_and_log(
            session_id=session_id,
            channel_id=channel_id,
            trigger=trigger,
            history_len=history_len,
            action="deny-gate-error",
            reason=(
                f"nunchi gate error: {gate_error}. Do not send this message; "
                "stay silent this turn."
            ),
            t0=t0,
            error=gate_error,
        )

    verdict = str(directive.get("verdict"))
    reasons = directive.get("reasons") or []
    if verdict == "PASS":
        first_reason = (reasons[0] if reasons else "not this agent's turn").rstrip(".")
        _deny_and_log(
            session_id=session_id,
            channel_id=channel_id,
            trigger=trigger,
            history_len=history_len,
            verdict=verdict,
            action="deny-pass",
            reason=(
                f"nunchi gate: PASS - {first_reason}. Do not send this message; "
                "stay silent this turn and end without further send attempts."
            ),
            reasons=reasons,
            t0=t0,
        )

    _write_receipt(
        session_id=session_id,
        channel_id=channel_id,
        trigger=trigger,
        history_len=history_len,
        verdict=verdict,
        action=f"allow-{verdict.lower()}",
        elapsed_ms=(time.monotonic() - t0) * 1000,
        reasons=reasons,
    )
    print(_allow_output())
    sys.exit(0)


def main() -> None:
    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)
    if not isinstance(hook_input, dict):
        sys.exit(0)

    candidate = _send_candidate(
        str(hook_input.get("tool_name") or ""),
        hook_input.get("tool_input"),
    )
    if candidate is None:
        sys.exit(0)

    _run_gate(
        session_id=str(hook_input.get("session_id") or ""),
        transcript_path=str(hook_input.get("transcript_path") or ""),
        candidate=candidate,
    )


if __name__ == "__main__":
    main()
