"""Reference rehearsal records: versions, configuration, commands and results.

Records describe the standalone participant and Discord stand-in. They are not
installed-agent evidence. Secret values must be scanned before publication.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
import contextlib
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from evals.behavior.score import cell as grade_cell, symbol as move_symbol

from .checks import MISSES
from .standin import JsonLines

SCHEMA = "nunchi-rehearsal-probe/1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def redact(text: str, secrets: Mapping[str, str]) -> str:
    """``text`` with every secret's value replaced by ``${NAME}``."""

    for name, value in sorted(secrets.items(), key=lambda item: -len(item[1] or "")):
        if value:
            text = text.replace(value, "${" + name + "}")
    return text


def config_entry(name: str, path: Path, *, base: Path) -> dict[str, Any]:
    """One config the run wrote: where, its sha256, and its text (it names variables; the scan guards the rest)."""

    raw = path.read_bytes()
    try:
        where = str(path.relative_to(base))
    except ValueError:
        where = str(path)
    return {
        "name": name,
        "path": where,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "content": raw.decode("utf-8", errors="replace"),
    }


# -- identity of what ran ------------------------------------------------------------------


def git_commit(root: Path) -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            done = subprocess.run(
                ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=20, check=False
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return done.stdout.strip() if done.returncode == 0 else None

    sha = git("rev-parse", "HEAD")
    status = git("status", "--porcelain", "--untracked-files=no")
    untracked = git("ls-files", "--others", "--exclude-standard")
    return {
        "sha": sha,
        # Tracked files changed since the commit.
        "dirty": bool(status) if status is not None else None,
        # Files the commit does not have (the run's own outputs among them).
        "untracked_files": len(untracked.splitlines()) if untracked else 0,
        "root": str(root),
    }


def nunchi_install(wheel: Path | None) -> dict[str, Any]:
    """Which Nunchi ran: the installed wheel (with its sha256), or a source tree."""

    import nunchi

    location = Path(nunchi.__file__).resolve().parent
    entry: dict[str, Any] = {"version": nunchi.__version__, "location": str(location)}
    if wheel is not None:
        entry["wheel"] = {"file": wheel.name, "sha256": sha256_file(wheel) if wheel.is_file() else None}
    try:
        distribution = importlib.metadata.distribution("nunchi")
        entry["distribution"] = {"version": distribution.version, "path": str(distribution.locate_file(""))}
    except importlib.metadata.PackageNotFoundError:
        entry["distribution"] = None
    entry["from_source_tree"] = location.parent.name == "src"
    return entry


def python_packages() -> list[str]:
    """``name==version`` for every distribution this interpreter can import."""

    seen = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            seen[name.lower()] = f"{name}=={distribution.version}"
    return [seen[key] for key in sorted(seen)]


def python_identity() -> dict[str, Any]:
    return {"version": sys.version.split()[0], "executable": sys.executable}


def tree_sizes(path: Path) -> dict[str, Any]:
    """How many files a throwaway home holds, and how many bytes: proof the harness wrote there."""

    if not path.exists():
        return {"path": str(path), "exists": False}
    files = [item for item in path.rglob("*") if item.is_file() and not item.is_symlink()]
    return {"path": str(path), "exists": True, "files": len(files), "bytes": sum(item.stat().st_size for item in files)}


# -- the harnesses' own transcripts --------------------------------------------------------------


def copy_tree(source: Path, target: Path, *, patterns: Iterable[str] = ("*",)) -> list[str]:
    """Copy the files under ``source`` that match ``patterns`` into ``target``; returns their relative paths."""

    copied: list[str] = []
    if not source.exists():
        return copied
    for pattern in patterns:
        for item in sorted(source.rglob(pattern)):
            if not item.is_file() or item.is_symlink():
                continue
            relative = item.relative_to(source)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copyfile(item, destination)
            except OSError:
                continue
            copied.append(str(relative))
    return sorted(set(copied))


def served_providers(document: Any) -> list[dict[str, Any]]:
    """Every ``provider`` (with its ``model``) a transcript's objects name, as OpenRouter reports them."""

    found: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            provider = value.get("provider")
            if isinstance(provider, str) and provider:
                entry = {"provider": provider}
                if isinstance(value.get("model"), str):
                    entry["model"] = value["model"]
                if entry not in found:
                    found.append(entry)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(document)
    return found


# -- summary.md -------------------------------------------------------------------------------------


def _cell(text: Any, limit: int) -> str:
    rendered = str(text).replace("|", "\\|").replace("\n", " ")
    return rendered if len(rendered) <= limit else rendered[: limit - 1] + "…"


def _facts(value: Mapping[str, Any], prefix: str = "") -> Iterable[tuple[str, Any]]:
    """A report's plain values, nested names joined with dots; lists of objects stay in run.json."""

    for key, item in value.items():
        if isinstance(item, Mapping):
            yield from _facts(item, f"{prefix}{key}.")
        elif isinstance(item, list) and any(isinstance(entry, (Mapping, list)) for entry in item):
            yield f"{prefix}{key}", f"{len(item)} entries (run.json)"
        else:
            yield f"{prefix}{key}", item


# Every code a matrix cell can carry (`score.symbol` for the letter, `score.cell` for the mark), said once, so that the run's own
# summary and the dispatch's matrix (`matrix.py`) cannot list different ones. `E` is printed beside the visible grade
# ``agent-decides``: the agent was woken, made an action, and the action never reached the room.
CELL_CODES = (
    "`Q` quiet by attention, `q` quiet by the agent's choice, `m` its own mhm, `S` it spoke, `O` another action, "
    "`W` woken (no turn began on it), `E` an error (the turn's action did not reach the room), `-` not judged; "
    "`!` marks a clear miss, `?` an unlisted move"
)


def _outcome_words(moment: Mapping[str, Any]) -> str:
    """A moment's outcome as the Moments table says it, in step with the matrix cells under it.

    The recorded ``outcome`` is what the run's checks read: ``misses`` means
    the moment did not fit its draft, which covers more than a clear miss
    (a turn that did not deliver, an unlisted move, a step 1 the draft does
    not expect, a hold that did not hold). The table says ``misses`` only
    where a cell carries ``!``, and otherwise says which of the others it was,
    in the cells' own words, so that a row never reads ``misses`` over cells
    that show none.
    """

    outcome = str(moment.get("outcome"))
    graded = [item for item in moment.get("graded", ()) if item.get("grade")]
    if outcome != MISSES or not graded or any(item["grade"].get("visible") == "miss" for item in graded):
        return outcome
    reasons: list[str] = []
    for item in graded:
        grade = item["grade"]
        if item.get("provider_error"):
            reasons.append("the turn's action did not reach the room (E)")
        elif grade.get("visible") == "unlisted":
            reasons.append("a move the draft does not list (?)")
        elif grade.get("visible") == "agent-decides":
            reasons.append("woken, with no turn on it (W)")
        if grade.get("step1") not in (None, "ok"):
            reasons.append(f"step 1 {grade['step1']}")
        if item.get("hold") not in (None, "held"):
            reasons.append(f"hold {item['hold']}")
    return "did not fit: " + "; ".join(dict.fromkeys(reasons)) if reasons else outcome


def _matrix_cell(item: Mapping[str, Any]) -> str:
    """One graded moment's cell: the suite's letter for the move, then the visible grade and step 1 (`score.cell`).

    A moment whose setup the live agent did not make is not graded: it reads
    ``precondition not met`` beside the letter for what the agent did; a moment
    that is not graded for any other reason (it was never judged) reads ``not
    judged``. A hold that did not hold is named after the grade, one that held
    where the column's record cannot show it (the reference's) says so, and an
    attention call that failed is named, since step 1 was then not judged.
    """

    grade = item.get("grade")
    if not grade:
        letter = move_symbol(item) if item.get("result") is not None else "-"
        return f"`{letter}` precondition not met" if item.get("precondition") else f"`{letter}` not judged"
    if item.get("hold") not in (None, "held"):
        hold = f" hold {item['hold']}"
    elif item.get("hold_unproven"):
        hold = " hold held (unproven: timing alone)"
    else:
        hold = ""
    error = f" attention error: {_cell(item['attention_error'], 80)}" if item.get("attention_error") else ""
    return f"`{grade_cell([item])}` {grade['visible']}/{grade['step1']}{' off script' if item.get('off_script') else ''}{hold}{error}"


def _said(item: Mapping[str, Any]) -> str:
    """What the agent did at a graded moment, in a few words: its delivered actions, or that it did nothing."""

    done = [action for action in item.get("actions", ()) if action.get("delivered")]
    if not done:
        if not item.get("reached"):
            return "nothing: the message was not posted, or never reached Nunchi"
        return {"attention": "attention suppressed it, so no turn began", "agent": "the agent stayed silent"}.get(
            str(item.get("by")), "no action was delivered"
        )
    return "; ".join(
        f"{action.get('kind')} \"{_cell(action.get('text'), 160)}\"" if action.get("kind") in ("message", "reply") else
        f"{action.get('kind')} {action.get('reaction')}"
        for action in done
    )


def _matrix_lines(run: Mapping[str, Any]) -> list[str]:
    """The grade matrix of a directed scene: each graded moment against the column, as the suite's matrix shows a cell.

    A cell holds the suite's letter for the move (`score.cell`), then the
    visible grade and step 1: ``S`` fits/ok. The scenes are drafts. A live
    scene adds what the agent did at each moment, and the facts of the moment
    that attention's evidence points at (``cited``).
    """

    rows = [(moment, item) for moment in run.get("moments", ()) for item in moment.get("graded", ()) if item.get("grade") or item.get("precondition")]
    if not rows:
        return []
    live = any(moment.get("played_live") for moment, _ in rows)
    lines = [
        "## Grade matrix (draft expectations, not reviewed)" if live else "## Grade matrix (draft expectations)",
        "",
        "The scenes are drafts awaiting the maintainer's review (`evals/behavior/README.md`): a grade compares the move with the draft's "
        "fitting moves and clear misses, and is not a finding about the model."
        + (" Here the agent is live, so every grade is reported and none is a failure, and its words are its own." if live else "")
        + f" Cell: {CELL_CODES}. Then the visible grade and step 1"
        + (", and `precondition not met` where the setup the scene needs was not made (not graded)." if live else
           ", and `off script` where the delivered action was not exactly the one the script makes."),
        "",
        f"| Scene | Moment | Fitting (step 1) | {run.get('harness')} |",
        "|---|---|---|---|",
        *(
            f"| {moment.get('name')} | {_cell(item.get('label'), 80)} | {', '.join(item.get('fitting', ()))} ({item.get('step1')}) | "
            f"{_matrix_cell(item)} |"
            for moment, item in rows
        ),
        "",
    ]
    if live:
        lines += ["### What the agent did, and the facts attention cited", ""]
        for moment, item in rows:
            lines.append(f"- {moment.get('name')}, {_cell(item.get('label'), 80)}: {_said(item)}.")
            for fact, cited in zip(item.get("facts", ()), item.get("cited", ())):
                lines.append(f"  - {'cited' if cited else 'not cited'}: {_cell(fact, 160)}")
            for reason in item.get("precondition", ()):
                lines.append(f"  - precondition not met: {_cell(reason, 300)}")
        lines.append("")
    return lines


def _reordered(moment: Mapping[str, Any], hold: Mapping[str, Any]) -> list[str]:
    """A line that says the scene was played in another order than it is written, where a held turn made the agent's line come last.

    The messages that land in a held turn are posted before the agent's line the turn plays, so a scene that has that line
    before one of them (`asked-while-busy`: the agent's reply, then Alice's thanks) is played with it after. A live model composes
    its reply with the later message already in the room and may drop it once the core has shown it the page.
    """

    scene = list(moment.get("live") or ())
    if hold.get("trigger") not in scene:
        return []
    start = scene.index(hold["trigger"])
    land = [event for event in hold.get("events", ()) if event in scene]
    end = max((scene.index(event) for event in land), default=start)
    moved = [
        line["event"] for line in moment.get("lines", ()) if line.get("trigger") == hold.get("trigger") and line.get("event") in scene[start : end + 1]
    ]
    if not moved:
        return []
    written = ", ".join(scene[start : end + 1])
    played = ", ".join([hold["trigger"], *land, *moved])
    return [
        f"- {moment.get('name')}: **played in another order than the scene's.** The scene has {written}; played, {played}: the agent's "
        f"{', '.join(moved)} is said after {', '.join(land)} have landed, since they land in the turn that plays it. A live model composes its "
        f"reply with those messages already in the room and may drop it once it has been shown them, so {', '.join(moved)} cannot be assumed in a "
        f"live run, and what the scene says the agent had already done holds only once {land[-1]} is in."
    ]


def _played_lines(run: Mapping[str, Any]) -> list[str]:
    """How a directed scene was played where the agent's own history or a held turn is in it (rehearsal PR 4c).

    The cue the director added, the time that was compressed, each earlier line
    of the agent's and whether it landed as the scene has it, and each hold
    and how it went. A scene without any of them has nothing to say here.
    """

    lines: list[str] = []
    for moment in run.get("moments", ()):
        if moment.get("expect") != "directed" or not (moment.get("lines") or moment.get("holds") or moment.get("stopped")):
            continue
        name = moment.get("name")
        for cue in moment.get("cues", ()):
            lines.append(
                f"- {name}: played with a cue. The agent's {cue.get('before')} answers nothing in the scene, so the director added "
                f"{cue.get('author')}'s message just before it: \"{cue.get('text')}\". A live model sees it in the room's history."
            )
        if moment.get("compressed"):
            seconds = int(moment["compressed"])
            span = f"{seconds // 3600} h" if seconds >= 3600 and not seconds % 3600 else f"{seconds // 60} min" if seconds >= 120 else f"{seconds} s"
            lines.append(
                f"- {name}: time compressed. The scene's {span} after the agent's first line play out in seconds, since the stand-in "
                "stamps the agent's post at the wall and nothing after it can be backdated."
            )
        for line in moment.get("lines", ()):
            said = f"reaction {line.get('reaction')}" if line.get("kind") == "reaction" else f"{line.get('kind')} \"{_cell(line.get('text'), 90)}\""
            if line.get("live"):
                # Live, the agent's words are its own: only the kind of move is checked.
                result = "landed" if not line.get("problems") else "**did not land**"
                lines.append(
                    f"- {name}: the scene has the agent's earlier line {line.get('event')} ({said}, on {line.get('trigger')}). The live "
                    f"agent did this instead: {_cell(line.get('did'), 300)}. The kind of move {result}."
                )
                continue
            landed = "landed as the scene has it" if not line.get("problems") else "did not land: " + "; ".join(line["problems"])
            lines.append(f"- {name}: the agent's earlier line {line.get('event')} ({said}, on {line.get('trigger')}) {landed}.")
        for hold in moment.get("holds", ()):
            lines.append(
                f"- {name}: hold on the turn at {hold.get('trigger')} ({hold.get('kind')}; {', '.join(hold.get('events', ()))} landed in it"
                + ("; timing, nothing held the live agent" if hold.get("live") else "")
                + f"): **{hold.get('outcome')}{', unproven' if hold.get('live') and hold.get('outcome') == 'held' and hold.get('shown') is None else ''}**"
                f" ({hold.get('detail')})."
            )
            lines += _reordered(moment, hold)
        if moment.get("stopped"):
            stop = moment["stopped"]
            lines.append(
                f"- {name}: **the scene stopped** after {stop.get('after')}, because the agent's earlier line {stop.get('line')} did not land "
                f"({_cell(stop.get('why'), 300)}); what comes after it would be judged against a history the agent did not have."
            )
    return ["## How the scenes were played", "", *lines, ""] if lines else []


def _discord_lines(discord: Mapping[str, Any]) -> list[str]:
    """The Discord room in a few lines: the launcher, each process, the stand-in's verdict, continuity."""

    launcher = discord.get("launcher") or {}
    bwrap = launcher.get("bwrap") or {}
    column = discord.get("column") or {}
    standin = discord.get("standin") or {}
    lines = [
        f"- Column: #{column.get('channel')} ({column.get('channel_id')}), bot {column.get('bot')} ({column.get('bot_id')})",
        f"- Launcher: {'offline' if launcher.get('offline') else 'online'}, bubblewrap check "
        + ("skipped (" + str(bwrap.get("skipped")) + ")" if bwrap.get("skipped") else "ran"),
    ]
    for process in discord.get("processes", ()):
        preflight = process.get("preflight") or {}
        installed = process.get("installed") or {}
        on = ", ".join(f"{name} {version}" for name, version in installed.items() if name not in ("nunchi_from", "error"))
        lines.append(
            f"- {process.get('name')} ({on or installed.get('error') or 'versions not read'}): "
            f"preflight {'passed' if preflight.get('ok') else 'failed'}, keys "
            f"{', '.join(process.get('secrets', ())) or 'none'}, stopped by {process.get('stopped_by')} (exit {process.get('exit')})"
        )
    unknown = standin.get("unknown") or ()
    lines.append(
        f"- Stand-in: {'clean' if standin.get('clean') else f'{len(unknown)} unknown record(s)'}; "
        + ", ".join(f"`{name}`" for name in standin.get("outputs", ()))
    )
    start = discord.get("start_gap") or {}
    lines.append(f"- Start: {start.get('detail') or 'no start gap recorded'}" + ("" if start.get("gap") else " (the participant never saw it)"))
    for item in discord.get("reconnects", ()):
        gaps = [*item.get("transport_gaps", ()), *item.get("participant_gaps", ())]
        lines.append(
            f"- Op 7 to {item.get('bot')} before {item.get('moment')}: "
            + ("resumed" if item.get("resumed") else "did not resume")
            + (", identified again" if item.get("identified_again") else "")
            + (", the message posted meanwhile reached Nunchi" if item.get("message_reached") else ", the message posted meanwhile never reached Nunchi")
            + (f"; gaps marked: {', '.join(map(str, gaps))}" if gaps else "; no gap marked")
        )
    return lines


def summary_markdown(run: Mapping[str, Any]) -> str:
    """The run in a page: first the outcome and every reason for it, then what each check and moment found."""

    harness = run.get("harness", "?")
    mode = run.get("mode", "?")
    status = run.get("status", "?")
    checks = list(run.get("checks", ()))
    failed = [check for check in checks if not check.get("ok")]
    arm = f", {run['arm']}" if run.get("arm") else ""
    lines = [f"# Rehearsal probe: {harness} ({mode}{arm})", ""]
    delivered = sum(1 for moment in run.get("moments", ()) for post in moment.get("posts", ()) if post.get("delivered"))
    scene = any(moment.get("expect") == "directed" for moment in run.get("moments", ()))
    live_scene = any(moment.get("played_live") for moment in run.get("moments", ()))
    if status == "pass" and live_scene:
        headline = (
            "**Passed (reported, not judged):** every hard check held: the director played the scene on Discord with a live model "
            "behind the column. The grades below compare what the agent did with draft expectations nobody has reviewed; they are "
            "reported and never a failure."
        )
    elif status == "pass" and scene:
        # A scene's moves may all be silences or nods; what a pass shows is the director and the grader.
        headline = (
            "**Passed (draft expectations):** every hard check held: the director played the scene on Discord, the agent "
            "and attention were scripted, and each graded moment fit what the scene expects. This checks the director and "
            "the grader, not a model."
        )
    elif status == "pass" and not delivered:
        # Every check held, but the agent never posted: the room tools were not exercised.
        headline = (
            "**Passed, without a room action:** every hard check held and the harness reached its model, "
            "but no post reached the room, so the room tools were not exercised in this run."
        )
    elif status == "pass":
        headline = (
            "**Passed:** every hard check held: the reference participant reached its model and took part in the room "
            "through Nunchi, with attention judging."
        )
    elif status == "fail":
        headline = (
            f"**Failed:** {', '.join(check['name'] for check in failed)} did not hold."
            if failed
            else "**Failed:** the probe raised an error."
        )
    else:
        headline = {
            "could-not-run": "**Could not run:** the probe stopped before the room.",
            "stopped-at-budget": "**Stopped at the budget:** a moment was not run.",
        }.get(status, f"**{status}**")
    lines += [headline, ""]
    for check in failed:
        lines.append(f"- **{check['name']}:** {_cell(check.get('detail', ''), 1500)}")
    for error in run.get("errors", ()):
        lines.append(f"- Error: {error}")
    for moment in run.get("moments", ()):
        if moment.get("unsettled"):
            # A wait for a quiet room ran out (`checks.unsettled`): a scripted run fails on it, a live run only flags it.
            late = moment["unsettled"]
            events = ", ".join(map(str, late[:6])) + (f" and {len(late) - 6} more" if len(late) > 6 else "")
            lines.append(
                f"- Not settled ({'fails the run' if mode == 'scripted' else 'flagged, not failed'}): {moment.get('name')}: "
                f"the wait after {events} timed out, so the room had not gone quiet and a late turn or post may be missing from this record."
            )
    stopped = (run.get("spend") or {}).get("stopped_before")
    if stopped:
        # A stop before the direct question usually leaves no wake, so the run reads as failed: say why.
        lines.append(f"- The spend watchdog stopped the run at the budget before {stopped}.")
    # What the run settles, in plain lines, never cut: attention, and each harness's own verdict.
    for check in checks:
        if check.get("name") == "attention-judged" and check.get("ok"):
            lines.append(f"- Attention: {_cell(check.get('detail', ''), 1500)}")
    reports = run.get("reports") or {}
    for key, value in reports.items():
        if isinstance(value, Mapping) and value.get("verdict"):
            lines.append(f"- {key}: {value['verdict']}")
    for key, value in reports.items():
        sandbox = value.get("sandbox") if isinstance(value, Mapping) else None
        if isinstance(sandbox, Mapping) and "on" in sandbox:
            state = {True: "on", False: "off"}.get(sandbox["on"], "not known")
            lines.append(f"- {key} sandbox: {state} ({sandbox.get('detail')})")
    lines.append("")
    moments = run.get("moments", ())
    if moments:
        judged = "checked: the model and attention are scripted" if mode == "scripted" else "reported, not pass or fail: the model decides"
        lines += [
            f"## Moments ({judged})",
            "",
            "| Moment | Expected | Graded message reached Nunchi | Turns on it | Posts delivered | Outcome |",
            "|---|---|---|---|---|---|",
        ]
        for moment in moments:
            posts = moment.get("posts", ())
            outcome = _outcome_words(moment)
            if "ERROR_FALLBACK" in moment.get("graded_wake_sources", ()):
                outcome += " (woken by attention's error fallback, not its judgment)"
            lines.append(
                f"| {moment.get('name')} | {moment.get('expect')} | {'yes' if moment.get('reached') else 'no'} | "
                f"{moment.get('graded_turns', 0)} | {sum(1 for post in posts if post.get('delivered'))} of {len(posts)} | {outcome} |"
            )
        lines.append("")
        for moment in moments:
            for post in moment.get("posts", ()):
                text = str(post.get("text", "")).replace("\n", " ")
                lines.append(f"- {moment.get('name')} post ({post.get('delivery')}): {text[:300]}")
            # The Discord room's other moves: a reaction is not a post.
            for action in moment.get("actions", ()):
                if action.get("kind") == "reaction":
                    lines.append(f"- {moment.get('name')} reaction ({action.get('delivery')}): {action.get('reaction')} on {action.get('target_event_id')}")
            for delivery in moment.get("deliveries", ()) if run.get("discord") else ():
                if delivery.get("note"):
                    lines.append(f"- {moment.get('name')}, {delivery.get('scene_event')}: {delivery['note']}")
        lines.append("")
    lines += _matrix_lines(run)
    lines += _played_lines(run)
    discord = run.get("discord")
    if isinstance(discord, Mapping):
        lines += ["## The Discord room", "", *_discord_lines(discord), ""]
    if checks:
        lines += ["## Hard checks", "", "| Check | Result | Detail |", "|---|---|---|"]
        for check in checks:
            lines.append(f"| {check['name']} | {'pass' if check['ok'] else 'FAIL'} | {_cell(check.get('detail', ''), 600)} |")
        lines.append("")
    if reports:
        lines += ["## What the harness showed", ""]
        for key, value in reports.items():
            if not isinstance(value, Mapping):
                continue
            for name, item in _facts(value):
                if name != "verdict":
                    shown = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, default=str)
                    lines.append(f"- {key}.{name}: {_cell(shown, 300)}")
        lines.append("")
    models = run.get("models") or {}
    if models:
        lines += ["## Models", ""]
        for role, entry in models.items():
            lines.append(f"- {role}: requested `{entry.get('requested')}`; served {entry.get('served') or 'not shown'}")
        lines.append("")
    spend = run.get("spend") or {}
    if spend:
        lines += [
            "## Spend",
            "",
            f"- Budget: ${spend.get('budget_usd')} per probe run ({spend.get('limit')})",
            f"- Spent according to the key's usage: {spend.get('spent_usd')}",
        ]
        readings = spend.get("readings") or ()
        last = readings[-1] if readings and isinstance(readings[-1], Mapping) else {}
        if "series" in last:
            # The last reading read the lagging figure up to its bound; the last figure is the settled one.
            settled = last.get("usage")
            lines += [
                f"- Last reading, after the last moment: {len(last['series'])} read(s) over {last.get('waited_seconds')} s, "
                f"up to the bound of {last.get('wait_bound_seconds')} s; the settled figure is the last one read "
                f"({settled if settled is not None else 'none: no read gave a figure'}), "
                "and charges posted after the bound are missed",
                "- Each read, as seconds after the last moment: usage (the lag shows here): "
                + "; ".join(f"{at}: {'not read' if usage is None else usage}" for at, usage in last["series"]),
            ]
        calls = spend.get("model_calls")
        if isinstance(calls, Mapping):
            lines.append(f"- Model calls counted: agent {calls.get('agent')}, attention {calls.get('attention')} ({calls.get('basis')})")
            lines.append(
                f"- Cost of the run: recorded {spend.get('spent_usd')} (the key's usage, which lags and counts other runs on the key), "
                f"estimated {spend.get('estimated_usd')} (the counted calls times assumed costs per call, `spend.ESTIMATED_USD_PER_CALL`, "
                "not measured)"
            )
        if spend.get("stopped_before"):
            lines.append(f"- Stopped before: {spend['stopped_before']}")
        if not spend.get("read"):
            lines.append(f"- Not read: {spend.get('not_read_because')}")
        lines.append("")
    lines += [
        "## Key and canary scan",
        "",
        "Every output, this page included, is scanned once written (`scan.json`); a hit deletes them all and puts the leak notice here.",
        "",
    ]
    install = run.get("harness_install") or {}
    commit = run.get("commit") or {}
    lines += [
        "## Record",
        "",
        f"- Commit: `{commit.get('sha')}`{' (dirty)' if commit.get('dirty') else ''}",
        f"- Nunchi: {json.dumps(run.get('nunchi', {}).get('wheel') or run.get('nunchi', {}).get('location'))}",
        f"- Harness: {install.get('version')} (pinned {install.get('expected')})",
        f"- Command: `{' '.join(run.get('command', ()))}`",
        "",
        "Everything else is in `run.json`.",
        "",
    ]
    return "\n".join(lines)
