"""Enforcement: the retired send-time gate and the permit ledger stay removed.

Nunchi makes ONE admission judgment per turn, at wake. The Claude Code
integration once had a second, send-time judgment (``nunchi_gate_hook.py``, a
``PreToolUse`` hook) plus a permit/ledger side-store to keep the two judgments
consistent. Both were removed by design decision (2026-07-10): the second
judgment re-derived "which message am I answering" and silenced composed
replies (the false-PASS bug); the ledger existed only to patch that split.

Removal means removal: this test scans the ENTIRE project — source, tests,
docs, examples — and fails if the retired artifacts or the ledger shape creep
back in. A narrowly-scoped enforcement test would be worse than none.

Honest limitation (Aleph): this is a NAME-level guard. It keeps the retired
filenames and the ledger vocabulary out and asserts the installer never
re-registers a PreToolUse entry — it cannot detect a *renamed* second judge or
literally count classifier invocations per turn. That property is enforced by
review of the settings surface (the installer snippet is the only registration
path this repo ships) rather than by grep.

Allowed exceptions, each one deliberate:
  * this file (it names the patterns as literals);
  * ``CHANGELOG.md`` (immutable release history may mention removed things);
The V2 installer is blocked until accepted external packets exist, so it has no
exception here: even retirement vocabulary does not belong in that surface.
"""
from __future__ import annotations

import pathlib
import re
import unittest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Directories never scanned: VCS internals, caches, other worktrees, vendored
# runtime state.
_SKIP_DIRS = {
    ".git", "__pycache__", ".worktrees", ".specify", "node_modules",
    # Build artifacts are copies of tracked source; scanning them makes the
    # test fail after an ordinary `python -m build` (round-2 finding).
    "build", "dist", ".eggs",
    # Gitignored agent-session history written into the checkout by the
    # operator's harness; conversation notes about removing the ledger would
    # otherwise trip the ledger scan forever.
    ".remember",
}

_TEXT_SUFFIXES = {".py", ".md", ".sh", ".example", ".toml", ".yaml", ".yml", ".json", ".txt"}

# The retired send-time gate: nothing may reference these artifact names,
# except the installer/uninstaller machinery that removes them.
_RETIRED_ARTIFACTS = (
    "nunchi_gate_hook",
    "nunchi-pretool-reply",
)
_RETIRED_ALLOWED = {
    "tests/test_no_second_judgment.py",
    "CHANGELOG.md",
    "tests/test_no_home_writes.py",  # scanner marker history in its docstring
    # Migration instructions must NAME the retired artifacts so operators can
    # delete the right settings entry / recognize the retired files:
    "docs/INSTALL.md",
}

# The ledger shape: no permit store, no correlation records, no obligation
# queue anywhere in the Claude Code integration or core.
_LEDGER_PATTERNS = (
    re.compile(r"nunchi_causal_permit", re.IGNORECASE),
    re.compile(r"\bcausal[ _-]permit\b", re.IGNORECASE),
    re.compile(r"NUNCHI_PERMIT_", re.IGNORECASE),
    re.compile(r"\bwrite_permit\b|\bread_permit\b|\bclear_permit\b"),
    re.compile(r"\bbid[ _-]ledger\b", re.IGNORECASE),
)
_LEDGER_ALLOWED = {
    "tests/test_no_second_judgment.py",
    "CHANGELOG.md",
}


def _iter_files() -> list[pathlib.Path]:
    out = []
    for path in _REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in _TEXT_SUFFIXES:
            continue
        rel_parts = path.relative_to(_REPO_ROOT).parts
        if any(part in _SKIP_DIRS or part.endswith(".egg-info") for part in rel_parts):
            continue
        out.append(path)
    return sorted(out)


def _rel(path: pathlib.Path) -> str:
    return str(path.relative_to(_REPO_ROOT))


class RetiredSendTimeGateStaysRemoved(unittest.TestCase):
    def test_retired_artifact_files_do_not_exist(self):
        ghosts = [
            _rel(p)
            for p in _iter_files()
            if any(p.name.startswith(a) for a in _RETIRED_ARTIFACTS)
        ]
        self.assertEqual(ghosts, [], f"retired send-time gate files present: {ghosts}")

    def test_no_references_to_retired_artifacts(self):
        violations: list[str] = []
        scanned = 0
        for path in _iter_files():
            rel = _rel(path)
            if rel in _RETIRED_ALLOWED:
                continue
            scanned += 1
            text = path.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), start=1):
                for artifact in _RETIRED_ARTIFACTS:
                    if artifact in line:
                        violations.append(f"{rel}:{lineno}: references {artifact!r}")
        self.assertGreaterEqual(scanned, 40, "scan looks broken: too few files")
        self.assertEqual(violations, [], "\n".join(violations))

class LedgerShapeStaysRemoved(unittest.TestCase):
    def test_no_ledger_references_anywhere(self):
        violations: list[str] = []
        scanned = 0
        for path in _iter_files():
            rel = _rel(path)
            if rel in _LEDGER_ALLOWED:
                continue
            scanned += 1
            text = path.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), start=1):
                for pattern in _LEDGER_PATTERNS:
                    if pattern.search(line):
                        violations.append(
                            f"{rel}:{lineno}: ledger-shaped reference {pattern.pattern!r}"
                        )
        self.assertGreaterEqual(scanned, 40, "scan looks broken: too few files")
        self.assertEqual(violations, [], "\n".join(violations))

    def test_detector_catches_known_bad_samples(self):
        """An enforcement test that cannot fail is worse than none."""
        bad_lines = (
            "from nunchi_causal_permit import read_permit",
            "NUNCHI_PERMIT_DIR=/tmp/permits",
            "the bid ledger records an obligation",
        )
        for bad in bad_lines:
            self.assertTrue(
                any(p.search(bad) for p in _LEDGER_PATTERNS),
                f"detector missed: {bad!r}",
            )


if __name__ == "__main__":
    unittest.main()
