"""Deterministic pre-classifier fast-path for certain-from-the-envelope cases.

This module resolves only the handful of admission cases that are provably
certain from *structured* envelope signals — never from fuzzy text. It exists to
cut per-turn provider cost/latency for the unambiguous "not this agent's turn"
cases, while escalating everything else to the LLM classifier untouched.

Hard constraint: this short-circuit uses ONLY structured, deterministic signals
(explicit ``<@id>`` mention tokens, author identity, exact content equality). It
performs NO substring or keyword matching against natural-language content — the
substring/keyword traps are exactly what the product classifier exists to catch,
so the fast-path must never reintroduce them. When any precondition is missing or
the situation is at all ambiguous, it returns ``None`` to escalate.
"""

from __future__ import annotations

import re
from typing import Any

from .models import AdmissionRequest

FASTPATH_PROVIDER = "fastpath"

# Discord-style explicit mention tokens: <@123>, <@!123> (nickname form). Only a
# fully structured token counts — bare numbers or names in prose never match, so
# this can never collapse into substring/keyword guessing.
_MENTION_PATTERN = re.compile(r"<@!?(\d+)>")

# A short-circuit always lands on PASS: the fast-path only ever decides "not this
# agent's turn", never an affirmative SPEAK/ACK/ASK (those require judgement).
_PASS_CONFIDENCES = {"PASS": 1.0, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.0}


def _agent_identifiers(agent: dict[str, Any] | None) -> set[str]:
    """Return the structured ids that address this agent (id + mention_id).

    Non-string or empty values are ignored. An empty set means we cannot
    determine addressing and therefore must not short-circuit.
    """
    if not isinstance(agent, dict):
        return set()
    identifiers: set[str] = set()
    for key in ("id", "mention_id"):
        value = agent.get(key)
        if isinstance(value, str) and value.strip():
            identifiers.add(value)
    return identifiers


def _pass_result(request: AdmissionRequest, *, context_checked: list[str], reason: str) -> dict[str, Any]:
    """Build a schema-identical PASS result dict for a short-circuit.

    Mirrors the shape ``core.evaluate`` returns via
    ``AdmissionResult.to_dict()``. ``classifier_model`` is intentionally omitted
    (equivalent to None) because no model was consulted.
    """
    payload: dict[str, Any] = {
        "classifier": "product",
        "classifier_provider": FASTPATH_PROVIDER,
        "verdict": "PASS",
        "confidences": dict(_PASS_CONFIDENCES),
        "context_checked": context_checked,
        "reasons": [reason],
    }
    if request.request_id is not None:
        payload["request_id"] = request.request_id
    return payload


def _mention_elsewhere_result(request: AdmissionRequest) -> dict[str, Any] | None:
    """PASS when the trigger explicitly @mentions others but not this agent.

    Certainty conditions (all required):
      - the agent's structured ids are known (id/mention_id present),
      - the trigger content contains one or more explicit ``<@id>`` tokens,
      - none of those mentioned ids is this agent's id/mention_id.

    If there are no mentions at all, this is NOT a short-circuit: the message may
    be room-addressed, which only the classifier can judge.
    """
    agent_ids = _agent_identifiers(request.agent)
    if not agent_ids:
        return None

    mentioned = set(_MENTION_PATTERN.findall(request.trigger.content))
    if not mentioned:
        return None

    if agent_ids.intersection(mentioned):
        return None

    return _pass_result(
        request,
        context_checked=[request.trigger.reference],
        reason="Trigger @mentions other participants only; this agent is not addressed.",
    )


def _self_caused_result(request: AdmissionRequest) -> dict[str, Any] | None:
    """PASS when the trigger is this agent's own message echoed back.

    Two structured signals, either sufficient:
      - the trigger's author is exactly this agent's id, or
      - the trigger content exactly equals (after strip) the content of some
        context item authored by this agent's id.

    Requires a known agent id; no fuzzy comparison is performed.
    """
    agent = request.agent
    if not isinstance(agent, dict):
        return None
    agent_id = agent.get("id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        return None

    if request.trigger.author is not None and request.trigger.author == agent_id:
        return _pass_result(
            request,
            context_checked=[request.trigger.reference],
            reason="Trigger is authored by this agent (self-caused echo).",
        )

    trigger_text = request.trigger.content.strip()
    for item in request.context:
        if item.author == agent_id and item.content.strip() == trigger_text:
            return _pass_result(
                request,
                context_checked=[request.trigger.reference, item.reference],
                reason="Trigger exactly echoes this agent's own prior context message (self-caused).",
            )

    return None


def fast_verdict(request: AdmissionRequest) -> dict[str, Any] | None:
    """Resolve only certain cases without an LLM call; else return None.

    Returns a schema-valid PASS result dict for a deterministic short-circuit, or
    ``None`` to escalate to the provider classifier. Self-caused echo is checked
    before mention addressing because an echoed self-message is unambiguous
    regardless of who else it mentions.
    """
    return _self_caused_result(request) or _mention_elsewhere_result(request)
