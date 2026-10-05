"""Claude Code V2 room presence: a per-room gate and a dedicated session.

The gate is the platform-owned wrapper described by `docs/v2-delivery.md` and
`docs/platform-v2.md`.  It owns the platform obligations: native identity, the
dedicated Claude Code session and its Nunchi mod, the session's environment,
cancellation, private persistence, and the inventoried privileged executors.
It reuses the shared owners for everything else.  Observation, attention,
scheduling, the participant host, the privileged-action coordinator, and the
Discord consumer transport are imported, never reimplemented.

The participant is the user's own Claude Code agent in one dedicated session
per room (`claude_code_gate`).  It keeps the user's configuration and native
tools under the user's own permission rules.  Its only way into the room is
the room tools the Nunchi mod registers, and every room action passes the
host's one output commit point.
"""

from __future__ import annotations

import argparse
import errno
from collections.abc import Mapping, Sequence
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any
import urllib.error

from .. import __version__
from ..ack import AckJournal, AckPolicy
from ..adapters.decisions_api import ATTENTION_KINDS
from ..adapters.runtime import load_pinned_config
from ..attention import (
    AttentionEngine,
    AttentionPolicy,
    attention_model_from_config,
    ParticipantProfile,
)
from ..authorization import (
    AuthorizationCoordinator,
    AuthorizationJournal,
    PinnedFilePolicySource,
)
from ..errors import NunchiError, ValidationError
from ..observation import ObservationLimits, ObservationProvider, ParticipantBinding
from ..participant import ConversationOpportunityScheduler, TransportResult
from ..pipeline import AsyncDeliveryLane, DeliveryOutcome, NunchiV2Pipeline
from ..receipts import ReceiptJournal
from ..v2_contracts import validate_canonical_event
from ..mcp_discord.authorization import make_tool_authorization
from .claude_code_gate import (
    SESSION_ENV,
    SOCKET_ENV,
    ClaudeCodeSession,
    GatedParticipant,
    GatedTurnHost,
    GateServer,
    SecretGuard,
    full_tool_name,
)
from .discord_participant_transport import MCPDiscordTransport
from .mcp_client import StreamableMCPClient

NOTIFICATION_METHOD = "notifications/nunchi/v2/discord-event"
SURFACE = "claude-code"
MINIMUM_CLAUDE_CODE = (2, 1, 287)
MOD_DIRECTORY = Path(__file__).with_name("claude_code_mod")
# What the session loads.  Claude Code writes generated type files into a mod
# folder it loads, so the session gets a private copy, never the package.
MOD_FILES = (
    ".claude-plugin/plugin.json",
    "hooks/hooks.json",
    "hooks/register.ts",
)

_CLAUDE_CODE_KEYS = {
    "executable",
    "working_directory",
    "model",
    "timeout_seconds",
    "session_mode",
    "disallowed_tools",
    "protect_nunchi_files",
    "withhold_env",
}
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")


class ConfinedPathDrift(OSError):
    """The rooted path stopped naming the object we wrote.

    The write itself stayed confined and durable, but the resource the
    privileged proposal named changed underneath it.  A privileged effect
    cannot report success for a resource it can no longer identify, so this
    becomes `unknown` rather than `sent` or `failed`.
    """



def _assert_root_identity(root_fd: int, root_path: Path) -> None:
    """Confirm the handle we opened still *is* the configured workspace root.

    Holding a directory handle proves the write stayed under that inode. It
    does not prove the inode is still the authorized location: renaming the
    root itself moves the whole workspace, and every ancestry check inside it
    keeps passing because they are all relative to the moved root.

    The configured path is the trust anchor, so it is re-stated here without
    following a symlink at its final component — a symlink substituted at the
    configured path is a different inode and is drift, not a resolution.
    """
    try:
        observed = os.stat(root_path, follow_symlinks=False)
    except OSError as exc:
        raise ConfinedPathDrift(
            "the configured workspace root no longer exists"
        ) from exc
    held = os.fstat(root_fd)
    if (observed.st_dev, observed.st_ino) != (held.st_dev, held.st_ino):
        raise ConfinedPathDrift(
            "the configured workspace root no longer names the directory in use"
        )


def _assert_still_rooted(
    root_path: Path, handles: list[int], parts, written_stat
) -> None:
    """Confirm the write is still inside the root *and* at the proposed path.

    Two independent checks, because each catches what the other misses:

    * **Ancestry.** Walking `..` from the directory handle we wrote through
      must arrive at the root handle's inode. A rooted handle does not keep
      its ancestry: an opened directory that is renamed out of the workspace
      takes our writes with it, and only walking up detects that.
    * **Rooted re-resolution.** Re-walking the proposed path from the root,
      refusing symlinks at every component, must land on exactly the inode we
      wrote. A plain `os.stat(..., follow_symlinks=False)` is not enough — it
      only refuses a symlink as the *final* component and silently follows
      intermediate ones, so a substituted parent directory resolves straight
      back to our inode and the check passes while the file sits outside.
    """
    root_fd, current = handles[0], handles[-1]
    # The root itself first: every check below is relative to this handle, so
    # a moved root would let all of them pass against the wrong location.
    _assert_root_identity(root_fd, root_path)
    root_stat = os.fstat(root_fd)

    probe = os.open(".", os.O_RDONLY | os.O_DIRECTORY, dir_fd=current)
    try:
        for _ in range(len(parts) - 1):
            parent = os.open("..", os.O_RDONLY | os.O_DIRECTORY, dir_fd=probe)
            os.close(probe)
            probe = parent
        reached = os.fstat(probe)
    finally:
        try:
            os.close(probe)
        except OSError:
            pass
    if (reached.st_dev, reached.st_ino) != (root_stat.st_dev, root_stat.st_ino):
        raise ConfinedPathDrift(
            "the written directory is no longer inside the workspace root"
        )

    walk = os.open(".", os.O_RDONLY | os.O_DIRECTORY, dir_fd=root_fd)
    try:
        for part in parts[:-1]:
            try:
                nxt = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=walk,
                )
            except OSError as exc:
                raise ConfinedPathDrift(
                    "proposed workspace path no longer resolves without symlinks"
                ) from exc
            os.close(walk)
            walk = nxt
        try:
            observed = os.stat(parts[-1], dir_fd=walk, follow_symlinks=False)
        except OSError as exc:
            raise ConfinedPathDrift(
                "proposed workspace path no longer resolves"
            ) from exc
    finally:
        try:
            os.close(walk)
        except OSError:
            pass
    if (observed.st_dev, observed.st_ino) != (
        written_stat.st_dev,
        written_stat.st_ino,
    ):
        raise ConfinedPathDrift(
            "proposed workspace path no longer names the written file"
        )


def _write_confined(root: Path, relative: str, payload: bytes) -> str:
    """Write `payload` at `root/relative`, confined by rooted directory handles.

    Pathname-based confinement is not enough.  Validating a resolved path and
    then calling `os.open`/`os.replace` on pathnames leaves a window in which a
    validated parent directory can be replaced by a symlink, so the write or
    the rename resolves somewhere else entirely.

    This walks the path one component at a time from an open handle on the
    root, opening each directory `O_NOFOLLOW | O_DIRECTORY` relative to the
    previous handle, and performs the staging open, the rename, and the
    read-back relative to the final handle.  A component swapped for a symlink
    fails the open; a component swapped for another directory after the handle
    is taken cannot move the write, because the handle still refers to the
    original inode.  There is no window in which a pathname is re-resolved.

    Returns the SHA-256 of the bytes actually read back from the written file.
    """
    parts = PurePosixPath(relative).parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ValueError("confined path must not be empty or traverse upward")
    handles: list[int] = [
        os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    ]
    try:
        current = handles[0]
        for part in parts[:-1]:
            try:
                os.mkdir(part, 0o700, dir_fd=current)
            except FileExistsError:
                pass
            current = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current,
            )
            handles.append(current)
        name = parts[-1]
        staged = f".{name}.{secrets.token_hex(8)}.tmp"
        fd = os.open(
            staged,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o600,
            dir_fd=current,
        )
        try:
            try:
                if os.write(fd, payload) != len(payload):
                    raise OSError("short confined write")
                os.fsync(fd)
            finally:
                os.close(fd)
            _assert_root_identity(handles[0], root)
            os.replace(staged, name, src_dir_fd=current, dst_dir_fd=current)
        except BaseException:
            try:
                os.unlink(staged, dir_fd=current)
            except OSError:
                pass
            raise
        os.fsync(current)
        verify = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=current)
        try:
            written = b""
            while True:
                chunk = os.read(verify, 65536)
                if not chunk:
                    break
                written += chunk
        finally:
            os.close(verify)
        if written != payload:
            raise OSError("confined write could not be confirmed")
        # Confinement is not attestation.  The rooted handles guarantee the
        # bytes landed inside the root, but a directory renamed out from under
        # us would leave the proposed path naming something else entirely.
        # Compare what we wrote against a fresh resolution of the proposed
        # path; any drift means the exact action can no longer be attested.
        written_stat = os.stat(name, dir_fd=current, follow_symlinks=False)
        try:
            _assert_still_rooted(root, handles, parts, written_stat)
        except ConfinedPathDrift:
            # The bytes may have landed outside the root because the directory
            # we held was moved there.  Remove what we wrote before reporting;
            # an unattestable effect should not also be a lasting one.
            try:
                os.unlink(name, dir_fd=current)
            except OSError:
                pass
            raise
        return hashlib.sha256(written).hexdigest()
    finally:
        for handle in reversed(handles):
            try:
                os.close(handle)
            except OSError:
                pass


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)



def claude_code_version(executable: str) -> tuple[int, int, int] | None:
    """Return the installed Claude Code version, or None when it cannot be read."""

    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = _VERSION.search(completed.stdout or "")
    if completed.returncode != 0 or match is None:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def mod_version() -> str | None:
    """Return the version of the Nunchi mod shipped with this package."""

    try:
        manifest = json.loads(
            (MOD_DIRECTORY / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return None
    version = manifest.get("version") if isinstance(manifest, dict) else None
    return version if isinstance(version, str) else None


def _string_list(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValidationError(f"Claude Code {label} must be a list of non-empty strings")
    return tuple(value)


def _absolute(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        raise ValidationError(f"Claude Code {label} must be an absolute path")
    return Path(value)


def _runtime_directory() -> Path:
    """A short private directory for the gate socket (Unix socket paths are short)."""

    base = os.environ.get("XDG_RUNTIME_DIR")
    if not base or len(base) > 60 or not os.path.isdir(base):
        base = tempfile.gettempdir()
    return Path(base) / f"nunchi-cc-{secrets.token_hex(6)}"



class ClaudeCodeRoomRuntime:
    """One Claude Code participant bound to one room over shared transport."""

    def __init__(
        self,
        config: Mapping[str, Any],
        client: StreamableMCPClient,
        *,
        session: Any = None,
    ) -> None:
        required = {
            "schema_version",
            "binding",
            "profile",
            "attention",
            "limits",
            "state_directory",
            "transport",
            "claude_code",
        }
        optional = {"authorization", "ack"}
        supplied = set(config)
        if not required <= supplied or supplied - (required | optional):
            raise ValidationError(
                "Claude Code V2 config has a missing or unexpected field"
            )
        if config["schema_version"] != 2:
            raise ValidationError("Claude Code V2 config is not V2")

        binding_raw = config["binding"]
        if not isinstance(binding_raw, Mapping):
            raise ValidationError("Claude Code binding must be an object")
        self.binding = ParticipantBinding(
            **{**binding_raw, "names": tuple(binding_raw.get("names", ()))}
        )
        if self.binding.platform != "discord":
            raise ValidationError(
                "Claude Code V2 currently requires the shared Discord transport"
            )

        profile_raw = config["profile"]
        if not isinstance(profile_raw, Mapping) or set(profile_raw) != {
            "path",
            "sha256",
        }:
            raise ValidationError("Claude Code profile config is invalid")
        profile = ParticipantProfile.load(
            profile_raw["path"],
            expected_sha256=profile_raw["sha256"],
        )
        if (
            profile.participant_id != self.binding.participant_id
            or profile.actor_id != self.binding.actor_id
        ):
            raise ValidationError(
                "Claude Code profile and exact transport self differ"
            )
        self.profile = profile

        attention_raw = config["attention"]
        if not isinstance(attention_raw, Mapping) or set(attention_raw) != {
            "policy",
            "model",
        }:
            raise ValidationError("Claude Code attention config is invalid")
        policy = AttentionPolicy(**attention_raw["policy"])
        model = (
            attention_model_from_config(attention_raw["model"], host_kinds=ATTENTION_KINDS)
            if policy.preattention_enabled
            else None
        )

        limits = ObservationLimits(**config["limits"])
        state = Path(config["state_directory"])
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.state_directory = state
        self.settings = self._claude_code_settings(config["claude_code"], state)

        receipts = ReceiptJournal(state / "claude-code-v2-receipts.jsonl")
        observation = ObservationProvider(
            self.binding,
            limits=limits,
            receipts=receipts,
            persistence_path=state / "claude-code-v2-observations.jsonl",
            event_visibility={
                "message": "history-and-live",
                "reaction": "history-and-live",
                "membership": "live-only",
            },
        )
        scheduler = ConversationOpportunityScheduler(
            f"{self.binding.participant_id}:{self.binding.continuity_scope_id}"
        )
        self.output_secret = self._output_secret(config["transport"])
        transport = MCPDiscordTransport(
            client,
            self.binding.room_id,
            self.binding.participant_id,
            self.binding.actor_id,
            self.output_secret,
        )
        privileged = self._privileged(
            config.get("authorization"),
            observation=observation,
            state=state,
        )

        # Nunchi's own secrets never enter the session's environment, and the
        # gate refuses room text that carries one.
        withheld = {config["transport"]["output_key_env"], *self.settings["withhold_env"]}
        model_config = attention_raw.get("model")
        if isinstance(model_config, Mapping):
            withheld.update(
                value
                for key, value in model_config.items()
                if key.endswith("_env") and isinstance(value, str) and value
            )
        self.withheld_env = frozenset(withheld)
        guard = SecretGuard(
            [os.environ[name] for name in self.withheld_env if name in os.environ]
            + [self.output_secret.decode()]
        )

        self.mod_directory = state / "claude-code-mod"
        self.socket_path = _runtime_directory() / "gate.sock"
        self.session_secret = secrets.token_urlsafe(32)
        self.disallowed_tools = self._disallowed_tools()
        if session is None:
            try:
                executable: str | None = self.executable()
            except ValidationError:
                executable = None
            session = ClaudeCodeSession(
                executable=executable,
                plugin_directory=self.mod_directory,
                working_directory=self.settings["working_directory"],
                environment=self.session_environment(),
                model=self.settings["model"],
                disallowed_tools=self.disallowed_tools,
                session_store=(
                    state / "claude-code-session.json"
                    if self.settings["session_mode"] == "persistent"
                    else None
                ),
            )
        self.session = session
        participant = GatedParticipant(
            profile=profile,
            session=session,
            guard=guard,
            privileged_enabled=privileged is not None,
        )
        session.on_turn_end = participant.turn_ended
        self.participant = participant
        try:
            ack_policy = AckPolicy(**dict(config.get("ack", {})))
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"Claude Code ACK policy is invalid: {exc}") from exc
        host = GatedTurnHost(
            observation=observation,
            participant=participant,
            transport=transport,
            scheduler=scheduler,
            receipts=receipts,
            privileged=privileged,
            ack_policy=ack_policy,
            ack_journal=AckJournal(state / "claude-code-v2-acks.jsonl"),
            participant_timeout_seconds=self.settings["timeout_seconds"],
        )
        attention = AttentionEngine(
            profile=profile,
            model=model,
            policy=policy,
            receipts=receipts,
            ack_policy=ack_policy,
            reaction_capability_provider=host.reaction_capability,
        )
        self.privileged = privileged
        self.pipeline = NunchiV2Pipeline(
            observation=observation,
            attention=attention,
            host=host,
            scheduler=scheduler,
        )
        self.lane = AsyncDeliveryLane(self.pipeline)
        self.client = client
        self.server = GateServer(
            participant,
            socket_path=self.socket_path,
            session_secret=self.session_secret,
        )

    @staticmethod
    def _claude_code_settings(raw: Any, state: Path) -> dict[str, Any]:
        if not isinstance(raw, Mapping):
            raise ValidationError("Claude Code session config must be an object")
        unexpected = set(raw) - _CLAUDE_CODE_KEYS
        if unexpected:
            raise ValidationError(
                "Claude Code session config has unexpected fields: "
                + ", ".join(sorted(unexpected))
            )
        model = raw.get("model")
        if model is not None and (not isinstance(model, str) or not model):
            raise ValidationError("Claude Code model must be a non-empty string")
        timeout = raw.get("timeout_seconds", 300)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(float(timeout))
            or timeout <= 0
        ):
            raise ValidationError("Claude Code timeout must be positive and finite")
        session_mode = raw.get("session_mode", "persistent")
        if session_mode not in ("persistent", "fresh"):
            raise ValidationError("Claude Code session_mode must be persistent or fresh")
        protect = raw.get("protect_nunchi_files", True)
        if not isinstance(protect, bool):
            raise ValidationError("Claude Code protect_nunchi_files must be a boolean")
        withhold = _string_list(raw.get("withhold_env", []), "withhold_env")
        if not all(_ENV_NAME.fullmatch(name) for name in withhold):
            raise ValidationError("Claude Code withhold_env names must be variable names")
        working = (
            Path(raw["working_directory"]).resolve()
            if isinstance(raw.get("working_directory"), str)
            else None
        )
        if protect and working is not None and working.is_relative_to(state.resolve()):
            raise ValidationError(
                "Claude Code working_directory must be outside state_directory, "
                "which the session may not read"
            )
        return {
            "executable": (
                _absolute(raw["executable"], "executable") if "executable" in raw else None
            ),
            "working_directory": (
                _absolute(raw["working_directory"], "working_directory")
                if "working_directory" in raw
                else state.parent / f"{state.name}-workspace"
            ),
            "model": model,
            "timeout_seconds": float(timeout),
            "session_mode": session_mode,
            "disallowed_tools": _string_list(
                raw.get("disallowed_tools", []), "disallowed_tools"
            ),
            "protect_nunchi_files": protect,
            "withhold_env": withhold,
        }

    def executable(self) -> str:
        configured = self.settings["executable"]
        found = str(configured) if configured is not None else shutil.which("claude")
        if found is None or not os.access(found, os.X_OK):
            raise ValidationError("Claude Code executable is not installed on trusted PATH")
        return found

    def _disallowed_tools(self) -> tuple[str, ...]:
        rules = list(self.settings["disallowed_tools"])
        if self.settings["protect_nunchi_files"]:
            state = self.state_directory.resolve()
            # Claude Code spells an absolute path in a rule with a leading //.
            rules.extend((f"Read(/{state}/**)", f"Edit(/{state}/**)"))
        return tuple(dict.fromkeys(rules))

    def session_environment(self) -> dict[str, str]:
        environment = {
            name: value
            for name, value in os.environ.items()
            if name not in self.withheld_env and not name.startswith("NUNCHI_")
        }
        environment[SOCKET_ENV] = str(self.socket_path)
        environment[SESSION_ENV] = self.session_secret
        return environment

    def require_supported_claude_code(self) -> tuple[int, int, int]:
        version = claude_code_version(self.executable())
        if version is None or version < MINIMUM_CLAUDE_CODE:
            raise ValidationError(
                "Claude Code "
                + ".".join(map(str, MINIMUM_CLAUDE_CODE))
                + " or later is required for the Nunchi mod"
                + (f"; found {'.'.join(map(str, version))}" if version else "")
            )
        return version

    def install_mod(self) -> None:
        """Copy the shipped mod into the private folder the session loads."""

        if self.mod_directory.exists():
            shutil.rmtree(self.mod_directory)
        for relative in MOD_FILES:
            target = self.mod_directory / relative
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(MOD_DIRECTORY / relative, target)

    def start(self) -> None:
        """Install the mod and open the gate socket.

        The session starts on the first wake.
        """

        self.install_mod()
        self.socket_path.parent.mkdir(mode=0o700)
        self.server.start()

    def close(self) -> None:
        self.lane.cancel()
        self.server.close()
        stop = getattr(self.session, "stop", None)
        if callable(stop):
            stop()
        try:
            self.socket_path.parent.rmdir()
        except OSError:
            pass

    @staticmethod
    def _output_secret(transport: Mapping[str, Any]) -> bytes:
        if not isinstance(transport, Mapping):
            raise ValidationError("Claude Code transport config must be an object")
        env_name = transport.get("output_key_env")
        if not isinstance(env_name, str) or not env_name:
            raise ValidationError(
                "Claude Code transport output_key_env must be non-empty"
            )
        value = os.environ.get(env_name)
        if value is None or len(value.encode()) < 32:
            raise ValidationError(
                "Claude Code transport output authorization key is absent or "
                f"short in {env_name}"
            )
        return value.encode()

    def _privileged(
        self,
        authorization: Any,
        *,
        observation: ObservationProvider,
        state: Path,
    ) -> AuthorizationCoordinator | None:
        """Wire the shared coordinator, or disable privileged actions entirely.

        Claude Code adds no authorization semantics of its own.  It supplies a
        trusted pinned policy source, private persistence, and the exact native
        executors; every requester, scope, digest, approval, expiry, revocation
        and replay decision stays in the shared coordinator.

        Ordinary conversation is deliberately not in this inventory.  Speaking
        in the room is the participant's normal path and is guarded by
        attention and the host commit point, not by an operator grant.
        """
        if authorization is None:
            return None
        if not isinstance(authorization, Mapping) or set(authorization) - {
            "policy_path",
            "policy_sha256",
            "workspace_root",
        } or not {"policy_path", "policy_sha256"} <= set(authorization):
            raise ValidationError(
                "Claude Code authorization config has an invalid shape"
            )
        return AuthorizationCoordinator(
            observation=observation,
            policy_source=PinnedFilePolicySource(
                authorization["policy_path"],
                expected_sha256=authorization["policy_sha256"],
            ),
            journal=AuthorizationJournal(state / "claude-code-v2-authorization.jsonl"),
            executors=self._executors(authorization.get("workspace_root")),
        )

    @staticmethod
    def _executors(workspace_root: Any) -> dict[str, Any]:
        """Exactly the native privileged effects this surface can perform.

        Every entry is an inventoried effect.  A capability with no entry here
        has no executor and therefore no possible effect: an unconfigured
        workspace root leaves `workspace.file.write` explicitly disabled rather
        than defaulting to some ambient directory.
        """
        if workspace_root is None:
            return {}
        if not isinstance(workspace_root, str) or not workspace_root:
            raise ValidationError(
                "Claude Code authorization workspace_root must be a non-empty path"
            )
        root = Path(workspace_root)
        if not root.is_absolute():
            raise ValidationError(
                "Claude Code authorization workspace_root must be absolute"
            )
        # Detection alone cannot stop a concurrent local attacker from renaming
        # directories inside the workspace mid-write; it can only refuse to
        # attest the result.  Requiring the root to be private to this runtime
        # removes that principal instead of racing it.
        try:
            root_stat = root.stat()
        except OSError as exc:
            raise ValidationError(
                f"Claude Code authorization workspace_root is unusable: {exc}"
            ) from exc
        if not stat.S_ISDIR(root_stat.st_mode):
            raise ValidationError(
                "Claude Code authorization workspace_root must be a directory"
            )
        if root_stat.st_uid != os.getuid():
            raise ValidationError(
                "Claude Code authorization workspace_root must be owned by the "
                "runtime user"
            )
        if root_stat.st_mode & 0o077:
            raise ValidationError(
                "Claude Code authorization workspace_root must not be writable "
                "or readable by group or other"
            )

        def workspace_file_write(
            operation: Mapping[str, Any],
            idempotency_key: str | None,
        ) -> TransportResult:
            if set(operation) != {"path", "content"} or not all(
                isinstance(operation[name], str) for name in ("path", "content")
            ):
                return TransportResult(
                    "unavailable",
                    "privileged workspace write operation has an invalid shape",
                )
            relative = operation["path"]
            # Cheap syntactic rejections first.  Real confinement is enforced
            # by the rooted directory handles in `_write_confined`, not here:
            # these checks only reject obviously bad input early.
            if (
                not relative
                or relative.startswith("/")
                or "\x00" in relative
                or PurePosixPath(relative).is_absolute()
                or any(
                    part in ("", ".", "..")
                    for part in PurePosixPath(relative).parts
                )
                or not PurePosixPath(relative).parts
            ):
                return TransportResult(
                    "failed", "privileged workspace path escapes the workspace"
                )
            try:
                digest = _write_confined(root, relative, operation["content"].encode("utf-8"))
            except ConfinedPathDrift:
                # The bytes are written and confined, but the named resource
                # changed: neither a clean success nor a clean failure.
                return TransportResult(
                    "unknown",
                    "privileged workspace resource changed during the write",
                )
            except (NotADirectoryError, IsADirectoryError, FileExistsError, ValueError):
                return TransportResult(
                    "failed", "privileged workspace path escapes the workspace"
                )
            except OSError as exc:
                # ELOOP / ENOTDIR from O_NOFOLLOW mean a component was a
                # symbolic link: refused, not retried.
                if exc.errno in (errno.ELOOP, errno.ENOTDIR, errno.ENOENT):
                    return TransportResult(
                        "failed",
                        "privileged workspace path traverses a symbolic link",
                    )
                return TransportResult(
                    "unknown", "privileged workspace write was not attested"
                )
            return TransportResult("sent", f"workspace-file:{digest}")

        return {"workspace.file.write": workspace_file_write}

    # -- shared Discord consumer obligations --------------------------------

    def handle(self, params: Mapping[str, Any]) -> DeliveryOutcome:
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
            raise ValidationError(
                "shared Discord notification has an invalid V2 shape"
            )
        if params["schema_version"] != 2:
            raise ValidationError("shared Discord notification is not V2")
        if not isinstance(params["continuity_gap"], bool):
            raise ValidationError("shared Discord continuity_gap must be a boolean")
        if params["target_participant_id"] != self.binding.participant_id:
            raise ValidationError(
                "shared Discord notification targets another participant"
            )
        if params["transport_self_actor_id"] != self.binding.actor_id:
            raise ValidationError(
                "authenticated Discord self differs from exact binding"
            )
        if str(params["room_id"]) != self.binding.room_id:
            raise ValidationError("shared Discord notification targets another room")
        if params["continuity_gap"]:
            if params["event"] is not None or params["actors"] != {}:
                raise ValidationError(
                    "Discord gap notification cannot fabricate event facts"
                )
            self.lane.cancel()
            observed = self.pipeline.observation.mark_continuity_gap(
                delivery_id=str(params["delivery_id"]),
                detail="shared Discord transport declared a bounded queue gap",
            )
            return DeliveryOutcome(observed, (), False)
        event = (
            validate_canonical_event(params["event"])
            if params["event"] is not None
            else None
        )
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
            raise RuntimeError(
                "shared Discord registration returned an invalid result"
            )
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
            raise RuntimeError(
                "shared Discord registration attestation binding differs"
            )

    def transport_interrupted(self) -> None:
        """Invalidate active work and record uncertainty before reconnect."""
        self.lane.cancel()
        self.pipeline.observation.mark_continuity_gap(
            delivery_id=f"discord:claude-code-stream-gap:{time.time_ns()}",
            detail="shared Discord notification stream continuity is uncertain",
        )

    def probe(self) -> dict[str, Any]:
        try:
            executable: str | None = self.executable()
        except ValidationError:
            executable = None
        version = claude_code_version(executable) if executable else None
        return {
            "product": "nunchi",
            "product_version": __version__,
            "generation": 2,
            "surface": SURFACE,
            "participant_id": self.binding.participant_id,
            "actor_id": self.binding.actor_id,
            "room_id": self.binding.room_id,
            "participant": "claude-code-session",
            "claude_code_executable": executable,
            "claude_code_version": ".".join(map(str, version)) if version else None,
            "minimum_claude_code_version": ".".join(map(str, MINIMUM_CLAUDE_CODE)),
            "claude_code_supported": version is not None and version >= MINIMUM_CLAUDE_CODE,
            "mod_directory": str(MOD_DIRECTORY),
            "mod_version": mod_version(),
            "session_mode": self.settings["session_mode"],
            "persistent_session": self.settings["session_mode"] == "persistent",
            "working_directory": str(self.settings["working_directory"]),
            "native_tools": "claude-code-permission-rules",
            "disallowed_tools": list(self.disallowed_tools),
            "room_tools": [
                full_tool_name(role) for role in self.participant.registered_roles
            ],
            "shared_discord_transport": True,
            "send_time_social_judgment": False,
            "privileged_actions_enabled": self.privileged is not None,
            "v1_fallback": False,
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nunchi-claude-code-room-runner")
    parser.add_argument("--config")
    parser.add_argument(
        "--config-sha256",
        default=os.environ.get("NUNCHI_CLAUDE_CODE_CONFIG_SHA256"),
    )
    parser.add_argument("--probe", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if not args.config:
            if args.probe:
                print(
                    _canonical_json(
                        {
                            "product": "nunchi",
                            "product_version": __version__,
                            "generation": 2,
                            "surface": SURFACE,
                            "configured": False,
                            "mod_version": mod_version(),
                            "v1_fallback": False,
                        }
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
            raise ValidationError("Claude Code shared transport config is invalid")
        client = StreamableMCPClient(
            str(transport["url"]),
            timeout_seconds=float(transport["timeout_seconds"]),
        )
        runtime = ClaudeCodeRoomRuntime(config, client)
        if args.probe:
            probe = runtime.probe()
            probe["configured"] = True
            print(_canonical_json(probe))
            return 0
        runtime.require_supported_claude_code()
        runtime.start()
        try:
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
                    print(
                        "Claude Code shared transport reconnect after operational error",
                        file=sys.stderr,
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, 30)
        finally:
            runtime.close()
    except (NunchiError, ValueError) as exc:
        print(f"Claude Code V2 runner error: {exc}", file=sys.stderr)
        return 3 if isinstance(exc, ValidationError) else 1


if __name__ == "__main__":
    raise SystemExit(main())
