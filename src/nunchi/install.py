"""Robust installer/upgrader for Nunchi's operator-installed artifacts.

Nunchi ships integration artifacts that must live in *stable operator
locations*, decoupled from any git checkout:

1. The Hermes gateway plugin (``integrations/hermes/nunchi-gate/``) →
   ``$HERMES_HOME/plugins/nunchi-gate/`` (default ``~/.hermes``).
2. The Claude Code hook scripts
   (``integrations/claude-code/nunchi_gate_hook.py`` and
   ``nunchi_prompt_gate.py``) → ``~/.claude/hooks/``, plus fail-open shell
   wrappers that Claude Code's ``settings.json`` points at.
3. The ``nunchi-channel`` CLI, which both of the above shell out to (checked
   for presence on ``PATH``; never installed here).

Why this module exists — the incident it fixes
------------------------------------------------
The Hermes plugin was previously **symlinked** into ``~/.hermes/plugins`` from
a live git checkout. When the checkout switched branches, the running plugin
silently became whatever code that branch carried — a stale, unintended
plugin, with no signal to the operator. Separately, the Claude Code hooks were
registered by floating absolute paths into the checkout (``/Volumes/...``);
when that path moved or the volume unmounted, the hooks broke.

The fix, implemented here, is to **copy** every artifact into a stable
operator location (never symlink), stamp each destination with the source
commit it was built from, and provide safe ``upgrade`` / ``verify`` /
``uninstall`` flows. A symlink already present at a destination is detected,
its target recorded, backed up, and replaced with a real copy.

Determinism / testability
--------------------------
The wall clock and the source-commit resolver are injectable so tests are
fully deterministic and offline. Destinations are fully overridable
(``--prefix`` / ``--hermes-home`` / ``--claude-home``) so tests only ever
touch temp directories and never the operator's real ``~/.hermes`` or
``~/.claude``.

Stdlib only (Python 3.11+); no third-party dependencies.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

#: Marker file dropped in every installed destination.
MARKER_NAME = ".nunchi-install.json"

#: Marker schema version, so future readers can detect format changes.
MARKER_VERSION = 1

#: Directory names never copied into an installed Hermes plugin. ``docs`` is
#: operator reference material (the core-patch), not runtime plugin code;
#: ``__pycache__`` and ``tests`` never belong in a deployed plugin. Everything
#: else under ``nunchi-gate/`` — the runtime ``.py`` files, ``plugin.yaml``,
#: and the ``dashboard/`` tab assets — is the *running plugin* and is copied.
HERMES_EXCLUDE_DIRS = frozenset({"__pycache__", "docs", "tests"})

#: The two Claude Code hook scripts copied into ``~/.claude/hooks/``.
CLAUDE_HOOK_FILES = ("nunchi_gate_hook.py", "nunchi_prompt_gate.py")

#: Fail-open shell wrappers written next to the hooks, mapped to the hook they
#: invoke. ``settings.json`` registers *these*, never a repo path.
CLAUDE_WRAPPERS = {
    "nunchi-pretool-reply.sh": "nunchi_gate_hook.py",
    "nunchi-user-prompt-submit.sh": "nunchi_prompt_gate.py",
}

#: Default Discord reply-tool matcher used in the printed settings snippet.
DEFAULT_REPLY_MATCHER = "mcp__plugin_discord_discord__reply"

#: Default hook timeout (seconds) in the printed settings snippet.
DEFAULT_HOOK_TIMEOUT = 35

#: Artifact group identifiers.
GROUP_HERMES = "hermes"
GROUP_CLAUDE = "claude"
GROUP_CLI = "cli"
ALL_GROUPS = (GROUP_HERMES, GROUP_CLAUDE, GROUP_CLI)

# Verify statuses.
STATUS_IN_SYNC = "in-sync"
STATUS_STALE = "stale"
STATUS_NOT_INSTALLED = "not-installed"
STATUS_SYMLINK_FOUND = "symlink-found"

# Exit codes.
EXIT_OK = 0
EXIT_ERROR = 1


class InstallError(RuntimeError):
    """A hard installer failure (e.g. missing source artifact in the repo)."""


# --------------------------------------------------------------------------
# Source-commit + repo-root resolution
# --------------------------------------------------------------------------


def discover_repo_root(start: Path | None = None) -> Path:
    """Find the repo root: the nearest ancestor holding the integration tree.

    When *start* is given, only that anchor is searched. Otherwise both the
    current working directory (so a pip-installed ``nunchi-install`` run from a
    checkout resolves its source) and this module's location are tried, in that
    order. Falls back to two levels above ``src/nunchi`` for a source layout.
    """
    if start is not None:
        anchors = [Path(start).resolve()]
    else:
        anchors = [Path.cwd().resolve(), Path(__file__).resolve()]

    for anchor in anchors:
        candidates = [anchor] if anchor.is_dir() else []
        candidates.extend(anchor.parents)
        for parent in candidates:
            if (parent / "integrations" / "hermes" / "nunchi-gate").is_dir():
                return parent

    # src/nunchi/install.py -> parents[2] == repo root
    here = Path(__file__).resolve()
    return here.parents[2] if len(here.parents) >= 3 else here.parent


def resolve_source_commit(repo_root: Path) -> str:
    """Best-effort source version stamp for *repo_root*.

    Order: ``git rev-parse HEAD`` → a ``VERSION`` file → ``"unknown"``.
    Never raises.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0:
            commit = proc.stdout.strip()
            if commit:
                return commit
    except (OSError, subprocess.SubprocessError):
        pass

    version_file = repo_root / "VERSION"
    try:
        if version_file.is_file():
            text = version_file.read_text(encoding="utf-8").strip()
            if text:
                return text
    except OSError:
        pass

    return "unknown"


# --------------------------------------------------------------------------
# Settings snippet + wrapper rendering (pure, reused by CLI + tests)
# --------------------------------------------------------------------------


def build_claude_settings_snippet(
    claude_home: Path,
    *,
    matcher: str = DEFAULT_REPLY_MATCHER,
    timeout: int = DEFAULT_HOOK_TIMEOUT,
) -> str:
    """Return the ``settings.json`` hook registration the operator should use.

    The commands point at the **stable wrapper paths** under
    ``<claude_home>/hooks/`` — never at a repo checkout.
    """
    hooks_dir = Path(claude_home) / "hooks"
    snippet = {
        "hooks": {
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": str(hooks_dir / "nunchi-user-prompt-submit.sh"),
                            "timeout": timeout,
                        }
                    ]
                }
            ],
            "PreToolUse": [
                {
                    "matcher": matcher,
                    "hooks": [
                        {
                            "type": "command",
                            "command": str(hooks_dir / "nunchi-pretool-reply.sh"),
                            "timeout": timeout,
                        }
                    ],
                }
            ],
        }
    }
    return json.dumps(snippet, indent=2)


def render_wrapper(
    wrapper_name: str, hook_path: Path, env_files: Sequence[Path]
) -> str:
    """Render a fail-open POSIX-sh wrapper for one Claude Code hook.

    The wrapper sources each operator env file in *env_files* order — a shared
    identity file first, then an optional per-hook override — before running the
    Python hook. Each file is sourced only if present, and a later file's
    exports win, so the outbound gate can narrow a shared default (e.g. its peer
    roster) without a separate wrapper. ANY failure — missing hook file, no
    ``python3``, hook error — exits ``0`` so a missing or broken gate can never
    block Claude Code.
    """
    source_lines = "".join(
        f'[ -f "{env_file}" ] && . "{env_file}"\n' for env_file in env_files
    )
    return (
        "#!/bin/sh\n"
        f"# {wrapper_name} — fail-open wrapper for the Nunchi Claude Code gate.\n"
        "# Installed and managed by `nunchi-install`. Do not edit by hand;\n"
        "# re-run `nunchi-install upgrade` to refresh it.\n"
        "#\n"
        "# Sources the operator env file(s) (if present), then runs the Python\n"
        "# hook. ANY failure — missing hook, no python3, hook error — exits 0\n"
        "# so a broken gate never blocks Claude Code.\n"
        "set -u\n"
        f'HOOK="{hook_path}"\n'
        f"{source_lines}"
        "command -v python3 >/dev/null 2>&1 || exit 0\n"
        '[ -f "$HOOK" ] || exit 0\n'
        'python3 "$HOOK" "$@" || exit 0\n'
    )


# --------------------------------------------------------------------------
# Installer
# --------------------------------------------------------------------------


class Installer:
    """Copy-based installer/upgrader for Nunchi's operator artifacts.

    All destinations are explicit and confined to *hermes_home* / *claude_home*;
    the installer never writes outside them. Pass ``dry_run=True`` to plan
    without touching disk. *clock* and *commit_resolver* are injectable for
    deterministic tests.
    """

    def __init__(
        self,
        *,
        repo_root: Path | str | None = None,
        hermes_home: Path | str | None = None,
        claude_home: Path | str | None = None,
        dry_run: bool = False,
        clock: Callable[[], datetime] | None = None,
        commit_resolver: Callable[[], str] | None = None,
        out: io.TextIOBase | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).expanduser() if repo_root else discover_repo_root()
        self.hermes_home = (
            Path(hermes_home).expanduser() if hermes_home else Path("~/.hermes").expanduser()
        )
        self.claude_home = (
            Path(claude_home).expanduser() if claude_home else Path("~/.claude").expanduser()
        )
        self.dry_run = dry_run
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._commit_resolver = commit_resolver or (lambda: resolve_source_commit(self.repo_root))
        self._out = out if out is not None else sys.stdout

        self._commit_cache: str | None = None
        self._stamp_dt: datetime = self._clock()
        self._actions: list[dict[str, Any]] = []

    # -- source paths -------------------------------------------------------

    @property
    def hermes_src(self) -> Path:
        return self.repo_root / "integrations" / "hermes" / "nunchi-gate"

    @property
    def hermes_dest(self) -> Path:
        return self.hermes_home / "plugins" / "nunchi-gate"

    @property
    def claude_src(self) -> Path:
        return self.repo_root / "integrations" / "claude-code"

    @property
    def claude_hooks_dir(self) -> Path:
        return self.claude_home / "hooks"

    # -- clock / commit -----------------------------------------------------

    def _commit(self) -> str:
        if self._commit_cache is None:
            self._commit_cache = self._commit_resolver()
        return self._commit_cache

    def _stamp_iso(self) -> str:
        return self._stamp_dt.isoformat()

    def _stamp_slug(self) -> str:
        return self._stamp_dt.strftime("%Y%m%dT%H%M%SZ")

    # -- logging ------------------------------------------------------------

    def _begin(self) -> None:
        """Reset per-command state: snapshot the clock, clear actions."""
        self._stamp_dt = self._clock()
        self._actions = []

    def _act(self, op: str, target: Path | str, note: str = "") -> None:
        record = {"op": op, "target": str(target), "note": note, "dry_run": self.dry_run}
        self._actions.append(record)
        prefix = "DRY-RUN " if self.dry_run else ""
        line = f"{prefix}{op}: {target}"
        if note:
            line += f"  ({note})"
        self._emit(line)

    def _emit(self, line: str) -> None:
        self._out.write(line + "\n")

    # -- filesystem helpers (respect dry_run) -------------------------------

    def _mkdir(self, path: Path) -> None:
        if path.exists():
            return
        self._act("mkdir", path)
        if not self.dry_run:
            path.mkdir(parents=True, exist_ok=True)

    def _backup(self, path: Path, *, kind: str = "bak") -> Path:
        """Move *path* aside to a timestamped sibling. Works for dir/file/link.

        ``kind`` distinguishes ordinary backups (``bak``) from a replaced
        symlink (``symlink.bak``) so ``uninstall`` can find and restore it. A
        numeric suffix is appended if a same-timestamp backup already exists
        (e.g. two installs within one second), so a backup never clobbers an
        earlier one or raises.
        """
        base = path.parent / f"{path.name}.{kind}.{self._stamp_slug()}"
        backup = base
        counter = 1
        while backup.exists() or backup.is_symlink():
            backup = path.parent / f"{base.name}.{counter}"
            counter += 1
        self._act("backup", path, note=f"-> {backup.name}")
        if not self.dry_run:
            os.rename(path, backup)
        return backup

    def _copy_tree(self, src: Path, dest: Path) -> list[str]:
        """Copy *src* into *dest* as a REAL directory, honoring exclusions.

        Returns the sorted list of relative file paths copied. Never creates a
        symlink: directories are made with ``mkdir`` and files are copied by
        content (a symlinked source file copies its referent's bytes).
        """
        copied: list[str] = []
        for root, dirs, files in os.walk(src):
            dirs[:] = sorted(d for d in dirs if d not in HERMES_EXCLUDE_DIRS)
            rel_root = os.path.relpath(root, src)
            for name in sorted(files):
                if name.endswith(".pyc") or name == MARKER_NAME:
                    continue
                rel = os.path.normpath(os.path.join(rel_root, name))
                copied.append(rel)
                if not self.dry_run:
                    target = dest / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(os.path.join(root, name), target)
        copied.sort()
        for rel in copied:
            self._act("copy", dest / rel)
        return copied

    def _copy_file(self, src: Path, dest: Path) -> None:
        self._act("copy", dest)
        if not self.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    def _write_text(self, dest: Path, text: str, *, executable: bool = False) -> None:
        self._act("write", dest)
        if not self.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")
            if executable:
                os.chmod(dest, 0o755)

    def _remove_tree(self, path: Path) -> None:
        self._act("remove", path)
        if not self.dry_run:
            shutil.rmtree(path)

    def _remove_file(self, path: Path) -> None:
        self._act("remove", path)
        if not self.dry_run:
            path.unlink()

    # -- markers ------------------------------------------------------------

    def _marker_path(self, dest_dir: Path) -> Path:
        return dest_dir / MARKER_NAME

    def _write_marker(
        self,
        dest_dir: Path,
        *,
        artifact: str,
        source_path: Path,
        files: Iterable[str],
        extra: dict[str, Any] | None = None,
    ) -> None:
        marker = {
            "marker_version": MARKER_VERSION,
            "artifact": artifact,
            "installer": "nunchi-install",
            "source_commit": self._commit(),
            "source_path": str(source_path),
            "installed_at": self._stamp_iso(),
            "files": sorted(files),
        }
        if extra:
            marker.update(extra)
        text = json.dumps(marker, indent=2, sort_keys=True)
        self._act("stamp", self._marker_path(dest_dir), note=f"commit={self._commit()}")
        if not self.dry_run:
            self._marker_path(dest_dir).write_text(text + "\n", encoding="utf-8")

    def _read_marker(self, dest_dir: Path) -> dict[str, Any] | None:
        path = self._marker_path(dest_dir)
        try:
            if not path.is_file():
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    # -- public commands ----------------------------------------------------

    def install(self, groups: Sequence[str] | None = None) -> dict[str, Any]:
        self._begin()
        groups = self._normalize_groups(groups)
        artifacts: dict[str, Any] = {}
        if GROUP_HERMES in groups:
            artifacts[GROUP_HERMES] = self._install_hermes()
        if GROUP_CLAUDE in groups:
            artifacts[GROUP_CLAUDE] = self._install_claude()
        if GROUP_CLI in groups:
            artifacts[GROUP_CLI] = self._check_cli()
        return self._report("install", artifacts)

    def upgrade(self, groups: Sequence[str] | None = None, *, force: bool = False) -> dict[str, Any]:
        self._begin()
        groups = self._normalize_groups(groups)
        artifacts: dict[str, Any] = {}
        if GROUP_HERMES in groups:
            artifacts[GROUP_HERMES] = self._install_hermes(upgrade=True, force=force)
        if GROUP_CLAUDE in groups:
            artifacts[GROUP_CLAUDE] = self._install_claude(upgrade=True, force=force)
        if GROUP_CLI in groups:
            artifacts[GROUP_CLI] = self._check_cli()
        return self._report("upgrade", artifacts)

    def verify(self, groups: Sequence[str] | None = None) -> dict[str, Any]:
        self._begin()
        groups = self._normalize_groups(groups)
        artifacts: dict[str, Any] = {}
        if GROUP_HERMES in groups:
            artifacts[GROUP_HERMES] = self._verify_hermes()
        if GROUP_CLAUDE in groups:
            artifacts[GROUP_CLAUDE] = self._verify_claude()
        if GROUP_CLI in groups:
            artifacts[GROUP_CLI] = self._verify_cli()
        for name, info in artifacts.items():
            self._act("verify", info.get("dest", name), note=info["status"])
        return self._report("verify", artifacts)

    def uninstall(self, groups: Sequence[str] | None = None) -> dict[str, Any]:
        self._begin()
        groups = self._normalize_groups(groups)
        artifacts: dict[str, Any] = {}
        if GROUP_HERMES in groups:
            artifacts[GROUP_HERMES] = self._uninstall_hermes()
        if GROUP_CLAUDE in groups:
            artifacts[GROUP_CLAUDE] = self._uninstall_claude()
        return self._report("uninstall", artifacts)

    # -- hermes -------------------------------------------------------------

    def _install_hermes(self, *, upgrade: bool = False, force: bool = False) -> dict[str, Any]:
        src = self.hermes_src
        dest = self.hermes_dest
        if not src.is_dir():
            raise InstallError(f"Hermes plugin source not found: {src}")

        is_symlink = dest.is_symlink()
        marker = None if is_symlink else self._read_marker(dest)

        if upgrade and not force:
            decision = self._upgrade_decision(dest_exists=dest.exists(), is_symlink=is_symlink, marker=marker)
            if decision == "skip":
                self._act("skip", dest, note=f"in-sync at {self._commit()}")
                return {
                    "action": "skip",
                    "status": STATUS_IN_SYNC,
                    "dest": str(dest),
                    "source_commit": self._commit(),
                }

        self._mkdir(dest.parent)
        extra: dict[str, Any] = {}

        if is_symlink:
            target = os.readlink(dest)
            backup = self._backup(dest, kind="symlink.bak")
            extra["replaced_symlink"] = {"target": target, "backup": str(backup)}
            self._act("replace-symlink", dest, note=f"was -> {target}")
        elif dest.exists():
            self._backup(dest, kind="bak")

        files = self._copy_tree(src, dest)
        self._write_marker(
            dest,
            artifact="hermes-plugin",
            source_path=src,
            files=files,
            extra=extra,
        )
        result = {
            "action": "upgrade" if upgrade else "install",
            "status": "installed",
            "dest": str(dest),
            "source_commit": self._commit(),
            "files": files,
        }
        if extra:
            result["replaced_symlink"] = extra["replaced_symlink"]
        return result

    def _verify_hermes(self) -> dict[str, Any]:
        dest = self.hermes_dest
        base = {"dest": str(dest), "repo_commit": self._commit()}
        if dest.is_symlink():
            return {**base, "status": STATUS_SYMLINK_FOUND, "symlink_target": os.readlink(dest)}
        if not dest.exists():
            return {**base, "status": STATUS_NOT_INSTALLED}
        marker = self._read_marker(dest)
        if marker is None:
            return {**base, "status": STATUS_STALE, "detail": "present but unmanaged (no install marker)"}
        installed = marker.get("source_commit", "unknown")
        status = STATUS_IN_SYNC if installed == self._commit() else STATUS_STALE
        return {**base, "status": status, "installed_commit": installed}

    def _uninstall_hermes(self) -> dict[str, Any]:
        dest = self.hermes_dest
        if dest.is_symlink():
            self._act("skip", dest, note="destination is a symlink, not a nunchi-install copy")
            return {"action": "skip", "dest": str(dest), "detail": "symlink, left untouched"}
        if not dest.exists():
            self._act("skip", dest, note="not installed")
            return {"action": "skip", "dest": str(dest), "detail": "not installed"}

        marker = self._read_marker(dest)
        replaced = (marker or {}).get("replaced_symlink")
        self._remove_tree(dest)

        restored = None
        if replaced:
            restored = self._restore_symlink(dest, replaced)
        result: dict[str, Any] = {"action": "removed", "dest": str(dest)}
        if restored:
            result["restored_symlink"] = restored
        return result

    def _restore_symlink(self, dest: Path, replaced: dict[str, Any]) -> dict[str, Any] | None:
        backup = replaced.get("backup")
        target = replaced.get("target")
        if backup and Path(backup).is_symlink():
            self._act("restore-symlink", dest, note=f"from backup {backup}")
            if not self.dry_run:
                os.rename(backup, dest)
            return {"dest": str(dest), "target": target, "from": "backup"}
        if target:
            self._act("restore-symlink", dest, note=f"-> {target}")
            if not self.dry_run:
                os.symlink(target, dest)
            return {"dest": str(dest), "target": target, "from": "recreated"}
        return None

    # -- claude code --------------------------------------------------------

    def _claude_installed_paths(self) -> list[Path]:
        hooks = self.claude_hooks_dir
        return [hooks / name for name in (*CLAUDE_HOOK_FILES, *CLAUDE_WRAPPERS)]

    def _claude_has_symlink(self) -> str | None:
        for path in self._claude_installed_paths():
            if path.is_symlink():
                return str(path)
        return None

    def _install_claude(self, *, upgrade: bool = False, force: bool = False) -> dict[str, Any]:
        hooks_dir = self.claude_hooks_dir
        for name in CLAUDE_HOOK_FILES:
            if not (self.claude_src / name).is_file():
                raise InstallError(f"Claude Code hook source not found: {self.claude_src / name}")

        symlink = self._claude_has_symlink()
        marker = self._read_marker(hooks_dir)

        if upgrade and not force:
            decision = self._upgrade_decision(
                dest_exists=any(p.exists() for p in self._claude_installed_paths()),
                is_symlink=symlink is not None,
                marker=marker,
            )
            if decision == "skip":
                self._act("skip", hooks_dir, note=f"in-sync at {self._commit()}")
                return {
                    "action": "skip",
                    "status": STATUS_IN_SYNC,
                    "dest": str(hooks_dir),
                    "source_commit": self._commit(),
                }

        self._mkdir(hooks_dir)
        installed_files: list[str] = []

        # Hook scripts: back up any existing copy (incl. a symlink) then copy.
        for name in CLAUDE_HOOK_FILES:
            dest = hooks_dir / name
            if dest.is_symlink() or dest.exists():
                self._backup(dest, kind="symlink.bak" if dest.is_symlink() else "bak")
            self._copy_file(self.claude_src / name, dest)
            installed_files.append(name)

        # Fail-open wrappers pointing at the stable hook paths. Each sources a
        # shared identity file first, then an optional per-hook override
        # (``nunchi-<wrapper-stem>.env``) — e.g. the outbound reply gate narrows
        # its peer roster there. Both env files are operator-owned; the
        # installer writes the wrappers but never the env files (see INSTALL.md).
        shared_env = self.claude_home / "nunchi-gate.env"
        for wrapper_name, hook_name in CLAUDE_WRAPPERS.items():
            dest = hooks_dir / wrapper_name
            if dest.is_symlink() or dest.exists():
                self._backup(dest, kind="symlink.bak" if dest.is_symlink() else "bak")
            override_env = self.claude_home / f"{Path(wrapper_name).stem}.env"
            content = render_wrapper(
                wrapper_name, hooks_dir / hook_name, [shared_env, override_env]
            )
            self._write_text(dest, content, executable=True)
            installed_files.append(wrapper_name)

        self._write_marker(
            hooks_dir,
            artifact="claude-code-hooks",
            source_path=self.claude_src,
            files=installed_files,
        )
        return {
            "action": "upgrade" if upgrade else "install",
            "status": "installed",
            "dest": str(hooks_dir),
            "source_commit": self._commit(),
            "files": installed_files,
            "settings_snippet": build_claude_settings_snippet(self.claude_home),
        }

    def _verify_claude(self) -> dict[str, Any]:
        hooks_dir = self.claude_hooks_dir
        base = {"dest": str(hooks_dir), "repo_commit": self._commit()}
        symlink = self._claude_has_symlink()
        if symlink is not None:
            return {**base, "status": STATUS_SYMLINK_FOUND, "symlink_path": symlink}
        present = [p for p in self._claude_installed_paths() if p.exists()]
        if not present:
            return {**base, "status": STATUS_NOT_INSTALLED}
        marker = self._read_marker(hooks_dir)
        if marker is None:
            return {**base, "status": STATUS_STALE, "detail": "present but unmanaged (no install marker)"}
        installed = marker.get("source_commit", "unknown")
        status = STATUS_IN_SYNC if installed == self._commit() else STATUS_STALE
        return {**base, "status": status, "installed_commit": installed}

    def _uninstall_claude(self) -> dict[str, Any]:
        hooks_dir = self.claude_hooks_dir
        removed: list[str] = []
        for name in (*CLAUDE_HOOK_FILES, *CLAUDE_WRAPPERS, MARKER_NAME):
            path = hooks_dir / name
            if path.is_symlink() or path.exists():
                self._remove_file(path)
                removed.append(name)
        if not removed:
            self._act("skip", hooks_dir, note="not installed")
            return {"action": "skip", "dest": str(hooks_dir), "detail": "not installed"}
        return {"action": "removed", "dest": str(hooks_dir), "removed": removed}

    # -- cli ----------------------------------------------------------------

    def _check_cli(self) -> dict[str, Any]:
        path = shutil.which("nunchi-channel")
        if path:
            self._act("check", "nunchi-channel", note=f"found: {path}")
            return {"status": STATUS_IN_SYNC, "resolved": path}
        guidance = (
            "nunchi-channel not found on PATH. Install the package to provide it: "
            "`pip install nunchi` (or `pip install .` from a checkout). Both the "
            "Hermes plugin and the Claude Code hooks shell out to nunchi-channel."
        )
        self._act("check", "nunchi-channel", note="MISSING")
        self._emit("  " + guidance)
        return {"status": STATUS_NOT_INSTALLED, "resolved": None, "guidance": guidance}

    def _verify_cli(self) -> dict[str, Any]:
        return self._check_cli()

    # -- shared helpers -----------------------------------------------------

    def _upgrade_decision(self, *, dest_exists: bool, is_symlink: bool, marker: dict[str, Any] | None) -> str:
        """Return ``"install"`` or ``"skip"`` for an upgrade of one artifact.

        A symlink or a missing/unmanaged destination always (re)installs — the
        symlink is the exact bug we replace. Otherwise re-copy only when the
        installed commit differs from the current source commit.
        """
        if is_symlink or not dest_exists or marker is None:
            return "install"
        return "skip" if marker.get("source_commit") == self._commit() else "install"

    def _normalize_groups(self, groups: Sequence[str] | None) -> tuple[str, ...]:
        if not groups:
            return ALL_GROUPS
        unknown = [g for g in groups if g not in ALL_GROUPS]
        if unknown:
            raise InstallError(f"unknown artifact group(s): {', '.join(unknown)}")
        # preserve canonical order
        return tuple(g for g in ALL_GROUPS if g in groups)

    def _report(self, command: str, artifacts: dict[str, Any]) -> dict[str, Any]:
        return {
            "command": command,
            "dry_run": self.dry_run,
            "repo_root": str(self.repo_root),
            "source_commit": self._commit(),
            "artifacts": artifacts,
            "actions": list(self._actions),
        }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _resolve_home(
    explicit: str | None,
    env_var: str | None,
    prefix: Path | None,
    prefix_subdir: str,
    default: str,
) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    if env_var and os.environ.get(env_var):
        return Path(os.environ[env_var]).expanduser()
    if prefix is not None:
        return prefix / prefix_subdir
    return Path(default).expanduser()


def _build_parser() -> argparse.ArgumentParser:
    # Global options live on a shared parent attached to BOTH the top parser
    # and every subparser, with SUPPRESS defaults so a subparser's absence
    # never clobbers a value parsed before the subcommand. This lets the
    # operator write flags in either position: `nunchi-install --dry-run
    # install` and `nunchi-install install --dry-run` both work.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--dry-run", action="store_true", default=argparse.SUPPRESS,
        help="print planned actions; touch nothing",
    )
    common.add_argument(
        "--prefix", metavar="DIR", default=argparse.SUPPRESS,
        help="base dir; homes default to DIR/.hermes and DIR/.claude",
    )
    common.add_argument(
        "--hermes-home", metavar="DIR", default=argparse.SUPPRESS,
        help="Hermes home (default $HERMES_HOME or ~/.hermes)",
    )
    common.add_argument(
        "--claude-home", metavar="DIR", default=argparse.SUPPRESS,
        help="Claude Code home (default ~/.claude)",
    )
    common.add_argument(
        "--repo-root", metavar="DIR", default=argparse.SUPPRESS,
        help="source repo root (default: auto-discovered)",
    )

    parser = argparse.ArgumentParser(
        prog="nunchi-install",
        parents=[common],
        description=(
            "Install/upgrade Nunchi's operator artifacts (Hermes plugin, Claude "
            "Code hooks) by copying — never symlinking — into stable locations."
        ),
    )

    sub = parser.add_subparsers(dest="command", required=True)

    def add_group_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--only",
            action="append",
            choices=list(ALL_GROUPS),
            metavar="GROUP",
            help="limit to one or more of: hermes, claude, cli (repeatable)",
        )

    add_group_arg(
        sub.add_parser("install", parents=[common], help="install all artifacts (backs up any existing copy first)")
    )
    up = sub.add_parser("upgrade", parents=[common], help="re-copy only artifacts whose source commit changed")
    add_group_arg(up)
    up.add_argument("--force", action="store_true", help="re-copy even if the commit is unchanged")
    add_group_arg(sub.add_parser("verify", parents=[common], help="report installed-vs-repo drift per artifact"))
    add_group_arg(
        sub.add_parser("uninstall", parents=[common], help="remove installed copies; restore a backed-up symlink")
    )
    ps = sub.add_parser(
        "print-claude-settings", parents=[common], help="print the settings.json hook registration snippet"
    )
    ps.add_argument("--matcher", default=DEFAULT_REPLY_MATCHER, help="PreToolUse tool matcher")

    return parser


def main(argv: Sequence[str] | None = None, *, out: io.TextIOBase | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    stream = out if out is not None else sys.stdout

    # Global options use SUPPRESS defaults (see _build_parser); read via getattr.
    arg_prefix = getattr(args, "prefix", None)
    arg_hermes_home = getattr(args, "hermes_home", None)
    arg_claude_home = getattr(args, "claude_home", None)
    arg_repo_root = getattr(args, "repo_root", None)
    dry_run = getattr(args, "dry_run", False)

    prefix = Path(arg_prefix).expanduser() if arg_prefix else None
    hermes_home = _resolve_home(arg_hermes_home, "HERMES_HOME", prefix, ".hermes", "~/.hermes")
    claude_home = _resolve_home(arg_claude_home, None, prefix, ".claude", "~/.claude")

    installer = Installer(
        repo_root=arg_repo_root,
        hermes_home=hermes_home,
        claude_home=claude_home,
        dry_run=dry_run,
        out=stream,
    )

    try:
        if args.command == "print-claude-settings":
            stream.write(build_claude_settings_snippet(claude_home, matcher=args.matcher) + "\n")
            return EXIT_OK

        groups = getattr(args, "only", None)
        if args.command == "install":
            installer.install(groups)
            _print_post_install(installer, stream)
        elif args.command == "upgrade":
            installer.upgrade(groups, force=args.force)
            _print_post_install(installer, stream)
        elif args.command == "verify":
            installer.verify(groups)
        elif args.command == "uninstall":
            installer.uninstall(groups)
        else:  # pragma: no cover - argparse enforces the choices
            parser.error(f"unknown command: {args.command}")
    except InstallError as exc:
        stream.write(f"install error: {exc}\n")
        return EXIT_ERROR

    return EXIT_OK


def _print_post_install(installer: Installer, stream: io.TextIOBase) -> None:
    """After an install/upgrade, print the settings.json snippet + reminders."""
    stream.write("\nClaude Code settings.json — register the stable wrapper paths:\n\n")
    stream.write(build_claude_settings_snippet(installer.claude_home) + "\n")
    stream.write(
        "\nThis snippet is NOT applied for you: settings.json is the operator's "
        "file. Merge the block above by hand (or re-print it with "
        "`nunchi-install print-claude-settings`).\n"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
