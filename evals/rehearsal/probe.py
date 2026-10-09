"""The probe: does each real harness reach a live model and take part in a room through Nunchi? (#94 step 9f, PR 1)

    python -m evals.rehearsal.probe --harness {claude-code,codex,hermes} --out DIR \\
        --budget-usd 2 --agent-model anthropic/claude-haiku-4.5 \\
        --attention-model openai/gpt-6-luna@low [--scripted] [--arm LABEL]

One harness per run, on its pinned install, as a clean user: fresh HOME,
CODEX_HOME, HERMES_HOME, CLAUDE_CONFIG_DIR and TMPDIR, and nothing else of
the job's environment but the path, the locale and the network settings.
The agent's model goes through OpenRouter on the harness's own route
(`routes.py`); attention is live too, on OpenRouter's chat route, with its key
in ``NUNCHI_ATTENTION_API_KEY`` in Nunchi's own process, or, beside Hermes,
which runs the plugin in its own process, in Hermes's ``OPENROUTER_API_KEY``
(`routes.attention_key_env`). ``run.json`` records the variable names each
process got, and the pins-and-isolation check fails when a process got a key
it should not.

The room is the in-process stand-in the tests already have (`standin.py`):

- Claude Code and Codex run through their production runtimes
  (`ClaudeCodeRoomRuntime`, `CodexRoomRunner`) with the stand-in in place of
  the shared Discord transport;
- Hermes runs the real `GatewayRunner` in this process, on the conformance
  kit's Discord world, with the shipped plugin directory loaded by Hermes
  from a Nunchi config written as its README says, and the README's
  peer-agent settings so that it hears the bot's status report
  (`HERMES_PEER_AGENTS`).

Two moments, each a scene played message by message as live deliveries,
with each message's time taken from the scene (backdated where the scene
says so). The status report goes first, so the room's clock only moves
forward:

1. a bot's status report (`evals/behavior/scenes/behavior/bot-status-report.json`):
   expected, no harness turn;
2. a person asks the agent a direct question (`scenes/direct-question.json`):
   expected, a wake, a bound turn and exactly one room post.

A pass means exactly that the harness reached its model and took part in
the room through Nunchi, with attention judging: the hard checks in
`checks.py`, each of which fails the run with its reason at the top of
summary.md. In a live run, whether each moment went as expected is reported,
never a failure: the model decides. Each moment is judged once the run is
over (`judge_moments`), when every delivery is known; a moment whose graded
message never reached Nunchi reads ``not delivered``. Everything is recorded
under ``DIR/<harness>/`` (`record.py`), then every output is scanned for the
key and the canary (`scan.enforce`: a hit deletes them all and fails the
run), and the key's spend is read between moments (`spend.py`).

``--scripted`` runs the same probe offline: the agent's model is the
conformance kit's scripted endpoint, attention is a scripted endpoint that
wakes only for the direct question, and nothing needs a key. Each moment's
outcome is then known, so it is a hard check too (`checks.scripted_outcomes`).
It is available for Codex and Hermes; Claude Code's needs a scripted
Anthropic Messages endpoint, which is PR 2.

Exit status: 0 every hard check held; 1 a hard check failed, the probe
raised an error, or the scan found a secret; 2 bad arguments (among them a
Claude Code agent model with no row in `routes.CLAUDE_CODE_MODELS`); 3 the
probe could not run (a harness or a key is missing); 4 it stopped at the
budget before a moment, every hard check holding; 5 ``--scripted`` is not available
for this harness yet.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
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
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from types import SimpleNamespace
from typing import Any
from unittest import mock

from evals.behavior.scene import SCENES as BEHAVIOR_SCENES, Scene, load_participants, load_scene, parse_offset

from . import checks as checks_module
from .checks import PROBE_SCENARIO, Check
from .record import (
    SCHEMA,
    config_entry,
    copy_tree,
    git_commit,
    home_snapshot,
    npm_packages,
    nunchi_install,
    python_identity,
    python_packages,
    recording_app_server,
    recording_claude_session,
    redact,
    served_providers,
    sqlite_tables,
    summary_markdown,
    tree_sizes,
    write_json,
)
from .routes import (
    ATTENTION_KEY_ENV,
    CANARY_ENV,
    CLAUDE_SETTINGS,
    DEFAULT_AGENT_MODEL,
    DEFAULT_ATTENTION_MODEL,
    HARNESS_KEY_ENV,
    HARNESSES,
    OPENROUTER,
    OUTPUT_KEY_ENV,
    PINS,
    ClaudeModel,
    Homes,
    Route,
    attention_config,
    attention_key_env,
    claude_code_model,
    clean_environment,
    codex_config,
    hermes_auxiliary_tasks,
    hermes_model_config,
    hermes_section,
    route_for,
)
from .scan import delete_outputs, enforce
from .spend import SpendWatch
from .standin import (
    JsonLines,
    ScriptedAttention,
    ScriptedCodexAgent,
    ScriptedHermesAgent,
    StandInRoomClient,
    snowflake,
    timestamp,
)

EXIT_PASS = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_COULD_NOT_RUN = 3
EXIT_BUDGET = 4
EXIT_NOT_YET = 5

NOT_YET = (
    "claude-code --scripted is not available yet: running the real claude CLI offline needs a scripted "
    "Anthropic Messages endpoint (step 9f, PR 2). Until then tests/v2/test_rehearsal.py covers the Claude "
    "Code leg with a faked claude process."
)

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
    # "post": a wake, a bound turn, one room post. "no-turn": no harness turn.
    expect: str
    # Scripted attention wakes for a message holding this phrase.
    wake_phrase: str | None = None


# The status report first: its first message is 30 minutes old, so playing it
# second would put it before the question in the room's log.
MOMENTS = (
    MomentSpec("bot-status-report", BEHAVIOR_SCENES / "behavior" / "bot-status-report.json", "no-turn"),
    MomentSpec("direct-question", SCENES / "direct-question.json", "post", "sensible default timeout"),
)


class CouldNotRun(RuntimeError):
    """The probe could not reach the room: a harness, a key or a setting is missing."""


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
    claude_bin: str | None = None
    codex_bin: str | None = None
    expect_version: str | None = None
    keep_work: bool = False
    turn_timeout_seconds: float = 300.0
    command: list[str] = field(default_factory=list)
    # A label for a run that is one arm of a comparison (the workflow's OpenAI-model arm for Codex).
    arm: str = ""


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


def _now() -> str:
    return timestamp(datetime.now(timezone.utc))


def _profile() -> dict[str, Any]:
    participant = load_participants()[PARTICIPANT]
    return {
        "display_name": participant["display_name"],
        "names": list(participant.get("names", [participant["display_name"]])),
        "instructions": participant["instructions"],
    }


def _homes(environment: Mapping[str, str], own_home: str) -> dict[str, str]:
    """The homes in the environment the integration hands its harness: HOME, TMPDIR and the harness's own."""

    return {name: environment.get(name, "") for name in ("HOME", "TMPDIR", own_home)}


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
    # Nunchi's actor id for the agent's bot, and the room's continuity scope.
    actor_id = ""
    scope = ""
    # The harness posts the agent's final answer itself, so its delivery reads "unknown" by design.
    harness_posts = False

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
        self.tool_names: list[str] = []
        # What the integration declares its harness shows by itself (`turn_conformance.KnownGap`).
        self.known_gaps: list[Any] = []
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

    def npm(self, executable: str) -> dict[str, Any] | None:
        packages = npm_packages(executable)
        if packages is not None and packages.get("command"):
            command = packages.pop("command")
            self.ran("npm ls, the harness's install, for the record", command["argv"], command["env"])
        return packages

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
                "room_id": ROOM_ID,
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

    def instrument(self, participant: Any, room: Any) -> None:
        """Watch, without changing, each turn the host hands the harness and each committed action."""

        run_protocol = participant.run_protocol

        def recorded_run(*, wake, opportunity, expand, cancel):
            entry: dict[str, Any] = {
                "request_id": wake["request_id"],
                "trigger": wake.get("trigger_event_id"),
                "source": (wake.get("attention") or {}).get("source"),
                "started": _now(),
            }
            with self._lock:
                self.invocations.append(entry)
            try:
                action = run_protocol(wake=wake, opportunity=opportunity, expand=expand, cancel=cancel)
            except BaseException as exc:
                entry["error"] = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                entry["ended"] = _now()
                entry["bound"] = any(item["request_id"] == entry["request_id"] and item["bound"] for item in self.binds)
            entry["result"] = _summarize_action(action)
            return action

        participant.run_protocol = recorded_run
        bind_turn = participant.bind_turn

        def recorded_bind(*, turn_id, wake_id):
            active = participant.active
            bound = bind_turn(turn_id=turn_id, wake_id=wake_id)
            with self._lock:
                self.binds.append(
                    {
                        "request_id": getattr(active, "request_id", None),
                        "turn_id": turn_id,
                        "bound": bool(bound),
                        "with_wake_id": wake_id is not None,
                        "at": _now(),
                    }
                )
            return bound

        participant.bind_turn = recorded_bind
        self.instrument_room(room)

    def instrument_room(self, room: Any) -> None:
        transport = room.host.transport
        dispatch = transport.dispatch

        def recorded_dispatch(*, action, wake):
            # Recorded before it leaves: a dispatch that raises stays "pending", never unseen.
            entry = {"request_id": wake.get("request_id"), **_summarize_action(action), "delivery": "pending"}
            entry.pop("why", None)
            with self._lock:
                self.committed.append(entry)
            result = dispatch(action=action, wake=wake)
            entry.update({"delivery": result.delivery, "detail": result.detail})
            return result

        transport.dispatch = recorded_dispatch
        model = room.attention.model
        if model is None:
            return
        judge = model.judge

        def recorded_judge(*, instructions, projection, timeout_seconds):
            entry: dict[str, Any] = {"trigger": projection.get("trigger_event_id"), "model": getattr(model, "model_id", None)}
            try:
                return judge(instructions=instructions, projection=projection, timeout_seconds=timeout_seconds)
            except BaseException as exc:
                entry["error"] = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                response = getattr(model, "last_response", None)
                if isinstance(response, Mapping):
                    entry["served"] = {
                        "model": response.get("model"),
                        "provider": response.get("provider"),
                        "usage": response.get("usage"),
                    }
                with self._lock:
                    self.attention_calls.append(entry)

        model.judge = recorded_judge

    def receipts(self) -> list[dict[str, Any]]:
        room = self.room
        if room is None:
            return []
        return [dict(record) for record in room.receipts.all_records()]

    def copy_state(self) -> None:
        state = self.ctx.base / "state"
        copy_tree(state, self.ctx.out / "receipts", patterns=("*.jsonl",))


# -- Claude Code and Codex: the library hosts the harness, on the shared transport ---------------------


class SharedTransportLeg(Leg):
    """A library-hosted harness: its runtime takes the room from the shared Discord transport's stand-in."""

    actor_id = f"discord:actor:{BOT_ID}"
    scope = f"discord:channel:{ROOM_ID}"

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self.client = StandInRoomClient(
            participant_id=PARTICIPANT,
            room_id=ROOM_ID,
            actor_id=self.actor_id,
            secret=ctx.secrets[OUTPUT_KEY_ENV].encode(),
            display_name=ctx.profile["display_name"],
            wire=JsonLines(ctx.out / "wire.jsonl"),
        )
        self.connection: Any = None
        self.participant: Any = None
        self._room: Any = None

    @property
    def room(self) -> Any:
        return self._room

    def transport_section(self) -> dict[str, Any]:
        # The stand-in is in process; the URL is never dialled.
        return {"url": "http://127.0.0.1:9/mcp", "timeout_seconds": 30, "output_key_env": OUTPUT_KEY_ENV}

    def deliver(self, raw: Mapping[str, Any], at: datetime, scene: Scene, sequence: int) -> dict[str, Any]:
        if raw.get("type", "message") != "message":
            raise CouldNotRun(f"the probe plays messages only, not {raw.get('type')}")
        message_id = snowflake(at, sequence)
        event_id = f"discord:message:{message_id}"
        author = f"discord:actor:{self.person_id(raw['author'])}"
        mentioned = [f"discord:actor:{self.person_id(name)}" for name in raw.get("mentions", ())]
        event: dict[str, Any] = {
            "id": event_id,
            "type": "message",
            "author_id": author,
            "text": raw["text"],
            "mentioned_actor_ids": mentioned,
            "mentions_room": bool(raw.get("mentions_room", False)),
            "timestamp": timestamp(at),
        }
        actors = {}
        for name in (raw["author"], *raw.get("mentions", ())):
            actor = scene.actors.get(name, {})
            actors[f"discord:actor:{self.person_id(name)}"] = {
                "display_name": actor.get("display_name", name),
                "kind": actor.get("kind", "unknown"),
            }
        self.connection.handle(self.client.notification(event, actors, f"rehearsal:{event_id}"))
        return {
            "scene_event": raw["id"],
            "event_id": event_id,
            "author": author,
            "reached_nunchi": True,
            "observed": self._room.observation.resolve_event(event_id) is not None,
        }

    def settle(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        drained = self._room.drain(timeout)
        while self.participant.active is not None and time.monotonic() < deadline:
            time.sleep(0.1)
        for echo in self.client.take_echoes():
            # The shared transport shows the bot's own message back to its room.
            self.connection.handle(self.client.notification(echo, self.client.self_actor(), f"rehearsal:echo:{echo['id']}"))
        self._room.drain(max(1.0, deadline - time.monotonic()))
        return drained and self.participant.active is None

    def room_effects(self) -> list[dict[str, Any]]:
        return list(self.client.effects)


class ClaudeCodeLeg(SharedTransportLeg):
    harness = "claude-code"

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self.runtime: Any = None
        self.settings: Mapping[str, Any] = {}
        self.model: ClaudeModel | None = None
        self.transcript = JsonLines(ctx.out / "transcript" / "claude-stream.jsonl")
        self.launched: list[dict[str, Any]] = []

    def executable(self) -> str:
        found = (
            self.ctx.options.claude_bin
            or shutil.which("claude", path=self.ctx.env.get("PATH"))
        )
        if not found or not os.access(found, os.X_OK):
            raise CouldNotRun("Claude Code is not installed: pass --claude-bin or set NUNCHI_CLAUDE_BIN")
        return str(Path(found).absolute())

    def prepare(self) -> None:
        from nunchi.integrations import claude_code_v2
        from nunchi.integrations.claude_code_gate import full_tool_name

        executable = self.executable()
        try:
            self.model = claude_code_model(self.ctx.route.model)
        except ValueError as exc:
            raise CouldNotRun(str(exc)) from exc
        # The README's settings, and the slug mapped to the id Claude Code knows the model by.
        self.settings = {**CLAUDE_SETTINGS, "modelOverrides": {self.model.anthropic_id: self.ctx.route.model}}
        settings = Path(self.ctx.homes["CLAUDE_CONFIG_DIR"]) / "settings.json"
        settings.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        self.configs.append(("claude code user settings", settings))
        work = self.ctx.base / "work"
        work.mkdir(parents=True, exist_ok=True)
        config, _ = self.room_config(
            {
                "transport": self.transport_section(),
                "claude_code": {
                    "executable": executable,
                    "working_directory": str(work),
                    "model": self.ctx.route.model,
                    "session_mode": "fresh",
                    "timeout_seconds": self.ctx.options.turn_timeout_seconds,
                },
            }
        )
        (self.ctx.out / "transcript").mkdir(parents=True, exist_ok=True)
        session_class = recording_claude_session(self.transcript, self.launched)
        with mock.patch.object(claude_code_v2, "ClaudeCodeSession", session_class):
            runtime = claude_code_v2.ClaudeCodeRoomRuntime(config, self.client)
        self.runtime = runtime
        self.install = {
            "version": self.version([executable, "--version"], runtime.user_environment()),
            "expected": self.ctx.options.expect_version or PINS["claude-code"],
            "executable": executable,
            "mod_version": claude_code_v2.mod_version(),
            "npm": self.npm(executable),
        }
        self.ran("the runtime's version floor (claude_code_version)", [executable, "--version"], runtime.user_environment())
        try:
            runtime.require_supported_claude_code()
        except Exception as exc:  # the runtime's own version floor
            raise CouldNotRun(f"Claude Code cannot run the mod: {exc}") from exc
        self.connection = runtime.connection
        self.participant = runtime.participant
        self._room = runtime.room
        self.actual_homes = _homes(runtime.session_environment(), "CLAUDE_CONFIG_DIR")
        self.tool_names = [full_tool_name(role) for role in runtime.participant.registered_roles]
        self.instrument(runtime.participant, runtime.room)
        runtime.start()
        runtime.register_transport()

    def collect(self) -> None:
        self.copy_state()
        if self.runtime is not None:
            for launch in self.launched:
                self.ran("the room's Claude Code session, launched by the runtime", launch["argv"], launch["environment"], cwd=launch["cwd"])
            report = claude_code_report(
                self.transcript.entries,
                requested_model=self.ctx.route.model,
                mod_attached=bool(self.runtime.participant.attached),
                invocations=self.invocations,
                diagnostics=list(getattr(self.runtime.session, "diagnostics", ())),
                sandbox_settings=self.settings.get("sandbox") or {},
                permission_mode=self.model.permission_mode if self.model is not None else None,
            )
            self.sandbox = report["sandbox"]
            self.not_as_configured = list(report["not_as_configured"])
            self.reports["claude_code"] = report

    def close(self) -> None:
        if self.runtime is not None:
            with contextlib.suppress(Exception):
                self.runtime.close()


def claude_code_report(
    entries: Sequence[Mapping[str, Any]],
    *,
    requested_model: str,
    mod_attached: bool,
    invocations: Sequence[Mapping[str, Any]],
    diagnostics: Sequence[str] = (),
    sandbox_settings: Mapping[str, Any] | None = None,
    permission_mode: str | None = None,
) -> dict[str, Any]:
    """What Claude Code's own stream-json says: whether the mod loaded, which models ran, how each turn ended.

    ``verdict`` says it in one line, first what failed: the mod never
    attached, no turn was bound, or a turn ended in error with Claude Code's
    own words for it (a result's ``errors``). ``not_as_configured`` lists
    where Claude Code showed it did not run as the probe set it up: it did
    not recognize the model (``[claude-code:unrecognized_model]`` on its
    stderr), or a session started in another permission mode than
    ``permission_mode``, the one the pinned version starts in for this model
    (`routes.CLAUDE_CODE_MODELS`). ``sandbox`` says whether Bash ran in
    Claude Code's sandbox: its stream-json does not say, but with
    ``failIfUnavailable`` Claude Code refuses to start a session whose
    sandbox cannot run, so a session that started (its ``init``) had it.
    """

    messages = [entry["message"] for entry in entries if entry.get("direction") == "from-claude" and isinstance(entry.get("message"), Mapping)]
    stderr = [str(entry.get("message")) for entry in entries if entry.get("direction") == "claude-stderr"]
    stderr = list(dict.fromkeys([*stderr, *map(str, diagnostics)]))
    inits = [message for message in messages if message.get("type") == "system" and message.get("subtype") == "init"]
    init = inits[0] if inits else {}
    plugins = init.get("plugins") if isinstance(init.get("plugins"), list) else []
    plugin_names = [plugin.get("name") if isinstance(plugin, Mapping) else str(plugin) for plugin in plugins]
    models: list[str] = []
    # The models the responses name: an assistant message came back from the model (not one Claude Code made up).
    answered: list[str] = []
    for message in messages:
        inner = message.get("message")
        if message.get("type") == "assistant" and isinstance(inner, Mapping) and isinstance(inner.get("model"), str):
            models.append(inner["model"])
            if inner["model"] != "<synthetic>":
                answered.append(inner["model"])
        usage = message.get("modelUsage")
        if message.get("type") == "result" and isinstance(usage, Mapping):
            models.extend(str(name) for name in usage)
    if isinstance(init.get("model"), str):
        models.insert(0, init["model"])
    results = [
        {
            "subtype": message.get("subtype"),
            "is_error": message.get("is_error"),
            "total_cost_usd": message.get("total_cost_usd"),
            "result": str(message.get("result") or "")[:500],
            "errors": [str(error)[:300] for error in message.get("errors") or ()][:5],
        }
        for message in messages
        if message.get("type") == "result"
    ]
    errors = [result for result in results if result["is_error"]]
    named = list(dict.fromkeys(models))
    answered = list(dict.fromkeys(answered))
    turn_bound = any(item.get("bound") for item in invocations)
    accepted = (bool(answered) and not errors) if messages else None
    not_as_configured = [
        f"Claude Code did not recognize the model: {line[:300]}" for line in stderr if "[claude-code:unrecognized_model]" in line
    ][:1]
    modes = list(dict.fromkeys(message.get("permissionMode") for message in inits))
    if permission_mode is not None and any(mode != permission_mode for mode in modes):
        not_as_configured.append(
            f"Claude Code started in permission mode {', '.join(map(repr, modes))}, not {permission_mode!r} as the pinned "
            "version does for this model"
        )
    failed = next((result for result in results if result["is_error"] or result["subtype"] != "success"), None)
    why = ""
    if failed is not None:
        why = f"; Claude Code ended a turn as {failed['subtype']}: " + ("; ".join(failed["errors"]) or failed["result"] or "no detail")
    elif not messages and stderr:
        why = f"; its stderr ends: {stderr[-1][:300]}"
    if not invocations:
        verdict = "no wake reached Claude Code"
    elif not mod_attached:
        verdict = "the mod never attached" + (f" (plugin errors: {init.get('plugin_errors')})" if init.get("plugin_errors") else "") + why
    elif not turn_bound:
        verdict = "the mod attached, but no turn was bound to its wake" + why
    elif failed is not None:
        verdict = "the mod attached and bound the turn" + why
    elif accepted:
        verdict = f"the mod attached and bound the turn, and the model answered as {', '.join(answered)}"
    else:
        verdict = "the mod attached and bound the turn, but no answer from the model is in the transcript"
    if not_as_configured:
        verdict += "; " + "; ".join(not_as_configured)
    settings = dict(sandbox_settings or {})
    if not settings.get("enabled"):
        sandbox = {"on": False, "detail": "off in the user settings"}
    elif not settings.get("failIfUnavailable"):
        sandbox = {"on": None, "detail": "enabled without failIfUnavailable, so Claude Code may have run Bash unsandboxed"}
    elif init:
        sandbox = {"on": True, "detail": "enabled with failIfUnavailable, and the session started"}
    else:
        sandbox = {"on": None, "detail": "enabled with failIfUnavailable, but no session started"}
    sandbox["settings"] = settings
    return {
        "verdict": verdict,
        "not_as_configured": not_as_configured,
        "sandbox": sandbox,
        "mod_loaded": {
            "attached_to_the_gate": mod_attached,
            "init_plugins": plugin_names,
            "init_plugin_errors": init.get("plugin_errors"),
        },
        "turn_bound": turn_bound,
        "model": {
            "requested": requested_model,
            "init_model": init.get("model"),
            "named_in_transcript": named,
            "answered_as": answered,
            "accepted": accepted,
        },
        "permission_mode": init.get("permissionMode"),
        "api_key_source": init.get("apiKeySource"),
        "results": results,
        "stderr_tail": stderr[-10:],
    }


class CodexLeg(SharedTransportLeg):
    harness = "codex"

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self.runner: Any = None
        self.agent: ScriptedCodexAgent | None = None
        self.transcript = JsonLines(ctx.out / "transcript" / "codex-app-server.jsonl")
        self.launched: list[dict[str, Any]] = []
        self._patch: Any = None

    def executable(self) -> str:
        found = (
            self.ctx.options.codex_bin
            or shutil.which("codex", path=self.ctx.env.get("PATH"))
        )
        if not found or not os.access(found, os.X_OK):
            raise CouldNotRun("Codex is not installed: pass --codex-bin or set NUNCHI_CODEX_BIN")
        return str(Path(found).absolute())

    def prepare(self) -> None:
        from nunchi.integrations.codex_app_server import integration as codex_integration
        from nunchi.integrations.codex_app_server.integration import TOOL_NAMES
        from nunchi.integrations.codex_app_server.runner import CodexRoomRunner

        executable = self.executable()
        base_url = OPENROUTER
        if self.ctx.options.scripted:
            self.agent = ScriptedCodexAgent(SCRIPTED_ANSWER)
            base_url = self.agent.base_url
        codex_home = Path(self.ctx.homes["CODEX_HOME"])
        toml = codex_home / "config.toml"
        toml.write_text(codex_config(self.ctx.route.model, base_url=base_url, scripted=self.ctx.options.scripted), encoding="utf-8")
        self.configs.append(("codex user config", toml))
        work = self.ctx.base / "work"
        work.mkdir(parents=True, exist_ok=True)
        # A git checkout, as the kit runs it: the case in which Codex would write trust (contract, gap 5).
        git_init = ["git", "init", "-q", str(work)]
        self.ran("git init, the agent's working directory", git_init, self.ctx.env)
        subprocess.run(git_init, check=True, env=self.ctx.env, capture_output=True)
        config, _ = self.room_config(
            {
                "transport": self.transport_section(),
                "codex": {
                    "working_directory": str(work),
                    "project_trust_level": "trusted",
                    "executable": executable,
                    "withheld_env": ["DISCORD_BOT_TOKEN"],
                    "resume_thread": False,
                    "start_timeout_seconds": 120,
                },
            }
        )
        (self.ctx.out / "transcript").mkdir(parents=True, exist_ok=True)
        # Every app-server the integration starts is recorded, for the whole leg.
        self._patch = mock.patch.object(codex_integration, "AppServer", recording_app_server(self.transcript, self.launched))
        self._patch.start()
        runner = CodexRoomRunner(config, self.client, environ=dict(os.environ))
        self.runner = runner
        environment = runner.integration.environment
        self.install = {
            "version": self.version([executable, "--version"], environment),
            "expected": self.ctx.options.expect_version or PINS["codex"],
            "executable": executable,
            "npm": self.npm(executable),
        }
        self.connection = runner.connection
        self.participant = runner.integration.participant
        self._room = runner.room
        self.actual_homes = _homes(environment, "CODEX_HOME")
        self.tool_names = [TOOL_NAMES[role] for role in self.participant.registered_roles]
        self.tool_names.append(f"mcp__{codex_integration.MCP_SERVER_NAME}")
        self.instrument(self.participant, runner.room)
        runner.connection.register()

    def collect(self) -> None:
        self.copy_state()
        copy_tree(Path(self.ctx.homes["CODEX_HOME"]) / "sessions", self.ctx.out / "transcript" / "codex-sessions")
        if self.runner is None:
            return
        from nunchi.integrations.codex_app_server.integration import MCP_SERVER_NAME, UNCONTAINED_SANDBOXES

        integration = self.runner.integration
        for launch in self.launched:
            self.ran("codex app-server, started by the integration", launch["argv"], launch["environment"], cwd=launch["cwd"])
        if self.launched:
            # Codex starts the room's MCP server from the thread's config: the
            # integration's variables, on top of the defaults Codex gives every MCP server.
            server = integration.thread_config(None)["mcp_servers"][MCP_SERVER_NAME]
            self.ran(
                "the room's MCP server, started by Codex (its variables beyond the ones Codex gives every MCP server)",
                [server["command"], *server["args"]],
                server["env"],
                cwd=server["cwd"],
            )
        items = [
            {"tool": item.get("tool"), "server": item.get("server"), "status": item.get("status")}
            for item in integration.tool_items.values()
            if item.get("type") == "mcpToolCall"
        ]
        room_calls = [item for item in items if item["server"] == MCP_SERVER_NAME]
        turns = [
            {"status": turn.get("status"), "error": (turn.get("error") or {}).get("message") if isinstance(turn.get("error"), Mapping) else None}
            for turn in integration.completed_turns.values()
        ]
        offered = None
        if self.agent is not None:
            from nunchi.integrations.codex_app_server_conformance import ScriptedModel

            requests = self.agent.requests()
            # Whether the room tools reached the model as Codex's namespace tool. Unknown if no request
            # did, or in Codex's code mode (its GPT-6 models): there the tools come in an
            # ``additional_tools`` input item, and the room's are nested in ``exec``, unlisted.
            code_mode = any(
                isinstance(item, Mapping) and item.get("type") == "additional_tools"
                for request in requests
                for item in request.get("input", ())
            )
            offered = any(ScriptedModel.is_agent(request) for request in requests) if requests and not code_mode else None
            write_json(self.ctx.out / "transcript" / "scripted-model-requests.json", requests)
        verdict = codex_verdict(room_calls=len(room_calls), turns=turns, wakes=len(self.invocations), tools_offered=offered)
        self.sandbox = codex_sandbox(self.runner.status(), list(integration.warnings), uncontained=UNCONTAINED_SANDBOXES)
        report = {
            "verdict": verdict,
            "room_tool_called": bool(room_calls),
            "tool_calls": items,
            "turns": turns,
            "sandbox": self.sandbox,
            "warnings": list(integration.warnings)[-10:],
            "declined": list(integration.declined)[-10:],
        }
        if self.agent is not None:
            report["scripted_model"] = {
                "agent_requests": len(self.agent.model.requests),
                "other_requests": len(self.agent.model.other_requests),
                "room_tools_offered_as_namespace": offered,
            }
        self.reports["codex"] = report

    def close(self) -> None:
        if self.runner is not None:
            with contextlib.suppress(Exception):
                self.runner.close()
        if self._patch is not None:
            with contextlib.suppress(Exception):
                self._patch.stop()
            self._patch = None
        if self.agent is not None:
            self.agent.close()


def codex_verdict(*, room_calls: int, turns: Sequence[Mapping[str, Any]], wakes: int, tools_offered: bool | None = None) -> str:
    """What Codex's turns show about its route, in one line.

    R3 (OpenRouter and Codex's ``namespace`` tools, docs/rehearsal.md) is
    named only on evidence: a turn error that names the namespace, or, where
    the model's requests are seen (``tools_offered``, scripted), the room
    tools missing from them. Any other turn error is given in Codex's own
    words. A live turn that ends without a room tool is reported as that: the
    probe cannot see which tools the model got, and the OpenAI-model arm is
    the comparison that tells a refusal of the room tools apart.
    """

    errors = [str(turn["error"]) for turn in turns if turn.get("error")]
    unfinished = [str(turn.get("status")) for turn in turns if turn.get("status") != "completed"]
    # A provider refusing the tool type ('namespace' quoted, or named with tools),
    # not a Linux-namespace error from the sandbox.
    namespace = next(
        (
            error
            for error in errors
            if re.search(r"['\"]namespace['\"]|namespace[^.]*tool|tool[^.]*namespace", error, re.I)
            and "sandbox" not in error.lower()
        ),
        None,
    )
    if room_calls:
        return "the room tools reached the model through this route: a room tool was called"
    if namespace is not None:
        return f"blocked on a model route (R3): the provider refused Codex's namespace tools: {namespace[:300]}"
    if errors:
        return f"Codex's turn failed: {errors[0][:300]}"
    if unfinished or len(turns) < wakes:
        return (
            f"no room tool was called, and a turn did not complete ({', '.join(unfinished) or 'no end reported'}): "
            "it was cancelled or outlived the host's deadline"
        )
    if tools_offered is False:
        return "no room tool was called: the room tools were missing from what the model got (R3)"
    if wakes:
        return "no room tool was called: the turn ended without one"
    return "no turn started"


def codex_sandbox(status: Mapping[str, Any], warnings: Sequence[str], *, uncontained: Sequence[str]) -> dict[str, Any]:
    """Whether Codex ran the agent's commands in its sandbox, from what Codex reported.

    Codex reports the thread's sandbox policy; on Linux a containing policy
    runs commands in bubblewrap, and Codex warns at start when bubblewrap
    cannot create user namespaces (codex-rs/linux-sandbox/README.md at
    0.160.1), or when it is not on PATH and the bundled copy is used.
    """

    policy = status.get("codex_sandbox")
    notes = [warning for warning in warnings if "bubblewrap" in warning or "namespace" in warning]
    if not isinstance(policy, Mapping):
        sandbox: dict[str, Any] = {"on": None, "detail": "Codex never started the thread, so it reported no sandbox"}
    elif policy.get("type") in uncontained or policy.get("type") == "unknown":
        sandbox = {"on": False, "detail": f"Codex's sandbox policy is {policy.get('type')}"}
    elif any("namespace" in warning for warning in notes):
        sandbox = {"on": False, "detail": f"{policy.get('type')}, but bubblewrap cannot create user namespaces here"}
    else:
        bundled = any("bundled bubblewrap" in warning for warning in notes)
        sandbox = {
            "on": True,
            "detail": f"{policy.get('type')}, network {'on' if policy.get('networkAccess') else 'off'}"
            + (", in Codex's bundled bubblewrap (none on PATH)" if bundled else ""),
        }
    sandbox.update({"policy": policy, "warning": status.get("codex_sandbox_warning"), "bubblewrap_warnings": notes})
    return sandbox


# -- Hermes: the plugin inside a real gateway -------------------------------------------------------


# Hermes drops other bots' messages by default (`discord.allow_bots: none`), before any plugin
# hook. A room with peer agents needs them heard, so the probe takes the Hermes README's
# peer-agent settings, and the bot's status report reaches attention as in the other harnesses.
# Their cost is the README's: they apply to the whole profile, and Hermes's bot loop guard
# still drops bot messages once bots post 20 in 5 minutes in one chat.
HERMES_PEER_AGENTS = {"allow_bots": "all", "bots_require_inline_mention": False}
# Hermes's own record of its sessions: what the model saw and answered, and its model calls.
HERMES_STATE_TABLES = ("sessions", "messages", "session_model_usage", "system_prompts")


class HermesLeg(Leg):
    harness = "hermes"
    actor_id = f"discord:user:{BOT_ID}"
    scope = f"discord:{ROOM_ID}"
    harness_posts = True

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self.gateway: Any = None
        self.plugin: Any = None
        self.agent: ScriptedHermesAgent | None = None
        self._patch: Any = None
        self.delivered_people: set[str] = set()

    @property
    def room(self) -> Any:
        return self.plugin.room if self.plugin is not None else None

    def prepare(self) -> None:
        from nunchi.integrations import hermes_plugin_conformance as kit

        if not kit.discord_available():
            raise CouldNotRun("Hermes with discord.py is not installed in this Python (hermes-agent[messaging])")
        # Before Hermes is imported: its home is a throwaway one under this run's TMPDIR.
        kit.isolate()
        try:
            aux_tasks = hermes_auxiliary_tasks()
        except ImportError as exc:
            raise CouldNotRun(f"Hermes's config cannot be read for its auxiliary tasks: {exc}") from exc
        import nunchi.integrations.hermes_plugin as package
        from nunchi.integrations.hermes_plugin import plugin as plugin_module
        from nunchi.integrations.hermes_plugin.plugin import TOOL_NAMES

        if self.ctx.options.scripted:
            self.agent = ScriptedHermesAgent(SCRIPTED_ANSWER)
            model: Any = self.agent.model
            model_config = hermes_model_config(self.ctx.route.model, aux_tasks, scripted_base_url=self.agent.base_url)
        else:
            # The kit's gateway reads only ``base_url`` of its model; the route replaces the whole block.
            model = SimpleNamespace(base_url=OPENROUTER)
            model_config = hermes_model_config(self.ctx.route.model, aux_tasks)
        _, config_path = self.room_config({"hermes": hermes_section(kit.DISCORD_ROOM)})
        build_plugin = plugin_module.build_plugin

        def recorded_build(config):
            plugin = build_plugin(config)
            factory = plugin.room_factory

            def room_factory(owner):
                room = factory(owner)
                self.instrument(owner.participant, room)
                return room

            plugin.room_factory = room_factory
            self.plugin = plugin
            return plugin

        # Observe the plugin Hermes builds from the config; build it unchanged.
        self._patch = mock.patch.object(plugin_module, "build_plugin", recorded_build)
        self._patch.start()
        # The agent's terminal starts in a fresh directory, as the other legs'
        # harnesses do. Left unset, in-process Hermes would start it in this
        # process's directory (the Nunchi checkout) and read its AGENTS.md as
        # project context; a real `hermes gateway` falls back to HOME.
        work = self.ctx.base / "work"
        work.mkdir(parents=True, exist_ok=True)
        self.gateway = kit.HermesGateway(
            model=model,
            plugin_source=Path(package.__file__).parent,
            plugin_settings={"config_path": str(config_path)},
            platform="discord",
            platform_actions=True,
            extra_config={**model_config, "discord": dict(HERMES_PEER_AGENTS), "terminal": {"cwd": str(work)}},
        )
        if self.plugin is None:
            raise CouldNotRun("Hermes did not load the plugin from its config")
        home = Path(self.gateway.home)
        self.configs.append(("hermes config.yaml", home / "config.yaml"))
        self.configs.append(("hermes profile .env", home / ".env"))
        # Hermes runs in this process: its environment is this process's (`collect` records it).
        self.actual_homes = _homes(os.environ, "HERMES_HOME")
        self.tool_names = list(TOOL_NAMES.values())
        self.known_gaps = [replace(gap, scenarios=(PROBE_SCENARIO,)) for gap in kit.HERMES_KNOWN_GAPS]
        self.install = hermes_install(self.ctx.options.expect_version or PINS["hermes"])
        if self.install.get("executable"):
            self.ran(
                "git rev-parse HEAD in Hermes's source tree (the install record, and the plugin's version check)",
                ["git", "-C", self.install["executable"], "rev-parse", "HEAD"],
                os.environ,
            )
        self.install["plugin_version"] = _plugin_version(Path(package.__file__).parent / "plugin.yaml")
        self.reports["hermes_setup"] = {
            "auxiliary_tasks_pinned": aux_tasks,
            "plugin_directory": str(Path(package.__file__).parent),
            "gateway": "GatewayRunner in this process, on the conformance kit's Discord world (DiscordWorld)",
        }
        self.commands.append(
            {
                "what": "Hermes's GatewayRunner, in the probe's process (nunchi.integrations.hermes_plugin_conformance.HermesGateway)",
                "argv": list(self.ctx.options.command),
                "python": sys.executable,
                "hermes_home": str(home),
                # Not a process of its own: its variables are this process's (environment.processes).
                "in_process": True,
            }
        )

    def _discord_user(self, name: str, scene: Scene) -> str:
        from nunchi.integrations import hermes_plugin_conformance as kit

        user_id = self.person_id(name)
        if user_id == BOT_ID or user_id in self.delivered_people:
            return user_id
        actor = scene.actors.get(name, {})
        display = actor.get("display_name", name)
        world = self.gateway.world
        if actor.get("kind") == "bot":
            world.peer_bot(user_id, display)
        else:
            # A person in the room has the room's role (README: DISCORD_ALLOWED_ROLES).
            world.person(user_id, display)
            world.give_role(user_id, kit.DISCORD_ROOM_ROLE)
        self.delivered_people.add(user_id)
        return user_id

    def deliver(self, raw: Mapping[str, Any], at: datetime, scene: Scene, sequence: int) -> dict[str, Any]:
        if raw.get("type", "message") != "message":
            raise CouldNotRun(f"the probe plays messages only, not {raw.get('type')}")
        user_id = self._discord_user(raw["author"], scene)
        mentions = tuple(self._discord_user(name, scene) for name in raw.get("mentions", ()))
        message_id = snowflake(at, sequence)
        reached = self.gateway.run(
            self.gateway.person_says(raw["text"], user_id=user_id, message_id=message_id, mentions=mentions),
            timeout=60,
        )
        event_id = f"discord:message:{message_id}"
        observed = False
        deadline = time.monotonic() + (10 if reached else 2)
        while time.monotonic() < deadline:
            room = self.room
            if room is not None and room.observation.resolve_event(event_id) is not None:
                observed = True
                break
            time.sleep(0.05)
        entry = {
            "scene_event": raw["id"],
            "event_id": event_id,
            "author": f"discord:user:{user_id}",
            "reached_nunchi": bool(reached),
            "observed": observed,
        }
        if not reached:
            entry["note"] = "Hermes's Discord adapter dropped it before any plugin hook"
        return entry

    def settle(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        steady = 0
        while time.monotonic() < deadline:
            room = self.room
            idle = (room is None or room.drain(0.5)) and self.gateway.idle() and self.plugin.participant.active is None
            steady = steady + 1 if idle else 0
            if steady >= 3:
                return True
            time.sleep(0.5)
        return False

    def room_effects(self) -> list[dict[str, Any]]:
        if self.gateway is None:
            return []
        world = self.gateway.world
        effects = [{"kind": "message", "where": chat, "text": text} for chat, text in world.sent]
        effects += [{"kind": "reaction", "where": chat, "reaction": emoji} for chat, _, emoji in world.reactions]
        effects += [{"kind": "reaction", "where": chat, "reaction": emoji, "removed": True} for chat, _, emoji in world.reactions_removed]
        return effects

    def collect(self) -> None:
        self.copy_state()
        if self.gateway is None:
            return
        self.record_environments()
        home = Path(self.gateway.home)
        copied = copy_tree(home / "sessions", self.ctx.out / "transcript" / "hermes-sessions")
        copied += copy_tree(home / "logs", self.ctx.out / "transcript" / "hermes-logs")
        # Hermes keeps its sessions in state.db, which the kit deletes with the home on close.
        try:
            state = sqlite_tables(home / "state.db", HERMES_STATE_TABLES)
        except Exception as exc:
            state = {"error": [{"error": f"{type(exc).__name__}: {exc}"}]}
        write_json(self.ctx.out / "transcript" / "hermes-state.json", state)
        usage = [row for row in state.get("session_model_usage", ()) if isinstance(row, Mapping)]
        calls = sum(int(row.get("api_call_count") or 0) for row in usage)
        if self.plugin is None:
            verdict = "Hermes did not load the plugin"
        elif self.room is None:
            verdict = "the plugin loaded, but no room was built"
        elif not calls:
            verdict = "the plugin loaded and built the room; Hermes's session records no model call"
        else:
            models = ", ".join(sorted({str(row.get("model")) for row in usage}))
            verdict = f"the plugin loaded and built the room; Hermes's session records {calls} model call(s), to {models}"
        adapter = self.gateway.adapter
        report: dict[str, Any] = {
            "verdict": verdict,
            "sandbox": self.sandbox,
            "plugin_loaded": self.plugin is not None,
            "room_built": self.room is not None,
            "model_calls_in_session": calls,
            "transcript_files": [*copied, "hermes-state.json"],
            "typing": list(getattr(adapter, "typing", ())),
            "threads_opened": list(getattr(adapter, "threads", ())),
        }
        if self.agent is not None:
            requests = self.agent.requests()
            report["scripted_model"] = {"agent_requests": len(requests)}
            write_json(self.ctx.out / "transcript" / "scripted-model-requests.json", requests)
        self.reports["hermes"] = report

    def record_environments(self) -> None:
        """Hermes's environment, and what Hermes's own builders give the agent's commands.

        Hermes runs in this process. Its terminal and code tools build their
        children's environment with ``tools.environments.local._make_run_env``,
        and its background and other children with ``_sanitize_subprocess_env``;
        both strip Hermes's provider keys, ``OPENROUTER_API_KEY`` among them.
        The pins-and-isolation check fails if either would pass a key on.
        """

        self.runs_in("Hermes's GatewayRunner and the plugin, in the probe's process", os.environ)
        try:
            from tools.environments import local as hermes_local  # type: ignore[import-not-found]

            terminal = hermes_local._make_run_env({})
            children = hermes_local._sanitize_subprocess_env(dict(os.environ))
        except Exception as exc:  # the pinned Hermes has both; another may not
            self.processes.append(
                {"process": "the agent's terminal", "agent_shell": True, "error": f"{type(exc).__name__}: {exc}"[:300]}
            )
        else:
            self.runs_in("the agent's terminal and code tools (Hermes's _make_run_env)", terminal, agent_shell=True)
            self.runs_in("Hermes's background and other children (Hermes's _sanitize_subprocess_env)", children, agent_shell=True)
        try:
            from hermes_cli.config import load_config  # type: ignore[import-not-found]

            backend = (load_config().get("terminal") or {}).get("backend") or "local"
        except Exception as exc:
            self.sandbox = {"on": None, "detail": f"Hermes's terminal backend could not be read: {type(exc).__name__}"}
        else:
            self.sandbox = {
                "on": backend != "local",
                "detail": f"Hermes's terminal backend is {backend}"
                + (": the agent's commands run as this user, unsandboxed" if backend == "local" else ""),
                "terminal_backend": backend,
            }

    def close(self) -> None:
        if self.gateway is not None:
            with contextlib.suppress(Exception):
                self.gateway.close()
        if self._patch is not None:
            with contextlib.suppress(Exception):
                self._patch.stop()
            self._patch = None
        if self.agent is not None:
            self.agent.close()


def hermes_install(expected: str) -> dict[str, Any]:
    """Which Hermes ran: its version, and the commit of its source tree."""

    entry: dict[str, Any] = {"expected": expected}
    try:
        from nunchi.integrations.hermes_version import hermes_version

        version = hermes_version()
    except Exception as exc:  # the version check refuses an unverifiable install
        version = None
        entry["version_error"] = str(exc)[:300]
    commit = None
    try:
        import hermes_cli

        source = Path(hermes_cli.__file__).resolve().parent.parent
        entry["executable"] = str(source)
        done = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False)
        commit = done.stdout.strip() or None
    except (ImportError, OSError, subprocess.SubprocessError):
        pass
    entry["hermes_version"] = version
    entry["commit"] = commit
    entry["version"] = f"{version} ({commit})" if commit else version
    return entry


def _plugin_version(manifest: Path) -> str | None:
    """The ``version:`` of the plugin's own ``plugin.yaml``."""

    try:
        text = manifest.read_text(encoding="utf-8")
    except OSError:
        return None
    found = re.search(r"^version:\s*(\S+)\s*$", text, re.MULTILINE)
    return found.group(1) if found else None


LEGS: dict[str, type[Leg]] = {"claude-code": ClaudeCodeLeg, "codex": CodexLeg, "hermes": HermesLeg}


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
    when every delivery is known.
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
    return {
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
    """The key for attention, the key for the harness, and the canary; placeholders when scripted."""

    canary = os.environ.get(CANARY_ENV) or f"canary-{secrets.token_urlsafe(24)}"
    if options.scripted:
        placeholder = f"scripted-placeholder-{secrets.token_urlsafe(24)}"
        return placeholder, placeholder, canary
    attention_key = os.environ.get(ATTENTION_KEY_ENV)
    if not attention_key:
        raise CouldNotRun(f"{ATTENTION_KEY_ENV} is not set: the live probe needs the OpenRouter key")
    harness_key = os.environ.get(HARNESS_KEY_ENV[options.harness]) or attention_key
    return attention_key, harness_key, canary


def _reset(directory: Path) -> None:
    if directory.exists():
        delete_outputs(directory)
    directory.mkdir(parents=True, exist_ok=True)


def run_probe(options: Options) -> int:
    """Run the probe for one harness; returns the exit status. Restores this process's environment."""

    if options.harness not in HARNESSES:
        raise ValueError(f"unknown harness {options.harness!r}")
    out = options.out / options.harness
    _reset(out)
    original_env = dict(os.environ)
    # The pinned executables, as the job names them, before this process becomes the clean user.
    options.claude_bin = options.claude_bin or original_env.get("NUNCHI_CLAUDE_BIN")
    options.codex_bin = options.codex_bin or original_env.get("NUNCHI_CODEX_BIN")
    original_tempdir = tempfile.tempdir
    user_home = Path(os.path.expanduser("~"))
    user_homes = [user_home / ".codex", user_home / ".hermes"]
    before = [home_snapshot(path) for path in user_homes]
    base = Path(tempfile.mkdtemp(prefix="nunchi-rehearsal-"))
    started = _now()
    errors: list[str] = []
    moments: list[dict[str, Any]] = []
    secret_values: dict[str, str] = {}
    harness_env: dict[str, str] = {}
    # Nunchi's own keys, in this process only: none beside Hermes (`routes.attention_key_env`).
    nunchi_env: dict[str, str] = {}
    homes: dict[str, str] = {}
    could_not_run = False
    leg: Leg | None = None
    spend: SpendWatch | None = None
    scripted_attention: ScriptedAttention | None = None
    route = route_for(options.harness, options.agent_model)
    try:
        attention_key, harness_key, canary = _secret_values(options)
        key_env = attention_key_env(options.harness)
        if key_env in route.secret_env:
            # Beside Hermes, attention reads Hermes's own key variable: one value for both.
            attention_key = harness_key
        secret_values = {key_env: attention_key, CANARY_ENV: canary}
        homes = Homes(base).create()
        harness_env = clean_environment(homes, route, inherited=original_env)
        harness_env[CANARY_ENV] = canary
        for name in route.secret_env:
            harness_env[name] = harness_key
            secret_values[name] = harness_key
        if key_env not in harness_env:
            nunchi_env[key_env] = attention_key
        if issubclass(LEGS[options.harness], SharedTransportLeg):
            nunchi_env[OUTPUT_KEY_ENV] = secrets.token_urlsafe(48)
        secret_values.update(nunchi_env)
        if options.scripted:
            scripted_attention = ScriptedAttention(spec.wake_phrase for spec in MOMENTS if spec.wake_phrase)
            attention = attention_config(
                options.attention_model, base_url=scripted_attention.base_url, provider="scripted", api_key_env=key_env
            )
        else:
            attention = attention_config(options.attention_model, api_key_env=key_env)
        # From here this process is the clean user, plus Nunchi's own keys for
        # Claude Code and Codex, whose integrations strip every NUNCHI_* name
        # from the harness. Beside Hermes, which runs in this process, there are none.
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
        )
        spend = SpendWatch(None if options.scripted else attention_key, options.budget_usd)
        leg = LEGS[options.harness](ctx)
        leg.prepare()
        settle = 120.0 if options.scripted else options.turn_timeout_seconds + 60
        spend.read("before the first moment")
        for index, spec in enumerate(MOMENTS):
            if index and not spend.may_continue(spec.name):
                break
            moments.append(play_moment(leg, spec, settle_seconds=settle))
        spend.read("after the last moment")
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
            leg.close()
        if scripted_attention is not None:
            scripted_attention.close()
        os.environ.clear()
        os.environ.update(original_env)
        tempfile.tempdir = original_tempdir
    after = [home_snapshot(path) for path in user_homes]
    if leg is not None:
        try:
            judge_moments(leg, moments)
        except Exception as exc:
            errors.append(f"judging the moments failed: {type(exc).__name__}: {exc}")
    # A key echoed in an exception is replaced by its name, so it does not cost the whole record.
    errors = [redact(error, secret_values) for error in errors]
    document = _record(
        options=options,
        leg=leg,
        route=route,
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
        checks = _checks(leg, document, base=base, before=before, after=after, scripted=options.scripted)
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
            "room_id": ROOM_ID,
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
        "spend": spend.document() if spend is not None else {"budget_usd": options.budget_usd},
        "moments": moments,
        "reports": leg.reports if leg is not None else {},
        "lane_errors": list(leg.room.errors) if leg is not None and leg.room is not None else [],
        "errors": errors,
    }


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
) -> list[Check]:
    """The hard checks; the scan runs over the written outputs (`_finish`)."""

    install = leg.install or {}
    host_receipts = [record for record in leg.receipts() if record.get("stage") == "participant-host"] if leg.room is not None else []
    ids = [*(turn["request_id"] for turn in leg.invocations), *leg.tool_names]
    environment = document["environment"]
    checks = [
        checks_module.pins_and_isolation(
            harness_version=install.get("version"),
            expected=str(install.get("expected") or PINS[leg.harness]),
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
        checks_module.turns_bound_and_ended(leg.invocations, host_receipts, leg.committed),
        checks_module.turns_on_others_messages(
            leg.invocations,
            [delivery.get("event_id") for moment in document["moments"] for delivery in moment.get("deliveries", ())],
        ),
        checks_module.attention_judged(leg.attention_calls, leg.invocations),
        checks_module.one_room_action_per_turn(leg.committed, [item.get("delivered", False) for item in leg.committed]),
        checks_module.no_leaks(leg.committed, leg.room_effects(), ids, known_gaps=leg.known_gaps),
    ]
    if scripted:
        codex = leg.reports.get("codex") or {}
        checks.append(
            checks_module.scripted_outcomes(document["moments"], SCRIPTED_ANSWER, room_tool_called=codex.get("room_tool_called"))
        )
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
    parser.add_argument("--harness", required=True, choices=HARNESSES)
    parser.add_argument("--out", required=True, help="output directory; the run writes <out>/<harness>/")
    parser.add_argument("--budget-usd", type=float, default=2.0, help="stop before the next moment once the key has spent this (soft)")
    parser.add_argument("--agent-model", default=DEFAULT_AGENT_MODEL)
    parser.add_argument("--attention-model", default=DEFAULT_ATTENTION_MODEL, help="an OpenRouter id, optionally @effort")
    parser.add_argument("--scripted", action="store_true", help="offline: scripted model endpoints, no key, no network")
    parser.add_argument("--wheel", help="the Nunchi wheel installed for this run, to record its sha256")
    parser.add_argument("--claude-bin", help="the pinned claude executable (else NUNCHI_CLAUDE_BIN, else claude on PATH)")
    parser.add_argument("--codex-bin", help="the pinned codex executable (else NUNCHI_CODEX_BIN, else codex on PATH)")
    parser.add_argument("--expect-version", help="the pinned harness version to check (default: the CI pin)")
    parser.add_argument("--turn-timeout", type=float, default=300.0, help="seconds one harness turn may take")
    parser.add_argument("--keep-work", action="store_true", help="keep the throwaway homes after the run")
    parser.add_argument("--arm", default="", help="a label for this run as one arm of a comparison, recorded and shown in the summary")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    args = _parser().parse_args(arguments)
    if args.harness == "claude-code" and args.scripted:
        print(NOT_YET, file=sys.stderr)
        return EXIT_NOT_YET
    if args.budget_usd <= 0:
        print("--budget-usd must be positive", file=sys.stderr)
        return EXIT_USAGE
    try:
        attention_config(args.attention_model)
        if args.harness == "claude-code":
            claude_code_model(args.agent_model)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    options = Options(
        harness=args.harness,
        out=Path(args.out).absolute(),
        budget_usd=args.budget_usd,
        agent_model=args.agent_model,
        attention_model=args.attention_model,
        scripted=args.scripted,
        wheel=Path(args.wheel).absolute() if args.wheel else None,
        claude_bin=args.claude_bin,
        codex_bin=args.codex_bin,
        expect_version=args.expect_version,
        keep_work=args.keep_work,
        turn_timeout_seconds=args.turn_timeout,
        command=["python", "-m", "evals.rehearsal.probe", *arguments],
        arm=args.arm,
    )
    return run_probe(options)


if __name__ == "__main__":
    raise SystemExit(main())
