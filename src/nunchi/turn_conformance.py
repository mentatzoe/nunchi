"""Conformance for the agent's turn, through any integration (#94 step 9d).

Every harness must give its agent the same turn (`docs/harness-contract.md`).
This kit checks that: a scripted agent plays a scenario's turns through an
integration's real path, and the kit compares what the room and the agent saw
with what the turn's rules say. The results make the parity table.

Most scenarios are one turn, started by a message. Two have a second turn that
the library starts itself, with no new message: after a pause, when it looks
again at a moment it waited on, and after an operator approves an action the
agent proposed, when it gives the agent a turn about the outcome.

One scenario, ``launch-secret``, needs a secret the harness itself holds: the
per-launch secret an integration's room tools call the library with. An
integration without one reports it as not applicable.

Two final-answer scenarios need a harness that can end a run with its own
text in place of the model's answer (``final-not-own-words``,
``final-no-answer``). An integration whose harness never does that reports
them as not applicable. One scenario plays once per answer in its ``forms``
(``final-silence-forms``).

Two scenarios need a harness whose surface can fail the agent's model call
(``harness-failure``, ``final-harness-failure``); without it they are not
applicable.

An integration takes part by providing a `KitIntegration`: the participant the
shared turn host invokes, wired so that when its agent is started the scripted
agent's steps go through the integration's own surface (its tool calls, its
socket, its hooks). The kit owns the room, attention, the host, and the checks.

**The leak count.** In every scenario the room must receive only what the
library committed, and nothing that names Nunchi's machinery (the wake marker,
the turn's tag, its field names, the silence marker, thinking tags, internal
ids). After each scenario the kit takes what reached the room: what the
library's own transport sent, and everything the harness itself showed the
room (`KitIntegration.visible`: messages, reactions, typing, threads it
opened). Each item that does not match a committed action is a leak, and so
is each committed post that `nunchi.turn.machinery_in` says names machinery.
A leak fails the scenario, unless the integration declares it as a known gap
(`KnownGap`): the scenario then reads ``gap``, never ``pass``. An integration
without ``visible`` reports the leak count as not applicable.
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
from .reactions import ReactionCapability
from .room import Room, RoomSettings
from .turn import (
    HARNESS_DELIVERS,
    WAKE_MARKER,
    HarnessDelivery,
    SecretGuard,
    Turn,
    TurnDriver,
    TurnParticipant,
    machinery_in,
)

PERSON = "conformance:person"
TRIGGER = "conformance:message:1"
SECRET = "conformance-withheld-secret-value"
# Stands for the integration's launch secret in a step's text.
LAUNCH_SECRET = "@launch-secret"
# What the agent posts once its post with a secret was refused.
NO_SECRET = "I can't share that here."
SILENCE = "[SILENT]"
# Another answer the reference harness treats as silence, as many harnesses do.
NO_REPLY = "NO_REPLY"
# Stands for the first of the integration's own other silent answers
# (``also_silent``) in a form; a play with none to use is skipped.
ALSO_SILENT = "@also-silent"
# What the model wrote before its run ended without an answer, and the text a
# harness puts in place of the missing answer.
CHECKING = "Let me check the deploy logs first."
STAND_IN = "I reached the iteration limit and couldn't generate a summary."
EMPTY_STAND_IN = "(empty)"
# The agent's silence, as models write it: wrapped, or in its harness's other
# silence word. Each keeps the agent's thinking as its reason.
SILENCE_FORMS = (
    "**[SILENT]**",
    "`[SILENT]`",
    "[silent].",
    ALSO_SILENT,
)
# A post that only looks like a silence word: it must go out.
NEAR_SILENCE = "No reply from Bob yet. Want me to ping him?"
# The agent's own "mhm" (docs/behavior.md): one reaction the kit's room offers.
MHM = "👂"
# Why the agent waits, what it posts after the pause, and its outcome report.
WAITED = "Castor was asked, not me."
LOOKED_AGAIN = "Still stuck? I can take a look."
REPORTED = "Done: the runbook is in the README."
OPERATOR = "operator:conformance"
# What an agent echoes from its own turn: a wake marker from its history, and
# its thinking in the tags models write it in.
ECHOED_MARKER = WAKE_MARKER.format("conformance-echoed-wake")
THOUGHT = "My plan: check the logs."
# What the provider says when it refuses the agent's model call.
MODEL_REFUSED = "conformance: the provider refused the request"
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
# ("finish", answer), the answer its model wrote, ("end", ok) or ("end", ok,
# last_words); or what happens around it: ("arrive", text), someone posts;
# ("cancel",), the library cancels the turn; ("stand_in", text, wrote), the
# run ends with the harness's own ``text`` in place of an answer, after its
# model wrote ``wrote`` ("" for nothing); ("fail",), the agent's model call
# fails, and the harness ends the run as it does on such a failure. "@form"
# in a finish step is the scenario's form being played.
Step = tuple


@dataclass(frozen=True)
class Scenario:
    """One scenario: the first turn's steps, and a second turn the library may start.

    ``next_occasion`` names what starts the second turn: ``"pause"``, the room
    stays quiet after a moment the agent waited on, and the library looks
    again; ``"outcome"``, an operator approves the action the agent proposed
    in its first turn. The agent plays ``next_steps`` in that turn.

    ``launch_secret``: the scenario needs the integration's launch secret, and
    is not applicable to an integration that has none.

    ``harness_text``: the scenario needs a harness that ends a run with its
    own text in place of the model's answer (a ``stand_in`` step), and is not
    applicable to an integration whose harness never does.

    ``forms``: the scenario plays once per form, with the form in place of
    "@form" in its steps; it passes when every play passes. The form
    ``@also-silent`` is the first answer the integration's participant lists
    in ``also_silent``; when it lists none, that play is skipped.

    ``model_failure``: the scenario fails the agent's model call (a ``fail``
    step), and is not applicable to an integration whose surface cannot.
    """

    posting: str
    description: str
    steps: tuple[Step, ...]
    check: Callable[["Played"], list[str]]
    next_occasion: str | None = None
    next_steps: tuple[Step, ...] = ()
    launch_secret: bool = False
    harness_text: bool = False
    forms: tuple[str, ...] = ()
    model_failure: bool = False


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
    # The integration's launch secret, in the scenario that uses it.
    launch_secret: str | None = None
    # The form this play used, in a scenario with forms.
    form: str | None = None
    # What the library's own transport sent to the room: every action in tool
    # posting; in final-answer posting only what it sends itself, such as a
    # reaction, since the harness posts the answer.
    library_sent: list[dict[str, Any]] = field(default_factory=list)
    # What the harness itself showed the room (`KitIntegration.visible`), or
    # None when the integration cannot say.
    shown: list[dict[str, Any]] | None = None
    # Internal ids a post must not name: each turn's request id.
    ids: set[str] = field(default_factory=set)
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

    # Only for an integration with ``harness_text``.
    def stand_in(self, turn_id: str, text: str, wrote: str) -> tuple[str, str]: ...

    # Only for an integration with ``model_failure``.
    def fail(self, turn_id: str) -> None: ...


@dataclass(frozen=True)
class KnownGap:
    """Something the harness shows the room by itself that nothing public can stop.

    The integration declares it, and documents it where its users read
    (its README, the contract's candidate gaps). The kit counts it as a leak
    and shows the scenario as ``gap``, never ``pass``; anything else the
    harness shows still fails.

    ``scenarios`` are where it shows; ``kind`` is what the room sees
    (``message``, ``reaction``, ``typing`` or ``thread``); ``text``, for a
    message, is part of its text. ``reason`` says why nothing stops it and
    where it is documented.
    """

    reason: str
    scenarios: tuple[str, ...]
    kind: str
    text: str | None = None

    def covers(self, scenario: str, shown: Mapping[str, Any]) -> bool:
        return (
            scenario in self.scenarios
            and shown.get("kind") == self.kind
            and (self.text is None or self.text in str(shown.get("text", "")))
        )


class KitIntegration(Protocol):
    """An integration under test.

    An integration whose harness holds a launch secret, such as the secret
    its room tools call the library's socket with (`nunchi.turn_server`),
    also sets ``launch_secret`` to it in `participant`. Without one, the
    ``launch-secret`` scenario is not applicable.

    A final-answer integration whose harness can end a run with its own text
    in place of the model's answer sets ``harness_text = True``, and its
    surface plays ``stand_in`` steps: the model writes ``wrote``, then the
    harness ends the run with its own text. A harness that chooses its own
    words may use them instead of ``text``. Without it, the scenarios that
    need it are not applicable.

    An integration whose surface can fail the agent's model call sets
    ``model_failure = True``, and its surface plays ``fail`` steps: the model
    call fails the way it fails in that harness (an error from the model's
    API, an exception), and the harness ends the run as it would.

    For the leak count, an integration gives ``visible()``: everything the
    harness itself showed the room in the scenario just played, outside the
    library's transport, the answers it posted for the library included, as
    a list of ``{"kind": "message", "text": ...}``, ``{"kind": "reaction",
    "reaction": ...}``, ``{"kind": "typing"}`` or ``{"kind": "thread"}`` (any
    other kind counts too); ``where`` may name the chat. The kit calls it
    before ``close``. A harness that reaches the room only through the
    library's transport returns an empty list. ``known_gaps`` lists what the
    harness shows that nothing public can stop (`KnownGap`).
    """

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
    arrived during the scenario, once it has arrived. ``@launch-secret`` in a
    call's text stands for ``launch_secret``, the integration's own.
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
        self.launch_secret: str | None = None
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
        def value_of(value: Any) -> Any:
            if not isinstance(value, str):
                return value
            if value.startswith("@arrival:"):
                return self.arrivals[int(value.split(":")[1])]
            if LAUNCH_SECRET in value:
                if self.launch_secret is None:
                    raise ValueError("this agent has no launch secret to post")
                return value.replace(LAUNCH_SECRET, self.launch_secret)
            return value

        return {key: value_of(value) for key, value in arguments.items()}

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
                    elif kind == "stand_in":
                        answer = surface.stand_in(turn_id, step[1], step[2])
                    elif kind == "fail":
                        answer = surface.fail(turn_id)
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
    def __init__(self, participant: TurnParticipant, turn: Turn, shown: list[dict[str, Any]]) -> None:
        self.participant = participant
        self.turn = turn
        # What the reference harness posts: each answer the library tells it to deliver.
        self.shown = shown

    def _posts(self, kind: str, text: str) -> tuple[str, str]:
        if kind == "deliver":
            self.shown.append({"kind": "message", "text": text})
        return kind, text

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
        # The scripted model wrote the answer, and the harness reports it.
        self.participant.model_wrote(turn_id=turn_id, text=answer)
        decision = self.participant.finish(turn_id=turn_id, answer=answer)
        return self._posts(decision.kind, decision.text)

    def stand_in(self, turn_id: str, text: str, wrote: str) -> tuple[str, str]:
        # The model wrote something else, or nothing; the harness answers for it.
        self.participant.model_wrote(turn_id=turn_id, text=wrote)
        decision = self.participant.finish(turn_id=turn_id, answer=text)
        return self._posts(decision.kind, decision.text)

    def fail(self, turn_id: str) -> None:
        # The harness's model call raised; the harness ends its run as failed.
        error = ConnectionError(MODEL_REFUSED)
        self.participant.end_turn(turn_id=None, ok=False, detail=f"the model call failed: {error!r}")

    def end(self, turn_id: str, ok: bool, note: str | None = None) -> None:
        # The harness reports its agent's end of turn, bound or not.
        self.participant.end_turn(turn_id=None, ok=ok, detail="scripted end", note=note)


class _DirectDriver(TurnDriver):
    def __init__(self, agent: ScriptedAgent, shown: list[dict[str, Any]]) -> None:
        self.agent = agent
        self.shown = shown
        self.participant: TurnParticipant | None = None

    def start(self, turn: Turn) -> None:
        assert self.participant is not None
        self.agent.play(_DirectSurface(self.participant, turn, self.shown))

    def interrupt(self, turn: Turn) -> None:
        pass


class ReferenceIntegration:
    """The core turn with no harness around it: what every integration must match.

    In final-answer posting its harness reports what the scripted model
    wrote, treats ``NO_REPLY`` as silence too, and can put its own text in
    place of a missing answer, as many harnesses do. It posts only the
    answers the library tells it to deliver, and shows the room nothing else.
    """

    known_gaps: tuple[KnownGap, ...] = ()
    model_failure = True

    def __init__(self, posting: str = "tools") -> None:
        self.posting = posting
        self.name = f"reference ({posting})"
        self.harness_text = posting == "final-answer"
        self._shown: list[dict[str, Any]] = []

    def visible(self) -> list[dict[str, Any]]:
        """The answers its harness posted; in tool posting none, as the library's transport is the only path."""

        return list(self._shown)

    def participant(
        self, *, profile: ParticipantProfile, guard: SecretGuard, agent: ScriptedAgent, privileged: bool = False
    ) -> Any:
        # The turn offers propose and withdraw only when the room authorizes them.
        self._shown = []
        driver = _DirectDriver(agent, self._shown)
        participant = TurnParticipant(
            profile=profile,
            driver=driver,
            guard=guard,
            tool_names={role: role for role in ("send", "react", "propose", "withdraw", "context")},
            result_wait_seconds=5,
            **(
                {"silence_marker": SILENCE, "also_silent": (NO_REPLY,), "model_text": True}
                if self.posting == "final-answer"
                else {}
            ),
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
    _expect(reasons == [WAITED], f"the last words are not the silence's reason: {reasons}", failures)
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


def _check_launch_secret(played: Played) -> list[str]:
    failures: list[str] = []
    refused = played.answer(1)
    _expect(refused[0] is False and "secret" in refused[1], f"the launch secret was not refused: {refused}", failures)
    secret = played.launch_secret or LAUNCH_SECRET
    _expect(all(secret not in text for text in _texts(played)), "the launch secret reached the room", failures)
    _expect(played.answer(2)[0] is True, f"the post without the secret failed: {played.answer(2)}", failures)
    _expect(_texts(played) == [NO_SECRET], f"expected only the post without the secret, saw {_texts(played)}", failures)
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


def _remembers_why_it_waited(played: Played, failures: list[str], *, shown: int) -> None:
    _expect(
        f'"why":{json.dumps(WAITED)}' in str(played.answer(shown)),
        "the turn after the pause does not remember why the agent waited",
        failures,
    )


def _check_pause(played: Played) -> list[str]:
    failures: list[str] = []
    _expect(played.answer(0) is True, "the first turn did not bind", failures)
    _later_turn(played, failures, occasion="pause", bound=2, shown=3)
    _remembers_why_it_waited(played, failures, shown=3)
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
    _remembers_why_it_waited(played, failures, shown=4)
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


def _check_mhm(played: Played, *, reacted: int) -> list[str]:
    failures: list[str] = []
    _expect(played.answer(reacted)[0] is True, f"the reaction was refused: {played.answer(reacted)}", failures)
    expected = [{"kind": "reaction", "target_event_id": TRIGGER, "reaction": MHM}]
    seen = [
        {key: action.get(key) for key in ("kind", "target_event_id", "reaction")}
        for action in played.dispatched
    ]
    _expect(seen == expected, f"expected one {MHM} on the message, saw {seen}", failures)
    return failures


def _check_final_mhm(played: Played) -> list[str]:
    failures = _check_mhm(played, reacted=1)
    _expect(played.answer(2)[0] == "silent", f"the reaction was the turn's action, yet saw {played.answer(2)}", failures)
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
    _expect(reasons == [WAITED], f"expected {WAITED!r} as the silence's reason, saw {reasons}", failures)
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


def _check_not_own_words(played: Played) -> list[str]:
    """The harness's text in place of an answer: never posted or remembered, and the turn fails."""

    failures: list[str] = []
    _expect(played.answer(1)[0] == "silent", f"the harness posted {played.answer(1)}", failures)
    _expect(not played.dispatched, f"the harness's text was committed as the agent's post: {_texts(played)}", failures)
    _expect(
        played.host_result is not None and played.host_result.delivery == "failed",
        f"the turn must fail, host said {played.host_result}",
        failures,
    )
    moves = [(move.get("kind"), move.get("text")) for move in played.own_moves]
    _expect(not moves, f"the agent's memory holds a move it never made: {moves}", failures)
    return failures


def _check_silence_form(played: Played) -> list[str]:
    failures: list[str] = []
    if played.form == NEAR_SILENCE:
        _expect(played.answer(1) == ("deliver", NEAR_SILENCE), f"the post was not delivered: {played.answer(1)}", failures)
        _expect(_texts(played) == [NEAR_SILENCE], f"expected the post committed, saw {_texts(played)}", failures)
        _expect(
            any(move.get("kind") in ("message", "reply") and move.get("text") == NEAR_SILENCE for move in played.own_moves),
            "the post is not in the agent's memory",
            failures,
        )
        return failures
    _expect(played.answer(1)[0] == "silent", f"expected silence, saw {played.answer(1)}", failures)
    _expect(not played.dispatched, f"a silent answer was committed: {_texts(played)}", failures)
    moves = [(move.get("kind"), move.get("why")) for move in played.own_moves]
    _expect(moves == [("silence", WAITED)], f"expected a silence with its reason in memory, saw {moves}", failures)
    return failures


def _check_leak(played: Played) -> list[str]:
    failures: list[str] = []
    _expect(played.answer(1)[0] is True, f"the post was refused: {played.answer(1)}", failures)
    # The kit's room never shows a tool post back, so its memory is not checked here.
    _expect(_texts(played) == ["On it."], f"expected only the agent's words posted, saw {_texts(played)}", failures)
    return failures


def _check_leak_markup(played: Played) -> list[str]:
    failures: list[str] = []
    refused = played.answer(1)
    _expect(
        refused[0] is False and "private thinking" in refused[1],
        f"a post of only private text was not refused: {refused}",
        failures,
    )
    _expect(played.answer(2)[0] is True, f"the post after it failed: {played.answer(2)}", failures)
    _expect(_texts(played) == ["On it."], f"expected only the second post, saw {_texts(played)}", failures)
    return failures


def _check_model_failure(played: Played) -> list[str]:
    """The model call failed: the turn ends as a failure before the library's deadline, and nothing is committed."""

    failures: list[str] = []
    _expect(played.answer(0) is True, "the turn did not bind", failures)
    _expect(not played.dispatched, f"a failed turn committed {played.dispatched}", failures)
    result = played.host_result
    _expect(
        result is not None and result.delivery == "failed" and "deadline" not in result.detail,
        f"the turn must end as a failure before the library's deadline, host said {result}",
        failures,
    )
    moves = [(move.get("kind"), move.get("text") or move.get("why")) for move in played.own_moves]
    _expect(not moves, f"the agent's memory holds a move it never made: {moves}", failures)
    return failures


def _check_final_leak(played: Played) -> list[str]:
    failures: list[str] = []
    _expect(played.answer(1) == ("deliver", "Checking now."), f"saw {played.answer(1)}", failures)
    _expect(_texts(played) == ["Checking now."], f"expected only the agent's words, saw {_texts(played)}", failures)
    moves = [
        (move.get("text"), move.get("why")) for move in played.own_moves if move.get("kind") in ("message", "reply")
    ]
    _expect(
        moves == [("Checking now.", THOUGHT)],
        f"expected the post in memory with its thinking as reason, saw {moves}",
        failures,
    )
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
        (("bind",), ("end", True, WAITED)),
        _check_silence_reason,
    ),
    "mhm": Scenario(
        "tools",
        "the agent's own mhm is one reaction on the message, through its react tool",
        (("bind",), ("call", "react", {"target_event_id": TRIGGER, "reaction": MHM}), ("end", True)),
        lambda played: _check_mhm(played, reacted=1),
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
    "launch-secret": Scenario(
        "tools",
        "the launch secret the harness holds never reaches the room, and the agent can post without it",
        (
            ("bind",),
            ("call", "send", {"text": f"My session is {LAUNCH_SECRET}"}),
            ("call", "send", {"text": NO_SECRET}),
            ("end", True),
        ),
        _check_launch_secret,
        launch_secret=True,
    ),
    "cancel": Scenario(
        "tools",
        "a cancelled turn posts nothing",
        (("bind",), ("cancel",), ("call", "send", {"text": "On it."}), ("end", False)),
        _check_cancel,
    ),
    "pause": Scenario(
        "tools",
        "after a pause the library starts a turn with no new message, which remembers why the agent waited",
        (("bind",), ("end", True, WAITED)),
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
    "leak": Scenario(
        "tools",
        "a post loses the agent's thinking, kept as its reason, and an echoed wake marker",
        (("bind",), ("call", "send", {"text": f"<think>{THOUGHT}</think>\n{ECHOED_MARKER}\nOn it."}), ("end", True)),
        _check_leak,
    ),
    "leak-markup": Scenario(
        "tools",
        "a post of only thinking and a wake marker is refused, and the agent writes again",
        (
            ("bind",),
            ("call", "send", {"text": f"<thinking>{WAITED}</thinking>\n{ECHOED_MARKER}"}),
            ("call", "send", {"text": "On it."}),
            ("end", True),
        ),
        _check_leak_markup,
    ),
    "harness-failure": Scenario(
        "tools",
        "a failed model call ends the turn as a failure promptly, and nothing reaches the room",
        (("bind",), ("fail",)),
        _check_model_failure,
        model_failure=True,
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
        (("bind",), ("finish", f"<thinking>{WAITED}</thinking>\n{SILENCE}"), ("end", True)),
        _check_final_silence,
    ),
    "final-mhm": Scenario(
        "final-answer",
        "the agent's own mhm is one reaction through its react tool, and the answer after it posts nothing",
        (
            ("bind",),
            ("call", "react", {"target_event_id": TRIGGER, "reaction": MHM}),
            ("finish", SILENCE),
            ("end", True),
        ),
        _check_final_mhm,
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
        "after a pause the library starts a turn with no new message, which remembers why the agent waited",
        (("bind",), ("finish", f"<thinking>{WAITED}</thinking>\n{SILENCE}"), ("end", True)),
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
    "final-not-own-words": Scenario(
        "final-answer",
        "text the harness puts in place of the agent's answer is never posted or remembered, and the turn fails",
        (("bind",), ("stand_in", STAND_IN, CHECKING), ("end", True)),
        _check_not_own_words,
        harness_text=True,
    ),
    "final-no-answer": Scenario(
        "final-answer",
        "a run whose model wrote nothing, with the harness's text as its answer, posts nothing and fails",
        (("bind",), ("stand_in", EMPTY_STAND_IN, ""), ("end", True)),
        _check_not_own_words,
        harness_text=True,
    ),
    "final-silence-forms": Scenario(
        "final-answer",
        "a wrapped marker or the harness's other silence word is silence, remembered with its reason; a post that only looks like one goes out",
        (("bind",), ("finish", f"<thinking>{WAITED}</thinking>\n@form"), ("end", True)),
        _check_silence_form,
        forms=(*SILENCE_FORMS, NEAR_SILENCE),
    ),
    "final-leak": Scenario(
        "final-answer",
        "an answer loses the agent's thinking, kept as its reason, and an echoed wake marker",
        (("bind",), ("finish", f"<think>{THOUGHT}</think>\n{ECHOED_MARKER}\nChecking now."), ("end", True)),
        _check_final_leak,
    ),
    "final-leak-markup": Scenario(
        "final-answer",
        "an answer of only thinking and a wake marker is silence, and the thinking is its reason",
        (("bind",), ("finish", f"<reasoning>{WAITED}</reasoning>\n{ECHOED_MARKER}"), ("end", True)),
        _check_final_silence,
    ),
    "final-trailing-silence": Scenario(
        "final-answer",
        "the silence marker after the agent's words is silence, and the words are its reason",
        (("bind",), ("finish", f"{WAITED} {SILENCE}"), ("end", True)),
        _check_final_silence,
    ),
    "final-harness-failure": Scenario(
        "final-answer",
        "a failed model call ends the turn as a failure promptly, and nothing reaches the room",
        (("bind",), ("fail",)),
        _check_model_failure,
        model_failure=True,
    ),
}


# -- running ---------------------------------------------------------------------------


class _RecordingTransport:
    def __init__(self) -> None:
        self.actions: list[dict[str, Any]] = []
        # Each turn's request id: an internal id a post must not name.
        self.ids: set[str] = set()

    def reaction_capability(self) -> ReactionCapability:
        # The room lets the agent add its own mhm, and nothing else.
        return ReactionCapability(
            supported=True,
            authenticated=True,
            operations=("add",),
            reactions=(MHM,),
            permissions_revision="conformance:reactions:v1",
        )

    def dispatch(self, *, action, wake=None, **_):
        self.actions.append(dict(action))
        _note_ids(self.ids, wake)
        return TransportResult("sent", "conformance room")


def _note_ids(ids: set[str], wake: Any) -> None:
    request_id = wake.get("request_id") if isinstance(wake, Mapping) else None
    if isinstance(request_id, str) and request_id:
        ids.add(request_id)


class _NativeReactions(_RecordingTransport):
    """A harness's own reaction path: the harness posts messages, not this."""

    def ordinary_action_capabilities(self) -> list[str]:
        return ["reaction"]


class _CommittedForHarness(HarnessDelivery):
    """Records what the host committed for the harness to post.

    Reactions go to the room directly, as a harness's native transport would
    send them.
    """

    def __init__(self) -> None:
        # The kit's room never shows the agent's messages back.
        super().__init__(_NativeReactions(), room_shows_own_messages=False)
        self.actions: list[dict[str, Any]] = []
        self.ids: set[str] = set()

    def dispatch(self, *, action, wake):
        self.actions.append(dict(action))
        _note_ids(self.ids, wake)
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


def _with_form(step: Step, form: str) -> Step:
    return tuple(part.replace("@form", form) if isinstance(part, str) else part for part in step)


def run_scenario(name: str, integration: KitIntegration, *, timeout: float = 15.0) -> dict[str, Any]:
    """Play one scenario through ``integration`` and check it, with its leak count.

    The result's ``status`` is ``pass``, ``fail``, ``gap`` (it passed but for
    leaks the integration declares as known gaps), ``n/a`` or ``skipped``.
    ``failures`` holds each failed check and each undeclared leak (`leaks`);
    ``gaps`` the declared ones; ``leak_count`` counts both, or is ``n/a`` for
    an integration without ``visible``.
    """

    scenario = SCENARIOS[name]
    if (
        scenario.posting != integration.posting
        or (scenario.harness_text and not getattr(integration, "harness_text", False))
        or (scenario.model_failure and not getattr(integration, "model_failure", False))
    ):
        return {"scenario": name, "integration": integration.name, "status": "n/a"}
    if not scenario.forms:
        return _play(name, scenario, integration, steps=scenario.steps, form=None, timeout=timeout)
    failures: list[str] = []
    skipped: list[str] = []
    gaps: list[str] = []
    counts: list[Any] = []
    for form in scenario.forms:
        steps = tuple(_with_form(step, form) for step in scenario.steps)
        result = _play(name, scenario, integration, steps=steps, form=form, timeout=timeout)
        if result["status"] == "n/a":
            return result
        if result["status"] == "skipped":
            skipped.append(form)
            continue
        form = result.get("form", form)
        failures += [f"{form!r}: {failure}" for failure in result.get("failures", ())]
        gaps += [f"{form!r}: {gap}" for gap in result.get("gaps", ())]
        counts.append(result.get("leak_count", "n/a"))
    return {
        "scenario": name,
        "integration": integration.name,
        "status": _status(failures, gaps),
        "failures": failures,
        "gaps": gaps,
        "leak_count": sum(counts) if counts and "n/a" not in counts else "n/a",
        **({"skipped": skipped} if skipped else {}),
    }


def _status(failures: Sequence[str], gaps: Sequence[str]) -> str:
    return "fail" if failures else "gap" if gaps else "pass"


def _same(committed: Mapping[str, Any], shown: Mapping[str, Any]) -> bool:
    """Whether what the room got is this committed action."""

    kind = shown.get("kind")
    if kind == "message":
        return committed.get("kind") in ("message", "reply") and str(committed.get("text", "")).strip() == str(
            shown.get("text", "")
        ).strip()
    if kind == "reaction":
        return committed.get("kind") == "reaction" and committed.get("reaction") == shown.get("reaction")
    return False


def _describe(shown: Mapping[str, Any]) -> str:
    where = f" in {shown['where']}" if shown.get("where") else ""
    kind = shown.get("kind", "something")
    if kind == "message":
        return f"a message{where}: {shown.get('text', '')!r}"
    if kind == "reaction":
        return f"a reaction{where}: {shown.get('reaction', '')!r}"
    return f"{kind}{where}"


def leaks(name: str, played: Played, known_gaps: Sequence[KnownGap] = ()) -> tuple[list[str], list[str]]:
    """The leaks in one play: undeclared ones, and the integration's declared known gaps.

    What reached the room is what the library's transport sent, all of it
    committed, and what the harness showed (``played.shown``). Each thing the
    harness showed that matches no committed action left for it to deliver
    is a leak, and so is each committed post that names Nunchi's machinery
    (`nunchi.turn.machinery_in`), the turn's request ids included.
    """

    found: list[str] = []
    declared: list[str] = []
    unmatched = [dict(action) for action in played.dispatched]
    for sent in played.library_sent:
        if sent in unmatched:
            unmatched.remove(sent)
    for item in played.shown or ():
        match = next((action for action in unmatched if _same(action, item)), None)
        if match is not None:
            unmatched.remove(match)
            continue
        gap = next((gap for gap in known_gaps if gap.covers(name, item)), None)
        if gap is not None:
            declared.append(f"{_describe(item)}: {gap.reason}")
        else:
            found.append(f"the room got {_describe(item)}, which the library never committed")
    for action in played.dispatched:
        if action.get("kind") not in ("message", "reply"):
            continue
        machinery = machinery_in(str(action.get("text", "")), ids=played.ids)
        if machinery:
            found.append(f"a committed post names Nunchi's machinery {machinery}: {action.get('text')!r}")
    return found, declared


def _play(
    name: str,
    scenario: Scenario,
    integration: KitIntegration,
    *,
    steps: tuple[Step, ...],
    form: str | None,
    timeout: float,
) -> dict[str, Any]:
    """Play the scenario once, with ``steps`` as its first turn, and check it."""

    binding = fixture_binding()
    profile = fixture_profile(binding)
    played = Played(form=form)
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
            steps,
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
        if scenario.launch_secret:
            # Only an integration whose harness holds a launch secret has one to leak.
            secret = getattr(integration, "launch_secret", None)
            if not secret:
                integration.close()
                return {"scenario": name, "integration": integration.name, "status": "n/a"}
            agent.launch_secret = played.launch_secret = secret
        if form == ALSO_SILENT:
            # The integration's own other silence word, if its harness has one.
            also = tuple(getattr(participant, "also_silent", ()) or ())
            if not also:
                integration.close()
                return {"scenario": name, "integration": integration.name, "status": "skipped"}
            played.form = also[0]
            agent.turns = tuple(
                tuple(
                    tuple(part.replace(ALSO_SILENT, also[0]) if isinstance(part, str) else part for part in step)
                    for step in turn
                )
                for turn in agent.turns
            )
            agent.steps = agent.turns[0]
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
            # What the harness showed the room, read before it closes.
            visible = getattr(integration, "visible", None)
            if callable(visible):
                try:
                    played.shown = [dict(item) for item in visible()]
                except Exception as exc:  # recorded for the result
                    played.error = played.error or f"visible() failed: {type(exc).__name__}: {exc}"
            integration.close()
        played.answers = list(agent.answers)
        played.dispatched = list(transport.actions)
        # In final-answer posting the library sends only what is not a message itself.
        sent = transport.native if isinstance(transport, HarnessDelivery) else transport
        played.library_sent = list(sent.actions)
        played.ids = set(transport.ids)
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
    found, declared = leaks(name, played, getattr(integration, "known_gaps", ()))
    if played.shown is None:
        # Without what the harness showed, the room cannot be counted.
        found, declared = [], []
    return {
        "scenario": name,
        "integration": integration.name,
        "status": _status([*failures, *found], declared),
        "failures": [*failures, *found],
        "gaps": declared,
        "leak_count": "n/a" if played.shown is None else len(found) + len(declared),
        **({"form": played.form} if played.form is not None else {}),
    }


def parity_table(results: Sequence[Mapping[str, Any]]) -> str:
    """The parity table: one row per scenario, one column per integration, and the leak count.

    A cell is ``pass``, ``fail``, ``gap`` (it passed but for a known gap the
    integration declares) or ``n/a``. The last row counts the leaks in every
    scenario that ran, with how many are declared gaps, or ``n/a`` for an
    integration that cannot say what its harness showed.
    """

    integrations = list(dict.fromkeys(result["integration"] for result in results))
    cells = {(result["scenario"], result["integration"]): result["status"] for result in results}
    lines = [
        "| Scenario | " + " | ".join(integrations) + " |",
        "|---|" + "---|" * len(integrations),
    ]
    for name, scenario in SCENARIOS.items():
        row = [cells.get((name, integration), "n/a") for integration in integrations]
        lines.append(f"| {name}: {scenario.description} | " + " | ".join(row) + " |")
    lines.append(
        "| **leak count**: what reached the room beyond what the library committed, or named its machinery | "
        + " | ".join(_leak_cell([result for result in results if result["integration"] == integration])
                     for integration in integrations)
        + " |"
    )
    return "\n".join(lines)


def _leak_cell(results: Sequence[Mapping[str, Any]]) -> str:
    counts = [result["leak_count"] for result in results if "leak_count" in result]
    if not counts or "n/a" in counts:
        return "n/a"
    total = sum(counts)
    declared = sum(len(result.get("gaps", ())) for result in results)
    return f"{total} ({declared} known gap{'s' if declared != 1 else ''})" if declared else str(total)


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
            print(f"{name:24s} {scenario.posting:13s} {scenario.description}")
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
            for gap in result.get("gaps", ()):
                print(f"GAP {result['integration']} {result['scenario']}: {gap}")
    # A declared known gap is documented, not a failure.
    return 0 if all(result["status"] in ("pass", "n/a", "gap") for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
