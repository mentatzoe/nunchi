"""Keep a Nunchi process's memory and starting environment private.

An agent that runs code as the same OS user as Nunchi can read another
process of that user through ``/proc``: ``/proc/<pid>/environ`` holds the
environment the process started with, keys included, and ``/proc/<pid>/mem``
its memory. A participant's keys then let the agent post to the room without
the library. `keep_private` stops those reads of Nunchi's own processes from
the moment it is called. It does not stop them during start-up (below).

On Linux it marks the process not dumpable (``prctl(PR_SET_DUMPABLE, 0)``)
and checks that this took. Another process of the same user then gets
``PermissionError`` on both files; only a process with ``CAP_SYS_PTRACE``
(root, usually) still reads them. A process that is not dumpable writes no
core file either.

Call it first in an entry point that holds a secret: before it reads any
secret, and before any agent process starts. It returns one status:

- ``"private"``: done and checked.
- ``"unsupported"``: not Linux. On macOS another process of the same user
  can still read the starting environment (``ps eww``).
- ``"failed"``: the system refused; the reason is logged as a warning. The
  process carries on, as unprotected as before the call. Refusing to run
  would turn a hardening step into an outage on an unusual kernel; the
  process's probe reports the status instead.

``"private"`` means reads are stopped from now on. It does not mean the keys
are safe. What it does not cover:

- Start-up. Keys in the starting environment are readable by any process of
  the same user from the program's start until the call: Python's start-up
  and Nunchi's imports, about a tenth of a second, at every start. An agent
  with an unsandboxed shell can leave a reader running and force a start: it
  can kill a supervised runner (a signal needs only the same user), and the
  supervisor starts it again. Only a separation the agent cannot cross
  closes this: a harness sandbox that runs the agent's commands in their own
  process namespace or with a fresh ``/proc`` (each integration's README
  names its harness's setting), or running the agent as its own OS user.
- Anything else the same OS user can read: the shell that exported the keys,
  environment files, a service manager's view of a unit's environment (for
  systemd, ``systemctl show`` of ``Environment=``), and any process started
  without this call.
- Programs this process starts. The setting is reset when a child runs a new
  program, so a harness Nunchi starts is not private. It holds only its
  launch secret, which the guard withholds.
- Root, or any process with ``CAP_SYS_PTRACE``.

Never call it in a process that is not Nunchi's own: a harness that loads
Nunchi as a plugin keeps its own process settings.
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("nunchi.private_process")

PRIVATE = "private"
UNSUPPORTED = "unsupported"
FAILED = "failed"

# From <linux/prctl.h>.
PR_GET_DUMPABLE = 3
PR_SET_DUMPABLE = 4


def keep_private() -> str:
    """Stop this user's other processes reading this process's memory and starting environment from now on.

    Returns ``"private"``, ``"unsupported"`` (not Linux) or ``"failed"``
    (the reason is logged); never raises.
    """

    if not _linux():
        return UNSUPPORTED
    try:
        _not_dumpable()
    except (OSError, AttributeError, ImportError, ValueError) as exc:
        logger.warning(
            "nunchi: this process could not be made private (%s); other processes of "
            "this OS user can read its starting environment and memory",
            exc,
        )
        return FAILED
    return PRIVATE


def probe_facts(status: str) -> dict[str, object]:
    """What a probe reports about `keep_private`'s status."""

    return {"process_private": status == PRIVATE, "process_private_status": status}


def _linux() -> bool:
    return sys.platform.startswith("linux")


def _not_dumpable() -> None:
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    prctl.restype = ctypes.c_int
    if prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, f"prctl(PR_SET_DUMPABLE, 0) failed: {os.strerror(error)}")
    state = prctl(PR_GET_DUMPABLE, 0, 0, 0, 0)
    if state != 0:
        raise OSError(f"prctl(PR_GET_DUMPABLE) reads {state} after PR_SET_DUMPABLE 0")
