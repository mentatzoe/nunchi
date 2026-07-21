"""Enforcement: served web assets must not use HTML-injection sinks.

The retired Hermes V1 dashboard is no longer part of the executable product
surface. This repository-wide guard remains for every served asset that does
exist:

- Scans the ENTIRE repository for served web assets (.js/.mjs/.cjs/.jsx/
  .ts/.tsx/.html/.htm/.vue/.svelte) — not a hand-picked file list — and
  fails on any forbidden sink.
- Self-tests the detector against known-bad samples so the enforcement
  itself is verified.
- Asserts the scan is non-empty so layout changes cannot silently disable it.
"""

from __future__ import annotations

import pathlib
import unittest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Anything a browser would execute/render counts as a served asset.
_ASSET_SUFFIXES = {
    ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".html", ".htm", ".vue", ".svelte",
}

# Directories that never contain served assets of this project.
# .remember is gitignored agent-session history written into live checkouts
# by the operator's harness (same rationale as test_no_second_judgment).
_SKIP_DIRS = {".git", ".worktrees", "__pycache__", "node_modules", ".venv", "venv", ".remember"}

# Forbidden HTML-injection sinks. Substring match is intentional:
# "document.write" also catches document.writeln; property writes and reads
# are both banned (there is no legitimate use in this codebase).
FORBIDDEN_SINKS = (
    "innerHTML",
    "outerHTML",
    "insertAdjacentHTML",
    "document.write",
    "dangerouslySetInnerHTML",
    "srcdoc",
)

def _iter_served_assets() -> list[pathlib.Path]:
    assets: list[pathlib.Path] = []
    for path in _REPO_ROOT.rglob("*"):
        rel_parts = path.relative_to(_REPO_ROOT).parts
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        if path.is_file() and path.suffix.lower() in _ASSET_SUFFIXES:
            assets.append(path)
    return sorted(assets)


def _scan_asset(name: str, text: str) -> list[str]:
    """Return violation strings for forbidden sinks in *text*."""
    violations = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for sink in FORBIDDEN_SINKS:
            if sink in line:
                violations.append(f"{name}:{lineno}: forbidden sink {sink!r}")
    return violations


class TestNoInjectionSinksInServedAssets(unittest.TestCase):
    def test_whole_repo_scan_finds_no_forbidden_sinks(self):
        violations: list[str] = []
        scanned: list[pathlib.Path] = []
        for path in _iter_served_assets():
            scanned.append(path)
            rel = str(path.relative_to(_REPO_ROOT))
            violations.extend(_scan_asset(rel, path.read_text(encoding="utf-8")))
        self.assertEqual(violations, [], "\n".join(violations))
        # Guard against a silently-empty scan.
        self.assertTrue(scanned, "served-asset scan unexpectedly found no files")


class TestSinkDetectorSelfTest(unittest.TestCase):
    """An enforcement scan that cannot fail is worse than none."""

    def test_detector_catches_each_sink(self):
        samples = {
            "innerHTML": "el.innerHTML = receipt.reason;",
            "outerHTML": "el.outerHTML = row;",
            "insertAdjacentHTML": "el.insertAdjacentHTML('beforeend', html);",
            "document.write": "document.write(html);",
            "dangerouslySetInnerHTML": "h('div', {dangerouslySetInnerHTML: {__html: x}})",
            "srcdoc": "iframe.srcdoc = untrusted;",
        }
        for sink, sample in samples.items():
            with self.subTest(sink=sink):
                hits = _scan_asset("bad.js", sample)
                self.assertTrue(hits, f"detector missed {sink!r}")

    def test_detector_catches_writeln_via_document_write_prefix(self):
        self.assertTrue(_scan_asset("bad.js", "document.writeln(x);"))

    def test_detector_passes_safe_dom_building(self):
        safe = 'return h("span", null, String(r.payload.trigger.content));'
        self.assertEqual(_scan_asset("ok.js", safe), [])


if __name__ == "__main__":
    unittest.main()
