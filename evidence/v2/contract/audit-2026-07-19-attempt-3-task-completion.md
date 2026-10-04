# Audit note — slice 010 attempt-3 task-completion claim

**Recorded on**: 2026-07-19

**Audit target**: `evidence/v2/contract/slice-candidate.md`, attempt 3

**Candidate commit**: `7f9e81460d570e078c4bcbacb138f81c1b291455`

**Disposition**: `HISTORICAL_FALSE_CLAIM_REJECTED`

## Finding

Attempt 3 records `Tasks complete: YES` and declares T001–T046 complete. Direct
inspection of `specs/010-v2-contract/tasks.md` at the exact candidate commit
shows 46 canonical task entries, of which only 38 are literally checked.

The unchecked task IDs are:

```text
T036, T037, T038, T039, T040, T041, T044, T045
```

The shared governance checker did not detect this at the time because
`_task_entries()` normalized `[x]`/`[X]` to `[ ]` before `_task_manifest()`
computed `Completed task IDs` and `Tasks SHA256`. The resulting manifest proved
sequential normalized task identity, not literal checkbox completion.

## Lifecycle effect

Attempt 3 was subsequently rejected in the existing append-only handoff stream.
This audit note does not alter, rewrite, reopen, or retroactively invalidate any
candidate, handoff, rejection, or acceptance record.

The terminal accepted attempt 6 candidate
`bff6b463a44c1b9066fc654691042f9550da6c64` contains 49 canonical tasks and all
49 are literally checked. Slice 010's attempt-6 `ACCEPTED` state therefore
remains independently supported.

## Reproduction

```sh
python3 - <<'PY'
import re
import subprocess

for label, commit in (
    ("attempt-3", "7f9e81460d570e078c4bcbacb138f81c1b291455"),
    ("attempt-6", "bff6b463a44c1b9066fc654691042f9550da6c64"),
):
    text = subprocess.run(
        ["git", "show", f"{commit}:specs/010-v2-contract/tasks.md"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    tasks = [line for line in text.splitlines() if re.match(r"^- \[[ xX]\] T\d+", line)]
    checked = [line for line in tasks if re.match(r"^- \[[xX]\] T\d+", line)]
    unchecked = [
        re.match(r"^- \[ \] (T\d+)", line).group(1)
        for line in tasks
        if re.match(r"^- \[ \] T\d+", line)
    ]
    print(label, {"total": len(tasks), "checked": len(checked), "unchecked": unchecked})
PY
```

Expected:

```text
attempt-3 {'total': 46, 'checked': 38, 'unchecked': ['T036', 'T037', 'T038', 'T039', 'T040', 'T041', 'T044', 'T045']}
attempt-6 {'total': 49, 'checked': 49, 'unchecked': []}
```

This note is historical audit evidence only. It grants no lifecycle transition,
integration, deployment, release, promotion, or cutover authority.
