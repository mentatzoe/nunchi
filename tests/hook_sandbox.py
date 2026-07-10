"""Sandboxed subprocess environment for hook-script tests.

The Claude Code hook script (``nunchi_prompt_gate.py``) resolves its
receipt log from
``NUNCHI_HOOK_LOG`` with a home-anchored default
(``~/.claude/nunchi-gate-receipts.jsonl``). Tests that ran those scripts
with the bare parent environment polluted the OPERATOR'S LIVE receipt log
with hundreds of test artifacts.

This module is the single designated place where a test subprocess
environment may be derived from ``os.environ``: :func:`sandbox_env` copies
the parent environment, then pins ``HOME`` and ``NUNCHI_HOOK_LOG`` into a
fresh temp directory so that even a forgotten override can only ever write
inside the sandbox.

Enforced by ``tests/test_no_home_writes.py``: hook-running test modules must
build their subprocess env through this helper, never from bare
``os.environ``.
"""

from __future__ import annotations

import os
import tempfile


def sandbox_env(env_overrides: dict | None = None) -> dict:
    """Return a subprocess env dict with HOME and NUNCHI_HOOK_LOG sandboxed.

    - ``HOME`` points at a fresh temp directory, so any home-anchored
      default path (``Path.home()`` / ``~`` expansion) resolves inside it.
    - ``NUNCHI_HOOK_LOG`` defaults to a receipts file inside that sandbox.
    - *env_overrides* are applied last, so explicit test choices (a specific
      temp log path, ``/dev/null``, a stub binary) always win.
    """
    home = tempfile.mkdtemp(prefix="nunchi-test-home-")
    env = dict(os.environ)
    env["HOME"] = home
    env["NUNCHI_HOOK_LOG"] = os.path.join(home, "receipts.jsonl")
    if env_overrides:
        env.update(env_overrides)
    return env
