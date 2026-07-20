"""Secure off-surface V2 receipt persistence adapters."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
from typing import Any

from .authorization import (
    AuthorizationRequestError,
    validate_authorization_decision,
)
from .core import ReceiptSinkPersistenceError
from .observation import validate_attention_receipt_record
from .policy import OperatorPolicy, ReceiptSinkPolicy


class ReceiptSinkConstructionError(ValueError):
    pass


class ExclusiveJSONFileReceiptSink:
    """No-follow, owner-only, exclusive-create receipt storage.

    One request ID and stage map to one SHA-256 filename. Existing files are
    never touched. Any failure after creation is ``unknown`` because durable side
    effects may have occurred; schema rejection or a pre-create failure that
    created nothing is ``not-persisted``.
    """

    def __init__(self, policy: ReceiptSinkPolicy) -> None:
        if not isinstance(policy, ReceiptSinkPolicy):
            raise ReceiptSinkConstructionError("receipt sink policy is invalid")
        flags = os.O_RDONLY
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_DIRECTORY", 0)
        try:
            descriptor = os.open(policy.directory, flags)
        except OSError as exc:
            raise ReceiptSinkConstructionError("receipt directory is unavailable") from exc
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISDIR(metadata.st_mode):
                raise ReceiptSinkConstructionError("receipt directory is unsafe")
            if metadata.st_uid != os.geteuid():
                raise ReceiptSinkConstructionError("receipt directory is unsafe")
            if stat.S_IMODE(metadata.st_mode) & 0o077:
                raise ReceiptSinkConstructionError("receipt directory is unsafe")
        except BaseException:
            os.close(descriptor)
            raise
        self._directory_fd = descriptor
        self._lock = threading.RLock()

    @staticmethod
    def _filename(request_id: str, stage: str) -> str:
        digest = hashlib.sha256(
            f"{request_id}\0{stage}".encode("utf-8")
        ).hexdigest()
        return f"{stage}-{digest}.jsonl"

    def __call__(self, record: dict[str, Any]) -> None:
        errors = validate_attention_receipt_record(record)
        if errors:
            raise ReceiptSinkPersistenceError("not-persisted")
        try:
            payload = (
                json.dumps(
                    record,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ReceiptSinkPersistenceError("not-persisted") from exc
        filename = self._filename(record["request_id"], record["stage"])
        self._write_payload(filename, payload)

    def _write_payload(self, filename: str, payload: bytes) -> None:
        with self._lock:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            flags |= getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            try:
                file_fd = os.open(
                    filename,
                    flags,
                    0o600,
                    dir_fd=self._directory_fd,
                )
            except FileExistsError as exc:
                raise ReceiptSinkPersistenceError("unknown") from exc
            except OSError as exc:
                raise ReceiptSinkPersistenceError("not-persisted") from exc
            failure: BaseException | None = None
            try:
                view = memoryview(payload)
                while view:
                    written = os.write(file_fd, view)
                    if written <= 0:
                        raise OSError("receipt write made no progress")
                    view = view[written:]
                os.fsync(file_fd)
            except BaseException as exc:
                failure = exc
            finally:
                try:
                    os.close(file_fd)
                except OSError as exc:
                    if failure is None:
                        failure = exc
                if failure is not None:
                    try:
                        os.unlink(filename, dir_fd=self._directory_fd)
                        os.fsync(self._directory_fd)
                    except OSError:
                        pass
            if failure is not None:
                if isinstance(failure, Exception):
                    raise ReceiptSinkPersistenceError("unknown") from failure
                raise failure
            try:
                os.fsync(self._directory_fd)
            except OSError as exc:
                raise ReceiptSinkPersistenceError("unknown") from exc

    def close(self) -> None:
        with self._lock:
            if self._directory_fd >= 0:
                descriptor = self._directory_fd
                self._directory_fd = -1
                os.close(descriptor)

    def __enter__(self) -> "ExclusiveJSONFileReceiptSink":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()


class ExclusiveJSONFileAuthorizationSink(ExclusiveJSONFileReceiptSink):
    """Persist one closed host authorization decision by unique decision ID."""

    @staticmethod
    def _authorization_filename(decision_id: str) -> str:
        digest = hashlib.sha256(decision_id.encode("utf-8")).hexdigest()
        return f"authorization-{digest}.jsonl"

    def __call__(self, record: dict[str, Any]) -> None:
        try:
            accepted = validate_authorization_decision(record)
            payload = (
                json.dumps(
                    accepted,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        except (AuthorizationRequestError, TypeError, ValueError) as exc:
            raise ReceiptSinkPersistenceError("not-persisted") from exc
        self._write_payload(
            self._authorization_filename(accepted["decision_id"]),
            payload,
        )


class ReloadingPolicyReceiptSink:
    """Route each offer through the currently trusted receipt-sink policy."""

    def __init__(self, policy_loader) -> None:
        if not callable(policy_loader):
            raise ReceiptSinkConstructionError("policy loader is invalid")
        self._policy_loader = policy_loader
        self._lock = threading.RLock()
        self._binding: tuple[str, str, str] | None = None
        self._sink: ExclusiveJSONFileReceiptSink | None = None

    def __call__(self, record: dict[str, Any]) -> None:
        with self._lock:
            policy = self._policy_loader()
            if not isinstance(policy, OperatorPolicy):
                raise ReceiptSinkConstructionError("policy loader returned an invalid policy")
            sink_policy = policy.receipt_sink
            binding = (sink_policy.type, sink_policy.directory, sink_policy.source)
            if binding != self._binding:
                replacement = ExclusiveJSONFileReceiptSink(sink_policy)
                previous = self._sink
                self._sink = replacement
                self._binding = binding
                if previous is not None:
                    previous.close()
            assert self._sink is not None
            self._sink(record)

    def close(self) -> None:
        with self._lock:
            if self._sink is not None:
                self._sink.close()
                self._sink = None
                self._binding = None


class ReloadingPolicyAuthorizationSink:
    """Route authorization audits through the current owner-only sink policy."""

    def __init__(self, policy_loader) -> None:
        if not callable(policy_loader):
            raise ReceiptSinkConstructionError("policy loader is invalid")
        self._policy_loader = policy_loader
        self._lock = threading.RLock()
        self._binding: tuple[str, str, str] | None = None
        self._sink: ExclusiveJSONFileAuthorizationSink | None = None

    def __call__(self, record: dict[str, Any]) -> None:
        with self._lock:
            policy = self._policy_loader()
            if not isinstance(policy, OperatorPolicy):
                raise ReceiptSinkConstructionError("policy loader returned an invalid policy")
            sink_policy = policy.receipt_sink
            binding = (sink_policy.type, sink_policy.directory, sink_policy.source)
            if binding != self._binding:
                replacement = ExclusiveJSONFileAuthorizationSink(sink_policy)
                previous = self._sink
                self._sink = replacement
                self._binding = binding
                if previous is not None:
                    previous.close()
            assert self._sink is not None
            self._sink(record)

    def close(self) -> None:
        with self._lock:
            if self._sink is not None:
                self._sink.close()
                self._sink = None
                self._binding = None


__all__ = [
    "ExclusiveJSONFileAuthorizationSink",
    "ExclusiveJSONFileReceiptSink",
    "ReceiptSinkConstructionError",
    "ReloadingPolicyAuthorizationSink",
    "ReloadingPolicyReceiptSink",
]
