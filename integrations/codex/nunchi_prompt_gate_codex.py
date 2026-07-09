#!/usr/bin/env python3
"""Codex UserPromptSubmit hook: gate inbound channel messages pre-LLM.

Port of ``integrations/claude-code/nunchi_prompt_gate.py`` to Codex's hooks
contract (https://developers.openai.com/codex/hooks). Reads the
UserPromptSubmit JSON envelope from stdin (``session_id``,
``transcript_path``, ``cwd``, ``hook_event_name``, ``model``, ``turn_id``,
``prompt``, ``permission_mode``); when the submitted prompt contains a
``<channel ...>`` tag (a Discord/channel-sourced message injected into an
interactive session), it builds a nunchi-channel payload, calls the gate
binary, and blocks on PASS by printing ``{"decision": "block", "reason":
...}`` to stdout (Codex also accepts exit code 2 + stderr; the stdout JSON
form is used here to mirror the Claude Code hook).

Prompts WITHOUT a channel tag are the operator typing and are ALWAYS allowed
through immediately — zero gate calls, no receipt. The room runner's wake
prompts intentionally carry no channel tag (they were already gated), so
this hook never double-gates them; it is the second layer for other bridges
that paste channel-tagged messages into interactive Codex sessions.

This hook is permanently fail-OPEN — the opposite of the room runner. Any
configuration error, missing binary, gate timeout, or unparseable output
allows the prompt through and records the failure in the receipt log. A
broken gate must never silence an operator typing at their own terminal.

VERDICT POLARITY (inbound gate):
    PASS               → block the prompt (suppress before the LLM runs).
    SPEAK / ACK / ASK  → allow the prompt through.

Transcript history is best-effort: Codex rollout JSONL is parsed tolerantly
(``payload``-wrapped response items, plain role/content objects, and
function_call/tool_use send records); on any parse failure the gate runs on
the trigger alone.

Environment variables
---------------------
NUNCHI_HOOK_AGENT_ID       Agent identifier in the nunchi payload (default: ``agent``).
NUNCHI_HOOK_MENTION_ID     Optional @mention handle for the agent. This is the
                           PLATFORM mention token — on Discord the numeric
                           snowflake (e.g. ``1496355876234199040``) — NOT the
                           display name. A display name here makes the gate
                           blind to real @-mentions; names belong in
                           NUNCHI_HOOK_ALIASES.
NUNCHI_HOOK_ALIASES        Comma-separated additional identities this agent
                           answers to: display names, nicknames, secondary
                           handles, extra mention tokens (e.g.
                           ``Vigil,Codex,Aether``). Sent as ``agent.aliases``
                           so addressing recognizes the full bundle. Optional;
                           absent means behavior is unchanged.
NUNCHI_HOOK_PEER_BOTS      Comma-separated bot usernames; matched users get
                           ``author_kind`` ``peer_bot`` (default: all → ``human``).
NUNCHI_HOOK_HISTORY_WINDOW Transcript events to include as history (default: 25).
NUNCHI_HOOK_TOOL_PATTERN   Regex matched against tool/function names to identify
                           outbound self-sends in the transcript
                           (default: ``(?:send|reply)_message$`` — the
                           nunchi-discord MCP tools).
NUNCHI_HOOK_TIMEOUT        Gate subprocess timeout in seconds (default: 30).
NUNCHI_RUNNER_LOG          Receipt JSONL path, shared with the room runner
                           (default: ``~/.nunchi/codex-runner-receipts.jsonl``).
                           Records from this hook carry ``"direction": "hook-inbound"``.
NUNCHI_CHANNEL_BIN         Path or name of the nunchi-channel binary
                           (default: located via ``shutil.which("nunchi-channel")``).
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

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_AGENT_ID = os.environ.get("NUNCHI_HOOK_AGENT_ID", "agent")
_MENTION_ID = os.environ.get("NUNCHI_HOOK_MENTION_ID")


def _parse_aliases(raw: str | None) -> list[str]:
    """Split a comma-separated alias string; strip, drop blanks, dedupe in order."""
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


_ALIASES: list[str] = _parse_aliases(os.environ.get("NUNCHI_HOOK_ALIASES"))
_PEER_BOTS: frozenset[str] = frozenset(
    b.strip()
    for b in (os.environ.get("NUNCHI_HOOK_PEER_BOTS", "") or "").split(",")
    if b.strip()
)
_HISTORY_WINDOW = int(os.environ.get("NUNCHI_HOOK_HISTORY_WINDOW", "25"))
_TIMEOUT = int(os.environ.get("NUNCHI_HOOK_TIMEOUT", "30"))
_LOG_PATH = Path(
    os.environ.get(
        "NUNCHI_RUNNER_LOG",
        str(Path.home() / ".nunchi" / "codex-runner-receipts.jsonl"),
    )
)
_CHANNEL_BIN: str | None = os.environ.get("NUNCHI_CHANNEL_BIN") or shutil.which(
    "nunchi-channel"
)

# Regex to locate a <channel ...>...</channel> block anywhere in text.
_CHANNEL_TAG_RE = re.compile(
    r"<channel\s+([^>]+)>\s*(.*?)\s*</channel>",
    re.DOTALL,
)
# Regex to parse one key="value" or key='value' attribute.
_ATTR_RE = re.compile(r'(\w+)=["\']([^"\']*)["\']')

# Tool/function-name pattern for identifying outbound self-sends.
_TOOL_RE = re.compile(os.environ.get("NUNCHI_HOOK_TOOL_PATTERN", r"(?:send|reply)_message$"))

_VERDICTS = frozenset({"PASS", "ACK", "ASK", "SPEAK"})

# ---------------------------------------------------------------------------
# Channel tag parsing
# ---------------------------------------------------------------------------


def _parse_attrs(attr_string: str) -> dict[str, str]:
    """Parse all key="value" / key='value' pairs from a tag attribute string."""
    return {k: v for k, v in _ATTR_RE.findall(attr_string)}


def _extract_channel_tag(text: str) -> dict | None:
    """Return parsed channel tag fields from *text*, or None if absent."""
    m = _CHANNEL_TAG_RE.search(text)
    if not m:
        return None
    attrs = _parse_attrs(m.group(1))
    return {
        "chat_id": attrs.get("chat_id", ""),
        "message_id": attrs.get("message_id", ""),
        "user": attrs.get("user", ""),
        "ts": attrs.get("ts", ""),
        "body": m.group(2).strip(),
    }


# ---------------------------------------------------------------------------
# Transcript parsing (best-effort Codex rollout JSONL)
# ---------------------------------------------------------------------------


def _content_text(content) -> str:
    """Flatten a message content value (str or list of text items) to a string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text", ""))
        return "\n".join(parts)
    return ""


def _send_args(obj: dict) -> dict | None:
    """Return the arguments dict of a send-tool call item, or None."""
    name = obj.get("name", "")
    if not isinstance(name, str) or not _TOOL_RE.search(name):
        return None
    args = obj.get("arguments", obj.get("input"))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return None
    return args if isinstance(args, dict) else None


def _parse_transcript_history(transcript_path: str, chat_id: str) -> list[dict]:
    """Parse the rollout JSONL and return past events for *chat_id* in order.

    Tolerant by design: each line is unwrapped from an optional ``payload``
    envelope; user-role text is scanned for channel tags (inbound events) and
    send-tool calls matching ``NUNCHI_HOOK_TOOL_PATTERN`` become self events.
    Silently returns whatever was collected on any OS/parse error.
    """
    events: list[dict] = []
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
                if isinstance(item.get("message"), dict):  # claude-style nesting
                    item = {**item["message"], **{k: v for k, v in item.items() if k != "message"}}

                # Past inbound: user-role text containing a <channel ...> tag
                if item.get("role") == "user":
                    tag = _extract_channel_tag(_content_text(item.get("content", "")))
                    if tag and tag["chat_id"] == chat_id:
                        author = tag["user"]
                        events.append(
                            {
                                "author": author,
                                "author_kind": "peer_bot" if author in _PEER_BOTS else "human",
                                "message_id": tag["message_id"],
                                "content": tag["body"],
                            }
                        )
                    continue

                # Past outbound: function_call / tool_use send records
                candidates = [item]
                if isinstance(item.get("content"), list):
                    candidates.extend(c for c in item["content"] if isinstance(c, dict))
                for cand in candidates:
                    args = _send_args(cand)
                    if args is None:
                        continue
                    target = str(args.get("channel_id") or args.get("chat_id") or "")
                    content = args.get("content") or args.get("text") or ""
                    if target == chat_id and content:
                        events.append(
                            {
                                "author": _AGENT_ID,
                                "author_kind": "self",
                                "message_id": str(cand.get("call_id") or cand.get("id") or ""),
                                "content": content,
                            }
                        )
    except OSError:
        pass  # Transcript missing or unreadable; return whatever was collected

    return events


# ---------------------------------------------------------------------------
# Payload building
# ---------------------------------------------------------------------------


def _build_nunchi_payload(trigger_event: dict, history_events: list[dict]) -> dict:
    """Build the nunchi-channel JSON payload from parsed events."""

    def _to_msg(ev: dict) -> dict:
        return {
            "content": ev["content"],
            "author": ev["author"],
            "author_kind": ev["author_kind"],
            "message_id": ev["message_id"],
        }

    agent: dict = {"id": _AGENT_ID}
    if _MENTION_ID:
        agent["mention_id"] = _MENTION_ID
    aliases = [a for a in _ALIASES if a != _AGENT_ID and a != _MENTION_ID]
    if aliases:
        agent["aliases"] = aliases

    return {
        "trigger": _to_msg(trigger_event),
        "history": [_to_msg(ev) for ev in history_events],
        "agent": agent,
        "fail_policy": "raise",
    }


# ---------------------------------------------------------------------------
# Hook output helper (Codex UserPromptSubmit block contract)
# ---------------------------------------------------------------------------


def _block_output(reason: str) -> str:
    return json.dumps({"decision": "block", "reason": reason})


# Allow → exit 0 with no stdout output.

# ---------------------------------------------------------------------------
# Receipt logging
# ---------------------------------------------------------------------------


def _write_receipt(
    session_id: str,
    chat_id: str,
    trigger_event: dict | None,
    history_len: int,
    verdict: str | None,
    action: str,
    elapsed_ms: float,
    reasons: list[str],
    error: str | None,
) -> None:
    """Append one JSON line to the shared runner receipts log.

    Always sets ``"direction": "hook-inbound"`` to distinguish these records
    from the room runner's receipts in the same file.
    """
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "direction": "hook-inbound",
            "session_id": session_id,
            "channel": chat_id,
            "message_id": trigger_event["message_id"] if trigger_event else None,
            "author": trigger_event["author"] if trigger_event else None,
            "history_len": history_len,
            "verdict": verdict,
            "action": action,
            "elapsed_ms": round(elapsed_ms, 1),
            "reasons": reasons[:3],
        }
        if error:
            record["error"] = error
        with open(_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass  # Non-fatal; receipts are telemetry


# ---------------------------------------------------------------------------
# Main gate logic
# ---------------------------------------------------------------------------


def _run_gate(session_id: str, prompt: str, transcript_path: str) -> None:
    """Evaluate the inbound prompt and write block output or exit silently.

    Always exits with code 0. All errors are fail-open: allow + log.
    """
    t0 = time.monotonic()

    # Non-channel prompts (operator typing) — always allow, no gate call, no receipt.
    tag = _extract_channel_tag(prompt)
    if tag is None:
        sys.exit(0)

    chat_id = tag["chat_id"]
    trigger_event = {
        "author": tag["user"],
        "author_kind": "peer_bot" if tag["user"] in _PEER_BOTS else "human",
        "message_id": tag["message_id"],
        "content": tag["body"],
    }

    # Best-effort history from the rollout (the current prompt is not in it yet).
    history_events: list[dict] = []
    if transcript_path:
        history_events = _parse_transcript_history(transcript_path, chat_id)[-_HISTORY_WINDOW:]

    def _fail_open(error_msg: str) -> None:
        _write_receipt(
            session_id=session_id,
            chat_id=chat_id,
            trigger_event=trigger_event,
            history_len=len(history_events),
            verdict=None,
            action="allow-gate-error",
            elapsed_ms=(time.monotonic() - t0) * 1000,
            reasons=[],
            error=error_msg,
        )
        sys.exit(0)

    if not _CHANNEL_BIN:
        _fail_open("nunchi-channel not found; check NUNCHI_CHANNEL_BIN or install nunchi")

    payload = _build_nunchi_payload(trigger_event, history_events)

    try:
        result = subprocess.run(
            [_CHANNEL_BIN],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        _fail_open(f"nunchi-channel timed out after {_TIMEOUT}s")
    except OSError as exc:
        _fail_open(f"failed to run nunchi-channel: {exc}")

    if result.returncode != 0:
        _fail_open(
            (result.stderr or "").strip() or f"nunchi-channel exited {result.returncode}"
        )

    try:
        directive = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        _fail_open(f"nunchi-channel returned invalid JSON: {exc}")

    if not isinstance(directive, dict):
        _fail_open("nunchi-channel returned a malformed directive")

    verdict: str = directive.get("verdict", "")
    if verdict not in _VERDICTS:
        _fail_open("nunchi-channel returned a malformed directive")
    if "silent" in directive and bool(directive.get("silent")) != (verdict == "PASS"):
        _fail_open("nunchi-channel returned a contradictory silent flag")

    reasons: list[str] = directive.get("reasons") or []
    elapsed_ms = (time.monotonic() - t0) * 1000

    # PASS → block the prompt before the LLM runs.
    if verdict == "PASS":
        first_reason = (reasons[0] if reasons else "not this agent's turn").rstrip(".")
        _write_receipt(
            session_id=session_id,
            chat_id=chat_id,
            trigger_event=trigger_event,
            history_len=len(history_events),
            verdict=verdict,
            action="block-pass",
            elapsed_ms=elapsed_ms,
            reasons=reasons,
            error=None,
        )
        print(_block_output(f"nunchi gate: PASS — {first_reason}."))
        sys.exit(0)

    # SPEAK / ACK / ASK → allow through (no stdout).
    _write_receipt(
        session_id=session_id,
        chat_id=chat_id,
        trigger_event=trigger_event,
        history_len=len(history_events),
        verdict=verdict,
        action=f"allow-{verdict.lower()}",
        elapsed_ms=elapsed_ms,
        reasons=reasons,
        error=None,
    )
    sys.exit(0)


def main() -> None:
    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Malformed stdin — fail open, no receipt (nothing useful to log).
        sys.exit(0)

    if not isinstance(hook_input, dict):
        sys.exit(0)

    session_id: str = hook_input.get("session_id", "")
    prompt: str = hook_input.get("prompt", "")
    # transcript_path is "string | null" in the Codex contract.
    transcript_path: str = hook_input.get("transcript_path") or ""

    _run_gate(session_id, prompt, transcript_path)


if __name__ == "__main__":
    main()
