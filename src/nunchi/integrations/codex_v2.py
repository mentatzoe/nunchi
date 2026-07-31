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
import shutil
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
        allowed = {"model", "timeout_seconds", "session_mode"}
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
        self.session_mode = str(config.get("session_mode", "persistent"))
        if self.session_mode not in ("persistent", "fresh"):
            raise ValidationError("Codex session_mode must be persistent or fresh")
        self.session_path = state_root / "codex-v2-session.json"
        self.output_schema_path = state_root / "codex-v2-action.schema.json"
        self._write_output_schema()
        behavior = {
            "profile_sha256": self.profile.sha256,
            "participant_id": self.binding.participant_id,
            "actor_id": self.binding.actor_id,
            "room_id": self.binding.room_id,
            "continuity_scope_id": self.binding.continuity_scope_id,
            "model": self.model,
            "disabled_features": list(_DISABLED_CODEX_FEATURES),
            "sandbox": "read-only",
        }
        self.behavior_sha256 = hashlib.sha256(
            json.dumps(
                behavior,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        self._lock = threading.Lock()

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
        payload = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
        temporary = self.output_schema_path.with_suffix(".tmp")
        fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        try:
            if os.write(fd, payload) != len(payload):
                raise OSError("short Codex output-schema write")
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, self.output_schema_path)
        directory_fd = os.open(self.output_schema_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _load_session(self) -> str | None:
        if self.session_mode == "fresh" or not self.session_path.exists():
            return None
        try:
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
            or not isinstance(state["thread_id"], str)
            or not _THREAD_ID.fullmatch(state["thread_id"])
        ):
            raise RuntimeError("Codex session state binding is invalid")
        return state["thread_id"]

    def _save_session(self, thread_id: str) -> None:
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.session_path.with_suffix(".tmp")
        payload = json.dumps(
            {
                "schema_version": 2,
                "thread_id": thread_id,
                "participant_id": self.binding.participant_id,
                "actor_id": self.binding.actor_id,
                "room_id": self.binding.room_id,
                "continuity_scope_id": self.binding.continuity_scope_id,
                "profile_sha256": self.profile.sha256,
                "behavior_sha256": self.behavior_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        try:
            if os.write(fd, payload) != len(payload):
                raise OSError("short Codex session-state write")
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, self.session_path)
        directory_fd = os.open(self.session_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

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
            active_thread = self._load_session()
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
                    env={
                        key: os.environ[key]
                        for key in (
                            "CODEX_HOME",
                            "HOME",
                            "LANG",
                            "LC_ALL",
                            "LOGNAME",
                            "PATH",
                            "TMPDIR",
                            "USER",
                        )
                        if key in os.environ
                    },
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                deadline = time.monotonic() + self.timeout_seconds
                while process.poll() is None:
                    if cancel.is_set() or time.monotonic() >= deadline:
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
                if self.session_mode == "persistent":
                    if active_thread is None:
                        raise RuntimeError(
                            "Codex did not report a persistent task ID"
                        )
                    self._save_session(active_thread)
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
        receipts = ReceiptJournal(state / "codex-v2-receipts.jsonl")
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
        participant = CodexParticipant(
            profile=profile,
            config=config["codex"],
            binding=self.binding,
            state_directory=state,
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
        return {
            "product": "nunchi",
            "product_version": __version__,
            "generation": 2,
            "surface": "codex",
            "participant_id": self.binding.participant_id,
            "actor_id": self.binding.actor_id,
            "room_id": self.binding.room_id,
            "persistent_session": True,
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
