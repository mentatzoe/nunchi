"""Profile-scoped child supervisor used by shared service controls."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

from .errors import ValidationError
from .operator import OperatorStore, ServiceManager, _atomic_write

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


class DuplicateSupervisor(RuntimeError):
    pass


class ServiceSupervisor:
    def __init__(self, store: OperatorStore, service_name: str) -> None:
        self.store = store
        self.manager = ServiceManager(store)
        self.definition, self.config_revision = self.manager._definition(service_name)
        self.name = service_name
        self.directory = self.manager._directory(service_name)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.stop_requested = False
        self.child: subprocess.Popen[bytes] | None = None
        self.restart_count = 0
        self._lock_fd: int | None = None

    def _acquire(self) -> None:
        path = self.directory / "supervisor.lock"
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        if fcntl is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                os.close(fd)
                raise DuplicateSupervisor(f"service {self.name!r} already has a supervisor") from exc
        self._lock_fd = fd

    def _release(self) -> None:
        if self._lock_fd is None:
            return
        if fcntl is not None:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        os.close(self._lock_fd)
        self._lock_fd = None

    def _environment(self) -> dict[str, str]:
        environment = {
            name: os.environ[name]
            for name in ("HOME", "LANG", "LC_ALL", "PATH", "TMPDIR", "USER", "LOGNAME")
            if name in os.environ
        }
        for destination, source in self.definition["environment"].items():
            value = os.environ.get(source)
            if value is None:
                raise ValidationError(
                    f"service {self.name!r} credential or environment source {source} is absent"
                )
            environment[destination] = value
        environment["NUNCHI_PROFILE"] = self.store.paths.profile_id
        return environment

    def _status(self, state: str, **extra: Any) -> None:
        _atomic_write(
            self.directory / "status.json",
            (
                json.dumps(
                    {
                        "schema_version": 1,
                        "state": state,
                        "supervisor_pid": os.getpid(),
                        "restart_count": self.restart_count,
                        "config_revision": self.config_revision,
                        **extra,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8"),
        )

    def request_stop(self, *_: Any) -> None:
        self.stop_requested = True
        child = self.child
        if child is not None and child.poll() is None:
            child.terminate()

    def _pidfile(self) -> None:
        _atomic_write(
            self.manager._pidfile(self.name),
            (
                json.dumps(
                    {
                        "schema_version": 1,
                        "pid": os.getpid(),
                        "profile_id": self.store.paths.profile_id,
                        "service": self.name,
                        "config_revision": self.config_revision,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8"),
        )

    def run(self, *, max_restarts: int | None = None) -> int:
        self._acquire()
        previous_term = signal.signal(signal.SIGTERM, self.request_stop)
        previous_int = signal.signal(signal.SIGINT, self.request_stop)
        try:
            self._pidfile()
            while not self.stop_requested:
                self._status("starting")
                started = time.monotonic()
                self.child = subprocess.Popen(
                    self.definition["command"],
                    cwd=self.directory,
                    env=self._environment(),
                    stdin=subprocess.DEVNULL,
                    stdout=None,
                    stderr=None,
                    close_fds=True,
                )
                self._status("running", child_pid=self.child.pid)
                returncode = self.child.wait()
                self.child = None
                if self.stop_requested:
                    self._status("stopped", last_exit=returncode)
                    return 0
                policy = self.definition["restart"]
                should_restart = policy == "always" or (
                    policy == "on-failure" and returncode != 0
                )
                if not should_restart:
                    self._status("exited", last_exit=returncode)
                    return returncode
                self.restart_count += 1
                self._status("recovering", last_exit=returncode)
                if max_restarts is not None and self.restart_count > max_restarts:
                    self._status("restart-limit", last_exit=returncode)
                    return returncode or 1
                lifetime = time.monotonic() - started
                if lifetime < 1:
                    time.sleep(min(0.1 * self.restart_count, 1.0))
            return 0
        finally:
            signal.signal(signal.SIGTERM, previous_term)
            signal.signal(signal.SIGINT, previous_int)
            state = self.manager._read_pidfile(self.name)
            if isinstance(state, dict) and state.get("pid") == os.getpid():
                self.manager._pidfile(self.name).unlink(missing_ok=True)
            self._release()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nunchi-service-worker")
    parser.add_argument("--config-root", required=True, type=Path)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--service", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return ServiceSupervisor(
            OperatorStore(args.config_root, args.state_root, args.profile),
            args.service,
        ).run()
    except (DuplicateSupervisor, ValidationError, OSError) as exc:
        print(f"nunchi-service-worker: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
