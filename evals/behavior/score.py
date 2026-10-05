"""Grade what the room saw at a moment.

Attention first decides one of:

- `stay_quiet`: attention suppressed it, or the transport kept the
  participant's own event from waking it;
- `mhm`: attention chose ACK and Nunchi reacted for the agent;
- `woken`: the agent got a turn (WAKE, DEFER, or a provider error under the
  default wake-on-error policy);
- `unsupported`: today's V2 has no route for this moment (a pause).

When the agent's turn is simulated, a woken agent's own move replaces
`woken`: `speak` (a message or reply), `mhm` (its own reaction),
`stay_quiet` (it chose silence), or `other` (anything else, such as a
privileged proposal).

Each run gets two grades:

- `visible`: `fits`, `miss`, or `unlisted` for the move the room saw;
  `agent-decides` when the agent was woken but not simulated. Staying quiet
  also fits where waiting does, since nothing looks again yet.
- `step1`: from attention alone. `ok`, `over-suppress` (suppressed something
  step 1 must pass, so the agent never saw it), or `over-wake` (woke for
  something step 1 may suppress, which costs one turn).
"""

from __future__ import annotations

from typing import Any, Mapping

from .scene import Moment


def visible_result(decision: Mapping[str, Any] | None, *, transport_self: bool = False) -> str:
    if transport_self:
        return "stay_quiet"
    if decision is None:
        return "unsupported"
    status = decision.get("status")
    if status == "ok":
        effective = decision["effective_disposition"]
        if effective == "SUPPRESS":
            return "stay_quiet"
        if effective == "ACK":
            return "mhm"
        return "woken"
    if status == "error" and decision.get("wake_action") == "NO_WAKE":
        return "stay_quiet"
    # bypass, and errors under the default wake-on-error policy.
    return "woken"


def grade(moment: Moment, result: str, *, attention: str | None = None) -> dict[str, str]:
    """Grade the move the room saw (`result`) and what attention did."""

    attention = attention or result
    if result == "unsupported":
        return {"visible": "unsupported", "step1": "unsupported"}
    if result == "woken":
        visible = "agent-decides"
    elif result in moment.fitting or (result == "stay_quiet" and "wait" in moment.fitting):
        visible = "fits"
    elif moment.miss_reason(result) is not None:
        visible = "miss"
    else:
        visible = "unlisted"
    if attention == "stay_quiet":
        step1 = "over-suppress" if moment.step1 == "pass" else "ok"
    else:
        step1 = "over-wake" if moment.step1 == "suppress" else "ok"
    return {"visible": visible, "step1": step1}


def collective_silence(results: list[str]) -> bool:
    """Every participant stayed quiet at the same moment."""

    return bool(results) and all(result == "stay_quiet" for result in results)


def pile_on(results: list[str]) -> bool:
    """Every participant spoke at the same moment, where one voice was enough."""

    return len(results) > 1 and all(result == "speak" for result in results)


def symbol(item: Mapping[str, Any]) -> str:
    """One letter for one run.

    Q quiet by attention, q quiet by the agent's choice, M Nunchi's mhm,
    m the agent's own mhm, S the agent spoke, O another agent action,
    W woken (agent not simulated), E an error, - not supported today.
    """

    if item.get("provider_error"):
        return "E"
    result, by = item["result"], item.get("by")
    if result == "unsupported":
        return "-"
    if result == "woken":
        return "W"
    if result == "stay_quiet":
        return "q" if by == "agent" else "Q"
    if result == "mhm":
        return "m" if by == "agent" else "M"
    if result == "speak":
        return "S"
    return "O"


def cell(results: list[dict[str, Any]]) -> str:
    """Compact per-run outcomes for one moment and one model, such as "QqS!".

    A trailing "!" marks a clear miss in any run, "?" an unlisted move.
    """

    text = "".join(symbol(item) for item in results)
    grades = {item["grade"]["visible"] for item in results}
    if "miss" in grades:
        text += "!"
    elif "unlisted" in grades:
        text += "?"
    return text
