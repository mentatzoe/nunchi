from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any


def policy_document() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "source": "operator:local-v2",
        "attention": {
            "participant_id": "vigil",
            "preattention_enabled": True,
            "social_suppression_enabled": True,
            "attention_max_events": 50,
            "attention_max_bytes": 65536,
            "participant_max_events": 50,
            "participant_max_bytes": 65536,
            "fetch_max_events": 20,
            "fetch_max_bytes": 32768,
            "error_action": "WAKE",
            "transition_defer_margin": 0.12,
            "transition_defer_margin_source": "operator:initial-margin",
        },
        "recoverability": {
            "participant_id": "vigil",
            "continuity_scope_id": "discord:room:42",
            "eligible": True,
        },
        "classifier": {
            "provider": "openai-compatible",
            "endpoint": "https://provider.invalid/v1/chat/completions",
            "model": "participant-shaped-model",
            "api_key": "do-not-project-this-secret",
            "timeout_seconds": 30,
            "max_retries": 2,
        },
        "authorization": {
            "decision_ttl_seconds": 30,
            "approval_ttl_seconds": 300,
            "grants": [
                {
                    "grant_id": "grant-direct-write",
                    "actor_id": "discord-user-1001",
                    "capability": "workspace.file.write",
                    "scope": {
                        "platform": "discord",
                        "room_id": "room-42",
                        "participant_id": "vigil",
                        "resource": {
                            "kind": "workspace-file",
                            "id": "docs/release.md",
                        },
                    },
                    "impact": "mutation",
                    "execution": "direct",
                    "status": "active",
                    "expires_at": "2030-01-01T00:00:00Z",
                },
                {
                    "grant_id": "grant-approved-delete",
                    "actor_id": "discord-user-1002",
                    "capability": "workspace.file.delete",
                    "scope": {
                        "platform": "discord",
                        "room_id": "room-42",
                        "participant_id": "vigil",
                        "resource": {
                            "kind": "workspace-file",
                            "id": "tmp/stale.txt",
                        },
                    },
                    "impact": "destructive",
                    "execution": "approval",
                    "status": "active",
                    "allowed_approver_actor_ids": ["discord-user-admin"],
                },
            ],
        },
        "receipt_sink": {
            "type": "exclusive-json-file",
            "directory": "/tmp",
            "source": "operator:local-receipts",
        },
    }


def write_policy(directory: str | os.PathLike[str], document: dict[str, Any] | None = None) -> Path:
    path = Path(directory) / "policy.json"
    path.write_text(
        json.dumps(document if document is not None else policy_document()),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def clone_policy() -> dict[str, Any]:
    return copy.deepcopy(policy_document())
