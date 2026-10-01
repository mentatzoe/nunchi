"""Plugin-owned native invocation ledger, not a replacement authority engine.

A claim is durable before handing control to Hermes. A returned value is not
proof of an effect: native approvals/guards may have declined the invocation.
Unknown and returned claims both remain reserved across process restarts.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import stat
from typing import Any, Iterator, Mapping

from ..receipts import PersistenceError


class NativeInvocationJournal:
    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
            self._check_file()
            with self._connect() as db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS invocations ("
                    "identity TEXT PRIMARY KEY, binding TEXT NOT NULL, "
                    "invocation TEXT NOT NULL, effect TEXT NOT NULL)"
                )
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except (OSError, sqlite3.Error) as exc:
            raise PersistenceError("native invocation ledger unavailable") from exc

    def _check_file(self) -> None:
        info = self.path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_mode & 0o077
            or info.st_uid != os.getuid()
        ):
            raise PersistenceError("native invocation ledger is not a private regular file")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self._check_file()
        db = sqlite3.connect(self.path, timeout=0)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def reserve(self, identity: str, binding: Mapping[str, Any]) -> bool:
        try:
            payload = json.dumps(dict(binding), sort_keys=True, separators=(",", ":"), allow_nan=False)
            with self._connect() as db:
                result = db.execute(
                    "INSERT OR IGNORE INTO invocations VALUES (?, ?, 'committed', 'unknown')",
                    (identity, payload),
                )
                return result.rowcount == 1
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            raise PersistenceError("could not reserve native invocation") from exc

    def finish(self, identity: str, invocation: str) -> None:
        if invocation not in {"returned", "raised", "cancelled-before-handoff"}:
            raise ValueError("unsupported native invocation outcome")
        try:
            with self._connect() as db:
                result = db.execute(
                    "UPDATE invocations SET invocation = ? WHERE identity = ?",
                    (invocation, identity),
                )
                if result.rowcount != 1:
                    raise PersistenceError("native invocation has no durable claim")
        except (OSError, sqlite3.Error) as exc:
            raise PersistenceError("could not record native invocation outcome") from exc

    def records(self) -> list[dict[str, Any]]:
        try:
            with self._connect() as db:
                return [
                    {"identity": identity, "binding": json.loads(binding),
                     "invocation": invocation, "effect": effect}
                    for identity, binding, invocation, effect in db.execute(
                        "SELECT identity, binding, invocation, effect FROM invocations ORDER BY rowid"
                    )
                ]
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise PersistenceError("could not read native invocation ledger") from exc
