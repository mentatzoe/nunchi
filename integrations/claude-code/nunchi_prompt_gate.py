#!/usr/bin/env python3
"""Claude Code UserPromptSubmit hook: nunchi's ONE judgment per turn, at wake.

Reads the UserPromptSubmit JSON envelope from stdin; when the submitted
prompt contains a ``<channel ...>`` tag (indicating a Discord/channel-sourced
message), parses the session transcript to build a nunchi-channel payload,
calls the gate binary, and decides admission. This is the only judgment the
turn gets — there is no send-time re-judgment (a retired second hook used to
re-judge composed replies against the newest transcript line and silenced them
by mistake; nunchi now judges once, here, and then gets out of the way).

Prompts WITHOUT a channel tag are the operator typing at the terminal and are
ALWAYS allowed through immediately — zero gate calls, no receipt.

This hook is permanently fail-open.  Any configuration error, missing binary,
gate timeout, or unparseable output allows the prompt through and records the
failure in the receipt log.  A broken gate must never silence the operator or
wedge the session.

DECISIONS:
    PASS (confident)  → block the prompt (not this agent's turn; suppress pre-LLM).
    PASS (uncertain)  → DEFER: the gate abstains and hands the turn to the
                        agent's own model with its hesitation noted. The agent
                        may reply or choose silence — a small fast gate may only
                        silence what it can confidently judge.
    SPEAK / ACK / ASK → admit: allow the prompt through, noting in-band which
                        message this turn answers (the admission travels with
                        the turn; no side state).

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
NUNCHI_HOOK_TOOL_PATTERN   Regex matched against tool_name to identify outbound
                           self-sends in the transcript (default: ``__reply$``).
NUNCHI_HOOK_TIMEOUT        Subprocess timeout in seconds (default: 30).
NUNCHI_HOOK_LOG            Path for per-call receipt log
                           (default: ``~/.claude/nunchi-gate-receipts.jsonl``).
NUNCHI_CHANNEL_BIN         Path or name of the nunchi-channel binary
                           (default: located via ``shutil.which("nunchi-channel")``).
NUNCHI_DEFER               Kill switch for DEFER. Default ON (abstain on an
                           uncertain PASS); set to ``off``/``0``/``false``/``no``
                           to make every PASS block regardless of confidence.
NUNCHI_DEFER_MARGIN        A PASS is "uncertain" when the best alternative
                           verdict's confidence is within this margin of it
                           (default: 0.25; uncalibrated placeholder — see
                           DEFER_EVAL.md).
"""

from __future__ import annotations

import hashlib
import json
import math
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
def _parse_history_window() -> int:
    """Safe numeric config: a malformed NUNCHI_HOOK_HISTORY_WINDOW must not
    crash the hook at import (round-2 finding); fall back to the default."""
    raw = os.environ.get("NUNCHI_HOOK_HISTORY_WINDOW", "25")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 25
    return value if value >= 0 else 25


_HISTORY_WINDOW = _parse_history_window()
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

# Regex to locate a <channel ...>...</channel> block anywhere in text.
# GREEDY body match — the judged content runs to the LAST closing delimiter.
# A message whose body contains a literal "</channel>" must not truncate the
# judged trigger at that first occurrence: the sole admission judge has to see
# everything the participant model will see (Aleph's envelope-integrity
# finding, 2026-07-10). Over-matching trailing text is the safe direction;
# under-matching lets content ride in unjudged.
_CHANNEL_TAG_RE = re.compile(
    r"<channel\s+([^>]+)>\s*(.*)\s*</channel>",
    re.DOTALL,
)
# Regex to parse one complete key="value" / key='value' attribute token. The
# leading boundary (start or whitespace) is load-bearing: without it,
# not-chat_id="c1" parses as chat_id="c1" and a spoofed envelope binds
# (round-2 finding).
_ATTR_RE = re.compile(r'(?:^|\s)(\w+)=["\']([^"\']*)["\']')

# Tool pattern for identifying outbound self-sends in the transcript.
_TOOL_RE = re.compile(os.environ.get("NUNCHI_HOOK_TOOL_PATTERN", "__reply$"))

# DEFER: abstain on an uncertain PASS instead of silencing. Default ON — the
# abstention IS the design, not an experiment; the env var is a kill switch.
_DEFER_ENABLED = (os.environ.get("NUNCHI_DEFER") or "").strip().lower() not in {
    "off", "0", "false", "no",
}


_DEFER_MARGIN_DEFAULT = 0.25


def _defer_margin() -> float:
    """Effective margin, clamped to sane bounds. A margin outside [0, 1] or a
    non-finite value (inf defers everything; nan disables DEFER by comparing
    false) is operator error — fall back to the default rather than silently
    running a degenerate gate."""
    raw = os.environ.get("NUNCHI_DEFER_MARGIN")
    if raw is None or not raw.strip():
        return _DEFER_MARGIN_DEFAULT
    try:
        value = float(raw)
    except ValueError:
        return _DEFER_MARGIN_DEFAULT
    if not math.isfinite(value) or not (0.0 <= value <= 1.0):
        return _DEFER_MARGIN_DEFAULT
    return value


_ALT_VERDICTS = ("SPEAK", "ACK", "ASK")
_ALL_VERDICTS = ("PASS", *_ALT_VERDICTS)


def _confidence_malformation(conf) -> str | None:
    """Why this confidence map cannot justify a HARD suppression, or ``None``.

    Hard suppression requires a complete, finite, correctly typed confidence
    vector (review contract, 2026-07-10). A missing, partial, mistyped, or
    non-finite map is broken *evidence* — not proof of confidence, and not
    proof of uncertainty either. The caller decides what broken evidence means
    (with DEFER on: abstain to the participant; with DEFER off: the operator
    chose hard mode)."""
    if conf is None:
        return "confidences missing"
    if not isinstance(conf, dict):
        return f"confidences is {type(conf).__name__}, expected object"
    missing = [k for k in _ALL_VERDICTS if k not in conf]
    if missing:
        return f"confidences incomplete (missing {', '.join(missing)})"
    for key in _ALL_VERDICTS:
        value = conf[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"confidence {key} is {type(value).__name__}, expected number"
        if not math.isfinite(float(value)):
            return f"confidence {key} is not finite"
    return None


def _uncertain_pass(conf: dict, margin: float) -> bool:
    """True when a VALIDATED confidence vector shows an ambiguous PASS: some
    alternative verdict sits within *margin* of PASS (inclusive — "within"
    includes the exact boundary). Callers must have cleared
    ``_confidence_malformation`` first; this function only compares numbers."""
    pass_c = float(conf["PASS"])
    best_alt = max(float(conf[k]) for k in _ALT_VERDICTS)
    return (pass_c - best_alt) <= margin

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
        # Values are stripped so a whitespace-only identifier reads as missing
        # (round-2 finding: blank ids were accepted as bound envelopes).
        "chat_id": attrs.get("chat_id", "").strip(),
        "message_id": attrs.get("message_id", "").strip(),
        "user": attrs.get("user", "").strip(),
        "ts": attrs.get("ts", "").strip(),
        "body": m.group(2).strip(),
    }


# ---------------------------------------------------------------------------
# Transcript parsing (history — trigger is the current prompt, not recorded yet)
# ---------------------------------------------------------------------------


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


def _parse_transcript_history(transcript_path: str, chat_id: str) -> list[dict]:
    """Parse the JSONL transcript and return past events for *chat_id* in order.

    Returns a list of dicts with keys:
        kind         ``"inbound"`` | ``"self"``
        author       str
        author_kind  ``"human"`` | ``"peer_bot"`` | ``"self"``
        message_id   str
        content      str
        ts           str  (raw timestamp from tag, or ``""``)

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
                    continue  # a JSONL row like [] is noise, not a crash

                entry_type = obj.get("type")

                # Past inbound: user entries containing a <channel ...> tag
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

                # Past outbound: assistant tool_use reply blocks for this chat_id
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
        pass  # Transcript missing or unreadable; return whatever was collected

    return events


# ---------------------------------------------------------------------------
# Payload building
# ---------------------------------------------------------------------------


def _build_nunchi_payload(
    trigger_event: dict,
    history_events: list[dict],
) -> dict:
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
# Hook output helpers (Claude Code UserPromptSubmit block contract)
# ---------------------------------------------------------------------------


def _block_output(reason: str) -> str:
    return json.dumps({"decision": "block", "reason": reason})


def _context_output(context: str) -> str:
    """Allow the prompt through with a short nunchi note added to the turn's
    context. The note carries admission facts only (verdict, origin, the gate's
    hesitation) — never reply prose; what to say, and whether to say anything,
    stays the agent's."""
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context,
            }
        }
    )


# Plain allow (operator prompts) → exit 0 with no stdout output.

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
    extra: dict | None = None,
) -> None:
    """Append one JSON line to the receipts log.

    Always sets ``"direction": "inbound"`` — kept for log-format continuity
    with records written before the send-time hook was retired. ``extra``
    carries decision provenance the offline eval arm reads back (the DEFER
    confidence vector, effective margin, classifier identity, envelope
    fingerprint); a receipt without it is still valid telemetry.
    """
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "direction": "inbound",
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
        if extra:
            record.update(extra)
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
    prompt: str,
    transcript_path: str,
) -> None:
    """Evaluate the inbound prompt and write block output or exit silently.

    Always exits with code 0.  All errors are fail-open: allow + log.
    """
    t0 = time.monotonic()

    # Non-channel prompts (operator typing) — always allow, no gate call, no receipt.
    tag = _extract_channel_tag(prompt)
    if tag is None:
        sys.exit(0)

    chat_id = tag["chat_id"]

    # A channel envelope missing its identifying attributes cannot produce a
    # BOUND judgment — judging it anyway would attach a verdict to nothing.
    # Fail open with telemetry instead (the prompt passes, unlabelled).
    missing = [k for k in ("chat_id", "message_id", "user") if not tag[k]]
    if missing:
        _write_receipt(
            session_id=session_id,
            chat_id=chat_id,
            trigger_event=None,
            history_len=0,
            verdict=None,
            silent=None,
            action="allow-envelope-error",
            elapsed_ms=(time.monotonic() - t0) * 1000,
            reasons=[],
            error=f"channel envelope missing required attributes: {', '.join(missing)}",
        )
        sys.exit(0)

    trigger_event = {
        "kind": "inbound",
        "author": tag["user"],
        "author_kind": "peer_bot" if tag["user"] in _PEER_BOTS else "human",
        "message_id": tag["message_id"],
        "content": tag["body"],
        "ts": tag["ts"],
    }

    # Build history from the transcript (the current prompt is not recorded yet).
    history_events: list[dict] = []
    if transcript_path:
        all_past = _parse_transcript_history(transcript_path, chat_id)
        history_events = all_past[-_HISTORY_WINDOW:]

    elapsed_ms = (time.monotonic() - t0) * 1000

    # Gate binary unavailable — fail open.
    if not _CHANNEL_BIN:
        error_msg = "nunchi-channel not found; check NUNCHI_CHANNEL_BIN or install nunchi"
        elapsed_ms = (time.monotonic() - t0) * 1000
        _write_receipt(
            session_id=session_id,
            chat_id=chat_id,
            trigger_event=trigger_event,
            history_len=len(history_events),
            verdict=None,
            silent=None,
            action="allow-gate-error",
            elapsed_ms=elapsed_ms,
            reasons=[],
            error=error_msg,
        )
        sys.exit(0)

    payload = _build_nunchi_payload(trigger_event, history_events)

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
        _write_receipt(
            session_id=session_id,
            chat_id=chat_id,
            trigger_event=trigger_event,
            history_len=len(history_events),
            verdict=None,
            silent=None,
            action="allow-gate-error",
            elapsed_ms=elapsed_ms,
            reasons=[],
            error=error_msg,
        )
        sys.exit(0)
    except OSError as exc:
        elapsed_ms = (time.monotonic() - t0) * 1000
        error_msg = f"failed to run nunchi-channel: {exc}"
        _write_receipt(
            session_id=session_id,
            chat_id=chat_id,
            trigger_event=trigger_event,
            history_len=len(history_events),
            verdict=None,
            silent=None,
            action="allow-gate-error",
            elapsed_ms=elapsed_ms,
            reasons=[],
            error=error_msg,
        )
        sys.exit(0)

    # Binary exited non-zero — fail open.
    if result.returncode != 0:
        error_msg = (result.stderr or "").strip() or f"nunchi-channel exited {result.returncode}"
        _write_receipt(
            session_id=session_id,
            chat_id=chat_id,
            trigger_event=trigger_event,
            history_len=len(history_events),
            verdict=None,
            silent=None,
            action="allow-gate-error",
            elapsed_ms=elapsed_ms,
            reasons=[],
            error=error_msg,
        )
        sys.exit(0)

    # Parse directive — fail open if unparseable.
    try:
        directive = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        error_msg = f"nunchi-channel returned invalid JSON: {exc}"
        _write_receipt(
            session_id=session_id,
            chat_id=chat_id,
            trigger_event=trigger_event,
            history_len=len(history_events),
            verdict=None,
            silent=None,
            action="allow-gate-error",
            elapsed_ms=elapsed_ms,
            reasons=[],
            error=error_msg,
        )
        sys.exit(0)

    # Validate the directive SHAPE before trusting any field (parity with the
    # Codex hook). Valid JSON is not a valid directive: a list crashes .get(),
    # an empty object "admits" nothing-in-particular, and a contradictory
    # silent flag would forge a PASS out of a SPEAK. All malformed shapes fail
    # open with a receipt — never a crash, never a fabricated verdict.
    def _malformed(detail: str) -> None:
        _write_receipt(
            session_id=session_id,
            chat_id=chat_id,
            trigger_event=trigger_event,
            history_len=len(history_events),
            verdict=None,
            silent=None,
            action="allow-gate-error",
            elapsed_ms=elapsed_ms,
            reasons=[],
            error=f"nunchi-channel returned a malformed directive: {detail}",
        )
        sys.exit(0)

    if not isinstance(directive, dict):
        _malformed(f"expected an object, got {type(directive).__name__}")
    verdict: str = directive.get("verdict", "")
    if verdict not in ("PASS", "ACK", "ASK", "SPEAK"):
        _malformed(f"unknown verdict {verdict!r}")
    # `silent` must be an actual boolean that agrees with the verdict. bool()
    # coercion is forbidden here: bool("false") is True, which forged blocks
    # out of string-typed flags (review finding, 2026-07-10). Absence is not
    # contradiction — it defaults to agreeing.
    silent_raw = directive.get("silent", verdict == "PASS")
    if not isinstance(silent_raw, bool):
        _malformed(f"silent is {type(silent_raw).__name__}, expected boolean")
    silent: bool = silent_raw
    if silent != (verdict == "PASS"):
        _malformed(f"silent={silent!r} contradicts verdict {verdict!r}")
    reasons_raw = directive.get("reasons", [])
    if not isinstance(reasons_raw, list):
        _malformed(f"reasons is {type(reasons_raw).__name__}, expected list")
    reasons: list[str] = [str(r) for r in reasons_raw]

    # Decision provenance for every gate-judged receipt (the eval arm joins on
    # these; a defer receipt without its numbers cannot be swept).
    provenance: dict = {
        "request_id": directive.get("request_id"),
        "classifier_model": directive.get("classifier_model"),
        "envelope_sha256": hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16],
    }

    # PASS → the gate wants to silence this turn.
    if verdict == "PASS":
        # DEFER: a small fast gate may only silence what it can confidently
        # judge. On an *uncertain* PASS it abstains — the turn goes to the
        # agent's own model with the hesitation noted, and the agent may still
        # choose silence. No second classifier; the "bigger model" is the agent.
        #
        # Hard suppression requires a complete, finite, correctly typed
        # confidence vector. Broken evidence is not confidence: with DEFER on
        # (default) a PASS whose confidences are missing/partial/non-finite
        # ABSTAINS with the malformation receipted. NUNCHI_DEFER=off is the
        # operator's explicit hard mode and keeps its meaning: every PASS
        # blocks.
        margin = _defer_margin()
        conf_raw = directive.get("confidences")
        malformation = _confidence_malformation(conf_raw)
        if _DEFER_ENABLED and malformation is not None:
            _write_receipt(
                session_id=session_id,
                chat_id=chat_id,
                trigger_event=trigger_event,
                history_len=len(history_events),
                verdict=verdict,
                silent=silent,
                action="defer-malformed-confidence",
                elapsed_ms=elapsed_ms,
                reasons=reasons,
                error=None,
                extra={
                    **provenance,
                    "confidences": conf_raw if isinstance(conf_raw, dict) else None,
                    "confidence_malformation": malformation,
                    "defer_margin": margin,
                    "defer_enabled": True,
                },
            )
            note = (
                f"nunchi: the gate returned PASS on message "
                f"{trigger_event['message_id']} from {trigger_event['author']}, "
                f"but its confidence evidence is unusable ({malformation}). "
                "Suppression requires evidence, so the gate abstains. Read the "
                "room with your own judgment — replying and staying silent are "
                "both fine outcomes; if you stay silent, simply send nothing "
                "this turn."
            )
            print(_context_output(note))
            sys.exit(0)
        if _DEFER_ENABLED and malformation is None and _uncertain_pass(conf_raw, margin):
            _write_receipt(
                session_id=session_id,
                chat_id=chat_id,
                trigger_event=trigger_event,
                history_len=len(history_events),
                verdict=verdict,
                silent=silent,
                action="defer-uncertain-pass",
                elapsed_ms=elapsed_ms,
                reasons=reasons,
                error=None,
                extra={
                    **provenance,
                    "confidences": conf_raw,
                    "defer_margin": margin,
                    "defer_enabled": True,
                },
            )
            note = (
                f"nunchi: the gate leaned PASS on message "
                f"{trigger_event['message_id']} from {trigger_event['author']} "
                f"but not confidently (confidences: {json.dumps(conf_raw)}). It "
                "abstains rather than silence you. Read the room with your own "
                "judgment — replying and staying silent are both fine outcomes; "
                "if you stay silent, simply send nothing this turn."
            )
            print(_context_output(note))
            sys.exit(0)

        first_reason = (reasons[0] if reasons else "not this agent's turn").rstrip(".")
        block_reason = f"nunchi gate: PASS — {first_reason}."
        _write_receipt(
            session_id=session_id,
            chat_id=chat_id,
            trigger_event=trigger_event,
            history_len=len(history_events),
            verdict=verdict,
            silent=silent,
            action="block-pass",
            elapsed_ms=elapsed_ms,
            reasons=reasons,
            error=None,
            extra={
                **provenance,
                "confidences": directive.get("confidences") or {},
                "defer_margin": _defer_margin(),
                "defer_enabled": _DEFER_ENABLED,
            },
        )
        print(_block_output(block_reason))
        sys.exit(0)

    # SPEAK / ACK / ASK → admit. The admission note travels with the turn so
    # the composition stays anchored to the message it answers, even if later
    # room lines land while the agent is composing.
    _write_receipt(
        session_id=session_id,
        chat_id=chat_id,
        trigger_event=trigger_event,
        history_len=len(history_events),
        verdict=verdict,
        silent=silent,
        action=f"allow-{verdict.lower()}",
        elapsed_ms=elapsed_ms,
        reasons=reasons,
        error=None,
        extra=provenance,
    )
    note = (
        f"nunchi: admitted ({verdict}) — this turn answers message "
        f"{trigger_event['message_id']} from {trigger_event['author']}. "
        "The gate judged only that a turn is open; what you say, and whether you "
        "say anything at all, is yours."
    )
    print(_context_output(note))
    sys.exit(0)


def _input_error_receipt(session_id: str, detail: str) -> None:
    _write_receipt(
        session_id=session_id,
        chat_id="",
        trigger_event=None,
        history_len=0,
        verdict=None,
        silent=None,
        action="allow-input-error",
        elapsed_ms=0.0,
        reasons=[],
        error=detail,
    )


def main() -> None:
    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Malformed stdin — fail open, no receipt (nothing useful to log).
        sys.exit(0)

    if not isinstance(hook_input, dict):
        sys.exit(0)

    session_id = hook_input.get("session_id", "")
    if not isinstance(session_id, str):
        session_id = ""
    # Present-but-mistyped fields fail open WITH telemetry (round-2 finding:
    # prompt=null crashed with exit 1 and no receipt).
    prompt = hook_input.get("prompt", "")
    if not isinstance(prompt, str):
        _input_error_receipt(session_id, f"prompt is {type(prompt).__name__}, expected string")
        sys.exit(0)
    transcript_path = hook_input.get("transcript_path", "")
    if not isinstance(transcript_path, str):
        _input_error_receipt(
            session_id, f"transcript_path is {type(transcript_path).__name__}, expected string"
        )
        transcript_path = ""

    try:
        _run_gate(session_id, prompt, transcript_path)
    except SystemExit:
        raise
    except Exception as exc:  # the documented contract: ALWAYS exit 0, receipted
        try:
            _write_receipt(
                session_id=session_id,
                chat_id="",
                trigger_event=None,
                history_len=0,
                verdict=None,
                silent=None,
                action="allow-hook-error",
                elapsed_ms=0.0,
                reasons=[],
                error=f"unhandled hook error ({type(exc).__name__}): {exc}",
            )
        except Exception:
            pass
        sys.exit(0)


if __name__ == "__main__":
    main()
