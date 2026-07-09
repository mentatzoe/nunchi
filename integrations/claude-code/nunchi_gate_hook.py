#!/usr/bin/env python3
"""Claude Code PreToolUse hook: gate channel sends through nunchi-channel.

Reads the PreToolUse JSON envelope from stdin; when the tool matches a channel
reply pattern AND the tool_input has both chat_id and text, parses the session
transcript (JSONL) to build a nunchi-channel payload, calls the gate binary,
and outputs the hookSpecificOutput JSON to allow or deny the tool call.

Non-matching tools and agent-initiated sends (no inbound trigger in transcript)
pass through silently (exit 0, no stdout output).

Environment variables
---------------------
NUNCHI_HOOK_TOOL_PATTERN   Regex matched against tool_name (default: ``__reply$``).
                           Tool must also have chat_id + text in tool_input.
NUNCHI_HOOK_AGENT_ID       Agent identifier sent in the nunchi payload (default: "agent").
NUNCHI_HOOK_MENTION_ID     Optional @mention handle for the agent. This is the
                           PLATFORM mention token — on Discord the numeric
                           snowflake (e.g. "1496355876234199040") — NOT the
                           display name. A display name here makes the gate
                           blind to real @-mentions (a direct @<snowflake>
                           mention reads as "someone else"); names belong in
                           NUNCHI_HOOK_ALIASES.
NUNCHI_HOOK_ALIASES        Comma-separated additional identities this agent
                           answers to: display names, nicknames, secondary
                           handles, extra mention tokens (e.g.
                           "Vigil,Codex,Aether"). Sent as agent.aliases so
                           addressing recognizes the full bundle. Optional;
                           absent means behavior is unchanged.
NUNCHI_HOOK_PEER_BOTS      Comma-separated bot usernames; matched users get
                           author_kind "peer_bot" (default: none → all inbound
                           users are "human").
NUNCHI_HOOK_FAIL_POLICY    What to do when the gate binary fails or is unavailable:
                           "open" (default) → allow, "closed" → deny.
NUNCHI_HOOK_TIMEOUT        Subprocess timeout in seconds (default: 30).
NUNCHI_HOOK_LOG            Path for per-call receipt log
                           (default: ~/.claude/nunchi-gate-receipts.jsonl).
NUNCHI_HOOK_HISTORY_WINDOW  Transcript entries to include as history before
                           the trigger (default: 25).
NUNCHI_CHANNEL_BIN         Path or name of the nunchi-channel binary
                           (default: located via shutil.which("nunchi-channel")).
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

_TOOL_PATTERN_ENV = os.environ.get("NUNCHI_HOOK_TOOL_PATTERN", "__reply$")
_TOOL_RE = re.compile(_TOOL_PATTERN_ENV)

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
_FAIL_POLICY = os.environ.get("NUNCHI_HOOK_FAIL_POLICY", "open")
_TIMEOUT = int(os.environ.get("NUNCHI_HOOK_TIMEOUT", "30"))
_LOG_PATH = Path(
    os.environ.get(
        "NUNCHI_HOOK_LOG",
        str(Path.home() / ".claude" / "nunchi-gate-receipts.jsonl"),
    )
)
_CHANNEL_BIN: str | None = os.environ.get("NUNCHI_CHANNEL_BIN") or shutil.which(
    "nunchi-channel"
)

# Regex to parse a <channel ...> tag from transcript content strings.
# Captures: the full attribute string and the tag body.
_CHANNEL_TAG_RE = re.compile(
    r"<channel\s+([^>]+)>\s*(.*?)\s*</channel>",
    re.DOTALL,
)
# Regex to parse a single attribute from the <channel ...> opening tag.
_ATTR_RE = re.compile(r'(\w+)=["\']([^"\']*)["\']')

_MAX_HISTORY = int(os.environ.get("NUNCHI_HOOK_HISTORY_WINDOW", "25"))

# ---------------------------------------------------------------------------
# Hook output helpers (Claude Code PreToolUse JSON contract)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Transcript parsing
# ---------------------------------------------------------------------------


def _parse_attrs(attr_string: str) -> dict[str, str]:
    """Parse all key="value" or key='value' pairs from a tag attribute string."""
    return {k: v for k, v in _ATTR_RE.findall(attr_string)}


def _extract_channel_tag(text: str) -> dict | None:
    """Return parsed channel tag fields from a text string, or None."""
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


def _content_text(content) -> str:
    """Flatten a message content value to a plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text", ""))
        return "\n".join(parts)
    return ""


def _parse_transcript(transcript_path: str, chat_id: str) -> list[dict]:
    """Parse the JSONL transcript and return all events for chat_id in order.

    Returns a list of dicts with keys:
        kind      "inbound" | "self"
        author    str
        author_kind  "human" | "peer_bot" | "self"
        message_id  str
        content   str
        ts        str  (raw timestamp from tag, or "")
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

                entry_type = obj.get("type")

                # ----------------------------------------------------------
                # Inbound: user entries containing a <channel ...> tag
                # ----------------------------------------------------------
                if entry_type == "user":
                    msg = obj.get("message") or {}
                    text = _content_text(msg.get("content", ""))
                    tag = _extract_channel_tag(text)
                    if tag and tag["chat_id"] == chat_id:
                        author = tag["user"]
                        author_kind = "peer_bot" if author in _PEER_BOTS else "human"
                        events.append(
                            {
                                "kind": "inbound",
                                "author": author,
                                "author_kind": author_kind,
                                "message_id": tag["message_id"],
                                "content": tag["body"],
                                "ts": tag["ts"],
                            }
                        )

                # ----------------------------------------------------------
                # Outbound: assistant tool_use blocks for the target chat_id
                # ----------------------------------------------------------
                elif entry_type == "assistant":
                    msg = obj.get("message") or {}
                    content_list = msg.get("content", [])
                    if not isinstance(content_list, list):
                        continue
                    for item in content_list:
                        if (
                            isinstance(item, dict)
                            and item.get("type") == "tool_use"
                            and _TOOL_RE.search(item.get("name", ""))
                        ):
                            inp = item.get("input") or {}
                            if (
                                isinstance(inp, dict)
                                and inp.get("chat_id") == chat_id
                            ):
                                events.append(
                                    {
                                        "kind": "self",
                                        "author": _AGENT_ID,
                                        "author_kind": "self",
                                        "message_id": item.get("id", ""),
                                        "content": inp.get("text", ""),
                                        "ts": "",
                                    }
                                )

    except OSError:
        pass  # Transcript missing or unreadable; return what we have

    return events


# ---------------------------------------------------------------------------
# Payload building
# ---------------------------------------------------------------------------


def _build_nunchi_payload(
    trigger_event: dict,
    history_events: list[dict],
) -> dict:
    """Build the nunchi-channel JSON payload from parsed transcript events."""

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
# Receipt logging
# ---------------------------------------------------------------------------


def _write_receipt(
    session_id: str,
    chat_id: str,
    trigger_event: dict | None,
    history_len: int,
    verdict: str | None,
    silent: bool | None,
    action: str,
    elapsed_ms: float,
    reasons: list[str],
    error: str | None,
) -> None:
    """Append one JSON line to the receipts log."""
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "chat_id": chat_id,
            "trigger_message_id": trigger_event["message_id"] if trigger_event else None,
            "trigger_author": trigger_event["author"] if trigger_event else None,
            "history_len": history_len,
            "verdict": verdict,
            "silent": silent,
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


def _run_gate(
    session_id: str,
    transcript_path: str,
    tool_name: str,
    tool_input: dict,
) -> None:
    """Run the gate and write the hookSpecificOutput JSON to stdout.

    Raises SystemExit with exit code 0 (allow or deny) or 1 (internal error).
    """
    chat_id: str = tool_input.get("chat_id", "")
    t0 = time.monotonic()

    # Parse transcript for events on this chat_id
    events = _parse_transcript(transcript_path, chat_id)

    # Find the most recent inbound event
    trigger_idx: int | None = None
    for i in range(len(events) - 1, -1, -1):
        if events[i]["kind"] == "inbound":
            trigger_idx = i
            break

    elapsed_ms = (time.monotonic() - t0) * 1000

    if trigger_idx is None:
        # No inbound trigger → agent-initiated send; pass through unexamined
        _write_receipt(
            session_id=session_id,
            chat_id=chat_id,
            trigger_event=None,
            history_len=0,
            verdict=None,
            silent=None,
            action="allow-untriggered",
            elapsed_ms=elapsed_ms,
            reasons=[],
            error=None,
        )
        # No output → Claude Code applies normal permission flow
        sys.exit(0)

    trigger_event = events[trigger_idx]
    history_events = events[max(0, trigger_idx - _MAX_HISTORY) : trigger_idx]

    # Build payload and call nunchi-channel
    payload = _build_nunchi_payload(trigger_event, history_events)

    if not _CHANNEL_BIN:
        # Gate binary not available
        error_msg = "nunchi-channel not found; check NUNCHI_CHANNEL_BIN or install nunchi"
        elapsed_ms = (time.monotonic() - t0) * 1000
        if _FAIL_POLICY == "closed":
            action = "deny-gate-error"
            out = _deny_output(f"nunchi gate unavailable: {error_msg}. Do not send this message; stay silent this turn and end your reply without further send attempts.")
        else:
            action = "allow-gate-error"
            out = _allow_output()
        _write_receipt(
            session_id=session_id,
            chat_id=chat_id,
            trigger_event=trigger_event,
            history_len=len(history_events),
            verdict=None,
            silent=None,
            action=action,
            elapsed_ms=elapsed_ms,
            reasons=[],
            error=error_msg,
        )
        print(out)
        sys.exit(0)

    try:
        result = subprocess.run(
            [_CHANNEL_BIN],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        elapsed_ms = (time.monotonic() - t0) * 1000
    except subprocess.TimeoutExpired:
        elapsed_ms = (time.monotonic() - t0) * 1000
        error_msg = f"nunchi-channel timed out after {_TIMEOUT}s"
        if _FAIL_POLICY == "closed":
            action = "deny-gate-error"
            out = _deny_output(f"nunchi gate error: {error_msg}. Do not send this message; stay silent this turn and end your reply without further send attempts.")
        else:
            action = "allow-gate-error"
            out = _allow_output()
        _write_receipt(
            session_id=session_id,
            chat_id=chat_id,
            trigger_event=trigger_event,
            history_len=len(history_events),
            verdict=None,
            silent=None,
            action=action,
            elapsed_ms=elapsed_ms,
            reasons=[],
            error=error_msg,
        )
        print(out)
        sys.exit(0)
    except OSError as exc:
        elapsed_ms = (time.monotonic() - t0) * 1000
        error_msg = f"failed to run nunchi-channel: {exc}"
        if _FAIL_POLICY == "closed":
            action = "deny-gate-error"
            out = _deny_output(f"nunchi gate error: {error_msg}. Do not send this message; stay silent this turn and end your reply without further send attempts.")
        else:
            action = "allow-gate-error"
            out = _allow_output()
        _write_receipt(
            session_id=session_id,
            chat_id=chat_id,
            trigger_event=trigger_event,
            history_len=len(history_events),
            verdict=None,
            silent=None,
            action=action,
            elapsed_ms=elapsed_ms,
            reasons=[],
            error=error_msg,
        )
        print(out)
        sys.exit(0)

    # Binary exited
    if result.returncode != 0:
        error_msg = (result.stderr or "").strip() or f"nunchi-channel exited {result.returncode}"
        if _FAIL_POLICY == "closed":
            action = "deny-gate-error"
            out = _deny_output(f"nunchi gate error: {error_msg}. Do not send this message; stay silent this turn and end your reply without further send attempts.")
        else:
            action = "allow-gate-error"
            out = _allow_output()
        _write_receipt(
            session_id=session_id,
            chat_id=chat_id,
            trigger_event=trigger_event,
            history_len=len(history_events),
            verdict=None,
            silent=None,
            action=action,
            elapsed_ms=elapsed_ms,
            reasons=[],
            error=error_msg,
        )
        print(out)
        sys.exit(0)

    # Parse directive from nunchi-channel stdout
    try:
        directive = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        error_msg = f"nunchi-channel returned invalid JSON: {exc}"
        if _FAIL_POLICY == "closed":
            action = "deny-gate-error"
            out = _deny_output(f"nunchi gate error: {error_msg}. Do not send this message; stay silent this turn and end your reply without further send attempts.")
        else:
            action = "allow-gate-error"
            out = _allow_output()
        _write_receipt(
            session_id=session_id,
            chat_id=chat_id,
            trigger_event=trigger_event,
            history_len=len(history_events),
            verdict=None,
            silent=None,
            action=action,
            elapsed_ms=elapsed_ms,
            reasons=[],
            error=error_msg,
        )
        print(out)
        sys.exit(0)

    verdict: str = directive.get("verdict", "")
    silent: bool = directive.get("silent", False)
    reasons: list[str] = directive.get("reasons") or []

    if silent:
        first_reason = (reasons[0] if reasons else "no reason given").rstrip(".")
        deny_reason = (
            f"nunchi gate: PASS — {first_reason}. "
            "Do not send this message; stay silent this turn and end your reply "
            "without further send attempts."
        )
        action = "deny-pass"
        out = _deny_output(deny_reason)
    else:
        action = f"allow-{verdict.lower()}"
        out = _allow_output()

    _write_receipt(
        session_id=session_id,
        chat_id=chat_id,
        trigger_event=trigger_event,
        history_len=len(history_events),
        verdict=verdict,
        silent=silent,
        action=action,
        elapsed_ms=elapsed_ms,
        reasons=reasons,
        error=None,
    )
    print(out)
    sys.exit(0)


def main() -> None:
    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"nunchi_gate_hook: invalid JSON on stdin: {exc}", file=sys.stderr)
        sys.exit(1)

    tool_name: str = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input") or {}
    session_id: str = hook_input.get("session_id", "")
    transcript_path: str = hook_input.get("transcript_path", "")

    # Only act on tools matching the pattern AND having chat_id + text in input
    if not _TOOL_RE.search(tool_name):
        sys.exit(0)
    if not isinstance(tool_input, dict):
        sys.exit(0)
    if not (tool_input.get("chat_id") and tool_input.get("text") is not None):
        sys.exit(0)

    if not transcript_path:
        # No transcript path → cannot judge context; pass through
        sys.exit(0)

    _run_gate(session_id, transcript_path, tool_name, tool_input)


if __name__ == "__main__":
    main()
