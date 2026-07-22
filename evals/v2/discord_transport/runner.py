"""Replay the portable Discord source corpus without provider or network I/O."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from nunchi.mcp_discord.events import DiscordEventSourceV2, message_event_from_create


FIXTURES = ROOT / "tests" / "fixtures" / "v2" / "discord"
CATALOGS = (Path(__file__).with_name("scenes.jsonl"), Path(__file__).with_name("recovery.jsonl"))


def run() -> tuple[dict, ...]:
    source = DiscordEventSourceV2(allowed_channel_ids=frozenset({"42"}))
    results = []
    sequence = 100
    for catalog in CATALOGS:
        for raw in catalog.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            case = json.loads(raw)
            payload = json.loads((FIXTURES / case["fixture"]).read_text(encoding="utf-8"))
            event = message_event_from_create(
                payload,
                gateway_session_id="eval-session",
                gateway_sequence=sequence,
                gateway_self_user_id="9001",
            )
            sequence += 1
            actual = source.native_input(event)["disposition"]
            if actual != case["expected_disposition"]:
                raise AssertionError(f"{case['scene_id']}: {actual}")
            results.append({"scene_id": case["scene_id"], "result": "PASS"})
    return tuple(results)


if __name__ == "__main__":
    for result in run():
        print(json.dumps(result, sort_keys=True))
