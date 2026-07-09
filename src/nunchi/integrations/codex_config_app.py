"""MCP Apps configuration surface for the Codex room integration."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Mapping
from importlib import resources
from pathlib import Path
from typing import Any

from .codex_room_runner import RunnerConfig
from .codex_runtime_state import (
    RuntimeStateError,
    apply_patch,
    configured_channel_ids,
    load_state,
    resolve_channel_policy,
    save_state,
    tail_receipts,
)


TEMPLATE_URI = "ui://nunchi/codex-config.html"
DEFAULT_RUNNER_CONFIG = Path(".nunchi/codex-runner.toml")


def default_config_argv(environ: Mapping[str, str]) -> list[str]:
    """Use the conventional runner config when no explicit path is configured."""
    if environ.get("NUNCHI_RUNNER_CONFIG"):
        return []
    home = Path(environ["HOME"]).expanduser() if environ.get("HOME") else Path.home()
    candidate = home / DEFAULT_RUNNER_CONFIG
    return ["--config", str(candidate)] if candidate.is_file() else []


def _binary_status(value: str | None) -> dict[str, Any]:
    if not value:
        return {"configured": False, "available": False}
    has_separator = os.sep in value or (os.altsep is not None and os.altsep in value)
    available = Path(value).is_file() if has_separator else shutil.which(value) is not None
    return {"configured": True, "available": available}


class ConfigAppService:
    """Pure filesystem/config backend shared by MCP handlers and tests."""

    def __init__(
        self,
        *,
        environ: Mapping[str, str] | None = None,
        config: RunnerConfig | None = None,
    ) -> None:
        self.environ = dict(os.environ if environ is None else environ)
        self.config = config or RunnerConfig.from_sources(argv=[], environ=self.environ)
        if self.config.state_path is None:
            raise RuntimeStateError("Codex runtime state path is not configured")

    @property
    def state_path(self) -> Path:
        assert self.config.state_path is not None
        return self.config.state_path

    def _resolved_model(self, state: Mapping[str, Any]) -> dict[str, Any]:
        global_state = state.get("global") if isinstance(state.get("global"), Mapping) else {}
        if global_state.get("model"):
            return {"value": global_state["model"], "source": "runtime-state"}
        if self.environ.get("NUNCHI_RUNNER_MODEL"):
            return {"value": self.environ["NUNCHI_RUNNER_MODEL"], "source": "environment"}
        if self.environ.get("NUNCHI_CLASSIFIER_MODEL"):
            return {"value": self.environ["NUNCHI_CLASSIFIER_MODEL"], "source": "environment"}
        if self.config.model:
            return {"value": self.config.model, "source": "runner-baseline"}
        return {"value": None, "source": None}

    def snapshot(self) -> dict[str, Any]:
        state = load_state(self.state_path)
        channel_ids = configured_channel_ids(self.config.channels, state)
        effective: dict[str, Any] = {}
        for channel_id in channel_ids:
            effective[channel_id] = resolve_channel_policy(
                self.config.runtime_baseline(),
                state,
                channel_id,
                self.config.channels,
            )

        receipts = tail_receipts(self.config.log_path, limit=1)
        last_receipt = receipts[0] if receipts else None
        baseline = self.config.runtime_baseline()
        baseline["channels"] = sorted(self.config.channels)
        baseline["channel_mode"] = "finite" if self.config.channels else "all"
        return {
            "api_version": 1,
            "baseline": baseline,
            "overrides": state,
            "effective": effective,
            "resolved_model": self._resolved_model(state),
            "health": {
                "transport_url": self.config.transport_url,
                "gate_binary": _binary_status(self.config.channel_bin),
                "codex_binary": _binary_status(self.config.codex_bin),
                "last_receipt_at": last_receipt.get("ts") if last_receipt else None,
                "last_receipt_action": last_receipt.get("action") if last_receipt else None,
            },
        }

    def update(self, patch: Mapping[str, Any]) -> dict[str, Any]:
        current = load_state(self.state_path)
        updated, rejected = apply_patch(current, patch)
        if rejected:
            return {
                "ok": False,
                "rejected_keys": rejected,
                "error": "runtime state was not changed because the patch contained unsupported keys",
                "snapshot": self.snapshot(),
            }
        saved = save_state(self.state_path, updated, updated_by="codex-app")
        return {
            "ok": True,
            "rejected_keys": [],
            "applied_state": saved,
            "snapshot": self.snapshot(),
        }

    def receipts(self, *, limit: int = 50) -> dict[str, Any]:
        return {
            "receipts": tail_receipts(self.config.log_path, limit=limit),
            "limit": max(1, min(int(limit), 500)),
        }


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


def build_mcp_server(service: ConfigAppService | None = None) -> Any:
    """Build lazily so importing the package does not require the MCP extra."""
    from mcp import types
    from mcp.server.fastmcp import FastMCP

    backend = service or ConfigAppService()
    server = FastMCP(
        "nunchi-codex-config",
        instructions="Inspect and update Nunchi Codex room presence settings.",
    )

    @server.resource(
        TEMPLATE_URI,
        name="Nunchi Codex configuration",
        description="Interactive room-presence settings and receipt viewer.",
        mime_type="text/html;profile=mcp-app",
        meta={
            "ui": {
                "prefersBorder": False,
                "csp": {"connectDomains": [], "resourceDomains": []},
            },
            "openai/widgetDescription": "Nunchi Codex room configuration and receipts.",
        },
    )
    def nunchi_config_ui() -> str:
        return load_ui_html()

    @server.tool(
        name="open_nunchi_config",
        title="Open Nunchi configuration",
        description="Open the interactive Nunchi Codex room settings and receipts panel.",
        annotations=types.ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
        meta={
            "ui": {"resourceUri": TEMPLATE_URI, "visibility": ["model", "app"]},
            "openai/outputTemplate": TEMPLATE_URI,
            "openai/toolInvocation/invoking": "Opening Nunchi settings...",
            "openai/toolInvocation/invoked": "Nunchi settings opened.",
        },
    )
    def open_nunchi_config():
        snapshot = backend.snapshot()
        return _tool_result(types, snapshot, "Opened Nunchi Codex configuration.")

    @server.tool(
        name="get_nunchi_config",
        title="Refresh Nunchi configuration",
        description="Read current Nunchi Codex runtime settings and health.",
        annotations=types.ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
        meta={"ui": {"visibility": ["model", "app"]}},
    )
    def get_nunchi_config():
        snapshot = backend.snapshot()
        return _tool_result(types, snapshot, "Read current Nunchi Codex configuration.")

    @server.tool(
        name="update_nunchi_config",
        title="Save Nunchi configuration",
        description=(
            "Atomically apply global or per-channel Nunchi runtime overrides. "
            "Null deletes one override; an empty global/channels object resets that scope."
        ),
        annotations=types.ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
        meta={"ui": {"visibility": ["model", "app"]}},
    )
    def update_nunchi_config(patch: dict[str, Any]):
        result = backend.update(patch)
        message = "Saved Nunchi Codex configuration." if result["ok"] else result["error"]
        return _tool_result(types, result, message)

    @server.tool(
        name="get_nunchi_receipts",
        title="Read Nunchi receipts",
        description="Read recent Codex room gate receipts, newest first.",
        annotations=types.ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
        meta={"ui": {"visibility": ["model", "app"]}},
    )
    def get_nunchi_receipts(limit: int = 50):
        result = backend.receipts(limit=limit)
        return _tool_result(
            types,
            result,
            f"Read {len(result['receipts'])} Nunchi receipt(s).",
        )

    return server


def main(argv: list[str] | None = None) -> int:
    config_argv = list(sys.argv[1:] if argv is None else argv)
    if not config_argv:
        config_argv = default_config_argv(os.environ)
    try:
        config = RunnerConfig.from_sources(argv=config_argv, environ=os.environ)
        server = build_mcp_server(ConfigAppService(environ=os.environ, config=config))
    except ImportError:
        print(
            "nunchi-codex-config-app: the mcp SDK is not installed.\n"
            "Install it with: pip install nunchi[mcp-discord]",
            file=sys.stderr,
        )
        return 1
    except (RuntimeStateError, ValueError) as exc:
        print(f"nunchi-codex-config-app: configuration error: {exc}", file=sys.stderr)
        return 2
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
