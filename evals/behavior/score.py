"""Grade what today's V2 did at a moment.

Today's V2 makes one attention decision, so the visible result of a moment
is one of:

- `stay_quiet`: attention suppressed it, or the transport kept the
  participant's own event from waking it;
- `mhm`: attention chose ACK and Nunchi reacted for the agent;
- `woken`: the agent got a turn and decides itself (WAKE, DEFER, or a
  provider error under the default wake-on-error policy);
- `unsupported`: today's V2 has no route for this moment (a pause).

Each run gets two grades:

- `visible`: `fits`, `miss`, or `unlisted` for a quiet or mhm result;
  `agent-decides` for a woken one, since the agent's own move is not
  simulated yet.
- `step1`: `ok`, `over-suppress` (suppressed something step 1 must pass, so
  the agent never saw it), or `over-wake` (woke for something step 1 may
  suppress, which costs one turn).
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


def grade(moment: Moment, result: str) -> dict[str, str]:
    if result == "unsupported":
        return {"visible": "unsupported", "step1": "unsupported"}
    if result == "woken":
        visible = "agent-decides"
    elif result in moment.fitting:
        visible = "fits"
    elif moment.miss_reason(result) is not None:
        visible = "miss"
    else:
        visible = "unlisted"
    if result == "stay_quiet":
        step1 = "over-suppress" if moment.step1 == "pass" else "ok"
    else:
        step1 = "over-wake" if moment.step1 == "suppress" else "ok"
    return {"visible": visible, "step1": step1}


def collective_silence(results: list[str]) -> bool:
    """Every participant stayed quiet at the same moment."""

    return bool(results) and all(result == "stay_quiet" for result in results)


SYMBOL = {
    "stay_quiet": "Q",
    "mhm": "M",
    "woken": "W",
    "unsupported": "-",
}


def cell(results: list[dict[str, Any]]) -> str:
    """Compact per-run outcomes for one moment and one model, such as "QQW!".

    Q quiet, M mhm, W woken, E provider error (woken), - unsupported; a
    trailing "!" marks a clear miss in any run, "?" an unlisted move.
    """

    letters = []
    for item in results:
        letters.append("E" if item.get("provider_error") else SYMBOL[item["result"]])
    text = "".join(letters)
    grades = {item["grade"]["visible"] for item in results}
    if "miss" in grades:
        text += "!"
    elif "unlisted" in grades:
        text += "?"
    return text
