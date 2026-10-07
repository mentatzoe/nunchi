"""A live room for Codex: the shared Discord transport, the library, and `codex app-server` (#94 step 9e).

`nunchi-codex-app-server-runner --config <path> --config-sha256 <hash>` runs one
participant: the room comes from the shared Discord transport
(`nunchi.integrations.discord_room`, the same connection the Claude Code runtime
uses), the library decides each turn (`nunchi.room`), and Codex takes the turns
through its app-server (`integration.py`). ``--probe`` reports what is
configured without connecting.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
import os
import sys
from typing import Any

from nunchi import __version__
from nunchi.adapters.model_apis import ATTENTION_KINDS
from nunchi.adapters.runtime import load_pinned_config
from nunchi.errors import NunchiError, ValidationError
from nunchi.room import Room

from ..discord_room import DiscordRoomConnection, output_secret, transport_client
from ..mcp_client import StreamableMCPClient
from .integration import MCP_SERVER_NAME, TOOL_NAMES, CodexIntegrationError, build_integration

SURFACE = "codex-app-server"
LABEL = "Codex app-server"
# The shared Discord transport shows messages and reactions as they arrive and
# from its retained history; joins and leaves only live.
EVENT_VISIBILITY = {
    "message": "history-and-live",
    "reaction": "history-and-live",
    "membership": "live-only",
}


class CodexRoomRunner:
    """One participant in one Discord room, with Codex taking its turns."""

    def __init__(
        self,
        config: Mapping[str, Any],
        client: StreamableMCPClient,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        environ = os.environ if environ is None else environ
        transport = config.get("transport")
        if not isinstance(transport, Mapping):
            raise ValidationError(f"{LABEL} transport config must be an object")
        secret = output_secret(transport, label=LABEL, environ=environ)
        # The transport's key never reaches Codex, and the room never sees it.
        settings, integration = build_integration(
            config,
            environ=environ,
            sections=("transport",),
            withhold=(transport["output_key_env"],),
        )
        if settings.binding.platform != "discord":
            raise ValidationError(f"{LABEL} currently requires the shared Discord transport")
        self.settings = settings
        self.integration = integration
        self.connection = DiscordRoomConnection(
            client=client,
            binding=settings.binding,
            secret=secret,
            label=LABEL,
            surface=SURFACE,
        )
        self.room = Room(
            settings,
            participant=integration.participant,
            transport=self.connection.transport,
            event_visibility=EVENT_VISIBILITY,
            state_prefix=f"{SURFACE}-",
            attention_kinds=ATTENTION_KINDS,
        )
        self.connection.attach(self.room)

    def serve(self) -> None:
        self.connection.serve()

    def close(self) -> None:
        self.room.cancel()
        self.integration.close()

    def probe(self) -> dict[str, Any]:
        binding = self.settings.binding
        codex = self.integration.settings
        try:
            executable: str | None = codex.resolve_executable(self.integration.environment)
        except CodexIntegrationError:
            executable = None
        return {
            "product": "nunchi",
            "product_version": __version__,
            "generation": 2,
            "surface": SURFACE,
            "configured": True,
            "participant_id": binding.participant_id,
            "actor_id": binding.actor_id,
            "room_id": binding.room_id,
            "codex_executable": executable,
            "working_directory": str(codex.working_directory),
            "project_trust_level": codex.project_trust_level,
            "room_mcp_server": MCP_SERVER_NAME,
            "room_tools": [
                TOOL_NAMES[role] for role in self.integration.participant.registered_roles
            ],
            "shared_discord_transport": True,
            "privileged_actions_enabled": self.room.privileged is not None,
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nunchi-codex-app-server-runner")
    parser.add_argument("--config")
    parser.add_argument("--config-sha256", default=os.environ.get("NUNCHI_CODEX_CONFIG_SHA256"))
    parser.add_argument("--probe", action="store_true")
    return parser


def _print(document: Mapping[str, Any]) -> None:
    print(json.dumps(document, sort_keys=True, separators=(",", ":")))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if not args.config:
            if args.probe:
                _print(
                    {
                        "product": "nunchi",
                        "product_version": __version__,
                        "generation": 2,
                        "surface": SURFACE,
                        "configured": False,
                    }
                )
                return 0
            raise ValidationError("--config is required")
        if not args.config_sha256:
            raise ValidationError("--config-sha256 is required")
        config = load_pinned_config(args.config, args.config_sha256)
        client = transport_client(config.get("transport"), label=LABEL)
        runner = CodexRoomRunner(config, client)
        if args.probe:
            _print(runner.probe())
            runner.close()
            return 0
        try:
            runner.serve()
        finally:
            runner.close()
    except (NunchiError, ValueError) as exc:
        print(f"{LABEL} runner error: {exc}", file=sys.stderr)
        return 3 if isinstance(exc, ValidationError) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
