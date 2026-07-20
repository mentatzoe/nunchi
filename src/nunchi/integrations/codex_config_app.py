"""Secret-redacted MCP Apps surface for trusted Codex V2 operation."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from importlib import resources
from pathlib import Path
from typing import Any

from ..classifiers import attention_v2_prompt_digest
from ..policy import (
    OperatorPolicy,
    PolicyLoadError,
    load_operator_policy,
    update_operator_attention_controls,
)
from .codex_session_v2 import (
    CodexSessionStateError,
    load_codex_session,
    reset_codex_session,
)


TEMPLATE_URI = "ui://nunchi/codex-v2-config.html"
MAX_RECEIPT_BYTES = 1024 * 1024
MAX_RECEIPT_FILES = 10000


class ConfigAppError(ValueError):
    pass


def _policy_snapshot(policy: OperatorPolicy) -> dict[str, Any]:
    attention = policy.attention
    classifier = policy.classifier
    authorization = policy.authorization
    return {
        "schema_version": policy.schema_version,
        "source": policy.source_label,
        "provenance": policy.provenance,
        "identity": {
            "participant_id": attention.participant_id,
            "continuity_scope_id": policy.recoverability.continuity_scope_id,
        },
        "attention": {
            "preattention_enabled": attention.preattention_enabled,
            "social_suppression_enabled": attention.social_suppression_enabled,
            "error_action": attention.error_action,
            "transition_defer_margin": attention.transition_defer_margin,
            "transition_defer_margin_source": (
                attention.transition_defer_margin_source
            ),
            "budgets": {
                "attention_max_events": attention.attention_max_events,
                "attention_max_bytes": attention.attention_max_bytes,
                "participant_max_events": attention.participant_max_events,
                "participant_max_bytes": attention.participant_max_bytes,
                "fetch_max_events": attention.fetch_max_events,
                "fetch_max_bytes": attention.fetch_max_bytes,
            },
        },
        "recoverability": {"eligible": policy.recoverability.eligible},
        "classifier": {
            "provider": classifier.provider,
            "model": classifier.model,
            "timeout_seconds": classifier.timeout_seconds,
            "max_retries": classifier.max_retries,
            "credential_configured": classifier.api_key is not None,
            "prompt_digest": attention_v2_prompt_digest(),
        },
        "authorization": {
            "decision_ttl_seconds": authorization.decision_ttl_seconds,
            "approval_ttl_seconds": authorization.approval_ttl_seconds,
            "grants": [
                {
                    "grant_id": grant.grant_id,
                    "actor_id": grant.actor_id,
                    "capability": grant.capability,
                    "scope": grant.scope.to_contract(),
                    "impact": grant.impact,
                    "execution": grant.execution,
                    "status": grant.status,
                    "allowed_approver_actor_ids": list(
                        grant.allowed_approver_actor_ids
                    ),
                    "expires_at": (
                        grant.expires_at.isoformat()
                        if grant.expires_at is not None
                        else None
                    ),
                }
                for grant in authorization.grants
            ],
        },
        "receipt_sink": {
            "type": policy.receipt_sink.type,
            "configured": True,
        },
    }


def _read_receipt(path: Path) -> tuple[int, dict[str, Any]] | None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
            or metadata.st_size > MAX_RECEIPT_BYTES
        ):
            return None
        raw = os.read(descriptor, MAX_RECEIPT_BYTES + 1)
        if len(raw) > MAX_RECEIPT_BYTES:
            return None
        try:
            value = json.loads(
                raw,
                object_pairs_hook=lambda pairs: _unique_object(pairs),
                parse_constant=lambda _value: (_ for _ in ()).throw(
                    ValueError("non-finite")
                ),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return None
        if not isinstance(value, dict):
            return None
        return metadata.st_mtime_ns, value
    finally:
        os.close(descriptor)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _tail_receipts(policy: OperatorPolicy, limit: int) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ConfigAppError("receipt limit must be an integer")
    bounded_limit = max(1, min(limit, 100))
    directory = Path(policy.receipt_sink.directory)
    try:
        metadata = directory.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise OSError
        paths = []
        with os.scandir(directory) as entries:
            for index, entry in enumerate(entries):
                if index >= MAX_RECEIPT_FILES:
                    break
                if entry.name.endswith(".jsonl"):
                    paths.append(directory / entry.name)
    except OSError:
        return {"available": False, "receipts": [], "limit": bounded_limit}
    records = [record for path in paths if (record := _read_receipt(path)) is not None]
    records.sort(key=lambda item: item[0], reverse=True)
    return {
        "available": True,
        "receipts": [record for _, record in records[:bounded_limit]],
        "limit": bounded_limit,
        "scanned": len(paths),
        "scan_truncated": len(paths) >= MAX_RECEIPT_FILES,
    }


class ConfigAppService:
    """Filesystem-only backend; no room content or platform token is accepted."""

    def __init__(
        self,
        *,
        policy_path: Path,
        session_path: Path,
        allow_policy_write: bool = False,
        allow_session_reset: bool = False,
    ) -> None:
        if (
            not policy_path.is_absolute()
            or not session_path.is_absolute()
            or not isinstance(allow_policy_write, bool)
            or not isinstance(allow_session_reset, bool)
        ):
            raise ConfigAppError("policy and session paths must be absolute")
        self.policy_path = policy_path
        self.session_path = session_path
        self.allow_policy_write = allow_policy_write
        self.allow_session_reset = allow_session_reset

    def _policy(self) -> OperatorPolicy:
        return load_operator_policy(self.policy_path)

    def _session_health(self) -> dict[str, Any]:
        try:
            state = load_codex_session(self.session_path)
        except CodexSessionStateError:
            return {"active": False, "state": "invalid"}
        if state is None:
            return {"active": False, "state": "absent"}
        return {
            "active": True,
            "state": "valid",
            "created_at": state["created_at"],
            "updated_at": state["updated_at"],
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "api_version": 2,
            "policy": _policy_snapshot(self._policy()),
            "health": {"codex_session": self._session_health()},
            "capabilities": {
                "policy_write": self.allow_policy_write,
                "session_reset": self.allow_session_reset,
            },
        }

    def update_attention(
        self,
        patch: dict[str, Any],
        *,
        expected_provenance: str,
    ) -> dict[str, Any]:
        if not self.allow_policy_write:
            return {"ok": False, "error": "policy-write-disabled"}
        try:
            update_operator_attention_controls(
                self.policy_path,
                patch,
                expected_provenance=expected_provenance,
            )
        except PolicyLoadError as exc:
            return {"ok": False, "error": exc.code}
        return {"ok": True, "snapshot": self.snapshot()}

    def receipts(self, *, limit: int = 50) -> dict[str, Any]:
        return _tail_receipts(self._policy(), limit)

    def reset_session(self) -> dict[str, Any]:
        if not self.allow_session_reset:
            return {"ok": False, "error": "session-reset-disabled"}
        try:
            reset_codex_session(self.session_path)
        except CodexSessionStateError:
            return {"ok": False, "error": "session-reset-failed"}
        return {"ok": True, "snapshot": self.snapshot()}


def load_ui_html() -> str:
    return (
        resources.files("nunchi.integrations")
        .joinpath("codex_config_ui.html")
        .read_text(encoding="utf-8")
    )


def _tool_result(types: Any, structured: dict[str, Any], message: str) -> Any:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=message)],
        structuredContent=structured,
    )


def build_mcp_server(service: ConfigAppService) -> Any:
    """Build lazily so package import and ``--help`` do not require MCP."""
    from mcp import types
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(
        "nunchi-codex-v2-config",
        instructions="Inspect trusted Nunchi V2 policy and operating evidence.",
    )

    @server.resource(
        TEMPLATE_URI,
        name="Nunchi V2 Codex configuration",
        description="Trusted V2 attention controls, identity, grants, and receipts.",
        mime_type="text/html;profile=mcp-app",
        meta={"ui": {"prefersBorder": False, "csp": {"connectDomains": [], "resourceDomains": []}}},
    )
    def nunchi_config_ui() -> str:
        return load_ui_html()

    @server.tool(
        name="open_nunchi_config",
        title="Open Nunchi V2 configuration",
        description="Inspect secret-redacted V2 policy and session health.",
        annotations=types.ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
        meta={"ui": {"resourceUri": TEMPLATE_URI, "visibility": ["model", "app"]}, "openai/outputTemplate": TEMPLATE_URI},
    )
    def open_nunchi_config():
        snapshot = service.snapshot()
        return _tool_result(types, snapshot, "Opened Nunchi V2 configuration.")

    @server.tool(
        name="get_nunchi_config",
        title="Refresh Nunchi V2 configuration",
        description="Read current secret-redacted V2 policy and session health.",
        annotations=types.ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
        meta={"ui": {"visibility": ["model", "app"]}},
    )
    def get_nunchi_config():
        snapshot = service.snapshot()
        return _tool_result(types, snapshot, "Read Nunchi V2 configuration.")

    @server.tool(
        name="update_nunchi_attention",
        title="Save Nunchi V2 attention controls",
        description="App-only optimistic update of four non-secret attention controls.",
        annotations=types.ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
        meta={"ui": {"visibility": ["app"]}},
    )
    def update_nunchi_attention(patch: dict[str, Any], expected_provenance: str):
        result = service.update_attention(
            patch,
            expected_provenance=expected_provenance,
        )
        return _tool_result(types, result, "Updated Nunchi attention controls." if result["ok"] else "Nunchi attention controls were not changed.")

    @server.tool(
        name="reset_nunchi_session",
        title="Start a new Codex V2 session",
        description="App-only removal of the owner-only persistent Codex thread binding.",
        annotations=types.ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False),
        meta={"ui": {"visibility": ["app"]}},
    )
    def reset_nunchi_session_tool():
        result = service.reset_session()
        return _tool_result(types, result, "Reset Codex V2 session." if result["ok"] else "Codex V2 session was not reset.")

    @server.tool(
        name="get_nunchi_receipts",
        title="Read Nunchi V2 receipts",
        description="Read bounded immutable V2 receipt records, newest first.",
        annotations=types.ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
        meta={"ui": {"visibility": ["model", "app"]}},
    )
    def get_nunchi_receipts(limit: int = 50):
        result = service.receipts(limit=limit)
        return _tool_result(types, result, f"Read {len(result['receipts'])} V2 receipt(s).")

    return server


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nunchi-codex-config-app",
        description="Inspect and explicitly operate one trusted Nunchi V2 policy.",
    )
    parser.add_argument("--policy", type=Path, default=os.environ.get("NUNCHI_V2_POLICY"))
    parser.add_argument("--session", type=Path, default=os.environ.get("NUNCHI_CODEX_SESSION_STATE"))
    parser.add_argument("--allow-policy-write", action="store_true")
    parser.add_argument("--allow-session-reset", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv if argv is not None else sys.argv[1:])
    if args.policy is None or args.session is None:
        print("nunchi-codex-config-app: --policy and --session are required", file=sys.stderr)
        return 2
    try:
        service = ConfigAppService(
            policy_path=args.policy,
            session_path=args.session,
            allow_policy_write=args.allow_policy_write,
            allow_session_reset=args.allow_session_reset,
        )
        service.snapshot()
    except (ConfigAppError, PolicyLoadError):
        print("nunchi-codex-config-app: V2 configuration is invalid", file=sys.stderr)
        return 2
    try:
        server = build_mcp_server(service)
    except ImportError:
        print("nunchi-codex-config-app: install the 'mcp-discord' extra", file=sys.stderr)
        return 2
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
