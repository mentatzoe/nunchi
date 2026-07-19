#!/usr/bin/env python3
"""Scan added Slice 020 diff lines for high-confidence secret signatures.

The command requires an explicit committed ``--base``/``--head`` range and scans
only Slice 020-owned implementation, test, evaluation, evidence, and scanner
paths. Managed specification paths remain outside executable dependencies. It
never prints matching source text or secret bytes.

Matcher set (deliberately high confidence):

1. PEM/OpenSSH private-key headers.
2. OpenAI-style ``sk-`` keys with at least 20 key characters.
3. GitHub ``gh[pousr]_`` tokens with at least 20 token characters.
4. Long quoted values assigned to explicit key/secret/token variable names.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import re
# Fixed git argv is required to inspect immutable Git objects; no shell is used.
import subprocess  # nosec B404
from typing import Sequence


SLICE020_PATHS = (
    "src/nunchi/observation.py",
    "tests/v2/observation",
    "evals/v2/observation",
    "evidence/v2/observation",
    "scripts/check_slice020_secrets.py",
)

MATCHERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private-key-header",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "openai-style-key",
        re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "github-token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    ),
    (
        "quoted-secret-assignment",
        re.compile(
            r"(?i)(?:api[_-]?key|client[_-]?secret|access[_-]?token|secret|token)"
            r"\s*[:=]\s*[\"'][A-Za-z0-9_./+\-=]{16,}[\"']"
        ),
    ),
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    matcher: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: [{self.matcher}] possible secret (content redacted)"


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def scan_added_lines(diff_text: str) -> list[Finding]:
    """Return redacted findings from added lines in one unified diff."""
    findings: list[Finding] = []
    path = "<unknown>"
    new_line = 0
    for raw_line in diff_text.splitlines():
        if raw_line.startswith("+++ "):
            candidate = raw_line[4:]
            path = candidate[2:] if candidate.startswith("b/") else candidate
            continue
        hunk = _HUNK.match(raw_line)
        if hunk:
            new_line = int(hunk.group(1))
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            added = raw_line[1:]
            for label, matcher in MATCHERS:
                if matcher.search(added):
                    findings.append(Finding(path=path, line=new_line, matcher=label))
                    break
            new_line += 1
            continue
        if not raw_line.startswith("-") and not raw_line.startswith("diff "):
            new_line += 1
    return findings


def _git(*args: str) -> str:
    # The executable and argv shape are fixed; base/head remain separate argv
    # elements and ``shell`` is never enabled, so ref text cannot become code.
    completed = subprocess.run(  # nosec B603 B607
        ["git", *args], check=True, text=True, capture_output=True,
    )
    return completed.stdout.strip()


def _commit(ref: str) -> str:
    return _git("rev-parse", "--verify", f"{ref}^{{commit}}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="base commit/ref (exclusive)")
    parser.add_argument("--head", required=True, help="head commit/ref (inclusive)")
    args = parser.parse_args(argv)

    base = _commit(args.base)
    head = _commit(args.head)
    diff = _git(
        "diff", "--no-ext-diff", "--unified=0", "--diff-filter=ACMR",
        base, head, "--", *SLICE020_PATHS,
    )
    changed_files_text = _git(
        "diff", "--name-only", "--diff-filter=ACMR", base, head, "--",
        *SLICE020_PATHS,
    )
    changed_files = [line for line in changed_files_text.splitlines() if line]
    added_lines = sum(
        1
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    findings = scan_added_lines(diff)
    status = "CLEAN" if not findings else "FINDINGS"
    print(
        f"SLICE020_SECRET_SCAN {status} base={base} head={head} "
        f"files={len(changed_files)} additions={added_lines} matchers={len(MATCHERS)}"
    )
    for finding in findings:
        print(finding.render())
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
