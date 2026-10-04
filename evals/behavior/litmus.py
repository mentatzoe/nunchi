"""Convert the V1 litmus corpus into draft behavior scenes.

The V1 corpus (`evals/verdict_suite/fixtures/`) holds real and constructed
conversations, each with one expected V1 verdict. This writes one draft scene
per conversation under `scenes/litmus/<category>/`. The scene files are the
source from then on: Zoe reviews and edits their ranges, so the converter
never overwrites an existing scene unless asked with `--force`.

Conversion rules, all drafts:

- V1 verdicts map to moves: PASS to stay quiet, ACK to mhm, ASK to ask,
  SPEAK to contribute. The mapped moves fit.
- Where V1 expected only SPEAK or ASK, staying quiet and a nod alone are
  clear misses.
- Step 1 passes everything except the participant's own echo (suppress) and
  tool output from another bot that V1 expected to PASS (either). Being
  addressed to someone else is never a reason to suppress at step 1.
- The `contract` category tests a V1 output format, not behavior, and is
  skipped.

    python3 -m evals.behavior.litmus [--force]
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .scene import SCENES, load_participants, parse_scene


FIXTURES = Path(__file__).resolve().parents[1] / "verdict_suite" / "fixtures"
OUT = SCENES / "litmus"
SKIP = {"contract"}
MOVE = {"PASS": "stay_quiet", "ACK": "mhm", "ASK": "ask", "SPEAK": "contribute"}
HUMANS = {"zoe", "tpm", "mira", "mallory"}
_MENTION = re.compile(r"<@!?(\d+)>")
_PLATFORM = {"discord-channel": "discord", "issue-thread": "issue-thread"}


def _when(text: str | None) -> datetime | None:
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _known_snowflakes() -> dict[str, str]:
    """Discord user IDs that belong to agents anywhere in the corpus."""

    known: dict[str, str] = {}
    for path in FIXTURES.glob("*/*.json"):
        if path.name.endswith(".meta.json"):
            continue
        agent = json.loads(path.read_text(encoding="utf-8"))["agent"]
        for value in [agent.get("mention_id"), *agent.get("aliases", [])]:
            if value and value.isdigit():
                known[value] = agent["id"]
    return known


def _display(actor_id: str) -> str:
    return actor_id if "-" in actor_id else actor_id[:1].upper() + actor_id[1:]


def convert(category: str, fixture: Mapping[str, Any], meta: Mapping[str, Any], *, snowflakes: Mapping[str, str]) -> dict[str, Any]:
    agent = fixture["agent"]
    me = agent["id"]
    aliases = [alias for alias in agent.get("aliases", []) if not alias.isdigit()]
    my_snowflakes = {
        value for value in [agent.get("mention_id"), *agent.get("aliases", [])] if value and value.isdigit()
    }
    actors: dict[str, dict[str, str]] = {}

    def author_id(item: Mapping[str, Any]) -> str:
        kind = item.get("type")
        author = item["author"]
        if kind == "self" or author == me or author in aliases:
            return me
        if kind == "system-state":
            actors["system"] = {"display_name": "System", "kind": "system"}
            return "system"
        actor_kind = "human" if author in HUMANS else "bot"
        actors.setdefault(author, {"display_name": _display(author), "kind": actor_kind})
        return author

    def mentions(text: str) -> list[str]:
        found: list[str] = []
        for snowflake in _MENTION.findall(text):
            if snowflake in my_snowflakes:
                target = me
            elif snowflake in snowflakes:
                target = snowflakes[snowflake]
            else:
                target = f"user-{snowflake}"
                actors.setdefault(target, {"display_name": target, "kind": "unknown"})
            if target not in found:
                found.append(target)
        return found

    items = [*fixture["context"], {**fixture["trigger"], "type": "message"}]
    times = [_when(item.get("timestamp")) for item in items]
    latest = max((when for when in times if when is not None), default=None)
    events = []
    for item, when in zip(items, times):
        event: dict[str, Any] = {"id": item["id"], "author": author_id(item)}
        if when is not None:
            seconds = int((latest - when).total_seconds())
            event["at"] = f"-{seconds}s" if seconds else "0s"
        event["text"] = item["content"]
        found = mentions(item["content"])
        if found:
            event["mentions"] = found
        events.append(event)

    expected = meta["expected"]["verdict"]
    expected = [expected] if isinstance(expected, str) else list(expected)
    fitting = list(dict.fromkeys(MOVE[verdict] for verdict in expected))
    misses = []
    if set(expected) <= {"SPEAK", "ASK"}:
        misses = [
            {"move": "stay_quiet", "why": f"V1 expected a turn. {meta['rationale']}"},
            {"move": "mhm", "why": "V1 expected a turn; a nod alone leaves the ask unanswered."},
        ]
    if events[-1]["author"] == me:
        step1 = "suppress"
    elif category == "tool-chrome" and "PASS" in expected:
        step1 = "either"
    else:
        step1 = "pass"

    profile = dict(load_participants()[me])
    if aliases:
        profile["names"] = list(dict.fromkeys([*profile.get("names", []), *aliases]))
    scene: dict[str, Any] = {
        "id": f"litmus-{meta['id']}",
        "title": meta["title"],
        "source": f"evals/verdict_suite/fixtures/{category}/{meta['id']}.json",
        "review": (
            f"draft: converted from the V1 litmus corpus; V1 expected {' or '.join(expected)}. "
            f"V1 rationale: {meta['rationale']}"
        ),
        "platform": _PLATFORM.get(fixture["surface"]["type"], fixture["surface"]["type"]),
        "participants": [me],
        "actors": actors,
        "events": events,
        "moments": [
            {
                "event": fixture["trigger"]["id"],
                "step1": step1,
                "fitting": fitting,
                "misses": misses,
            }
        ],
    }
    if aliases:
        scene["profiles"] = {me: profile}
    return scene


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert the V1 litmus corpus into draft scenes.")
    parser.add_argument("--force", action="store_true", help="overwrite existing scene files")
    args = parser.parse_args(argv)
    snowflakes = _known_snowflakes()
    participants = load_participants()
    written = skipped = 0
    for path in sorted(FIXTURES.glob("*/*.json")):
        if path.name.endswith(".meta.json") or path.parent.name in SKIP:
            continue
        fixture = json.loads(path.read_text(encoding="utf-8"))
        meta = json.loads(path.with_name(path.stem + ".meta.json").read_text(encoding="utf-8"))
        scene = convert(path.parent.name, fixture, meta, snowflakes=snowflakes)
        parse_scene(scene, participants=participants)
        target = OUT / path.parent.name / f"{meta['id']}.json"
        if target.exists() and not args.force:
            skipped += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(scene, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written += 1
    print(f"wrote {written} scene(s); kept {skipped} existing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
