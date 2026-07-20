"""Capability-aware shared/reference observation comparator (T003, FR-012).

Compares two ``AttentionRequestV2`` documents (or two continuation pages)
assembled from equivalent native facts and budgets and reports every semantic
difference. Request-local correlation IDs, issued handle IDs, expiry clocks, and
exact cursor bytes are intentionally opaque; their presence/shape remains
semantic. Every other difference is classified as *explained* (an explicitly
declared capability gap) or *unexplained* (a real divergence). Zero unexplained
differences is the reusable comparison contract (SC-006); it never certifies a
real surface or final cross-surface parity.
"""

from __future__ import annotations

from typing import Any

CapabilityContext = dict[str, Any]
"""Optional per-side context.

Supported declarations:

- ``unavailable_event_ids``: exact event IDs that side cannot attest;
- ``unavailable_actor_ids``: exact actor IDs that side cannot attest;
- ``explained_paths``: exact semantic paths (or path prefixes) whose divergence
  is capability-explained;
- ``reason``: human-readable explanation included in comparator output.
"""

_MISSING = object()


def _reason(capability: CapabilityContext) -> str:
    return str(capability.get("reason") or "declared capability gap")


def _declared_path(path: str, capability: CapabilityContext) -> bool:
    declared = capability.get("explained_paths") or []
    return any(path == item or path.startswith(f"{item}.") for item in declared)


def _record_difference(
    path: str,
    left: Any,
    right: Any,
    *,
    unexplained: list[str],
    explained: list[str],
    left_capability: CapabilityContext,
    right_capability: CapabilityContext,
) -> None:
    if _declared_path(path, left_capability):
        explained.append(f"{path} differs by left capability ({_reason(left_capability)})")
    elif _declared_path(path, right_capability):
        explained.append(f"{path} differs by right capability ({_reason(right_capability)})")
    elif left is _MISSING:
        unexplained.append(f"{path} is missing on the left; right={right!r}")
    elif right is _MISSING:
        unexplained.append(f"{path} is missing on the right; left={left!r}")
    else:
        unexplained.append(f"{path} differs: {left!r} vs {right!r}")


def _compare_value(
    path: str,
    left: Any,
    right: Any,
    *,
    unexplained: list[str],
    explained: list[str],
    left_capability: CapabilityContext,
    right_capability: CapabilityContext,
) -> None:
    if left is _MISSING or right is _MISSING:
        _record_difference(
            path,
            left,
            right,
            unexplained=unexplained,
            explained=explained,
            left_capability=left_capability,
            right_capability=right_capability,
        )
        return
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            child = f"{path}.{key}" if path else str(key)
            _compare_value(
                child,
                left.get(key, _MISSING),
                right.get(key, _MISSING),
                unexplained=unexplained,
                explained=explained,
                left_capability=left_capability,
                right_capability=right_capability,
            )
        return
    if left != right:
        _record_difference(
            path,
            left,
            right,
            unexplained=unexplained,
            explained=explained,
            left_capability=left_capability,
            right_capability=right_capability,
        )


def _event_map(document: dict) -> dict[str, dict]:
    return {event["id"]: event for event in document.get("events", [])}


def _compare_events(
    left: dict,
    right: dict,
    *,
    unexplained: list[str],
    explained: list[str],
    left_capability: CapabilityContext,
    right_capability: CapabilityContext,
) -> None:
    left_event_list = left.get("events", [])
    right_event_list = right.get("events", [])
    left_ids = [event["id"] for event in left_event_list]
    right_ids = [event["id"] for event in right_event_list]
    if len(left_ids) != len(set(left_ids)):
        unexplained.append(f"left events contain duplicate IDs: {left_ids!r}")
    if len(right_ids) != len(set(right_ids)):
        unexplained.append(f"right events contain duplicate IDs: {right_ids!r}")

    left_events, right_events = _event_map(left), _event_map(right)
    left_unavailable = set(left_capability.get("unavailable_event_ids") or [])
    right_unavailable = set(right_capability.get("unavailable_event_ids") or [])

    only_left = set(left_events) - set(right_events)
    only_right = set(right_events) - set(left_events)
    for event_id in sorted(only_left):
        if event_id in right_unavailable:
            explained.append(
                f"event {event_id!r} honestly unavailable on the right "
                f"({_reason(right_capability)})"
            )
        else:
            unexplained.append(f"event {event_id!r} present on the left but missing on the right")
    for event_id in sorted(only_right):
        if event_id in left_unavailable:
            explained.append(
                f"event {event_id!r} honestly unavailable on the left "
                f"({_reason(left_capability)})"
            )
        else:
            unexplained.append(f"event {event_id!r} present on the right but missing on the left")

    common = set(left_events) & set(right_events)
    left_common_order = [event_id for event_id in left_ids if event_id in common]
    right_common_order = [event_id for event_id in right_ids if event_id in common]
    if left_common_order != right_common_order:
        unexplained.append(
            "authoritative event order differs: "
            f"{left_common_order!r} vs {right_common_order!r}"
        )

    for event_id in sorted(common):
        _compare_value(
            f"events[{event_id!r}]",
            left_events[event_id],
            right_events[event_id],
            unexplained=unexplained,
            explained=explained,
            left_capability=left_capability,
            right_capability=right_capability,
        )


def _compare_actors(
    left: dict,
    right: dict,
    *,
    unexplained: list[str],
    explained: list[str],
    left_capability: CapabilityContext,
    right_capability: CapabilityContext,
) -> None:
    left_actors = left.get("actors", {})
    right_actors = right.get("actors", {})
    left_unavailable = set(left_capability.get("unavailable_actor_ids") or [])
    right_unavailable = set(right_capability.get("unavailable_actor_ids") or [])
    for actor_id in sorted(set(left_actors) | set(right_actors)):
        if actor_id not in left_actors:
            if actor_id in left_unavailable:
                explained.append(
                    f"actor {actor_id!r} honestly unavailable on the left "
                    f"({_reason(left_capability)})"
                )
            else:
                unexplained.append(f"actor {actor_id!r} present on the right but missing on the left")
            continue
        if actor_id not in right_actors:
            if actor_id in right_unavailable:
                explained.append(
                    f"actor {actor_id!r} honestly unavailable on the right "
                    f"({_reason(right_capability)})"
                )
            else:
                unexplained.append(f"actor {actor_id!r} present on the left but missing on the right")
            continue
        _compare_value(
            f"actors.{actor_id}",
            left_actors[actor_id],
            right_actors[actor_id],
            unexplained=unexplained,
            explained=explained,
            left_capability=left_capability,
            right_capability=right_capability,
        )


def _compare_coverage(
    left: dict,
    right: dict,
    *,
    unexplained: list[str],
    explained: list[str],
    left_capability: CapabilityContext,
    right_capability: CapabilityContext,
) -> None:
    left_coverage = left.get("coverage", {})
    right_coverage = right.get("coverage", {})
    keys = set(left_coverage) | set(right_coverage)
    for key in sorted(keys):
        left_value = left_coverage.get(key, _MISSING)
        right_value = right_coverage.get(key, _MISSING)
        if left_value == right_value:
            continue
        if key == "continuity" and left_value is not _MISSING and right_value is not _MISSING:
            explained.append(
                "coverage.continuity differs by declared capability: "
                f"{left_value!r} vs {right_value!r}"
            )
            continue
        _compare_value(
            f"coverage.{key}",
            left_value,
            right_value,
            unexplained=unexplained,
            explained=explained,
            left_capability=left_capability,
            right_capability=right_capability,
        )


def _normalized_continuation(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    normalized = {
        key: item
        for key, item in value.items()
        if key not in {"handle_id", "expires_at"}
    }
    normalized["expires_at_present"] = "expires_at" in value
    return normalized


def _compare_documents(
    left: dict,
    right: dict,
    *,
    opaque_top_level: set[str],
    compare_cursor_presence: bool,
    left_capability: CapabilityContext,
    right_capability: CapabilityContext,
) -> dict[str, Any]:
    unexplained: list[str] = []
    explained: list[str] = []

    _compare_events(
        left,
        right,
        unexplained=unexplained,
        explained=explained,
        left_capability=left_capability,
        right_capability=right_capability,
    )
    _compare_actors(
        left,
        right,
        unexplained=unexplained,
        explained=explained,
        left_capability=left_capability,
        right_capability=right_capability,
    )
    _compare_coverage(
        left,
        right,
        unexplained=unexplained,
        explained=explained,
        left_capability=left_capability,
        right_capability=right_capability,
    )

    excluded = set(opaque_top_level) | {"events", "actors", "coverage", "continuation"}
    if compare_cursor_presence:
        excluded.add("next_cursor")
        left_has_cursor = left.get("next_cursor") is not None
        right_has_cursor = right.get("next_cursor") is not None
        if left_has_cursor != right_has_cursor:
            unexplained.append(
                "next_cursor presence differs: "
                f"{left_has_cursor!r} vs {right_has_cursor!r}"
            )

    for key in sorted((set(left) | set(right)) - excluded):
        _compare_value(
            key,
            left.get(key, _MISSING),
            right.get(key, _MISSING),
            unexplained=unexplained,
            explained=explained,
            left_capability=left_capability,
            right_capability=right_capability,
        )

    if "continuation" in left or "continuation" in right:
        left_continuation = _normalized_continuation(left.get("continuation", _MISSING))
        right_continuation = _normalized_continuation(right.get("continuation", _MISSING))
        _compare_value(
            "continuation",
            left_continuation,
            right_continuation,
            unexplained=unexplained,
            explained=explained,
            left_capability=left_capability,
            right_capability=right_capability,
        )

    return {
        "equivalent": not unexplained,
        "unexplained": unexplained,
        "explained": explained,
    }


def compare_requests(
    left: dict,
    right: dict,
    *,
    left_capability: CapabilityContext | None = None,
    right_capability: CapabilityContext | None = None,
) -> dict[str, Any]:
    """Compare two equivalent-input ``AttentionRequestV2`` documents."""
    return _compare_documents(
        left,
        right,
        opaque_top_level={"request_id"},
        compare_cursor_presence=False,
        left_capability=left_capability or {},
        right_capability=right_capability or {},
    )


def compare_pages(
    left: dict,
    right: dict,
    *,
    left_capability: CapabilityContext | None = None,
    right_capability: CapabilityContext | None = None,
) -> dict[str, Any]:
    """Compare two ``ContextContinuationV2`` pages semantically.

    Request IDs, handle IDs, and exact cursor token bytes are host-local opaque
    identities. Cursor *presence* is semantic because it controls whether more
    of the fixed remainder is available.
    """
    return _compare_documents(
        left,
        right,
        opaque_top_level={"request_id", "handle_id"},
        compare_cursor_presence=True,
        left_capability=left_capability or {},
        right_capability=right_capability or {},
    )
