#!/usr/bin/env python3
"""Fail-closed literal task-state check for slice 020.

The shared governance manifest deliberately normalizes checkbox state for graph
identity. Slice 020 needs a separate read-only completion oracle without
changing that shared behavior. Historical final-gate tasks that were explicitly
superseded in tasks.md remain unchecked and are labelled here; they are never
reported as completed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re

TASK_RE = re.compile(r"^- \[([ Xx])\] (T\d{3})\b", re.MULTILINE)
SUPERSEDED_BY = {
    "T107": "T140",
    "T112": "T140",
    "T119": "T140",
    "T124": "T140",
    "T131": "T140",
}


@dataclass(frozen=True)
class TaskState:
    all_ids: tuple[str, ...]
    checked: frozenset[str]
    superseded: frozenset[str]
    open_ids: frozenset[str]


def evaluate_task_state(path: Path, *, allowed_open: frozenset[str]) -> TaskState:
    matches = TASK_RE.findall(path.read_text(encoding="utf-8"))
    if not matches:
        raise ValueError(f"no task checkboxes found in {path}")
    ids = [task_id for _, task_id in matches]
    if len(ids) != len(set(ids)):
        duplicates = sorted({task_id for task_id in ids if ids.count(task_id) > 1})
        raise ValueError(f"duplicate task IDs: {duplicates}")
    numeric = [int(task_id[1:]) for task_id in ids]
    expected = list(range(1, max(numeric) + 1))
    if numeric != expected:
        raise ValueError("task IDs must be unique, ordered, and contiguous")

    literal_checked = frozenset(
        task_id for mark, task_id in matches if mark.lower() == "x"
    )
    superseded = frozenset(SUPERSEDED_BY) & frozenset(ids)
    unclosed_superseded = superseded - literal_checked
    if unclosed_superseded:
        raise ValueError(
            "superseded task IDs must be literally checked as resolved: "
            f"{sorted(unclosed_superseded)}"
        )
    checked = literal_checked - superseded
    unchecked = frozenset(ids) - literal_checked
    unexplained = unchecked - allowed_open
    unknown_allowed = allowed_open - unchecked
    if unexplained:
        raise ValueError(f"unexplained unchecked task IDs: {sorted(unexplained)}")
    if unknown_allowed:
        raise ValueError(
            "allowed-open IDs are not literally unchecked: "
            f"{sorted(unknown_allowed)}"
        )
    return TaskState(
        all_ids=tuple(ids),
        checked=checked,
        superseded=frozenset(superseded),
        open_ids=unchecked,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument(
        "--allow-open",
        default="",
        help="comma-separated literal open task IDs permitted at this lifecycle point",
    )
    args = parser.parse_args()
    allowed = frozenset(part.strip() for part in args.allow_open.split(",") if part.strip())
    try:
        state = evaluate_task_state(args.tasks, allowed_open=allowed)
    except (OSError, ValueError) as exc:
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
