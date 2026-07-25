"""Generate a pinned, profile-scoped Hermes V2 operator bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Sequence


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_private(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        written = os.write(fd, payload)
        if written != len(payload):
            raise OSError(f"short write ({written}/{len(payload)} bytes)")
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    os.chmod(path, 0o600)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _canonical_actor(platform: str, actor_id: str) -> str:
    prefix = f"{platform}:actor:"
    if actor_id.startswith(prefix):
        return actor_id
    return prefix + actor_id


def create_bundle(args: argparse.Namespace) -> dict[str, Any]:
    output = Path(args.output_dir).expanduser().resolve()
    instructions_path = Path(args.instructions_file).expanduser()
    instructions = instructions_path.read_text(encoding="utf-8")
    if not instructions.strip():
        raise ValueError("participant instructions must not be empty")
    actor_id = _canonical_actor(args.platform, args.actor_id)
    names = tuple(dict.fromkeys(args.name or [args.participant_id]))
    profile = {
        "profile_id": args.profile_id,
        "participant_id": args.participant_id,
        "actor_id": actor_id,
        "instructions": instructions,
        "provenance": args.provenance,
    }
    profile_path = output / "participant-profile.json"
    _write_private(profile_path, _json_bytes(profile))

    authorization = None
    if args.authorization_policy:
        policy_path = Path(args.authorization_policy).expanduser().resolve()
        authorization = {
            "policy": {"path": str(policy_path), "sha256": _digest(policy_path)},
            "enabled_capabilities": list(args.enable_capability or []),
        }
    elif args.enable_capability:
        raise ValueError("enabled capabilities require --authorization-policy")

    recovery_evidence = None
    if args.enable_suppression:
        if not args.suppression_recovery_evidence:
            raise ValueError("suppression requires pinned recovery evidence")
        evidence_path = Path(args.suppression_recovery_evidence).expanduser().resolve()
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("suppression recovery evidence must be valid JSON") from exc
        if not isinstance(evidence, dict):
            raise ValueError("suppression recovery evidence must be a JSON object")
        if evidence.get("surface") != args.platform or evidence.get("later_hearing") != "verified":
            raise ValueError("suppression recovery evidence does not verify this platform")
        recovery_evidence = {"path": str(evidence_path), "sha256": _digest(evidence_path)}

    config = {
        "schema_version": 2,
        "hermes_profile": args.hermes_profile,
        "state_root": str(Path(args.state_root).expanduser().resolve()),
        "rooms": [
            {
                "binding": {
                    "participant_id": args.participant_id,
                    "actor_id": actor_id,
                    "platform": args.platform,
                    "room_id": args.room_id,
                    "continuity_scope_id": args.continuity_scope_id
                    or f"{args.platform}:room:{args.room_id}",
                    "names": list(names),
                    "role": args.role,
                    "description": args.description,
                    "room_name": args.room_name,
                    "room_kind": args.room_kind,
                    "provenance": args.provenance,
                },
                "profile": {"path": str(profile_path), "sha256": _digest(profile_path)},
                "attention": {
                    "recovery_evidence": recovery_evidence,
                    "policy": {
                        "preattention_enabled": not args.disable_attention,
                        "suppression_enabled": args.enable_suppression,
                        "suppression_recovery_verified": args.enable_suppression,
                        "margin_status": "active",
                        "effective_margin": args.effective_margin,
                        "margin_source": args.provenance,
                        "provenance": args.provenance,
                        "timeout_seconds": args.attention_timeout,
                        "error_action": args.attention_error_action,
                    }
                },
                "participant": {
                    "timeout_seconds": args.participant_timeout,
                    "max_expansions": args.max_expansions,
                },
                "limits": {},
                "authorization": authorization,
            }
        ],
    }
    config_path = output / "hermes-v2-config.json"
    _write_private(config_path, _json_bytes(config))
    token = re.sub(r"[^A-Za-z0-9]", "_", args.hermes_profile).upper()
    return {
        "generation": 2,
        "hermes_profile": args.hermes_profile,
        "participant_profile": {"path": str(profile_path), "sha256": _digest(profile_path)},
        "config": {"path": str(config_path), "sha256": _digest(config_path)},
        "environment": {
            f"NUNCHI_HERMES_V2_CONFIG_{token}": str(config_path),
            f"NUNCHI_HERMES_V2_CONFIG_SHA256_{token}": _digest(config_path),
        },
    }


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        prog="nunchi-hermes-v2-config",
        description="Create a private, digest-pinned Nunchi V2 Hermes profile/config bundle.",
    )
    command.add_argument("--hermes-profile", required=True)
    command.add_argument("--platform", choices=("discord", "telegram"), required=True)
    command.add_argument("--room-id", required=True, help="Canonical bound room; Telegram topics use CHAT_ID:topic:TOPIC_ID")
    command.add_argument("--actor-id", required=True, help="Exact native participant/bot actor ID")
    command.add_argument("--participant-id", required=True)
    command.add_argument("--profile-id", required=True)
    command.add_argument("--instructions-file", required=True)
    command.add_argument("--output-dir", required=True)
    command.add_argument("--state-root", required=True)
    command.add_argument("--continuity-scope-id")
    command.add_argument("--name", action="append", default=[])
    command.add_argument("--role", default="participant")
    command.add_argument("--description", default="Hermes Nunchi V2 participant")
    command.add_argument("--room-name")
    command.add_argument("--room-kind", choices=("group", "direct", "unknown"), default="group")
    command.add_argument("--provenance", default="trusted:hermes-v2-operator-config@1")
    command.add_argument("--attention-timeout", type=float, default=30.0)
    command.add_argument("--participant-timeout", type=float, default=300.0)
    command.add_argument("--attention-error-action", choices=("WAKE", "NO_WAKE"), default="WAKE")
    command.add_argument("--effective-margin", type=float, default=0.12)
    command.add_argument("--max-expansions", type=int, default=3)

    command.add_argument("--disable-attention", action="store_true")
    command.add_argument("--enable-suppression", action="store_true")
    command.add_argument("--suppression-recovery-evidence")
    command.add_argument("--authorization-policy")
    command.add_argument("--enable-capability", action="append", default=[])
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = create_bundle(args)
    except (OSError, ValueError) as exc:
        print(f"nunchi-hermes-v2-config: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
