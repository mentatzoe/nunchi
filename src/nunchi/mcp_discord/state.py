"""Durable, bounded transport state for the standing Discord MCP process."""

from __future__ import annotations

import hashlib
import os
import stat
import threading


class TransportStateError(RuntimeError):
    pass


class ExclusiveRequestClaimStore:
    """Permanently reserve mutation request IDs before native effects.

    Claims are owner-only exclusive-create files.  They survive process
    restart, never evict, and fail closed once the configured capacity is
    exhausted.
    """

    def __init__(self, directory: str, *, max_claims: int = 4096) -> None:
        if (
            not isinstance(directory, str)
            or not directory
            or isinstance(max_claims, bool)
            or not isinstance(max_claims, int)
            or not 1 <= max_claims <= 100000
        ):
            raise TransportStateError("Discord transport state configuration is invalid")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_DIRECTORY", 0)
        try:
            descriptor = os.open(directory, flags)
        except OSError as exc:
            raise TransportStateError("Discord transport state directory is unavailable") from exc
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) & 0o077
            ):
                raise TransportStateError("Discord transport state directory is unsafe")
            count = sum(
                1
                for name in os.listdir(descriptor)
                if name.startswith("mcp-action-") and name.endswith(".claim")
            )
        except BaseException:
            os.close(descriptor)
            raise
        self._descriptor = descriptor
        self._max_claims = max_claims
        self._count = count
        self._lock = threading.RLock()

    def claim(self, request_id: str) -> None:
        if not isinstance(request_id, str) or not request_id or len(request_id) > 512:
            raise TransportStateError("Discord action request ID is invalid")
        digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        filename = f"mcp-action-{digest}.claim"
        with self._lock:
            if self._count >= self._max_claims:
                raise TransportStateError("Discord action replay registry is exhausted")
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            try:
                file_descriptor = os.open(
                    filename,
                    flags,
                    0o600,
                    dir_fd=self._descriptor,
                )
            except FileExistsError as exc:
                raise TransportStateError("Discord action request was already consumed") from exc
            except OSError as exc:
                raise TransportStateError("Discord action request could not be reserved") from exc
            failure: OSError | None = None
            try:
                payload = (request_id + "\n").encode("utf-8")
                view = memoryview(payload)
                while view:
                    written = os.write(file_descriptor, view)
                    if written <= 0:
                        raise OSError("claim write made no progress")
                    view = view[written:]
                os.fsync(file_descriptor)
            except OSError as exc:
                failure = exc
            finally:
                try:
                    os.close(file_descriptor)
                except OSError as exc:
                    if failure is None:
                        failure = exc
            if failure is not None:
                try:
                    os.unlink(filename, dir_fd=self._descriptor)
                except OSError:
                    pass
                raise TransportStateError("Discord action reservation outcome is unknown") from failure
            try:
                os.fsync(self._descriptor)
            except OSError as exc:
                raise TransportStateError("Discord action reservation outcome is unknown") from exc
            self._count += 1

    def close(self) -> None:
        with self._lock:
            if self._descriptor >= 0:
                descriptor = self._descriptor
                self._descriptor = -1
                os.close(descriptor)


__all__ = ["ExclusiveRequestClaimStore", "TransportStateError"]
