"""Shared trusted-host construction for native V2 room adapters."""

from __future__ import annotations

import argparse
import json
import os
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..integrations.subprocess_participant_v2 import SubprocessParticipantV2
from ..observation import ObservationProvider
from ..policy import OperatorPolicySource
from ..receipts import ReloadingPolicyReceiptSink
from ..runtime import LiveRoomRuntime


class NativeHostV2Error(RuntimeError):
    pass


def add_participant_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--participant-id", required=True)
    parser.add_argument("--participant-name", required=True)
    parser.add_argument("--participant-workspace", type=Path)
    parser.add_argument("--participant-timeout", type=float, default=120)
    parser.add_argument("--participant-env", action="append", default=[])
    parser.add_argument("--silent-participant", action="store_true")
    parser.add_argument("--participant-command", nargs=argparse.REMAINDER)


@dataclass(frozen=True)
class NativeRuntimeV2:
    runtime: LiveRoomRuntime
    receipt_sink: ReloadingPolicyReceiptSink

    def close(self) -> None:
        self.receipt_sink.close()


def build_native_runtime(
    arguments: argparse.Namespace,
    *,
    participant_actor_id: str,
    platform: str,
    room_id: str,
    continuity_scope_id: str,
    continuity: str,
    has_restart_gap: bool | None,
    event_visibility: dict[str, str],
    action_sink_factory: Callable[[ReloadingPolicyReceiptSink], Callable],
) -> NativeRuntimeV2:
    source = OperatorPolicySource(arguments.policy)
    policy = source.load()
    if (
        policy.attention.participant_id != arguments.participant_id
        or policy.recoverability.participant_id != arguments.participant_id
        or policy.recoverability.continuity_scope_id != continuity_scope_id
    ):
        raise NativeHostV2Error("native adapter policy binding is invalid")
    if policy.recoverability.eligible and (
        continuity != "restart-safe" or has_restart_gap is not False
    ):
        raise NativeHostV2Error(
            "suppression recoverability contradicts native host capabilities"
        )
    if arguments.silent_participant:
        if arguments.participant_command:
            raise NativeHostV2Error("participant mode is ambiguous")
        participant = lambda _turn: None
    else:
        if not arguments.participant_command:
            raise NativeHostV2Error("participant command is required")
        if arguments.participant_workspace is None:
            raise NativeHostV2Error("participant workspace is required")
        participant = SubprocessParticipantV2(
            command=arguments.participant_command,
            workspace=arguments.participant_workspace,
            timeout_seconds=arguments.participant_timeout,
            pass_env=tuple(arguments.participant_env),
        )
    receipt_sink = ReloadingPolicyReceiptSink(source.load)
    try:
        action_sink = action_sink_factory(receipt_sink)
        observation = ObservationProvider(
            participant_id=arguments.participant_id,
            actor_id=participant_actor_id,
            names=[arguments.participant_name],
            role="participant",
            platform=platform,
            room_id=room_id,
            room_kind="group",
            continuity_scope_id=continuity_scope_id,
            continuity=continuity,
            has_restart_gap=has_restart_gap,
            event_visibility=event_visibility,
        )
        runtime = LiveRoomRuntime(
            observation=observation,
            policy_loader=source.load,
            receipt_sink=receipt_sink,
            participant=participant,
            correlated_action_sink=action_sink,
        )
    except Exception:
        receipt_sink.close()
        raise
    return NativeRuntimeV2(runtime, receipt_sink)


def _strict_json(raw: bytes) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    return json.loads(
        raw,
        object_pairs_hook=pairs,
        parse_constant=lambda _value: (_ for _ in ()).throw(
            ValueError("non-finite")
        ),
    )


class DurableCursorStoreV2:
    """Owner-only, no-follow, atomically replaced transport checkpoint."""

    def __init__(
        self,
        path: Path,
        *,
        platform: str,
        room_id: str,
        cursor_type: type[str] | type[int],
    ) -> None:
        resolved = Path(path)
        if not resolved.is_absolute() or cursor_type not in (str, int):
            raise NativeHostV2Error("native cursor configuration is invalid")
        self.path = resolved
        self.name = resolved.name
        self.platform = platform
        self.room_id = room_id
        self.cursor_type = cursor_type
        flags = os.O_RDONLY
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_DIRECTORY", 0)
        try:
            self._directory_fd = os.open(resolved.parent, flags)
            metadata = os.fstat(self._directory_fd)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) & 0o077
            ):
                raise NativeHostV2Error("native cursor directory is unsafe")
            self._check_existing()
        except Exception:
            descriptor = getattr(self, "_directory_fd", -1)
            if descriptor >= 0:
                os.close(descriptor)
            raise NativeHostV2Error("native cursor storage is unavailable") from None

    def _check_existing(self) -> None:
        try:
            metadata = os.stat(
                self.name,
                dir_fd=self._directory_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise NativeHostV2Error("native cursor file is unsafe")

    def _validate_cursor(self, value: Any) -> str | int:
        if self.cursor_type is str:
            if not isinstance(value, str) or not value or len(value) > 4096:
                raise NativeHostV2Error("native cursor is invalid")
        elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise NativeHostV2Error("native cursor is invalid")
        return value

    def load(self) -> str | int | None:
        self._check_existing()
        flags = os.O_RDONLY
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.name, flags, dir_fd=self._directory_fd)
        except FileNotFoundError:
            return None
        try:
            payload = os.read(descriptor, 65537)
            if len(payload) > 65536 or os.read(descriptor, 1):
                raise NativeHostV2Error("native cursor file is invalid")
        finally:
            os.close(descriptor)
        try:
            document = _strict_json(payload)
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            raise NativeHostV2Error("native cursor file is invalid") from exc
        if (
            not isinstance(document, dict)
            or set(document) != {"schema_version", "platform", "room_id", "cursor"}
            or document.get("schema_version") != 2
            or document.get("platform") != self.platform
            or document.get("room_id") != self.room_id
        ):
            raise NativeHostV2Error("native cursor binding is invalid")
        return self._validate_cursor(document["cursor"])

    def save(self, cursor: Any) -> None:
        accepted = self._validate_cursor(cursor)
        self._check_existing()
        payload = (
            json.dumps(
                {
                    "schema_version": 2,
                    "platform": self.platform,
                    "room_id": self.room_id,
                    "cursor": accepted,
                },
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        temporary = f".{self.name}.{uuid.uuid4().hex}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = -1
        try:
            descriptor = os.open(
                temporary,
                flags,
                0o600,
                dir_fd=self._directory_fd,
            )
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("cursor write made no progress")
                view = view[written:]
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(
                temporary,
                self.name,
                src_dir_fd=self._directory_fd,
                dst_dir_fd=self._directory_fd,
            )
            os.fsync(self._directory_fd)
        except Exception as exc:
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            try:
                os.unlink(temporary, dir_fd=self._directory_fd)
            except OSError:
                pass
            raise NativeHostV2Error("native cursor persistence failed") from exc

    def close(self) -> None:
        if self._directory_fd >= 0:
            descriptor = self._directory_fd
            self._directory_fd = -1
            os.close(descriptor)


__all__ = [
    "DurableCursorStoreV2",
    "NativeHostV2Error",
    "NativeRuntimeV2",
    "add_participant_arguments",
    "build_native_runtime",
]
