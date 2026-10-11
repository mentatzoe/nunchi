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
  and the stand-in refuses a post as a harness's bot. A scene that holds an
  earlier line of the agent's (a promise it made, a nod it gave) therefore
  has the agent say it itself, as its scripted move on the message it answers
  (PR 4c, `standin.Line`), and the run checks the line landed exactly as the
  scene has it. A line that answers nothing gets a cue: one added person
  message posted just before it, whose scripted answer is the line. The cue
  is recorded ("played with a cue") because a live model sees it in history.
  `plan` calls a scene unplayable only when it cannot place such a line, and
  says why (`REASONS`; `docs/rehearsal.md` has the table).
- **Scenes are drafts** (`evals/behavior/README.md`). Every result says
  "draft expectations": it compares the agent with a draft, and is not a
  finding about the model until Zoe reviews the scene.

Timing: events older than `HISTORY_SECONDS` before the first graded message
are history, posted backdated (`post(at=)`), oldest first, so the room's
clock only moves forward. The room's clock is then moved to the wall
(`advance`) and the rest is posted live, in order, one message after
another, each after the room has gone quiet. Their gaps are `pace` times the
scene's own (0 scripted: no wait). The stand-in stamps the agent's own post
at the wall, so nothing after the agent's first line can be backdated: a scene
with a line of the agent's is played live from the message that triggers it,
and its time is compressed (the result says so). `advance` does not move the
agent's look-again timer (300 real seconds), so a scene that needs a pause
cannot be played here either.

A hold (PR 4c) puts a message into a turn that is under way, which is what
a one-person test cannot show. The scripted model endpoint holds the turn's
first model call (`standin.Gate`); the director waits until the endpoint has
it, posts the scene's `during_turn` messages (or the `unattended` ones, with
the moment's own message, which also arrives while the agent is busy), waits
for them to reach Nunchi, and releases the call. The same gate holds each
column's turn. The agent's first attempt is what it had ready; the core's look
before posting holds it back and shows the agent the page of news; and the
script then does what the scene fits. The result says how each hold went:
`held`, `raced` (the turn went on before a held message reached Nunchi: not a
miss, but the scripted run fails), `unseen` (the held message reached Nunchi
and the core did not show it to the turn), `unmerged` (an unattended message
was judged on its own, or read twice, and not only with the moment) or `never-asked`.

Live (PR 4d, `--room discord --scene` without `--scripted`, on a CI runner): the
same scene is played with a live model behind the column, and nothing is
scripted but the people. The director posts what the scene's people say and
waits for the room to go quiet, as above, but it cannot force the agent's
words, so:

- an earlier line of the agent's is the live agent's own move on the message
  it answers (or on the cue), and is only checked to be of the scene's kind (a
  reply or a post for a reply, a reaction for a nod). If the agent made no such
  move, the line's moment is reported ``precondition not met`` with what the
  agent did, it is not graded, and the scene is not played further, since the
  moments after it would be judged against a history the agent did not have;
- a hold is timing: the director posts the held messages as soon as the
  column's turn has begun and reports whether they reached Nunchi before the
  agent's move (``held``), after it (``raced``), or reached it in time and were
  not shown to the turn (``unseen``, only where the column's own record shows
  what the turn was shown);
- the grades are reported, never failed (`checks.py`): the scene's expectations
  are drafts nobody has reviewed. What fails a live run is the plumbing and
  safety checks, as for any run.

A graded message's grade is the move the room saw: the turns the message
started (or was listed as unattended in), their delivered actions
(`score.agent_move`), and the step 1 judgment attention recorded for it
(`score.visible_result`). A turn that ran on the message is graded whatever
attention said of it: the room saw the agent's move. The scripted run is held
to more than the kind of move (`checks.directed_outcomes`): the delivered
actions must be exactly the one the script makes, about the graded message
(`off_script`), nothing may be committed outside the graded turns and the
turns that play the agent's own lines (`other_actions`), every message posted
must reach Nunchi, and no wait for the room to go quiet may time out.
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
from .standin import SCENE_NOD, SCENE_SAY, Line, SceneScript, timestamp

# Events older than this before the first graded message are history: backdated, not played.
HISTORY_SECONDS = 600
# A graded message that follows a quiet longer than this, in a scene that holds a line of the agent's, cannot be played: the
# stand-in stamps the agent's post at the wall, so the hours of quiet the scene is about would be seconds.
QUIET_SECONDS = 4 * 3600
# How long the director waits for the agent's model to be asked about a held turn (a harness process has to start first).
HOLD_ASK_SECONDS = 60.0
# Live: how often the director looks for the column's turn to begin on a held message, and the kinds of action that make a
# line of each kind (a reply or a plain post answers, a reaction nods).
BEGUN_POLL_SECONDS = 0.05
LINE_ACTIONS = {"reply": ("message", "reply"), "message": ("message", "reply"), "reaction": ("reaction",)}
# The person's message the director adds just before an earlier line of the agent's that answers nothing in the scene (a cue).
CUE_TEXT = "{agent}, anything to report?"

# Why a scene cannot be played, in the order they are listed; `docs/rehearsal.md` explains each.
REASONS = {
    "several-participants": "it is judged from several agents' points of view, and the room has one agent",
    "other-participant": "it is judged from another agent's point of view than the rehearsal's",
    "agent-event": "it holds an event of the agent's own that the agent cannot play as its scripted move on a message",
    "reaction-event": "it holds a reaction by someone else, which the director cannot add",
    "outcome": "it settles an approved action, and the Discord lanes have no approval path",
    "seen-through": "its moment is judged after later messages, a snapshot the live pipeline cannot be asked for",
    "during-turn": "a message must arrive while the agent composes, and the scene's held messages cannot be placed in a turn",
    "unattended": "a message must arrive while the agent is busy, and no line of the agent's was being composed then",
    "pause": "it needs a pause, and the agent's look-again timer counts 300 real seconds",
    "time": "it is about hours of quiet, and the agent's own post is stamped at the wall, so the hours would become seconds",
}

SCENE_DIRECTORY = BEHAVIOR_SCENES / "behavior"


class Unplayable(ValueError):
    """A scene cannot be played on Discord, or does not exist."""


@dataclass(frozen=True)
class Hold:
    """A turn the scripted model's first call is held for, and the messages that arrive while it is held (rehearsal PR 4c).

    ``trigger`` is the scene event whose turn is held and ``events`` the
    scene's messages that land in it, in the scene's order. A ``during-turn``
    moment holds its own turn (the messages that arrive while the agent is
    composing its answer). An ``unattended`` moment holds the turn the agent
    was busy with, the one that plays the line it was composing: the
    unattended messages and the moment's own message all arrive while it is
    busy, since Nunchi then reads them as a single moment (#94 step 6). Posted
    after the turn, the first would be judged on its own. ``moment`` is the
    graded event the hold is for.
    """

    trigger: str
    events: tuple[str, ...]
    kind: str
    moment: str


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
    # The scene's events of the agent's own, each played by the agent as its scripted move on a message (`standin.Line`),
    # and the cues the director adds for the ones that answer nothing: {id, author, mentions, text, before}.
    lines: tuple[Line, ...] = ()
    cues: tuple[Mapping[str, Any], ...] = ()
    # The turns that are held while messages land in them.
    holds: tuple[Hold, ...] = ()
    # How many seconds of the scene's own time play out in seconds, because a line of the agent's is stamped at the wall
    # and nothing after it can be backdated; 0 where the scene has no line.
    compressed: int = 0


def _offsets(scene: Scene) -> list[int]:
    """Each event's seconds before the end of the scene; an event with no time keeps the one before it."""

    found: list[int] = []
    for event in scene.events:
        found.append(parse_offset(event["at"]) if "at" in event else (found[-1] if found else 0))
    return found


def _cue_author(scene: Scene) -> str | None:
    """The person whose message cues a line of the agent's: the first human who posts in the scene."""

    for kind in ("human", None):
        for event in scene.events:
            actor = scene.actors.get(event["author"], {})
            if event["author"] not in scene.participants and (kind is None or actor.get("kind") == kind):
                return event["author"]
    return None


def _lines(scene: Scene, refuse: Any) -> tuple[list[Line], list[dict[str, Any]]]:
    """The scene's events of the agent's, as lines it can play on a message, and the cues for those that answer nothing.

    An event that answers or reacts to a person's message is the agent's
    scripted move on that message. One that answers nothing is its move on a
    cue, a message of a person's the director adds just before it. Anything
    else (a line on a graded message, two lines on one message, one on the
    agent's own event, several cues) cannot be placed and is refused.
    """

    graded = {moment.event for moment in scene.moments if moment.event}
    own = {event["id"] for event in scene.events if event["author"] in scene.participants}
    found: list[Line] = []
    cues: list[dict[str, Any]] = []
    taken: set[str] = set()
    for event in scene.events:
        if event["author"] not in scene.participants:
            continue
        kind = "reaction" if event.get("type", "message") == "reaction" else ("reply" if event.get("reply_to") else "message")
        trigger = event.get("target") if kind == "reaction" else event.get("reply_to")
        if kind == "message":
            author = _cue_author(scene)
            if cues or author is None:
                refuse("agent-event", f"{event['id']} answers nothing, and {'a cue is already added for another line' if cues else 'no person posts to cue it'}")
                continue
            trigger = f"cue-{event['id']}"
            cues.append(
                {
                    "id": trigger,
                    "author": author,
                    "mentions": list(scene.participants),
                    "text": CUE_TEXT.format(agent=scene.actors[scene.participants[0]].get("display_name", scene.participants[0])),
                    "before": event["id"],
                }
            )
        elif trigger in own or trigger in graded:
            refuse("agent-event", f"{event['id']} is the agent's move on {trigger}, which {'is its own event' if trigger in own else 'a moment grades'}")
            continue
        if trigger in taken:
            refuse("agent-event", f"{event['id']} is a second move on {trigger}, and the agent makes one action per turn")
            continue
        taken.add(trigger)
        found.append(
            Line(event["id"], trigger, kind, text=event.get("text"), reaction=event.get("reaction") if kind == "reaction" else None, cue=kind == "message")
        )
    return found, cues


def _begins(line: Line, position: Mapping[str, int]) -> int:
    """Where in the scene the agent's turn on a line begins: at the message it answers, or, for a cue, just before the line."""

    return position[line.event] if line.cue else position[line.trigger]


def _holds(scene: Scene, lines: Sequence[Line], refuse: Any) -> list[Hold]:
    """The turns to hold: where a message must arrive while the agent composes (`during_turn`) or is busy (`unattended`)."""

    position = {event["id"]: index for index, event in enumerate(scene.events)}
    own = {event["id"] for event in scene.events if event["author"] in scene.participants}
    found: list[Hold] = []
    for moment in scene.moments:
        if moment.event is None:
            continue
        if moment.during_turn:
            if any(event in own for event in moment.during_turn):
                refuse("during-turn", f"{moment.label}: the agent's own event cannot arrive during its turn")
                continue
            found.append(Hold(moment.event, tuple(moment.during_turn), "during-turn", moment.event))
        if moment.unattended:
            # The agent was busy with a line of its own, begun before the first unattended message and said after it. A line
            # that answers nothing begins where it is said (its cue is just before it), so it is never the one.
            first = min(position[event] for event in moment.unattended)
            busy = [line for line in lines if _begins(line, position) < first < position[line.event]]
            if not busy:
                refuse("unattended", f"{moment.label}: the agent says no line while its messages arrive")
                continue
            trigger = busy[-1].trigger
            events = tuple(dict.fromkeys((*moment.unattended, moment.event)))
            found.append(Hold(trigger, events, "unattended", moment.event))
    return found


def plan(scene: Scene) -> Plan:
    """Sort a scene into what the director can play, and say why when it cannot."""

    found: dict[str, list[str]] = {}

    def refuse(code: str, detail: str) -> None:
        found.setdefault(code, []).append(detail)

    solo = len(scene.participants) == 1 and scene.participants[0] == PARTICIPANT
    if len(scene.participants) > 1:
        refuse("several-participants", ", ".join(scene.participants))
    elif scene.participants[0] != PARTICIPANT:
        refuse("other-participant", scene.participants[0])
    lines: list[Line] = []
    cues: list[dict[str, Any]] = []
    if solo:
        lines, cues = _lines(scene, refuse)
    for event in scene.events:
        if event["author"] in scene.participants:
            if not solo:
                refuse("agent-event", event["id"])
        elif event.get("type", "message") != "message":
            refuse("reaction-event", event["id"])
    holds = _holds(scene, lines, refuse) if solo else []
    for moment in scene.moments:
        if moment.outcome is not None:
            refuse("outcome", moment.label)
        if moment.seen_through:
            refuse("seen-through", moment.label)
        if moment.pause_after:
            refuse("pause", moment.label)
    offsets = _offsets(scene)
    for number, event in enumerate(scene.events):
        graded = any(moment.event == event["id"] for moment in scene.moments)
        if lines and graded and number and offsets[number - 1] - offsets[number] > QUIET_SECONDS:
            hours = (offsets[number - 1] - offsets[number]) // 3600
            refuse("time", f"{event['id']} follows {hours} hours of quiet")
    reasons = tuple(code for code in REASONS if code in found)
    graded_at = [scene.event_index(moment.event) for moment in scene.moments if moment.event]
    first = min(graded_at) if graded_at else 0
    cut = 0
    while cut < first and offsets[cut] - offsets[first] > HISTORY_SECONDS:
        cut += 1
    # Nothing after the agent's first line can be backdated, and a held turn starts live: play from the earliest of them.
    position = {event["id"]: index for index, event in enumerate(scene.events)}
    starts = [_begins(line, position) for line in lines]
    compressed = 0
    if starts:
        compressed = offsets[min(starts)] - min(offsets[min(starts):])
        cut = min(cut, min(starts))
    cut = min([cut, *(position[hold.trigger] for hold in holds)])
    return Plan(
        scene=scene,
        history=tuple(scene.events[:cut]),
        live=tuple(scene.events[cut:]),
        reasons=reasons,
        unplayable=(
            "; ".join(f"{REASONS[code]} ({', '.join(found[code])})" for code in reasons) if reasons else None
        ),
        lines=tuple(lines),
        cues=tuple(cues),
        holds=tuple(holds),
        compressed=compressed,
    )


def load_plans(directory: Path = SCENE_DIRECTORY) -> list[Plan]:
    """The plan of every behavior scene."""

    return [plan(scene) for scene in load_scenes(directory)]


def script_for(scene_plan: Plan, *, word_first: bool = False) -> SceneScript:
    """The script the scene's graded moments are played with: attention and the agent both follow it.

    With ``word_first`` the agent's nod is first a word, which the core refuses
    before committing anything, and then the emoji, in the same turn
    (`SceneScript`): the one scripted case of a reaction that is refused.
    """

    moments: dict[str, Any] = {}
    for moment in scene_plan.scene.moments:
        if moment.event:
            moments.setdefault(moment.event, moment)
    return SceneScript(moments, lines=scene_plan.lines, holds=[hold.trigger for hold in scene_plan.holds], word_first=word_first)


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


def spec(scene_id: str, directory: Path = SCENE_DIRECTORY, *, word_first: bool = False) -> DirectedSpec:
    """The spec for a behavior scene by its id; `Unplayable` where there is none or it cannot be played."""

    plans = {item.scene.id: item for item in load_plans(directory)}
    if scene_id not in plans:
        raise Unplayable(f"no behavior scene is called {scene_id!r}: {', '.join(sorted(plans))}")
    chosen = plans[scene_id]
    if chosen.unplayable:
        playable = ", ".join(sorted(item.scene.id for item in plans.values() if not item.unplayable))
        raise Unplayable(f"{scene_id} cannot be played on Discord: {chosen.unplayable}. Playable: {playable}")
    return DirectedSpec(chosen, script_for(chosen, word_first=word_first))


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


def graded_moments(scene: Scene, deliveries: Sequence[Mapping[str, Any]], *, live: bool = False) -> list[dict[str, Any]]:
    """One entry per graded moment, with what the scene expects and what the script is to do, before it is judged.

    A live run has no script, so ``scripted`` and ``scripted_action`` are None
    there: nothing is expected of the agent but what the scene fits.
    ``facts`` are the moment's own, in the scene's words, in the order
    ``cited`` reads them.
    """

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
                "facts": [fact["fact"] for fact in moment.notice],
                "scripted": None if live else SceneScript.intended(moment),
                "scripted_action": None if live else scripted_action(moment, delivery.get("event_id")),
            }
        )
    return entries


def _line_record(line: Line) -> dict[str, Any]:
    return {
        "event": line.event,
        "trigger": line.trigger,
        "kind": line.kind,
        "text": line.text,
        "reaction": line.reaction,
        "cue": line.cue,
    }


def _hold_scene(
    leg: Any,
    spec: Hold,
    trigger: dict[str, Any],
    events: Mapping[str, Mapping[str, Any]],
    post: Any,
    settle_seconds: float,
) -> dict[str, Any]:
    """Hold the turn on ``spec.trigger``: wait until the model is asked about it, post what lands in it, release it, let the room settle.

    The held messages are posted one after another, each waited on until
    Nunchi has taken it in (``leg.deliver``), so that the release comes after
    all of them have arrived. Each is stamped when it had (``delivered_at``),
    and the gate stamps the release: `hold_outcome` compares the two. The wait
    for the room to go quiet is one wait, recorded on the trigger and on every
    held message.
    """

    gate = leg.script.gates[spec.trigger]
    asked = gate.wait_asked(HOLD_ASK_SECONDS)
    arrived = []
    for event in spec.events:
        delivery = post(events[event], None)
        delivery["phase"] = "live"
        delivery["delivered_at"] = timestamp(datetime.now(timezone.utc))
        delivery["held_for"] = spec.trigger
        arrived.append(delivery)
    gate.release()
    settled = leg.settle(settle_seconds)
    for delivery in (trigger, *arrived):
        delivery["settled"] = settled
    return {
        "trigger": spec.trigger,
        "kind": spec.kind,
        "moment": spec.moment,
        "events": list(spec.events),
        "asked": asked,
        "held": [
            {"event": delivery["scene_event"], "event_id": delivery["event_id"], "observed": bool(delivery.get("observed")),
             "delivered_at": delivery["delivered_at"]}
            for delivery in arrived
        ],
    }


def _when(value: Any) -> datetime | None:
    """A recorded time (the director's ``...Z`` stamps and the wire's ``+00:00`` ones) as a moment, or None."""

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _wait_begun(leg: Any, event_id: str, timeout: float) -> bool:
    """Live: until the column's turn has begun on ``event_id`` (``leg.begun``, the earliest signal it has), or ``timeout``."""

    deadline = time.monotonic() + timeout
    while True:
        leg.refresh()
        if leg.begun(event_id):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(BEGUN_POLL_SECONDS)


def _hold_live(
    leg: Any,
    spec: Hold,
    trigger: dict[str, Any],
    events: Mapping[str, Mapping[str, Any]],
    post: Any,
    settle_seconds: float,
) -> dict[str, Any]:
    """Live: post the held messages as soon as the column's turn on ``spec.trigger`` has begun, and let the room settle.

    Nothing holds the live agent (there is no gate in front of a live model), so
    whether the messages land in its turn is timing: each is posted when the turn
    has begun, and waited on until Nunchi has taken it in (``leg.deliver``), which
    stamps ``delivered_at``. `live_hold_outcome` compares that with when the agent
    moved. A turn that never began within `HOLD_ASK_SECONDS` leaves the messages
    posted all the same, so the scene goes on, and the hold reads ``never-asked``.
    """

    began = _wait_begun(leg, trigger["event_id"], HOLD_ASK_SECONDS)
    began_at = timestamp(datetime.now(timezone.utc)) if began else None
    arrived = []
    for event in spec.events:
        delivery = post(events[event], None)
        delivery["phase"] = "live"
        delivery["delivered_at"] = timestamp(datetime.now(timezone.utc))
        delivery["held_for"] = spec.trigger
        arrived.append(delivery)
    settled = leg.settle(settle_seconds)
    for delivery in (trigger, *arrived):
        delivery["settled"] = settled
    return {
        "trigger": spec.trigger,
        "kind": spec.kind,
        "moment": spec.moment,
        "events": list(spec.events),
        "asked": began,
        "began_at": began_at,
        "live": True,
        "held": [
            {"event": delivery["scene_event"], "event_id": delivery["event_id"], "observed": bool(delivery.get("observed")),
             "delivered_at": delivery["delivered_at"]}
            for delivery in arrived
        ],
    }


def line_landing(line: Mapping[str, Any] | Line, event_id: str | None, invocations: Sequence[Mapping[str, Any]], committed: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Live: whether the agent made the kind of move the scene's earlier line is, on the message that triggers it, and what it did.

    A reply or a plain post answers, a reaction nods (`LINE_ACTIONS`); the
    words and the emoji are the agent's own and are not compared with the
    scene's. ``did`` says in words what the agent did there, for the summary;
    ``problems`` is empty when it landed. Only an action that reads ``sent`` counts.
    """

    kind = line.kind if isinstance(line, Line) else line["kind"]
    turns = [turn for turn in invocations if event_id and turn.get("trigger") == event_id]
    requests = {turn["request_id"] for turn in turns}
    actions = [dict(action) for action in committed if action.get("request_id") in requests]
    sent = [action for action in actions if action.get("delivery") == "sent"]
    fitting = [action for action in sent if action.get("kind") in LINE_ACTIONS[kind]]
    wanted = "a reaction" if kind == "reaction" else "a reply or a post"
    if event_id is None:
        did, problems = "the message that triggers it was never posted", ["the scene stopped before the message that triggers it was posted"]
    elif not turns:
        did, problems = "nothing: no turn began on it", [f"no turn began on it, so the agent made no move there (the scene has {wanted})"]
    elif not sent:
        ended = "ended in silence" if not actions else "made an action that was not delivered"
        did, problems = f"the turn {ended}", [f"the turn on it {ended}, where the scene has {wanted}"]
    elif not fitting:
        did = "; ".join(checks_module._describe(action) for action in sent)
        problems = [f"it made {did} where the scene has {wanted}"]
    else:
        did, problems = checks_module._describe(fitting[0]), []
    return {"landed": not problems, "did": did, "problems": problems, "turns": sorted(requests), "actions": sent}


def _live_line(leg: Any, line: Line, delivery: Mapping[str, Any]) -> dict[str, Any] | None:
    """Live: after the room went quiet on a line's trigger, did the agent make the move? None if it did; otherwise why the scene stops."""

    leg.refresh()
    landing = line_landing(line, delivery.get("event_id"), leg.invocations, leg.committed)
    if landing["landed"]:
        return None
    return {"after": delivery.get("scene_event"), "line": line.event, "why": "; ".join(landing["problems"])}


def play_scene(leg: Any, scene_plan: Plan, settle_seconds: float, pace: float = 0.0, *, live: bool = False) -> dict[str, Any]:
    """Play a scene on the leg's Discord room and return the record of what was posted, not yet judged.

    ``leg`` posts a message with ``deliver(raw, at, scene, sequence)`` (``at``
    None for the room's own time) and waits for the room to go quiet with
    ``settle(seconds)``; ``leg.discord`` holds the stand-in. History goes
    first, oldest first, backdated; the room's clock is then moved to the
    wall; each live event follows after the room settled, ``pace`` times the
    scene's own gap later. Where the leg has a `SceneScript`, each graded
    message's text is told to it before it is posted, and so is the text of
    each message that triggers a line of the agent's. A scene's own events of
    the agent's are not posted: the agent says them as its move on the message
    that triggers them, and a line that answers nothing is cued by a message
    the director adds just before it. A held turn (`Hold`) is posted into
    (`_hold_scene`). A wait that timed out is recorded in its delivery
    (``settled``) and listed in ``unsettled`` (a scripted run fails on it:
    `checks.unsettled`).

    ``live`` plays the scene with a live model behind the column (module doc):
    no script is told anything and no gate holds a turn. After the room settles
    on a message that triggers a line of the agent's, the director checks that
    the agent made that kind of move (`line_landing`); if it did not, the scene
    stops there (``stopped``), since everything after would be judged against a
    history the agent did not have. A held turn is posted into as soon as the
    column's turn has begun (`_hold_live`).
    """

    if scene_plan.unplayable:
        raise Unplayable(f"{scene_plan.scene.id} cannot be played on Discord: {scene_plan.unplayable}")
    scene = scene_plan.scene
    room = leg.discord
    script = getattr(leg, "script", None)
    graded = {moment.event for moment in scene.moments if moment.event}
    # The script is told the text of every message it must tell apart: the graded ones and those that trigger a line.
    known = graded | {line.trigger for line in scene_plan.lines}
    spoken = {line.event for line in scene_plan.lines}
    line_at = {line.trigger: line for line in scene_plan.lines}
    cues = {cue["before"]: cue for cue in scene_plan.cues}
    holds = {hold.trigger: hold for hold in scene_plan.holds}
    landing = {event for hold in scene_plan.holds for event in hold.events}
    events = {event["id"]: event for event in scene.events}
    offsets = dict(zip((event["id"] for event in scene.events), _offsets(scene)))
    anchor = offsets[scene_plan.live[0]["id"]]
    now = datetime.now(timezone.utc)
    deliveries: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []
    stopped: dict[str, Any] | None = None

    def post(raw: Mapping[str, Any], at: datetime | None) -> dict[str, Any]:
        if not live and isinstance(script, SceneScript) and raw["id"] in known:
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
        if raw["id"] in spoken:
            # The agent's own event: its turn on the message it answers plays it. One that answers nothing is cued here.
            cue = cues.get(raw["id"])
            if cue is not None:
                delivery = post({key: cue[key] for key in ("id", "author", "mentions", "text")}, None)
                delivery["phase"], delivery["cue"] = "live", True
                delivery["settled"] = leg.settle(settle_seconds)
                stopped = _live_line(leg, line_at[cue["id"]], delivery) if live else None
                if stopped:
                    break
            continue
        if raw["id"] in landing:
            continue  # posted while its turn was held
        if previous is not None and pace > 0:
            time.sleep(max(0, offsets[previous] - offsets[raw["id"]]) * pace)
        delivery = post(raw, None)
        delivery["phase"] = "live"
        if raw["id"] in holds:
            held.append((_hold_live if live else _hold_scene)(leg, holds[raw["id"]], delivery, events, post, settle_seconds))
        else:
            delivery["settled"] = leg.settle(settle_seconds)
        if live and raw["id"] in line_at:
            stopped = _live_line(leg, line_at[raw["id"]], delivery)
            if stopped:
                break
        previous = raw["id"]
    entries = graded_moments(scene, deliveries, live=live)
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
    if live:
        played["played_live"] = True
        if stopped:
            played["stopped"] = stopped
    if scene_plan.lines:
        # What the scene says the agent said earlier, how it was played (cues), and how much of the scene's time was compressed.
        played["lines"] = [_line_record(line) for line in scene_plan.lines]
        played["cues"] = [dict(cue) for cue in scene_plan.cues]
        played["compressed"] = scene_plan.compressed
    if held:
        played["holds"] = held
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


def hold_outcome(hold: Mapping[str, Any]) -> tuple[str, str]:
    """How a hold went, and why, from the record the director and the gate kept.

    ``held``: the model was asked about the turn, every held message had
    reached Nunchi before the director released it, and the core showed the
    turn the page that holds them. ``never-asked``: the model was never asked
    about the turn, so nothing was held. ``raced``: the turn went on before a
    held message reached Nunchi (the model's wait ran out, or the release came
    before the message had arrived): the moment was not played as scripted,
    which is the run's fault and not a miss. ``unseen``: the messages reached
    Nunchi in time and the core did not show them to the turn before it posted,
    which is the column's miss. (An ``unattended`` hold that held can still be
    ``unmerged``, which `judge_scene` decides from the graded turn: see there.)
    """

    trigger = hold.get("trigger")
    gate = hold.get("gate") or {}
    if not hold.get("asked") or not gate.get("asked_at"):
        return "never-asked", f"the model was never asked about the turn on {trigger}, so nothing was held"
    released = str(gate.get("released_at") or "")
    if not released:
        return "raced", f"the turn on {trigger} was still held when the scene ended: the director never released it"
    if gate.get("released_by") == "timeout":
        return "raced", f"the model's wait for the turn on {trigger} ran out, so the turn went on without the held message(s)"
    late = [
        str(item.get("event"))
        for item in hold.get("held", ())
        if not item.get("observed") or str(item.get("delivered_at") or "~") > released
    ]
    if late:
        return "raced", f"the turn on {trigger} was released before {', '.join(late)} reached Nunchi"
    shown = set(hold.get("shown") or ())
    unseen = [str(item.get("event")) for item in hold.get("held", ()) if item.get("event_id") not in shown]
    if unseen:
        return "unseen", (
            f"{', '.join(unseen)} reached Nunchi before the turn on {trigger} was released, and the core did not show the turn "
            "a page that holds it before the turn posted"
        )
    return "held", f"{', '.join(str(item.get('event')) for item in hold.get('held', ()))} reached Nunchi while the turn on {trigger} was held, and the core showed the turn them"


def _judge_holds(leg: Any, record: dict[str, Any]) -> None:
    """Add to each hold the gate's own record, the held messages the turn was shown, and how the hold went (`hold_outcome`)."""

    gates = getattr(getattr(leg, "script", None), "gates", None) or {}
    for hold in record.get("holds", ()):
        gate = gates.get(hold["trigger"])
        hold["gate"] = gate.document() if gate is not None else {}
        hold["shown"] = gate.shown(item["event_id"] for item in hold["held"]) if gate is not None else []
        hold["outcome"], hold["detail"] = hold_outcome(hold)


def _line_problems(line: Mapping[str, Any], event_id: str | None, actions: Sequence[Mapping[str, Any]]) -> list[str]:
    """How the delivered ``actions`` of the turn on a line's trigger differ from the one the scene has, in words (none when it landed)."""

    delivered = [action for action in actions if action.get("delivered")]
    if len(delivered) != 1:
        return [f"it delivered {len(delivered)} action(s), not the one scripted {line['kind']}"]
    action, problems = delivered[0], []
    # A reaction and a reply are about the message they answer (``target_event_id``), a cue's answer by the turn it began on (``origin_event_id``).
    about = "origin_event_id" if line["kind"] == "message" else "target_event_id"
    expected = {"kind": "reaction", "reaction": line["reaction"]} if line["kind"] == "reaction" else {"kind": line["kind"], "text": line["text"]}
    for key, value in expected.items():
        if action.get(key) != value:
            problems.append(f"its {key} is {str(action.get(key))[:80]!r}, not the scene's {str(value)[:80]!r}")
    if action.get(about) != event_id:
        problems.append(f"its {about} is {action.get(about)}, not the message that triggers it, {event_id}")
    return problems


def _judge_lines(leg: Any, record: dict[str, Any]) -> set[str]:
    """Check that each of the agent's earlier lines landed exactly as the scene has it; the request ids of the turns that played them.

    A line is the agent's scripted move on a message (`standin.Line`), so its
    turn must have begun on that message and delivered exactly one action: the
    scene's words as a reply to it (or a post, for a cue), or its reaction on
    it. Nothing is graded here: a line that does not land fails the run
    (`checks.directed_outcomes`), since the moments after it would be judged
    against a history the agent never had.
    """

    native = {delivery["scene_event"]: delivery["event_id"] for delivery in record["deliveries"]}
    played: set[str] = set()
    for line in record.get("lines", ()):
        event_id = native.get(line["trigger"])
        turns = [turn for turn in leg.invocations if event_id and turn.get("trigger") == event_id]
        requests = {turn["request_id"] for turn in turns}
        played |= requests
        actions = [action for action in leg.committed if action.get("request_id") in requests]
        problems = _line_problems(line, event_id, actions)
        if not turns:
            problems.insert(0, f"no turn began on {line['trigger']}, so the agent never got to say it")
        line.update(event_id=event_id, turns=sorted(requests), actions=[_summary(action) for action in actions], problems=problems)
    return played


def live_hold_outcome(hold: Mapping[str, Any]) -> tuple[str, str]:
    """Live: how a hold went, from when each held message reached Nunchi and when the agent moved.

    Nothing held the live agent, so this is timing. ``held``: the column's turn
    began on the trigger, every held message reached Nunchi, and each did so
    before the agent's move reached the room (or, if it made none, before the
    turn ended). ``raced``: the agent moved first, or a held message never
    reached Nunchi: the moment was not played as the scene has it, which is not a
    miss and leaves the moment's grade aside. ``unseen``: they reached Nunchi in
    time, the agent made a move, and the column's own record shows the turn was
    never shown them (only where it shows what the turn was shown: ``shown`` is
    None in a column whose record does not). ``never-asked``: no turn began on
    the trigger, so nothing was held. The times are the director's, the harness's
    own turn record, and the stand-in's wire, each to the millisecond; the
    director looks for a turn to begin about every `BEGUN_POLL_SECONDS` and a
    receipt-reading column is read about every 0.1 s, so a difference of that
    order is a tie that reads ``held``.
    """

    trigger = hold.get("trigger")
    if not hold.get("asked"):
        return "never-asked", f"no turn began on {trigger} within {HOLD_ASK_SECONDS:.0f} s, so nothing was held"
    turn = hold.get("turn") or {}
    moved = _when(turn.get("moved_at"))
    ended = _when(turn.get("ended"))
    limit, what = (moved, "moved") if moved is not None else (ended, "ended")
    unreached = [str(item.get("event")) for item in hold.get("held", ()) if not item.get("observed")]
    if unreached:
        return "raced", f"{', '.join(unreached)} never reached Nunchi, so it was not held in the turn on {trigger}"
    packet = set(turn.get("first_packet") or ())
    early = [str(item.get("event")) for item in hold.get("held", ()) if item.get("event_id") in packet]
    if early:
        return "raced", (
            f"{', '.join(early)} was already in the first packet handed to the agent for the turn on {trigger}: it reached Nunchi "
            "before the turn began, so it did not arrive while the turn was under way"
        )
    late = [
        (str(item.get("event")), item.get("delivered_at"))
        for item in hold.get("held", ())
        if limit is not None and (_when(item.get("delivered_at")) or limit) > limit
    ]
    if late:
        names = "; ".join(f"{event} reached Nunchi at {at}" for event, at in late)
        return "raced", f"the agent's turn on {trigger} {what} at {(turn.get('moved_at') or turn.get('ended'))}, before {names}"
    unfinished = "" if limit is not None else " (the turn had not ended when the scene's wait ran out)"
    names = ", ".join(str(item.get("event")) for item in hold.get("held", ()))
    shown = hold.get("shown")
    if shown is None:
        return "held", (
            f"{names} reached Nunchi while the turn on {trigger} was under way{unfinished}; "
            "this column's record does not show whether the turn was shown them"
        )
    unseen = [str(item.get("event")) for item in hold.get("held", ()) if item.get("event_id") not in shown]
    if unseen and moved is not None:
        return "unseen", (
            f"{', '.join(unseen)} reached Nunchi before the agent's move on {trigger}, and the column's record shows the turn was "
            "never shown them before it posted"
        )
    note = " (the turn ended in silence and was not shown them)" if unseen else ""
    return "held", f"{names} reached Nunchi while the turn on {trigger} was under way{unfinished}{note}"


def _judge_holds_live(leg: Any, record: dict[str, Any]) -> None:
    """Live: add to each hold the turn it landed in, what the turn was shown where the column's record says, and how it went."""

    native = {delivery["scene_event"]: delivery["event_id"] for delivery in record["deliveries"]}
    for hold in record.get("holds", ()):
        event_id = native.get(hold["trigger"])
        turns = [turn for turn in leg.invocations if event_id and turn.get("trigger") == event_id]
        requests = {turn["request_id"] for turn in turns}
        delivered = [action for action in leg.committed if action.get("request_id") in requests and action.get("delivered")]
        moves = [_when(action.get("at")) for action in delivered if _when(action.get("at")) is not None]
        started = min((turn["started"] for turn in turns if turn.get("started")), default=None)
        hold["turn"] = {
            "requests": sorted(requests),
            "started": started,
            "ended": max((turn["ended"] for turn in turns if turn.get("ended")), default=None),
            "moved_at": min(moves).isoformat(timespec="milliseconds") if moves else None,
            "acted": bool(delivered),
        }
        # The messages the turn was handed with: one of the held messages among them reached Nunchi before the turn began.
        hold["turn"]["first_packet"] = sorted({event for turn in turns for event in turn.get("first_packet") or ()})
        # What the turn was shown, from its start to the moment it moved (or, if it never did, ended): a later turn of the same
        # transcript, handed the held message in its own wake, shows nothing of this one.
        until = hold["turn"]["moved_at"] or hold["turn"]["ended"]
        hold["shown"] = leg.shown_to_turn([item["event_id"] for item in hold["held"]], started, until) if started else None
        hold["outcome"], hold["detail"] = live_hold_outcome(hold)


def _judge_lines_live(leg: Any, record: dict[str, Any]) -> set[str]:
    """Live: check that the agent made each of the scene's earlier lines' kind of move on the message that triggers it; the turns that played them.

    Nothing here is graded or compared with the scene's words: a line that did
    not land makes the moments after it ``precondition not met``
    (`judge_scene`), and what the agent did there is reported
    (``did``, ``actions``, ``problems``).
    """

    native = {delivery["scene_event"]: delivery["event_id"] for delivery in record["deliveries"]}
    played: set[str] = set()
    for line in record.get("lines", ()):
        event_id = native.get(line["trigger"])
        landing = line_landing(line, event_id, leg.invocations, leg.committed)
        played |= set(landing["turns"])
        line.update(
            event_id=event_id,
            live=True,
            landed=landing["landed"],
            did=landing["did"],
            turns=landing["turns"],
            actions=[_summary(action) for action in leg.committed if action.get("request_id") in set(landing["turns"])],
            problems=landing["problems"],
        )
    return played


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
    from the one the script makes (`_off_script`) and, where the script acts, a
    message that no turn began on (a later turn only listed it as unattended);
    the record's ``other_actions`` are every committed action outside the
    graded turns. ``leg`` supplies ``invocations`` (the turns, each with its
    ``trigger`` and any ``unattended`` messages), ``committed`` (the actions,
    ``delivered`` once judged) and ``attention_calls``.

    A live scene (``record["played_live"]``) is graded the same way from what
    the live agent did, with no script to hold it to: ``off_script`` is empty
    and the record's ``other_actions`` are only reported. Where the setup the
    scene needs was not made, a line of the agent's that did not land or a hold
    no turn began for, the moments are not graded: ``grade`` is None and
    ``precondition`` says what the agent did instead, and the record reads
    `checks.PRECONDITION`. A hold that raced (`live_hold_outcome`) is not a miss.
    """

    native = {delivery["scene_event"]: delivery["event_id"] for delivery in record["deliveries"]}
    live = bool(record.get("played_live"))
    # The turns that play the agent's own earlier lines are the scene's setup: checked to have landed, not graded.
    played = _judge_lines_live(leg, record) if live else _judge_lines(leg, record)
    (_judge_holds_live if live else _judge_holds)(leg, record)
    holds = {hold["moment"]: hold for hold in record.get("holds", ())}
    # Live: the setup the scene needs that the agent did not make. It gates every graded moment of the scene, since the
    # lines come before them and the scene stops at the first one that did not land.
    unmet = [
        f"the agent's earlier line {line.get('event')} (on {line.get('trigger')}) did not land: {line.get('did')}"
        for line in record.get("lines", ())
        if live and line.get("problems")
    ] + [
        f"{hold.get('detail')}" for hold in record.get("holds", ()) if live and hold.get("outcome") == "never-asked"
    ]
    observes = getattr(leg, "observes_unattended", True)
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
        # An attention call that failed judged nothing: the agent was woken by the error fallback, which is not attention's
        # reading of the message and must not be graded as a wake (step 1).
        errored = bool(call and call.get("error"))
        failed = any(not action.get("delivered") for action in actions)
        result, by = attention, None
        if item["reached"] and (own or (attention == "woken" and turns)):
            result, by = ("woken", None) if failed else (agent_move(actions), "agent")
        elif attention == "stay_quiet":
            by = "attention"
        evidence = set((call or {}).get("evidence") or ())
        allowed = {event_id, *(turn.get("trigger") for turn in turns)}
        off_script = [] if live else _off_script(item.get("scripted_action"), actions, event_id, allowed)
        if item["reached"] and item.get("scripted_action") is not None and turns and not own:
            # The script acts here, so the agent must have taken this message as a moment of its own. A later turn that only listed
            # it as unattended read it with another message: one action there cannot stand for two moments.
            folded = ", ".join(sorted({str(turn.get("trigger")) for turn in turns}))
            off_script.append(f"no turn began on it: it was only folded into the turn on {folded} as an unattended message")
        item.update(
            result=result,
            by=by,
            # A turn on a message nothing judged was not read by step 1.
            grade=None if unmet else grade(moment, result, attention="not judged" if attention == "unsupported" or errored else attention),
            provider_error=failed,
            cited=[bool(evidence & {native[event] for event in fact["events"] if event in native}) for fact in moment.notice],
            turns=sorted(requests),
            actions=[_summary(action) for action in actions],
            off_script=off_script,
        )
        if unmet:
            item["precondition"] = list(unmet)
        if errored:
            item["attention_error"] = str(call["error"])[:200]
        why = moment.miss_reason(result)
        if why and not unmet:
            item["why"] = why
        hold = holds.get(item["event"])
        if hold is not None and hold["kind"] == "unattended" and hold["outcome"] == "held":
            # The moment is the scene's: the messages that arrived while the agent was busy are read with it, as one moment, and
            # only with it. A turn that did not list them as unattended read the moment on its own, and they were judged before
            # it; a message that also started a turn of its own was read twice.
            listed = {event for turn in own for event in turn.get("unattended") or ()}
            if observes:
                apart = [event for event in moment.unattended if native.get(event) not in listed]
            else:
                # A column that does not show which messages a turn read as unattended (the reference, out of process, live): a message
                # that began a turn of its own was judged on its own.
                apart = [event for event in moment.unattended if any(turn.get("trigger") == native.get(event) for turn in leg.invocations)]
            twice = [
                event
                for event in moment.unattended
                if observes and event not in apart and any(turn.get("trigger") == native.get(event) for turn in leg.invocations)
            ]
            if apart or twice:
                hold["outcome"] = "unmerged"
                hold["detail"] = "; ".join(
                    [
                        *(
                            f"{event} arrived while the agent was busy, but the turn on {item['event']} did not list it as unattended: "
                            "it was judged on its own, so the moment was not read as the scene has it"
                            if observes
                            else f"{event} arrived while the agent was busy but began a turn of its own: it was judged on its own, so the "
                            "moment was not read as the scene has it"
                            for event in apart
                        ),
                        *(
                            f"{event} was read with {item['event']} as unattended and also started a turn of its own: "
                            "the moment was not read as the scene has it"
                            for event in twice
                        ),
                    ]
                )
        if hold is not None:
            item["hold"] = hold["outcome"]
            if live and hold["outcome"] == "held" and hold.get("shown") is None:
                # The column's record cannot show whether the turn was shown the held messages (the reference's, out of process):
                # `held` is then timing alone, and the matrix and the summary say so.
                item["hold_unproven"] = True
        started.update({turn["request_id"]: turn for turn in turns})
        shown += item["actions"]
    record["turns"] = list(leg.invocations)
    record["graded_turns"] = len(started)
    record["graded_wake_sources"] = [turn.get("source") for turn in started.values()]
    record["other_turns"] = sum(1 for turn in leg.invocations if turn["request_id"] not in started and turn["request_id"] not in played)
    # What the agent did on the messages nobody graded: the script is silent there. Its earlier lines are the exception.
    record["other_actions"] = [
        _summary(action) for action in leg.committed if action.get("request_id") not in started and action.get("request_id") not in played
    ]
    record["actions"] = shown
    record["posts"] = [
        {"text": action.get("text"), "delivery": action.get("delivery"), "delivered": bool(action.get("delivered"))}
        for action in shown
        if action.get("kind") in ("message", "reply")
    ]
    outcomes = {hold["outcome"] for hold in record.get("holds", ())}
    if live:
        # Reported, never failed: a setup the agent did not make is named, and a hold that raced is not a miss.
        if unmet:
            record["outcome"] = checks_module.PRECONDITION
        elif not record["reached"]:
            record["outcome"] = checks_module.NOT_DELIVERED
        elif "raced" in outcomes:
            record["outcome"] = checks_module.RACED
        elif all(item["grade"]["visible"] == "fits" and item["grade"]["step1"] == "ok" for item in record["graded"]) and outcomes <= {"held"}:
            record["outcome"] = checks_module.FITS
        else:
            record["outcome"] = checks_module.MISSES
        return
    if not record["reached"]:
        record["outcome"] = checks_module.NOT_DELIVERED
    elif "raced" in outcomes:
        # The turn went on before a held message reached Nunchi: not played as scripted, and not a miss.
        record["outcome"] = checks_module.RACED
    elif (
        all(item["grade"]["visible"] == "fits" and item["grade"]["step1"] == "ok" and not item["off_script"] for item in record["graded"])
        and not record["other_actions"]
        and not any(line.get("problems") for line in record.get("lines", ()))
        and outcomes <= {"held"}
    ):
        record["outcome"] = checks_module.FITS
    else:
        record["outcome"] = checks_module.MISSES
