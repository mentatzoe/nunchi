"""Standalone Discord reference rehearsal.

Runs the reference participant on a Discord stand-in, with scripted models or
an explicitly requested live model. This exercises current reference and channel
mechanisms; it is not evidence about Claude Code, Codex, Hermes or another agent
harness. See docs/rehearsal.md for commands, prerequisites and interpretation.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping, Sequence
import contextlib
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from types import SimpleNamespace
from typing import Any
from unittest import mock
import urllib.request

from evals.behavior.scene import SCENES as BEHAVIOR_SCENES, Scene, load_participants, load_scene, parse_offset

from . import checks as checks_module
from .checks import PROBE_SCENARIO, Check
from .record import SCHEMA, config_entry, copy_tree, git_commit, nunchi_install, python_identity, python_packages, redact, served_providers, summary_markdown, tree_sizes, write_json
from .routes import ATTENTION_KEY_ENV, CANARY_ENV, DEFAULT_AGENT_MODEL, DEFAULT_ATTENTION_MODEL, HARNESSES, LIVE_SCENE_KEYS, OPENROUTER, Homes, Route, attention_config, attention_key_env, clean_environment, harness_key_env
from .scan import delete_outputs, enforce
from .spend import SpendWatch, estimate_usd
from .standin import JsonLines, RoomScript, ScriptedAttention, snowflake, timestamp

EXIT_PASS = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_COULD_NOT_RUN = 3
EXIT_BUDGET = 4

ROOT = Path(__file__).resolve().parents[2]
SCENES = Path(__file__).resolve().parent / "scenes"

PARTICIPANT = "vigil"
# The bound channel and the agent's bot: the conformance kit's Discord lane.
ROOM_ID = "1100"
BOT_ID = "9900"
# Scene people and bots get Discord ids from here, in the order they appear.
FIRST_PERSON_ID = 4201
# What the scripted agent posts, and the phrase scripted attention wakes for.
SCRIPTED_ANSWER = "Ten seconds is a sensible default, with a retry and backoff if the receiver is slow."
@dataclass(frozen=True)
class MomentSpec:
    name: str
    scene: Path
    # "post": a wake, a bound turn, one room post. "no-turn": no harness turn. The Discord room
    # adds "reply", "reaction", "thread-reply" (a reply that must land in the moment's
    # thread) and "report" (reported, never graded; `discord_room.py`).
    expect: str
    # Scripted attention wakes for a message holding this phrase.
    wake_phrase: str | None = None
    # The Discord room only: the graded message replies to the agent's last post; it goes in a
    # thread of this name under the room; the gateway reconnects every bot just before it.
    reply_to_agent: bool = False
    thread: str | None = None
    reconnect_before: bool = False


# The status report first: its first message is 30 minutes old, so playing it
# second would put it before the question in the room's log.
MOMENTS = (
    MomentSpec("bot-status-report", BEHAVIOR_SCENES / "behavior" / "bot-status-report.json", "no-turn"),
    MomentSpec("direct-question", SCENES / "direct-question.json", "post", "sensible default timeout"),
)


class CouldNotRun(RuntimeError):
    """The probe could not reach the room: a harness, a key or a setting is missing."""


def live_scene_refusal(options: "Options", environ: Mapping[str, str]) -> tuple[int, str] | None:
    """Why a live scene must not start, as (exit status, reason); None when it may. Nothing has started and nothing was spent.

    A live scene runs on a CI runner only: the launcher then runs without
    ``--offline`` (it needs the model providers' network), which changes the
    port setting of the machine's network namespace and is allowed only where
    ``CI=true``, a runner that is discarded after its job
    (`discord_net.refusal`). The probe refuses too, so that nothing here starts
    on a developer's machine whatever launched it (exit 2). And it needs every key its
    column reads, under that key's own name (`routes.LIVE_SCENE_KEYS`; exit 3):
    the live probe elsewhere falls back to the attention key for a harness's
    own, a scene does not.
    """

    if not options.live_scene:
        return None
    if environ.get("CI") != "true":
        return EXIT_USAGE, (
            "a live scene runs only on a CI runner (CI=true): the launcher it needs, without --offline, changes the network "
            "namespace's port setting, and its model calls spend money. Use a disposable CI runner; "
            "run a scene scripted (--scripted) anywhere else"
        )
    names = LIVE_SCENE_KEYS.get(options.harness, ())
    missing = [name for name in names if not environ.get(name)]
    if missing:
        return EXIT_COULD_NOT_RUN, f"a live scene by {options.harness} needs {', '.join(names)} set; missing: {', '.join(missing)}"
    return None


@dataclass
class Options:
    harness: str
    out: Path
    budget_usd: float = 2.0
    agent_model: str = DEFAULT_AGENT_MODEL
    attention_model: str = DEFAULT_ATTENTION_MODEL
    # The agent's scripted model endpoint, scripted attention, no key, no spend reading.
    scripted: bool = False
    wheel: Path | None = None
    keep_work: bool = False
    turn_timeout_seconds: float = 300.0
    command: list[str] = field(default_factory=list)
    # Optional label recorded with the result.
    arm: str = ""
    # The reference process on the Discord stand-in, inside the launcher.
    room: str = "discord"
    # The Python that runs the Discord processes (the reference needs discord.py); default this one.
    discord_python: str | None = None
    # The behavior scene to play instead of the moments (a Discord room column; `directed.py`). Without ``scripted`` it is played live
    # (PR 4d): on a CI runner only, with the keys of its column (`live_scene_refusal`).
    scene: str | None = None
    # A scripted scene in which the agent's nod is first a word, which the core refuses, and then the emoji (`--nod-with-a-word-first`).
    word_first: bool = False

    @property
    def live_scene(self) -> bool:
        """A behavior scene played with a live model behind the column."""

        return bool(self.scene) and not self.scripted


@dataclass
class Context:
    """What every leg of the probe shares."""

    options: Options
    out: Path
    base: Path
    homes: dict[str, str]
    env: dict[str, str]
    secrets: dict[str, str]
    route: Route
    attention: Mapping[str, Any]
    profile: Mapping[str, Any]
    # The scripted attention endpoint, in a scripted run.
    attention_endpoint: Any = None
    # The job's environment as the probe found it, before it became the clean user.
    original_env: Mapping[str, str] = field(default_factory=dict)
    # The behavior scene being played, as the director's spec (`directed.DirectedSpec`); None for the moments.
    directed: Any = None


def _now() -> str:
    return timestamp(datetime.now(timezone.utc))


def _profile() -> dict[str, Any]:
    participant = load_participants()[PARTICIPANT]
    return {
        "display_name": participant["display_name"],
        "names": list(participant.get("names", [participant["display_name"]])),
        "instructions": participant["instructions"],
    }


def _env_names(environment: Mapping[str, str], secret_values: Mapping[str, str]) -> dict[str, list[str]]:
    """The variable names of an environment a process got, and which of them hold a secret; never a value."""

    values = {value for value in secret_values.values() if value}
    return {
        "env": sorted(environment),
        "secrets": sorted(name for name, value in environment.items() if value in values),
    }


def _summarize_action(action: Any) -> dict[str, Any]:
    if action is None:
        return {"kind": "silence"}
    if not isinstance(action, Mapping):
        return {"kind": type(action).__name__}
    keep = ("kind", "text", "reaction", "target_event_id", "operation", "why")
    return {key: action[key] for key in keep if key in action}


# -- one harness in the room ---------------------------------------------------------------


class Leg:
    """One harness taking part in the stand-in room; subclasses adapt each harness."""

    harness = ""
    # Nunchi's actor id for the agent's bot, the bound channel, and the room's continuity scope.
    actor_id = ""
    room_id = ROOM_ID
    scope = ""
    # The harness posts the agent's final answer itself, so its delivery reads "unknown" by design.
    harness_posts = False
    # The agent acts in the room through a room tool, whose calls the harness's own record shows (`room_calls`).
    room_tools = False

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self.invocations: list[dict[str, Any]] = []
        self.binds: list[dict[str, Any]] = []
        self.committed: list[dict[str, Any]] = []
        self.attention_calls: list[dict[str, Any]] = []
        self.configs: list[tuple[str, Path]] = []
        self.commands: list[dict[str, Any]] = []
        self.reports: dict[str, Any] = {}
        self.install: dict[str, Any] = {}
        self.actual_homes: dict[str, str] = {}
        # The environments of the harness's processes that no command in ``commands`` starts
        # (variable names only); ``agent_shell`` marks the agent's own commands' environment.
        self.processes: list[dict[str, Any]] = []
        # Whether the harness's sandbox was on, as the harness showed it (`sandbox_status`).
        self.sandbox: dict[str, Any] = {}
        # Where the harness showed it did not run as the probe configured it (pins-and-isolation).
        self.not_as_configured: list[str] = []
        # Turn failures, including an unconfirmed delivery.
        self.harness_failures: list[str] = []
        self.tool_names: list[str] = []
        # Optional room tool records for generic checks.
        self.room_calls: list[dict[str, Any]] | None = None
        # What the integration declares its harness shows by itself (`turn_conformance.KnownGap`).
        self.known_gaps: list[Any] = []
        # How the wake the host handed each turn showed its trigger was addressed (`RoomScript.received`), by trigger: what a live
        # scene reads in place of the scripted model's requests (`discord-addressing`).
        self.wake_views: dict[str, dict[str, Any]] = {}
        # The attention calls this process made (the in-process legs), counted as they are made.
        self.attention_calls_made = 0
        self._ids: dict[str, str] = {}
        self._lock = threading.Lock()

    # -- what each harness supplies --------------------------------------------------------

    def prepare(self) -> None:
        raise NotImplementedError

    def deliver(self, raw: Mapping[str, Any], at: datetime, scene: Scene, sequence: int) -> dict[str, Any]:
        raise NotImplementedError

    def settle(self, timeout: float) -> bool:
        raise NotImplementedError

    def room_effects(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def collect(self) -> None:
        """Copy the harness's own transcript and the participant's receipts into the outputs."""

    def close(self) -> None:
        pass

    @property
    def room(self) -> Any:
        raise NotImplementedError

    # -- shared --------------------------------------------------------------------------------

    def ran(self, what: str, argv: Sequence[str], environment: Mapping[str, str], *, cwd: Any = None) -> None:
        """Record a command the probe or an integration ran: its argv, cwd and variable names."""

        entry: dict[str, Any] = {"what": what, "argv": [str(item) for item in argv]}
        if cwd is not None:
            entry["cwd"] = str(cwd)
        entry.update(_env_names(environment, self.ctx.secrets))
        with self._lock:
            self.commands.append(entry)

    def runs_in(self, process: str, environment: Mapping[str, str], *, agent_shell: bool = False) -> None:
        """Record the variable names of a process no recorded command starts."""

        entry: dict[str, Any] = {"process": process, **_env_names(environment, self.ctx.secrets)}
        if agent_shell:
            entry["agent_shell"] = True
        self.processes.append(entry)

    def version(self, argv: Sequence[str], environment: Mapping[str, str]) -> str | None:
        self.ran("the harness's version, for the record", argv, environment)
        return _version_text(argv, environment)


    # -- a live scene (`directed.py`) ----------------------------------------------------------------

    # Whether the column's turns say which messages they read as unattended (the in-process legs do; the reference out of process, live, does not).
    observes_unattended = True

    @property
    def live_run(self) -> bool:
        """Whether a live model is behind the column: the run is not scripted."""

        return not getattr(getattr(self.ctx, "options", None), "scripted", True)

    def refresh(self) -> None:
        """Bring ``invocations`` and ``committed`` up to date with a column that runs outside this process: none for the in-process legs."""

    def begun(self, event_id: str) -> bool:
        """Whether the column's turn has begun on ``event_id``: the earliest signal the column has, which a live hold posts on.

        The in-process legs record a turn the moment the host hands it to the
        harness (`instrument`).
        """

        with self._lock:
            return any(turn.get("trigger") == event_id for turn in self.invocations)

    def shown_to_turn(self, event_ids: Sequence[str], since: str | None, until: str | None = None) -> list[str] | None:
        """Which of ``event_ids`` the column's own record shows the turn was shown from ``since`` to ``until``; None where it shows no such thing."""

        return None

    def live_check(self, moments: Sequence[Mapping[str, Any]]) -> Check:
        """The plumbing a live scene is still held to (`checks.live_scene_plumbing`); the grades are reported."""

        return checks_module.live_scene_plumbing(
            moments, committed=self.committed, room_tool_calls=(self.room_calls or []) if self.room_tools else None
        )

    def model_calls(self) -> dict[str, Any]:
        """The model calls this column made in the run, counted: ``agent`` (None where not counted), ``attention``, and how."""

        return {"agent": None, "attention": self.attention_calls_made, "basis": "not counted for this column"}

    def person_id(self, name: str) -> str:
        """A Discord id for one of the scene's people or bots; the agent is its bot."""

        if name == PARTICIPANT:
            return BOT_ID
        with self._lock:
            if name not in self._ids:
                self._ids[name] = str(FIRST_PERSON_ID + len(self._ids))
            return self._ids[name]

    def room_config(self, sections: Mapping[str, Any]) -> tuple[dict[str, Any], Path]:
        """The participant's Nunchi config: the shared sections, and the integration's own."""

        directory = self.ctx.base / "config"
        directory.mkdir(parents=True, exist_ok=True)
        profile = {
            "profile_id": f"{PARTICIPANT}-rehearsal",
            "participant_id": PARTICIPANT,
            "actor_id": self.actor_id,
            "instructions": self.ctx.profile["instructions"],
            "provenance": "rehearsal:probe",
        }
        profile_path = directory / f"{PARTICIPANT}.profile.json"
        raw = json.dumps(profile, sort_keys=True).encode()
        profile_path.write_bytes(raw)
        self.configs.append(("participant profile", profile_path))
        config = {
            "schema_version": 2,
            "binding": {
                "participant_id": PARTICIPANT,
                "actor_id": self.actor_id,
                "platform": "discord",
                "room_id": self.room_id,
                "continuity_scope_id": self.scope,
                "names": list(self.ctx.profile["names"]),
            },
            "profile": {"path": str(profile_path), "sha256": hashlib.sha256(raw).hexdigest()},
            "attention": {
                "policy": {"preattention_enabled": True, "provenance": "rehearsal:probe@1"},
                "model": dict(self.ctx.attention),
            },
            "limits": {},
            "state_directory": str(self.ctx.base / "state"),
            **sections,
        }
        path = directory / f"{self.harness}.nunchi.json"
        path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
        self.configs.append(("nunchi config", path))
        return config, path


    def receipts(self) -> list[dict[str, Any]]:
        room = self.room
        if room is None:
            return []
        return [dict(record) for record in room.receipts.all_records()]

    # -- what a room other than the in-process stand-in changes (`discord_room.py`) ---------------

    def play(self, spec: MomentSpec, *, settle_seconds: float) -> dict[str, Any]:
        return play_moment(self, spec, settle_seconds=settle_seconds)

    def judge(self, moments: Sequence[dict[str, Any]]) -> None:
        judge_moments(self, moments)

    def scripted_check(self, moments: Sequence[Mapping[str, Any]]) -> Check:
        """With the model and attention scripted, each moment's outcome is known (`checks.scripted_outcomes`)."""

        return checks_module.scripted_outcomes(moments, SCRIPTED_ANSWER)

    def room_checks(self, document: Mapping[str, Any]) -> list[Check]:
        """The room's own hard checks, beside the shared ones: none for the in-process stand-in."""

        return []

    def room_record(self) -> dict[str, Any]:
        """The room's own part of run.json: none for the in-process stand-in."""

        return {}

    def copy_state(self) -> None:
        state = self.ctx.base / "state"
        copy_tree(state, self.ctx.out / "receipts", patterns=("*.jsonl",))


ROOMS = ("discord",)
REFERENCE = "reference"
SCENE_HARNESSES = (REFERENCE,)


def _room_parts(options: Options) -> tuple[type[Leg], tuple[MomentSpec, ...], Route]:
    from . import directed, discord_room

    route = discord_room.reference_route(options.agent_model if options.live_scene else None)
    moments = ((directed.spec(options.scene, word_first=options.word_first),)
               if options.scene else discord_room.MOMENTS)
    return discord_room.LEGS[REFERENCE], moments, route


def _version_text(argv: Sequence[str], environment: Mapping[str, str]) -> str | None:
    try:
        done = subprocess.run(list(argv), capture_output=True, text=True, timeout=60, check=False, env=dict(environment))
    except (OSError, subprocess.SubprocessError):
        return None
    text = (done.stdout or done.stderr or "").strip().splitlines()
    return text[-1] if text else None


# -- the moments -------------------------------------------------------------------------------------


def play_moment(leg: Leg, spec: MomentSpec, *, settle_seconds: float) -> dict[str, Any]:
    """Play one scene as live deliveries, and record what happened at its graded moment.

    Its posts and outcome are judged once the run is over (`judge_moments`),
    when every delivery is known. A wait for the room to go quiet that timed
    out is recorded in its delivery (``settled``) and, where there is one, on
    the moment (``unsettled``); a scripted run fails on it (`checks.unsettled`).
    """

    scene = load_scene(spec.scene)
    graded = scene.moments[0].event
    end = datetime.now(timezone.utc)
    deliveries: list[dict[str, Any]] = []
    first_turn = len(leg.invocations)
    graded_delivery: dict[str, Any] = {}
    for sequence, raw in enumerate(scene.events):
        offset = parse_offset(raw["at"]) if "at" in raw else 0
        delivery = leg.deliver(raw, end - timedelta(seconds=offset), scene, sequence)
        delivery["settled"] = leg.settle(settle_seconds)
        deliveries.append(delivery)
        if raw["id"] == graded:
            graded_delivery = delivery
    turns = leg.invocations[first_turn:]
    graded_turns = [turn for turn in turns if turn.get("trigger") == graded_delivery.get("event_id")]
    moment = {
        "name": spec.name,
        "scene": str(spec.scene.relative_to(ROOT)) if spec.scene.is_relative_to(ROOT) else str(spec.scene),
        "graded_event": graded_delivery.get("event_id"),
        # Whether the graded message reached Nunchi: when it did not, the moment tested nothing.
        "reached": bool(graded_delivery.get("observed")),
        "expect": spec.expect,
        "deliveries": deliveries,
        "turns": turns,
        "graded_turns": len(graded_turns),
        # How attention woke each graded turn: ERROR_FALLBACK is not attention's judgment.
        "graded_wake_sources": [turn.get("source") for turn in graded_turns],
        "other_turns": len(turns) - len(graded_turns),
    }
    late = checks_module.unsettled(deliveries)
    if late:
        # A wait for the room to go quiet ran out: the record may lack what came after (`checks.unsettled`).
        moment["unsettled"] = late
    return moment


def judge_moments(leg: Leg, moments: Sequence[dict[str, Any]]) -> None:
    """Mark each committed action delivered or not, then each moment's posts and outcome."""

    flags = checks_module.delivered(leg.committed, leg.room_effects(), harness_posts=leg.harness_posts)
    for item, ok in zip(leg.committed, flags):
        item["delivered"] = ok
    for moment in moments:
        graded = {turn["request_id"] for turn in moment["turns"] if turn.get("trigger") == moment["graded_event"]}
        moment["posts"] = [
            {"text": item.get("text"), "delivery": item.get("delivery"), "delivered": item["delivered"]}
            for item in leg.committed
            if item.get("request_id") in graded and item.get("kind") in ("message", "reply")
        ]
        moment["outcome"] = checks_module.moment_outcome(
            moment["expect"],
            reached=moment["reached"],
            graded_turns=moment["graded_turns"],
            delivered_posts=sum(1 for post in moment["posts"] if post["delivered"]),
        )


# -- the run --------------------------------------------------------------------------------------------


def _secret_values(options: Options) -> tuple[str, str, str]:
    """The key for attention, the key for the harness, and the canary; placeholders when scripted.

    A live scene needs every key its column reads under its own name
    (`live_scene_refusal`), and the reference's participant model reads its own
    (`routes.PARTICIPANT_KEY_ENV`).
    """

    canary = os.environ.get(CANARY_ENV) or f"canary-{secrets.token_urlsafe(24)}"
    if options.scripted:
        placeholder = f"scripted-placeholder-{secrets.token_urlsafe(24)}"
        return placeholder, placeholder, canary
    if options.live_scene:
        refusal = live_scene_refusal(options, os.environ)
        if refusal is not None:
            raise CouldNotRun(refusal[1])
    attention_key = os.environ.get(ATTENTION_KEY_ENV)
    if not attention_key:
        raise CouldNotRun(f"{ATTENTION_KEY_ENV} is not set: the live probe needs the OpenRouter key")
    harness_key = os.environ.get(harness_key_env(options.harness)) or attention_key
    return attention_key, harness_key, canary


def _reset(directory: Path) -> None:
    if directory.exists():
        delete_outputs(directory)
    directory.mkdir(parents=True, exist_ok=True)


def _interrupt_on_termination() -> dict[int, Any]:
    """SIGTERM and SIGHUP interrupt the run once, as Ctrl-C does, so its ``finally`` stops the Discord processes.

    They run in sessions of their own, so no signal sent to the probe reaches
    them. A second signal is ignored while the run is wound up. Returns the
    handlers to put back; none where signals cannot be handled (not the main
    thread).
    """

    numbers = (signal.SIGTERM, signal.SIGHUP)
    armed = [True]

    def interrupt(signum: int, _frame: Any) -> None:
        try:
            armed.pop()  # atomic: of signals that arrive together, one interrupts
        except IndexError:
            return
        raise KeyboardInterrupt(f"signal {signum}")

    previous: dict[int, Any] = {}
    for number in numbers:
        if signal.getsignal(number) == signal.SIG_IGN:
            continue  # ignored on purpose, as nohup does
        try:
            previous[number] = signal.signal(number, interrupt)
        except ValueError:
            break
    return previous


def run_probe(options: Options) -> int:
    """Run the probe for one harness; returns the exit status. Restores this process's environment."""

    if options.harness not in HARNESSES and not (options.harness == REFERENCE and options.room == "discord"):
        raise ValueError(f"unknown harness {options.harness!r}")
    if options.room not in ROOMS:
        raise ValueError(f"unknown room {options.room!r}")
    if options.room == "discord" and not options.scripted and not options.scene:
        raise ValueError("the Discord room is scripted unless a scene is played")
    if options.scene and not (options.room == "discord" and options.harness in SCENE_HARNESSES):
        raise ValueError(f"a scene is played in the Discord room by {' or '.join(SCENE_HARNESSES)} (--room discord)")
    refusal = live_scene_refusal(options, os.environ)
    if refusal is not None and refusal[0] == EXIT_USAGE:
        # Off a CI runner, before anything is written or started: the keys are checked as the run begins (`_secret_values`).
        raise ValueError(refusal[1])
    out = options.out / options.harness
    _reset(out)
    original_env = dict(os.environ)
    original_tempdir = tempfile.tempdir
    before: list[dict[str, Any]] = []
    base = Path(tempfile.mkdtemp(prefix="nunchi-rehearsal-"))
    started = _now()
    errors: list[str] = []
    moments: list[dict[str, Any]] = []
    secret_values: dict[str, str] = {}
    harness_env: dict[str, str] = {}
    # Attention credentials for the reference process.
    nunchi_env: dict[str, str] = {}
    homes: dict[str, str] = {}
    could_not_run = False
    ctx: Context | None = None
    leg: Leg | None = None
    spend: SpendWatch | None = None
    scripted_attention: ScriptedAttention | None = None
    leg_class, moment_specs, route = _room_parts(options)
    handlers = _interrupt_on_termination()
    try:
        attention_key, harness_key, canary = _secret_values(options)
        key_env = attention_key_env(options.harness)
        secret_values = {key_env: attention_key, CANARY_ENV: canary}
        homes = Homes(base).create()
        harness_env = clean_environment(homes, route, inherited=original_env)
        harness_env[CANARY_ENV] = canary
        for name in route.secret_env:
            harness_env[name] = harness_key
            secret_values[name] = harness_key
        if key_env not in harness_env:
            nunchi_env[key_env] = attention_key
        secret_values.update(nunchi_env)
        directed = moment_specs[0] if options.scene else None
        if options.scripted:
            scripted_attention = ScriptedAttention(
                (spec.wake_phrase for spec in moment_specs if spec.wake_phrase), script=directed.script if directed else None
            )
            attention = attention_config(
                options.attention_model, base_url=scripted_attention.base_url, provider="scripted", api_key_env=key_env
            )
        else:
            attention = attention_config(options.attention_model, api_key_env=key_env)
        # From here the reference uses only its isolated process environment.
        os.environ.clear()
        os.environ.update(harness_env)
        os.environ.update(nunchi_env)
        tempfile.tempdir = None
        ctx = Context(
            options=options,
            out=out,
            base=base,
            homes=homes,
            # The clean user's environment, for the commands the probe runs for the harness.
            env=dict(harness_env),
            secrets=secret_values,
            route=route,
            attention=attention,
            profile=_profile(),
            attention_endpoint=scripted_attention,
            original_env=original_env,
            directed=directed,
        )
        spend = SpendWatch(None if options.scripted else attention_key, options.budget_usd)
        leg = leg_class(ctx)
        leg.prepare()
        settle = 120.0 if options.scripted else options.turn_timeout_seconds + 60
        spend.read_first("before the first moment")
        for index, spec in enumerate(moment_specs):
            if index and not spend.may_continue(spec.name):
                break
            moments.append(leg.play(spec, settle_seconds=settle))
    except CouldNotRun as exc:
        could_not_run = True
        errors.append(str(exc))
    except Exception as exc:  # recorded: a failed run is still a complete record
        errors.append(f"{type(exc).__name__}: {exc}")
        errors.append("".join(traceback.format_exc().splitlines(keepends=True)[-6:]))
    finally:
        if leg is not None:
            try:
                leg.collect()
            except Exception as exc:
                errors.append(f"collecting the record failed: {type(exc).__name__}: {exc}")
            try:
                leg.close()
            except Exception as exc:
                errors.append(f"closing the harness failed: {type(exc).__name__}: {exc}")
        if spend is not None and not could_not_run:
            # OpenRouter's usage figure lags: the last reading reads it up to a
            # bound and keeps each read, after a failed run too.
            try:
                spend.settle("after the last moment")
            except Exception as exc:
                errors.append(f"the last spend reading failed: {type(exc).__name__}: {exc}")
        if scripted_attention is not None:
            scripted_attention.close()
        os.environ.clear()
        os.environ.update(original_env)
        tempfile.tempdir = original_tempdir
        # urlopen keeps the proxy settings it saw at its first call: the next call builds anew.
        urllib.request.install_opener(None)
        for number, handler in handlers.items():
            signal.signal(number, handler)
    after: list[dict[str, Any]] = []
    if leg is not None:
        try:
            leg.judge(moments)
        except Exception as exc:
            errors.append(f"judging the moments failed: {type(exc).__name__}: {exc}")
    # A key echoed in an exception is replaced by its name, so it does not cost the whole record.
    errors = [redact(error, secret_values) for error in errors]
    document = _record(
        options=options,
        leg=leg,
        # The route as the leg set it up: a scripted run's points at its scripted endpoint.
        route=ctx.route if ctx is not None else route,
        base=base,
        homes=homes,
        nunchi_env=nunchi_env,
        moments=moments,
        spend=spend,
        errors=errors,
        started=started,
        before=before,
        after=after,
    )
    checks: list[Check] = []
    if leg is not None and not could_not_run:
        checks = _checks(
            leg, document, base=base, before=before, after=after, scripted=options.scripted, live_scene=options.live_scene
        )
    stopped = spend is not None and spend.stopped_before is not None
    status = _finish(out, document, secret_values, checks, could_not_run=could_not_run, stopped=stopped)
    if not options.keep_work:
        shutil.rmtree(base, ignore_errors=True)
    print((out / "summary.md").read_text(encoding="utf-8"))
    return status


def _record(
    *,
    options: Options,
    leg: Leg | None,
    route: Route,
    base: Path,
    homes: Mapping[str, str],
    nunchi_env: Mapping[str, str],
    moments: list[dict[str, Any]],
    spend: SpendWatch | None,
    errors: list[str],
    started: str,
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> dict[str, Any]:
    """run.json, apart from its checks; also writes the turns, attention calls and room effects."""

    out = options.out / options.harness
    configs = []
    if leg is not None:
        for name, path in leg.configs:
            if path.exists():
                configs.append(config_entry(name, path, base=base))
        write_json(out / "turns.json", {"turns": leg.invocations, "binds": leg.binds, "committed": leg.committed})
        write_json(out / "attention.json", leg.attention_calls)
        write_json(out / "room.json", {"effects": leg.room_effects()})
    attention_served: list[dict[str, Any]] = []
    for call in leg.attention_calls if leg is not None else ():
        served = call.get("served") or {}
        entry = {"model": served.get("model"), "provider": served.get("provider")}
        if served and entry not in attention_served:
            attention_served.append(entry)
    return {
        "schema": SCHEMA,
        "harness": options.harness,
        "arm": options.arm,
        "mode": "scripted" if options.scripted else "live",
        "started_at": started,
        "finished_at": _now(),
        "command": options.command or [sys.executable, "-m", "evals.rehearsal.probe"],
        "commit": git_commit(ROOT),
        "nunchi": nunchi_install(options.wheel),
        "python": python_identity(),
        "python_packages": python_packages(),
        "harness_install": leg.install if leg is not None else {},
        "binding": {
            "participant_id": PARTICIPANT,
            "actor_id": leg.actor_id if leg is not None else None,
            "room_id": leg.room_id if leg is not None else ROOM_ID,
            "continuity_scope_id": leg.scope if leg is not None else None,
            "names": list(_profile()["names"]),
        },
        "models": {
            "agent": {"requested": options.agent_model, "route": route.describe(), "served": _agent_served(out)},
            "attention": {"requested": options.attention_model, "served": attention_served},
        },
        "configs": configs,
        "commands": leg.commands if leg is not None else [],
        "environment": {
            # Every command above lists the variables it ran with; these are the harness's
            # processes that no recorded command starts.
            "processes": leg.processes if leg is not None else [],
            "nunchi_process_only": sorted(nunchi_env),
            "attention_key": attention_key_env(options.harness),
            "harness_keys": list(route.secret_env),
            "canary": CANARY_ENV,
            "note": (
                "variable names only, never a value: each command's and each process's, as the integration or "
                "the harness's own builder handed them; 'secrets' names the variables holding a key or the canary"
            ),
        },
        "isolation": {
            "work_directory": str(base),
            "homes": dict(homes),
            "actual_homes": dict(leg.actual_homes) if leg is not None else {},
            "homes_written": {
                name: tree_sizes(Path(path)) for name, path in (leg.actual_homes if leg is not None else {}).items()
            },
            "user_homes_before": before,
            "user_homes_after": after,
        },
        "spend": _spend_document(options, leg, spend),
        "moments": moments,
        "reports": leg.reports if leg is not None else {},
        "lane_errors": list(leg.room.errors) if leg is not None and leg.room is not None else [],
        "errors": errors,
        **(leg.room_record() if leg is not None else {}),
    }


def _spend_document(options: Options, leg: Leg | None, spend: SpendWatch | None) -> dict[str, Any]:
    """The spend watchdog's record; for a live scene also the model calls the column counted and what they would cost (`spend.estimate_usd`)."""

    document = spend.document() if spend is not None else {"budget_usd": options.budget_usd}
    if options.live_scene and leg is not None:
        try:
            calls = leg.model_calls()
        except Exception as exc:  # recorded as not counted: `checks.spend_recorded` then fails the run, and the record is still whole
            calls = {"agent": None, "attention": None, "basis": f"not counted: {type(exc).__name__}: {exc}"[:300]}
        document["model_calls"] = calls
        document["estimated_usd"] = estimate_usd(options.harness, calls)
    return document


def _agent_served(out: Path) -> list[dict[str, Any]]:
    """The providers (and models) the harness's transcripts name, as OpenRouter reported them."""

    found: list[dict[str, Any]] = []
    directory = out / "transcript"
    if not directory.exists():
        return found
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix not in (".json", ".jsonl"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for chunk in text.splitlines() if path.suffix == ".jsonl" else [text]:
            try:
                document = json.loads(chunk)
            except ValueError:
                continue
            for entry in served_providers(document):
                if entry not in found:
                    found.append(entry)
    return found


def _checks(
    leg: Leg,
    document: Mapping[str, Any],
    *,
    base: Path,
    before: Sequence[Mapping[str, Any]],
    after: Sequence[Mapping[str, Any]],
    scripted: bool,
    live_scene: bool = False,
) -> list[Check]:
    """The hard checks; the scan runs over the written outputs (`_finish`).

    A live scene holds no script to its scene: its grades are reported
    (`directed.judge_scene`), so `scripted_check` is not among them, and it must
    record what it spent (`checks.spend_recorded`).
    """

    install = leg.install or {}
    host_receipts = [record for record in leg.receipts() if record.get("stage") == "participant-host"]
    ids = [*(turn["request_id"] for turn in leg.invocations), *leg.tool_names]
    environment = document["environment"]
    checks = [
        checks_module.pins_and_isolation(
            harness_version=install.get("version"),
            expected=str(install.get("expected") or "discord.py 2.7.1"),
            actual_homes=leg.actual_homes,
            base=str(base),
            user_homes_before=before,
            user_homes_after=after,
            processes=[*leg.commands, *leg.processes],
            harness_keys=environment["harness_keys"],
            canary=environment["canary"],
            not_as_configured=leg.not_as_configured,
        ),
        checks_module.record_complete(document, require_wheel=bool(document["nunchi"].get("wheel"))),
        checks_module.turns_bound_and_ended(leg.invocations, host_receipts, leg.committed, harness_failures=leg.harness_failures),
        checks_module.turns_on_others_messages(
            leg.invocations,
            [delivery.get("event_id") for moment in document["moments"] for delivery in moment.get("deliveries", ())],
        ),
        checks_module.attention_judged(leg.attention_calls, leg.invocations),
        checks_module.one_room_action_per_turn(leg.committed, [item.get("delivered", False) for item in leg.committed]),
        checks_module.no_leaks(leg.committed, leg.room_effects(), ids, known_gaps=leg.known_gaps),
    ]
    checks += leg.room_checks(document)
    if scripted:
        checks.append(leg.scripted_check(document["moments"]))
    if live_scene:
        checks.append(leg.live_check(document["moments"]))
        checks.append(checks_module.spend_recorded(document, turns=len(leg.invocations)))
    return checks


def _finish(
    out: Path,
    document: dict[str, Any],
    secret_values: Mapping[str, str],
    checks: list[Check],
    *,
    could_not_run: bool,
    stopped: bool,
) -> int:
    """Write the record, then scan every output (`scan.enforce`): a hit deletes them all and fails the run."""

    document["checks"] = [check.document() for check in checks]
    _set_status(document, checks, could_not_run=could_not_run, stopped=stopped)
    _write(out, document)
    if not enforce(out, secret_values)["clean"]:
        return EXIT_FAILED
    return int(document["exit_code"])


def _set_status(document: dict[str, Any], checks: Sequence[Check], *, could_not_run: bool, stopped: bool) -> None:
    if could_not_run:
        status, code = "could-not-run", EXIT_COULD_NOT_RUN
    elif any(not check.ok for check in checks) or document.get("errors"):
        status, code = "fail", EXIT_FAILED
    elif stopped:
        status, code = "stopped-at-budget", EXIT_BUDGET
    else:
        status, code = "pass", EXIT_PASS
    document["status"] = status
    document["exit_code"] = code


def _write(out: Path, document: Mapping[str, Any]) -> None:
    write_json(out / "run.json", document)
    write_json(out / "checks.json", document.get("checks", []))
    (out / "summary.md").write_text(summary_markdown(document), encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m evals.rehearsal.probe", description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--harness",
        required=True,
        choices=HARNESSES,
        help=f"{REFERENCE}: nunchi-discord with a scripted participant, in the Discord room only (--room discord --scripted)",
    )
    parser.add_argument("--out", required=True, help="output directory; the run writes <out>/<harness>/")
    parser.add_argument("--budget-usd", type=float, default=2.0, help="stop before the next moment once the key has spent this (soft)")
    parser.add_argument("--agent-model", default=DEFAULT_AGENT_MODEL)
    parser.add_argument("--attention-model", default=DEFAULT_ATTENTION_MODEL, help="an OpenRouter id, optionally @effort")
    parser.add_argument("--scripted", action="store_true", help="offline: scripted model endpoints, no key, no network")
    parser.add_argument("--wheel", help="the Nunchi wheel installed for this run, to record its sha256")
    parser.add_argument("--turn-timeout", type=float, default=300.0, help="seconds one reference turn may take")
    parser.add_argument("--keep-work", action="store_true", help="keep the throwaway homes after the run")
    parser.add_argument("--arm", default="", help="a label for this run as one arm of a comparison, recorded and shown in the summary")
    parser.add_argument(
        "--room",
        choices=ROOMS,
        default="discord",
        help="the reference Discord process on the Discord stand-in, "
        "inside the launcher (python -m evals.rehearsal.discord_net)",
    )
    parser.add_argument(
        "--scene",
        metavar="ID",
        help="play this behavior scene instead of the moments, graded from its own expectations (--room discord, "
        f"--harness {' or '.join(SCENE_HARNESSES)}; one scene per run; draft expectations; see directed.py). With --scripted it is offline "
        "and every grade is a hard check; without it a live model plays the agent, on a CI runner only, and the grades are reported",
    )
    parser.add_argument(
        "--nod-with-a-word-first",
        action="store_true",
        help="with --scripted --scene: the scripted agent's nod is first a word, which the core refuses before committing anything "
        "(a tool error, or the turn's next page), and then the emoji, in the same turn. One case of the scripted lanes; "
        "a hard check holds that every nod was refused once and then made",
    )
    parser.add_argument(
        "--discord-python",
        help="the Python that runs the Discord processes, with Nunchi installed (the reference also needs discord.py); "
        "default this one",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    args = _parser().parse_args(arguments)
    if not 0 < args.budget_usd < float("inf"):  # nan and inf compare as neither: a budget that stops nothing is no budget
        print("--budget-usd must be a positive, finite number", file=sys.stderr)
        return EXIT_USAGE
    if args.harness == REFERENCE and args.room != "discord":
        print(f"--harness {REFERENCE} runs in the Discord room only: pass --room discord --scripted", file=sys.stderr)
        return EXIT_USAGE
    if args.room == "discord" and not args.scripted and not args.scene:
        print(
            "--room discord is scripted unless a scene is played: pass --scripted, or --scene ID for a live scene (on a CI runner only); "
            "the reference moments require --scripted",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if args.nod_with_a_word_first and not (args.scene and args.scripted):
        print("--nod-with-a-word-first scripts the agent's nod, so it needs --scripted and --scene", file=sys.stderr)
        return EXIT_USAGE
    if args.scene:
        if not (args.harness in SCENE_HARNESSES and args.room == "discord"):
            print(
                f"--scene is played by --harness {' or '.join(SCENE_HARNESSES)} with --room discord",
                file=sys.stderr,
            )
            return EXIT_USAGE
        from . import directed

        try:
            directed.spec(args.scene, word_first=args.nod_with_a_word_first)
        except directed.Unplayable as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_USAGE
    try:
        attention_config(args.attention_model)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    options = Options(
        harness=args.harness,
        out=Path(args.out).absolute(),
        budget_usd=args.budget_usd,
        # The reference's agent is its scripted plain-call participant, or, in a live scene, the agent's model: the control.
        agent_model="scripted-participant" if args.harness == REFERENCE and args.scripted else args.agent_model,
        attention_model=args.attention_model,
        scripted=args.scripted,
        wheel=Path(args.wheel).absolute() if args.wheel else None,
        keep_work=args.keep_work,
        turn_timeout_seconds=args.turn_timeout,
        command=["python", "-m", "evals.rehearsal.probe", *arguments],
        arm=args.arm,
        room=args.room,
        discord_python=str(Path(args.discord_python).absolute()) if args.discord_python else None,
        scene=args.scene,
        word_first=args.nod_with_a_word_first,
    )
    refusal = live_scene_refusal(options, os.environ)
    if refusal is not None:
        # Nothing has started, nothing was written and nothing was spent.
        print(refusal[1], file=sys.stderr)
        return refusal[0]
    return run_probe(options)


if __name__ == "__main__":
    # One module whether run or imported: the Discord room's legs subclass this module's
    # classes (`discord_room.py`), so `python -m` runs the imported module's main.
    from evals.rehearsal.probe import main as _main

    raise SystemExit(_main())
