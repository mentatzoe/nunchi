"""Conformance for the agent's turn, through any integration (#94 step 9d).

Every harness must give its agent the same turn (`docs/harness-contract.md`).
This kit checks that: a scripted agent plays a scenario's turns through an
integration's real path, and the kit compares what the room and the agent saw
with what the turn's rules say. The results make the parity table.

Most scenarios are one turn, started by a message. Two have a second turn that
the library starts itself, with no new message: after a pause, when it looks
again at a moment it waited on, and after an operator approves an action the
agent proposed, when it gives the agent a turn about the outcome.

An integration takes part by providing a `KitIntegration`: the participant the
shared turn host invokes, wired so that when its agent is started the scripted
agent's steps go through the integration's own surface (its tool calls, its
socket, its hooks). The kit owns the room, attention, the host, and the checks.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import threading
from typing import Any, Protocol

from .attention import AttentionPolicy, ParticipantProfile
from .conformance import fixture_attention_model, fixture_binding, fixture_profile
from .observation import ObservationLimits
from .participant import TransportResult
from .room import Room, RoomSettings
from .turn import HARNESS_DELIVERS, HarnessDelivery, SecretGuard, Turn, TurnDriver, TurnParticipant

PERSON = "conformance:person"
TRIGGER = "conformance:message:1"
SECRET = "conformance-withheld-secret-value"
SILENCE = "[SILENT]"
# What the agent posts after a pause, and when it reports an outcome.
LOOKED_AGAIN = "Still stuck? I can take a look."
REPORTED = "Done: the runbook is in the README."
OPERATOR = "operator:conformance"
# The privileged action the outcome scenarios propose, and the policy that
# lets the person ask for it with an operator's approval.
CAPABILITY = "workspace.file.write"
PROPOSAL = {
    "capability": CAPABILITY,
    "resource": {"kind": "workspace-file", "id": "repo:README.md"},
    "operation": {"path": "README.md", "content": "The deploy runbook."},
}

# Each step is what the agent does next: ("bind",), ("read",), the turn's text
# as the agent received it, ("call", role, arguments), ("after_tool",),
# ("finish", answer), ("end", ok) or ("end", ok, last_words); or what happens
# around it: ("arrive", text), someone posts; ("cancel",), the library
# cancels the turn.
Step = tuple


@dataclass(frozen=True)
class Scenario:
    """One scenario: the first turn's steps, and a second turn the library may start.

    ``next_occasion`` names what starts the second turn: ``"pause"``, the room
    stays quiet after a moment the agent waited on, and the library looks
    again; ``"outcome"``, an operator approves the action the agent proposed
    in its first turn. The agent plays ``next_steps`` in that turn.
    """

    posting: str
    description: str
    steps: tuple[Step, ...]
    check: Callable[["Played"], list[str]]
    next_occasion: str | None = None
    next_steps: tuple[Step, ...] = ()


@dataclass
class Played:
    """What happened in one scenario's turn."""

    answers: list[tuple[Step, Any]] = field(default_factory=list)
    dispatched: list[dict[str, Any]] = field(default_factory=list)
    host_result: TransportResult | None = None
    own_moves: list[dict[str, Any]] = field(default_factory=list)
    arrivals: list[str] = field(default_factory=list)
    # The privileged operations the room's executor ran.
    executed: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def answer(self, index: int) -> Any:
        return self.answers[index][1]


class TurnSurface(Protocol):
    """How a scripted agent reaches its turn through one integration."""

    def bind(self, turn_id: str) -> bool: ...
    def read(self, turn_id: str) -> str: ...
    def call(self, turn_id: str, role: str, arguments: Mapping[str, Any]) -> tuple[bool, str]: ...
    def after_tool(self, turn_id: str) -> str | None: ...
    def finish(self, turn_id: str, answer: str) -> tuple[str, str]: ...
    def end(self, turn_id: str, ok: bool, note: str | None = None) -> None: ...


class KitIntegration(Protocol):
    """An integration under test."""

    name: str
    posting: str

    def participant(self, *, profile: ParticipantProfile, guard: SecretGuard, agent: "ScriptedAgent") -> Any:
        """The participant the host invokes; starting its agent plays ``agent``.

        Every turn the library starts plays the agent's next turn. For the
        outcome scenarios the kit also passes ``privileged=True``: the room
        authorizes privileged actions, so the integration offers ``propose``
        and ``withdraw`` as it would with an ``authorization`` section.
        """

    def close(self) -> None: ...


class ScriptedAgent:
    """Plays a scenario's turns through an integration's surface, each in its own thread.

    ``steps`` is the first turn; ``later`` holds the turns the library starts
    after it. Each `play` plays the next turn. A turn the script does not
    have is counted in ``unexpected`` and not played.

    A call's argument written ``"@arrival:N"`` names the N-th message that
    arrived during the scenario, once it has arrived.
    """

    def __init__(
        self,
        steps: Sequence[Step],
        arrive: Callable[[str], str],
        cancel: Callable[[], None] | None = None,
        *,
        later: Sequence[Sequence[Step]] = (),
    ) -> None:
        self.turns = (tuple(steps), *(tuple(turn) for turn in later))
        self.steps = self.turns[0]
        self.arrive = arrive
        self.cancel = cancel
        self.arrivals: list[str] = []
        self.answers: list[tuple[Step, Any]] = []
        # Set when every turn's steps have played; `turn_done` per turn.
        self.done = threading.Event()
        self.turn_done = tuple(threading.Event() for _ in self.turns)
        self.unexpected = 0
        self.error: BaseException | None = None
        self._lock = threading.Lock()
        self._started = 0
        self._seen: list[Any] = []

    def play_once(self, key: Any, surface: Callable[[], "TurnSurface"]) -> None:
        """Play the next turn the first time ``key``, the harness's turn, is seen.

        For integrations that learn of a turn from something that repeats
        within it, such as each model request.
        """

        with self._lock:
            if any(seen is key for seen in self._seen):
                return
            self._seen.append(key)
        self.play(surface())

    def _arguments(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: self.arrivals[int(value.split(":")[1])]
            if isinstance(value, str) and value.startswith("@arrival:")
            else value
            for key, value in arguments.items()
        }

    def play(self, surface: TurnSurface, turn_id: str | None = None) -> None:
        with self._lock:
            index = self._started
            if index >= len(self.turns):
                self.unexpected += 1
                return
            self._started += 1
        steps = self.turns[index]
        turn_id = turn_id or f"turn-{index + 1}"

        def run() -> None:
            try:
                for step in steps:
                    kind = step[0]
                    if kind == "bind":
                        answer: Any = surface.bind(turn_id)
                    elif kind == "read":
                        answer = surface.read(turn_id)
                    elif kind == "call":
                        answer = surface.call(turn_id, step[1], self._arguments(step[2]))
                    elif kind == "after_tool":
                        answer = surface.after_tool(turn_id)
                    elif kind == "finish":
                        answer = surface.finish(turn_id, step[1])
                    elif kind == "arrive":
                        answer = self.arrive(step[1])
                        self.arrivals.append(answer)
                    elif kind == "cancel":
                        if self.cancel is None:
                            raise ValueError("this agent cannot cancel its turn")
                        answer = self.cancel()
                    elif kind == "end":
                        # The agent's last words, if the step has them.
                        answer = surface.end(turn_id, step[1], **({"note": step[2]} if len(step) > 2 else {}))
                    else:
                        raise ValueError(f"unknown step {kind!r}")
                    self.answers.append((step, answer))
            except BaseException as exc:  # recorded for the result
                self.error = exc
            finally:
                self.turn_done[index].set()
                if all(event.is_set() for event in self.turn_done):
                    self.done.set()

        threading.Thread(target=run, name="nunchi-scripted-agent", daemon=True).start()


# -- the reference integration: the core turn, called directly ---------------------


class _DirectSurface:
    def __init__(self, participant: TurnParticipant, turn: Turn) -> None:
        self.participant = participant
        self.turn = turn

    def bind(self, turn_id: str) -> bool:
        return self.participant.bind_turn(turn_id=turn_id, wake_id=self.turn.wake_id)

    def read(self, turn_id: str) -> str:
        return self.turn.text

    def call(self, turn_id: str, role: str, arguments: Mapping[str, Any]) -> tuple[bool, str]:
        return self.participant.call_tool(
            turn_id=turn_id, tool=self.participant.tool_names.get(role, role), arguments=dict(arguments)
        )

    def after_tool(self, turn_id: str) -> str | None:
        return self.participant.news(turn_id=turn_id)

    def finish(self, turn_id: str, answer: str) -> tuple[str, str]:
        decision = self.participant.finish(turn_id=turn_id, answer=answer)
        return decision.kind, decision.text

    def end(self, turn_id: str, ok: bool, note: str | None = None) -> None:
        # The harness reports its agent's end of turn, bound or not.
        self.participant.end_turn(turn_id=None, ok=ok, detail="scripted end", note=note)


class _DirectDriver(TurnDriver):
    def __init__(self, agent: ScriptedAgent) -> None:
        self.agent = agent
        self.participant: TurnParticipant | None = None

    def start(self, turn: Turn) -> None:
        assert self.participant is not None
        self.agent.play(_DirectSurface(self.participant, turn))

    def interrupt(self, turn: Turn) -> None:
        pass


class ReferenceIntegration:
    """The core turn with no harness around it: what every integration must match."""

    def __init__(self, posting: str = "tools") -> None:
        self.posting = posting
        self.name = f"reference ({posting})"

    def participant(
        self, *, profile: ParticipantProfile, guard: SecretGuard, agent: ScriptedAgent, privileged: bool = False
    ) -> Any:
        # The turn offers propose and withdraw only when the room authorizes them.
        driver = _DirectDriver(agent)
        participant = TurnParticipant(
            profile=profile,
            driver=driver,
            guard=guard,
            tool_names={role: role for role in ("send", "react", "propose", "withdraw", "context")},
            result_wait_seconds=5,
            silence_marker=SILENCE if self.posting == "final-answer" else None,
        )
        driver.participant = participant
        return participant

    def close(self) -> None:
        pass


# -- the scenarios -------------------------------------------------------------------


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def _texts(played: Played) -> list[str]:
    return [action.get("text", "") for action in played.dispatched]


def _check_post(played: Played) -> list[str]:
    failures: list[str] = []
    _expect(played.answer(0) is True, "the turn did not bind", failures)
    _expect(_texts(played) == ["On it."], f"expected one post, saw {_texts(played)}", failures)
    _expect(played.answer(1)[0] is True, "the tool call failed", failures)
    _expect("Done" in played.answer(1)[1], "the agent was not told the room accepted it", failures)
    return failures


def _check_bound_silence(played: Played) -> list[str]:
    failures: list[str] = []
    _expect(not played.dispatched, "a silent turn posted", failures)
    _expect(played.host_result is None, f"expected silence, host said {played.host_result}", failures)
    _expect(
        any(move.get("kind") == "silence" for move in played.own_moves),
        "the silence is not in the agent's memory",
        failures,
    )
    return failures


def _check_silence_reason(played: Played) -> list[str]:
    failures: list[str] = []
    _expect(not played.dispatched, f"a silent turn posted {_texts(played)}", failures)
    reasons = [move.get("why") for move in played.own_moves if move.get("kind") == "silence"]
    _expect(reasons == ["Castor was asked, not me."], f"the last words are not the silence's reason: {reasons}", failures)
    return failures


def _check_unbound_failure(played: Played) -> list[str]:
    failures: list[str] = []
    _expect(not played.dispatched, "an unbound turn posted", failures)
    _expect(
        played.host_result is not None and played.host_result.delivery == "failed",
        f"an unbound turn must fail, host said {played.host_result}",
        failures,
    )
    _expect(
        not any(move.get("kind") == "silence" for move in played.own_moves),
        "an unbound turn was remembered as silence",
        failures,
    )
    return failures


def _check_look_again(played: Played) -> list[str]:
    failures: list[str] = []
    held = played.answer(2)
    _expect(held[0] is True and held[1].startswith("Not posted yet"), f"the first post was not held: {held}", failures)
    _expect(_texts(played) == ["Never mind, then."], f"expected only the second post, saw {_texts(played)}", failures)
    return failures


def _check_steering(played: Played) -> list[str]:
    failures: list[str] = []
    update = played.answer(3)
    _expect(isinstance(update, str) and "use the staging box" in update, f"no steering update: {update!r}", failures)
    _expect(played.answer(4) is None, "the same update was shown twice", failures)
    posted = played.dispatched[0] if played.dispatched else {}
    _expect(posted.get("kind") == "reply", f"expected one reply, saw {played.dispatched}", failures)
    _expect(
        played.arrivals and posted.get("target_event_id") == played.arrivals[0],
        "the reply does not answer the message shown by steering",
        failures,
    )
    return failures


def _check_one_action(played: Played) -> list[str]:
    failures: list[str] = []
    _expect(_texts(played) == ["First."], f"expected one post, saw {_texts(played)}", failures)
    _expect(played.answer(2)[0] is False, "a second room action was accepted", failures)
    return failures


def _check_secret(played: Played) -> list[str]:
    failures: list[str] = []
    refused = played.answer(1)
    _expect(refused[0] is False and "secret" in refused[1], f"the secret was not refused: {refused}", failures)
    _expect(not played.dispatched, "a secret reached the room", failures)
    return failures


def _check_cancel(played: Played) -> list[str]:
    failures: list[str] = []
    _expect(not played.dispatched, f"a cancelled turn posted {_texts(played)}", failures)
    _expect(played.answer(2)[0] is False, "the post was accepted after the cancel", failures)
    _expect(played.host_result is None, f"expected nothing committed, host said {played.host_result}", failures)
    return failures


def _check_final_cancel(played: Played) -> list[str]:
    failures: list[str] = []
    _expect(played.answer(2) == ("silent", ""), f"expected silence after the cancel, saw {played.answer(2)}", failures)
    _expect(not played.dispatched, f"a cancelled turn committed {_texts(played)}", failures)
    return failures


def _later_turn(played: Played, failures: list[str], *, occasion: str, bound: int, shown: int) -> None:
    """The second turn reached the agent, bound, and told it why it came."""

    _expect(played.answer(bound) is True, f"the {occasion} turn did not bind", failures)
    text = played.answer(shown)
    _expect(
        isinstance(text, str) and f'"occasion":"{occasion}"' in text,
        f"the turn's text does not give its occasion, {occasion}",
        failures,
    )


def _check_pause(played: Played) -> list[str]:
    failures: list[str] = []
    _expect(played.answer(0) is True, "the first turn did not bind", failures)
    _later_turn(played, failures, occasion="pause", bound=2, shown=3)
    _expect(played.answer(4)[0] is True, f"the post after the pause failed: {played.answer(4)}", failures)
    _expect(_texts(played) == [LOOKED_AGAIN], f"expected only the post after the pause, saw {_texts(played)}", failures)
    return failures


def _check_outcome(played: Played) -> list[str]:
    failures: list[str] = []
    proposed = played.answer(1)
    _expect(proposed[0] is True, f"the proposal was refused: {proposed}", failures)
    _expect(played.executed == [PROPOSAL["operation"]], f"the approved action did not run: {played.executed}", failures)
    _later_turn(played, failures, occasion="outcome", bound=3, shown=4)
    _expect('"status":"done"' in str(played.answer(4)), "the agent was not told the action ran", failures)
    _expect(played.answer(5)[0] is True, f"the report failed: {played.answer(5)}", failures)
    _expect(_texts(played) == [REPORTED], f"expected only the agent's report, saw {_texts(played)}", failures)
    return failures


def _check_final_pause(played: Played) -> list[str]:
    failures: list[str] = []
    _expect(played.answer(1)[0] == "silent", f"the first turn was not silent: {played.answer(1)}", failures)
    _later_turn(played, failures, occasion="pause", bound=3, shown=4)
    _expect(played.answer(5) == ("deliver", LOOKED_AGAIN), f"the answer after the pause: {played.answer(5)}", failures)
    _expect(_texts(played) == [LOOKED_AGAIN], f"expected only the answer after the pause, saw {_texts(played)}", failures)
    return failures


def _check_final_outcome(played: Played) -> list[str]:
    failures: list[str] = []
    proposed = played.answer(1)
    _expect(proposed[0] is True, f"the proposal was refused: {proposed}", failures)
    _expect(played.answer(2)[0] == "silent", f"the proposal was the turn's action, yet saw {played.answer(2)}", failures)
    _expect(played.executed == [PROPOSAL["operation"]], f"the approved action did not run: {played.executed}", failures)
    _later_turn(played, failures, occasion="outcome", bound=4, shown=5)
    _expect('"status":"done"' in str(played.answer(5)), "the agent was not told the action ran", failures)
    _expect(played.answer(6) == ("deliver", REPORTED), f"the report: {played.answer(6)}", failures)
    _expect(_texts(played) == [REPORTED], f"expected only the agent's report, saw {_texts(played)}", failures)
    return failures


def _check_final_deliver(played: Played) -> list[str]:
    failures: list[str] = []
    _expect(played.answer(1) == ("deliver", "On it."), f"expected delivery, saw {played.answer(1)}", failures)
    _expect(
        played.host_result == TransportResult("unknown", HARNESS_DELIVERS),
        f"the host did not commit the post for the harness: {played.host_result}",
        failures,
    )
    _expect(_texts(played) == ["On it."], f"expected one committed post, saw {_texts(played)}", failures)
    _expect(
        any(move.get("kind") in ("message", "reply") and move.get("text") == "On it." for move in played.own_moves),
        "the post is not in the agent's memory",
        failures,
    )
    return failures


def _check_final_silence(played: Played) -> list[str]:
    failures: list[str] = []
    _expect(played.answer(1)[0] == "silent", f"expected silence, saw {played.answer(1)}", failures)
    _expect(not played.dispatched, "a silent final answer was committed", failures)
    reasons = [move.get("why") for move in played.own_moves if move.get("kind") == "silence"]
    _expect(reasons == ["Castor was asked, not me."], f"the thinking is not the silence's reason: {reasons}", failures)
    return failures


def _check_final_look_again(played: Played) -> list[str]:
    failures: list[str] = []
    _expect(played.answer(2)[0] == "continue", f"the first answer was not held: {played.answer(2)}", failures)
    _expect(played.answer(3) == ("deliver", "Never mind, then."), f"the second answer: {played.answer(3)}", failures)
    _expect(_texts(played) == ["Never mind, then."], f"expected only the second answer, saw {_texts(played)}", failures)
    return failures


def _check_final_thinking(played: Played) -> list[str]:
    failures: list[str] = []
    _expect(played.answer(1) == ("deliver", "Checking now."), f"saw {played.answer(1)}", failures)
    _expect(
        all("thinking" not in text and "plan" not in text for text in _texts(played)),
        f"thinking reached the room: {_texts(played)}",
        failures,
    )
    return failures


def _check_final_secret(played: Played) -> list[str]:
    failures: list[str] = []
    _expect(played.answer(1)[0] == "continue" and "secret" in played.answer(1)[1], f"saw {played.answer(1)}", failures)
    _expect(played.answer(2) == ("deliver", "I can't share that here."), f"saw {played.answer(2)}", failures)
    _expect(all(SECRET not in text for text in _texts(played)), "a secret reached the room", failures)
    return failures


SCENARIOS: dict[str, Scenario] = {
    "post": Scenario(
        "tools",
        "one post goes to the room, and the tool call says so",
        (("bind",), ("call", "send", {"text": "On it."}), ("end", True)),
        _check_post,
    ),
    "bound-silence": Scenario(
        "tools",
        "a bound turn that ends without an action is silence, remembered",
        (("bind",), ("end", True)),
        _check_bound_silence,
    ),
    "silence-reason": Scenario(
        "tools",
        "a silent turn's last words are its reason, remembered and never posted",
        (("bind",), ("end", True, "Castor was asked, not me.")),
        _check_silence_reason,
    ),
    "unbound-failure": Scenario(
        "tools",
        "a turn never bound to its wake is a failure, not silence",
        (("end", True),),
        _check_unbound_failure,
    ),
    "look-again": Scenario(
        "tools",
        "the first post is held once when someone posted meanwhile",
        (
            ("bind",),
            ("arrive", "Actually, I found it myself."),
            ("call", "send", {"text": "On it."}),
            ("call", "send", {"text": "Never mind, then."}),
            ("end", True),
        ),
        _check_look_again,
    ),
    "steering": Scenario(
        "tools",
        "a message that arrives mid-turn is shown once after a tool call, and can be answered",
        (
            ("bind",),
            ("arrive", "Please use the staging box."),
            ("call", "context", {"direction": "before"}),
            ("after_tool",),
            ("after_tool",),
            ("call", "send", {"text": "Will do.", "reply_to_event_id": "@arrival:0"}),
            ("end", True),
        ),
        _check_steering,
    ),
    "one-action": Scenario(
        "tools",
        "one room action per turn",
        (
            ("bind",),
            ("call", "send", {"text": "First."}),
            ("call", "send", {"text": "Second."}),
            ("end", True),
        ),
        _check_one_action,
    ),
    "secret": Scenario(
        "tools",
        "a withheld secret never reaches the room",
        (("bind",), ("call", "send", {"text": f"The key is {SECRET}"}), ("end", True)),
        _check_secret,
    ),
    "cancel": Scenario(
        "tools",
        "a cancelled turn posts nothing",
        (("bind",), ("cancel",), ("call", "send", {"text": "On it."}), ("end", False)),
        _check_cancel,
    ),
    "pause": Scenario(
        "tools",
        "after a pause the library starts a turn with no new message, and the agent can post",
        (("bind",), ("end", True)),
        _check_pause,
        next_occasion="pause",
        next_steps=(("bind",), ("read",), ("call", "send", {"text": LOOKED_AGAIN}), ("end", True)),
    ),
    "outcome": Scenario(
        "tools",
        "an approved action's outcome starts a turn, and the agent reports it",
        (("bind",), ("call", "propose", PROPOSAL), ("end", True)),
        _check_outcome,
        next_occasion="outcome",
        next_steps=(("bind",), ("read",), ("call", "send", {"text": REPORTED}), ("end", True)),
    ),
    "final-deliver": Scenario(
        "final-answer",
        "the final answer is the post, committed for the harness to deliver, and remembered",
        (("bind",), ("finish", "On it."), ("end", True)),
        _check_final_deliver,
    ),
    "final-silence": Scenario(
        "final-answer",
        "the silence marker is silence, and the agent's thinking is its reason",
        (("bind",), ("finish", f"<thinking>Castor was asked, not me.</thinking>\n{SILENCE}"), ("end", True)),
        _check_final_silence,
    ),
    "final-look-again": Scenario(
        "final-answer",
        "the final answer is held once when someone posted meanwhile",
        (
            ("bind",),
            ("arrive", "Actually, I found it myself."),
            ("finish", "On it."),
            ("finish", "Never mind, then."),
            ("end", True),
        ),
        _check_final_look_again,
    ),
    "final-thinking": Scenario(
        "final-answer",
        "thinking is never posted",
        (("bind",), ("finish", "<thinking>My plan: check the logs.</thinking>Checking now."), ("end", True)),
        _check_final_thinking,
    ),
    "final-secret": Scenario(
        "final-answer",
        "a withheld secret is refused once, and the agent answers again",
        (
            ("bind",),
            ("finish", f"The key is {SECRET}"),
            ("finish", "I can't share that here."),
            ("end", True),
        ),
        _check_final_secret,
    ),
    "final-cancel": Scenario(
        "final-answer",
        "a cancelled turn's final answer is silent",
        (("bind",), ("cancel",), ("finish", "On it."), ("end", False)),
        _check_final_cancel,
    ),
    "final-pause": Scenario(
        "final-answer",
        "after a pause the library starts a turn with no new message, and its answer is the post",
        (("bind",), ("finish", SILENCE), ("end", True)),
        _check_final_pause,
        next_occasion="pause",
        next_steps=(("bind",), ("read",), ("finish", LOOKED_AGAIN), ("end", True)),
    ),
    "final-outcome": Scenario(
        "final-answer",
        "an approved action's outcome starts a turn, and the agent's answer reports it",
        (("bind",), ("call", "propose", PROPOSAL), ("finish", "I asked for approval."), ("end", True)),
        _check_final_outcome,
        next_occasion="outcome",
        next_steps=(("bind",), ("read",), ("finish", REPORTED), ("end", True)),
    ),
}


# -- running ---------------------------------------------------------------------------


class _RecordingTransport:
    def __init__(self) -> None:
        self.actions: list[dict[str, Any]] = []

    def dispatch(self, *, action, **_):
        self.actions.append(dict(action))
        return TransportResult("sent", "conformance room")


class _CommittedForHarness(HarnessDelivery):
    """Records what the host committed for the harness to post."""

    def __init__(self) -> None:
        # The kit's room never shows the agent's messages back.
        super().__init__(room_shows_own_messages=False)
        self.actions: list[dict[str, Any]] = []

    def dispatch(self, *, action, wake):
        self.actions.append(dict(action))
        return super().dispatch(action=action, wake=wake)


def _policy(directory: Path, binding: Any) -> dict[str, str]:
    """A pinned policy: the person may ask for the kit's action, with an operator's approval."""

    raw = json.dumps(
        {
            "policy_id": "conformance-policy",
            "revision": "1",
            "approver_ids": [OPERATOR],
            "rules": [
                {
                    "requester_actor_id": PERSON,
                    "capability": CAPABILITY,
                    "platform": binding.platform,
                    "room_id": binding.room_id,
                    "participant_id": binding.participant_id,
                    "resource_kind": PROPOSAL["resource"]["kind"],
                    "resource_id": PROPOSAL["resource"]["id"],
                    "impact": "high",
                }
            ],
        }
    ).encode()
    path = directory / "policy.json"
    path.write_bytes(raw)
    return {"policy_path": str(path), "policy_sha256": hashlib.sha256(raw).hexdigest()}


def _start_next_turn(room: Room, occasion: str) -> str | None:
    """Start the scenario's second turn the way the library does; an error, or None."""

    if occasion == "pause":
        # The room stayed quiet: what the delivery lane's timer does when due.
        if room.pipeline.look_again(now=True) is None:
            return "the library had nothing to look again at after the pause"
        return None
    if occasion == "outcome":
        assert room.privileged is not None
        waiting = room.privileged.pending_for_operator()
        if not waiting:
            return "no proposal was waiting for an operator"
        # The operator approves; the action runs, and the delivery lane gives
        # the agent its outcome turn on its own worker.
        room.privileged.complete_authenticated_approval(
            approval_challenge_id=waiting[0]["challenge"]["approval_challenge_id"],
            authenticated_approver_id=OPERATOR,
        )
        return None
    raise ValueError(f"unknown occasion {occasion!r}")


def run_scenario(name: str, integration: KitIntegration, *, timeout: float = 15.0) -> dict[str, Any]:
    scenario = SCENARIOS[name]
    if scenario.posting != integration.posting:
        return {"scenario": name, "integration": integration.name, "status": "n/a"}
    binding = fixture_binding()
    profile = fixture_profile(binding)
    played = Played()
    privileged = scenario.next_occasion == "outcome"
    with tempfile.TemporaryDirectory(prefix="nunchi-turn-conformance-") as directory:
        settings = RoomSettings(
            binding=binding,
            profile=profile,
            attention=AttentionPolicy(),
            attention_model=None,
            limits=ObservationLimits(),
            state_directory=Path(directory) / "state",
            authorization=_policy(Path(directory), binding) if privileged else None,
        )
        transport = _CommittedForHarness() if scenario.posting == "final-answer" else _RecordingTransport()
        room: Room | None = None

        def arrive(text: str) -> str:
            assert room is not None
            event_id = f"conformance:message:{len(played.arrivals) + 2}"
            room.observation.observe(
                delivery_id=f"conformance:delivery:{event_id}",
                event={
                    "id": event_id,
                    "type": "message",
                    "author_id": PERSON,
                    "text": text,
                    "mentioned_actor_ids": [],
                    "mentions_room": False,
                },
                actors={PERSON: {"kind": "human", "display_name": "Sam"}},
            )
            played.arrivals.append(event_id)
            return event_id

        def cancel() -> None:
            assert room is not None
            room.cancel()

        def execute(operation: Mapping[str, Any], idempotency_key: str) -> TransportResult:
            played.executed.append(dict(operation))
            return TransportResult("sent", "conformance workspace")

        agent = ScriptedAgent(
            scenario.steps,
            arrive,
            cancel,
            later=(scenario.next_steps,) if scenario.next_occasion else (),
        )
        try:
            participant = integration.participant(
                profile=profile,
                guard=SecretGuard([SECRET]),
                agent=agent,
                **({"privileged": True} if privileged else {}),
            )
        except TypeError as exc:
            if not privileged:
                raise
            integration.close()
            return {
                "scenario": name,
                "integration": integration.name,
                "status": "fail",
                "failures": [f"the integration cannot offer privileged actions: {exc}"],
            }
        # The same assembly every integration uses (`nunchi.room`).
        room = Room(
            settings,
            participant=participant,
            transport=transport,
            event_visibility={
                "message": "history-and-live",
                "reaction": "history-and-live",
                "membership": "live-only",
            },
            state_prefix="conformance-",
            # A pause follows a moment whose most likely move was to wait.
            attention_model=fixture_attention_model("DEFER" if scenario.next_occasion == "pause" else "WAKE"),
            privileged_executors={CAPABILITY: execute} if privileged else None,
            participant_timeout_seconds=timeout,
        )
        host = room.host
        pipeline = room.pipeline
        try:
            outcome = pipeline.handle_delivery(
                delivery_id="conformance:delivery:1",
                event={
                    "id": TRIGGER,
                    "type": "message",
                    "author_id": PERSON,
                    "text": "Can someone look at the failing deploy?",
                    "mentioned_actor_ids": [],
                    "mentions_room": False,
                },
                actors={PERSON: {"kind": "human", "display_name": "Sam"}},
            )
            agent.turn_done[0].wait(timeout)
            if outcome.opportunities:
                played.host_result = outcome.opportunities[0].transport
            if scenario.next_occasion is not None:
                played.error = _start_next_turn(room, scenario.next_occasion)
                if played.error is None and not agent.done.wait(timeout):
                    played.error = f"the {scenario.next_occasion} turn never reached the agent"
                room.drain(timeout)
            if agent.unexpected:
                played.error = played.error or f"{agent.unexpected} turn(s) started that the scenario does not expect"
        except BaseException as exc:  # recorded for the result
            played.error = f"{type(exc).__name__}: {exc}"
        finally:
            integration.close()
        played.answers = list(agent.answers)
        played.dispatched = list(transport.actions)
        facts = host.memory_facts(TRIGGER) or {}
        played.own_moves = list(facts.get("own_moves", ()))
        if agent.error is not None and played.error is None:
            played.error = f"{type(agent.error).__name__}: {agent.error}"
    try:
        failures = [] if played.error is None else [f"error: {played.error}"]
        if not failures:
            failures = scenario.check(played)
    except (IndexError, TypeError, KeyError) as exc:
        failures = [f"the turn did not play out: {type(exc).__name__}: {exc}"]
    return {
        "scenario": name,
        "integration": integration.name,
        "status": "pass" if not failures else "fail",
        "failures": failures,
    }


def parity_table(results: Sequence[Mapping[str, Any]]) -> str:
    """The parity table: one row per scenario, one column per integration."""

    integrations = list(dict.fromkeys(result["integration"] for result in results))
    cells = {(result["scenario"], result["integration"]): result["status"] for result in results}
    lines = [
        "| Scenario | " + " | ".join(integrations) + " |",
        "|---|" + "---|" * len(integrations),
    ]
    for name, scenario in SCENARIOS.items():
        row = [cells.get((name, integration), "n/a") for integration in integrations]
        lines.append(f"| {name}: {scenario.description} | " + " | ".join(row) + " |")
    return "\n".join(lines)


def _load(spec: str) -> list[KitIntegration]:
    if spec == "reference":
        return [ReferenceIntegration("tools"), ReferenceIntegration("final-answer")]
    module_name, _, factory = spec.partition(":")
    built = getattr(importlib.import_module(module_name), factory or "conformance_integrations")()
    return list(built)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nunchi-turn-conformance")
    parser.add_argument("--list", action="store_true")
    parser.add_argument(
        "--integration",
        action="append",
        default=[],
        help="'reference', or module:factory returning integrations under test (repeatable)",
    )
    parser.add_argument("--format", choices=("table", "jsonl"), default="table")
    args = parser.parse_args(argv)
    if args.list:
        for name, scenario in SCENARIOS.items():
            print(f"{name:18s} {scenario.posting:13s} {scenario.description}")
        return 0
    integrations = [item for spec in (args.integration or ["reference"]) for item in _load(spec)]
    results = []
    for integration_spec in integrations:
        for name in SCENARIOS:
            # Each scenario gets a fresh participant from the integration, which
            # closes after it, so no turn leaks into the next.
            results.append(run_scenario(name, integration_spec))
    if args.format == "jsonl":
        for result in results:
            print(json.dumps(result, sort_keys=True))
    else:
        print(parity_table(results))
        for result in results:
            for failure in result.get("failures", ()):
                print(f"FAIL {result['integration']} {result['scenario']}: {failure}")
    return 0 if all(result["status"] in ("pass", "n/a") for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
