#!/usr/bin/env python3
"""Fail-closed literal task-state diagnostic for Slice 020.

Shared governance owns lifecycle authority. This slice-owned diagnostic pins the
exact terminal graph and its currently legitimate ACTIVE gates, validates every
historical review supersession, and never accepts caller-selected open tasks.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re

try:
    from scripts.check_governance import (
        SLICE_TASK_POLICIES,
        _literal_completed_task_ids,
        _slice_task_policy_errors,
        _validated_task_entries,
    )
except ModuleNotFoundError:  # direct ``python3 scripts/...`` execution
    from check_governance import (  # type: ignore[no-redef]
        SLICE_TASK_POLICIES,
        _literal_completed_task_ids,
        _slice_task_policy_errors,
        _validated_task_entries,
    )


_POLICY = SLICE_TASK_POLICIES["020-v2-observation"]
TERMINAL_TASK_NUMBER = _POLICY.terminal
EXPECTED_IDS = tuple(f"T{number:03d}" for number in range(1, TERMINAL_TASK_NUMBER + 1))
ACTIVE_OPEN_OPTIONS = _POLICY.active_open_options
SUPERSEDED_BY = dict(_POLICY.superseded_by)
_TASK_MARK = re.compile(r"^- \[([ Xx])\] (T\d{3})\b", re.MULTILINE)
_SLICE_STATE = re.compile(
    r"^\*\*Slice state\*\*: `(ACTIVE|CONVERGED|HANDOFF_READY|ACCEPTED)`$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class TaskState:
    all_ids: tuple[str, ...]
    checked: frozenset[str]
    superseded: frozenset[str]
    open_ids: frozenset[str]


def evaluate_task_state(path: Path) -> TaskState:
    text = path.read_text(encoding="utf-8")
    entries = _validated_task_entries(text)
    ids = tuple(task_id for task_id, _line in entries)
    if ids != EXPECTED_IDS:
        raise ValueError(
            f"Slice 020 task manifest must contain exactly T001 through "
            f"T{TERMINAL_TASK_NUMBER:03d}"
        )

    marks = {task_id: mark for mark, task_id in _TASK_MARK.findall(text)}
    if tuple(marks) != EXPECTED_IDS:
        raise ValueError("literal task marks do not match the exact terminal manifest")
    completed_text = _literal_completed_task_ids(text)
    checked = frozenset(item for item in completed_text.split(", ") if item)
    unchecked = frozenset(EXPECTED_IDS) - checked

    state_match = _SLICE_STATE.search(text)
    if state_match is None:
        raise ValueError("missing or invalid Slice state declaration")
    lifecycle_state = state_match.group(1)
    policy_errors = _slice_task_policy_errors(
        "020-v2-observation", text, lifecycle_state
    )
    if policy_errors:
        raise ValueError(policy_errors[0])

    return TaskState(
        all_ids=ids,
        checked=checked,
        superseded=frozenset(SUPERSEDED_BY),
        open_ids=unchecked,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, required=True)
    args = parser.parse_args()
    try:
        state = evaluate_task_state(args.tasks)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"SLICE020_TASK_STATE FAIL: {exc}")
        return 1
    print(
        "SLICE020_TASK_STATE OK "
        f"total={len(state.all_ids)} checked={len(state.checked)} "
        f"superseded={','.join(sorted(state.superseded)) or '-'} "
        f"open={','.join(sorted(state.open_ids)) or '-'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
