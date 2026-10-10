"""The Discord room: Nunchi's own Discord processes, unmodified, on the Discord stand-in (step 9f, PR 3b).

    sudo -E "$PY" -m evals.rehearsal.discord_net --offline -- \\
        "$PY" -m evals.rehearsal.probe --harness {claude-code,codex,reference,hermes} --scripted --room discord --out DIR

The launcher (`discord_net.py`) leads Discord's names to this machine and
names its record in ``NUNCHI_DISCORD_NET``; without it ``--room discord`` does
not run. Here the stand-in (`fake_discord`) answers at 127.0.0.1:443 with the
launcher's certificate, and each column runs at Discord's real names:

- **Claude Code and Codex**: a `nunchi-mcp-discord` process of their own, with
  its own bot, port, routes, 32-byte output key and state directory. The
  runner (`ClaudeCodeRoomRuntime`, `CodexRoomRunner`) runs in the probe's
  process, built with the same calls as its CLI's ``main``
  (`load_pinned_config`, `transport_client`), and serves the room over real
  MCP (`DiscordRoomConnection.serve`); the probe watches it as it watches the
  in-process room.
- **The reference**: `nunchi-discord` (discord.py) in its own process, with a
  scripted plain-call participant (`standin.ScriptedParticipant`). Its
  evidence comes from outside it: its receipts and delivery audits, what the
  scripted endpoints were asked and answered, and the wire.
- **Hermes** (PR 3c): `hermes gateway run`, unmodified, with the Nunchi plugin,
  in its own process with a fresh ``HERMES_HOME`` written as the plugin's
  README says, and a scripted model (`standin.ScriptedHermesAgent`). The
  plugin and the library run inside Hermes, so its evidence comes from outside
  too (`HermesGatewayLeg`), and Hermes posts the agent's final answer itself:
  a plain message, in the main channel also for a thread question. The lane
  pins what Hermes and its plugin do not do (README, Known gaps), so that a
  change either way fails it until the pins and docs follow: those two, no
  gap declared at the start, a person's reply to the agent's answer has no
  target in the room log, and the agent's own reaction is not remembered.

Each Discord process starts as its console script does (``main`` from the
same module), and only after the preflight (`preflight.py`) reached this
run's stand-in in exactly the environment the process gets. Attention is
`standin.ScriptedAttention`. The world, the wire log and the stand-in's
verdict are written to the run's output directory, where the key and canary
scan covers them; the bots' per-run tokens are among the values it looks for.

The moments, in one channel named after the column:

1. ``first-message``: a person greets the room. Reported, not graded, and pinned
   ``reached``: a fresh transport declares a continuity gap when it starts
   (``discord-continuity`` requires that the participant sees it), and the
   message arrives behind it. The reference is pinned ``reached`` too.
2. ``bot-status-report``: a scripted bot posts; no turn.
3. ``direct-question``: one post.
4. ``reply``: the person replies to the agent's post; the agent replies to it.
5. ``reaction``: op 7 goes to every bot first, and the message is posted at
   once, so it crosses the reconnect; the person asks for a thumbs up and the
   agent reacts. The transport must resume with no gap; the reference marks
   a stream gap on any disconnect, which is recorded, not failed.
6. ``thread``: the person opens a thread under the room and posts in it.
   Reported, not graded, and pinned ``reached``: a thread under the room is
   part of the room.
7. ``thread-question``: the person asks the agent a question in that thread.
   The agent replies to it, and the reply must land in the thread (not in the
   channel): the wire shows where it was posted.

Each graded message must reach the agent as it was sent
(``discord-addressing``): the pings it carried (a reply pings the author of the
message it answers), for the reply the agent's own last post as the message it
answers, and for the thread question the thread it was said in.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import contextlib
from dataclasses import replace
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Any

from evals.behavior.scene import SCENES as BEHAVIOR_SCENES, Scene, load_scene

from . import checks as checks_module
from .checks import PROBE_SCENARIO, REACHED, Check
from .discord_net import ENV as NET_ENV
from .fake_discord.control import FakeDiscord
from .probe import (
    HERMES_PEER_AGENTS,
    HERMES_STATE_TABLES,
    PARTICIPANT,
    REFERENCE,
    ROOT,
    SCENES,
    SCRIPTED_ANSWER,
    ClaudeCodeLeg,
    CodexLeg,
    Context,
    CouldNotRun,
    Leg,
    MomentSpec,
    _env_names,
    _plugin_version,
    _summarize_action,
    play_moment,
)
from .record import copy_tree, sqlite_tables, write_json
from .routes import (
    ATTENTION_KEY_ENV,
    CANARY_ENV,
    OUTPUT_KEY_ENV,
    PASSTHROUGH_ENV,
    PINS,
    Route,
    hermes_model_config,
    hermes_section,
)
from .standin import RoomScript, ScriptedHermesAgent, ScriptedParticipant, received_triggers

# What the scripted agent does at each graded moment, and the phrases scripted attention wakes for.
REPLY_PHRASE = "back off exponentially"
SCRIPTED_REPLY = "Exponentially, with jitter, and a cap of about a minute between tries."
REACTION_PHRASE = "thumbs up if that works"
REACTION = "\N{THUMBS UP SIGN}"
THREAD_PHRASE = "how many tries"
SCRIPTED_THREAD_REPLY = "Five tries, then it stops and reports the failure."
SCRIPT = RoomScript(
    answer=SCRIPTED_ANSWER,
    reply=SCRIPTED_REPLY,
    reply_phrase=REPLY_PHRASE,
    reaction=REACTION,
    reaction_phrase=REACTION_PHRASE,
    thread_reply=SCRIPTED_THREAD_REPLY,
    thread_phrase=THREAD_PHRASE,
)
# The one delivered action each graded moment expects (`checks.discord_scripted_outcomes`).
EXPECTED = {
    "post": {"kind": "message", "text": SCRIPTED_ANSWER},
    "reply": {"kind": "reply", "text": SCRIPTED_REPLY},
    "reaction": {"kind": "reaction", "reaction": REACTION},
    "thread-reply": {"kind": "reply", "text": SCRIPTED_THREAD_REPLY},
}
THREAD = "retry details"

MOMENTS = (
    MomentSpec("first-message", SCENES / "first-message.json", "report"),
    MomentSpec("bot-status-report", BEHAVIOR_SCENES / "behavior" / "bot-status-report.json", "no-turn"),
    MomentSpec("direct-question", SCENES / "direct-question.json", "post", "sensible default timeout"),
    MomentSpec("reply", SCENES / "reply.json", "reply", REPLY_PHRASE, reply_to_agent=True),
    MomentSpec("reaction", SCENES / "reaction.json", "reaction", REACTION_PHRASE, reconnect_before=True),
    MomentSpec("thread", SCENES / "thread.json", "report", thread=THREAD),
    MomentSpec("thread-question", SCENES / "thread-question.json", "thread-reply", THREAD_PHRASE, thread=THREAD),
)

# The two gaps the shared transport and the reference had, closed: a person's first message after a
# start reaches the participant (behind the continuity gap the process declares), and a message in
# a thread under the room is part of the room. Pinned `reached` so that a regression fails the lane
# (update the pin and its docs). The thread question is graded, not pinned: its reply must land in
# the thread.
TRANSPORT_PINS = {"first-message": REACHED, "thread": REACHED}
REFERENCE_PINS = {"first-message": REACHED, "thread": REACHED}

# The reference runs discord.py; the stand-in's shape pin is discord.py 2.7.1's.
REFERENCE_PIN = "discord.py 2.7.1"
PARTICIPANT_KEY_ENV = "NUNCHI_PARTICIPANT_API_KEY"
BOT_TOKEN_ENV = "DISCORD_BOT_TOKEN"

# The console scripts, run as their entry points do: ``main`` from the same module.
CONSOLE_SCRIPTS = {
    "nunchi-mcp-discord": "nunchi.mcp_discord.server",
    "nunchi-discord": "nunchi.adapters.discord",
}
# What each process runs on, recorded from its own Python and environment: the transport's
# mcp-discord extra, the reference's discord.py, Hermes's own package and its discord.py.
PACKAGES = {"nunchi-mcp-discord": ("mcp",), "nunchi-discord": ("discord.py", "aiohttp"), "hermes": ("hermes-agent", "discord.py", "aiohttp")}
INSTALLED = (
    "import importlib.metadata as metadata, json, sys\n"
    "import nunchi\n"
    "def version(name):\n"
    "    try:\n"
    "        return metadata.version(name)\n"
    "    except metadata.PackageNotFoundError:\n"
    "        return None\n"
    "print(json.dumps({'python': sys.version.split()[0], 'nunchi': nunchi.__version__, 'nunchi_from': nunchi.__file__,\n"
    "                  **{name: version(name) for name in sys.argv[1:]}}))\n"
)

# What each column's bot must have done on the wire (`checks.discord_clients_complete`).
POST = "POST /channels/{channel}/messages"
REACT = "PUT /channels/{channel}/messages/{message}/reactions/{emoji}/@me"
TRANSPORT_CALLS = (POST, REACT, "GET /channels/{channel}", "GET /guilds/{guild}/members/{user}", "GET /guilds/{guild}/roles")
REFERENCE_CALLS = ("GET /users/@me", POST, REACT)

# The transport journal's outcomes that mean a gap (`nunchi.mcp_discord.server.TransportAuditJournal`).
TRANSPORT_GAP_OUTCOMES = ("source-gap", "gap-signal", "queue-rejected", "client-delivery-lost", "shutdown-lost")
# How long a posted message may take to reach Nunchi before it reads as not delivered.
REACH_SECONDS = 8.0


def reference_route() -> Route:
    """The reference's model route: the scripted plain-call participant (set once it starts), its key by name."""

    return Route(REFERENCE, "scripted-participant", secret_env=(PARTICIPANT_KEY_ENV,), base_url="(the scripted participant)")


def load_net(environment: Mapping[str, str]) -> dict[str, Any]:
    """The launcher's record of this run (`discord_net.py`); without it the Discord room does not run."""

    path = environment.get(NET_ENV)
    if not path:
        raise CouldNotRun(
            f"{NET_ENV} is not set: --room discord runs inside the launcher, as "
            "sudo -E <python> -m evals.rehearsal.discord_net --offline -- <python> -m evals.rehearsal.probe ..."
        )
    try:
        net = json.loads(Path(path).read_text(encoding="utf-8"))
        net["tls"]["cert"], net["tls"]["key"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CouldNotRun(f"the launcher's record {path} cannot be read: {exc}") from exc
    return net


def world_spec(column: str, scenes: Sequence[Scene], *, agent: str) -> tuple[dict[str, Any], dict[str, str]]:
    """The stand-in's world for one column, and each scene name's member in it.

    People keep their scene name (Discord shows it title-cased); a scene's
    bot is a scripted bot no harness runs, named as the scene shows it; the
    agent is the column's own bot, named as its profile. One channel,
    named after the column.
    """

    people: list[str] = []
    bots: dict[str, dict[str, Any]] = {}
    members: dict[str, str] = {PARTICIPANT: agent}
    for scene in scenes:
        for event in scene.events:
            for name in (event["author"], *event.get("mentions", ())):
                if name in members:
                    continue
                actor = scene.actors.get(name, {})
                if actor.get("kind") == "bot":
                    members[name] = str(actor.get("display_name") or name)
                    bots[members[name]] = {"harness": False}
                else:
                    members[name] = name
                    people.append(name)
    bots[agent] = {}
    return {"guild": "nunchi-rehearsal", "people": people, "bots": bots, "channels": {column: {}}}, members


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def delivery_audits(state: Path) -> list[dict[str, Any]]:
    """Every delivery audit a room wrote in ``state`` (`nunchi.observation`), in the order written."""

    found: list[dict[str, Any]] = []
    for path in sorted(state.glob("*.delivery-audit.jsonl")):
        found += read_jsonl(path)
    return found


def audit_for(audits: Sequence[Mapping[str, Any]], message_id: str) -> dict[str, Any] | None:
    """The first audit of a Discord message: by its event id, or, refused before it had one, by its delivery id.

    A message's delivery id ends in ``:MESSAGE_CREATE:<its id>``
    (`nunchi.adapters.v2.normalize_discord_gateway`).
    """

    event_id = f"discord:message:{message_id}"
    for audit in audits:
        if audit.get("event_id") == event_id or str(audit.get("delivery_id", "")).endswith(f":MESSAGE_CREATE:{message_id}"):
            return dict(audit)
    return None


def room_events(state: Path) -> dict[str, dict[str, Any]]:
    """Every event in the participant's own room log (its observations, `nunchi.observation`) in ``state``, by id."""

    found: dict[str, dict[str, Any]] = {}
    for path in sorted(state.glob("*observations.jsonl")):
        for record in read_jsonl(path):
            event = record.get("event") if isinstance(record.get("event"), Mapping) else {}
            if event.get("id"):
                found[str(event["id"])] = dict(event)
    return found


# Outcomes of an audit that mean the message is now in the participant's room.
OBSERVED = ("recorded", "exact-self-context", "exact-duplicate")


def wire_writes(records: Sequence[Mapping[str, Any]], bot: str) -> list[dict[str, Any]]:
    """The bot's 2xx writes on the wire: each message with its content and reply target, each reaction with its emoji and message."""

    writes: list[dict[str, Any]] = []
    for record in records:
        status = record.get("status")
        if record.get("kind") != "http" or record.get("bot") != bot or record.get("method") == "GET":
            continue
        if not isinstance(status, int) or not 200 <= status < 300:
            continue
        parts = str(record.get("decoded_path", "")).split("/")
        if record.get("route") == "/channels/{channel}/messages":
            body = record.get("request") if isinstance(record.get("request"), Mapping) else {}
            response = record.get("response") if isinstance(record.get("response"), Mapping) else {}
            reference = body.get("message_reference") if isinstance(body.get("message_reference"), Mapping) else {}
            writes.append(
                {
                    "kind": "message",
                    "content": body.get("content"),
                    "reply_to": str(reference["message_id"]) if reference.get("message_id") else None,
                    "message_id": response.get("id"),
                    "channel_id": parts[4] if len(parts) > 4 else None,
                }
            )
        elif str(record.get("route", "")).endswith("/reactions/{emoji}/@me") and len(parts) > 8:
            writes.append(
                {
                    "kind": "reaction",
                    "emoji": parts[8],
                    "message_id": parts[6],
                    "channel_id": parts[4],
                    "removed": record.get("method") == "DELETE",
                }
            )
    return writes


def wire_calls(records: Sequence[Mapping[str, Any]], bot: str) -> list[str]:
    """Each ``METHOD /route`` the bot made with a 2xx answer, once each, in the order first made."""

    calls: dict[str, None] = {}
    for record in records:
        status = record.get("status")
        if record.get("kind") == "http" and record.get("bot") == bot and isinstance(status, int) and 200 <= status < 300:
            calls[f"{record.get('method')} {record.get('route')}"] = None
    return list(calls)


def typing_calls(records: Sequence[Mapping[str, Any]], bot: str) -> int:
    """How many typing indicators the bot sent, read from its requests (``POST .../typing``), not from a route.

    The stand-in serves no typing route: such a request is answered 599 and recorded as unknown, which
    fails ``discord-standin-clean``, and it carries no route template to count by.
    """

    return sum(
        1
        for record in records
        if record.get("kind") == "http"
        and record.get("bot") == bot
        and record.get("method") == "POST"
        and str(record.get("decoded_path", "")).endswith("/typing")
    )


def reconnect_facts(
    records: Sequence[Mapping[str, Any]],
    bot: str,
    *,
    message_reached: bool,
    transport_journal: Sequence[Mapping[str, Any]] = (),
    audits: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """What one bot did after op 7, from the wire records, journal records and audits written since it."""

    def frames(direction: str, **match: Any) -> list[Mapping[str, Any]]:
        return [
            record
            for record in records
            if record.get("kind") == "ws" and record.get("dir") == direction and record.get("bot") == bot
            and all(record.get(key) == value for key, value in match.items())
        ]

    return {
        "bot": bot,
        "op7": len(frames("out", op=7)),
        "resumed": bool(frames("in", op=6) and frames("out", t="RESUMED")),
        "identified_again": bool(frames("in", op=2)),
        "message_reached": message_reached,
        "transport_gaps": [record.get("outcome") for record in transport_journal if record.get("outcome") in TRANSPORT_GAP_OUTCOMES],
        "participant_gaps": [audit.get("delivery_id") for audit in audits if audit.get("outcome") == "continuity-gap"],
    }


class DiscordProcess:
    """One of Nunchi's Discord processes: its command, its environment's names, its preflight, and how it ended."""

    def __init__(
        self, name: str, argv: list[str], env: dict[str, str], *, cwd: Path, log: Path, secrets: Mapping[str, str], own_keys: Sequence[str]
    ) -> None:
        self.name = name
        self.argv = argv
        self.env = env
        self.cwd = cwd
        self.log = log
        self.own_keys = list(own_keys)
        self.names = _env_names(env, secrets)
        self.preflight: dict[str, Any] = {}
        self.installed: dict[str, Any] = {}
        self.port: int | None = None
        self.process: subprocess.Popen | None = None
        self.running_after_moments: bool | None = None
        self.stopped_by: str | None = None
        self.exit: int | None = None

    def start(self) -> None:
        self.log.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log, "wb") as handle:
            # Its own session: the probe stops it, never a signal meant for the probe.
            self.process = subprocess.Popen(
                self.argv, env=self.env, cwd=self.cwd, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True
            )

    def tail(self, lines: int = 8) -> str:
        try:
            text = self.log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return " | ".join(text.strip().splitlines()[-lines:])[-1200:]

    def alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def stop(self, waits: Sequence[float] = (15.0, 5.0, 5.0, 5.0)) -> None:
        """SIGINT, as a person would stop it, then SIGINT again, SIGTERM and SIGKILL, each after its wait."""

        if self.process is None:
            return
        if self.running_after_moments is None:
            self.running_after_moments = self.alive()
        for how, wait in zip(("SIGINT", "SIGINT again", "SIGTERM", "SIGKILL"), waits):
            if self.process.poll() is not None:
                break
            with contextlib.suppress(ProcessLookupError):
                self.process.send_signal(getattr(signal, how.split()[0]))
            try:
                self.process.wait(wait)
            except subprocess.TimeoutExpired:
                continue
            self.stopped_by = how.split()[0] if how != "SIGINT again" else "SIGINT"
            break
        self.exit = self.process.poll()

    def document(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "console_script": self.name,
            "argv": list(self.argv),
            "cwd": str(self.cwd),
            **self.names,
            "own_keys": self.own_keys,
            "installed": self.installed,
            "preflight": self.preflight,
            "port": self.port,
            "log": self.log.name,
            "running_after_moments": self.running_after_moments,
            "stopped_by": self.stopped_by,
            "exit": self.exit,
        }


class DiscordRoom:
    """The stand-in and the Discord processes of one run: what every column in the Discord room shares."""

    def __init__(self, ctx: Context, column: str, *, actor: str = "discord:actor") -> None:
        self.ctx = ctx
        self.column = column
        # How a person's or bot's id reads in an event: the shared transport and the reference
        # say ``discord:actor:<id>``, the Hermes plugin ``discord:user:<id>``.
        self.actor = actor
        self.net = load_net(ctx.original_env)
        self.python = ctx.options.discord_python or sys.executable
        self.base = ctx.base / "discord"
        # The room's state directory, where the participant's room writes its audits.
        self.state = ctx.base / "state"
        self.agent = str(ctx.profile["display_name"])
        self.fd: FakeDiscord | None = None
        self.members: dict[str, str] = {}
        self.processes: list[DiscordProcess] = []
        self.verdict: dict[str, Any] | None = None
        self.channel_id = ""
        self.agent_id = ""
        self.threads: dict[str, str] = {}
        self.start_gap: dict[str, Any] = {}
        self.reconnects: list[dict[str, Any]] = []
        self._pending_reconnect: dict[str, Any] | None = None
        self._scene_ids: dict[str, str] = {}

    # -- the stand-in --------------------------------------------------------------------------------

    def start(self) -> None:
        scenes = [load_scene(spec.scene) for spec in MOMENTS]
        spec, self.members = world_spec(self.column, scenes, agent=self.agent)
        tls = self.net["tls"]
        self.fd = FakeDiscord(spec, self.ctx.out, port=443, tls=(tls["cert"], tls["key"])).start()
        world = self.fd.world
        self.channel_id = world.channel(self.column).id
        self.agent_id = world.member(self.agent).id
        for member in world.members.values():
            if member.token:
                # Never in any output: the scan looks for each one.
                self.ctx.secrets[f"the {member.name} bot's token"] = member.token

    @property
    def records(self) -> list[dict[str, Any]]:
        return list(self.fd.wire.records) if self.fd is not None else []

    def quiet(self, seconds: float) -> bool:
        """Whether nothing but heartbeats has crossed the wire for ``seconds``."""

        return self.fd is not None and self.fd.wire.settle(seconds, 0.0)

    def close(self) -> None:
        for process in reversed(self.processes):
            process.stop()
        if self.fd is not None and self.verdict is None:
            self.verdict = self.fd.stop()

    # -- the processes -------------------------------------------------------------------------------

    def environment(self, name: str, own: Mapping[str, str]) -> tuple[dict[str, str], Path]:
        """A Discord process's environment: the path, locale and certificates, its own fresh HOME and TMPDIR, and ``own``.

        No proxy variable (the launcher refuses them, and a Discord client
        would follow one past the stand-in), no key of the harness's, no
        canary. ``PYTHONPATH``, where the probe was given one, is passed on
        with each entry made absolute, so a checkout's Nunchi imports.
        """

        directory = self.base / name
        env = {key: value for key, value in self.ctx.env.items() if key in PASSTHROUGH_ENV and not key.lower().endswith("_proxy")}
        for key in ("home", "tmp"):
            (directory / key).mkdir(parents=True, exist_ok=True, mode=0o700)
        env.update(HOME=str(directory / "home"), TMPDIR=str(directory / "tmp"))
        pythonpath = self.ctx.original_env.get("PYTHONPATH")
        if pythonpath:
            env["PYTHONPATH"] = os.pathsep.join(str(Path(item).absolute()) for item in pythonpath.split(os.pathsep) if item)
        env.update(own)
        return env, directory

    def run_preflight(self, process: DiscordProcess) -> None:
        """The preflight, in the process's own environment and Python; the process never starts unless it passed."""

        assert self.fd is not None
        argv = [self.python, "-m", "evals.rehearsal.preflight", "--nonce", self.fd.preflight_nonce]
        try:
            done = subprocess.run(argv, env=process.env, cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
            result = json.loads(done.stdout)
            result["exit"] = done.returncode
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            result = {"ok": False, "failures": [f"the preflight did not run: {type(exc).__name__}: {exc}"]}
        result["argv"] = argv
        process.preflight = result
        if not result.get("ok") or result.get("certificate_sha256") != self.net.get("leaf_sha256"):
            failures = "; ".join(result.get("failures") or ["it saw another certificate than the launcher's"])
            raise CouldNotRun(f"{process.name}'s preflight failed, so it was not started: {failures}")

    def installed(self, process: DiscordProcess) -> dict[str, Any]:
        """Which Nunchi, Python and packages the process runs on, read in its own Python, environment and directory."""

        argv = [self.python, "-c", INSTALLED, *PACKAGES.get(process.name, ())]
        try:
            done = subprocess.run(argv, env=process.env, cwd=process.cwd, capture_output=True, text=True, timeout=60, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}
        try:
            return dict(json.loads(done.stdout))
        except (ValueError, TypeError):
            return {"error": f"exit {done.returncode}: {' | '.join(done.stderr.strip().splitlines()[-3:])[-400:]}"}

    def launch(
        self, name: str, own: Mapping[str, str], *, own_keys: Sequence[str], arguments: Sequence[str] = (), argv: Sequence[str] | None = None
    ) -> DiscordProcess:
        env, directory = self.environment(name, own)
        if argv is None:
            argv = [self.python, "-c", f"import sys; from {CONSOLE_SCRIPTS[name]} import main; sys.exit(main())", *arguments]
        argv = list(argv)
        process = DiscordProcess(
            name, argv, env, cwd=directory, log=self.ctx.out / "discord" / f"{name}.log", secrets=self.ctx.secrets, own_keys=own_keys
        )
        self.processes.append(process)
        process.installed = self.installed(process)
        self.run_preflight(process)
        process.start()
        return process

    def wait_ready(self, process: DiscordProcess, bot: str, *, timeout: float = 60.0) -> None:
        """Until the bot's session got READY on the wire; the process must still run."""

        assert self.fd is not None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not process.alive():
                raise RuntimeError(f"{process.name} exited ({process.process.poll()}) before READY: {process.tail()}")
            try:
                self.fd.wait_for(
                    lambda record: record.get("kind") == "ws" and record.get("dir") == "out" and record.get("t") == "READY"
                    and record.get("bot") == bot,
                    timeout=1.0,
                )
                return
            except TimeoutError:
                continue
        raise RuntimeError(f"{bot}'s {process.name} got no READY within {timeout:.0f} s: {process.tail()}")

    def start_transport(self, output_key: str) -> DiscordProcess:
        """`nunchi-mcp-discord` for the agent's bot, on a free loopback port, routed to the column's channel alone."""

        assert self.fd is not None
        with socket.socket() as probe_socket:
            probe_socket.bind(("127.0.0.1", 0))
            port = probe_socket.getsockname()[1]
        state = self.base / "nunchi-mcp-discord" / "state"
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        own = {
            "NUNCHI_DISCORD_TOKEN": self.fd.token(self.agent),
            "NUNCHI_DISCORD_PARTICIPANT_ROUTES": json.dumps({PARTICIPANT: [self.channel_id]}),
            "NUNCHI_DISCORD_OUTPUT_HMAC_KEY": output_key,
            "NUNCHI_DISCORD_STATE_DIRECTORY": str(state),
            "NUNCHI_MCP_DISCORD_HOST": "127.0.0.1",
            "NUNCHI_MCP_DISCORD_PORT": str(port),
        }
        process = self.launch("nunchi-mcp-discord", own, own_keys=["NUNCHI_DISCORD_TOKEN", "NUNCHI_DISCORD_OUTPUT_HMAC_KEY"])
        process.port = port
        self.wait_ready(process, self.agent)
        deadline = time.monotonic() + 30
        while True:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                return process
            except OSError:
                if time.monotonic() > deadline or not process.alive():
                    raise RuntimeError(f"nunchi-mcp-discord never served MCP on port {port}: {process.tail()}") from None
                time.sleep(0.2)

    def transport_journal(self) -> list[dict[str, Any]]:
        return read_jsonl(self.base / "nunchi-mcp-discord" / "state" / "transport-delivery-audit.jsonl")

    # -- the moments ---------------------------------------------------------------------------------

    def render(self, raw: Mapping[str, Any], scene: Scene) -> str:
        """The message as a person types it in Discord: each mention a ping, in place of the name where the text has it."""

        assert self.fd is not None
        text = str(raw["text"])
        for name in raw.get("mentions", ()):
            member = self.fd.world.member(self.members[name])
            display = str(scene.actors.get(name, {}).get("display_name") or member.name)
            ping = f"<@{member.id}>"
            text = text.replace(display, ping, 1) if display in text else f"{ping} {text}"
        return text

    def agent_last_post(self) -> str | None:
        posts = [write for write in wire_writes(self.records, self.agent) if write["kind"] == "message" and write.get("message_id")]
        return str(posts[-1]["message_id"]) if posts else None

    def post(self, raw: Mapping[str, Any], at: datetime, scene: Scene, spec: MomentSpec) -> dict[str, Any]:
        """Post one scene message as its author, through the stand-in's control API; returns the delivery so far."""

        assert self.fd is not None
        if raw.get("type", "message") != "message":
            raise CouldNotRun(f"the probe plays messages only, not {raw.get('type')}")
        author = self.members[raw["author"]]
        channel = self.column
        if spec.thread:
            if spec.thread not in self.threads:
                self.threads[spec.thread] = self.fd.create_thread(author, self.column, spec.thread)["id"]
            channel = spec.thread
        reply_to = self._scene_ids.get(raw["reply_to"]) if raw.get("reply_to") else None
        note = None
        if spec.reply_to_agent and raw["id"] == scene.moments[0].event:
            reply_to = self.agent_last_post()
            if reply_to is None:
                note = "the agent had no post to reply to, so this went as a plain message"
        # A thread's message takes the room's time: the thread was opened just now, and its id is a time too.
        answer = self.fd.post(author, channel, self.render(raw, scene), reply_to=reply_to, at=None if spec.thread else at)
        self._scene_ids[raw["id"]] = answer["id"]
        delivery: dict[str, Any] = {
            "scene_event": raw["id"],
            "event_id": f"discord:message:{answer['id']}",
            "author": f"{self.actor}:{self.fd.world.member(author).id}",
            "channel": channel,
            # What the message carried, for `checks.discord_addressing` to compare with what Nunchi received: whom it
            # pinged (the pings in its text, and, for a reply, its target's author, as Discord does), and the message
            # it replied to.
            "mentioned_actor_ids": [f"{self.actor}:{user}" for user in self.fd.world.messages[answer["id"]]["mentions"]],
            "reply_to": reply_to,
            "dispatched_to": answer["dispatched_to"],
            "message_id": answer["id"],
            # The thread it was said in, as an event names it (`thread_root_event_id`); None in the room itself.
            "thread": f"discord:message:{self.threads[spec.thread]}" if spec.thread else None,
        }
        if note:
            delivery["note"] = note
        return delivery

    def reach(self, delivery: dict[str, Any], *, timeout: float = REACH_SECONDS) -> dict[str, Any]:
        """Wait until the participant's room audited the message, or ``timeout``; records how it was audited."""

        deadline = time.monotonic() + timeout
        audit = None
        while time.monotonic() < deadline:
            audit = audit_for(delivery_audits(self.state), delivery["message_id"])
            if audit is not None:
                break
            time.sleep(0.1)
        delivery["audit"] = audit.get("outcome") if audit else None
        delivery["reached_nunchi"] = audit is not None
        delivery["observed"] = bool(audit and audit.get("outcome") in OBSERVED)
        if audit and not delivery["observed"]:
            delivery["note"] = f"Nunchi refused it: {audit.get('outcome')} ({audit.get('detail')})"
        elif audit is None:
            delivery["note"] = "it never reached Nunchi"
        return delivery

    def holds_own_post(self, event_id: str) -> bool:
        """Whether the participant's room log holds the agent's own message under ``event_id``: what a reply to it resolves to."""

        event = room_events(self.state).get(event_id) or {}
        return event.get("type") == "message" and event.get("author_id") == f"{self.actor}:{self.agent_id}"

    def reconnect(self) -> None:
        """Op 7 to every harness bot; what follows is read after the next moment (`reconnected`)."""

        assert self.fd is not None
        bots = [member.name for member in self.fd.world.members.values() if member.harness]
        self._pending_reconnect = {
            "since": len(self.fd.wire.records),
            "journal": len(self.transport_journal()),
            "audits": len(delivery_audits(self.state)),
            "bots": bots,
        }
        for bot in bots:
            self.fd.gateway(bot, "reconnect")

    def reconnected(self, moment: Mapping[str, Any]) -> None:
        pending, self._pending_reconnect = self._pending_reconnect, None
        if pending is None:
            return
        reached = all(delivery.get("observed") for delivery in moment.get("deliveries", ()))
        records = self.records[pending["since"]:]
        journal = self.transport_journal()[pending["journal"]:]
        audits = delivery_audits(self.state)[pending["audits"]:]
        for bot in pending["bots"]:
            self.reconnects.append(
                {"moment": moment.get("name"), **reconnect_facts(records, bot, message_reached=reached, transport_journal=journal, audits=audits)}
            )

    def effects(self) -> list[dict[str, Any]]:
        """What reached the room from the agent's bot, read from the wire."""

        assert self.fd is not None
        names = {channel.id: channel.name for channel in self.fd.world.channels.values()}
        effects: list[dict[str, Any]] = []
        for write in wire_writes(self.records, self.agent):
            where = names.get(str(write.get("channel_id")), write.get("channel_id"))
            if write["kind"] == "message":
                effects.append({"kind": "message", "where": where, "text": write.get("content"), "reply_to": write.get("reply_to")})
            else:
                effect = {"kind": "reaction", "where": where, "reaction": write.get("emoji"), "message_id": write.get("message_id")}
                if write.get("removed"):
                    effect["removed"] = True
                effects.append(effect)
        return effects

    # -- the record and the checks -----------------------------------------------------------------

    def record(self) -> dict[str, Any]:
        verdict = self.verdict or {}
        launcher = {
            key: self.net.get(key)
            for key in ("names", "address", "offline", "ci", "namespace", "port_start", "bwrap", "leaf_sha256", "ca_sha256", "launcher", "started", "user")
            if key in self.net
        }
        return {
            "launcher": launcher,
            "python": self.python,
            "world": self.fd.world.describe() if self.fd is not None else {},
            "column": {"channel": self.column, "channel_id": self.channel_id, "bot": self.agent, "bot_id": self.agent_id},
            "processes": [process.document() for process in self.processes],
            "standin": {
                "clean": verdict.get("clean"),
                "unknown": verdict.get("unknown", []),
                "raised": len(verdict.get("raised") or ()),
                "bots": verdict.get("bots", {}),
                "outputs": ["world.json", "discord-wire.jsonl", "discord-standin.json"],
            },
            "threads": dict(self.threads),
            "start_gap": dict(self.start_gap),
            "reconnects": list(self.reconnects),
            "writes": wire_writes(self.records, self.agent) if self.fd is not None else [],
        }

    def checks(
        self,
        committed: Sequence[Mapping[str, Any]],
        *,
        expected: Mapping[str, Mapping[str, Any]],
        gaps_fail: bool,
        moments: Sequence[Mapping[str, Any]],
        start_required: bool | None = True,
        reply_resolves: bool = True,
        own_reaction_remembered: bool = True,
    ) -> list[Check]:
        verdict = self.verdict or {"clean": False, "unknown": [{"what": "no verdict: the stand-in never stopped"}]}
        records = self.records
        processes = [process.document() for process in self.processes]
        return [
            checks_module.discord_preflight(processes, leaf_sha256=self.net.get("leaf_sha256")),
            checks_module.discord_processes(processes),
            checks_module.discord_standin_clean(verdict),
            checks_module.discord_clients_complete(
                verdict.get("bots", {}), expected, {bot: wire_calls(records, bot) for bot in expected}
            ),
            checks_module.discord_writes_reconciled(committed, wire_writes(records, self.agent)),
            checks_module.discord_continuity(self.start_gap, self.reconnects, gaps_fail=gaps_fail, start_required=start_required),
            checks_module.discord_addressing(
                moments,
                agent=f"{self.actor}:{self.agent_id}",
                writes=wire_writes(records, self.agent),
                reply_resolves=reply_resolves,
                own_reaction_remembered=own_reaction_remembered,
            ),
        ]


def landed(action: Mapping[str, Any], effects: Sequence[Mapping[str, Any]]) -> str | None:
    """The channel an action of the agent's reached, by name, read from what the bot wrote on the wire (``effects``)."""

    target = str(action.get("target_event_id") or "").removeprefix("discord:message:")
    for effect in effects:
        if action.get("kind") in ("message", "reply"):
            if (
                effect.get("kind") == "message"
                and effect.get("text") == action.get("text")
                and (effect.get("reply_to") or None) == (target if action.get("kind") == "reply" else None)
            ):
                return effect.get("where")
        elif (
            action.get("kind") == "reaction"
            and effect.get("kind") == "reaction"
            and effect.get("reaction") == action.get("reaction")
            and effect.get("message_id") == target
        ):
            return effect.get("where")
    return None


def replied_to(action: Mapping[str, Any], effects: Sequence[Mapping[str, Any]]) -> str | None:
    """The message a harness-posted message answers on the wire: None when the wire shows it posted plain (or not posted at all)."""

    posted = [effect for effect in effects if effect.get("kind") == "message" and effect.get("text") == action.get("text")]
    if not posted or any(not effect.get("reply_to") for effect in posted):
        return None
    return str(posted[0]["reply_to"])


def judge_discord_moments(leg: Leg, moments: Sequence[dict[str, Any]], received: Mapping[str, Mapping[str, Any]]) -> None:
    """Mark each committed action delivered or not, then each moment's actions and outcome (`checks.discord_moment_outcome`).

    ``received`` is how the agent's turns showed each trigger was addressed; it goes beside what was sent, in
    each delivery (`checks.discord_addressing`), with ``reply_resolves``: whether the message a reply answers
    is the agent's own post in the participant's room log. Each action also records ``where`` it landed, by
    channel name, from the wire, and, for a message its harness posted itself, ``replied_to``: the message
    the wire shows it answering (None for a plain message).
    """

    for moment in moments:
        for delivery in moment.get("deliveries", ()):
            delivery["received"] = received.get(delivery.get("event_id"))
            target = (delivery["received"] or {}).get("reply_to_event_id")
            if target:
                delivery["reply_resolves"] = leg.discord.holds_own_post(target)  # type: ignore[attr-defined]
    flags = checks_module.delivered(leg.committed, leg.room_effects(), harness_posts=leg.harness_posts)
    for item, ok in zip(leg.committed, flags):
        item["delivered"] = ok
    effects = leg.room_effects()
    for moment in moments:
        graded = {turn["request_id"] for turn in moment["turns"] if turn.get("trigger") == moment["graded_event"]}
        actions = [
            {
                key: item.get(key)
                for key in ("kind", "text", "reaction", "target_event_id", "origin_event_id", "operation", "delivery", "delivered")
                if key in item
            }
            for item in leg.committed
            if item.get("request_id") in graded
        ]
        for action in actions:
            action["where"] = landed(action, effects)
            if leg.harness_posts and action.get("kind") == "message":
                action["replied_to"] = replied_to(action, effects)
        moment["actions"] = actions
        moment["posts"] = [
            {"text": action.get("text"), "delivery": action.get("delivery"), "delivered": action["delivered"]}
            for action in actions
            if action.get("kind") in ("message", "reply")
        ]
        moment["outcome"] = checks_module.discord_moment_outcome(
            moment["expect"],
            reached=moment["reached"],
            graded_turns=moment["graded_turns"],
            actions=[action for action in actions if action.get("delivered")],
            graded_event=moment["graded_event"],
            thread=moment.get("thread"),
            posts_itself=leg.harness_posts,
            channel=leg.discord.column,  # type: ignore[attr-defined]
        )


# -- Claude Code and Codex on a real nunchi-mcp-discord ------------------------------------------------


class OnTheTransport:
    """Claude Code or Codex in the Discord room: its own `nunchi-mcp-discord`, and its runner in this process."""

    script = SCRIPT
    pins = TRANSPORT_PINS
    expected_calls = TRANSPORT_CALLS

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)  # type: ignore[call-arg]
        self.discord = DiscordRoom(ctx, self.harness)  # type: ignore[attr-defined]
        self.transport_process: DiscordProcess | None = None
        self.runner_calls: dict[str, Any] = {}
        self.serve_errors: list[str] = []
        self._stop = threading.Event()
        self._serving: threading.Thread | None = None
        self._registered = threading.Event()
        self._streaming = threading.Event()
        self._spec: MomentSpec | None = None

    def prepare(self) -> None:
        self.executable()  # type: ignore[attr-defined]  # a missing harness stops the run before any process starts
        self.discord.start()
        self.room_id = self.discord.channel_id
        self.actor_id = f"discord:actor:{self.discord.agent_id}"
        self.scope = f"discord:channel:{self.room_id}"
        self.transport_process = self.discord.start_transport(self.ctx.secrets[OUTPUT_KEY_ENV])  # type: ignore[attr-defined]
        super().prepare()  # type: ignore[misc]

    def transport_section(self) -> dict[str, Any]:
        assert self.transport_process is not None
        return {"url": f"http://127.0.0.1:{self.transport_process.port}/mcp", "timeout_seconds": 30, "output_key_env": OUTPUT_KEY_ENV}

    def runtime_inputs(self, config: dict[str, Any], path: Path, *, label: str) -> tuple[dict[str, Any], Any]:
        """As the runner's CLI ``main`` does: the config by its pinned sha256, and the client for its transport."""

        from nunchi.adapters.runtime import load_pinned_config
        from nunchi.integrations.discord_room import transport_client

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        loaded = load_pinned_config(path, digest)
        client = transport_client(loaded.get("transport"), label=label)
        self.runner_calls = {
            "in": "the probe's process",
            "calls": ["load_pinned_config", "transport_client", "the runtime", "DiscordRoomConnection.serve"],
            "config": str(path),
            "config_sha256": digest,
            "transport_url": client.url,
        }
        return loaded, client

    def attach(self, connection: Any) -> None:
        """Serve the room over MCP, as the CLI's ``main`` does, on a thread the probe can stop; wait until it registered."""

        client = connection.client
        order = self.runner_calls.setdefault("order", [])
        register, connect, open_stream = connection.register, client.connect, client.open_stream

        def registered() -> None:
            order.append("register")
            register()
            self._registered.set()

        def connected() -> Any:
            order.append("connect")
            return connect()

        def streamed() -> Any:
            stream = open_stream()
            order.append("open_stream")
            self._streaming.set()
            return stream

        connection.register, client.connect, client.open_stream = registered, connected, streamed

        def serve() -> None:
            try:
                connection.serve(stop=self._stop)
            except BaseException as exc:  # recorded: the room stops hearing the transport
                self.serve_errors.append(f"{type(exc).__name__}: {exc}")

        self._serving = threading.Thread(target=serve, name="nunchi-rehearsal-serve", daemon=True)
        self._serving.start()
        if not self._registered.wait(60):
            raise RuntimeError(
                "the runner never registered with nunchi-mcp-discord: "
                + ("; ".join(self.serve_errors) or (self.transport_process.tail() if self.transport_process else ""))
            )
        # The runner opens the notification stream before it registers, so nothing posted from
        # here on can be lost to a stream that is not open yet: the first moment starts at once.
        if not self._streaming.is_set():
            raise RuntimeError("the runner registered with nunchi-mcp-discord before it opened its notification stream")

    def play(self, spec: MomentSpec, *, settle_seconds: float) -> dict[str, Any]:
        self._spec = spec
        if spec.reconnect_before:
            self.discord.reconnect()
        moment = play_moment(self, spec, settle_seconds=settle_seconds)  # type: ignore[arg-type]
        if spec.thread:
            moment["thread"] = spec.thread
        if spec.reconnect_before:
            self.discord.reconnected(moment)
        if spec.name == "first-message":
            gaps = [audit for audit in delivery_audits(self.discord.state) if str(audit.get("delivery_id", "")).startswith("discord:transport-gap:")]
            self.discord.start_gap = {
                "process": "nunchi-mcp-discord",
                "gap": gaps[0]["delivery_id"] if gaps else None,
                "detail": "the transport put a continuity gap ahead of the first routed event after it started",
                "journal": [record.get("outcome") for record in self.discord.transport_journal()],
            }
        return moment

    def deliver(self, raw: Mapping[str, Any], at: datetime, scene: Scene, sequence: int) -> dict[str, Any]:
        assert self._spec is not None
        return self.discord.reach(self.discord.post(raw, at, scene, self._spec))

    def settle(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        steady = 0
        while time.monotonic() < deadline:
            room = self._room  # type: ignore[attr-defined]
            idle = room.drain(0.5) and self.participant.active is None and self.discord.quiet(1.0)  # type: ignore[attr-defined]
            steady = steady + 1 if idle else 0
            if steady >= 2:
                return True
            time.sleep(0.2)
        return False

    def room_effects(self) -> list[dict[str, Any]]:
        return self.discord.effects()

    def judge(self, moments: Sequence[dict[str, Any]]) -> None:
        requests = self.agent.requests() if self.agent is not None else ()  # type: ignore[attr-defined]
        judge_discord_moments(self, moments, received_triggers(requests))  # type: ignore[arg-type]

    def scripted_check(self, moments: Sequence[Mapping[str, Any]]) -> Check:
        report = self.reports.get("codex") or self.reports.get("claude_code") or {}  # type: ignore[attr-defined]
        return checks_module.discord_scripted_outcomes(moments, EXPECTED, pins=self.pins, room_tool_called=report.get("room_tool_called"))

    def room_checks(self, document: Mapping[str, Any]) -> list[Check]:
        expected = {self.discord.agent: {"chunk": False, "calls": self.expected_calls}}
        return self.discord.checks(self.committed, expected=expected, gaps_fail=True, moments=document["moments"])  # type: ignore[attr-defined]

    def room_record(self) -> dict[str, Any]:
        return {"discord": {**self.discord.record(), "runner": self.runner_calls, "serve_errors": list(self.serve_errors)}}

    def close(self) -> None:
        self._stop.set()
        try:
            super().close()  # type: ignore[misc]
        finally:
            self.discord.close()
            if self._serving is not None:
                self._serving.join(15)


class DiscordClaudeCodeLeg(OnTheTransport, ClaudeCodeLeg):
    pass


class DiscordCodexLeg(OnTheTransport, CodexLeg):
    pass


# -- the reference: nunchi-discord in its own process ---------------------------------------------------


class ReferenceLeg(Leg):
    """`nunchi-discord` in its own process, with a scripted plain-call participant: the evidence comes from outside it."""

    harness = REFERENCE
    script = SCRIPT
    pins: Mapping[str, str] = REFERENCE_PINS
    expected_calls = REFERENCE_CALLS

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self.discord = DiscordRoom(ctx, self.harness)
        self.participant_endpoint: ScriptedParticipant | None = None
        self.process: DiscordProcess | None = None
        self._spec: MomentSpec | None = None

    @property
    def room(self) -> Any:
        return None

    def prepare(self) -> None:
        self.discord.start()
        self.room_id = self.discord.channel_id
        self.actor_id = f"discord:actor:{self.discord.agent_id}"
        self.scope = f"discord:channel:{self.room_id}"
        self.participant_endpoint = ScriptedParticipant(self.script)
        self.ctx.route = replace(self.ctx.route, base_url=self.participant_endpoint.base_url)
        _, path = self.room_config(
            {
                "participant_model": {
                    "model": self.ctx.route.model,
                    "base_url": self.participant_endpoint.base_url,
                    "provider": "scripted",
                    "api_key_env": PARTICIPANT_KEY_ENV,
                    "timeout_seconds": 30,
                },
                "transport": {"bot_token_env": BOT_TOKEN_ENV},
            }
        )
        assert self.discord.fd is not None
        own = {
            BOT_TOKEN_ENV: self.discord.fd.token(self.discord.agent),
            ATTENTION_KEY_ENV: self.ctx.secrets[ATTENTION_KEY_ENV],
            PARTICIPANT_KEY_ENV: self.ctx.secrets[PARTICIPANT_KEY_ENV],
        }
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.install = self.reference_install()
        self.process = self.discord.launch(
            "nunchi-discord", own, own_keys=list(own), arguments=["--config", str(path), "--config-sha256", digest]
        )
        self.actual_homes = {name: self.process.env[name] for name in ("HOME", "TMPDIR")}
        self.discord.wait_ready(self.process, self.discord.agent)
        # The runtime exists once discord.py's on_ready ran: it marks its startup gap first.
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            gaps = [
                audit for audit in delivery_audits(self.discord.state)
                if str(audit.get("delivery_id", "")).startswith("discord:standalone-startup-gap:")
            ]
            if gaps:
                self.discord.start_gap = {
                    "process": "nunchi-discord",
                    "gap": gaps[0]["delivery_id"],
                    "detail": "the reference marks a gap on a fresh gateway session: it cannot attest what it missed before READY",
                }
                return
            if not self.process.alive():
                break
            time.sleep(0.2)
        raise RuntimeError(f"nunchi-discord never built its room after READY: {self.process.tail()}")

    def reference_install(self) -> dict[str, Any]:
        """Which reference ran: Nunchi's and discord.py's versions, in the Python that runs it."""

        env, _ = self.discord.environment("version", {})
        argv = [self.discord.python, "-c", "import discord, nunchi, sys; print(f'nunchi-discord {nunchi.__version__} on discord.py {discord.__version__} (Python {sys.version.split()[0]})')"]
        self.ran("the reference's version, for the record", argv, env)
        try:
            done = subprocess.run(argv, env=env, cwd=self.discord.base, capture_output=True, text=True, timeout=60, check=False)
            version = (done.stdout or done.stderr).strip().splitlines()[-1] if (done.stdout or done.stderr).strip() else None
        except (OSError, subprocess.SubprocessError):
            version = None
        return {"version": version, "expected": self.ctx.options.expect_version or REFERENCE_PIN, "executable": self.discord.python}

    def deliver(self, raw: Mapping[str, Any], at: datetime, scene: Scene, sequence: int) -> dict[str, Any]:
        assert self._spec is not None
        return self.discord.reach(self.discord.post(raw, at, scene, self._spec))

    def play(self, spec: MomentSpec, *, settle_seconds: float) -> dict[str, Any]:
        self._spec = spec
        if spec.reconnect_before:
            self.discord.reconnect()
        moment = play_moment(self, spec, settle_seconds=settle_seconds)
        if spec.thread:
            moment["thread"] = spec.thread
        if spec.reconnect_before:
            self.discord.reconnected(moment)
        # The reference runs in its own process: its turns are read from outside it after each moment.
        self.read_turns()
        moment["turns"] = [turn for turn in self.invocations if turn.get("moment") == spec.name or turn.get("moment") is None]
        for turn in moment["turns"]:
            turn["moment"] = spec.name
        graded = [turn for turn in moment["turns"] if turn.get("trigger") == moment["graded_event"]]
        moment["graded_turns"] = len(graded)
        moment["graded_wake_sources"] = [turn.get("source") for turn in graded]
        moment["other_turns"] = len(moment["turns"]) - len(graded)
        return moment

    def settle(self, timeout: float) -> bool:
        """Until nothing moved for 2 s: the wire, both scripted endpoints, and the reference's receipts."""

        deadline = time.monotonic() + timeout
        last: Any = None
        since = time.monotonic()
        while time.monotonic() < deadline:
            mark = (
                len(self.participant_endpoint.answers) if self.participant_endpoint else 0,
                len(getattr(self.ctx.attention_endpoint, "judged", ())),
                self._written(),
            )
            if mark != last:
                last, since = mark, time.monotonic()
            if time.monotonic() - since >= 2.0 and self.discord.quiet(2.0):
                return True
            time.sleep(0.2)
        return False

    def _written(self) -> int:
        """How much the reference has written to its state directory."""

        total = 0
        for path in self.discord.state.glob("*.jsonl"):
            with contextlib.suppress(OSError):
                total += path.stat().st_size
        return total

    def receipts(self) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for path in sorted(self.discord.state.glob("*receipts.jsonl")):
            found += read_jsonl(path)
        return found

    def read_turns(self) -> None:
        """The turns, actions and attention calls, from the scripted endpoints' records and the reference's receipts.

        A turn is each request the scripted participant was asked, with the
        action it answered; it was bound when the host recorded it as
        invoked, since a plain-call participant's answer names the turn's
        request_id, which the host checks. An action was committed when the
        reference's transport receipt says how its delivery went.
        """

        receipts = self.receipts()
        stages: dict[str, dict[str, Any]] = {}
        for receipt in receipts:
            stages.setdefault(receipt["request_id"], {})[receipt["stage"]] = receipt.get("body") or {}
        answers: dict[str, list[dict[str, Any]]] = {}
        for answer in self.participant_endpoint.answers if self.participant_endpoint else ():
            answers.setdefault(answer["request_id"], []).append(answer)
        known = {turn["request_id"]: turn for turn in self.invocations}
        for request_id, given in answers.items():
            host = stages.get(request_id, {}).get("participant-host")
            turn = known.get(request_id)
            if turn is None:
                turn = {"request_id": request_id, "trigger": given[0]["trigger"], "source": given[0]["source"], "started": given[0]["at"], "moment": None}
                self.invocations.append(turn)
            turn.update(
                {
                    "calls": len(given),
                    "bound": bool(host and host.get("invoked")),
                    "result": _summarize_action(given[-1]["action"]),
                }
            )
            if host is not None:
                turn["ended"] = given[-1]["at"]
        committed = {item["request_id"] for item in self.committed}
        for request_id, stage in stages.items():
            transport = stage.get("transport")
            if transport is None or request_id in committed or request_id not in answers:
                continue
            action = _summarize_action(answers[request_id][-1]["action"])
            action.pop("why", None)
            self.committed.append({"request_id": request_id, **action, "delivery": transport.get("delivery"), "detail": transport.get("detail")})
        self.attention_calls = []
        for request_id, stage in stages.items():
            attention = stage.get("attention")
            if attention is None:
                continue
            trigger = (stage.get("observation") or {}).get("trigger_event_id")
            entry: dict[str, Any] = {"request_id": request_id, "trigger": trigger, "model": (self.ctx.attention or {}).get("model")}
            if "error" in attention:
                entry["error"] = f"{attention['error'].get('code')}: {attention['error'].get('detail')}"
            else:
                entry["disposition"] = attention.get("effective_disposition")
                entry["served"] = {"provider": "scripted"}
            self.attention_calls.append(entry)

    def collect(self) -> None:
        self.copy_state()
        self.read_turns()
        if self.participant_endpoint is not None:
            write_json(self.ctx.out / "transcript" / "scripted-participant.json", self.participant_endpoint.answers)
        audits = delivery_audits(self.discord.state)
        outcomes: dict[str, int] = {}
        for audit in audits:
            outcomes[str(audit.get("outcome"))] = outcomes.get(str(audit.get("outcome")), 0) + 1
        sent = sum(1 for item in self.committed if item.get("delivery") == "sent")
        self.reports["reference"] = {
            "verdict": (
                f"nunchi-discord took {len(self.invocations)} turn(s) through the scripted participant and delivered {sent} action(s)"
                if self.invocations
                else "no turn reached the scripted participant"
            ),
            "participant_calls": sum(turn.get("calls", 0) for turn in self.invocations),
            "observations": outcomes,
            "stream_gaps": [audit.get("delivery_id") for audit in audits if audit.get("outcome") == "continuity-gap"],
        }

    def room_effects(self) -> list[dict[str, Any]]:
        return self.discord.effects()

    def judge(self, moments: Sequence[dict[str, Any]]) -> None:
        answers = self.participant_endpoint.answers if self.participant_endpoint else ()
        received = {answer["received"]["trigger"]: answer["received"] for answer in answers if answer.get("received")}
        judge_discord_moments(self, moments, received)

    def scripted_check(self, moments: Sequence[Mapping[str, Any]]) -> Check:
        return checks_module.discord_scripted_outcomes(moments, EXPECTED, pins=self.pins)

    def room_checks(self, document: Mapping[str, Any]) -> list[Check]:
        expected = {self.discord.agent: {"chunk": True, "calls": self.expected_calls}}
        return self.discord.checks(self.committed, expected=expected, gaps_fail=False, moments=document["moments"])

    def room_record(self) -> dict[str, Any]:
        return {"discord": self.discord.record()}

    def close(self) -> None:
        try:
            self.discord.close()
        finally:
            if self.participant_endpoint is not None:
                self.participant_endpoint.close()


# -- Hermes: `hermes gateway run` in its own process, with the Nunchi plugin ----------------------------

HERMES = "hermes"
# The plugin's actor ids read ``discord:user:<id>``, not the shared transport's ``discord:actor:<id>``.
HERMES_ACTOR = "discord:user"
HERMES_KEY_ENV = "OPENROUTER_API_KEY"
# What Hermes's model posts at each graded moment: its final answer, in the channel, as a plain message
# (no Discord reply, whatever the moment is called); a reaction is the one move made with a room tool.
HERMES_EXPECTED = {
    "post": {"kind": "message", "text": SCRIPTED_ANSWER},
    "reply": {"kind": "message", "text": SCRIPTED_REPLY},
    "reaction": {"kind": "reaction", "reaction": REACTION},
    "thread-reply": {"kind": "message", "text": SCRIPTED_THREAD_REPLY},
}
HERMES_PINS = {"first-message": REACHED, "thread": REACHED}
# The known gap the thread question pins (integrations/hermes-plugin/README.md, Known gaps): Hermes posts the
# final answer where the run started, and the plugin starts every run in the main channel. The note is shown
# when that moment misses (`checks.discord_scripted_outcomes`): its reply would read this way too if it landed
# in the thread.
HERMES_NOTES = {
    "thread-question": "Hermes posts its answer in the main channel, a gap the README names; an answer that landed in the "
    "thread would read like this too: update the pin and its docs"
}
# The plain-message pin: Hermes posts its final answer as a plain message, never a Discord reply. An answer
# the wire shows as a reply fails with this note.
HERMES_REPLY_NOTE = "Hermes now replies: update the plain-message pin and the docs"
# Every call Hermes is shown to make on the stand-in (each has a route of its own there): its login, its capability read
# (`tools/discord_tool.py`), the slash-command sync (`GET` then one `POST` per command), the history it backfills for a
# reply or a thread message, the message it fetches to react to, and the agent's post and reaction.
HERMES_CALLS = (
    "GET /users/@me",
    "GET /applications/@me",
    "GET /applications/{application}/commands",
    "POST /applications/{application}/commands",
    "GET /channels/{channel}/messages",
    "GET /channels/{channel}/messages/{message}",
    POST,
    REACT,
)
# Python run in Hermes's own Python, from the checkout, before its home has a config: which Hermes this is, the
# auxiliary tasks its config has (`routes.hermes_auxiliary_tasks`), and the config version `hermes setup` stamps (a
# config without it is taken for a two-year-old one at boot). Prints one JSON line.
HERMES_INSTALL_FACTS = (
    "import json, sys\n"
    "from evals.rehearsal.probe import hermes_install\n"
    "from evals.rehearsal.routes import hermes_auxiliary_tasks\n"
    "from hermes_cli.config import DEFAULT_CONFIG\n"
    "print(json.dumps({'install': hermes_install(sys.argv[1]), 'auxiliary_tasks': hermes_auxiliary_tasks(),\n"
    "                  'config_version': DEFAULT_CONFIG.get('_config_version')}))\n"
)
# The same, once Hermes has run: what Hermes's own builders give the agent's terminal and its other children in
# exactly Hermes's environment, and the terminal backend its config names (`probe.HermesLeg.record_environments`).
HERMES_ENVIRONMENT_FACTS = (
    "import json, os\n"
    "facts = {}\n"
    "try:\n"
    "    from tools.environments import local\n"
    "    facts['terminal'] = local._make_run_env({})\n"
    "    facts['children'] = local._sanitize_subprocess_env(dict(os.environ))\n"
    "except Exception as exc:\n"
    "    facts['builders_error'] = f'{type(exc).__name__}: {exc}'[:300]\n"
    "try:\n"
    "    from hermes_cli.config import load_config\n"
    "    facts['backend'] = (load_config().get('terminal') or {}).get('backend') or 'local'\n"
    "except Exception as exc:\n"
    "    facts['backend_error'] = f'{type(exc).__name__}: {exc}'[:300]\n"
    "print(json.dumps(facts))\n"
)


def hermes_argv(python: str) -> list[str]:
    """`hermes gateway run` as a user starts it: the console script beside the Python, else its own body."""

    script = Path(python).with_name("hermes")
    if script.is_file():
        return [str(script), "gateway", "run"]
    return [python, "-c", "import sys; sys.argv[0] = 'hermes'; from hermes_cli.main import main; sys.exit(main())", "gateway", "run"]


# `nunchi.participant.DELIVERED_EVENT_PREFIX`, as the room log spells it.
DELIVERED_PREFIX = "nunchi:delivered:"


def delivered_messages(state: Path) -> dict[str, dict[str, Any]]:
    """The messages the harness posted that the library put in the room log, by the turn's request id.

    When the harness delivers a final answer itself, the library records it in the participant's own
    observations as a message of its own, in reply to the message the turn was about
    (``nunchi:delivered:<request_id>``, `nunchi.participant.DELIVERED_EVENT_PREFIX`): the one place outside
    the plugin's process that holds what the turn committed.
    """

    return {event_id[len(DELIVERED_PREFIX):]: event for event_id, event in room_events(state).items() if event_id.startswith(DELIVERED_PREFIX)}


class HermesGatewayLeg(Leg):
    """Hermes's real gateway process, unmodified, with the Nunchi plugin, on the Discord stand-in.

    The plugin runs inside Hermes's process, so the probe sees none of its objects: its evidence is
    outside it. The turns, their wake and their end come from the participant's receipts, the committed
    text from the library's own record of the message Hermes delivered (none is a hard problem), a
    reaction's emoji and target from the wire (the library records none), and what landed in the room
    from the stand-in's wire. The scripted endpoint says what the model was asked and only counts its
    calls. Whether a turn was bound to its wake cannot be seen from outside: a turn counts as bound when
    the plugin's hooks brought it to its result (a delivery or a silence), which only a bound run can do.
    """

    harness = HERMES
    harness_posts = True
    script = SCRIPT
    pins: Mapping[str, str] = HERMES_PINS
    expected_calls = HERMES_CALLS

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self.discord = DiscordRoom(ctx, HERMES, actor=HERMES_ACTOR)
        self.agent: ScriptedHermesAgent | None = None
        self.process: DiscordProcess | None = None
        self.home: Path | None = None
        self.facts: dict[str, Any] = {}
        self._spec: MomentSpec | None = None

    @property
    def room(self) -> Any:
        return None

    # -- starting Hermes -------------------------------------------------------------------------

    def run_facts(self, script: str, env: Mapping[str, str], *args: str) -> dict[str, Any]:
        """Run ``script`` in Hermes's Python with ``env``, from the checkout; the one JSON line it prints."""

        argv = [self.discord.python, "-c", script, *args]
        done = subprocess.run(argv, env=dict(env), cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
        try:
            return dict(json.loads(done.stdout.strip().splitlines()[-1]))
        except (ValueError, IndexError, TypeError) as exc:
            raise CouldNotRun(
                f"Hermes cannot be read in {self.discord.python} (hermes-agent[messaging] installed?): exit {done.returncode}: "
                f"{' | '.join(done.stderr.strip().splitlines()[-3:])[-400:] or exc}"
            ) from exc

    def own_environment(self) -> dict[str, str]:
        """What Hermes gets beside the path, locale and fresh HOME and TMPDIR: its home, its bot's token, and its model key and canary.

        The token goes in the environment and never in a file, so no recorded config holds it. The model
        key is the run's placeholder, which Hermes and the plugin's attention both read under its name,
        and the canary is in every harness's environment (`routes.CANARY_ENV`).
        """

        assert self.discord.fd is not None and self.home is not None
        return {
            "HERMES_HOME": str(self.home),
            "DISCORD_BOT_TOKEN": self.discord.fd.token(self.discord.agent),
            HERMES_KEY_ENV: self.ctx.env[HERMES_KEY_ENV],
            CANARY_ENV: self.ctx.env[CANARY_ENV],
        }

    def write_home(self, config_path: Path, auxiliary_tasks: Sequence[str], config_version: Any = None) -> None:
        """The room's Hermes profile, as integrations/hermes-plugin/README.md says to set it up.

        ``config.yaml`` has the README's room settings (`hermes_plugin_conformance.room_settings`: display,
        the ``discord:`` block with the bound channel as a free-response channel, sessions, disabled
        toolsets) beside the probe's peer-agent settings and the scripted model; ``.env`` has the room's
        role and no user allowlist, the turns' identity and no text batching. The plugin directory is
        copied where ``hermes plugins install`` puts it.
        """

        import nunchi.integrations.hermes_plugin as package
        from nunchi.integrations import hermes_plugin_conformance as kit

        assert self.home is not None and self.agent is not None and self.discord.fd is not None
        plugin = self.home / "plugins" / kit.PLUGIN_NAME
        shutil.copytree(Path(package.__file__).parent, plugin, ignore=shutil.ignore_patterns("__pycache__"))
        work = self.ctx.base / "work"
        work.mkdir(parents=True, exist_ok=True)
        settings = kit.room_settings("discord", channel=self.room_id)
        settings["discord"] = {**settings["discord"], **HERMES_PEER_AGENTS}
        config = {
            **hermes_model_config(self.ctx.route.model, auxiliary_tasks, scripted_base_url=self.agent.base_url),
            "plugins": {
                "enabled": [kit.PLUGIN_NAME],
                "entries": {
                    kit.PLUGIN_NAME: {"allow_gateway_injection": True, "allow_platform_actions": True, "settings": {"config_path": str(config_path)}}
                },
            },
            **settings,
            # The plugin's tools are shown to the model directly (the README: tool_search off also works).
            "tools": {"tool_search": {"enabled": "off"}},
            # The agent's terminal starts in a fresh directory, not the checkout or the home.
            "terminal": {"cwd": str(work)},
        }
        if config_version:
            config["_config_version"] = config_version
        (self.home / "config.yaml").write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
        environment = {**kit.room_env("discord"), "DISCORD_ALLOWED_ROLES": self.discord.fd.world.role("room").id}
        (self.home / ".env").write_text("".join(f"{name}={value}\n" for name, value in environment.items()), encoding="utf-8")
        self.configs.append(("hermes config.yaml", self.home / "config.yaml"))
        self.configs.append(("hermes profile .env", self.home / ".env"))

    def prepare(self) -> None:
        self.discord.start()
        self.room_id = self.discord.channel_id
        self.actor_id = f"{HERMES_ACTOR}:{self.discord.agent_id}"
        self.scope = f"discord:{self.room_id}"
        self.home = Path(self.ctx.homes["HERMES_HOME"])
        self.agent = ScriptedHermesAgent(SCRIPTED_ANSWER, script=self.script)
        self.ctx.route = replace(self.ctx.route, base_url=self.agent.base_url)
        env, _ = self.discord.environment(HERMES, {"HERMES_HOME": str(self.home)})
        self.facts = self.run_facts(HERMES_INSTALL_FACTS, env, self.ctx.options.expect_version or PINS[HERMES])
        self.install = dict(self.facts["install"])
        self.ran(
            "Hermes's version and its source tree's commit (git rev-parse HEAD), for the record",
            [self.discord.python, "-c", HERMES_INSTALL_FACTS, self.ctx.options.expect_version or PINS[HERMES]],
            env,
        )
        _, config_path = self.room_config({"hermes": hermes_section(self.room_id)})
        self.write_home(config_path, self.facts["auxiliary_tasks"], self.facts.get("config_version"))
        from nunchi.integrations.hermes_plugin import plugin as plugin_module
        from nunchi.integrations.hermes_plugin_conformance import HERMES_KNOWN_GAPS

        self.tool_names = list(plugin_module.TOOL_NAMES.values())
        self.known_gaps = [replace(gap, scenarios=(PROBE_SCENARIO,)) for gap in HERMES_KNOWN_GAPS]
        self.install["plugin_version"] = _plugin_version(Path(plugin_module.__file__).with_name("plugin.yaml"))
        process = self.discord.launch(
            HERMES, self.own_environment(), own_keys=[HERMES_KEY_ENV, "DISCORD_BOT_TOKEN", CANARY_ENV], argv=hermes_argv(self.discord.python)
        )
        self.process = process
        self.actual_homes = {name: process.env[name] for name in ("HOME", "TMPDIR", "HERMES_HOME")}
        self.discord.wait_ready(process, self.discord.agent)
        self.wait_connected(process)

    def wait_connected(self, process: DiscordProcess, *, timeout: float = 120.0) -> None:
        """Until Hermes's own record (``gateway_state.json``) says the gateway is running with its Discord adapter connected.

        Hermes writes that when the adapter connects, before its inbound gate opens: a message that comes in
        then is queued ("Queued inbound message during gateway startup restore" in ``gateway.log``) and handled
        about a second later, once the restore ends. The wait keeps the first moment from starting on a gateway
        that is still connecting; the queueing is covered by the reach budget (``REACH_SECONDS``), not by this wait.
        """

        assert self.home is not None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not process.alive():
                raise RuntimeError(f"hermes gateway run exited ({process.process.poll() if process.process else '?'}) before it connected: {process.tail()}")
            try:
                state = json.loads((self.home / "gateway_state.json").read_text(encoding="utf-8"))
                if state.get("gateway_state") == "running" and ((state.get("platforms") or {}).get("discord") or {}).get("state") == "connected":
                    return
            except (OSError, ValueError, AttributeError):
                pass
            time.sleep(0.5)
        raise RuntimeError(f"Hermes never reported its gateway running with Discord connected within {timeout:.0f} s: {process.tail()}")

    # -- the moments -------------------------------------------------------------------------------

    def deliver(self, raw: Mapping[str, Any], at: datetime, scene: Scene, sequence: int) -> dict[str, Any]:
        assert self._spec is not None
        return self.discord.reach(self.discord.post(raw, at, scene, self._spec))

    def play(self, spec: MomentSpec, *, settle_seconds: float) -> dict[str, Any]:
        self._spec = spec
        if spec.reconnect_before:
            self.discord.reconnect()
        moment = play_moment(self, spec, settle_seconds=settle_seconds)
        if spec.thread:
            moment["thread"] = spec.thread
        if spec.reconnect_before:
            self.discord.reconnected(moment)
        # Hermes runs in its own process: its turns are read from outside it after each moment.
        self.read_turns()
        moment["turns"] = [turn for turn in self.invocations if turn.get("moment") == spec.name or turn.get("moment") is None]
        for turn in moment["turns"]:
            turn["moment"] = spec.name
        graded = [turn for turn in moment["turns"] if turn.get("trigger") == moment["graded_event"]]
        moment["graded_turns"] = len(graded)
        moment["graded_wake_sources"] = [turn.get("source") for turn in graded]
        moment["other_turns"] = len(moment["turns"]) - len(graded)
        if spec.name == "first-message":
            self.discord.start_gap = self.start_facts()
        return moment

    def start_facts(self) -> dict[str, Any]:
        """What the plugin said of its start: a continuity gap in the participant's audit, or the coverage of its first snapshot.

        The shared transport and the reference declare a gap when they start. The plugin does not: its room is
        built on the first admitted message, and the first snapshot reports the participant's own log as
        restart-safe, with no restart gap.
        """

        gaps = [audit for audit in delivery_audits(self.discord.state) if audit.get("outcome") == "continuity-gap"]
        first = next((stage["observation"] for stage in self.stages().values() if stage.get("observation")), {})
        coverage = first.get("coverage") or {}
        return {
            "process": "hermes gateway run",
            "gap": gaps[0]["delivery_id"] if gaps else None,
            "declared": bool(gaps),
            "detail": (
                "the plugin declared a continuity gap when it started" if gaps
                else "the plugin declares no gap when it starts: its first snapshot reports continuity "
                f"{coverage.get('continuity')!r}, has_gaps {coverage.get('has_gaps')}, has_restart_gap {coverage.get('has_restart_gap')}"
            ),
        }

    def open_turns(self) -> list[str]:
        """Turns attention woke that the host has not ended yet: a receipt for the wake, none for the host."""

        stages = self.stages()
        return [
            request_id
            for request_id, stage in stages.items()
            if (stage.get("attention") or {}).get("effective_disposition") not in (None, "SUPPRESS") and "participant-host" not in stage
        ]

    def settle(self, timeout: float) -> bool:
        """Until no turn is open and nothing moved for 2 s: the wire, both scripted endpoints, and the plugin's files."""

        deadline = time.monotonic() + timeout
        last: Any = None
        since = time.monotonic()
        while time.monotonic() < deadline:
            mark = (
                len(self.agent.model.requests) if self.agent else 0,
                len(getattr(self.ctx.attention_endpoint, "judged", ())),
                self._written(),
            )
            if mark != last:
                last, since = mark, time.monotonic()
            if time.monotonic() - since >= 2.0 and not self.open_turns() and self.discord.quiet(2.0):
                return True
            time.sleep(0.2)
        return False

    def _written(self) -> int:
        total = 0
        for path in self.discord.state.glob("*.jsonl"):
            with contextlib.suppress(OSError):
                total += path.stat().st_size
        return total

    # -- what is read from outside the process ---------------------------------------------------------

    def receipts(self) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for path in sorted(self.discord.state.glob("*receipts.jsonl")):
            found += read_jsonl(path)
        return found

    def stages(self) -> dict[str, dict[str, Any]]:
        stages: dict[str, dict[str, Any]] = {}
        for receipt in self.receipts():
            stages.setdefault(receipt["request_id"], {})[receipt["stage"]] = receipt.get("body") or {}
        return stages

    def read_turns(self) -> None:
        """The turns, committed actions and attention calls, from the participant's receipts and the library's own record.

        A turn is a request the host invoked the harness for. Its result is a silence (the host's outcome), a
        message (the transport receipt says the harness delivers it; the text is what the library recorded
        as delivered, and with no record it is missing: a hard problem, never the scripted model's text) or a
        reaction (Hermes's other transport, which adds it). A reaction's emoji and target are in neither the
        receipt nor the library's record, which keeps none (README, Known gaps), so they are what Hermes put on
        the wire, the nth reaction for the nth reaction turn; the scripted model's arguments are never used.
        Each action's delivery is the transport receipt's.
        """

        from nunchi.participant import HARNESS_DELIVERS

        stages = self.stages()
        delivered = delivered_messages(self.discord.state)
        reactions = [write for write in wire_writes(self.discord.records, self.discord.agent) if write["kind"] == "reaction" and not write["removed"]]
        known = {turn["request_id"]: turn for turn in self.invocations}
        committed = {item["request_id"]: item for item in self.committed}
        reacted = 0
        for request_id, stage in stages.items():
            host = stage.get("participant-host")
            if host is None or not host.get("invoked"):
                continue
            trigger = (stage.get("observation") or {}).get("trigger_event_id")
            transport = stage.get("transport")
            result: dict[str, Any] | None
            item: dict[str, Any] | None = None
            if transport is not None and transport.get("detail") == HARNESS_DELIVERS:
                event = delivered.get(request_id)
                item = {
                    "kind": "message",
                    "text": event.get("text") if event else None,
                    "origin_event_id": (event or {}).get("reply_to_event_id") or trigger,
                    "text_from": "the library's record of the delivered message" if event else "missing: the library holds no record of it",
                }
            elif transport is not None:
                write = reactions[reacted] if reacted < len(reactions) else {}
                reacted += 1
                item = {
                    "kind": "reaction",
                    "reaction": write.get("emoji"),
                    "target_event_id": f"discord:message:{write['message_id']}" if write else None,
                    "operation": "add",
                    "reaction_from": "the wire: neither the receipt nor the library's record names it" if write else "missing: no reaction on the wire",
                }
            if item is not None:
                result = {key: item[key] for key in ("kind", "text", "reaction", "target_event_id") if key in item}
            elif host.get("outcome") == "silent":
                result = {"kind": "silence"}
            else:
                result = None
            turn = known.get(request_id)
            if turn is None:
                turn = {"request_id": request_id, "trigger": trigger, "source": host.get("wake_source"), "moment": None}
                self.invocations.append(turn)
            turn.update(
                {
                    "calls": sum(1 for entry in (self.agent.moves if self.agent else ()) if entry["trigger"] == trigger),
                    # Not seen, only inferred: only a run bound to its wake reaches the plugin's result.
                    "bound": result is not None,
                    "bound_evidence": "inferred from the receipts: the turn ended in a delivery or a silence through the plugin's hooks",
                    "result": result,
                }
            )
            if item is not None:
                action = {"request_id": request_id, **item, "delivery": transport.get("delivery"), "detail": transport.get("detail")}
                if request_id in committed:
                    # Read again: the record or the write may have come after the earlier read.
                    committed[request_id].update(action)
                else:
                    committed[request_id] = action
                    self.committed.append(action)
        # What the transport receipt says Hermes delivered, the library must hold: no fallback to the scripted model's words.
        self.harness_failures = [
            f"turn {item['request_id']}: the transport receipt says Hermes delivered its answer, but the library's room log "
            f"holds no record of it ({DELIVERED_PREFIX}{item['request_id']})"
            for item in self.committed
            if item.get("kind") == "message" and item.get("text") is None
        ]
        self.attention_calls = []
        for request_id, stage in stages.items():
            attention = stage.get("attention")
            if attention is None:
                continue
            trigger = (stage.get("observation") or {}).get("trigger_event_id")
            entry: dict[str, Any] = {"request_id": request_id, "trigger": trigger, "model": (self.ctx.attention or {}).get("model")}
            if "error" in attention:
                entry["error"] = f"{attention['error'].get('code')}: {attention['error'].get('detail')}"
            else:
                entry["disposition"] = attention.get("effective_disposition")
                entry["served"] = {"provider": "scripted"}
            self.attention_calls.append(entry)

    def stop_hermes(self) -> None:
        if self.process is not None and self.process.process is not None:
            self.process.stop()

    def collect(self) -> None:
        """Stop Hermes, then copy what it left: the plugin's state, Hermes's sessions, logs and ``state.db``."""

        self.stop_hermes()
        self.copy_state()
        self.read_turns()
        if self.home is None:
            return
        if self.process is not None:
            self.record_environments()
        copied = copy_tree(self.home / "sessions", self.ctx.out / "transcript" / "hermes-sessions")
        copied += copy_tree(self.home / "logs", self.ctx.out / "transcript" / "hermes-logs")
        # Hermes keeps its sessions in state.db, which is deleted with the run's home.
        try:
            state = sqlite_tables(self.home / "state.db", HERMES_STATE_TABLES)
        except Exception as exc:
            state = {"error": [{"error": f"{type(exc).__name__}: {exc}"}]}
        write_json(self.ctx.out / "transcript" / "hermes-state.json", state)
        usage = [row for row in state.get("session_model_usage", ()) if isinstance(row, Mapping)]
        calls = sum(int(row.get("api_call_count") or 0) for row in usage)
        sent = sum(1 for item in self.committed if item.get("delivery") in ("sent", "unknown"))
        records = self.discord.records
        report: dict[str, Any] = {
            "verdict": (
                f"hermes gateway run took {len(self.invocations)} turn(s) through the plugin and committed {sent} action(s); "
                f"its session records {calls} model call(s)"
            ),
            "sandbox": self.sandbox,
            "model_calls_in_session": calls,
            "transcript_files": [*copied, "hermes-state.json"],
            "typing": typing_calls(records, self.discord.agent),
            "commands_registered": sum(
                1 for r in records if r.get("kind") == "http" and r.get("bot") == self.discord.agent and r.get("method") == "POST" and r.get("route") == "/applications/{application}/commands"
            ),
            "evidence": "outside the process: the plugin's receipts and observations and the stand-in's wire; binding is inferred; "
            "Hermes's state.db is recorded for reading and no check reads it",
        }
        if self.agent is not None:
            report["scripted_model"] = {"agent_requests": len(self.agent.requests()), "moves": len(self.agent.moves)}
            write_json(self.ctx.out / "transcript" / "scripted-model-requests.json", self.agent.requests())
        self.reports[HERMES] = report

    def record_environments(self) -> None:
        """Hermes's environment, and what Hermes's own builders give the agent's commands in exactly that environment."""

        assert self.process is not None
        # Hermes's own process is recorded with the Discord room's (`DiscordProcess.document`): it holds its bot's token.
        try:
            facts = self.run_facts(HERMES_ENVIRONMENT_FACTS, self.process.env)
        except CouldNotRun as exc:
            self.processes.append({"process": "the agent's terminal", "agent_shell": True, "error": str(exc)[:300]})
            return
        if "builders_error" in facts:
            self.processes.append({"process": "the agent's terminal", "agent_shell": True, "error": facts["builders_error"]})
        else:
            self.runs_in("the agent's terminal and code tools (Hermes's _make_run_env)", facts["terminal"], agent_shell=True)
            self.runs_in("Hermes's background and other children (Hermes's _sanitize_subprocess_env)", facts["children"], agent_shell=True)
        backend = facts.get("backend")
        self.sandbox = (
            {"on": None, "detail": f"Hermes's terminal backend could not be read: {facts.get('backend_error')}"}
            if backend is None
            else {
                "on": backend != "local",
                "detail": f"Hermes's terminal backend is {backend}" + (": the agent's commands run as this user, unsandboxed" if backend == "local" else ""),
                "terminal_backend": backend,
            }
        )

    # -- judging and checking ----------------------------------------------------------------------------

    def room_effects(self) -> list[dict[str, Any]]:
        return self.discord.effects()

    def judge(self, moments: Sequence[dict[str, Any]]) -> None:
        judge_discord_moments(self, moments, received_triggers(self.agent.requests() if self.agent else ()))

    def scripted_check(self, moments: Sequence[Mapping[str, Any]]) -> Check:
        return checks_module.discord_scripted_outcomes(moments, HERMES_EXPECTED, pins=self.pins, notes=HERMES_NOTES, reply_note=HERMES_REPLY_NOTE)

    def room_checks(self, document: Mapping[str, Any]) -> list[Check]:
        expected = {self.discord.agent: {"chunk": True, "calls": self.expected_calls}}
        # The known gaps of the plugin and Hermes, pinned as they are (README, Known gaps): the plugin declares no gap
        # when it starts, a reply to the agent's answer has no target in the room log, and the agent's own reaction is
        # not remembered. It marks no gap after a reconnect either, so one that appears fails. Each fails the lane
        # when it changes, until the pin and its docs are updated.
        return self.discord.checks(
            self.committed,
            expected=expected,
            gaps_fail=True,
            moments=document["moments"],
            start_required=None,
            reply_resolves=False,
            own_reaction_remembered=False,
        )

    def room_record(self) -> dict[str, Any]:
        return {"discord": self.discord.record()}

    def close(self) -> None:
        try:
            self.stop_hermes()
            self.discord.close()
        finally:
            if self.agent is not None:
                self.agent.close()


LEGS: dict[str, type[Leg]] = {"claude-code": DiscordClaudeCodeLeg, "codex": DiscordCodexLeg, REFERENCE: ReferenceLeg, HERMES: HermesGatewayLeg}
