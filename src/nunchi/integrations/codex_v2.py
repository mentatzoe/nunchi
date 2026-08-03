"""Codex V2 room presence over the shared Discord transport."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import threading
import time
from typing import Any
import urllib.error

from .. import __version__
from ..ack import AckJournal, AckPolicy
from ..adapters.runtime import load_pinned_config
from ..attention import (
    AttentionEngine,
    AttentionPolicy,
    OpenAICompatibleAttentionModel,
    ParticipantProfile,
)
from ..errors import NunchiError, ValidationError
from ..observation import ObservationLimits, ObservationProvider, ParticipantBinding
from ..participant import (
    ConversationOpportunityScheduler,
    ParticipantTurnHost,
)
from ..participant_model import (
    PARTICIPANT_TURN_PROTOCOL_VERSION,
    ParticipantTurnProtocol,
)
from ..pipeline import AsyncDeliveryLane, DeliveryOutcome, NunchiV2Pipeline
from ..receipts import ReceiptJournal
from ..v2_contracts import validate_canonical_event
from ..mcp_discord.authorization import make_tool_authorization
from .discord_participant_transport import MCPDiscordTransport
from .mcp_client import StreamableMCPClient

NOTIFICATION_METHOD = "notifications/nunchi/v2/discord-event"
_THREAD_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_DISABLED_CODEX_FEATURES = (
    "apps",
    "auth_elicitation",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "code_mode_host",
    "computer_use",
    "hooks",
    "image_generation",
    "in_app_browser",
    "multi_agent",
    "network_proxy",
    "plugins",
    "plugin_sharing",
    "realtime_conversation",
    "remote_plugin",
    "request_permissions_tool",
    "shell_tool",
    "skill_mcp_dependency_install",
    "skill_search",
    "tool_call_mcp_elicitation",
    "tool_suggest",
    "unified_exec",
    "workspace_dependencies",
)
_MAX_PENDING_TASKS = 8
_MAX_AUTH_DOCUMENT_BYTES = 1_048_576
_RUNTIME_IDENTITY_FIELDS = {
    "provider",
    "account_id",
    "credential_scope",
    "auth_mode",
    "codex_home",
    "continuity_generation",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _atomic_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    """Durably replace one private state file without following symlinks."""

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    fd = os.open(
        temporary,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
        mode,
    )
    try:
        try:
            if os.write(fd, payload) != len(payload):
                raise OSError(f"short write to {path}")
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity_environment(codex_home: Path) -> dict[str, str]:
    environment = {
        key: os.environ[key]
        for key in (
            "HOME",
            "LANG",
            "LC_ALL",
            "LOGNAME",
            "PATH",
            "TMPDIR",
            "USER",
        )
        if key in os.environ
    }
    environment["CODEX_HOME"] = str(codex_home)
    return environment


def _codex_version(binary: str, environment: Mapping[str, str]) -> str:
    try:
        completed = subprocess.run(
            [binary, "--version"],
            env=dict(environment),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValidationError(f"Codex runtime version is unavailable: {exc}") from exc
    version = (completed.stdout or completed.stderr).strip()
    if completed.returncode != 0 or not version:
        raise ValidationError("Codex runtime version is unavailable")
    return version


def _codex_auth_mode(binary: str, environment: Mapping[str, str]) -> str:
    try:
        completed = subprocess.run(
            [binary, "login", "status"],
            env=dict(environment),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValidationError(f"Codex authentication status is unavailable: {exc}") from exc
    reported = f"{completed.stdout}\n{completed.stderr}".lower()
    if completed.returncode != 0:
        return "absent"
    if "chatgpt" in reported:
        return "chatgpt"
    if "api key" in reported or "api-key" in reported:
        return "api-key"
    if "access token" in reported or "access-token" in reported:
        return "access-token"
    return "unknown"


def _credential_binding(
    codex_home: Path,
    *,
    auth_mode: str,
    expected_account_id: str,
    provider: str,
    credential_scope: str,
) -> str:
    """Return a non-secret binding for the exact credential used by Codex."""

    auth_path = codex_home / "auth.json"
    try:
        fd = os.open(auth_path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise OSError("auth.json is not a regular file")
            with os.fdopen(fd, encoding="utf-8") as source:
                fd = -1
                raw = source.read(_MAX_AUTH_DOCUMENT_BYTES + 1)
            if len(raw.encode("utf-8")) > _MAX_AUTH_DOCUMENT_BYTES:
                raise OSError("auth.json exceeds the identity read limit")
            document = json.loads(raw)
        finally:
            if fd >= 0:
                os.close(fd)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(
            "persistent Codex mode requires readable file-backed credential identity: "
            f"{exc}"
        ) from exc
    if not isinstance(document, Mapping):
        raise ValidationError("Codex auth.json identity has an invalid shape")
    tokens = document.get("tokens")
    tokens = tokens if isinstance(tokens, Mapping) else {}
    stored_account_id = tokens.get("account_id")
    if isinstance(stored_account_id, str) and stored_account_id:
        if stored_account_id != expected_account_id:
            raise ValidationError(
                "Codex credential account differs from pinned runtime_identity"
            )
        material = (
            f"{provider}\0{auth_mode}\0{stored_account_id}\0{credential_scope}"
        )
        return hashlib.sha256(material.encode()).hexdigest()

    secret = None
    for candidate in (
        document.get("OPENAI_API_KEY"),
        document.get("api_key"),
        tokens.get("access_token"),
    ):
        if isinstance(candidate, str) and candidate:
            secret = candidate
            break
    if secret is None:
        raise ValidationError(
            "Codex credential identity is unavailable for persistent continuity; "
            "use fresh mode or file-backed authentication"
        )
    secret_digest = hashlib.sha256(secret.encode()).hexdigest()
    material = f"{provider}\0{auth_mode}\0{secret_digest}\0{credential_scope}"
    return hashlib.sha256(material.encode()).hexdigest()


def _strip_json_fence(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        value = value[3:]
        if value[:4].lower() == "json":
            value = value[4:]
        if value.rstrip().endswith("```"):
            value = value.rstrip()[:-3]
    return value.strip()


def _parse_codex_output(output: str) -> tuple[str | None, dict[str, Any] | None]:
    thread_id = None
    final_text = None
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "thread.started":
            candidate = event.get("thread_id")
            if isinstance(candidate, str) and _THREAD_ID.fullmatch(candidate):
                thread_id = candidate
        if event.get("type") == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    final_text = text
        if event.get("type") in ("agent_message", "turn.completed"):
            text = event.get("text") or event.get("final_output")
            if isinstance(text, str):
                final_text = text
    if final_text is None:
        return thread_id, None
    try:
        envelope = json.loads(_strip_json_fence(final_text))
    except json.JSONDecodeError:
        return thread_id, None
    if (
        not isinstance(envelope, dict)
        or set(envelope) != {"action_json"}
        or not isinstance(envelope["action_json"], str)
    ):
        return thread_id, None
    try:
        action = json.loads(envelope["action_json"])
    except json.JSONDecodeError:
        return thread_id, None
    return thread_id, action if isinstance(action, dict) else None


class CodexParticipant:
    core_protocol_version = PARTICIPANT_TURN_PROTOCOL_VERSION

    def __init__(
        self,
        *,
        profile: ParticipantProfile,
        config: Mapping[str, Any],
        binding: ParticipantBinding,
        state_directory: str | Path,
    ) -> None:
        allowed = {
            "model",
            "timeout_seconds",
            "session_mode",
            "runtime_identity",
            "capability_mode",
        }
        if set(config) - allowed:
            raise ValidationError("Codex participant config has unexpected fields")
        self.profile = profile
        self.binding = binding
        binary = shutil.which("codex")
        if binary is None:
            raise ValidationError("Codex executable is not installed on trusted PATH")
        self.binary = binary
        self.model = config.get("model")
        if self.model is not None and (
            not isinstance(self.model, str) or not self.model
        ):
            raise ValidationError("Codex model must be a non-empty string")
        state_root = Path(state_directory)
        self.working_directory = state_root / "participant-workspace"
        self.working_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.timeout_seconds = float(config.get("timeout_seconds", 300))
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValidationError("Codex timeout must be positive and finite")
        self.session_mode = str(config.get("session_mode", "fresh"))
        if self.session_mode not in ("persistent", "fresh"):
            raise ValidationError("Codex session_mode must be persistent or fresh")
        if self.session_mode == "persistent" and self.model is None:
            raise ValidationError("persistent Codex mode requires an exact model")
        self.capability_mode = str(config.get("capability_mode", "reduced"))
        if self.capability_mode != "reduced":
            raise ValidationError(
                "Codex configured capabilities are not yet secured by a final-effect "
                "bridge; use explicit capability_mode='reduced'"
            )
        self.session_path = state_root / "codex-v2-session.json"
        self.inflight_session_path = state_root / "codex-v2-session.inflight.json"
        self.output_schema_path = state_root / "codex-v2-action.schema.json"
        self._write_output_schema()

        identity_raw = config.get("runtime_identity")
        if self.session_mode == "persistent" and identity_raw is None:
            raise ValidationError(
                "persistent Codex mode requires a pinned runtime_identity"
            )
        if identity_raw is not None:
            if not isinstance(identity_raw, Mapping) or set(identity_raw) != _RUNTIME_IDENTITY_FIELDS:
                raise ValidationError("Codex runtime_identity has an invalid closed shape")
            strings = {
                key: identity_raw[key]
                for key in (
                    "provider",
                    "account_id",
                    "credential_scope",
                    "auth_mode",
                    "codex_home",
                )
            }
            if any(not isinstance(value, str) or not value for value in strings.values()):
                raise ValidationError("Codex runtime_identity strings must be non-empty")
            generation = identity_raw["continuity_generation"]
            if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
                raise ValidationError(
                    "Codex continuity_generation must be a positive integer"
                )
            if strings["auth_mode"] not in {
                "chatgpt",
                "api-key",
                "access-token",
            }:
                raise ValidationError("Codex runtime_identity auth_mode is unsupported")
            configured_home = Path(strings["codex_home"])
            if not configured_home.is_absolute():
                raise ValidationError("Codex runtime_identity codex_home must be absolute")
            try:
                self.codex_home = configured_home.resolve(strict=True)
            except OSError as exc:
                raise ValidationError(
                    f"Codex runtime_identity codex_home is unavailable: {exc}"
                ) from exc
            if not self.codex_home.is_dir():
                raise ValidationError("Codex runtime_identity codex_home must be a directory")
            try:
                binary_path = Path(self.binary).resolve(strict=True)
                binary_sha256 = _sha256_file(binary_path)
            except OSError as exc:
                raise ValidationError(
                    f"Codex executable identity is unavailable: {exc}"
                ) from exc
            self.binary = str(binary_path)
            identity_environment = _identity_environment(self.codex_home)
            version = _codex_version(self.binary, identity_environment)
            expected_auth_mode = strings["auth_mode"]
            observed_auth_mode = _codex_auth_mode(self.binary, identity_environment)
            if observed_auth_mode != expected_auth_mode:
                raise ValidationError(
                    "Codex authenticated runtime differs from pinned runtime_identity"
                )
            credential_binding_sha256 = _credential_binding(
                self.codex_home,
                auth_mode=expected_auth_mode,
                expected_account_id=strings["account_id"],
                provider=strings["provider"],
                credential_scope=strings["credential_scope"],
            )
            self.runtime_identity: dict[str, Any] = {
                **dict(identity_raw),
                "codex_home": str(self.codex_home),
                "binary_path": str(binary_path),
                "binary_sha256": binary_sha256,
                "codex_version": version,
                "credential_binding_sha256": credential_binding_sha256,
            }
        else:
            ambient_home = os.environ.get("CODEX_HOME")
            self.codex_home = Path(
                ambient_home if ambient_home else Path.home() / ".codex"
            ).resolve()
            self.runtime_identity = {
                "bound": False,
                "codex_home": str(self.codex_home),
                "binary_path": self.binary,
            }
        behavior = {
            "profile_sha256": self.profile.sha256,
            "participant_id": self.binding.participant_id,
            "actor_id": self.binding.actor_id,
            "room_id": self.binding.room_id,
            "continuity_scope_id": self.binding.continuity_scope_id,
            "model": self.model,
            "runtime_identity": self.runtime_identity,
            "capability_mode": self.capability_mode,
            "disabled_features": list(_DISABLED_CODEX_FEATURES),
            "sandbox": "read-only",
        }
        self.behavior_sha256 = hashlib.sha256(
            _canonical_json(behavior).encode()
        ).hexdigest()
        self._lock = threading.RLock()
        self._pending_lock = threading.Lock()
        self._pending_tasks: dict[str, str] = {}

    def _write_output_schema(self) -> None:
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "action_json": {
                    "type": "string",
                    "description": (
                        "One compact JSON object encoding the bound Nunchi "
                        "participant-turn action envelope."
                    ),
                }
            },
            "required": ["action_json"],
        }
        _atomic_write(self.output_schema_path, _canonical_json(schema).encode())

    def _load_session(self) -> str | None:
        if self.session_mode == "fresh" or not self.session_path.exists():
            return None
        try:
            if self.session_path.is_symlink():
                raise OSError("session state is a symlink")
            state = json.loads(self.session_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Codex session state is not trustworthy: {exc}") from exc
        expected = {
            "schema_version",
            "thread_id",
            "participant_id",
            "actor_id",
            "room_id",
            "continuity_scope_id",
            "profile_sha256",
            "behavior_sha256",
            "model",
            "capability_mode",
            "runtime_identity",
        }
        if not isinstance(state, dict) or set(state) != expected:
            raise RuntimeError("Codex session state has an invalid closed shape")
        if (
            state["schema_version"] != 2
            or state["participant_id"] != self.binding.participant_id
            or state["actor_id"] != self.binding.actor_id
            or state["room_id"] != self.binding.room_id
            or state["continuity_scope_id"] != self.binding.continuity_scope_id
            or state["profile_sha256"] != self.profile.sha256
            or state["behavior_sha256"] != self.behavior_sha256
            or state["model"] != self.model
            or state["capability_mode"] != self.capability_mode
            or state["runtime_identity"] != self.runtime_identity
            or not isinstance(state["thread_id"], str)
            or not _THREAD_ID.fullmatch(state["thread_id"])
        ):
            raise RuntimeError("Codex session state binding is invalid")
        return state["thread_id"]

    def stage_task(self, request_id: str, thread_id: str) -> None:
        """Hold a task ID until the core-owned host accepts this turn."""

        if (
            self.session_mode != "persistent"
            or not isinstance(request_id, str)
            or not _THREAD_ID.fullmatch(thread_id)
        ):
            return
        with self._pending_lock:
            self._pending_tasks.pop(request_id, None)
            self._pending_tasks[request_id] = thread_id
            while len(self._pending_tasks) > _MAX_PENDING_TASKS:
                self._pending_tasks.pop(next(iter(self._pending_tasks)))

    def commit_task(self, request_id: str) -> None:
        """Persist one staged task after host acceptance is durably recorded."""

        with self._pending_lock:
            thread_id = self._pending_tasks.pop(request_id, None)
        if thread_id is not None:
            with self._lock:
                self._save_session(thread_id)
                self._clear_inflight_session()

    def discard_task(self, request_id: str | None) -> None:
        if not isinstance(request_id, str):
            return
        with self._pending_lock:
            self._pending_tasks.pop(request_id, None)

    @property
    def pending_task_count(self) -> int:
        with self._pending_lock:
            return len(self._pending_tasks)

    def _save_session(self, thread_id: str) -> None:
        payload = _canonical_json(
            {
                "schema_version": 2,
                "thread_id": thread_id,
                "participant_id": self.binding.participant_id,
                "actor_id": self.binding.actor_id,
                "room_id": self.binding.room_id,
                "continuity_scope_id": self.binding.continuity_scope_id,
                "profile_sha256": self.profile.sha256,
                "behavior_sha256": self.behavior_sha256,
                "model": self.model,
                "capability_mode": self.capability_mode,
                "runtime_identity": self.runtime_identity,
            },
        ).encode()
        _atomic_write(self.session_path, payload)

    def _consume_committed_session(self) -> None:
        """Make a resumed task non-authoritative before Codex can mutate it.

        Codex has no non-interactive transactional resume seam. Moving the pin
        first means a crash, malformed result, cancellation, expiry, or host
        rejection resets safely instead of resuming a task whose failed turn
        may already have changed its internal history. Host acceptance writes a
        fresh committed pin and then clears this recoverable diagnostic marker.
        """

        if not self.session_path.exists():
            return
        os.replace(self.session_path, self.inflight_session_path)
        directory_fd = os.open(self.session_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _clear_inflight_session(self) -> None:
        try:
            os.unlink(self.inflight_session_path)
        except FileNotFoundError:
            return
        directory_fd = os.open(self.inflight_session_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def session_status(self) -> dict[str, Any]:
        with self._lock:
            if self.session_mode == "fresh":
                return {
                    "mode": "fresh",
                    "status": "new-task",
                    "compatible": True,
                    "committed_task_id": None,
                    "reset_reason": "fresh-mode",
                }
            try:
                thread_id = self._load_session()
            except RuntimeError as exc:
                return {
                    "mode": "persistent",
                    "status": "incompatible",
                    "compatible": False,
                    "committed_task_id": None,
                    "reset_reason": str(exc),
                    "repair": (
                        "quarantine codex-v2-session.json after inspection, then "
                        "restart to create a new task under the pinned runtime identity"
                    ),
                }
            if thread_id is None and self.inflight_session_path.exists():
                return {
                    "mode": "persistent",
                    "status": "reset-required",
                    "compatible": True,
                    "committed_task_id": None,
                    "reset_reason": (
                        "the prior committed task was consumed before a turn that "
                        "did not reach host acceptance"
                    ),
                    "repair": (
                        "the next accepted opportunity will create and commit a new task"
                    ),
                }
            return {
                "mode": "persistent",
                "status": "committed" if thread_id is not None else "new-task",
                "compatible": True,
                "committed_task_id": thread_id,
                "reset_reason": None if thread_id is not None else "not-created",
            }

    def runtime_status(self) -> dict[str, Any]:
        identity = self.runtime_identity
        if identity.get("bound") is False:
            return {
                "bound": False,
                "codex_home": identity["codex_home"],
                "binary_path": identity["binary_path"],
            }
        account_binding = hashlib.sha256(
            (
                f"{identity['provider']}\0{identity['account_id']}\0"
                f"{identity['credential_scope']}"
            ).encode()
        ).hexdigest()
        return {
            "bound": True,
            "provider": identity["provider"],
            "auth_mode": identity["auth_mode"],
            "credential_scope": identity["credential_scope"],
            "account_binding_sha256": account_binding,
            "codex_home": identity["codex_home"],
            "binary_path": identity["binary_path"],
            "binary_sha256": identity["binary_sha256"],
            "codex_version": identity["codex_version"],
            "credential_binding_sha256": identity["credential_binding_sha256"],
            "continuity_generation": identity["continuity_generation"],
        }

    def _environment(self) -> dict[str, str]:
        return _identity_environment(self.codex_home)

    def _verify_runtime_identity(self) -> None:
        """Re-attest persistent identity immediately before native execution."""

        identity = self.runtime_identity
        if identity.get("bound") is False:
            return
        try:
            binary_path = Path(self.binary).resolve(strict=True)
            binary_sha256 = _sha256_file(binary_path)
        except OSError as exc:
            raise RuntimeError(f"Codex executable identity is unavailable: {exc}") from exc
        environment = self._environment()
        observed = {
            "binary_path": str(binary_path),
            "binary_sha256": binary_sha256,
            "codex_version": _codex_version(self.binary, environment),
            "auth_mode": _codex_auth_mode(self.binary, environment),
            "credential_binding_sha256": _credential_binding(
                self.codex_home,
                auth_mode=identity["auth_mode"],
                expected_account_id=identity["account_id"],
                provider=identity["provider"],
                credential_scope=identity["credential_scope"],
            ),
        }
        if any(identity[key] != value for key, value in observed.items()):
            raise RuntimeError("Codex runtime identity changed before execution")

    def _prompt(self, protocol: ParticipantTurnProtocol) -> str:
        """Compatibility accessor; the prompt bytes are owned by core."""

        return protocol.text

    def run_protocol(self, *, wake, opportunity, expand, cancel):
        protocol = ParticipantTurnProtocol(
            profile=self.profile,
            wake=wake,
            opportunity=opportunity,
        )
        with self._lock:
            self._verify_runtime_identity()
            active_thread = self._load_session()
            if active_thread is not None:
                self._consume_committed_session()
            extra = [
                "--ignore-user-config",
                "--ignore-rules",
                "--strict-config",
                "--config",
                'sandbox_mode="read-only"',
                "--output-schema",
                str(self.output_schema_path),
                "--json",
                *(
                    item
                    for feature in _DISABLED_CODEX_FEATURES
                    for item in ("--disable", feature)
                ),
            ]
            if self.model is not None:
                extra.extend(("--model", self.model))
            deadline = time.monotonic() + self.timeout_seconds
            while True:
                prompt = self._prompt(protocol)
                if active_thread:
                    command = [
                        self.binary,
                        "exec",
                        "resume",
                        "--skip-git-repo-check",
                        *extra,
                        active_thread,
                        prompt,
                    ]
                else:
                    command = [
                        self.binary,
                        "exec",
                        "--skip-git-repo-check",
                        "--sandbox",
                        "read-only",
                        *extra,
                        prompt,
                    ]
                process = subprocess.Popen(
                    command,
                    cwd=self.working_directory,
                    env=self._environment(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                while process.poll() is None:
                    if cancel.is_set() or time.monotonic() >= deadline:
                        self.discard_task(protocol.request_id)
                        process.terminate()
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                        return None
                    time.sleep(0.05)
                stdout, stderr = process.communicate()
                thread_id, raw_action = _parse_codex_output(stdout)
                if active_thread and thread_id and thread_id != active_thread:
                    raise RuntimeError(
                        f"Codex resumed unexpected task {thread_id}; "
                        f"expected {active_thread}"
                    )
                active_thread = thread_id or active_thread
                if process.returncode != 0:
                    raise RuntimeError(
                        (stderr or f"Codex exited {process.returncode}")[-500:]
                    )
                if raw_action is None:
                    raise RuntimeError(
                        "Codex participant output was not one bound action envelope"
                    )
                done, action = protocol.consume(raw_action, expand=expand)
                if done:
                    if self.session_mode == "persistent":
                        if active_thread is None:
                            raise RuntimeError(
                                "Codex did not report a persistent task ID"
                            )
                        self.stage_task(protocol.request_id, active_thread)
                    return action
                if active_thread is None:
                    raise RuntimeError(
                        "Codex did not report a task ID for context expansion"
                    )

    def __call__(self, *, wake, expand, cancel):
        return self.run_protocol(
            wake=wake,
            opportunity={
                "generation": 1,
                "lifecycle_id": "direct-library-call",
                "deadline_id": "direct-library-call",
                "permissions": {
                    "revision": "direct-library-call",
                    "ordinary_actions": ["message", "reply", "reaction"],
                    "privileged_proposals": True,
                },
            },
            expand=expand,
            cancel=cancel,
        )


class CodexTaskReceiptJournal(ReceiptJournal):
    """Commit Codex task continuity only after the host accepts the turn."""

    def __init__(self, path, *, participant: CodexParticipant | None = None, **kwargs) -> None:
        super().__init__(path, **kwargs)
        self.participant = participant

    def append(self, record, *, writer):
        appended = super().append(record, writer=writer)
        participant = self.participant
        if participant is None:
            return appended
        if appended["stage"] == "transport":
            participant.commit_task(appended["request_id"])
        elif appended["stage"] == "participant-host":
            if appended["body"].get("outcome") == "silent":
                participant.commit_task(appended["request_id"])
        return appended


class CodexRoomRuntime:
    def __init__(self, config: Mapping[str, Any], client: StreamableMCPClient) -> None:
        required = {
            "schema_version",
            "binding",
            "profile",
            "attention",
            "limits",
            "state_directory",
            "transport",
            "codex",
        }
        if (
            required - set(config)
            or set(config) - (required | {"ack"})
            or config["schema_version"] != 2
        ):
            raise ValidationError("Codex V2 config has a missing or unexpected field")
        binding_raw = config["binding"]
        if not isinstance(binding_raw, Mapping):
            raise ValidationError("Codex binding must be an object")
        self.binding = ParticipantBinding(
            **{
                **binding_raw,
                "names": tuple(binding_raw.get("names", ())),
            }
        )
        if self.binding.platform != "discord":
            raise ValidationError("Codex V2 currently requires the shared Discord transport")
        profile_raw = config["profile"]
        if not isinstance(profile_raw, Mapping) or set(profile_raw) != {"path", "sha256"}:
            raise ValidationError("Codex profile config is invalid")
        profile = ParticipantProfile.load(
            profile_raw["path"],
            expected_sha256=profile_raw["sha256"],
        )
        if (
            profile.participant_id != self.binding.participant_id
            or profile.actor_id != self.binding.actor_id
        ):
            raise ValidationError("Codex profile and exact transport self differ")
        attention_raw = config["attention"]
        if not isinstance(attention_raw, Mapping) or set(attention_raw) != {"policy", "model"}:
            raise ValidationError("Codex attention config is invalid")
        policy = AttentionPolicy(**attention_raw["policy"])
        model = (
            OpenAICompatibleAttentionModel.from_trusted_config(attention_raw["model"])
            if policy.preattention_enabled
            else None
        )
        limits = ObservationLimits(**config["limits"])
        state = Path(config["state_directory"])
        state.mkdir(parents=True, exist_ok=True)
        participant = CodexParticipant(
            profile=profile,
            config=config["codex"],
            binding=self.binding,
            state_directory=state,
        )
        receipts = CodexTaskReceiptJournal(
            state / "codex-v2-receipts.jsonl",
            participant=participant,
        )
        observation = ObservationProvider(
            self.binding,
            limits=limits,
            receipts=receipts,
            persistence_path=state / "codex-v2-observations.jsonl",
            event_visibility={
                "message": "history-and-live",
                "reaction": "history-and-live",
                "membership": "live-only",
            },
        )
        scheduler = ConversationOpportunityScheduler(
            f"{self.binding.participant_id}:{self.binding.continuity_scope_id}"
        )
        try:
            ack_policy = AckPolicy(**dict(config.get("ack", {})))
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"Codex ACK policy is invalid: {exc}") from exc
        transport = MCPDiscordTransport(
            client,
            self.binding.room_id,
            self.binding.participant_id,
            self.binding.actor_id,
            self._output_secret(config["transport"]),
        )
        host = ParticipantTurnHost(
            observation=observation,
            participant=participant,
            transport=transport,
            scheduler=scheduler,
            receipts=receipts,
            ack_policy=ack_policy,
            ack_journal=AckJournal(state / "codex-v2-acks.jsonl"),
            participant_timeout_seconds=participant.timeout_seconds + 5,
        )
        attention = AttentionEngine(
            profile=profile,
            model=model,
            policy=policy,
            receipts=receipts,
            ack_policy=ack_policy,
            reaction_capability_provider=host.reaction_capability,
        )
        self.pipeline = NunchiV2Pipeline(
            observation=observation,
            attention=attention,
            host=host,
            scheduler=scheduler,
        )
        self.lane = AsyncDeliveryLane(self.pipeline)
        self.client = client
        self.participant = participant
        self.output_secret = self._output_secret(config["transport"])

    @staticmethod
    def _output_secret(transport: Mapping[str, Any]) -> bytes:
        env_name = transport.get("output_key_env")
        if not isinstance(env_name, str) or not env_name:
            raise ValidationError("Codex transport output_key_env must be non-empty")
        value = os.environ.get(env_name)
        if value is None or len(value.encode()) < 32:
            raise ValidationError(
                f"Codex transport output authorization key is absent or short in {env_name}"
            )
        return value.encode()

    def handle(self, params: Mapping[str, Any]):
        required = {
            "schema_version",
            "delivery_id",
            "room_id",
            "event",
            "actors",
            "continuity_gap",
            "target_participant_id",
            "transport_self_actor_id",
        }
        if not isinstance(params, Mapping) or set(params) != required:
            raise ValidationError("shared Discord notification has an invalid V2 shape")
        if params["schema_version"] != 2:
            raise ValidationError("shared Discord notification is not V2")
        if not isinstance(params["continuity_gap"], bool):
            raise ValidationError("shared Discord continuity_gap must be a boolean")
        if params["target_participant_id"] != self.binding.participant_id:
            raise ValidationError("shared Discord notification targets another participant")
        if params["transport_self_actor_id"] != self.binding.actor_id:
            raise ValidationError("authenticated Discord self differs from exact binding")
        if str(params["room_id"]) != self.binding.room_id:
            raise ValidationError("shared Discord notification targets another room")
        if params["continuity_gap"]:
            if params["event"] is not None or params["actors"] != {}:
                raise ValidationError("Discord gap notification cannot fabricate event facts")
            self.lane.cancel()
            observed = self.pipeline.observation.mark_continuity_gap(
                delivery_id=str(params["delivery_id"]),
                detail="shared Discord transport declared a bounded queue gap",
            )
            return DeliveryOutcome(observed, (), False)
        event = validate_canonical_event(params["event"]) if params["event"] is not None else None
        return self.lane.submit(
            delivery_id=params["delivery_id"],
            event=event,
            actors=params["actors"],
            authorized_route=True,
        )

    def register_transport(self) -> None:
        arguments = {
            "participant_id": self.binding.participant_id,
            "channel_id": self.binding.room_id,
        }
        supplied = {
            **arguments,
            "_nunchi_authorization": make_tool_authorization(
                secret=self.output_secret,
                request_id=f"transport-registration-{time.time_ns()}",
                participant_id=self.binding.participant_id,
                room_id=self.binding.room_id,
                tool="register_participant",
                arguments=arguments,
            ),
        }
        result = self.client.call_tool("register_participant", supplied)
        if not isinstance(result, Mapping) or result.get("isError") is True:
            raise RuntimeError("shared Discord participant registration failed")
        content = result.get("content")
        if not isinstance(content, list) or len(content) != 1:
            raise RuntimeError("shared Discord registration returned an invalid result")
        item = content[0]
        text = item.get("text") if isinstance(item, Mapping) else None
        if not isinstance(text, str):
            raise RuntimeError("shared Discord registration omitted its attestation")
        try:
            attestation = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "shared Discord registration attestation is malformed"
            ) from exc
        if attestation != {
            "registered": True,
            "participant_id": self.binding.participant_id,
            "room_id": self.binding.room_id,
            "transport_self_actor_id": self.binding.actor_id,
        }:
            raise RuntimeError("shared Discord registration attestation binding differs")

    def transport_interrupted(self) -> None:
        """Invalidate active work and record uncertainty before reconnect."""
        self.lane.cancel()
        self.pipeline.observation.mark_continuity_gap(
            delivery_id=f"discord:mcp-stream-gap:{time.time_ns()}",
            detail="shared Discord notification stream continuity is uncertain",
        )

    def probe(self):
        session = self.participant.session_status()
        return {
            "product": "nunchi",
            "product_version": __version__,
            "generation": 2,
            "surface": "codex",
            "participant_id": self.binding.participant_id,
            "actor_id": self.binding.actor_id,
            "room_id": self.binding.room_id,
            "session_mode": self.participant.session_mode,
            "persistent_session": self.participant.session_mode == "persistent",
            "task_state": session,
            "runtime_identity": self.participant.runtime_status(),
            "capability_mode": self.participant.capability_mode,
            "disabled_capabilities": list(_DISABLED_CODEX_FEATURES),
            "capability_limitation": (
                "normal Codex effect-bearing capabilities remain unavailable until "
                "they have a version-checked final-effect bridge"
            ),
            "shared_discord_transport": True,
            "send_time_social_judgment": False,
            "v1_fallback": False,
        }


def _parser():
    parser = argparse.ArgumentParser(prog="nunchi-codex-room-runner")
    parser.add_argument("--config")
    parser.add_argument(
        "--config-sha256",
        default=os.environ.get("NUNCHI_CODEX_CONFIG_SHA256"),
    )
    parser.add_argument("--probe", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if not args.config:
            if args.probe:
                print(
                    json.dumps(
                        {
                            "product": "nunchi",
                            "product_version": __version__,
                            "generation": 2,
                            "surface": "codex",
                            "configured": False,
                            "v1_fallback": False,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
                return 0
            raise ValidationError("--config is required")
        if not args.config_sha256:
            raise ValidationError("--config-sha256 is required")
        config = load_pinned_config(args.config, args.config_sha256)
        transport = config.get("transport")
        if not isinstance(transport, Mapping) or set(transport) != {
            "url",
            "timeout_seconds",
            "output_key_env",
        }:
            raise ValidationError("Codex shared transport config is invalid")
        client = StreamableMCPClient(
            str(transport["url"]),
            timeout_seconds=float(transport["timeout_seconds"]),
        )
        runtime = CodexRoomRuntime(config, client)
        if args.probe:
            probe = runtime.probe()
            probe["configured"] = True
            print(json.dumps(probe, sort_keys=True, separators=(",", ":")))
            return 0
        delay = 1.0
        while True:
            try:
                client.connect()
                runtime.register_transport()
                for method, params in client.notifications():
                    if method != NOTIFICATION_METHOD:
                        continue
                    runtime.handle(params)
                runtime.transport_interrupted()
                delay = 1.0
            except (urllib.error.URLError, RuntimeError, OSError):
                runtime.transport_interrupted()
                print("Codex shared transport reconnect after operational error", file=sys.stderr)
                time.sleep(delay)
                delay = min(delay * 2, 30)
    except (NunchiError, ValueError) as exc:
        print(f"Codex V2 runner error: {exc}", file=sys.stderr)
        return 3 if isinstance(exc, ValidationError) else 1


if __name__ == "__main__":
    raise SystemExit(main())
