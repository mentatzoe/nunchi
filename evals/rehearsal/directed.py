"""The director: a behavior scene played on Discord and graded from its own expectations (rehearsal PR 4a).

The behavior suite (`evals/behavior`) judges one moment at a time, with
the room handed to attention as a snapshot. Here the same scene is played as
a conversation: its people and bots post to the Discord stand-in through the
control API (`fake_discord.control`), and the agent's own process takes part
in it. What the room then saw of the agent is graded with the suite's own
`score.grade`, from each moment's `fitting` and `misses`, so a column reads
like a cell of the suite's matrix. This is the one thing a test with a single
person cannot show: several people, a bot's status report, a question for
someone else, a story told across messages.

Two rules bind the director:

- **It never posts as the agent.** Every visible move is the agent's own,
  and the stand-in refuses a post as a harness's bot. A scene that leans on
  the agent's earlier words, or on a message it would have posted, cannot be
  set up, so `plan` calls it unplayable and says why (the reasons are listed
  in `REASONS`; `docs/rehearsal.md` has the table).
- **Scenes are drafts** (`evals/behavior/README.md`). Every result says
  "draft expectations": it compares the agent with a draft, and is not a
  finding about the model until Zoe reviews the scene.

Timing: events older than `HISTORY_SECONDS` before the first graded message
are history, posted backdated (`post(at=)`), oldest first, so the room's
clock only moves forward. The room's clock is then moved to the wall
(`advance`) and the rest is posted live, in order, one message after
another, each after the room has gone quiet. Their gaps are `pace` times the
scene's own (0 scripted: no wait). The stand-in stamps the agent's own post
at the wall, so gaps after the agent first posts cannot be kept; `advance`
does not move the agent's look-again timer (300 real seconds), so a scene
that needs a pause cannot be played here either.

A graded message's grade is the move the room saw: the turns the message
started (or was listed as unattended in), their delivered actions
(`score.agent_move`), and the step 1 judgment attention recorded for it
(`score.visible_result`). A turn that ran on the message is graded whatever
attention said of it: the room saw the agent's move. The scripted run is held
to more than the kind of move (`checks.directed_outcomes`): the delivered
actions must be exactly the one the script makes, about the graded message
(`off_script`), nothing may be committed outside the graded turns
(`other_actions`), every message posted must reach Nunchi, and no wait for the
room to go quiet may time out.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
from typing import Any

from evals.behavior.scene import SCENES as BEHAVIOR_SCENES, Scene, load_scenes, parse_offset
from evals.behavior.score import agent_move, grade, visible_result

from . import checks as checks_module
from .probe import PARTICIPANT, ROOT
from .standin import SCENE_NOD, SCENE_SAY, SceneScript

# Events older than this before the first graded message are history: backdated, not played.
HISTORY_SECONDS = 600

# Why a scene cannot be played, in the order they are listed; `docs/rehearsal.md` explains each.
REASONS = {
    "several-participants": "it is judged from several agents' points of view, and the room has one agent",
    "other-participant": "it is judged from another agent's point of view than the rehearsal's",
    "agent-event": "it holds an event of the agent's own, and the director never posts as the agent",
    "reaction-event": "it holds a reaction by someone else, which the director cannot add",
    "outcome": "it settles an approved action, and the Discord lanes have no approval path",
    "seen-through": "its moment is judged after later messages, a snapshot the live pipeline cannot be asked for",
    "during-turn": "a message must arrive while the agent composes, and the director cannot hold a turn",
    "unattended": "a message must arrive while the agent is busy, and the director cannot hold a turn",
    "pause": "it needs a pause, and the agent's look-again timer counts 300 real seconds",
}

SCENE_DIRECTORY = BEHAVIOR_SCENES / "behavior"


class Unplayable(ValueError):
    """A scene cannot be played on Discord, or does not exist."""


@dataclass(frozen=True)
class Plan:
    """How one scene is played: the history to backdate, the events to post live, or why it cannot be played."""

    scene: Scene
    history: tuple[Mapping[str, Any], ...]
    live: tuple[Mapping[str, Any], ...]
    # The codes (`REASONS`) of everything that stops it, in their order; empty when it can be played.
    reasons: tuple[str, ...] = ()
    # The same as a sentence, naming the events and moments; None when it can be played.
    unplayable: str | None = None


def _offsets(scene: Scene) -> list[int]:
    """Each event's seconds before the end of the scene; an event with no time keeps the one before it."""

    found: list[int] = []
    for event in scene.events:
        found.append(parse_offset(event["at"]) if "at" in event else (found[-1] if found else 0))
    return found


def plan(scene: Scene) -> Plan:
    """Sort a scene into what the director can play, and say why when it cannot."""

    found: dict[str, list[str]] = {}

    def refuse(code: str, detail: str) -> None:
        found.setdefault(code, []).append(detail)

    if len(scene.participants) > 1:
        refuse("several-participants", ", ".join(scene.participants))
    elif scene.participants[0] != PARTICIPANT:
        refuse("other-participant", scene.participants[0])
    for event in scene.events:
        if event["author"] in scene.participants:
            refuse("agent-event", event["id"])
        elif event.get("type", "message") != "message":
            refuse("reaction-event", event["id"])
    for moment in scene.moments:
        if moment.outcome is not None:
            refuse("outcome", moment.label)
        if moment.seen_through:
            refuse("seen-through", moment.label)
        if moment.during_turn:
            refuse("during-turn", moment.label)
        if moment.unattended:
            refuse("unattended", moment.label)
        if moment.pause_after:
            refuse("pause", moment.label)
    reasons = tuple(code for code in REASONS if code in found)
    offsets = _offsets(scene)
    graded = [scene.event_index(moment.event) for moment in scene.moments if moment.event]
    first = min(graded) if graded else 0
    cut = 0
    while cut < first and offsets[cut] - offsets[first] > HISTORY_SECONDS:
        cut += 1
    return Plan(
        scene=scene,
        history=tuple(scene.events[:cut]),
        live=tuple(scene.events[cut:]),
        reasons=reasons,
        unplayable=(
            "; ".join(f"{REASONS[code]} ({', '.join(found[code])})" for code in reasons) if reasons else None
        ),
    )


def load_plans(directory: Path = SCENE_DIRECTORY) -> list[Plan]:
    """The plan of every behavior scene."""

    return [plan(scene) for scene in load_scenes(directory)]


def script_for(scene_plan: Plan) -> SceneScript:
    """The script the scene's graded moments are played with: attention and the agent both follow it."""

    moments: dict[str, Any] = {}
    for moment in scene_plan.scene.moments:
        if moment.event:
            moments.setdefault(moment.event, moment)
    return SceneScript(moments)


@dataclass(frozen=True)
class DirectedSpec:
    """What a moment spec is to the Discord room, for one scene: the room posts through it as it does for a moment."""

    plan: Plan
    script: SceneScript
    # The attributes of `probe.MomentSpec` the room and the probe read.
    expect: str = "directed"
    wake_phrase: str | None = None
    reply_to_agent: bool = False
    thread: str | None = None
    reconnect_before: bool = False

    @property
    def name(self) -> str:
        return self.plan.scene.id

    @property
    def scene(self) -> Path:
        return Path(self.plan.scene.path or self.plan.scene.id)


def spec(scene_id: str, directory: Path = SCENE_DIRECTORY) -> DirectedSpec:
    """The spec for a behavior scene by its id; `Unplayable` where there is none or it cannot be played."""

    plans = {item.scene.id: item for item in load_plans(directory)}
    if scene_id not in plans:
        raise Unplayable(f"no behavior scene is called {scene_id!r}: {', '.join(sorted(plans))}")
    chosen = plans[scene_id]
    if chosen.unplayable:
        playable = ", ".join(sorted(item.scene.id for item in plans.values() if not item.unplayable))
        raise Unplayable(f"{scene_id} cannot be played on Discord: {chosen.unplayable}. Playable: {playable}")
    return DirectedSpec(chosen, script_for(chosen))


# -- playing a scene ------------------------------------------------------------------------------


def scripted_action(moment: Any, event_id: str | None) -> dict[str, Any] | None:
    """The one action the script makes at ``moment``, about the message ``event_id``, as the room records it; None where it is quiet.

    It is worked out from what the scene expects (the first ``fitting`` move,
    `SceneScript.intended`), not read from what the script did, so a script
    that does something else cannot agree with it by doing it.
    """

    move = SceneScript.intended(moment)
    if move == "speak":
        return {"kind": "message", "text": SCENE_SAY.format(event=moment.event), "origin_event_id": event_id}
    if move == "mhm":
        return {"kind": "reaction", "reaction": SCENE_NOD, "target_event_id": event_id}
    return None


def graded_moments(scene: Scene, deliveries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One entry per graded moment, with what the scene expects and what the script is to do, before it is judged."""

    sent = {delivery["scene_event"]: delivery for delivery in deliveries}
    entries = []
    for moment in scene.moments:
        delivery = sent.get(moment.event, {})
        entries.append(
            {
                "label": moment.label,
                "event": moment.event,
                "event_id": delivery.get("event_id"),
                "reached": bool(delivery.get("observed")),
                "step1": moment.step1,
                "fitting": list(moment.fitting),
                "misses": [miss["move"] for miss in moment.misses],
                "scripted": SceneScript.intended(moment),
                "scripted_action": scripted_action(moment, delivery.get("event_id")),
            }
        )
    return entries


def play_scene(leg: Any, scene_plan: Plan, settle_seconds: float, pace: float = 0.0) -> dict[str, Any]:
    """Play a scene on the leg's Discord room and return the record of what was posted, not yet judged.

    ``leg`` posts a message with ``deliver(raw, at, scene, sequence)`` (``at``
    None for the room's own time) and waits for the room to go quiet with
    ``settle(seconds)``; ``leg.discord`` holds the stand-in. History goes
    first, oldest first, backdated; the room's clock is then moved to the
    wall; each live event follows after the room settled, ``pace`` times the
    scene's own gap later. Where the leg has a `SceneScript`, each graded
    message's text is told to it before it is posted. A wait that timed out is
    recorded in its delivery (``settled``) and listed in ``unsettled`` (a
    scripted run fails on it: `checks.unsettled`).
    """

    if scene_plan.unplayable:
        raise Unplayable(f"{scene_plan.scene.id} cannot be played on Discord: {scene_plan.unplayable}")
    scene = scene_plan.scene
    room = leg.discord
    script = getattr(leg, "script", None)
    graded = {moment.event for moment in scene.moments if moment.event}
    offsets = dict(zip((event["id"] for event in scene.events), _offsets(scene)))
    anchor = offsets[scene_plan.live[0]["id"]]
    now = datetime.now(timezone.utc)
    deliveries: list[dict[str, Any]] = []

    def post(raw: Mapping[str, Any], at: datetime | None) -> dict[str, Any]:
        if isinstance(script, SceneScript) and raw["id"] in graded:
            script.register(room.render(raw, scene), raw["id"])
        delivery = leg.deliver(raw, at, scene, len(deliveries))
        deliveries.append(delivery)
        return delivery

    for raw in scene_plan.history:
        post(raw, now - timedelta(seconds=offsets[raw["id"]] - anchor))["phase"] = "history"
    if scene_plan.history:
        settled = leg.settle(settle_seconds)
        for delivery in deliveries:
            delivery["settled"] = settled
        # The room's clock stands at the newest history message; the first live event is the wall's now.
        lag = room.fd.state()["channels"][room.column]["lag"]
        if lag:
            room.fd.advance(room.column, lag)
    previous: str | None = None
    for raw in scene_plan.live:
        if previous is not None and pace > 0:
            time.sleep(max(0, offsets[previous] - offsets[raw["id"]]) * pace)
        delivery = post(raw, None)
        delivery["phase"] = "live"
        delivery["settled"] = leg.settle(settle_seconds)
        previous = raw["id"]
    entries = graded_moments(scene, deliveries)
    played = {
        "name": scene.id,
        "scene": str(Path(scene.path).relative_to(ROOT)) if scene.path and Path(scene.path).is_relative_to(ROOT) else scene.path,
        "title": scene.title,
        "expect": "directed",
        "review": scene.review,
        "history": [event["id"] for event in scene_plan.history],
        "live": [event["id"] for event in scene_plan.live],
        "deliveries": deliveries,
        "graded": entries,
        # Whether every graded message reached Nunchi: when one did not, its moment tested nothing.
        "reached": all(entry["reached"] for entry in entries),
    }
    late = checks_module.unsettled(deliveries)
    if late:
        # A wait for the room to go quiet ran out: the record may lack what came after (`checks.unsettled`).
        played["unsettled"] = late
    return played


# -- judging a scene --------------------------------------------------------------------------------


def _decision(call: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Attention's decision for a message as `score.visible_result` reads it, from the call the leg recorded."""

    if call is None:
        return None
    if call.get("error"):
        return {"status": "error", "wake_action": call.get("wake_action")}
    return {"status": "ok", "effective_disposition": call.get("disposition")}


ACTION_KEYS = ("kind", "text", "reaction", "target_event_id", "origin_event_id", "delivery", "delivered")


def _summary(action: Mapping[str, Any]) -> dict[str, Any]:
    return {key: action.get(key) for key in ACTION_KEYS if key in action}


def _off_script(
    expected: Mapping[str, Any] | None, actions: Sequence[Mapping[str, Any]], event_id: str | None, allowed: set[str | None]
) -> list[str]:
    """How the delivered ``actions`` of a graded moment differ from the one the script makes (``expected``), in words.

    ``expected`` is None where the script is quiet: nothing may be delivered.
    Otherwise there must be exactly one delivered action, with the scripted
    kind and words (or reaction), about the graded message: a reaction's or
    reply's ``target_event_id``, a message's ``origin_event_id`` (as
    `checks.discord_moment_outcome` reads them for the plain lanes). A turn
    that listed the message as unattended took it with a later one, so the
    action may be about that turn's trigger as well (``allowed``).
    """

    delivered = [action for action in actions if action.get("delivered")]
    if expected is None:
        return [f"it made a {action.get('kind')} where the script is quiet" for action in delivered]
    if len(delivered) != 1:
        return [f"it delivered {len(delivered)} action(s), not the one scripted {expected['kind']}"]
    action, problems = delivered[0], []
    for key in ("kind", "text", "reaction"):
        if key in expected and action.get(key) != expected[key]:
            problems.append(f"its {key} is {str(action.get(key))[:80]!r}, not the scripted {str(expected[key])[:80]!r}")
    about = "target_event_id" if expected["kind"] == "reaction" else "origin_event_id"
    if action.get(about) not in allowed:
        problems.append(f"its {about} is {action.get(about)}, not the graded message {event_id}")
    return problems


def judge_scene(leg: Any, record: dict[str, Any], scene: Scene) -> None:
    """Grade each graded moment of a played scene, in the keys the suite's results use (`score.cell` reads them).

    For each moment: ``result`` and ``by``, the move the room saw and who
    chose it (attention suppressed it, or the agent did); ``grade``, its
    `score.grade` from the scene's ``fitting`` and ``misses`` for the
    visible move and from attention's judgment for step 1; ``cited``, for
    each of the moment's facts whether attention's evidence points at one of
    its messages. The room is graded: when a turn began on the message, its
    delivered actions are the move, whatever attention said of the message
    (a turn that ran on a message attention suppressed is the agent's, and may
    speak). A message that never reached Nunchi, or that attention never
    judged and no turn began on, reads ``unsupported``; one that woke the
    agent whose turn did not deliver reads ``woken`` (``provider_error``),
    which fits nothing. ``off_script`` lists how the delivered actions differ
    from the one the script makes (`_off_script`), and the record's
    ``other_actions`` every committed action outside the graded turns. ``leg``
    supplies ``invocations`` (the turns, each with its ``trigger`` and any
    ``unattended`` messages), ``committed`` (the actions, ``delivered`` once
    judged) and ``attention_calls``.
    """

    native = {delivery["scene_event"]: delivery["event_id"] for delivery in record["deliveries"]}
    started: dict[str, dict[str, Any]] = {}
    shown: list[dict[str, Any]] = []
    for item, moment in zip(record["graded"], scene.moments):
        event_id = item["event_id"]
        turns = [
            turn for turn in leg.invocations
            if event_id and (turn.get("trigger") == event_id or event_id in (turn.get("unattended") or ()))
        ]
        # The turns that began on this message: they ran, so the room saw what they did.
        own = [turn for turn in turns if turn.get("trigger") == event_id]
        requests = {turn["request_id"] for turn in turns}
        actions = [action for action in leg.committed if action.get("request_id") in requests]
        call = next((call for call in leg.attention_calls if event_id and call.get("trigger") == event_id), None)
        attention = visible_result(_decision(call)) if item["reached"] else "unsupported"
        failed = any(not action.get("delivered") for action in actions)
        result, by = attention, None
        if item["reached"] and (own or (attention == "woken" and turns)):
            result, by = ("woken", None) if failed else (agent_move(actions), "agent")
        elif attention == "stay_quiet":
            by = "attention"
        evidence = set((call or {}).get("evidence") or ())
        allowed = {event_id, *(turn.get("trigger") for turn in turns)}
        item.update(
            result=result,
            by=by,
            # A turn on a message nothing judged was not read by step 1.
            grade=grade(moment, result, attention="not judged" if attention == "unsupported" else attention),
            provider_error=failed,
            cited=[bool(evidence & {native[event] for event in fact["events"] if event in native}) for fact in moment.notice],
            turns=sorted(requests),
            actions=[_summary(action) for action in actions],
            off_script=_off_script(item.get("scripted_action"), actions, event_id, allowed),
        )
        why = moment.miss_reason(result)
        if why:
            item["why"] = why
        started.update({turn["request_id"]: turn for turn in turns})
        shown += item["actions"]
    record["turns"] = list(leg.invocations)
    record["graded_turns"] = len(started)
    record["graded_wake_sources"] = [turn.get("source") for turn in started.values()]
    record["other_turns"] = sum(1 for turn in leg.invocations if turn["request_id"] not in started)
    # What the agent did on the messages nobody graded: the script is silent there.
    record["other_actions"] = [_summary(action) for action in leg.committed if action.get("request_id") not in started]
    record["actions"] = shown
    record["posts"] = [
        {"text": action.get("text"), "delivery": action.get("delivery"), "delivered": bool(action.get("delivered"))}
        for action in shown
        if action.get("kind") in ("message", "reply")
    ]
    if not record["reached"]:
        record["outcome"] = checks_module.NOT_DELIVERED
    elif (
        all(item["grade"]["visible"] == "fits" and item["grade"]["step1"] == "ok" and not item["off_script"] for item in record["graded"])
        and not record["other_actions"]
    ):
        record["outcome"] = checks_module.FITS
    else:
        record["outcome"] = checks_module.MISSES
