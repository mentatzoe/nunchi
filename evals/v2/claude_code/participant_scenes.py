"""Real-participant acceptance scenes for the Claude Code V2 surface.

These scenes run the **real** `claude` binary as the participant through the
real `ClaudeCodeRoomRuntime`. They are not live-room evidence: the Discord
transport is a recording double, so nothing reaches a native platform. What
they establish is the part a stub cannot:

* a real headless Claude Code turn, invoked with exactly the flags and prompts
  this integration ships, returns exactly one valid Nunchi V2 action envelope —
  not a relevance verdict, an admission meta-answer, or prose;
* materially different valid participant instructions produce materially
  different participation while the room facts are held **constant** (scenes
  `profile-sensitivity-*`);
* silence makes zero outbound calls and ends its receipt stream at
  `participant-host`, distinct from model suppression.

Because the participant is stochastic, an individual run is evidence of one
observed outcome, not a deterministic guarantee. Record the raw output.

Usage:

    python3 -m evals.v2.claude_code.participant_scenes
    python3 -m evals.v2.claude_code.participant_scenes --list
    python3 -m evals.v2.claude_code.participant_scenes --scene profile-sensitivity-quiet

Requires the `claude` executable on PATH, authenticated. Set
`NUNCHI_DISCORD_OUTPUT_KEY` or the runner supplies an ephemeral test value.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from nunchi.integrations.claude_code_v2 import ClaudeCodeRoomRuntime

PARTICIPANT = "vigil"
ACTOR = "discord:actor:149"
ROOM = "152"
SCOPE = "discord:channel:152"

# One room moment, reused verbatim across the profile-sensitivity pair so the
# only variable is the participant's own trusted instructions.
#
# It is deliberately *open* — addressed to the room, naming nobody, and
# carrying no security question. A moment addressed to a named third party is
# a bad control: silence is the right answer under every profile, so the trial
# could not distinguish a profile-sensitive participant from an all-mute one.
CASUAL_ROOM_TEXT = (
    "ugh, this deploy has been a nightmare all morning. third rollback today "
    "and I am running on fumes"
)

SECURITY_ROOM_TEXT = (
    "Vigil, quick one: is it safe to log the raw auth header for debugging?"
)

QUIET_INSTRUCTIONS = (
    "You are Vigil. You only speak when the room genuinely needs your security "
    "expertise. If a message is small talk or clearly aimed at someone else, "
    "stay silent rather than filling the air."
)

SOCIABLE_INSTRUCTIONS = (
    "You are Vigil. You are a warm, sociable member of this room. Casual "
    "conversation is welcome and you happily join small talk when someone "
    "brings it up, even if you are not named."
)

DIRECT_INSTRUCTIONS = (
    "You are Vigil. You care about security review. When someone asks you "
    "directly for your view, answer them briefly and concretely in the room."
)

SCENES: dict[str, dict[str, str]] = {
    "addressed-contribution": {
        "instructions": DIRECT_INSTRUCTIONS,
        "text": SECURITY_ROOM_TEXT,
        "expect": "contribution",
    },
    "profile-sensitivity-quiet": {
        "instructions": QUIET_INSTRUCTIONS,
        "text": CASUAL_ROOM_TEXT,
        "expect": "silence",
    },
    "profile-sensitivity-sociable": {
        "instructions": SOCIABLE_INSTRUCTIONS,
        "text": CASUAL_ROOM_TEXT,
        "expect": "contribution",
    },
}


class RecordingTransportClient:
    """A shared-Discord MCP session double that records instead of sending."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        if name == "register_participant":
            body: dict[str, Any] = {
                "registered": True,
                "participant_id": PARTICIPANT,
                "room_id": ROOM,
                "transport_self_actor_id": ACTOR,
            }
        elif name in ("send_message", "reply_message"):
            body = {
                "message": {
                    "message_id": "900001",
                    "channel_id": ROOM,
                    "author_id": ACTOR.removeprefix("discord:actor:"),
                    "author_is_bot": True,
                    "content": arguments["content"],
                    "reply_to_message_id": arguments.get("message_id"),
                }
            }
        else:
            body = {}
        return {
            "isError": False,
            "content": [{"type": "text", "text": json.dumps(body)}],
        }

    def outbound(self) -> list[tuple[str, dict[str, Any]]]:
        return [call for call in self.calls if call[0] != "register_participant"]


def _runtime(root: Path, instructions: str):
    profile = {
        "profile_id": "vigil-scene",
        "participant_id": PARTICIPANT,
        "actor_id": ACTOR,
        "instructions": instructions,
        "provenance": "trusted:evals/v2/claude_code",
    }
    raw = json.dumps(profile).encode("utf-8")
    profile_path = root / "profile.json"
    profile_path.write_bytes(raw)
    config = {
        "schema_version": 2,
        "binding": {
            "participant_id": PARTICIPANT,
            "actor_id": ACTOR,
            "platform": "discord",
            "room_id": ROOM,
            "continuity_scope_id": SCOPE,
        },
        "profile": {
            "path": str(profile_path),
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
        # Pre-attention bypass: these scenes exercise the participant turn, so
        # no external classifier is involved and none is fabricated.
        "attention": {"policy": {"preattention_enabled": False}, "model": {}},
        "limits": {},
        "state_directory": str(root / "state"),
        "transport": {
            "url": "http://127.0.0.1:3993/mcp",
            "timeout_seconds": 30,
            "output_key_env": "NUNCHI_DISCORD_OUTPUT_KEY",
        },
        "claude_code": {"session_mode": "fresh", "timeout_seconds": 180},
    }
    client = RecordingTransportClient()
    return ClaudeCodeRoomRuntime(config, client), client


def run_scene(name: str, timeout: float = 300.0) -> dict[str, Any]:
    scene = SCENES[name]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        runtime, client = _runtime(root, scene["instructions"])
        runtime.handle(
            {
                "schema_version": 2,
                "delivery_id": f"{name}-d1",
                "room_id": ROOM,
                "event": {
                    "id": "discord:message:2001",
                    "type": "message",
                    "author_id": "discord:actor:42",
                    "text": scene["text"],
                    "mentioned_actor_ids": [],
                    "mentions_room": False,
                },
                "actors": {
                    "discord:actor:42": {"display_name": "Zoe", "kind": "human"},
                    ACTOR: {"display_name": "Vigil", "kind": "bot"},
                },
                "continuity_gap": False,
                "target_participant_id": PARTICIPANT,
                "transport_self_actor_id": ACTOR,
            }
        )
        drained = runtime.lane.drain(timeout=timeout)
        outbound = client.outbound()
        records = runtime.pipeline.observation.receipts.all_records()
        host = [r for r in records if r["stage"] == "participant-host"]
        observed = (
            "contribution"
            if outbound
            else "silence"
            if host and host[-1]["body"]["outcome"] == "silent"
            else "none"
        )
        return {
            "scene": name,
            "room_text": scene["text"],
            "instructions": scene["instructions"],
            "expected": scene["expect"],
            "observed": observed,
            "matched_expectation": observed == scene["expect"],
            "drained": drained,
            "lane_errors": list(runtime.lane.errors),
            "native_calls": [call[0] for call in outbound],
            "sent_text": outbound[0][1].get("content") if outbound else None,
            "receipt_stages": [
                {
                    "stage": record["stage"],
                    "writer": record["writer"],
                    "outcome": record["body"].get("outcome")
                    or record["body"].get("delivery"),
                }
                for record in records
            ],
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m evals.v2.claude_code.participant_scenes"
    )
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--scene", action="append", choices=sorted(SCENES))
    args = parser.parse_args(argv)
    if args.list:
        for name, scene in sorted(SCENES.items()):
            print(f"  {name:32} expect {scene['expect']}")
        return 0
    os.environ.setdefault("NUNCHI_DISCORD_OUTPUT_KEY", "z" * 48)
    failures = 0
    for name in args.scene or sorted(SCENES):
        result = run_scene(name)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if not result["matched_expectation"]:
            failures += 1
    if failures:
        print(f"{failures} scene(s) did not match their expectation", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
