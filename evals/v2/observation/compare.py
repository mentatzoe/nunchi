"""Capability-aware shared/reference observation comparator (T003, FR-012).

Compares two ``AttentionRequestV2`` documents (or two continuation pages)
assembled from equivalent native facts and budgets and reports every
difference, classifying each as *explained* (an honestly declared
capability gap on one side) or *unexplained* (a real divergence). Zero
unexplained differences is the reusable comparison contract (SC-006); it
never certifies a real surface or final cross-surface parity — slices
050/060-090 apply this comparator to their own bindings, and 110 alone
owns the final parity claim.
"""

from __future__ import annotations

from typing import Any

CapabilityContext = dict[str, Any]
"""Optional per-side context: ``{"unavailable_event_ids": {...}, "reason": "..."}``
naming facts that side honestly cannot attest, so a resulting difference
is explained rather than a real divergence."""


def _event_map(document: dict) -> dict[str, dict]:
    return {event["id"]: event for event in document.get("events", [])}


def compare_requests(
    left: dict,
    right: dict,
    *,
    left_capability: CapabilityContext | None = None,
    right_capability: CapabilityContext | None = None,
) -> dict[str, Any]:
    """Compare two equivalent-input ``AttentionRequestV2`` documents.

    Returns ``{"equivalent": bool, "unexplained": [...], "explained": [...]}``.
    ``equivalent`` is true exactly when every difference is explained.
    """
    left_capability = left_capability or {}
    right_capability = right_capability or {}
    left_unavailable = set(left_capability.get("unavailable_event_ids") or [])
    right_unavailable = set(right_capability.get("unavailable_event_ids") or [])

    unexplained: list[str] = []
    explained: list[str] = []

    if left["self"]["actor_id"] != right["self"]["actor_id"]:
        unexplained.append(
            f"self.actor_id differs: {left['self']['actor_id']!r} vs {right['self']['actor_id']!r}"
        )

    left_events, right_events = _event_map(left), _event_map(right)
    only_left = set(left_events) - set(right_events)
    only_right = set(right_events) - set(left_events)

    for event_id in sorted(only_left):
        if event_id in right_unavailable:
            explained.append(f"event {event_id!r} honestly unavailable on the right ({right_capability.get('reason', 'capability gap')})")
        else:
            unexplained.append(f"event {event_id!r} present on the left but missing on the right")
    for event_id in sorted(only_right):
        if event_id in left_unavailable:
            explained.append(f"event {event_id!r} honestly unavailable on the left ({left_capability.get('reason', 'capability gap')})")
        else:
            unexplained.append(f"event {event_id!r} present on the right but missing on the left")

    for event_id in sorted(set(left_events) & set(right_events)):
        left_event, right_event = left_events[event_id], right_events[event_id]
        shared_keys = set(left_event) & set(right_event)
        for key in sorted(shared_keys):
            if left_event[key] != right_event[key]:
                unexplained.append(f"event {event_id!r} field {key!r} differs: {left_event[key]!r} vs {right_event[key]!r}")

    if left["trigger_event_id"] != right["trigger_event_id"]:
        unexplained.append(
            f"trigger_event_id differs: {left['trigger_event_id']!r} vs {right['trigger_event_id']!r}"
        )

    left_continuity = left["coverage"].get("continuity")
    right_continuity = right["coverage"].get("continuity")
    if left_continuity != right_continuity:
        explained.append(f"coverage.continuity differs by declared capability: {left_continuity!r} vs {right_continuity!r}")

    return {
        "equivalent": not unexplained,
        "unexplained": unexplained,
        "explained": explained,
    }


def compare_pages(left: dict, right: dict, **kwargs: Any) -> dict[str, Any]:
    """Compare two ``ContextContinuationV2`` fetch pages using the same rules."""
    return compare_requests(
        {"self": {"actor_id": "n/a"}, "events": left["events"], "trigger_event_id": left["anchor_event_id"], "coverage": left["coverage"]},
        {"self": {"actor_id": "n/a"}, "events": right["events"], "trigger_event_id": right["anchor_event_id"], "coverage": right["coverage"]},
        **kwargs,
    )
