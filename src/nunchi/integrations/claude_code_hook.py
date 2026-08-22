"""The Claude Code hook client for the Nunchi session gate.

This runs once per hook event, inside the operator's own Claude Code session,
so it is deliberately tiny and imports nothing from ``nunchi``.  Its whole job
is to hand one hook payload to the gate and forward one answer back, and to
decide what happens when it cannot.

Fail direction is per event and is enforced *here*, at the process boundary,
not only inside the gate.  "Configured" means the gate socket path is set; when
it is not, this integration is inert and every event passes through.

``user-prompt-submit``
    fails **closed** for a room delivery.  A missing gate, a refused connect, a
    short read, a malformed answer, or any unexpected exception must block the
    prompt.  Every fail-closed safeguard that matters — foreign-room refusal,
    drift blocking, unroutable-event handling — lives inside the gate, so a
    gate that cannot run must not be able to let a room prompt through.
    Operator-typed prompts are not room deliveries and always pass.

``pre-tool``
    fails **closed for a room-effect call only**.  A guard that cannot run
    must deny a native send rather than wave it through, but a dead gate must
    not take the operator's own session offline by denying ``Bash``, ``Read``,
    or ``Edit`` — none of which can reach the room.  Classifying that without
    the gate is why this module carries its own deliberately wide room-effect
    matcher.

``post-tool``, ``stop``, ``session-start``, ``session-end``
    fail **open**.  None of them can admit anything on their own, and a broken
    one must not trap or deafen the participant.  A missing receipt stays an
    honest gap rather than becoming a stuck session.

The gate's answer is validated against this module's own idea of the allowed
shapes before it is forwarded.  Exit 0 with well-formed JSON is not enough:
an empty document, a duplicate-keyed object, or an unsupported decision value
can all read as success while meaning nothing, and each is treated exactly
like a crash.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
from typing import Any

#: Where the gate listens.  Absent means Nunchi is not configured here.
SOCKET_ENVIRONMENT_VARIABLE = "NUNCHI_CLAUDE_CODE_GATE_SOCKET"

#: Hook events this client serves, and whether a failure blocks.
FAIL_CLOSED = ("user-prompt-submit", "pre-tool")
HOOK_EVENTS = FAIL_CLOSED + (
    "post-tool",
    "stop",
    "session-start",
    "session-end",
)

#: Process environment the gate is allowed to see.  These are the facts that
#: identify the runtime; nothing else is forwarded, so a hook cannot leak the
#: operator's wider environment into gate state or receipts.
_FORWARDED_ENVIRONMENT = (
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_EXECPATH",
    "CLAUDE_PID",
)

_CONNECT_SECONDS = 5.0

#: Claude Code aborts a UserPromptSubmit hook after 30 s by default and
#: **discards its output** — an aborted hook yields `outcome: "cancelled"`, not
#: a `blockingError`, so the prompt proceeds. The whole fail-closed guarantee
#: for a room delivery is this process emitting its block document, which it
#: can only do while it is still alive. So the prompt path gets its own budget
#: comfortably under that ceiling and blocks on expiry rather than waiting for
#: an answer nobody will read.
_PROMPT_EXCHANGE_SECONDS = 20.0

#: Everything else runs under the ordinary 600 s hook budget.
_EXCHANGE_SECONDS = 300.0


def _exchange_budget(event: str) -> float:
    return _PROMPT_EXCHANGE_SECONDS if event == "user-prompt-submit" else _EXCHANGE_SECONDS


def _strict_json(raw: str) -> Any:
    """Parse JSON, refusing duplicate keys and non-finite constants.

    A duplicate-keyed object silently resolves to its last value, so
    ``{"permissionDecision":"deny","permissionDecision":"allow"}`` reads as a
    denial and means an allow.  Refusing the shape outright removes the
    ambiguity rather than depending on which parser sees it.
    """

    def pairs(items):
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def reject(_name: str):
        raise ValueError("non-finite constant")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)


def _is_prompt_answer(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if set(value) == {"hookSpecificOutput"}:
        inner = value["hookSpecificOutput"]
        return (
            isinstance(inner, dict)
            and set(inner) == {"hookEventName", "additionalContext"}
            and inner["hookEventName"] == "UserPromptSubmit"
            and isinstance(inner["additionalContext"], str)
        )
    if set(value) == {"decision", "reason", "hookSpecificOutput"}:
        inner = value["hookSpecificOutput"]
        return (
            value["decision"] == "block"
            and isinstance(value["reason"], str)
            and isinstance(inner, dict)
            and set(inner) == {"hookEventName", "suppressOriginalPrompt"}
            and inner["hookEventName"] == "UserPromptSubmit"
            and inner["suppressOriginalPrompt"] is True
        )
    return False


def _is_tool_answer(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {"hookSpecificOutput"}:
        return False
    inner = value["hookSpecificOutput"]
    return (
        isinstance(inner, dict)
        and set(inner) == {
            "hookEventName",
            "permissionDecision",
            "permissionDecisionReason",
        }
        and inner["hookEventName"] == "PreToolUse"
        and inner["permissionDecision"] in ("allow", "deny")
        and isinstance(inner["permissionDecisionReason"], str)
    )


def blocked_prompt(reason: str) -> dict[str, Any]:
    return {
        "decision": "block",
        "reason": reason,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "suppressOriginalPrompt": True,
        },
    }


def denied_tool(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


#: A conservative room-effect matcher, duplicated from the gate on purpose.
#: When the gate is unreachable it is the only thing that can tell a send into
#: the room from an ordinary tool call. Keeping it here means a dead gate
#: denies exactly the calls that could reach the room, instead of disabling the
#: operator's entire session. It is deliberately *wider* than the gate's
#: matcher — matching anything that looks like a channel send — because over-
#: denying while the gate is down is safe and under-denying is not.
_ROOM_EFFECT_TOOL = re.compile(
    r"^mcp__[A-Za-z0-9_]*(?:discord|telegram|slack|matrix|channel)[A-Za-z0-9_]*"
    r"__(?:reply|react|edit_message|send|post)$"
)


def looks_like_room_effect(payload: Any) -> bool:
    """Whether this tool call could reach the room, judged without the gate."""

    name = payload.get("tool_name") if isinstance(payload, dict) else None
    return isinstance(name, str) and _ROOM_EFFECT_TOOL.match(name) is not None


def looks_like_room_delivery(payload: Any) -> bool:
    """Whether this prompt is a channel delivery rather than operator text.

    Deliberately generous: anything carrying a channel opener counts, so a
    malformed or truncated envelope is treated as a room delivery and fails
    closed.  Deciding *which* room it belongs to is the gate's job, not this
    client's.
    """

    prompt = payload.get("prompt") if isinstance(payload, dict) else None
    return isinstance(prompt, str) and "<channel" in prompt


def exchange(
    socket_path: str,
    request: dict[str, Any],
    *,
    budget: float = _EXCHANGE_SECONDS,
) -> dict[str, Any]:
    """Send one request to the gate and read exactly one answer."""

    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(_CONNECT_SECONDS)
    try:
        connection.connect(socket_path)
        connection.settimeout(budget)
        connection.sendall(
            json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n"
        )
        connection.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        try:
            connection.close()
        except OSError:
            pass
    answer = _strict_json(b"".join(chunks).decode("utf-8"))
    if not isinstance(answer, dict) or "output" not in answer:
        raise ValueError("gate answer has an unsupported shape")
    if answer.get("status") != "ok":
        # The gate reached no decision. That is distinct from a decision of
        # "no objection", which is a real answer with ``output: None``.
        raise ValueError("gate reported no decision")
    return answer


def run(event: str, payload: dict[str, Any], environ: dict[str, str]) -> tuple[int, str]:
    """Return ``(exit_code, stdout)`` for one hook invocation."""

    socket_path = (environ.get(SOCKET_ENVIRONMENT_VARIABLE) or "").strip()
    configured = bool(socket_path)
    fail_closed = event in FAIL_CLOSED and configured
    if event == "user-prompt-submit":
        # An operator-typed prompt is not a room delivery. It passes whether or
        # not the gate is reachable, because there is nothing to gate.
        fail_closed = fail_closed and looks_like_room_delivery(payload)
    elif event == "pre-tool":
        # Only a call that could reach the room needs the gate. Denying every
        # tool because the gate is down would take the operator's own session
        # offline to protect a room the call was never going to touch.
        fail_closed = fail_closed and looks_like_room_effect(payload)
    if not configured:
        return 0, ""

    try:
        answer = exchange(
            socket_path,
            budget=_exchange_budget(event),
            request={
                "schema_version": 1,
                "event": event,
                "payload": payload,
                "environment": {
                    name: environ[name]
                    for name in _FORWARDED_ENVIRONMENT
                    if name in environ
                },
            },
        )
    except Exception as exc:  # noqa: BLE001 - every failure has one direction
        return _unavailable(event, fail_closed, f"{type(exc).__name__}: {exc}")

    output = answer.get("output")
    if output is None:
        return int(answer.get("exit_code") or 0), ""
    valid = (
        _is_prompt_answer(output)
        if event == "user-prompt-submit"
        else _is_tool_answer(output)
        if event == "pre-tool"
        else isinstance(output, dict)
    )
    if not valid:
        return _unavailable(event, fail_closed, "gate produced an unsupported answer")
    return int(answer.get("exit_code") or 0), json.dumps(output, ensure_ascii=False)


def _unavailable(event: str, fail_closed: bool, reason: str) -> tuple[int, str]:
    if not fail_closed:
        sys.stderr.write(f"nunchi-claude-code: {event} unavailable ({reason})\n")
        return 0, ""
    sys.stderr.write(
        f"nunchi-claude-code: {event} gate unavailable ({reason}); failing closed\n"
    )
    if event == "user-prompt-submit":
        return 0, json.dumps(
            blocked_prompt(
                "The Nunchi gate for this room is unavailable, so this room "
                "event was not judged. Fix the gate, or unset "
                f"{SOCKET_ENVIRONMENT_VARIABLE} to run this session ungated."
            )
        )
    return 0, json.dumps(
        denied_tool(
            "The Nunchi gate for this room is unavailable, so this send "
            "cannot be attributed to an admitted turn; denying. Other tools "
            "are unaffected."
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nunchi-claude-code-hook")
    parser.add_argument("event", choices=HOOK_EVENTS)
    arguments = parser.parse_args(argv)
    environ = dict(os.environ)
    try:
        raw = sys.stdin.read() or "{}"
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        # A payload this process could not read is not an empty payload. An
        # empty one has no prompt and no tool name, which would switch the
        # fail-closed direction off and admit a delivery with no observation,
        # no attention call, and no record that it existed.
        return _unreadable_payload(arguments.event, environ)
    if not isinstance(payload, dict):
        return _unreadable_payload(arguments.event, environ)
    exit_code, stdout = run(arguments.event, payload, environ)
    if stdout:
        sys.stdout.write(stdout)
    return exit_code


def _unreadable_payload(event: str, environ: dict[str, str]) -> int:
    """Fail closed for the gating events when the payload cannot be read."""

    if not (environ.get(SOCKET_ENVIRONMENT_VARIABLE) or "").strip():
        return 0
    exit_code, stdout = _unavailable(event, event in FAIL_CLOSED, "unreadable payload")
    if stdout:
        sys.stdout.write(stdout)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
