"""The job summary of a live scene dispatch: one grade matrix per pass, the columns side by side (step 9f, PR 4d).

    python -m evals.rehearsal.matrix --in rehearsal-out [--columns reference,claude-code,codex]
    python -m evals.rehearsal.matrix --in rehearsal-out/pass-1 --spent

The rehearsal workflow plays each scene once per column and pass, as a probe
run of its own, and lays the records out as
``<root>/pass-<n>/<scene>/<column>/run.json`` (the probe writes
``<out>/<column>/``), with ``<root>/status.tsv`` holding each run's exit status
(``pass``, ``scene``, ``column``, ``exit``, tab-separated; ``skipped`` for a run
the dispatch halted before starting), ``<root>/halted.tsv`` saying why it
halted (budget, time, or a spend that could not be read) and
``<root>/logs/pass-<n>-<scene>-<column>.stderr``, the tail of what a run said
on stderr. This reads them and writes a page for the job summary:

- the matrix per pass: a row for each graded moment of each scene, a column
  for each of the reference (the control), Claude Code and Codex, each cell
  the grade as the run's own summary shows it (the suite's letter for the move,
  then the visible grade and step 1, or ``precondition not met``). **The title
  says the expectations are drafts nobody has reviewed**: a grade compares the
  live agent with a draft, and is reported, never a failure;
- the facts each moment turns on and whether attention's evidence cites them;
- how each scene was played (the agent's earlier lines and what the live agent
  did instead, the holds and whether they held, a scene that stopped);
- each run's exit status and the hard checks that failed (those fail the job,
  the grades do not), and for a run that failed the tail of its stderr, which
  is the cause when it left no record (the launcher refusing, for one); a
  dispatch that halted says so first, and its runs not started read skipped;
- the cost of each pass, two ways: recorded (the key's usage, which lags) and
  estimated (the model calls counted times assumed costs per call,
  `spend.ESTIMATED_USD_PER_CALL`), with the calls counted per column.

``--spent`` prints the recorded spend of the runs under a directory, for the
workflow's soft stop between runs.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import re
import sys
from typing import Any

from .record import CELL_CODES, _cell, _matrix_cell, _played_lines

TITLE = "Directed scenes, live: grade matrix (draft expectations, not reviewed)"
COLUMNS = ("reference", "claude-code", "codex")
PASS = re.compile(r"^pass-(\d+)$")


SKIPPED = "skipped"


def read_status(root: Path) -> dict[tuple[int, str, str], int | str]:
    """Each run's exit status from ``status.tsv``, by (pass, scene, column): a number, or ``skipped``; a line that does not read is left out."""

    found: dict[tuple[int, str, str], int | str] = {}
    try:
        lines = (root / "status.tsv").read_text(encoding="utf-8").splitlines()
    except OSError:
        return found
    for line in lines:
        parts = line.split("\t")
        if len(parts) != 4 or not parts[0].isdigit():
            continue
        if parts[3].lstrip("-").isdigit():
            found[(int(parts[0]), parts[1], parts[2])] = int(parts[3])
        elif parts[3] == SKIPPED:
            found[(int(parts[0]), parts[1], parts[2])] = SKIPPED
    return found


HALT_WORDS = {
    "budget": "the dispatch had recorded {spent} of its {budget} budget",
    "time": "less than ten minutes of the play step's time were left",
    "spend-unreadable": "the recorded spend could not be read, and a figure that cannot be read does not count as nothing spent",
}


def read_halts(root: Path) -> list[dict[str, str]]:
    """Why the dispatch stopped starting runs, from ``halted.tsv`` (reason, spent, budget, the last run played); none if it ran to the end."""

    found: list[dict[str, str]] = []
    try:
        lines = (root / "halted.tsv").read_text(encoding="utf-8").splitlines()
    except OSError:
        return found
    for line in lines:
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0]:
            found.append({"reason": parts[0], "spent": parts[1], "budget": parts[2], "after": parts[3] if len(parts) > 3 else ""})
    return found


def _halt_line(halt: Mapping[str, str], skipped: int) -> str:
    """The headline of a halted dispatch: why, and how many runs it did not start."""

    def dollars(text: str) -> str:
        try:
            return f"${float(text):.2f}"
        except ValueError:
            return text  # "?" when the spend could not be read

    why = HALT_WORDS.get(halt["reason"], halt["reason"]).replace("{spent}", dollars(halt["spent"])).replace("{budget}", dollars(halt["budget"]))
    after = f" after {halt['after']}" if halt.get("after") and halt["after"] != "none" else ""
    return (
        f"**Halted ({halt['reason']}){after}:** {why}, so {skipped} run(s) were not started (skipped in the tables below). "
        "The budget is for the whole dispatch, all passes together, and the recorded figure lags the calls."
    )


def read_cause(root: Path, key: tuple[int, str, str]) -> str:
    """The tail of what a run said on stderr, as one line safe to put in a table; empty if it said nothing.

    The launcher's refusal or setup failure (before the probe ran) and the
    probe's own last words are only here, so the summary shows them beside the
    run. The text is not trusted: markup is stripped and it is shown as code.
    """

    try:
        text = (root / "logs" / f"pass-{key[0]}-{key[1]}-{key[2]}.stderr").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()][-3:]
    cleaned = re.sub(r"[`<>\x00-\x08\x0b-\x1f\x7f]", "", " / ".join(lines)).replace("|", "\\|")
    return f"`{cleaned[-300:]}`" if cleaned else ""


def read_runs(root: Path) -> dict[tuple[int, str, str], Mapping[str, Any]]:
    """Every ``pass-<n>/<scene>/<column>/run.json`` under ``root``, by (pass, scene, column); one that cannot be read is left out."""

    runs: dict[tuple[int, str, str], Mapping[str, Any]] = {}
    for path in sorted(root.glob("pass-*/*/*/run.json")):
        number = PASS.match(path.parents[2].name)
        if number is None:
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(document, dict):
            runs[(int(number.group(1)), path.parents[1].name, path.parents[0].name)] = document
    return runs


def scene_of(run: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The directed scene a run played: its one moment with ``expect`` ``directed``."""

    return next((moment for moment in run.get("moments", ()) if moment.get("expect") == "directed"), None)


def recorded_usd(run: Mapping[str, Any]) -> float | None:
    spent = (run.get("spend") or {}).get("spent_usd")
    return float(spent) if isinstance(spent, (int, float)) and not isinstance(spent, bool) else None


def spent(root: Path) -> float:
    """What the runs under ``root`` recorded as spent: the sum of each run's key usage, a run that recorded none counting nothing."""

    return round(sum(recorded_usd(run) or 0.0 for run in read_runs_anywhere(root).values()), 6)


def read_runs_anywhere(root: Path) -> dict[Any, Mapping[str, Any]]:
    """The runs under ``root`` whether it is the output root (``pass-<n>/...``) or one pass (``<scene>/<column>/run.json``)."""

    found: dict[Any, Mapping[str, Any]] = dict(read_runs(root))
    for path in sorted(root.glob("*/*/run.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(document, dict):
            found[(0, path.parents[1].name, path.parents[0].name)] = document
    return found


def _money(value: float | None) -> str:
    return "not read" if value is None else f"${value:.4f}"


def _cell_of(run: Mapping[str, Any] | None, status: int | str | None, moment_index: int) -> str:
    """One matrix cell: the run's grade for the moment, with a mark when the run failed its hard checks."""

    if run is None:
        if status == SKIPPED:
            return "skipped (halted)"
        return f"no record (exit {status})" if status is not None else "not run"
    scene = scene_of(run)
    items = (scene or {}).get("graded", ())
    if moment_index >= len(items):
        return "not played"
    cell = _matrix_cell(items[moment_index])
    if run.get("status") not in (None, "pass"):
        failed = [check["name"] for check in run.get("checks", ()) if not check.get("ok")]
        cell += f" (**run {run.get('status')}**{': ' + ', '.join(failed) if failed else ''})"
    return cell


def render(root: Path, columns: Sequence[str] = COLUMNS) -> str:
    """The page: the title, how to read it, a matrix and the notes for each pass, the runs, and the cost."""

    runs = read_runs(root)
    status = read_status(root)
    passes = sorted({key[0] for key in (*runs, *status)})
    lines = [
        f"# {TITLE}",
        "",
        "The scenes' expectations are drafts that Zoe has not reviewed (`evals/behavior/README.md`). A grade compares what the live agent "
        "did with a draft's fitting moves and clear misses, so it is **reported, never a failure**, and not a finding about a model until "
        "she has reviewed the scene. The reference (`nunchi-discord` on the same models) is the control: a miss only a harness column has "
        "is the integration's, a miss all columns share is the model's or Nunchi's. What does fail a run is the plumbing and safety "
        "checks, listed under *Runs*. Cell: the suite's letter for the move (" + CELL_CODES + "), then the "
        "visible grade and step 1, or `precondition not met` where the live agent did not make the setup the scene needs (not graded).",
        "",
    ]
    halts = read_halts(root)
    skipped = sum(1 for value in status.values() if value == SKIPPED)
    if halts:
        lines += [_halt_line(halt, skipped) for halt in halts[:1]] + [""]
    if not passes:
        return "\n".join([*lines, "No scene run left a record.", ""])
    models = next(
        (
            run.get("models") or {}
            for _, run in sorted(runs.items())
            if (run.get("models") or {}).get("agent")
        ),
        {},
    )
    lines += [
        f"- Agent model: `{(models.get('agent') or {}).get('requested')}`; attention: `{(models.get('attention') or {}).get('requested')}`",
        f"- Columns: {', '.join(columns)}; passes: {len(passes)}; scenes: {', '.join(sorted({key[1] for key in (*runs, *status)}))}",
        "",
    ]
    for number in passes:
        scenes = sorted({key[1] for key in (*runs, *status) if key[0] == number})
        lines += [f"## Pass {number}", "", "| Scene | Moment | Fitting (step 1) | " + " | ".join(columns) + " |", "|---|---|---|" + "---|" * len(columns)]
        notes: list[str] = []
        facts: list[str] = []
        for scene in scenes:
            first = next((runs[(number, scene, column)] for column in columns if (number, scene, column) in runs), None)
            played = scene_of(first) if first else None
            for index, item in enumerate((played or {}).get("graded", ())):
                lines.append(
                    f"| {scene} | {_cell(item.get('label'), 80)} | {', '.join(item.get('fitting', ()))} ({item.get('step1')}) | "
                    + " | ".join(
                        _cell_of(runs.get((number, scene, column)), status.get((number, scene, column)), index) for column in columns
                    )
                    + " |"
                )
                for fact_index, fact in enumerate(item.get("facts", ())):
                    marks = []
                    for column in columns:
                        run = runs.get((number, scene, column))
                        graded = (scene_of(run) or {}).get("graded", ()) if run else ()
                        cited = graded[index].get("cited", ()) if index < len(graded) else ()
                        marks.append("cited" if fact_index < len(cited) and cited[fact_index] else "not cited")
                    facts.append(f"| {scene} | {_cell(item.get('label'), 60)} | {_cell(fact, 120)} | " + " | ".join(marks) + " |")
            if not played:
                lines.append(f"| {scene} | (no record) | | " + " | ".join(_cell_of(runs.get((number, scene, column)), status.get((number, scene, column)), 0) for column in columns) + " |")
            for column in columns:
                run = runs.get((number, scene, column))
                if run:
                    notes += [f"{line} ({column})" for line in _played_lines(run)[2:-1] if line]
        lines.append("")
        if facts:
            lines += [
                f"### Pass {number}: the facts each moment turns on, and whether attention's evidence cites them",
                "",
                "| Scene | Moment | Fact | " + " | ".join(columns) + " |",
                "|---|---|---|" + "---|" * len(columns),
                *facts,
                "",
            ]
        if notes:
            lines += [f"### Pass {number}: how the scenes were played", "", *notes, ""]
    lines += [
        "## Runs",
        "",
        "| Pass | Scene | Column | Exit | Status | Hard checks that failed | Cause (the tail of stderr, for a run that failed) |",
        "|---|---|---|---|---|---|---|",
    ]
    for key in sorted({*runs, *status}):
        run = runs.get(key)
        code = status.get(key, "?")
        failed = [check["name"] for check in (run or {}).get("checks", ()) if not check.get("ok")]
        cause = read_cause(root, key) if code not in (0, SKIPPED) or (run or {}).get("status") not in (None, "pass") else ""
        lines.append(
            f"| {key[0]} | {key[1]} | {key[2]} | {code} | {(run or {}).get('status', 'skipped' if code == SKIPPED else 'no record')} | "
            f"{', '.join(failed) if failed else ('the run raised an error' if (run or {}).get('errors') else '-')} | {cause or '-'} |"
        )
    lines.append("")
    lines += _cost_lines(runs, passes, columns)
    return "\n".join(lines)


def _cost_lines(runs: Mapping[tuple[int, str, str], Mapping[str, Any]], passes: Sequence[int], columns: Sequence[str]) -> list[str]:
    """The cost of each pass: per column the model calls counted, the estimated cost and the recorded one."""

    lines = [
        "## Cost",
        "",
        "Recorded is the OpenRouter key's usage over each run, read before the first message and for about 75 s after the last; it "
        "lags the calls, counts other runs on the key, and can be missed or land in the next run, so only the sum over a pass is "
        "worth reading. Estimated is the model calls counted times assumed costs per call (`evals/rehearsal/spend.py`), which no run "
        "has measured; the reference's calls are a lower bound, since its process shows its turns and attention receipts but not "
        "every model call.",
        "",
        "| Pass | Column | Runs | Agent calls | Attention calls | Estimated | Recorded |",
        "|---|---|---|---|---|---|---|",
    ]
    for number in passes:
        total_estimated = total_recorded = 0.0
        read_all = True
        for column in columns:
            mine = [run for key, run in runs.items() if key[0] == number and key[2] == column]
            if not mine:
                continue
            calls = [(run.get("spend") or {}).get("model_calls") or {} for run in mine]
            agent = sum(call.get("agent") or 0 for call in calls)
            attention = sum(call.get("attention") or 0 for call in calls)
            estimated = sum((run.get("spend") or {}).get("estimated_usd") or 0.0 for run in mine)
            recorded = [recorded_usd(run) for run in mine]
            total_estimated += estimated
            total_recorded += sum(value or 0.0 for value in recorded)
            read_all = read_all and all(value is not None for value in recorded)
            lines.append(
                f"| {number} | {column} | {len(mine)} | {agent} | {attention} | {_money(estimated)} | "
                f"{_money(sum(value or 0.0 for value in recorded) if any(value is not None for value in recorded) else None)} |"
            )
        lines.append(f"| {number} | **all** | | | | **{_money(total_estimated)}** | **{_money(total_recorded if read_all else None)}** |")
    lines.append("")
    return lines


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m evals.rehearsal.matrix", description=__doc__.split("\n\n")[0])
    parser.add_argument("--in", dest="root", required=True, help="the output root (pass-<n>/<scene>/<column>/run.json, status.tsv)")
    parser.add_argument("--columns", default=",".join(COLUMNS), help="the columns, in the order the matrix shows them")
    parser.add_argument("--spent", action="store_true", help="print the recorded spend of the runs under --in, as a number, and nothing else")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(args.root)
    if args.spent:
        print(f"{spent(root):.6f}")
        return 0
    sys.stdout.write(render(root, [column for column in args.columns.split(",") if column]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
