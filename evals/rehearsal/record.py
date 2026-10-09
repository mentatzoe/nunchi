"""The run record AGENTS.md asks for, and the harnesses' own transcripts (step 9f, PR 1).

Every live run records the installed version, identity, configuration,
command, and complete result. The probe writes, under ``<out>/<harness>/``:

- ``run.json``: the commit, the Nunchi wheel's sha256, the harness, mod and
  plugin versions and package lists, the binding, the requested models and
  the providers that served them, every config written with its sha256 (the
  configs name variables, never their values), every command the probe and
  the integrations ran with the names of its environment's variables, the
  variable names of the harness's other processes (Hermes's own, and what
  its builders give the agent's commands), the spend readings against the
  budget (the last one reads the lagging usage figure up to a bound and keeps
  each read), each moment, and the checks;
- ``checks.json`` and ``summary.md`` (written even when the run fails), and
  ``scan.json``, the key and canary scan over all of it (`scan.enforce`);
- the participant's receipts, the stand-in's wire log, and the harness's own
  transcript.

Transcripts are recorded by thin subclasses of the integrations' own process
wrappers (`recording_app_server`, `recording_claude_session`): they copy each
line the harness reads and writes, and change nothing else.
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


def npm_packages(executable: str | None) -> dict[str, Any] | None:
    """``npm ls --all --json`` for the npm prefix an executable was installed into, when there is one."""

    if not executable:
        return None
    path = Path(executable).resolve()
    prefix = next((parent.parent for parent in path.parents if parent.name == "node_modules"), None)
    if prefix is None or shutil.which("npm") is None:
        return None
    argv = ["npm", "ls", "--all", "--json", "--prefix", str(prefix)]
    env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""), "npm_config_update_notifier": "false"}
    # The command it ran, for the record's ``commands``.
    entry: dict[str, Any] = {"prefix": str(prefix), "command": {"argv": argv, "env": env}}
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=120, check=False, env=env)
        entry["tree"] = json.loads(done.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        entry["error"] = type(exc).__name__
    return entry


def python_identity() -> dict[str, Any]:
    return {"version": sys.version.split()[0], "executable": sys.executable}


def home_snapshot(path: Path) -> dict[str, Any]:
    """Whether a directory exists, and a digest of its listing (names, sizes, times)."""

    if not path.exists():
        return {"path": str(path), "exists": False}
    lines = []
    for item in sorted(path.rglob("*")):
        try:
            stat = item.lstat()
        except OSError:
            continue
        lines.append(f"{item.relative_to(path)} {stat.st_size} {stat.st_mtime_ns}")
    return {
        "path": str(path),
        "exists": True,
        "entries": len(lines),
        "listing_sha256": hashlib.sha256("\n".join(lines).encode()).hexdigest(),
    }


def tree_sizes(path: Path) -> dict[str, Any]:
    """How many files a throwaway home holds, and how many bytes: proof the harness wrote there."""

    if not path.exists():
        return {"path": str(path), "exists": False}
    files = [item for item in path.rglob("*") if item.is_file() and not item.is_symlink()]
    return {"path": str(path), "exists": True, "files": len(files), "bytes": sum(item.stat().st_size for item in files)}


# -- the harnesses' own transcripts --------------------------------------------------------------


class _TeeLines:
    """A text stream's lines, each also written to a transcript."""

    def __init__(self, stream: Any, record: Callable[[str], None]) -> None:
        self._stream = stream
        self._record = record

    def __iter__(self):
        for line in self._stream:
            self._record(line)
            yield line

    def close(self) -> None:
        self._stream.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


def _parsed(line: str) -> Any:
    try:
        return json.loads(line)
    except ValueError:
        return {"text": line.rstrip("\n")}


def recording_app_server(transcript: JsonLines, launched: list[dict[str, Any]]) -> type:
    """`codex_app_server.client.AppServer`, also writing every JSON-RPC message both ways to ``transcript``.

    ``launched`` gets each app-server it starts: argv, cwd and environment
    (kept in memory; the record keeps only the variable names).
    """

    from nunchi.integrations.codex_app_server.client import AppServer

    class RecordingAppServer(AppServer):
        def start(self) -> None:
            launched.append(
                {"argv": self.command(), "cwd": self.working_directory, "environment": dict(self.environment)}
            )
            super().start()

        def _write(self, message: Mapping[str, Any]) -> None:
            transcript.write({"direction": "to-codex", "message": dict(message)})
            super()._write(message)

        def _read_stdout(self, process: Any) -> None:
            process.stdout = _TeeLines(
                process.stdout, lambda line: transcript.write({"direction": "from-codex", "message": _parsed(line)})
            )
            super()._read_stdout(process)

        def _read_stderr(self, process: Any) -> None:
            process.stderr = _TeeLines(
                process.stderr, lambda line: transcript.write({"direction": "codex-stderr", "message": line.rstrip("\n")})
            )
            super()._read_stderr(process)

    return RecordingAppServer


def recording_claude_session(
    transcript: JsonLines, launched: list[dict[str, Any]], environment: Mapping[str, str] | None = None
) -> type:
    """`ClaudeCodeSession`, also writing its stream-json both ways and its stderr to ``transcript``.

    ``environment`` is merged into the session's own before each launch: a
    scripted run's proxy settings, which only Claude Code's processes get.
    ``launched`` gets each process the session starts: argv, cwd and
    environment (kept in memory; the record keeps only the variable names).
    """

    from nunchi.integrations.claude_code_gate import ClaudeCodeSession

    extra = dict(environment or {})

    class RecordingClaudeSession(ClaudeCodeSession):
        _starting = False

        def start(self) -> None:
            self.environment.update(extra)
            self._starting = True
            try:
                super().start()
            finally:
                self._starting = False

        def command(self, resume: str | None) -> list[str]:
            command = super().command(resume)
            if self._starting:
                # Only start() launches; any other caller only asks what the command would be.
                launched.append(
                    {"argv": list(command), "cwd": str(self.working_directory), "environment": dict(self.environment)}
                )
            return command

        def _write(self, message: Mapping[str, Any]) -> None:
            transcript.write({"direction": "to-claude", "message": dict(message)})
            super()._write(message)

        def _read_stdout(self, process: Any) -> None:
            process.stdout = _TeeLines(
                process.stdout, lambda line: transcript.write({"direction": "from-claude", "message": _parsed(line)})
            )
            super()._read_stdout(process)

        def _read_stderr(self, process: Any) -> None:
            process.stderr = _TeeLines(
                process.stderr, lambda line: transcript.write({"direction": "claude-stderr", "message": line.rstrip("\n")})
            )
            super()._read_stderr(process)

    return RecordingClaudeSession


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


def sqlite_tables(path: Path, tables: Sequence[str]) -> dict[str, list[dict[str, Any]]]:
    """Every row of ``tables`` in a SQLite file, opened read-only; a table it lacks is left out."""

    import sqlite3

    if not path.exists():
        return {}
    found: dict[str, list[dict[str, Any]]] = {}
    with contextlib.closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        present = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for table in tables:
            if table in present:
                rows = db.execute(f'SELECT * FROM "{table}"')
                found[table] = [
                    {key: value.hex() if isinstance(value, bytes) else value for key, value in dict(row).items()} for row in rows
                ]
    return found


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
    if status == "pass" and not delivered:
        # Every check held, but the agent never posted: the room tools were not exercised.
        headline = (
            "**Passed, without a room action:** every hard check held and the harness reached its model, "
            "but no post reached the room, so the room tools were not exercised in this run."
        )
    elif status == "pass":
        headline = (
            "**Passed:** every hard check held: the harness reached its model and took part in the room "
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
    for key, value in reports.items():
        # Where a scripted harness reached, and what else it tried to (Claude Code's refusing proxy).
        network = value.get("network") if isinstance(value, Mapping) else None
        if isinstance(network, Mapping) and network.get("detail"):
            lines.append(f"- {key} network: {network['detail']}")
    for key, value in reports.items():
        # A credential the harness reads from a fixed path, whatever HOME says (Claude Code in a cloud container).
        credentials = value.get("fixed_credentials") if isinstance(value, Mapping) else None
        if isinstance(credentials, Mapping) and credentials.get("readable"):
            lines.append(f"- {key} credential files: {credentials.get('detail')}")
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
            outcome = str(moment.get("outcome"))
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
        lines.append("")
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
