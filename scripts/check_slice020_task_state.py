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
    from scripts.check_governance import _validated_task_entries
except ModuleNotFoundError:  # direct ``python3 scripts/...`` execution
    from check_governance import _validated_task_entries


TERMINAL_TASK_NUMBER = 153
EXPECTED_IDS = tuple(f"T{number:03d}" for number in range(1, TERMINAL_TASK_NUMBER + 1))
ACTIVE_OPEN_OPTIONS = (
    frozenset({"T103", "T152", "T153"}),
    frozenset({"T103", "T153"}),
)
SUPERSEDED_BY = {
    "T107": "T153",
    "T112": "T153",
    "T119": "T153",
    "T124": "T153",
    "T131": "T153",
    "T140": "T153",
    "T146": "T153",
}
_TASK_MARK = re.compile(r"^- \[([ Xx])\] (T\d{3})\b", re.MULTILINE)
_SLICE_STATE = re.compile(
    r"^\*\*Slice state\*\*: `(ACTIVE|CONVERGED|HANDOFF_READY|ACCEPTED)`$",
    re.MULTILINE,
)
_TASK_START = re.compile(r"^- \[[ Xx]\] (T\d{3})\b", re.MULTILINE)


@dataclass(frozen=True)
class TaskState:
    all_ids: tuple[str, ...]
    checked: frozenset[str]
    superseded: frozenset[str]
    open_ids: frozenset[str]


def _task_blocks(text: str) -> dict[str, str]:
    starts = list(_TASK_START.finditer(text))
    return {
        match.group(1): text[
            match.start() : starts[index + 1].start() if index + 1 < len(starts) else len(text)
        ]
        for index, match in enumerate(starts)
    }


def evaluate_task_state(path: Path) -> TaskState:
    text = path.read_text(encoding="utf-8")
    entries = _validated_task_entries(text)
    ids = tuple(task_id for task_id, _line in entries)
    if ids != EXPECTED_IDS:
        raise ValueError("Slice 020 task manifest must contain exactly T001 through T153")

    marks = {task_id: mark for mark, task_id in _TASK_MARK.findall(text)}
    if tuple(marks) != EXPECTED_IDS:
        raise ValueError("literal task marks do not match the exact terminal manifest")
    checked = frozenset(task_id for task_id, mark in marks.items() if mark.lower() == "x")
    unchecked = frozenset(EXPECTED_IDS) - checked

    blocks = _task_blocks(text)
    for historical_gate, successor in SUPERSEDED_BY.items():
        block = blocks.get(historical_gate, "")
        if historical_gate not in checked:
            raise ValueError(f"superseded gate {historical_gate} must be literally checked")
        if not re.search(
            rf"superseded\s+by\s+{re.escape(successor)}\b", block, re.IGNORECASE
        ):
            raise ValueError(
                f"superseded gate {historical_gate} must name exact successor {successor}"
            )
        if successor not in ids:
            raise ValueError(
                f"superseded gate {historical_gate} names absent successor {successor}"
            )

    state_match = _SLICE_STATE.search(text)
    if state_match is None:
        raise ValueError("missing or invalid Slice state declaration")
    lifecycle_state = state_match.group(1)
    expected_open_options = (
        ACTIVE_OPEN_OPTIONS if lifecycle_state == "ACTIVE" else (frozenset(),)
    )
    if unchecked not in expected_open_options:
        raise ValueError(
            f"{lifecycle_state} literal open task IDs must be one of "
            f"{[sorted(option) for option in expected_open_options]}; "
            f"observed {sorted(unchecked)}"
        )

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
