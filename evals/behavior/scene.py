"""Scene files: a conversation and the moments to judge in it.

A scene is JSON:

    {
      "id": "story-across-messages",
      "title": "A story told across five messages",
      "source": "docs/behavior.md",
      "review": "draft",
      "platform": "discord",
      "participants": ["vigil"],
      "actors": {"zoe": {"display_name": "Zoe", "kind": "human"}},
      "events": [
        {"id": "m1", "author": "zoe", "at": "-90s", "text": "...",
         "mentions": ["vigil"], "reply_to": "m0"},
        {"id": "r1", "type": "reaction", "author": "vigil", "at": "-60s",
         "target": "m1", "reaction": "👂"}
      ],
      "moments": [
        {"event": "m2", "step1": "pass",
         "notice": [{"fact": "Zoe is mid-story", "events": ["m1", "m2"]}],
         "fitting": ["mhm", "stay_quiet"],
         "misses": [{"move": "contribute", "why": "takes the floor mid-story"}]}
      ]
    }

`participants` lists whose point of view the scene is judged from; each one
must have a profile in `participants.json` or in the scene's own
`profiles`. `at` is an offset before the end of the scene ("-5h", "-90s",
"0s"); the runner places the scene so it ends now. An event without `at`
carries no timestamp.

A moment judges either an event (`event`, optionally `seen_through` a later
event when the judgment happens after more messages arrived) or a pause
(`pause_after` an event, for `pause`). `step1` is what the conservative
first step should do: `pass`, `suppress`, or `either`. `together` on a scene
with several participants names collective checks, for now only
`not-all-quiet`.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


MOVES = ("stay_quiet", "mhm", "wait", "ask", "contribute")
STEP1 = ("pass", "either", "suppress")
TOGETHER = ("not-all-quiet",)
ACTOR_KINDS = ("human", "bot", "system", "unknown")

ROOT = Path(__file__).resolve().parent
SCENES = ROOT / "scenes"
PARTICIPANTS = ROOT / "participants.json"

_OFFSET = re.compile(r"^-?(\d+)([smhd])$")
_UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400}


class SceneError(ValueError):
    """A scene file is malformed."""


def parse_offset(text: str) -> int:
    """Seconds before the end of the scene, from "-5h", "-90s", or "0s"."""

    match = _OFFSET.match(text) if isinstance(text, str) else None
    if match is None:
        raise SceneError(f"offset {text!r} must look like -90s, -5m, -2h, or -1d")
    seconds = int(match.group(1)) * _UNIT[match.group(2)]
    if seconds and not text.startswith("-"):
        raise SceneError(f"offset {text!r} must be before the end of the scene")
    return seconds


@dataclass(frozen=True)
class Moment:
    label: str
    event: str | None
    seen_through: str | None
    pause_after: str | None
    pause_seconds: int | None
    step1: str
    notice: tuple[Mapping[str, Any], ...]
    fitting: tuple[str, ...]
    misses: tuple[Mapping[str, str], ...]

    @property
    def is_pause(self) -> bool:
        return self.pause_after is not None

    def miss_reason(self, move: str) -> str | None:
        for miss in self.misses:
            if miss["move"] == move:
                return miss["why"]
        return None


@dataclass(frozen=True)
class Scene:
    id: str
    title: str
    source: str
    review: str
    platform: str
    participants: tuple[str, ...]
    profiles: Mapping[str, Mapping[str, Any]]
    actors: Mapping[str, Mapping[str, Any]]
    events: tuple[Mapping[str, Any], ...]
    moments: tuple[Moment, ...]
    together: tuple[str, ...]
    path: str | None = None

    def event_index(self, event_id: str) -> int:
        for index, event in enumerate(self.events):
            if event["id"] == event_id:
                return index
        raise SceneError(f"{self.id}: unknown event {event_id!r}")


def _require(condition: bool, scene_id: str, message: str) -> None:
    if not condition:
        raise SceneError(f"{scene_id}: {message}")


def _string(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _moment(raw: Mapping[str, Any], index: int, scene_id: str, event_ids: list[str]) -> Moment:
    where = f"moment {index + 1}"
    _require(isinstance(raw, Mapping), scene_id, f"{where} must be an object")
    allowed = {
        "label", "event", "seen_through", "pause_after", "pause",
        "step1", "notice", "fitting", "misses",
    }
    _require(not set(raw) - allowed, scene_id, f"{where} has unknown fields {sorted(set(raw) - allowed)}")
    event = raw.get("event")
    pause_after = raw.get("pause_after")
    _require(
        (event is None) != (pause_after is None),
        scene_id,
        f"{where} must judge exactly one of an event or a pause",
    )
    pause_seconds = None
    seen_through = raw.get("seen_through")
    if event is not None:
        _require(event in event_ids, scene_id, f"{where} judges unknown event {event!r}")
        _require("pause" not in raw, scene_id, f"{where}: pause needs pause_after")
        if seen_through is not None:
            _require(seen_through in event_ids, scene_id, f"{where}: unknown seen_through")
            _require(
                event_ids.index(seen_through) >= event_ids.index(event),
                scene_id,
                f"{where}: seen_through must not precede the judged event",
            )
    else:
        _require(pause_after in event_ids, scene_id, f"{where}: unknown pause_after")
        _require(seen_through is None, scene_id, f"{where}: a pause has no seen_through")
        pause_seconds = parse_offset("-" + str(raw.get("pause", "")).lstrip("-"))
        _require(pause_seconds > 0, scene_id, f"{where}: pause must be positive")
    step1 = raw.get("step1")
    _require(step1 in STEP1, scene_id, f"{where}: step1 must be one of {STEP1}")
    fitting = raw.get("fitting")
    _require(
        isinstance(fitting, list) and fitting and all(move in MOVES for move in fitting),
        scene_id,
        f"{where}: fitting must list moves from {MOVES}",
    )
    misses = raw.get("misses", [])
    _require(isinstance(misses, list), scene_id, f"{where}: misses must be a list")
    for miss in misses:
        _require(
            isinstance(miss, Mapping)
            and set(miss) == {"move", "why"}
            and miss["move"] in MOVES
            and _string(miss["why"]),
            scene_id,
            f"{where}: each miss needs a move and a why",
        )
    overlap = set(fitting) & {miss["move"] for miss in misses}
    _require(not overlap, scene_id, f"{where}: {sorted(overlap)} both fit and miss")
    notice = raw.get("notice", [])
    _require(isinstance(notice, list), scene_id, f"{where}: notice must be a list")
    for fact in notice:
        _require(
            isinstance(fact, Mapping)
            and set(fact) == {"fact", "events"}
            and _string(fact["fact"])
            and isinstance(fact["events"], list)
            and all(item in event_ids for item in fact["events"]),
            scene_id,
            f"{where}: each notice needs a fact and pointers to known events",
        )
    label = raw.get("label") or (
        f"at {event}" if event is not None else f"{raw.get('pause')} after {pause_after}"
    )
    return Moment(
        label=label,
        event=event,
        seen_through=seen_through,
        pause_after=pause_after,
        pause_seconds=pause_seconds,
        step1=step1,
        notice=tuple(notice),
        fitting=tuple(fitting),
        misses=tuple(misses),
    )


def _event(raw: Mapping[str, Any], scene_id: str, actors: Mapping[str, Any], seen: list[str]) -> dict[str, Any]:
    _require(isinstance(raw, Mapping), scene_id, "each event must be an object")
    event_id = raw.get("id")
    _require(_string(event_id) and event_id not in seen, scene_id, f"event id {event_id!r} must be unique")
    kind = raw.get("type", "message")
    _require(_string(raw.get("author")) and raw["author"] in actors, scene_id, f"{event_id}: author must be a known actor")
    if "at" in raw:
        parse_offset(raw["at"])
    if kind == "message":
        allowed = {"id", "type", "author", "at", "text", "mentions", "mentions_room", "reply_to"}
        _require(isinstance(raw.get("text"), str), scene_id, f"{event_id}: a message needs text")
        for mentioned in raw.get("mentions", []):
            _require(mentioned in actors, scene_id, f"{event_id}: mentions unknown actor {mentioned!r}")
        if "reply_to" in raw:
            _require(raw["reply_to"] in seen, scene_id, f"{event_id}: reply_to must name an earlier event")
    elif kind == "reaction":
        allowed = {"id", "type", "author", "at", "target", "reaction"}
        _require(raw.get("target") in seen, scene_id, f"{event_id}: target must name an earlier event")
        _require(_string(raw.get("reaction")), scene_id, f"{event_id}: a reaction needs reaction")
    else:
        raise SceneError(f"{scene_id}: {event_id}: type must be message or reaction")
    _require(not set(raw) - allowed, scene_id, f"{event_id}: unknown fields {sorted(set(raw) - allowed)}")
    return dict(raw)


def load_participants(path: Path = PARTICIPANTS) -> dict[str, dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_scene(
    raw: Mapping[str, Any],
    *,
    participants: Mapping[str, Mapping[str, Any]] | None = None,
    path: str | None = None,
) -> Scene:
    scene_id = raw.get("id") if isinstance(raw, Mapping) else None
    if not _string(scene_id):
        raise SceneError(f"{path or 'scene'}: id must be a non-empty string")
    allowed = {
        "id", "title", "source", "review", "platform", "participants",
        "profiles", "actors", "events", "moments", "together",
    }
    _require(not set(raw) - allowed, scene_id, f"unknown fields {sorted(set(raw) - allowed)}")
    for name in ("title", "source", "review", "platform"):
        _require(_string(raw.get(name)), scene_id, f"{name} must be a non-empty string")
    known = dict(participants if participants is not None else load_participants())
    profiles = dict(raw.get("profiles", {}))
    known.update(profiles)
    perspectives = raw.get("participants")
    _require(
        isinstance(perspectives, list) and perspectives and all(item in known for item in perspectives),
        scene_id,
        "participants must name known profiles",
    )
    actors = dict(raw.get("actors", {}))
    for actor_id, actor in actors.items():
        _require(
            isinstance(actor, Mapping)
            and set(actor) <= {"display_name", "kind"}
            and actor.get("kind", "unknown") in ACTOR_KINDS,
            scene_id,
            f"actor {actor_id!r} needs display_name and a kind from {ACTOR_KINDS}",
        )
    # Every participant whose profile is known is also an actor in the room.
    for participant_id, profile in known.items():
        actors.setdefault(
            participant_id,
            {"display_name": profile.get("display_name", participant_id), "kind": "bot"},
        )
    events: list[dict[str, Any]] = []
    seen: list[str] = []
    raw_events = raw.get("events")
    _require(isinstance(raw_events, list) and raw_events, scene_id, "events must be a non-empty list")
    for item in raw_events:
        event = _event(item, scene_id, actors, seen)
        events.append(event)
        seen.append(event["id"])
    raw_moments = raw.get("moments")
    _require(isinstance(raw_moments, list) and raw_moments, scene_id, "moments must be a non-empty list")
    moments = tuple(_moment(item, index, scene_id, seen) for index, item in enumerate(raw_moments))
    together = tuple(raw.get("together", []))
    _require(all(item in TOGETHER for item in together), scene_id, f"together must use {TOGETHER}")
    _require(not together or len(perspectives) > 1, scene_id, "together needs several participants")
    return Scene(
        id=scene_id,
        title=raw["title"],
        source=raw["source"],
        review=raw["review"],
        platform=raw["platform"],
        participants=tuple(perspectives),
        profiles={key: known[key] for key in perspectives},
        actors=actors,
        events=tuple(events),
        moments=moments,
        together=together,
        path=path,
    )


def load_scene(path: Path, *, participants: Mapping[str, Mapping[str, Any]] | None = None) -> Scene:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SceneError(f"{path}: {exc}") from exc
    return parse_scene(raw, participants=participants, path=str(path))


def load_scenes(
    directory: Path = SCENES,
    *,
    participants: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[Scene]:
    known = participants if participants is not None else load_participants()
    scenes = [
        load_scene(path, participants=known)
        for path in sorted(directory.rglob("*.json"))
    ]
    ids = [scene.id for scene in scenes]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise SceneError(f"duplicate scene ids: {duplicates}")
    return scenes


def profile_sha256(profile: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(profile, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
