"""Keep a Nunchi process's memory and starting environment private.

An agent that runs code as the same OS user as Nunchi can read another
process of that user through ``/proc``: ``/proc/<pid>/environ`` holds the
environment the process started with, keys included, and ``/proc/<pid>/mem``
its memory. A participant's keys then let the agent post to the room without
the library. `keep_private` closes both for Nunchi's own processes.

On Linux it marks the process not dumpable (``prctl(PR_SET_DUMPABLE, 0)``)
and checks that this took. Another process of the same user then gets
``PermissionError`` on both files; only a process with ``CAP_SYS_PTRACE``
(root, usually) still reads them. It also sets the process's core size limit
to zero, so a crash writes no core file that holds the keys.

Call it first in an entry point that holds a secret: before any secret is
read, and before any agent process starts. It returns one status:

- ``"private"``: done and checked.
- ``"unsupported"``: not Linux. On macOS another process of the same user
  can still read the starting environment (``ps eww``).
- ``"failed"``: the system refused; the reason is logged as a warning. The
  process carries on, as unprotected as before the call. Refusing to run
  would turn a hardening step into an outage on an unusual kernel; the
  process's probe reports the status instead.

What it does not cover:

- Anything else the same OS user can read: the shell that exported the keys,
  environment files, a service manager's view of a unit's environment (for
  systemd, ``systemctl show`` of ``Environment=``), and any process started
  without this call.
- Programs this process starts. The setting is reset when a child runs a new
  program, so a harness Nunchi starts is not private (it gets no Nunchi key);
  the zero core size limit is inherited.
- The few milliseconds between the program's start and the call.
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
    """Make this process's memory and starting environment unreadable to its user's other processes.

    Returns ``"private"``, ``"unsupported"`` (not Linux) or ``"failed"``
    (the reason is logged); never raises.
    """

    if not _linux():
        return UNSUPPORTED
    try:
        _not_dumpable()
        _no_core_files()
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


def _no_core_files() -> None:
    import resource

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
