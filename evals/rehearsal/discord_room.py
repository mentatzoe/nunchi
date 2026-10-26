"""Standalone Discord reference participant on the Discord stand-in.

The launcher maps Discord's real names to a private test server. The reference
runs nunchi-discord in its own process. Scripted or live participant calls,
attention, room events and receipts are recorded. This is reference adapter
evidence, not a rehearsal of an installed agent harness.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import contextlib
from dataclasses import replace
from datetime import datetime, timezone
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
from evals.behavior.score import visible_result

from . import checks as checks_module
from . import directed
from .checks import PROBE_SCENARIO, REACHED, Check
from .discord_net import ENV as NET_ENV
from .fake_discord.control import FakeDiscord
from .probe import PARTICIPANT, REFERENCE, ROOT, SCENES, SCRIPTED_ANSWER, Context, CouldNotRun, Leg, MomentSpec, _env_names, _summarize_action, play_moment
from .record import copy_tree, write_json
from nunchi.attention import ParticipantProfile
from nunchi.participant_model import OpenAICompatibleParticipant, ParticipantModelError, participant_turn_prompt
from .routes import ATTENTION_KEY_ENV, CANARY_ENV, OPENROUTER, OUTPUT_KEY_ENV, PARTICIPANT_KEY_ENV, PASSTHROUGH_ENV, Route
from .standin import SCENE_WORD, RoomScript, ScriptedParticipant, received_triggers, timestamp

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
# How long the reference's host waits for its participant model's answer. A scene's held turn is held at that model endpoint, so
# `standin.HOLD_SECONDS` stays under it.
PARTICIPANT_TIMEOUT_SECONDS = 30
# A live scene's participant model is a real one and may think for a while; the reference's host waits this long for its answer.
LIVE_PARTICIPANT_TIMEOUT_SECONDS = 120
# A live reference is quiet when its receipts and the wire have not moved for this long and no request is open (`ReferenceLeg.settle`).
LIVE_QUIET_SECONDS = 4.0
# A host receipt that says it handed an action to the room is followed by the transport's receipt; this long after it, none is expected.
TRANSPORT_GRACE_SECONDS = 15.0
BOT_TOKEN_ENV = "DISCORD_BOT_TOKEN"

# The console scripts, run as their entry points do: ``main`` from the same module.
CONSOLE_SCRIPTS = {
    "nunchi-mcp-discord": "nunchi.mcp_discord.server",
    "nunchi-discord": "nunchi.adapters.discord",
}
# What each process runs on, recorded from its own Python and environment: the transport's
# mcp-discord extra and the reference's discord.py.
PACKAGES = {"nunchi-mcp-discord": ("mcp",), "nunchi-discord": ("discord.py", "aiohttp")}
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


# The calls a transport column makes whatever the script does: it looks up the channel, the member and the roles of what it routes.
TRANSPORT_ALWAYS = tuple(call for call in TRANSPORT_CALLS if call not in (POST, REACT))


def directed_calls(
    moments: Sequence[Mapping[str, Any]], always: Sequence[str] = ("GET /users/@me",), *, live: bool = False
) -> tuple[str, ...]:
    """The calls a column must make in a directed scene: ``always`` (the reference's login by default), and a post or a reaction where the script makes one, in a graded moment or as an earlier line of the agent's.

    A live agent decides for itself, so a live scene requires only ``always``.
    """

    if live:
        return tuple(always)
    scripted = {item.get("scripted") for moment in moments if moment.get("expect") == "directed" for item in moment.get("graded", ())}
    # The agent's own earlier lines are made too: a post or a reply where the scene has it say something, a reaction where it nodded.
    earlier = {line.get("kind") for moment in moments if moment.get("expect") == "directed" for line in moment.get("lines", ())}
    posts = "speak" in scripted or bool(earlier & {"message", "reply"})
    reacts = "mhm" in scripted or "reaction" in earlier
    return (*always, *((POST,) if posts else ()), *((REACT,) if reacts else ()))


# The transport journal's outcomes that mean a gap (`nunchi.mcp_discord.server.TransportAuditJournal`).
TRANSPORT_GAP_OUTCOMES = ("source-gap", "gap-signal", "queue-rejected", "client-delivery-lost", "shutdown-lost")
# How long a posted message may take to reach Nunchi before it reads as not delivered.
REACH_SECONDS = 8.0
# A live scene allows longer for startup. A message that never reaches Nunchi fails the run.
LIVE_REACH_SECONDS = 60.0
# The one call the live reference makes before it starts (`ReferenceLeg.preflight`): how long the provider has to answer it.
PREFLIGHT_SECONDS = 60.0


def reference_route(agent_model: str | None = None) -> Route:
    """The reference's model route, its key by name.

    Scripted, the participant is a plain-call endpoint of the probe's (set once
    it starts). Given ``agent_model`` (a live scene), it is that model through
    OpenRouter's chat completions.
    """

    if agent_model is None:
        return Route(REFERENCE, "scripted-participant", secret_env=(PARTICIPANT_KEY_ENV,), base_url="(the scripted participant)")
    return Route(REFERENCE, agent_model, secret_env=(PARTICIPANT_KEY_ENV,), base_url=OPENROUTER)


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


def require_online(net: Mapping[str, Any]) -> None:
    """A live scene needs the launcher as a CI runner runs it: with the host's network (the model providers are on it), not ``--offline``.

    The probe refuses a live scene off a CI runner before it starts
    (`probe.live_scene_refusal`); this is the launcher's own record of the same,
    so a live scene started inside an offline launcher (where no model could be
    reached, and every call would fail) or one that never saw a runner stops
    before any process starts.
    """

    if net.get("offline"):
        raise CouldNotRun("a live scene needs the launcher without --offline: the model providers are not on loopback")
    if not net.get("ci"):
        raise CouldNotRun("a live scene runs only where the launcher saw a GitHub Actions runner (CI=true and GITHUB_ACTIONS=true; a runner is discarded after its job)")


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


def _wire_write_pairs(records: Sequence[Mapping[str, Any]], bot: str) -> list[tuple[Mapping[str, Any], dict[str, Any]]]:
    """The bot's 2xx writes on the wire, each with the wire record it was read from."""

    writes: list[tuple[Mapping[str, Any], dict[str, Any]]] = []
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
                (
                    record,
                    {
                        "kind": "message",
                        "content": body.get("content"),
                        "reply_to": str(reference["message_id"]) if reference.get("message_id") else None,
                        "message_id": response.get("id"),
                        "channel_id": parts[4] if len(parts) > 4 else None,
                    },
                )
            )
        elif str(record.get("route", "")).endswith("/reactions/{emoji}/@me") and len(parts) > 8:
            writes.append(
                (
                    record,
                    {
                        "kind": "reaction",
                        "emoji": parts[8],
                        "message_id": parts[6],
                        "channel_id": parts[4],
                        "removed": record.get("method") == "DELETE",
                    },
                )
            )
    return writes


def wire_writes(records: Sequence[Mapping[str, Any]], bot: str) -> list[dict[str, Any]]:
    """The bot's 2xx writes on the wire: each message with its content and reply target, each reaction with its emoji and message."""

    return [write for _, write in _wire_write_pairs(records, bot)]


def wire_write_times(records: Sequence[Mapping[str, Any]], bot: str) -> list[str | None]:
    """When the stand-in saw each of `wire_writes`, in the same order."""

    return [record.get("at") for record, _ in _wire_write_pairs(records, bot)]


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


def stages_by_request(receipts: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Each request's receipts by stage: ``{request_id: {stage: body}}``."""

    stages: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        stages.setdefault(receipt["request_id"], {})[receipt["stage"]] = receipt.get("body") or {}
    return stages


def attention_entries(
    stages: Mapping[str, Mapping[str, Any]], model: Any, *, evidence: bool, provider: str = "scripted"
) -> list[dict[str, Any]]:
    """Attention's decision for each request, from the participant's own receipts: the trigger, the disposition, and the evidence it cited.

    The reference reads them from its state directory in its own process.
    ``evidence`` (a scene) adds the message ids
    attention's reading points at (`directed.judge_scene` reads them as ``cited``).
    """

    found: list[dict[str, Any]] = []
    for request_id, stage in stages.items():
        attention = stage.get("attention")
        if attention is None:
            continue
        trigger = (stage.get("observation") or {}).get("trigger_event_id")
        entry: dict[str, Any] = {"request_id": request_id, "trigger": trigger, "model": model}
        if "error" in attention:
            entry["error"] = f"{attention['error'].get('code')}: {attention['error'].get('detail')}"
            if attention.get("wake_action"):
                entry["wake_action"] = attention["wake_action"]
        else:
            entry["disposition"] = attention.get("effective_disposition")
            entry["served"] = {"provider": provider}
            if evidence:
                entry["evidence"] = list(attention.get("evidence_event_ids") or ())
        found.append(entry)
    return found


def word_nod_checks(spec: Any, committed: Sequence[Mapping[str, Any]]) -> list[Check]:
    """The check of a scene played with the agent's nod first a word (``--nod-with-a-word-first``); none for any other scene."""

    script = spec.script
    if not script.word_first:
        return []
    return [checks_module.word_nod_refused(tried=script.words_tried, refused=script.words_refused, committed=committed, word=SCENE_WORD)]


def judge_directed(leg: Any, moments: Sequence[dict[str, Any]]) -> None:
    """Grade the directed scene(s): note what Nunchi's own room log holds of each message, then `directed.judge_scene`.

    The log holds every message it took in, a turn only some: ``logged`` is
    what `checks.discord_addressing` compares with what the stand-in sent.
    """

    logged = room_events(leg.discord.state)
    for moment in moments:
        if moment.get("expect") != "directed":
            continue
        for delivery in moment.get("deliveries", ()):
            event = logged.get(delivery.get("event_id"))
            if event is not None:
                delivery["logged"] = {
                    "mentioned_actor_ids": list(event.get("mentioned_actor_ids") or ()),
                    "reply_to_event_id": event.get("reply_to_event_id"),
                }
        directed.judge_scene(leg, moment, leg.directed.plan.scene)


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
        # How a person's or bot's id reads in an event.
        self.actor = actor
        self.net = load_net(ctx.original_env)
        if not getattr(ctx.options, "scripted", True):
            require_online(self.net)
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

    def start(self, scenes: Sequence[Scene] | None = None) -> None:
        """Start the stand-in with a world for ``scenes``: the moments' scenes unless given (a directed scene's)."""

        if scenes is None:
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
        if getattr(spec, "expect", None) == "directed":
            # The pings the scene meant, from the scene and not from the text sent (as actor ids): the director's check that
            # the stand-in sent them and that Nunchi saw them (`checks.discord_addressing`). The moments' records are as before.
            delivery["meant_actor_ids"] = [
                f"{self.actor}:{self.fd.world.member(self.members[name]).id}" for name in raw.get("mentions", ())
            ]
        if note:
            delivery["note"] = note
        return delivery

    def reach(self, delivery: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        """Wait until the participant's room audited the message, or ``timeout`` (`REACH_SECONDS`; `LIVE_REACH_SECONDS` in a live run)."""

        if timeout is None:
            timeout = REACH_SECONDS if getattr(self.ctx.options, "scripted", True) else LIVE_REACH_SECONDS
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
        reply_resolves: bool = True,
        reconnects_required: bool = True,
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
            checks_module.discord_continuity(
                self.start_gap, self.reconnects, gaps_fail=gaps_fail, reconnects_required=reconnects_required
            ),
            checks_module.discord_addressing(
                moments,
                agent=f"{self.actor}:{self.agent_id}",
                writes=wire_writes(records, self.agent),
                reply_resolves=reply_resolves,
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
        if moment.get("expect") == "directed":
            continue  # a scene has many graded messages: `directed.judge_scene` grades each
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


# -- the reference, live: its turns read from outside its process -----------------------------------------


def action_of_write(write: Mapping[str, Any]) -> dict[str, Any]:
    """The action a wire write is, as the room records it: a post, a reply (it names the message it answers), or a reaction."""

    if write.get("kind") == "reaction":
        return {
            "kind": "reaction",
            "reaction": write.get("emoji"),
            "target_event_id": f"discord:message:{write.get('message_id')}",
            "operation": "remove" if write.get("removed") else "add",
        }
    if write.get("reply_to"):
        return {"kind": "reply", "text": write.get("content"), "target_event_id": f"discord:message:{write['reply_to']}"}
    return {"kind": "message", "text": write.get("content")}


class LiveTurns:
    """The reference's turns while a live scene runs, read from outside its process: its receipts and the stand-in's wire.

    ``nunchi-discord`` runs in a process of its own, and its model is a real
    one, so nothing of the probe sits between them (no scripted endpoint
    to ask; no recording hop in front of the provider, which would change the
    timing a hold is about). What the probe has is what the library writes and
    what the bot does:

    - each request's receipts (`nunchi.receipts`): observation, attention, the
      participant host's, and the transport's, in that order, read as they are
      appended. They carry no time of their own, so each is stamped when this
      reads it (about every ``interval`` seconds, on a thread of its own once
      started). A request whose attention receipt reads as a wake is a turn
      that will begin (`_wakes`, the earliest signal the reference has); one
      with the host's receipt is a turn that ran, with the host's wake source
      and outcome;
    - the bot's 2xx writes on the wire, which give a delivered action its kind,
      words and target, and the time the stand-in saw it. The transport's
      receipts and the writes are paired in order: the n-th delivery that reads
      ``sent`` is the n-th write. ``discord-writes-reconciled`` then compares
      the count (the content is the wire's own).

    What it cannot read: which messages a turn took as unattended, how many
    model calls a turn made, and what the model was shown. The record says so
    (``ReferenceLeg.model_calls``, ``observes_unattended``).
    """

    def __init__(self, room: DiscordRoom, *, interval: float = 0.1) -> None:
        self.room = room
        self.interval = interval
        self.requests: dict[str, dict[str, Any]] = {}
        self.errors: list[str] = []
        self._order: list[str] = []
        self._transports: list[str] = []
        self._offsets: dict[Path, int] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def _stamp() -> str:
        return timestamp(datetime.now(timezone.utc))

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="nunchi-rehearsal-live-turns", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Read once more, then stop reading: what is read after the run ends is what the record holds."""

        self._stop.set()
        if self._thread is not None:
            self._thread.join(5)
            self._thread = None
        self.poll()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.poll()
            except Exception as exc:  # recorded: a reader that fails leaves the record short, and says so
                with self._lock:
                    self.errors.append(f"{type(exc).__name__}: {exc}"[:300])

    def poll(self) -> None:
        """Read the receipts appended since the last read, stamping each when first read."""

        with self._lock:
            for path in sorted(self.room.state.glob("*receipts.jsonl")):
                try:
                    with open(path, "rb") as handle:
                        handle.seek(self._offsets.get(path, 0))
                        chunk = handle.read()
                except OSError:
                    continue
                complete = chunk.rfind(b"\n") + 1
                self._offsets[path] = self._offsets.get(path, 0) + complete
                for line in chunk[:complete].splitlines():
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(record, dict) and record.get("request_id") and record.get("stage"):
                        self._ingest(record)

    def _ingest(self, record: Mapping[str, Any]) -> None:
        stamp = self._stamp()
        rid, stage = str(record["request_id"]), str(record["stage"])
        body = record.get("body") if isinstance(record.get("body"), Mapping) else {}
        if rid not in self.requests:
            self.requests[rid] = {"stages": {}, "seen": {}, "trigger": None}
            self._order.append(rid)
        request = self.requests[rid]
        request["stages"].setdefault(stage, dict(body))
        request["seen"].setdefault(stage, stamp)
        if stage == "observation":
            request["trigger"] = body.get("trigger_event_id")
        elif stage == "transport":
            self._transports.append(rid)

    @staticmethod
    def _wakes(request: Mapping[str, Any]) -> bool:
        attention = request["stages"].get("attention")
        return attention is not None and visible_result(
            {"status": "error" if "error" in attention else "ok", "effective_disposition": attention.get("effective_disposition"),
             "wake_action": attention.get("wake_action")}
        ) == "woken"

    def _no_turn_coming(self, rid: str) -> bool:
        """A woken request that has no host receipt and will not get one: it was judged for the memory alone.

        The pipeline judges the messages that arrived mid-turn (the ones the
        newest replaced) for the participant's memory before it judges the
        newest (`NunchiV2Pipeline._recall_midturn`): they get an observation
        and an attention receipt, a wake among them, and no turn follows, so no
        host receipt ever. A request is one of those when a later request has
        its attention back (the lane runs one opportunity at a time, so a real
        turn's host receipt comes before the next judgment), or when it is
        older than a host could take; until then it may still be a turn
        about to begin. Call under the lock.
        """

        position = self._order.index(rid)
        if any("attention" in self.requests[later]["stages"] for later in self._order[position + 1 :]):
            return True
        seen = _parse_stamp(self.requests[rid]["seen"].get("attention"))
        return seen is not None and time.time() - seen > LIVE_PARTICIPANT_TIMEOUT_SECONDS + TRANSPORT_GRACE_SECONDS

    def begun(self, event_id: str) -> bool:
        """Whether a turn has begun, or is about to, on ``event_id``: attention's receipt reads as a wake and a turn can follow.

        A message judged for the memory alone while a turn ran (a wake with no
        turn behind it, `_no_turn_coming`) is not a turn that begins.
        """

        self.poll()
        with self._lock:
            return any(
                request["trigger"] == event_id
                and self._wakes(request)
                and ("participant-host" in request["stages"] or not self._no_turn_coming(rid))
                for rid, request in self.requests.items()
            )

    def open_requests(self) -> list[str]:
        """The requests whose receipts are not complete yet: attention not back, a woken turn not ended, or a hand-off not yet attested."""

        self.poll()
        now = time.time()
        found = []
        with self._lock:
            for rid, request in self.requests.items():
                stages = request["stages"]
                attention = stages.get("attention")
                if attention is None:
                    found.append(rid)
                    continue
                host = stages.get("participant-host")
                if self._wakes(request) and host is None:
                    if not self._no_turn_coming(rid):
                        found.append(rid)
                elif host is not None and host.get("invoked") and host.get("outcome") != "silent" and "transport" not in stages:
                    seen = _parse_stamp(request["seen"].get("participant-host"))
                    if seen is None or now - seen < TRANSPORT_GRACE_SECONDS:
                        found.append(rid)
        return found

    def turns(self) -> list[dict[str, Any]]:
        """The turns that ran, in the order their receipts were first read, each as the probe records a turn."""

        self.poll()
        with self._lock:
            actions = self._actions()
            turns = []
            for rid in self._order:
                request = self.requests[rid]
                host = request["stages"].get("participant-host")
                if host is None or not host.get("invoked"):
                    continue
                action = actions.get(rid)
                turn: dict[str, Any] = {
                    "request_id": rid,
                    "trigger": request["trigger"],
                    "source": host.get("wake_source"),
                    "started": request["seen"].get("attention") or request["seen"].get("observation"),
                    "ended": request["seen"].get("participant-host"),
                    # The plain-call host binds a model's answer to the turn's request id: an answer that reached the host was bound.
                    "bound": True,
                    # The messages the turn was handed with (the host's receipt): a held message among them was there from the start.
                    "first_packet": list(host.get("delivered_event_ids") or []),
                }
                if action is not None:
                    turn["result"] = _summarize_action({key: action[key] for key in ("kind", "text", "reaction", "target_event_id") if key in action})
                elif host.get("outcome") == "silent":
                    turn["result"] = {"kind": "silence"}
                else:
                    turn["result"] = None
                turns.append(turn)
            return turns

    def _actions(self) -> dict[str, dict[str, Any]]:
        """Each handed-over action by its request id: the transport's receipts paired in order with the bot's writes."""

        records = self.room.records
        writes = wire_writes(records, self.room.agent)
        times = wire_write_times(records, self.room.agent)
        found: dict[str, dict[str, Any]] = {}
        cursor = 0
        for rid in self._transports:
            request = self.requests[rid]
            transport = request["stages"]["transport"]
            entry: dict[str, Any] = {"delivery": transport.get("delivery")}
            if transport.get("detail"):
                entry["detail"] = transport["detail"]
            if transport.get("delivery") == "sent" and cursor < len(writes):
                entry.update(action_of_write(writes[cursor]))
                entry["at"] = times[cursor]
                cursor += 1
            found[rid] = entry
        return found

    def committed(self) -> list[dict[str, Any]]:
        """The actions handed to the room, as the legs record them: the request, what it was, how it was delivered, when the wire saw it."""

        self.poll()
        with self._lock:
            actions = self._actions()
            committed = []
            for rid in self._transports:
                entry = {"request_id": rid, **actions[rid], "origin_event_id": self.requests[rid]["trigger"]}
                committed.append(entry)
            return committed

    def attention_calls(self) -> int:
        """The attention model calls the receipts show: a judgment that names the model (``classifier``), or an error after one was made."""

        self.poll()
        with self._lock:
            return sum(
                1
                for request in self.requests.values()
                if "classifier" in request["stages"].get("attention", {}) or "error" in request["stages"].get("attention", {})
            )

    def stages(self) -> dict[str, dict[str, Any]]:
        self.poll()
        with self._lock:
            return {rid: {stage: dict(body) for stage, body in request["stages"].items()} for rid, request in self.requests.items()}


def _parse_stamp(value: Any) -> float | None:
    """A ``LiveTurns`` stamp as seconds since the epoch; None for anything else."""

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


# -- the reference: nunchi-discord in its own process ---------------------------------------------------


class ReferenceLeg(Leg):
    """`nunchi-discord` in its own process, with a scripted plain-call participant: the evidence comes from outside it.

    With ``--scene`` (``ctx.directed``) it plays one behavior scene instead of
    the moments: the world holds that scene's people and bots, attention and
    the participant follow its `SceneScript`, the director (`directed.py`)
    posts the scene, and each graded moment is graded from the scene's own
    expectations (`directed.judge_scene`).

    A live scene (no ``--scripted``) gives the reference a participant model
    through OpenRouter and live attention. Nothing of the probe sits between
    the process and its models, so its turns are read from outside it
    (`LiveTurns`: its receipts and the wire), with what that cannot show named
    in the record (`model_calls`, ``observes_unattended``).
    """

    harness = REFERENCE
    script = SCRIPT
    pins: Mapping[str, str] = REFERENCE_PINS
    expected_calls = REFERENCE_CALLS
    live: LiveTurns | None = None
    # Where a live reference's participant model is (the agent's model through OpenRouter); a test points it at a provider of its own.
    participant_base_url = OPENROUTER

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self.discord = DiscordRoom(ctx, self.harness)
        self.participant_endpoint: ScriptedParticipant | None = None
        self.process: DiscordProcess | None = None
        self._spec: MomentSpec | directed.DirectedSpec | None = None
        self.directed: directed.DirectedSpec | None = ctx.directed
        if self.directed is not None:
            self.script = self.directed.script
        # A live scene: the participant model is a real one, and the turns are read from outside the process.
        self.preflight_calls = 0
        if self.live_run:
            self.live = LiveTurns(self.discord)
            self.observes_unattended = False

    def preflight(self, key: str, profile_sha256: str) -> None:
        """Live: one call to the participant model with the body the reference's participant will send, before anything starts.

        The reference asks its model for a JSON object (``response_format``
        ``json_object``) through OpenRouter's chat completions; whether the
        agent model's providers honor that is the first thing a live run learns,
        and it must not learn it by every turn of a 40-minute scene failing.
        So this makes the same request once, through the same code
        (`OpenAICompatibleParticipant`), and the run could not run, with the
        provider's answer, if what comes back is not a JSON object. It is a
        model call and is counted (`model_calls`).
        """

        profile = ParticipantProfile(
            profile_id=f"{PARTICIPANT}-rehearsal",
            participant_id=PARTICIPANT,
            actor_id=self.actor_id,
            instructions=self.ctx.profile["instructions"],
            provenance="rehearsal:probe",
            sha256=profile_sha256,
        )
        participant = OpenAICompatibleParticipant(
            profile=profile,
            model=self.ctx.route.model,
            api_key=key,
            base_url=self.participant_base_url,
            provider="openrouter",
            timeout_seconds=PREFLIGHT_SECONDS,
        )
        messages = [
            {"role": "system", "content": participant_turn_prompt(profile)},
            {"role": "user", "content": json.dumps({"preflight": "answer with a JSON object: {\"kind\": \"silence\"}"})},
        ]
        self.preflight_calls += 1
        try:
            answer = participant._complete(messages, json_reply=True)
        except ParticipantModelError as exc:
            raise CouldNotRun(f"the reference's participant model did not answer the request it will send: {exc}") from exc
        if isinstance(answer, str):
            try:
                answer = json.loads(answer)
            except ValueError:
                pass
        if not isinstance(answer, Mapping):
            raise CouldNotRun(
                f"the reference's participant model answered with something that is not a JSON object, so every turn would fail: {str(answer)[:300]!r}"
            )

    @property
    def room(self) -> Any:
        return None

    def prepare(self) -> None:
        self.discord.start([self.directed.plan.scene] if self.directed is not None else None)
        self.room_id = self.discord.channel_id
        self.actor_id = f"discord:actor:{self.discord.agent_id}"
        self.scope = f"discord:channel:{self.room_id}"
        if self.live is not None:
            participant_model = {
                "model": self.ctx.route.model,
                "base_url": self.participant_base_url,
                "provider": "openrouter",
                "api_key_env": PARTICIPANT_KEY_ENV,
                "timeout_seconds": LIVE_PARTICIPANT_TIMEOUT_SECONDS,
            }
        else:
            self.participant_endpoint = ScriptedParticipant(self.script)
            self.ctx.route = replace(self.ctx.route, base_url=self.participant_endpoint.base_url)
            participant_model = {
                "model": self.ctx.route.model,
                "base_url": self.participant_endpoint.base_url,
                "provider": "scripted",
                "api_key_env": PARTICIPANT_KEY_ENV,
                "timeout_seconds": PARTICIPANT_TIMEOUT_SECONDS,
            }
        _, path = self.room_config({"participant_model": participant_model, "transport": {"bot_token_env": BOT_TOKEN_ENV}})
        if self.live is not None:
            self.preflight(self.ctx.secrets[PARTICIPANT_KEY_ENV], hashlib.sha256((self.ctx.base / "config" / f"{PARTICIPANT}.profile.json").read_bytes()).hexdigest())
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
        if self.live is not None:
            self.live.start()
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
        return {"version": version, "expected": REFERENCE_PIN, "executable": self.discord.python}

    def deliver(self, raw: Mapping[str, Any], at: datetime, scene: Scene, sequence: int) -> dict[str, Any]:
        assert self._spec is not None
        return self.discord.reach(self.discord.post(raw, at, scene, self._spec))

    def play(self, spec: MomentSpec | directed.DirectedSpec, *, settle_seconds: float) -> dict[str, Any]:
        self._spec = spec
        if isinstance(spec, directed.DirectedSpec):
            moment = directed.play_scene(self, spec.plan, settle_seconds, **({"live": True} if self.live is not None else {}))
            self.read_turns()
            for turn in self.invocations:
                turn["moment"] = spec.name
            return moment
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

    def refresh(self) -> None:
        if self.live is not None:
            self.read_turns()

    def begun(self, event_id: str) -> bool:
        return self.live.begun(event_id) if self.live is not None else super().begun(event_id)

    def settle_live(self, timeout: float) -> bool:
        """A live reference is settled when no request is open and nothing moved for `LIVE_QUIET_SECONDS`: its receipts, its state, the wire.

        A live model takes seconds to answer and leaves nothing outside the
        process while it thinks, so "nothing moved" alone would end the wait
        in the middle of a turn: a request is open from the observation of a
        message until the attention model is back, and, once attention wakes
        the agent, until the host's receipt (`LiveTurns.open_requests`).
        """

        assert self.live is not None
        deadline = time.monotonic() + timeout
        last: Any = None
        since = time.monotonic()
        while time.monotonic() < deadline:
            open_requests = self.live.open_requests()
            mark = (self._written(), len(self.discord.records), len(open_requests))
            if mark != last:
                last, since = mark, time.monotonic()
            if not open_requests and time.monotonic() - since >= LIVE_QUIET_SECONDS and self.discord.quiet(LIVE_QUIET_SECONDS):
                return True
            time.sleep(0.2)
        return False

    def settle(self, timeout: float) -> bool:
        """Until nothing moved for 2 s: the wire, both scripted endpoints, and the reference's receipts."""

        if self.live is not None:
            return self.settle_live(timeout)
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

        if self.live is not None:
            self.read_turns_live()
            return
        stages = stages_by_request(self.receipts())
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
            if given[-1].get("unattended"):
                turn["unattended"] = given[-1]["unattended"]
            if host is not None:
                turn["ended"] = given[-1]["at"]
        committed = {item["request_id"] for item in self.committed}
        for request_id, stage in stages.items():
            transport = stage.get("transport")
            if transport is None or request_id in committed or request_id not in answers:
                continue
            given = answers[request_id][-1]["action"]
            action = _summarize_action(given)
            action.pop("why", None)
            if self.directed is not None and isinstance(given, Mapping) and "origin_event_id" in given:
                # A scene holds each action to the message it was about; a plain message names it only by its origin.
                action["origin_event_id"] = given["origin_event_id"]
            self.committed.append({"request_id": request_id, **action, "delivery": transport.get("delivery"), "detail": transport.get("detail")})
        self.attention_calls = attention_entries(stages, (self.ctx.attention or {}).get("model"), evidence=self.directed is not None)

    def read_turns_live(self) -> None:
        """The turns, actions and attention calls of a live scene, from `LiveTurns`: the receipts and the wire.

        The lists are replaced in place, since the director holds them, and a
        turn keeps the moment it was tagged with.
        """

        assert self.live is not None
        moments = {turn["request_id"]: turn.get("moment") for turn in self.invocations}
        turns = self.live.turns()
        for turn in turns:
            turn["moment"] = moments.get(turn["request_id"])
        self.invocations[:] = turns
        self.committed[:] = self.live.committed()
        self.attention_calls = attention_entries(
            self.live.stages(), (self.ctx.attention or {}).get("model"), evidence=self.directed is not None, provider="openrouter"
        )

    def received_live(self) -> dict[str, dict[str, Any]]:
        """For each message a turn was handed, how it showed it was addressed: the host's receipt that it was in the packet, and the room log's own record of it.

        The reference's wake is built in its process and goes to its model; the probe sees neither. The packet's event ids are
        in the host's receipt, and what the room log holds of each message is what that packet was built from.
        """

        assert self.live is not None
        logged = room_events(self.discord.state)
        found: dict[str, dict[str, Any]] = {}
        for request in self.live.stages().values():
            host = request.get("participant-host")
            trigger = (request.get("observation") or {}).get("trigger_event_id")
            event = logged.get(trigger) if trigger else None
            if host is None or not host.get("invoked") or event is None or trigger not in (host.get("delivered_event_ids") or ()):
                continue
            found.setdefault(
                trigger,
                {
                    "trigger": trigger,
                    "mentioned_actor_ids": list(event.get("mentioned_actor_ids") or ()),
                    "reply_to_event_id": event.get("reply_to_event_id"),
                    "thread_root_event_id": event.get("thread_root_event_id"),
                },
            )
        return found

    def model_calls(self) -> dict[str, Any]:
        turns = len(self.invocations)
        return {
            "agent": turns + self.preflight_calls,
            "attention": self.live.attention_calls() if self.live is not None else 0,
            "basis": "a lower bound: agent, the turns the host ran, one model call each at least (a page the look before posting "
            "showed, or a refused answer, asks again, and the process does not show it), plus the one preflight call; attention, the "
            "receipts that name a model or an error",
        }

    def collect(self) -> None:
        if self.live is not None:
            self.live.stop()
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
        if self.live is not None:
            self.reports["reference"]["live"] = "the turns are read from the process's receipts and the wire; its model calls are not shown"
            if self.live.errors:
                self.reports["reference"]["live_reader_errors"] = list(self.live.errors)

    def room_effects(self) -> list[dict[str, Any]]:
        return self.discord.effects()

    def judge(self, moments: Sequence[dict[str, Any]]) -> None:
        if self.live is not None:
            received = self.received_live()
        else:
            answers = self.participant_endpoint.answers if self.participant_endpoint else ()
            received = {answer["received"]["trigger"]: answer["received"] for answer in answers if answer.get("received")}
        judge_discord_moments(self, moments, received)
        if self.directed is not None:
            judge_directed(self, moments)

    def scripted_check(self, moments: Sequence[Mapping[str, Any]]) -> Check:
        if self.directed is not None:
            return checks_module.directed_outcomes(moments)
        return checks_module.discord_scripted_outcomes(moments, EXPECTED, pins=self.pins)

    def room_checks(self, document: Mapping[str, Any]) -> list[Check]:
        # A scene has no reconnect, and the calls it needs are the ones its script makes.
        calls = directed_calls(document["moments"], live=self.live is not None) if self.directed is not None else self.expected_calls
        expected = {self.discord.agent: {"chunk": True, "calls": calls}}
        found = self.discord.checks(
            self.committed, expected=expected, gaps_fail=False, moments=document["moments"], reconnects_required=self.directed is None
        )
        return found + word_nod_checks(self.directed, self.committed) if self.directed is not None else found

    def room_record(self) -> dict[str, Any]:
        return {"discord": self.discord.record()}

    def close(self) -> None:
        try:
            if self.live is not None:
                self.live.stop()
            self.discord.close()
        finally:
            if self.participant_endpoint is not None:
                self.participant_endpoint.close()


LEGS: dict[str, type[Leg]] = {REFERENCE: ReferenceLeg}
