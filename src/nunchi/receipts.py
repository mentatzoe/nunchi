"""Immutable, singly-owned V2 receipt persistence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from copy import deepcopy
import json
import os
from pathlib import Path
import threading
from typing import Any

from .errors import NunchiError, ValidationError
from .v2_contracts import RECEIPT_STAGES, validate_receipt, validate_receipt_stream


class PersistenceError(NunchiError):
    """Raised when an audit fact cannot be durably recorded."""

    label = "persistence error"


class ReceiptJournal:
    """Append-only receipt journal.

    When a path is supplied every append is flushed and fsynced before the
    caller may proceed.  A failed or uncertain write raises, so downstream
    code cannot claim a stage that was not durably recorded.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        writer: Callable[[int, bytes], int] = os.write,
        sync: Callable[[int], None] = os.fsync,
    ) -> None:
        self._path = Path(path) if path is not None else None
        self._writer = writer
        self._sync = sync
        self._records: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._lock = threading.RLock()
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if self._path.exists():
                self._load()

    def _load(self) -> None:
        assert self._path is not None
        by_request: dict[str, list[dict[str, Any]]] = defaultdict(list)
        try:
            with self._path.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    checked = validate_receipt(record)
                    by_request[checked["request_id"]].append(checked)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise PersistenceError(
                f"receipt journal {self._path} is unreadable at startup: {exc}"
            ) from exc
        for request_id, records in by_request.items():
            try:
                validate_receipt_stream(records)
            except ValidationError as exc:
                raise PersistenceError(
                    f"receipt journal {self._path} has an invalid stream "
                    f"for {request_id}: {exc}"
                ) from exc
        self._records = by_request

    def append(self, record: Mapping[str, Any], *, writer: str) -> dict[str, Any]:
        checked = validate_receipt(record)
        if checked["writer"] != writer:
            raise ValidationError(
                f"receipt writer {writer!r} cannot append stage {checked['stage']!r}"
            )
        request_id = checked["request_id"]
        with self._lock:
            proposed = [*self._records[request_id], checked]
            validate_receipt_stream(proposed)
            if self._path is not None:
                payload = (
                    json.dumps(checked, sort_keys=True, separators=(",", ":"))
                    + "\n"
                ).encode("utf-8")
                flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
                fd = os.open(self._path, flags, 0o600)
                try:
                    written = self._writer(fd, payload)
                    if written != len(payload):
                        raise OSError(f"short write ({written}/{len(payload)} bytes)")
                    self._sync(fd)
                except OSError as exc:
                    raise PersistenceError(
                        f"could not durably append {checked['stage']} receipt: {exc}"
                    ) from exc
                finally:
                    os.close(fd)
            self._records[request_id].append(deepcopy(checked))
        return deepcopy(checked)

    def records(self, request_id: str) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(deepcopy(self._records.get(request_id, ())))

    def all_records(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(
                deepcopy(record)
                for records in self._records.values()
                for record in records
            )

    def next_stage(self, request_id: str) -> str | None:
        with self._lock:
            count = len(self._records.get(request_id, ()))
        if count >= len(RECEIPT_STAGES):
            return None
        return RECEIPT_STAGES[count]
