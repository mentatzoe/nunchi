"""Nunchi's own processes keep their memory and starting environment private.

An agent that runs as the same OS user as a Nunchi process must not read the
process's keys out of ``/proc/<pid>/environ`` or ``/proc/<pid>/mem``
(`nunchi.private_process`). The first group runs the real mechanism: a
process with a key in its starting environment and in its memory starts a
child that tries to read both, with and without `keep_private`. Root (or any
process with ``CAP_SYS_PTRACE``) reads them regardless, so as root both run
with every capability dropped; without ``setpriv`` that cannot be done, and
the group skips.

The second group checks that every Nunchi entry point that holds a secret
calls `keep_private` first, before its config or any secret is read, and
that no Hermes integration calls it: those run inside Hermes's own process.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

import nunchi.private_process as private_process
from nunchi.errors import ValidationError

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(private_process.__file__).resolve().parents[1]
KEY_NAME = "NUNCHI_TEST_PRIVATE_KEY"
# CAP_SYS_PTRACE, from <linux/capability.h>.
_CAP_SYS_PTRACE = 19

# The "runtime": it holds the key in its starting environment and in its
# memory, optionally calls keep_private, then starts the "agent" without the
# key in its environment and reports what the agent could read.
_RUNTIME = r"""
import ctypes, json, os, resource, subprocess, sys
sys.path.insert(0, sys.argv[1])
mode, key_name = sys.argv[2], sys.argv[3]
key = os.environ[key_name]
held = ctypes.create_string_buffer(key.encode())
libc = ctypes.CDLL(None, use_errno=True)
# Under Yama's scope 1, only an ancestor may read a process's memory. Let any
# process try (PR_SET_PTRACER, PR_SET_PTRACER_ANY), so that what blocks the
# agent below is keep_private alone. Without Yama this call fails, harmlessly.
libc.prctl(ctypes.c_int(0x59616D61), ctypes.c_ulong((1 << 64) - 1), ctypes.c_ulong(0),
           ctypes.c_ulong(0), ctypes.c_ulong(0))
status = None
core_limit = resource.getrlimit(resource.RLIMIT_CORE)
if mode == "private":
    from nunchi.private_process import keep_private
    status = keep_private()
agent_env = {name: value for name, value in os.environ.items() if name != key_name}
agent = subprocess.run(
    [sys.executable, "-I", "-c", sys.argv[4], str(os.getpid()), str(ctypes.addressof(held)), key_name, key],
    env=agent_env, capture_output=True, text=True, timeout=60,
)
print(json.dumps({
    "status": status,
    "core_limit_kept": resource.getrlimit(resource.RLIMIT_CORE) == core_limit,
    "agent": agent.stdout.strip(),
    "agent_error": agent.stderr[-500:],
}))
"""

# The "agent": a child of the runtime that reads its parent through /proc.
_AGENT = r"""
import json, os, sys
pid, address, key_name, key = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
out = {"own_environment_has_key": key_name in os.environ}
try:
    with open(f"/proc/{pid}/environ", "rb") as handle:
        out["environ"] = "read" if f"{key_name}={key}".encode() in handle.read() else "read-without-key"
except OSError as exc:
    out["environ"] = type(exc).__name__
try:
    with open(f"/proc/{pid}/mem", "rb", buffering=0) as handle:
        handle.seek(address)
        out["mem"] = "read" if handle.read(len(key)) == key.encode() else "read-without-key"
except OSError as exc:
    out["mem"] = type(exc).__name__
print(json.dumps(out))
"""


def _has_ptrace_capability() -> bool:
    try:
        status = Path("/proc/self/status").read_text(encoding="utf-8")
    except OSError:
        return os.geteuid() == 0
    for line in status.splitlines():
        if line.startswith("CapEff:"):
            return bool(int(line.split()[1], 16) >> _CAP_SYS_PTRACE & 1)
    return os.geteuid() == 0


def _yama_scope() -> int:
    try:
        return int(Path("/proc/sys/kernel/yama/ptrace_scope").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0


def _unprivileged_prefix() -> list[str] | None:
    """How to run a process with no capabilities: nothing, setpriv, or None when impossible."""

    if not _has_ptrace_capability():
        return []
    setpriv = shutil.which("setpriv")
    if setpriv is None:
        return None
    # The same OS user, every capability dropped: a same-user agent, as the
    # kernel sees it, with the files this checkout's owner can read.
    return [setpriv, "--inh-caps=-all", "--bounding-set=-all"]


def _run(mode: str) -> dict:
    prefix = _unprivileged_prefix()
    assert prefix is not None
    key = "nunchi-test-" + secrets.token_hex(24)
    environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), KEY_NAME: key}
    completed = subprocess.run(
        [*prefix, sys.executable, "-I", "-B", "-c", _RUNTIME, str(SOURCE), mode, KEY_NAME, _AGENT],
        env=environment,
        cwd="/",
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        raise AssertionError(f"the runtime failed: {completed.stderr[-1000:]}")
    result = json.loads(completed.stdout)
    if not result["agent"]:
        raise AssertionError(f"the agent failed: {result['agent_error']}")
    result["agent"] = json.loads(result["agent"])
    return result


@unittest.skipUnless(sys.platform.startswith("linux"), "keep_private acts on Linux only")
class ProcReadTests(unittest.TestCase):
    """A child reading its parent through /proc, as an agent reads its runtime."""

    def setUp(self) -> None:
        if _unprivileged_prefix() is None:
            self.skipTest(
                "this process has CAP_SYS_PTRACE (root), which reads any process, and setpriv "
                "is not installed to drop it"
            )
        if _yama_scope() >= 2:
            self.skipTest(
                f"Yama ptrace_scope {_yama_scope()} already keeps same-user processes out of "
                "each other's memory"
            )

    def test_without_the_call_the_agent_reads_the_runtimes_key(self):
        result = _run("plain")
        self.assertFalse(result["agent"]["own_environment_has_key"])
        self.assertEqual("read", result["agent"]["environ"])
        self.assertEqual("read", result["agent"]["mem"])

    def test_after_the_call_the_agent_cannot_read_the_runtime(self):
        result = _run("private")
        self.assertEqual("private", result["status"])
        self.assertFalse(result["agent"]["own_environment_has_key"])
        self.assertEqual("PermissionError", result["agent"]["environ"])
        self.assertEqual("PermissionError", result["agent"]["mem"])
        # A process that is not dumpable writes no core file; the core size
        # limit, which the harness and its commands inherit, is left alone.
        self.assertTrue(result["core_limit_kept"])


class StatusTests(unittest.TestCase):
    def test_off_linux_it_is_unsupported(self):
        with mock.patch.object(private_process, "_linux", return_value=False), mock.patch.object(
            private_process, "_not_dumpable"
        ) as not_dumpable:
            self.assertEqual("unsupported", private_process.keep_private())
        not_dumpable.assert_not_called()

    def test_a_refusal_is_a_status_and_a_warning_not_a_crash(self):
        with mock.patch.object(private_process, "_linux", return_value=True), mock.patch.object(
            private_process, "_not_dumpable", side_effect=OSError(1, "Operation not permitted")
        ):
            with self.assertLogs("nunchi.private_process", "WARNING") as logs:
                self.assertEqual("failed", private_process.keep_private())
        self.assertIn("could not be made private", logs.output[0])

    def test_probe_facts(self):
        self.assertEqual(
            {"process_private": True, "process_private_status": "private"},
            private_process.probe_facts("private"),
        )
        self.assertFalse(private_process.probe_facts("failed")["process_private"])


class _Order:
    """Records keep_private and the first config or secret read, in order."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def private(self) -> str:
        self.calls.append("private")
        return "private"

    def config(self, *_args, **_kwargs):
        self.calls.append("config")
        raise ValidationError("stop before anything runs")


class EntryPointTests(unittest.TestCase):
    """Every entry point that holds a secret is private before it reads one."""

    PINNED = ["--config", "/srv/nunchi/config.json", "--config-sha256", "0" * 64]

    def _pinned(self, module) -> None:
        order = _Order()
        with mock.patch.object(module, "keep_private", side_effect=order.private), mock.patch.object(
            module, "load_pinned_config", side_effect=order.config
        ), contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(3, module.main(self.PINNED))
        self.assertEqual(["private", "config"], order.calls)

    def test_claude_code_runner(self):
        from nunchi.integrations import claude_code_v2

        self._pinned(claude_code_v2)

    def test_codex_app_server_runner(self):
        from nunchi.integrations.codex_app_server import runner

        self._pinned(runner)

    def test_codex_room_runner(self):
        from nunchi.integrations import codex_v2

        self._pinned(codex_v2)

    def test_reference_adapters(self):
        from nunchi.adapters import channel, discord, matrix, telegram

        for module in (channel, discord, matrix, telegram):
            with self.subTest(adapter=module.__name__):
                self._pinned(module)

    def test_discord_transport_server(self):
        from nunchi.mcp_discord import server

        order = _Order()

        def load(_environ):
            order.calls.append("config")
            raise RuntimeError("stop before anything runs")

        sdk = sys.modules.get("mcp") or types.ModuleType("mcp")
        with mock.patch.object(server, "keep_private", side_effect=order.private), mock.patch.object(
            server, "load_config", side_effect=load
        ), mock.patch.dict(sys.modules, {"mcp": sdk}), mock.patch.object(
            server.logging, "basicConfig"
        ), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(1, server.main([]))
        self.assertEqual(["private", "config"], order.calls)

    def test_service_worker(self):
        from nunchi import service_worker

        order = _Order()
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            service_worker, "keep_private", side_effect=order.private
        ), mock.patch.object(
            service_worker, "_load_environment_file", side_effect=order.config
        ), contextlib.redirect_stderr(io.StringIO()):
            code = service_worker.main(
                [
                    "--config-root", directory,
                    "--state-root", directory,
                    "--profile", "default",
                    "--service", "transport",
                    "--environment-file", str(Path(directory) / "environment.json"),
                ]
            )
        self.assertEqual(4, code)
        self.assertEqual(["private", "config"], order.calls)

    def test_no_hermes_integration_changes_hermes_s_process(self):
        integrations = ROOT / "src" / "nunchi" / "integrations"
        paths = [*integrations.glob("hermes*.py"), *(integrations / "hermes_plugin").glob("*.py")]
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(module=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("keep_private", text)
                self.assertNotIn("PR_SET_DUMPABLE", text)


if __name__ == "__main__":
    unittest.main()
