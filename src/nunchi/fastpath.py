"""Deterministic pre-classifier fast-path for certain-from-the-envelope cases.

This module resolves only the handful of admission cases that are provably
certain from *structured* envelope signals — never from fuzzy text. It exists to
cut per-turn provider cost/latency for the unambiguous "not this agent's turn"
cases, while escalating everything else to the LLM classifier untouched.

Hard constraint: this short-circuit uses ONLY structured, deterministic signals
(author identity, exact content equality). It performs NO substring or keyword
matching against natural-language content — the substring/keyword traps are
exactly what the product classifier exists to catch, so the fast-path must
never reintroduce them. When any precondition is missing or the situation is at
all ambiguous, it returns ``None`` to escalate.

The bar for a short-circuit (room-agreed, 2026-07-10): a deterministic rule may
hard-PASS only when it can PROVE the turn is not this agent's. A foreign
``<@id>`` mention token cannot meet that bar — it is evidence that another
participant appears in the message, not proof the floor went to them. The live
canary: the operator replied to this agent's own message, correcting it, while
referentially @mentioning a peer who featured in the anecdote — and the old
mention-elsewhere rule stamped ``PASS 1.0`` without any model ever reading it.
Referential mention ≠ floor assignment; that distinction is semantic, so it
belongs to the classifier. The only remaining short-circuit is self-caused
echo, where exclusivity is structural: an agent's own message needs no reply
from itself, whoever it mentions.
"""

from __future__ import annotations

from typing import Any

from .models import AdmissionRequest

FASTPATH_PROVIDER = "fastpath"

# A short-circuit always lands on PASS: the fast-path only ever decides "not this
# agent's turn", never an affirmative SPEAK/ACK/ASK (those require judgement).
# A fast-path PASS carries confidence 1.0, which sits above the DEFER margin by
# construction — so it must only ever be minted where certainty is REAL, or it
# manufactures exactly the overconfident silence DEFER exists to prevent.
_PASS_CONFIDENCES = {"PASS": 1.0, "ACK": 0.0, "ASK": 0.0, "SPEAK": 0.0}


def _agent_aliases(agent: dict[str, Any] | None) -> set[str]:
    """Return the agent's validated ``aliases`` entries as a set.

    ``validate_request`` has already rejected non-string/blank entries, but a
    defensive isinstance check keeps this safe for direct callers too.
    """
    if not isinstance(agent, dict):
        return set()
    aliases = agent.get("aliases")
    if not isinstance(aliases, list):
        return set()
    return {alias for alias in aliases if isinstance(alias, str) and alias.strip()}


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


def _self_caused_result(request: AdmissionRequest) -> dict[str, Any] | None:
    """PASS when the trigger is this agent's own message echoed back.

    Two structured signals, either sufficient:
      - the trigger's author is exactly this agent's id (or one of its
        declared ``aliases`` — a relay may report the author under the
        agent's display or profile name rather than its configured id), or
      - the trigger content exactly equals (after strip) the content of some
        context item authored by this agent's id or one of its aliases.

    Requires a known agent id; no fuzzy comparison is performed.
    ``mention_id`` deliberately does NOT join the self-identity set here:
    without aliases this path must behave exactly as it always has (author
    compared against ``id`` alone). An operator who wants the mention token
    recognized as a self author lists it in ``aliases``.
    """
    agent = request.agent
    if not isinstance(agent, dict):
        return None
    agent_id = agent.get("id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        return None
    self_identities = {agent_id} | _agent_aliases(agent)

    if request.trigger.author is not None and request.trigger.author in self_identities:
        return _pass_result(
            request,
            context_checked=[request.trigger.reference],
            reason="Trigger is authored by this agent (self-caused echo).",
        )

    trigger_text = request.trigger.content.strip()
    for item in request.context:
        if item.author in self_identities and item.content.strip() == trigger_text:
            return _pass_result(
                request,
                context_checked=[request.trigger.reference, item.reference],
                reason="Trigger exactly echoes this agent's own prior context message (self-caused).",
            )

    return None


def fast_verdict(request: AdmissionRequest) -> dict[str, Any] | None:
    """Resolve only certain cases without an LLM call; else return None.

    Returns a schema-valid PASS result dict for a deterministic short-circuit, or
    ``None`` to escalate to the provider classifier. The sole short-circuit is
    self-caused echo. The former mention-elsewhere rule was removed 2026-07-10:
    a foreign @mention is referential evidence, not proof of exclusive
    targeting, and it hard-PASSed the operator's direct correction of this
    agent at confidence 1.0 without semantic review (see module docstring).
    """
    return _self_caused_result(request)
