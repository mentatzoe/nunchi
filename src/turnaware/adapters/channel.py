"""Channel-local admission adapter.

This adapter bridges any turn-aware chat surface to the TurnAware core. It takes
the channel-local inputs a participant agent already has — the triggering
message, the recent transcript, and the agent's own identity — maps them to a
TurnAware admission request, runs the callable core, and routes the verdict
back into the host's action model.

It stays strictly inside the admission boundary: it returns a verdict and a
*run-shape* (what kind of turn is warranted), never composed reply prose. The
contract is transport-neutral — the host branches on ``silent``/``verdict`` and
owns how it stays quiet — so nothing here depends on a particular chat platform.

Some transports suppress a send by recognizing a magic final-output string.
That is the host's convention, not TurnAware's: supply your own token via
:meth:`ChannelGateResult.silent_token` (or the CLI's ``--silent-token``). The
`CC_CONNECT_SILENT_PASS` constant and ``--format cc-connect`` are just the
cc-connect *preset* of that mechanism — one named transport among many, with no
special status. Any other host ignores tokens entirely and branches on
``result.silent``.

Design lineage: pilot-bot `before-you-respond.md`, the open-floor pilot's
channel protocol. The core now judges by plain social sense; that pilot
doctrine survives as `profiles/open-floor.md`, supplied via ``pinned_rules``
by rooms that want it.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Callable, Literal

from ..core import evaluate
from ..errors import TurnAwareError, ValidationError

# The cc-connect preset suppression token (matches its core/message.go
# SilentPassSentinel). It has no privileged status — it is one value you may pass
# to silent_token()/--silent-token. Hosts on other transports supply their own.
SILENT_PASS_SENTINEL = "CC_CONNECT_SILENT_PASS"

FailPolicy = Literal["open", "closed", "raise"]

# Run-shape guidance per verdict. These describe the SHAPE of the turn the host
# should take; they are not, and must not become, composed replies.
RUN_SHAPE = {
    "SPEAK": "Produce one normal participant turn (1-3 short paragraphs of plain prose).",
    "ASK": "Ask the operator exactly one blocking clarifying question.",
    "ACK": "Emit one short presence signal (an emoji or a single sentence). No follow-up content.",
    "PASS": "Stay silent. Post nothing to the channel for this turn.",
}

# Author-kind normalization. The classifier reasons about who spoke — operator
# vs peer vs this agent's own earlier turns — so every transcript line is
# tagged with a normalized role.
_ROLE_ALIASES = {
    "human": "operator",
    "operator": "operator",
    "user": "operator",
    "peer_bot": "peer",
    "peer": "peer",
    "bot": "peer",
    "self": "self",
}


def _normalize_role(author_kind: str | None) -> str | None:
    if author_kind is None:
        return None
    return _ROLE_ALIASES.get(author_kind.strip().lower(), "peer")


@dataclass(frozen=True)
class ChannelMessage:
    """One message on the channel surface (trigger or transcript line)."""

    content: str
    author: str | None = None
    author_kind: str | None = None  # human|operator|peer_bot|peer|self
    message_id: str | None = None
    timestamp: str | None = None


@dataclass(frozen=True)
class ChannelGateResult:
    """The adapter's decision for one trigger, ready to route into the host.

    The transport-neutral contract is ``verdict`` + ``silent`` + ``run_shape``:
    if ``silent`` is True the host posts nothing; otherwise it composes one turn
    in the ``run_shape`` (the adapter never writes the reply itself). Nothing
    here is tied to any particular chat transport. The cc-connect sentinel is
    available via :meth:`cc_connect_sentinel` for that specific deployment only.
    """

    verdict: str
    silent: bool
    run_shape: str
    reasons: tuple[str, ...]
    confidences: dict[str, float]
    context_checked: tuple[str, ...]
    request_id: str | None
    classifier_model: str | None
    degraded: bool = False  # True when a fail policy produced this, not the classifier
    error: str | None = None  # off-surface telemetry only; never shown in-room

    def silent_token(self, token: str) -> str:
        """Generic suppression helper: return ``token`` when silent, else "".

        A transport that suppresses a send by recognizing a magic final-output
        string supplies its own ``token`` here. The token is the host's
        convention, not TurnAware's — most hosts never need this and just branch
        on ``silent``.
        """
        return token if self.silent else ""

    def cc_connect_sentinel(self) -> str:
        """cc-connect preset of :meth:`silent_token` (`CC_CONNECT_SILENT_PASS`)."""
        return self.silent_token(SILENT_PASS_SENTINEL)


def _coerce_message(value: Any, name: str) -> ChannelMessage:
    if isinstance(value, ChannelMessage):
        return value
    if not isinstance(value, dict):
        raise ValidationError(f"{name} must be an object or ChannelMessage")
    content = value.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValidationError(f"{name}.content must be a non-empty string")
    return ChannelMessage(
        content=content,
        author=value.get("author"),
        author_kind=value.get("author_kind"),
        message_id=value.get("message_id") or value.get("id"),
        timestamp=value.get("timestamp"),
    )


def build_request(
    trigger: ChannelMessage | dict,
    history: list[ChannelMessage | dict] | None = None,
    *,
    agent_id: str,
    agent_role: str | None = None,
    agent_mention_id: str | None = None,
    surface: dict[str, Any] | None = None,
    pinned_rules: str | None = None,
) -> dict[str, Any]:
    """Map channel-local inputs to a TurnAware admission request envelope.

    Transcript lines become ordered context items tagged with the speaker's
    normalized role (operator/peer/self); a line authored by ``agent_id`` is
    tagged ``self`` so the classifier can apply Self-caused / Duplicate
    suppression. ``agent_mention_id`` (the agent's @mention handle on the
    surface) is threaded into the envelope so the addressing rule can tell
    whether an @mention targets this agent. Optional ``pinned_rules`` (the
    channel's governance text) is supplied as a context item so the verdict is
    channel-aware.
    """
    trig = _coerce_message(trigger, "trigger")
    history = history or []

    context: list[dict[str, Any]] = []
    if pinned_rules and pinned_rules.strip():
        context.append(
            {
                "id": "pinned-rules",
                "type": "pinned-rules",
                "content": pinned_rules.strip(),
            }
        )

    for index, raw in enumerate(history, start=1):
        msg = _coerce_message(raw, f"history[{index}]")
        role = _normalize_role(msg.author_kind)
        if role is None and msg.author is not None and msg.author == agent_id:
            role = "self"
        context.append(
            {
                "id": msg.message_id or f"msg-{index}",
                "type": role or "message",
                "author": msg.author,
                "content": msg.content,
                "timestamp": msg.timestamp,
            }
        )

    agent: dict[str, Any] = {"id": agent_id}
    if agent_role:
        agent["role"] = agent_role
    if agent_mention_id:
        agent["mention_id"] = agent_mention_id

    request: dict[str, Any] = {
        "trigger": {
            "id": trig.message_id or "trigger",
            "author": trig.author,
            "content": trig.content,
            "timestamp": trig.timestamp,
        },
        "context": context,
        "agent": agent,
        "surface": surface or {"type": "channel"},
    }
    if trig.message_id:
        request["request_id"] = trig.message_id
    return request


def gate(
    trigger: ChannelMessage | dict,
    history: list[ChannelMessage | dict] | None = None,
    *,
    agent_id: str,
    agent_role: str | None = None,
    agent_mention_id: str | None = None,
    surface: dict[str, Any] | None = None,
    pinned_rules: str | None = None,
    fail_policy: FailPolicy = "open",
    evaluate_fn: Callable[..., dict] | None = None,
) -> ChannelGateResult:
    """Run one trigger through the admission gate and return a routed result.

    ``fail_policy`` governs what happens when the classifier itself fails
    (provider down, bad config, malformed output):

    - ``"open"`` (default): degrade to SPEAK. Silently swallowing a turn is the
      worse failure for a participant agent, so an unavailable gate lets the
      turn through rather than dropping it.
    - ``"closed"``: degrade to PASS (emit the sentinel, stay silent). Use when
      noise suppression matters more than never missing a turn.
    - ``"raise"``: re-raise the underlying error for the host to handle.

    Classifier errors are returned as off-surface telemetry (``error``,
    ``degraded``); they never enter the conversation.
    """
    request = build_request(
        trigger,
        history,
        agent_id=agent_id,
        agent_role=agent_role,
        agent_mention_id=agent_mention_id,
        surface=surface,
        pinned_rules=pinned_rules,
    )
    request_id = request.get("request_id")
    # Resolve at call time (not as a default arg) so the module-level `evaluate`
    # stays patchable by callers and tests.
    run = evaluate_fn if evaluate_fn is not None else evaluate
    try:
        result = run(request)
    except (TurnAwareError, ValidationError) as exc:
        if fail_policy == "raise":
            raise
        verdict = "SPEAK" if fail_policy == "open" else "PASS"
        return _build_result(
            verdict=verdict,
            reasons=(f"admission gate unavailable; fail-{fail_policy} -> {verdict}",),
            confidences={v: 0.0 for v in ("PASS", "ACK", "ASK", "SPEAK")},
            context_checked=(),
            request_id=request_id,
            classifier_model=None,
            degraded=True,
            error=str(exc),
        )

    return _build_result(
        verdict=result["verdict"],
        reasons=tuple(result.get("reasons", ())),
        confidences=dict(result.get("confidences", {})),
        context_checked=tuple(result.get("context_checked", ())),
        request_id=result.get("request_id", request_id),
        classifier_model=result.get("classifier_model"),
    )


def _build_result(
    *,
    verdict: str,
    reasons: tuple[str, ...],
    confidences: dict[str, float],
    context_checked: tuple[str, ...],
    request_id: str | None,
    classifier_model: str | None,
    degraded: bool = False,
    error: str | None = None,
) -> ChannelGateResult:
    return ChannelGateResult(
        verdict=verdict,
        silent=verdict == "PASS",
        run_shape=RUN_SHAPE[verdict],
        reasons=reasons,
        confidences=confidences,
        context_checked=context_checked,
        request_id=request_id,
        classifier_model=classifier_model,
        degraded=degraded,
        error=error,
    )


# --- CLI: a transport-neutral subprocess contract for any host ---


def _read_payload(argv: list[str]) -> dict:
    import argparse

    parser = argparse.ArgumentParser(
        prog="turnaware.adapters.channel",
        description="Channel-local admission gate. Reads a JSON payload "
        "(trigger, history, agent, [surface], [pinned_rules], [fail_policy]) "
        "from --input or stdin and prints a transport-neutral JSON directive "
        "(verdict + silent + run_shape). To suppress via a magic final-output "
        "string, give your platform's token with --silent-token (or use the "
        "--format cc-connect preset).",
    )
    parser.add_argument("--input", default=None, help="payload JSON file (default: stdin)")
    parser.add_argument(
        "--silent-token",
        default=None,
        metavar="STR",
        help="on PASS, print exactly STR (your transport's suppression sentinel) "
        "instead of JSON. Generic: any platform supplies its own token.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "cc-connect"],
        default="json",
        help="json (default): always a JSON directive, transport-neutral. "
        "cc-connect: preset of --silent-token CC_CONNECT_SILENT_PASS.",
    )
    args = parser.parse_args(argv)
    # Resolve the suppression token: an explicit --silent-token wins; the
    # cc-connect format is just a named preset of one. Default None -> JSON only.
    silent_token = args.silent_token
    if silent_token is None and args.format == "cc-connect":
        silent_token = SILENT_PASS_SENTINEL
    raw = open(args.input).read() if args.input else sys.stdin.read()
    try:
        return {"payload": json.loads(raw), "silent_token": silent_token}
    except json.JSONDecodeError as exc:
        raise ValidationError(f"payload must be valid JSON: {exc}") from exc


def _directive_json(result: ChannelGateResult) -> str:
    return json.dumps(
        {
            "verdict": result.verdict,
            "silent": result.silent,
            "run_shape": result.run_shape,
            "reasons": list(result.reasons),
            "confidences": result.confidences,
            "context_checked": list(result.context_checked),
            "request_id": result.request_id,
            "classifier_model": result.classifier_model,
            "degraded": result.degraded,
        },
        sort_keys=True,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry. Exit 0 on a routed verdict; 2 on a malformed payload.

    Default output is a transport-neutral JSON directive for every verdict — the
    host branches on ``silent``/``verdict`` and owns how it stays quiet, so the
    CLI carries no dependency on any particular chat platform. ``--silent-token``
    (or the ``--format cc-connect`` preset) opts into printing a transport's
    suppression sentinel on PASS.
    """
    try:
        parsed = _read_payload(sys.argv[1:] if argv is None else argv)
        payload, silent_token = parsed["payload"], parsed["silent_token"]
        if not isinstance(payload, dict):
            raise ValidationError("payload must be a JSON object")
        agent = payload.get("agent") or {}
        agent_id = agent.get("id") if isinstance(agent, dict) else None
        if not agent_id:
            raise ValidationError("payload.agent.id is required")
        result = gate(
            payload.get("trigger"),
            payload.get("history") or [],
            agent_id=agent_id,
            agent_role=agent.get("role") if isinstance(agent, dict) else None,
            agent_mention_id=agent.get("mention_id") if isinstance(agent, dict) else None,
            surface=payload.get("surface"),
            pinned_rules=payload.get("pinned_rules"),
            fail_policy=payload.get("fail_policy", "open"),
        )
    except (ValidationError, TurnAwareError) as exc:
        print(f"channel adapter error: {exc}", file=sys.stderr)
        return 2

    if result.degraded:
        # Off-surface telemetry: the host sees the directive on stdout; the
        # reason the gate degraded goes to stderr, never into the room.
        print(f"channel adapter degraded ({result.error})", file=sys.stderr)

    if silent_token is not None and result.silent:
        # The host opted into suppression-by-sentinel; print its token verbatim.
        print(result.silent_token(silent_token))
    else:
        print(_directive_json(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
