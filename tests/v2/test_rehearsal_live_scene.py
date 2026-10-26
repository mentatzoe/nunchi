"""Offline tests of live-model reference scene mechanics.

A loopback fake provider exercises timing, receipt reconstruction, spend records
and failure handling. No real model or agent harness is called.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
import urllib.error
import urllib.request
from unittest import mock

from evals.behavior.scene import load_scene
from evals.rehearsal import checks, directed, discord_room, probe, record, routes, spend, standin
from evals.rehearsal.fake_discord.control import FakeDiscord

from tests.v2.test_rehearsal_directed import PLAYABLE, ROOT, _moment, _scene
from tests.v2.test_rehearsal_discord_room import _StandIn, _room

CI = "CI"
KEY = "sk-or-v1-" + "k" * 40
CANARY = "canary-" + "c" * 30
FIRST_FOUR = ("bot-status-report", "story-across-messages", "said-it-would-check", "mention-in-busy-room")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(at: datetime | None = None) -> str:
    return standin.timestamp(at or _now())


def _live_env(harness: str, *, ci: str | None = "true", keys: dict[str, str] | None = None) -> dict[str, str]:
    """An environment a live scene by ``harness`` may start in: CI, and the keys its column reads (``keys`` replaces them)."""

    env = {name: KEY for name in routes.LIVE_SCENE_KEYS[harness]}
    env.update(keys or {})
    if ci is not None:
        env[CI] = ci
    return env


def _options(harness: str = "reference", **fields) -> probe.Options:
    fields.setdefault("out", Path("x"))
    return probe.Options(harness=harness, room="discord", scene="bot-status-report", command=["test"], **fields)


# -- a fake provider, and the live agent that asks it ---------------------------------------------------------------


class Provider:
    """A model provider on loopback, built on the scripted endpoints' own server (`standin._Server`).

    A POST is a chat call: it waits ``delay`` and answers the JSON ``decide``
    gives for the prompt. A GET is the key's usage document
    (`spend.SpendWatch` reads it through ``opener``), which rises by ``step``
    on every read, or answers ``key_status`` if that is not 200. Every call is
    kept.
    """

    def __init__(self, decide, *, step: float = 0.05, key_status: int = 200, chat_status: int = 200) -> None:
        from http.server import BaseHTTPRequestHandler

        self.decide, self.step, self.key_status, self.chat_status = decide, step, key_status, chat_status
        self.prompts: list[str] = []
        self.bodies: list[dict] = []
        self.auth: list[str | None] = []
        self.key_reads = 0
        self._lock = threading.Lock()
        provider = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args) -> None:
                pass

            def _send(self, status: int, document: dict) -> None:
                payload = json.dumps(document).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:  # noqa: N802
                with provider._lock:
                    provider.key_reads += 1
                    usage = round(1.0 + provider.step * provider.key_reads, 6)
                if provider.key_status != 200:
                    self._send(provider.key_status, {"error": "no"})
                else:
                    self._send(200, {"data": {"usage": usage, "label": "sk-or-v1-secret-label"}})

            def do_POST(self) -> None:  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
                prompt = body["messages"][-1]["content"]
                with provider._lock:
                    provider.prompts.append(prompt)
                    provider.bodies.append(body)
                    provider.auth.append(self.headers.get("Authorization"))
                if provider.chat_status != 200:
                    self._send(provider.chat_status, {"error": {"message": "No endpoints found that support the requested response_format json_object"}})
                    return
                delay, answer = provider.decide(prompt)
                time.sleep(delay)
                self._send(200, {"choices": [{"message": {"role": "assistant", "content": json.dumps(answer)}}]})

        self._server = standin._Server(Handler)
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def close(self) -> None:
        self._server.close()

    def ask(self, prompt: str) -> dict:
        request = urllib.request.Request(
            self._server.base_url + "/chat/completions",
            data=json.dumps({"messages": [{"role": "user", "content": prompt}]}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with self._opener.open(request, timeout=30) as response:
            return json.loads(json.load(response)["choices"][0]["message"]["content"])

    def opener(self, request, timeout: float = 20):
        """What `spend.SpendWatch` opens instead of OpenRouter's key endpoint: this provider's, on loopback."""

        return self._opener.open(urllib.request.Request(self._server.origin + "/key", headers=dict(request.header_items())), timeout=timeout)


def quiet_agent(prompt: str):
    return 0.0, {"move": "silent"}


class AgentLeg:
    """The part of a leg the director and the judge use, with a live agent behind it: a thread for each message addressed to it.

    The thread records the turn as the in-process legs do (``started`` the moment
    the host would hand it to the harness, ``ended`` when it is done), asks the
    provider and moves as it answers, after the delay the provider takes. The
    message takes ``reach_latency`` to reach Nunchi, as `DiscordRoom.reach`
    does, so a test decides which comes first, a held message arriving or the
    agent's move.
    """

    observes_unattended = True
    live_run = True

    def __init__(self, room, spec, provider: Provider, *, reach_latency: float = 0.0, hears=None, lost=(), packet=()) -> None:
        self.discord, self.script, self._spec = room, spec.script, spec
        self.provider, self.reach_latency = provider, reach_latency
        # The scene events that never reach Nunchi, and the scene events that are already in the first packet of the turn on a message.
        self.lost, self.packet = set(lost), set(packet)
        self.shown_asked: list[tuple] = []
        self.delivered_ids: dict[str, str] = {}
        self.hears = hears or (lambda raw, scene: "vigil" in raw.get("mentions", ()))
        self.invocations: list[dict] = []
        self.committed: list[dict] = []
        self.attention_calls: list[dict] = []
        self.shown: object = None  # what `shown_to_turn` answers: None (not shown by this column's record), or a list of event ids / a function
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()

    def refresh(self) -> None:
        pass

    def begun(self, event_id: str) -> bool:
        with self._lock:
            return any(turn.get("trigger") == event_id for turn in self.invocations)

    def shown_to_turn(self, event_ids, since, until=None):
        self.shown_asked.append((list(event_ids), since, until))
        if callable(self.shown):
            return self.shown(event_ids, since)
        return self.shown

    def deliver(self, raw, at, scene, sequence):
        delivery = self.discord.post(raw, at, scene, self._spec)
        time.sleep(self.reach_latency)
        delivery["observed"] = raw["id"] not in self.lost
        if not delivery["observed"]:
            delivery["reached_nunchi"], delivery["note"] = False, "it never reached Nunchi"
        self.delivered_ids[raw["id"]] = delivery["event_id"]
        if raw["id"] in self.packet:
            # The message was in the first packet of the turn(s) under way: it reached Nunchi before they were handed to the agent.
            with self._lock:
                for turn in self.invocations:
                    turn["first_packet"].append(delivery["event_id"])
        heard = bool(self.hears(raw, scene)) and delivery["observed"]
        self.attention_calls.append({"trigger": delivery["event_id"], "disposition": "WAKE" if heard else "SUPPRESS", "evidence": [delivery["event_id"]]})
        if heard:
            thread = threading.Thread(target=self._turn, args=(delivery, raw), daemon=True)
            self._threads.append(thread)
            thread.start()
        return delivery

    def _turn(self, delivery, raw) -> None:
        trigger = delivery["event_id"]
        with self._lock:
            request = f"r{len(self.invocations) + 1}"
            entry = {"request_id": request, "trigger": trigger, "source": "WAKE", "started": _stamp(), "bound": True, "first_packet": [trigger]}
            self.invocations.append(entry)
        answer = self.provider.ask(raw["text"])
        delivery_result = answer.get("delivery", "sent")
        action = {
            "reply": lambda: {"kind": "reply", "text": answer.get("text"), "target_event_id": trigger},
            "post": lambda: {"kind": "message", "text": answer.get("text")},
            "react": lambda: {"kind": "reaction", "reaction": answer.get("reaction", "\N{EAR}"), "target_event_id": trigger},
        }.get(answer["move"])
        if action is not None:
            made = action()
            with self._lock:
                self.committed.append(
                    {"request_id": request, **made, "origin_event_id": trigger, "delivery": delivery_result, "delivered": delivery_result == "sent", "at": _stamp()}
                )
            entry["result"] = {key: made[key] for key in ("kind", "text", "reaction", "target_event_id") if key in made}
        else:
            entry["result"] = {"kind": "silence"}
        entry["ended"] = _stamp()

    def settle(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        for thread in list(self._threads):
            thread.join(max(0.0, deadline - time.monotonic()))
        return not any(thread.is_alive() for thread in self._threads)


class DirectorCase(_StandIn, unittest.TestCase):
    """The director on a plain stand-in, with a fake provider and an `AgentLeg`."""

    def play(self, scene, decide, *, shown=None, reach_latency: float = 0.0, hears=None, lost=(), packet=(), **options):
        item = directed.plan(scene)
        self.assertIsNone(item.unplayable, item.unplayable)
        spec = directed.DirectedSpec(item, directed.script_for(item))
        world, members = discord_room.world_spec("reference", [scene], agent="Vigil")
        fd = self.start(world)
        base = Path(tempfile.mkdtemp(prefix="live-scene-"))
        self.addCleanup(shutil.rmtree, base, True)
        room = _room(base)
        room.fd, room.members = fd, members
        provider = Provider(decide)
        self.addCleanup(provider.close)
        leg = AgentLeg(room, spec, provider, reach_latency=reach_latency, hears=hears, lost=lost, packet=packet)
        leg.shown = shown
        played = directed.play_scene(leg, item, 10.0, live=True, **options)
        return leg, spec, played

    def judge(self, leg, spec, played) -> dict:
        directed.judge_scene(leg, played, spec.plan.scene)
        return played


# -- a live scene is refused off a CI runner and without its keys ----------------------------------------------------


class RefusalTest(unittest.TestCase):
    def main(self, *arguments, env: dict[str, str]):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stderr(
            io.StringIO()
        ) as error, contextlib.redirect_stdout(io.StringIO()):
            code = probe.main([*arguments, "--out", directory])
            written = list(Path(directory).iterdir())
        return code, error.getvalue(), written

    LIVE = ("--room", "discord", "--scene", "bot-status-report")

    def test_a_live_scene_is_refused_off_a_ci_runner_before_anything_is_written(self):
        for harness in ("reference",):
            for ci in (None, "false", "1", "True", ""):
                with self.subTest(harness=harness, ci=ci):
                    code, error, written = self.main("--harness", harness, *self.LIVE, env=_live_env(harness, ci=ci))
                    self.assertEqual(probe.EXIT_USAGE, code)
                    self.assertIn("only on a CI runner", error)
                    self.assertEqual([], written, "nothing was started or written")
        # The library entry refuses too, and writes nothing: a run is not started by calling it off a runner.
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, _live_env("reference", ci=None), clear=True):
            with self.assertRaisesRegex(ValueError, "only on a CI runner"):
                probe.run_probe(_options(scripted=False, out=Path(directory)))
            self.assertEqual([], list(Path(directory).iterdir()))

    def test_a_live_scene_is_refused_when_any_key_its_column_reads_is_missing_and_a_scripted_one_needs_none(self):
        for harness, names in routes.LIVE_SCENE_KEYS.items():
            self.assertEqual(2, len(names))
            self.assertEqual(routes.ATTENTION_KEY_ENV, names[0])
            for missing in names:
                with self.subTest(harness=harness, missing=missing):
                    env = _live_env(harness)
                    del env[missing]
                    code, error, written = self.main("--harness", harness, *self.LIVE, env=env)
                    self.assertEqual(probe.EXIT_COULD_NOT_RUN, code)
                    self.assertIn(missing, error)
                    self.assertEqual([], written)
                    # An empty value is no key.
                    code, _, _ = self.main("--harness", harness, *self.LIVE, env=_live_env(harness, keys={missing: ""}))
                    self.assertEqual(probe.EXIT_COULD_NOT_RUN, code)
            self.assertIsNone(probe.live_scene_refusal(_options(harness, scripted=False), _live_env(harness)))
            self.assertIsNone(probe.live_scene_refusal(_options(harness, scripted=True), {}), "a scripted scene needs neither")
        # The harness's own key is not borrowed from the attention key here, as the in-process live probe does.
        code, error, _ = self.main("--harness", "reference", *self.LIVE, env={CI: "true", routes.ATTENTION_KEY_ENV: KEY})
        self.assertEqual(probe.EXIT_COULD_NOT_RUN, code)
        self.assertIn(routes.PARTICIPANT_KEY_ENV, error)

    def test_a_run_started_without_its_keys_is_recorded_as_could_not_run_and_starts_no_process(self):
        env = _live_env("reference", keys={routes.PARTICIPANT_KEY_ENV: ""})
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(io.StringIO()):
            code = probe.run_probe(_options("reference", scripted=False, out=Path(directory), agent_model="anthropic/claude-haiku-4.5"))
            run = json.loads((Path(directory) / "reference" / "run.json").read_text())
            written = sorted(path.name for path in (Path(directory) / "reference").iterdir())
        self.assertEqual(probe.EXIT_COULD_NOT_RUN, code)
        self.assertEqual("could-not-run", run["status"])
        self.assertIn(routes.PARTICIPANT_KEY_ENV, " ".join(run["errors"]))
        self.assertNotIn("discord-wire.jsonl", written, "no stand-in and no Discord process was started")
        self.assertEqual("live", run["mode"])


    def test_the_launcher_must_have_run_online_on_a_ci_runner(self):
        discord_room.require_online({"offline": False, "ci": True})
        for net, words in (({"offline": True, "ci": True}, "without --offline"), ({"offline": False, "ci": False}, "CI=true"), ({}, "CI=true")):
            with self.subTest(net=net), self.assertRaisesRegex(probe.CouldNotRun, words):
                discord_room.require_online(net)
        # The Discord room takes the launcher's record for a live scene only, and a scripted run never asks.
        with tempfile.TemporaryDirectory() as directory:
            net = Path(directory) / "net.json"
            for record_, live, ok in (({"offline": True, "ci": True}, True, False), ({"offline": False, "ci": True}, True, True), ({"offline": True, "ci": False}, False, True)):
                net.write_text(json.dumps({"tls": {"cert": "c", "key": "k"}, **record_}))
                ctx = SimpleNamespace(
                    original_env={discord_room.NET_ENV: str(net)}, options=SimpleNamespace(discord_python=None, scripted=not live),
                    base=Path(directory), out=Path(directory), profile={"display_name": "Vigil"}, env={}, secrets={},
                )
                if ok:
                    discord_room.DiscordRoom(ctx, "reference")
                else:
                    with self.assertRaises(probe.CouldNotRun):
                        discord_room.DiscordRoom(ctx, "reference")


# -- an earlier line of the agent's is its own move ------------------------------------------------------------------


def _scene_of(scene_id: str):
    return directed.spec(scene_id).plan.scene


def _reply_to_the_promise(prompt: str):
    if "keep an eye" in prompt:
        return 0.0, {"move": "reply", "text": "I will tell you when it is done."}
    return 0.0, {"move": "post", "text": "The nightly passed: 2,311 tests, 0 failures."}


PROMISE_HEARS = lambda raw, scene: raw["id"] in ("z1", "c1")  # noqa: E731  Alice's request, and the CI line the promise is about


class LineTest(DirectorCase):
    def test_a_line_the_live_agent_makes_goes_on_with_its_own_words_and_the_moment_is_graded_from_what_it_did(self):
        leg, spec, played = self.play(_scene_of("build-finishes-after-promise"), _reply_to_the_promise, hears=PROMISE_HEARS)
        self.judge(leg, spec, played)
        self.assertNotIn("stopped", played)
        self.assertEqual(["z1", "s1", "c1"], [delivery["scene_event"] for delivery in played["deliveries"]], "the agent's v1 is not posted by the director")
        (line,) = played["lines"]
        self.assertEqual((True, True, []), (line["live"], line["landed"], line["problems"]))
        self.assertTrue(line["did"].startswith("reply 'I will tell you when it is done."), line["did"])
        self.assertNotEqual(line["text"], "I will tell you when it is done.", "the scene's words are not forced: only their kind is checked")
        (item,) = played["graded"]
        self.assertEqual({"visible": "fits", "step1": "ok"}, item["grade"])
        self.assertEqual("speak", item["result"])
        self.assertEqual(([], None, None), (item["off_script"], item["scripted"], item["scripted_action"]), "a live run has no script to hold it to")
        self.assertNotIn("precondition", item)
        self.assertEqual(checks.FITS, played["outcome"])
        self.assertEqual(
            ["Vigil told Alice it would tell her when the nightly finishes", "this CI line says the nightly finished and passed"], item["facts"],
            "the moment's own facts, in the scene's words, in the order `cited` reads them",
        )

    def test_a_line_the_agent_did_not_make_stops_the_scene_and_its_moments_are_reported_precondition_not_met_and_not_graded(self):
        scene = _scene_of("build-finishes-after-promise")
        for name, decide, hears, words in (
            ("silence", quiet_agent, PROMISE_HEARS, "the turn on it ended in silence"),
            ("no turn", quiet_agent, lambda raw, s: False, "no turn began on it"),
            ("a nod", lambda prompt: (0.0, {"move": "react", "reaction": "\N{THUMBS UP SIGN}"}), PROMISE_HEARS, "reaction"),
        ):
            with self.subTest(agent=name):
                leg, spec, played = self.play(scene, decide, hears=hears)
                self.judge(leg, spec, played)
                self.assertEqual(["z1"], [delivery["scene_event"] for delivery in played["deliveries"]], "nothing after the line is posted")
                self.assertEqual(("z1", "v1"), (played["stopped"]["after"], played["stopped"]["line"]))
                self.assertIn(words, played["stopped"]["why"])
                (line,) = played["lines"]
                self.assertFalse(line["landed"])
                self.assertIn(words, line["problems"][0])
                (item,) = played["graded"]
                self.assertIsNone(item["grade"], "not graded")
                self.assertFalse(item["reached"], "the moment's message was never posted")
                self.assertEqual(1, len(item["precondition"]))
                self.assertIn("v1", item["precondition"][0])
                self.assertEqual(checks.PRECONDITION, played["outcome"])
                if name == "a nod":
                    self.assertIn("where the scene has a reply or a post", line["problems"][0], "what it did instead is named")

    def test_the_kind_of_move_is_what_a_line_needs_a_reply_or_a_post_answers_and_only_a_reaction_nods(self):
        trigger = "discord:message:5"
        turn = [{"request_id": "r1", "trigger": trigger}]

        def landing(kind, *actions, turns=turn):
            return directed.line_landing({"kind": kind}, trigger, turns, [{"request_id": "r1", "delivery": "sent", **action} for action in actions])

        reply, post, nod = {"kind": "reply", "text": "x"}, {"kind": "message", "text": "x"}, {"kind": "reaction", "reaction": "\N{EAR}"}
        for kind, action, ok in (
            ("reply", reply, True), ("reply", post, True), ("reply", nod, False),
            ("message", post, True), ("message", reply, True), ("message", nod, False),
            ("reaction", nod, True), ("reaction", reply, False), ("reaction", post, False),
        ):
            with self.subTest(line=kind, did=action["kind"]):
                self.assertEqual(ok, landing(kind, action)["landed"])
        self.assertIn("no turn began", landing("reply", turns=[])["problems"][0])
        self.assertIn("ended in silence", landing("reply")["problems"][0])
        self.assertIn("never posted", directed.line_landing({"kind": "reply"}, None, turn, [])["did"])
        # Only an action the transport attested counts.
        unsent = directed.line_landing({"kind": "reply"}, trigger, turn, [{"request_id": "r1", "delivery": "failed", **reply}])
        self.assertFalse(unsent["landed"])
        self.assertIn("not delivered", unsent["problems"][0])
        # A turn on another message is not the agent's move on this one.
        self.assertFalse(directed.line_landing({"kind": "reply"}, trigger, [{"request_id": "r2", "trigger": "discord:message:9"}], [{"request_id": "r2", "delivery": "sent", **reply}])["landed"])

    def test_a_nod_is_a_reaction_of_any_emoji_and_a_reply_to_it_is_not_the_nod(self):
        scene = _scene_of("did-you-see")
        leg, spec, played = self.play(scene, lambda prompt: (0.0, {"move": "react", "reaction": "\N{EYES}"}), hears=lambda raw, s: raw["id"] == "z1")
        self.judge(leg, spec, played)
        (line,) = played["lines"]
        self.assertTrue(line["landed"], line["problems"])
        self.assertIn("reaction", line["did"])
        self.assertEqual(["z1", "z2"], [delivery["scene_event"] for delivery in played["deliveries"]])
        leg, spec, played = self.play(scene, lambda prompt: (0.0, {"move": "reply", "text": "Yes, I saw it."}), hears=lambda raw, s: raw["id"] == "z1")
        self.judge(leg, spec, played)
        self.assertFalse(played["lines"][0]["landed"])
        self.assertEqual(checks.PRECONDITION, played["outcome"])

    def test_a_line_that_answers_nothing_is_cued_and_the_agents_move_on_the_cue_is_its_line(self):
        scene = _scene_of("addressee-never-answers")
        leg, spec, played = self.play(scene, lambda prompt: (0.0, {"move": "post", "text": "Nothing to report."}), hears=lambda raw, s: raw["id"] == "cue-v1")
        cue = next(delivery for delivery in played["deliveries"] if delivery.get("cue"))
        self.assertEqual("cue-v1", cue["scene_event"])
        self.assertTrue(played["lines"][0]["cue"])
        self.judge(leg, spec, played)
        self.assertTrue(played["lines"][0]["landed"], played["lines"][0]["problems"])
        self.assertEqual("Nothing to report.", leg.committed[0]["text"])
        # A cue the agent does not answer stops the scene before anything the cue was for.
        leg, spec, played = self.play(scene, quiet_agent, hears=lambda raw, s: raw["id"] == "cue-v1")
        self.assertIn("stopped", played)
        self.assertEqual("cue-v1", played["stopped"]["after"])


# -- a hold is timing ------------------------------------------------------------------------------------------------


def _during_scene():
    """Alice asks Vigil; Sam answers while Vigil composes: a message that must land in the agent's turn."""

    return _scene(
        [
            {"id": "q1", "author": "alice", "at": "-30s", "mentions": ["vigil"], "text": "Vigil, why did last night's deploy fail?"},
            {"id": "a1", "author": "sam", "at": "-10s", "reply_to": "q1", "text": "It was the expired certificate."},
        ],
        [{**_moment("q1", ["stay_quiet", "mhm"], ["speak"]), "during_turn": ["a1"]}],
    )


def _answer_after(delay: float, move: str = "reply"):
    return lambda prompt: (delay, {"move": move, "text": "The certificate expired."})


class HoldTest(DirectorCase):
    def hold(self, scene=None, **options):
        leg, spec, played = self.play(scene or _during_scene(), **options)
        self.judge(leg, spec, played)
        (hold,) = played["holds"]
        return leg, played, hold

    def test_a_held_message_that_reached_nunchi_before_the_agent_moved_is_held(self):
        leg, played, hold = self.hold(decide=_answer_after(1.2), reach_latency=0.15, shown=lambda ids, since: list(ids))
        self.assertEqual("held", hold["outcome"], hold["detail"])
        self.assertTrue(hold["live"])
        self.assertTrue(hold["asked"], "the director posted a1 once the agent's turn had begun")
        (item,) = played["graded"]
        self.assertEqual("held", item["hold"])
        self.assertEqual(["q1", "a1"], [delivery["scene_event"] for delivery in played["deliveries"]])
        a1 = played["deliveries"][1]
        self.assertGreater(hold["turn"]["moved_at"].replace("+00:00", "Z"), a1["delivered_at"].replace("+00:00", "Z"), "a1 reached Nunchi first")
        self.assertEqual(checks.MISSES, played["outcome"], "the agent spoke where the draft fits quiet or a nod: a miss, reported")

    def test_a_turn_that_moved_before_the_held_message_reached_nunchi_raced_which_is_not_a_miss(self):
        leg, played, hold = self.hold(decide=_answer_after(0.0), reach_latency=0.15, shown=lambda ids, since: list(ids))
        self.assertEqual("raced", hold["outcome"], hold["detail"])
        self.assertIn("before a1 reached Nunchi", hold["detail"])
        self.assertEqual("raced", played["graded"][0]["hold"])
        self.assertEqual(checks.RACED, played["outcome"], "a race is the moment not played as scripted, not the agent's miss")

    def test_a_held_message_in_time_that_the_columns_record_shows_the_turn_never_saw_is_unseen_the_columns_miss(self):
        leg, played, hold = self.hold(decide=_answer_after(1.2), reach_latency=0.15, shown=lambda ids, since: [])
        self.assertEqual("unseen", hold["outcome"], hold["detail"])
        self.assertEqual(checks.MISSES, played["outcome"])
        # A column whose record does not show what the turn was shown cannot be called unseen; it is held, and says so.
        leg, played, hold = self.hold(decide=_answer_after(1.2), reach_latency=0.15, shown=None)
        self.assertEqual("held", hold["outcome"])
        self.assertIn("does not show whether the turn was shown them", hold["detail"])
        # A turn that stayed silent was never going to post, so what it was shown is not a miss.
        leg, played, hold = self.hold(decide=_answer_after(1.2, "silent"), reach_latency=0.15, shown=lambda ids, since: [])
        self.assertEqual("held", hold["outcome"])
        self.assertIn("ended in silence", hold["detail"])
        self.assertIsNone(hold["turn"]["moved_at"])

    def test_a_turn_that_never_began_leaves_nothing_held_and_the_moment_is_not_graded(self):
        with mock.patch.object(directed, "HOLD_ASK_SECONDS", 0.3):
            leg, played, hold = self.hold(decide=quiet_agent, hears=lambda raw, scene: False)
        self.assertEqual("never-asked", hold["outcome"])
        self.assertFalse(hold["asked"])
        self.assertEqual(["q1", "a1"], [delivery["scene_event"] for delivery in played["deliveries"]], "the scene goes on")
        self.assertEqual(checks.PRECONDITION, played["outcome"])
        self.assertIn("no turn began on q1", played["graded"][0]["precondition"][0])
        self.assertIsNone(played["graded"][0]["grade"])

    def test_a_held_message_that_never_reached_nunchi_raced(self):
        outcome = directed.live_hold_outcome(
            {"trigger": "q1", "asked": True, "turn": {"moved_at": None, "ended": _stamp()}, "shown": None,
             "held": [{"event": "a1", "event_id": "e", "observed": False, "delivered_at": _stamp()}]}
        )
        self.assertEqual("raced", outcome[0])
        self.assertIn("never reached Nunchi", outcome[1])

    def test_the_hold_reads_the_times_to_the_millisecond_and_a_tie_is_held(self):
        base = _now()
        at = lambda seconds: _stamp(base + timedelta(seconds=seconds))  # noqa: E731

        def outcome(delivered: float, moved: float | None, ended: float | None = None):
            turn = {"moved_at": None if moved is None else (base + timedelta(seconds=moved)).isoformat(timespec="milliseconds"), "ended": None if ended is None else at(ended)}
            hold = {"trigger": "q1", "asked": True, "turn": turn, "shown": None, "held": [{"event": "a1", "event_id": "e", "observed": True, "delivered_at": at(delivered)}]}
            return directed.live_hold_outcome(hold)[0]

        self.assertEqual("held", outcome(1.0, 2.0))
        self.assertEqual("raced", outcome(2.0, 1.0))
        self.assertEqual("held", outcome(1.0, 1.0), "a tie is held")
        self.assertEqual("raced", outcome(2.0, None, ended=1.0), "a silent turn that ended first raced too")
        self.assertEqual("held", outcome(1.0, None, ended=2.0))
        self.assertIn("had not ended", directed.live_hold_outcome(
            {"trigger": "q1", "asked": True, "turn": {}, "shown": None, "held": [{"event": "a1", "event_id": "e", "observed": True, "delivered_at": at(1)}]})[1])

    def test_a_scripted_hold_is_judged_as_it_was_and_the_live_judge_never_touches_it(self):
        # The scripted gate's record has no `live` flag, and `judge_scene` reads it with `hold_outcome`.
        hold = {"trigger": "q1", "asked": True, "gate": {"asked_at": "t", "released_at": "u", "released_by": "director"}, "held": [{"event": "a1", "event_id": "e", "observed": True, "delivered_at": "a"}], "shown": ["e"]}
        self.assertEqual("held", directed.hold_outcome(hold)[0])


class UnattendedHoldTest(DirectorCase):
    """`asked-while-busy`: Sam's question and Alice's thanks land in the turn on Alice's first question, and are read as one moment."""

    SCENE = "asked-while-busy"

    def run_scene(self, *, lists, observes=True, own_turn_on_s1=False):
        scene = _scene_of(self.SCENE)
        hears = lambda raw, s: raw["id"] in ("z1", "z2", *(("s1",) if own_turn_on_s1 else ()))  # noqa: E731
        leg, spec, played = self.play(scene, lambda prompt: (0.6, {"move": "reply", "text": "Done."}), hears=hears, reach_latency=0.1, shown=lambda ids, since: list(ids))
        leg.observes_unattended = observes
        if lists:
            # The turn on Alice's thanks (z2) took Sam's question (s1) as unattended, as the host's wake says.
            first, second = played["deliveries"][1]["event_id"], played["deliveries"][2]["event_id"]
            for turn in leg.invocations:
                if turn["trigger"] == second:
                    turn["unattended"] = [first]
        self.judge(leg, spec, played)
        (hold,) = played["holds"]
        return hold, played

    def test_the_messages_that_landed_in_the_turn_are_read_with_the_moment_when_its_turn_lists_them(self):
        hold, played = self.run_scene(lists=True)
        self.assertEqual("held", hold["outcome"], hold["detail"])
        self.assertEqual(["z1", "s1", "z2"], [delivery["scene_event"] for delivery in played["deliveries"]])

    def test_a_turn_that_did_not_list_them_judged_the_moment_on_its_own_which_is_unmerged_not_a_race(self):
        hold, played = self.run_scene(lists=False)
        self.assertEqual("unmerged", hold["outcome"], hold["detail"])
        self.assertIn("did not list it as unattended", hold["detail"])
        self.assertEqual(checks.MISSES, played["outcome"])

    def test_a_column_that_does_not_show_what_a_turn_read_as_unattended_is_judged_by_whether_the_message_began_a_turn(self):
        hold, _ = self.run_scene(lists=False, observes=False)
        self.assertEqual("held", hold["outcome"], "nothing shows s1 was judged on its own, so it was read with the moment")
        hold, _ = self.run_scene(lists=False, observes=False, own_turn_on_s1=True)
        self.assertEqual("unmerged", hold["outcome"], hold["detail"])
        self.assertIn("began a turn of its own", hold["detail"])


# -- the grades are the agent's own moves, read against the draft ---------------------------------------------------


def _live_played(scene) -> dict:
    deliveries = [
        {"scene_event": event["id"], "event_id": f"discord:message:{1000 + index}", "observed": True} for index, event in enumerate(scene.events)
    ]
    return {"deliveries": deliveries, "graded": directed.graded_moments(scene, deliveries, live=True), "reached": True, "played_live": True}


def _live_leg(turns=(), actions=(), calls=(), **fields) -> SimpleNamespace:
    return SimpleNamespace(
        invocations=[dict(turn) for turn in turns],
        committed=[dict(action) for action in actions],
        attention_calls=[dict(call) for call in calls],
        shown_to_turn=lambda ids, since: None,
        **fields,
    )


class JudgeTest(unittest.TestCase):
    def test_a_live_scene_has_no_script_so_its_moments_carry_none_and_name_their_facts(self):
        scene = _scene_of("build-finishes-after-promise")
        (item,) = directed.graded_moments(scene, [], live=True)
        self.assertEqual((None, None), (item["scripted"], item["scripted_action"]))
        self.assertEqual(2, len(item["facts"]))
        scripted = directed.graded_moments(scene, [])[0]
        self.assertEqual("speak", scripted["scripted"], "the scripted record is as it was")
        self.assertEqual(item["facts"], scripted["facts"])

    def test_a_move_the_draft_lists_as_a_miss_is_graded_a_miss_and_reported_with_its_reason(self):
        scene = _scene_of("bot-status-report")
        played = _live_played(scene)
        b1 = played["deliveries"][1]["event_id"]
        leg = _live_leg(
            [{"request_id": "r1", "trigger": b1, "source": "WAKE"}],
            [{"request_id": "r1", "kind": "message", "text": "Nice, the build passed.", "delivery": "sent", "delivered": True}],
            [{"trigger": b1, "disposition": "WAKE", "evidence": [b1]}],
        )
        directed.judge_scene(leg, played, scene)
        (item,) = played["graded"]
        self.assertEqual({"visible": "miss", "step1": "over-wake"}, item["grade"])
        self.assertEqual("S!", __import__("evals.behavior.score", fromlist=["cell"]).cell([item]))
        self.assertIn("restating a passing build is noise", item["why"])
        self.assertEqual([], item["off_script"])
        self.assertEqual(checks.MISSES, played["outcome"])
        self.assertEqual("agent", item["by"])

    def test_the_agent_staying_quiet_or_attention_suppressing_it_fits_and_what_it_did_elsewhere_is_listed_not_judged(self):
        scene = _scene_of("bot-status-report")
        played = _live_played(scene)
        b1 = played["deliveries"][1]["event_id"]
        leg = _live_leg(
            [{"request_id": "r9", "trigger": played["deliveries"][0]["event_id"], "source": "WAKE"}],
            [{"request_id": "r9", "kind": "message", "text": "Morning, Alice.", "delivery": "sent", "delivered": True}],
            [{"trigger": b1, "disposition": "SUPPRESS", "evidence": [b1]}],
        )
        directed.judge_scene(leg, played, scene)
        (item,) = played["graded"]
        self.assertEqual(("stay_quiet", "attention", {"visible": "fits", "step1": "ok"}), (item["result"], item["by"], item["grade"]))
        self.assertEqual(1, len(played["other_actions"]), "the greeting on the chatter is listed")
        self.assertEqual(checks.FITS, played["outcome"], "what the agent did on the chatter is not part of a moment's grade")

    def test_a_turn_attention_woke_that_ended_in_silence_is_the_agents_choice(self):
        scene = _scene_of("bot-status-report")
        played = _live_played(scene)
        b1 = played["deliveries"][1]["event_id"]
        leg = _live_leg([{"request_id": "r1", "trigger": b1, "source": "WAKE"}], [], [{"trigger": b1, "disposition": "WAKE", "evidence": []}])
        directed.judge_scene(leg, played, scene)
        (item,) = played["graded"]
        self.assertEqual(("stay_quiet", "agent"), (item["result"], item["by"]))
        self.assertEqual({"visible": "fits", "step1": "over-wake"}, item["grade"])

    def test_a_message_that_never_reached_nunchi_is_not_delivered_and_a_record_without_the_live_flag_is_judged_as_before(self):
        scene = _scene_of("bot-status-report")
        played = _live_played(scene)
        for entry in played["graded"]:
            entry["reached"] = False
        played["reached"] = False
        directed.judge_scene(_live_leg(), played, scene)
        self.assertEqual(checks.NOT_DELIVERED, played["outcome"])
        # The scripted judge is unchanged: a moment's scripted action is still held to what the script makes.
        played = _live_played(scene)
        del played["played_live"]
        played["graded"] = directed.graded_moments(scene, played["deliveries"])
        directed.judge_scene(_live_leg(), played, scene)
        self.assertEqual([], played["graded"][0]["off_script"], "the script is quiet and so is the leg")
        self.assertIsNotNone(played["graded"][0]["grade"])


# -- the reference's turns are read from outside its process ----------------------------------------------------------


class ReaderCase(unittest.TestCase):
    def setUp(self) -> None:
        self.state = Path(tempfile.mkdtemp(prefix="live-turns-"))
        self.addCleanup(shutil.rmtree, self.state, True)
        self.wire: list[dict] = []
        self.room = SimpleNamespace(state=self.state, agent="Vigil", records=self.wire, quiet=lambda seconds: True)

    def receipt(self, request: str, stage: str, **body) -> None:
        with open(self.state / "vigil.receipts.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"request_id": request, "stage": stage, "writer": "x", "body": body}) + "\n")

    def observed(self, request: str, trigger: str, **attention) -> None:
        self.receipt(request, "observation", trigger_event_id=trigger)
        if attention:
            self.receipt(request, "attention", **attention)

    def write(self, *, content=None, reply_to=None, emoji=None, message_id="500", at="2026-10-11T05:00:00.000+00:00", status=200) -> None:
        if emoji is not None:
            record_ = {"route": "/channels/{channel}/messages/{message}/reactions/{emoji}/@me", "method": "PUT",
                       "decoded_path": f"/api/v10/channels/9/messages/{message_id}/reactions/{emoji}/@me"}
        else:
            body = {"content": content, **({"message_reference": {"message_id": reply_to}} if reply_to else {})}
            record_ = {"route": "/channels/{channel}/messages", "method": "POST", "decoded_path": "/api/v10/channels/9/messages",
                       "request": body, "response": {"id": message_id}}
        self.wire.append({"kind": "http", "bot": "Vigil", "status": status, "at": at, **record_})


class LiveTurnsTest(ReaderCase):
    def turns(self) -> discord_room.LiveTurns:
        return discord_room.LiveTurns(self.room)

    def test_a_request_attention_woke_is_a_turn_that_will_begin_and_one_it_suppressed_is_not(self):
        live = self.turns()
        self.assertFalse(live.begun("discord:message:99"))
        # Each message is judged after the turn on the one before it has ended (the lane runs one opportunity at a time).
        self.observed("r1", "discord:message:1", effective_disposition="DEFER", classifier={"name": "m"})
        self.assertTrue(live.begun("discord:message:1"), "a deferral wakes the agent")
        self.receipt("r1", "participant-host", wake_source="WAKE", invoked=True, outcome="silent", delivered_event_ids=["discord:message:1"])
        self.observed("r2", "discord:message:2", effective_disposition="SUPPRESS", classifier={"name": "m"})
        self.assertFalse(live.begun("discord:message:2"))
        self.observed("r3", "discord:message:3", error={"code": "timeout", "detail": "slow"})
        self.assertTrue(live.begun("discord:message:3"), "an attention error wakes it: when unsure, pay attention")
        self.receipt("r3", "participant-host", wake_source="ERROR_FALLBACK", invoked=True, outcome="silent", delivered_event_ids=["discord:message:3"])
        self.observed("r4", "discord:message:4", error={"code": "timeout", "detail": "slow"}, wake_action="NO_WAKE")
        self.assertFalse(live.begun("discord:message:4"))
        self.assertTrue(live.begun("discord:message:1"), "a turn that ran began")
        self.assertEqual(["r1", "r3"], [turn["request_id"] for turn in live.turns()])

    def test_a_request_is_open_from_its_observation_until_its_receipts_are_complete(self):
        live = self.turns()
        self.observed("r1", "discord:message:1")
        self.assertEqual(["r1"], live.open_requests(), "attention is still thinking")
        self.receipt("r1", "attention", effective_disposition="WAKE", classifier={"name": "m"})
        self.assertEqual(["r1"], live.open_requests(), "attention woke the agent: the turn is under way")
        self.receipt("r1", "participant-host", wake_source="WAKE", invoked=True, outcome="sent", delivered_event_ids=["discord:message:1"])
        self.assertEqual(["r1"], live.open_requests(), "the host handed the room an action: its transport receipt is still to come")
        self.receipt("r1", "transport", delivery="sent")
        self.assertEqual([], live.open_requests())
        self.observed("r2", "discord:message:2", effective_disposition="SUPPRESS")
        self.observed("r3", "discord:message:3", effective_disposition="WAKE")
        self.receipt("r3", "participant-host", wake_source="WAKE", invoked=True, outcome="silent", delivered_event_ids=[])
        self.assertEqual([], live.open_requests(), "a suppressed message and a turn that ended in silence are complete")
        # A host receipt that promised an action and was never followed by a transport receipt is not waited for for ever.
        self.observed("r4", "discord:message:4", effective_disposition="WAKE")
        self.receipt("r4", "participant-host", wake_source="WAKE", invoked=True, outcome="unknown", delivered_event_ids=[])
        self.assertEqual(["r4"], live.open_requests())
        with mock.patch.object(discord_room, "TRANSPORT_GRACE_SECONDS", 0.0):
            self.assertEqual([], live.open_requests())

    def test_the_turns_and_the_actions_are_read_from_the_receipts_and_the_wire_paired_in_order(self):
        live = self.turns()
        for request, trigger, outcome, delivery in (
            ("r1", "discord:message:1", "sent", "sent"),
            ("r2", "discord:message:2", "sent", "sent"),
            ("r3", "discord:message:3", "silent", None),
            ("r4", "discord:message:4", "sent", "sent"),
        ):
            self.observed(request, trigger, effective_disposition="WAKE", classifier={"name": "m"})
            self.receipt(request, "participant-host", wake_source="WAKE", invoked=True, outcome=outcome, delivered_event_ids=[trigger])
            if delivery:
                self.receipt(request, "transport", delivery=delivery)
        self.write(content="An answer.", message_id="601", at="2026-10-11T05:00:01.000+00:00")
        self.write(content="A reply.", reply_to="2", message_id="602", at="2026-10-11T05:00:02.000+00:00")
        self.write(emoji="\N{EAR}", message_id="4", at="2026-10-11T05:00:03.000+00:00")
        self.write(content="not the bot's", status=403)  # a refused write is no write
        turns = {turn["request_id"]: turn for turn in live.turns()}
        self.assertEqual({"r1", "r2", "r3", "r4"}, set(turns))
        self.assertEqual({"kind": "message", "text": "An answer."}, turns["r1"]["result"])
        self.assertEqual({"kind": "reply", "text": "A reply.", "target_event_id": "discord:message:2"}, turns["r2"]["result"])
        self.assertEqual({"kind": "silence"}, turns["r3"]["result"])
        self.assertEqual({"kind": "reaction", "reaction": "\N{EAR}", "target_event_id": "discord:message:4"}, turns["r4"]["result"])
        self.assertTrue(all(turn["bound"] for turn in turns.values()))
        self.assertEqual("discord:message:1", turns["r1"]["trigger"])
        self.assertEqual("WAKE", turns["r1"]["source"])
        committed = {action["request_id"]: action for action in live.committed()}
        self.assertEqual({"r1", "r2", "r4"}, set(committed), "the silent turn committed nothing")
        self.assertEqual(
            ("2026-10-11T05:00:02.000+00:00", "reply", "sent", "discord:message:2"),
            (committed["r2"]["at"], committed["r2"]["kind"], committed["r2"]["delivery"], committed["r2"]["origin_event_id"]),
        )
        self.assertEqual(("reaction", "add"), (committed["r4"]["kind"], committed["r4"]["operation"]))

    def test_an_undelivered_action_takes_no_write_and_a_missing_write_leaves_the_action_unnamed(self):
        live = self.turns()
        for request, trigger, delivery in (("r1", "discord:message:1", "failed"), ("r2", "discord:message:2", "sent")):
            self.observed(request, trigger, effective_disposition="WAKE")
            self.receipt(request, "participant-host", wake_source="WAKE", invoked=True, outcome="sent", delivered_event_ids=[trigger])
            self.receipt(request, "transport", delivery=delivery, detail="refused")
        self.write(content="Only one write.", message_id="700")
        committed = {action["request_id"]: action for action in live.committed()}
        self.assertNotIn("kind", committed["r1"], "a failed delivery is paired with no write")
        self.assertEqual("failed", committed["r1"]["delivery"])
        self.assertEqual("Only one write.", committed["r2"]["text"])

    def test_each_receipt_is_stamped_when_first_read_the_turn_began_before_it_ended_and_a_half_written_line_waits(self):
        live = self.turns()
        self.observed("r1", "discord:message:1", effective_disposition="WAKE")
        live.poll()
        time.sleep(0.02)
        self.receipt("r1", "participant-host", wake_source="WAKE", invoked=True, outcome="silent", delivered_event_ids=[])
        (turn,) = live.turns()
        self.assertLess(turn["started"], turn["ended"])
        self.assertRegex(turn["started"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
        # A line the library has not finished writing is read when it is complete, not before and not twice.
        with open(self.state / "vigil.receipts.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"request_id": "r2", "stage": "observation", "writer": "x", "body": {"trigger_event_id": "discord:message:2"}})[:40])
        live.poll()
        self.assertNotIn("r2", live.requests)
        with open(self.state / "vigil.receipts.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"request_id": "r2", "stage": "observation", "writer": "x", "body": {"trigger_event_id": "discord:message:2"}})[40:] + "\n")
        live.poll()
        live.poll()
        self.assertEqual("discord:message:2", live.requests["r2"]["trigger"])
        self.assertEqual(["r1", "r2"], live._order)

    def test_the_attention_calls_are_counted_from_the_receipts_that_name_a_model_or_an_error(self):
        live = self.turns()
        self.observed("r1", "discord:message:1", effective_disposition="WAKE", classifier={"name": "m"})
        self.observed("r2", "discord:message:2", error={"code": "timeout", "detail": "slow"})
        self.observed("r3", "discord:message:3", classifier_not_invoked=True, cause="preattention-disabled")
        self.observed("r4", "discord:message:4")
        self.assertEqual(2, live.attention_calls())
        self.assertEqual({"observation", "attention"}, set(live.stages()["r1"]))

    def test_it_reads_on_a_thread_of_its_own_and_stopping_reads_once_more(self):
        live = discord_room.LiveTurns(self.room, interval=0.02)
        live.start()
        self.addCleanup(live.stop)
        self.observed("r1", "discord:message:1", effective_disposition="WAKE")
        deadline = time.monotonic() + 5
        while "r1" not in live.requests and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertIn("r1", live.requests, "nobody asked: the thread read it")
        live.stop()
        self.observed("r2", "discord:message:2", effective_disposition="WAKE")
        live.stop()
        self.assertIn("r2", live.requests, "stop reads what was written since the last read")
        self.assertEqual([], live.errors)


class ReferenceLegLiveTest(ReaderCase):
    def leg(self, **options):
        ctx = SimpleNamespace(
            directed=None, options=SimpleNamespace(scripted=False, discord_python=None, **options), original_env={}, attention={"model": "m"}
        )
        with mock.patch.object(discord_room, "DiscordRoom"):
            leg = discord_room.ReferenceLeg(ctx)
        leg.discord = SimpleNamespace(**vars(self.room), _written=None)
        leg.live = discord_room.LiveTurns(leg.discord)
        return leg

    def test_a_live_reference_reads_its_turns_from_outside_and_a_scripted_one_does_not(self):
        live = self.leg()
        self.assertIsNotNone(live.live)
        self.assertFalse(live.observes_unattended, "the process does not show which messages a turn read as unattended")
        with mock.patch.object(discord_room, "DiscordRoom"):
            scripted = discord_room.ReferenceLeg(SimpleNamespace(directed=None, options=SimpleNamespace(scripted=True, discord_python=None), original_env={}))
        self.assertIsNone(scripted.live)
        self.assertTrue(scripted.observes_unattended)

    def test_the_director_sees_a_turn_begin_and_the_lists_it_holds_are_replaced_in_place_keeping_the_moment(self):
        leg = self.leg()
        invocations, committed = leg.invocations, leg.committed
        self.assertFalse(leg.begun("discord:message:1"))
        self.observed("r1", "discord:message:1", effective_disposition="WAKE", classifier={"name": "m"})
        self.assertTrue(leg.begun("discord:message:1"), "the attention receipt is the earliest signal")
        self.receipt("r1", "participant-host", wake_source="WAKE", invoked=True, outcome="sent", delivered_event_ids=["discord:message:1"])
        self.receipt("r1", "transport", delivery="sent")
        self.write(content="Hello.", message_id="601")
        leg.refresh()
        self.assertEqual(["r1"], [turn["request_id"] for turn in invocations], "the same list the director holds")
        invocations[0]["moment"] = "the-scene"
        leg.refresh()
        self.assertEqual("the-scene", leg.invocations[0]["moment"])
        self.assertIs(invocations, leg.invocations)
        self.assertIs(committed, leg.committed)
        self.assertEqual("Hello.", leg.committed[0]["text"])
        self.assertEqual([{"request_id": "r1", "trigger": "discord:message:1", "model": "m", "disposition": "WAKE", "served": {"provider": "openrouter"}, "evidence": []}][0]["served"], leg.attention_calls[0]["served"])

    def test_the_model_calls_are_a_lower_bound_and_say_so(self):
        leg = self.leg()
        self.observed("r1", "discord:message:1", effective_disposition="WAKE", classifier={"name": "m"})
        self.receipt("r1", "participant-host", wake_source="WAKE", invoked=True, outcome="silent", delivered_event_ids=[])
        leg.refresh()
        calls = leg.model_calls()
        self.assertEqual((1, 1), (calls["agent"], calls["attention"]))
        self.assertIn("a lower bound", calls["basis"])

    def test_a_live_reference_is_settled_only_when_no_request_is_open_and_nothing_moved(self):
        leg = self.leg()
        leg._written = lambda: sum(path.stat().st_size for path in self.state.glob("*.jsonl"))
        with mock.patch.object(discord_room, "LIVE_QUIET_SECONDS", 0.3):
            self.assertTrue(leg.settle(5.0), "nothing at all is quiet")
            self.observed("r1", "discord:message:1", effective_disposition="WAKE")
            started = time.monotonic()
            self.assertFalse(leg.settle(0.8), "a woken turn is under way: nothing moving does not end the wait")
            self.assertGreaterEqual(time.monotonic() - started, 0.8)

            def finish() -> None:
                time.sleep(0.4)
                self.receipt("r1", "participant-host", wake_source="WAKE", invoked=True, outcome="silent", delivered_event_ids=[])

            thread = threading.Thread(target=finish)
            thread.start()
            started = time.monotonic()
            self.assertTrue(leg.settle(10.0))
            thread.join()
            self.assertGreaterEqual(time.monotonic() - started, 0.4 + 0.3 - 0.05, "settled after the host's receipt and a quiet of its own")
            # A message observed whose attention has not come back keeps the room open too.
            self.observed("r2", "discord:message:2")
            self.assertFalse(leg.settle(0.8))

    def test_what_a_turn_was_handed_is_the_host_receipts_packet_and_the_room_logs_record_of_the_message(self):
        leg = self.leg()
        events = {"discord:message:1": {"mentioned_actor_ids": ["discord:actor:9"], "reply_to_event_id": "discord:message:0"}, "discord:message:2": {}}
        with open(self.state / "vigil.observations.jsonl", "w", encoding="utf-8") as handle:
            for event_id, event in events.items():
                handle.write(json.dumps({"event": {"id": event_id, **event}}) + "\n")
        for request, trigger, delivered in (("r1", "discord:message:1", ["discord:message:1"]), ("r2", "discord:message:2", [])):
            self.observed(request, trigger, effective_disposition="WAKE")
            self.receipt(request, "participant-host", wake_source="WAKE", invoked=True, outcome="silent", delivered_event_ids=delivered)
        received = leg.received_live()
        self.assertEqual({"discord:message:1"}, set(received), "a turn whose packet did not hold its trigger was not handed it")
        self.assertEqual(["discord:actor:9"], received["discord:message:1"]["mentioned_actor_ids"])
        self.assertEqual("discord:message:0", received["discord:message:1"]["reply_to_event_id"])
        self.assertNotIn("own_moves", received["discord:message:1"], "the reference's memory is not shown to the probe")


# -- the model calls, and what the run says it cost ------------------------------------------------------------------


# -- the probe on a live scene: grades are reported, plumbing and secrets fail the run ----------------------------------


class FastSpend(spend.SpendWatch):
    """The spend watchdog, with a last reading that does not wait a minute and a first one that does not wait between tries."""

    first_read_pause = 0.0

    def settle(self, when, *, wait_seconds=0.3, interval_seconds=0.1):
        return super().settle(when, wait_seconds=wait_seconds, interval_seconds=interval_seconds)


def _fake_column(provider: Provider, hears, *, reach_latency: float = 0.0, lost=()):
    """A column for `run_probe`: the real director on a stand-in, an agent that asks the fake provider, and the record the checks read."""

    class FakeSceneLeg(probe.Leg):
        harness = "reference"
        actor_id = "discord:actor:9900"
        room_id = "9"
        scope = "discord:channel:9"

        @property
        def room(self):
            return None

        def prepare(self):
            spec = self.ctx.directed
            world, members = discord_room.world_spec("reference", [spec.plan.scene], agent="Vigil")
            self.fd = FakeDiscord(world, self.ctx.out).start()
            self.discord = discord_room.DiscordRoom(self.ctx, "reference")
            self.discord.fd, self.discord.members = self.fd, members
            self.inner = AgentLeg(self.discord, spec, provider, hears=hears, reach_latency=reach_latency, lost=lost)
            self.invocations, self.committed, self.attention_calls = self.inner.invocations, self.inner.committed, self.inner.attention_calls
            self.install = {"version": "discord.py 2.7.1", "expected": "discord.py 2.7.1", "executable": "/fake/reference"}
            self.actual_homes = {name: self.ctx.homes[name] for name in ("HOME", "TMPDIR")}
            config = self.ctx.base / "fake.nunchi.json"
            config.write_text("{}")
            self.configs.append(("fake config", config))
            self.ran("the fake column", ["fake"], self.ctx.env)

        def play(self, spec, *, settle_seconds):
            moment = directed.play_scene(self.inner, spec.plan, settle_seconds, live=True)
            for turn in self.invocations:
                turn["moment"] = spec.name
            return moment

        def room_effects(self):
            return [
                {"kind": "message", "where": "reference", "text": action.get("text"), "reply_to": None}
                if action["kind"] in ("message", "reply")
                else {"kind": "reaction", "where": "reference", "reaction": action.get("reaction")}
                for action in self.committed
                if action.get("delivery") == "sent"
            ]

        def judge(self, moments):
            for item, ok in zip(self.committed, checks.delivered(self.committed, self.room_effects(), harness_posts=False)):
                item["delivered"] = ok
            for moment in moments:
                directed.judge_scene(self, moment, self.ctx.directed.plan.scene)

        def receipts(self):
            return [
                {"request_id": turn["request_id"], "stage": "participant-host",
                 "body": {"invoked": True, "outcome": "sent" if any(a["request_id"] == turn["request_id"] for a in self.committed) else "silent"}}
                for turn in self.invocations
            ]

        def model_calls(self):
            return {"agent": len(provider.prompts), "attention": len(self.attention_calls), "basis": "the fake provider's calls"}

        def collect(self):
            self.reports["reference"] = {"verdict": "the fake column took part"}

        def close(self):
            self.fd.stop()

    return FakeSceneLeg


class ProbeTest(unittest.TestCase):
    def run_live(self, scene, decide, hears, *, key_status=200, spec=None, reach_latency=0.0, lost=(), opener=None, spend_class=None):
        provider = Provider(decide, key_status=key_status)
        self.addCleanup(provider.close)
        directory = Path(tempfile.mkdtemp(prefix="live-probe-"))
        self.addCleanup(shutil.rmtree, directory, True)
        net = directory / "net.json"
        net.write_text(json.dumps({"tls": {"cert": "c", "key": "k"}, "offline": False, "ci": True}))
        env = {**_live_env("reference"), routes.CANARY_ENV: CANARY, discord_room.NET_ENV: str(net)}
        item = spec or directed.spec(scene)
        route = discord_room.reference_route("anthropic/claude-haiku-4.5")
        options = probe.Options(
            harness="reference", out=directory / "out", scripted=False, room="discord", scene=scene, command=["test"], turn_timeout_seconds=30.0
        )
        printed = io.StringIO()
        with mock.patch.dict(os.environ, env), mock.patch.object(
            probe, "_room_parts", return_value=(_fake_column(provider, hears, reach_latency=reach_latency, lost=lost), (item,), route)
        ), mock.patch.object(probe, "SpendWatch", lambda key, budget: (spend_class or FastSpend)(key, budget, opener=(opener(provider) if opener else provider.opener))), contextlib.redirect_stdout(printed):
            before = dict(os.environ)
            code = probe.run_probe(options)
            self.assertEqual(before, dict(os.environ), "the probe restores this process's environment")
        out = directory / "out" / "reference"
        return code, out, printed.getvalue(), provider

    def test_a_grade_that_is_a_miss_is_reported_and_the_run_still_passes(self):
        speaks = lambda prompt: (0.0, {"move": "post", "text": "Nice, the build passed."})  # noqa: E731
        code, out, printed, provider = self.run_live("bot-status-report", speaks, lambda raw, scene: raw["id"] == "b1")
        run = json.loads((out / "run.json").read_text())
        self.assertEqual((0, "pass", "live"), (code, run["status"], run["mode"]), printed)
        self.assertEqual(
            ["pins-and-isolation", "record-complete", "turns-bound-and-ended", "turns-on-others-messages", "attention-judged",
             "one-room-action-per-turn", "no-leaks", "live-scene-plumbing", "spend-recorded"],
            [check["name"] for check in run["checks"]],
            "a live scene holds no script to its scene: there is no directed-outcomes and no scripted-outcomes",
        )
        self.assertTrue(all(check["ok"] for check in run["checks"]), run["checks"])
        (moment,) = run["moments"]
        self.assertEqual(checks.MISSES, moment["outcome"])
        (item,) = moment["graded"]
        self.assertEqual("miss", item["grade"]["visible"])
        summary = (out / "summary.md").read_text()
        self.assertIn("**Passed (reported, not judged):**", summary)
        self.assertIn("## Grade matrix (draft expectations, not reviewed)", summary)
        self.assertIn("`S!` miss/over-wake", summary)
        self.assertIn("Nice, the build passed.", summary, "what the agent said is in the page")
        self.assertEqual(json.loads((out / "scan.json").read_text())["clean"], True)
        # What it spent: the key's usage read before and after, the model calls counted, and the estimate beside it.
        spent = run["spend"]
        self.assertEqual({"agent": 1, "attention": 2}, {name: spent["model_calls"][name] for name in ("agent", "attention")})
        self.assertEqual(spend.estimate_usd("reference", spent["model_calls"]), spent["estimated_usd"])
        self.assertGreater(spent["spent_usd"], 0)
        self.assertIn("Cost of the run: recorded", summary)
        self.assertEqual(1, len(provider.prompts))

    def test_a_setup_the_agent_did_not_make_and_a_race_are_reported_and_do_not_fail_the_run_either(self):
        code, out, printed, _ = self.run_live("build-finishes-after-promise", quiet_agent, lambda raw, scene: raw["id"] == "z1")
        run = json.loads((out / "run.json").read_text())
        self.assertEqual((0, "pass"), (code, run["status"]), printed)
        self.assertEqual(checks.PRECONDITION, run["moments"][0]["outcome"])
        summary = (out / "summary.md").read_text()
        self.assertIn("precondition not met", summary)
        self.assertIn("**the scene stopped** after z1", summary)

        scene = _during_scene()
        item = directed.DirectedSpec(directed.plan(scene), directed.script_for(directed.plan(scene)))
        code, out, printed, _ = self.run_live("during", _answer_after(0.0), lambda raw, s: raw["id"] == "q1", spec=item, reach_latency=0.15)
        run = json.loads((out / "run.json").read_text())
        self.assertEqual((0, "pass"), (code, run["status"]), printed)
        self.assertEqual("raced", run["moments"][0]["holds"][0]["outcome"])
        self.assertEqual(checks.RACED, run["moments"][0]["outcome"])
        self.assertIn("hold raced", (out / "summary.md").read_text())


    def test_an_action_the_room_did_not_receive_fails_the_run_though_every_grade_is_only_reported(self):
        code, out, _, _ = self.run_live(
            "bot-status-report",
            lambda prompt: (0.0, {"move": "post", "text": "Nice.", "delivery": "failed"}),
            lambda raw, scene: raw["id"] == "b1",
        )
        run = json.loads((out / "run.json").read_text())
        self.assertEqual((probe.EXIT_FAILED, "fail"), (code, run["status"]))
        failed = {check["name"] for check in run["checks"] if not check["ok"]}
        self.assertIn("one-room-action-per-turn", failed)
        self.assertIn("**Failed:**", (out / "summary.md").read_text())

    def test_a_run_that_cannot_say_what_it_spent_fails(self):
        code, out, _, _ = self.run_live("bot-status-report", quiet_agent, lambda raw, scene: raw["id"] == "b1", key_status=500)
        run = json.loads((out / "run.json").read_text())
        self.assertEqual((probe.EXIT_FAILED, "fail"), (code, run["status"]))
        self.assertEqual({"spend-recorded"}, {check["name"] for check in run["checks"] if not check["ok"]})
        self.assertIn("gave a figure", next(check["detail"] for check in run["checks"] if check["name"] == "spend-recorded"))


# -- the summary and the cross-column matrix ---------------------------------------------------------------------------


def _live_run(*, harness="reference", reply=True, status="pass", failed=(), spent=0.1, estimated=0.2, calls=(5, 7), exit_text=None, delivered=True) -> dict:
    """A live run of `build-finishes-after-promise` as the probe records it: the agent's reply to Alice (or not), then the CI line."""

    scene = _scene_of("build-finishes-after-promise")
    played = _live_played(scene)
    z1, c1 = played["deliveries"][0]["event_id"], played["deliveries"][-1]["event_id"]
    played["lines"] = [{"event": "v1", "trigger": "z1", "kind": "reply", "text": "Sure, I'll tell you when it finishes.", "reaction": None, "cue": False}]
    turns = [{"request_id": "r1", "trigger": z1, "source": "WAKE", "started": _stamp(), "ended": _stamp()}]
    actions = []
    if reply:
        actions.append({"request_id": "r1", "kind": "reply", "text": "Will do.", "target_event_id": z1, "delivery": "sent", "delivered": True})
        turns.append({"request_id": "r2", "trigger": c1, "source": "WAKE"})
        actions.append({"request_id": "r2", "kind": "message", "text": "The nightly passed.", "delivery": "sent" if delivered else "failed", "delivered": delivered})
    else:
        played["stopped"] = {"after": "z1", "line": "v1", "why": "the turn on it ended in silence, where the scene has a reply or a post"}
        played["deliveries"] = played["deliveries"][:1]
        played["graded"] = directed.graded_moments(scene, played["deliveries"], live=True)
        played["reached"] = False
    calls_ = [{"trigger": z1, "disposition": "WAKE", "evidence": [z1]}, {"trigger": c1, "disposition": "WAKE", "evidence": [c1]}]
    directed.judge_scene(_live_leg(turns, actions, calls_), played, scene)
    played.update(name=scene.id, expect="directed")
    return {
        "harness": harness, "mode": "live", "status": status, "exit_code": 0 if status == "pass" else 1,
        "checks": [{"name": name, "ok": False, "detail": "x"} for name in failed] + [{"name": "no-leaks", "ok": True, "detail": ""}],
        "moments": [played],
        "models": {"agent": {"requested": "anthropic/claude-haiku-4.5", "served": []}, "attention": {"requested": "openai/gpt-6-luna@low", "served": []}},
        "spend": {"read": True, "budget_usd": 2, "limit": "soft", "readings": [{"usage": 1.0}], "spent_usd": spent, "estimated_usd": estimated,
                  "model_calls": {"agent": calls[0], "attention": calls[1], "basis": "counted"}},
        "errors": [],
    }


class SummaryTest(unittest.TestCase):
    def test_a_live_scene_run_says_its_grades_are_reported_and_what_the_agent_did_and_which_facts_attention_cited(self):
        text = record.summary_markdown(_live_run())
        self.assertIn("**Passed (reported, not judged):**", text)
        self.assertNotIn("This checks the director and the grader, not a model", text)
        self.assertIn("## Grade matrix (draft expectations, not reviewed)", text)
        self.assertIn("none is a failure", text)
        self.assertIn("| build-finishes-after-promise | the nightly finishes | speak (pass) | `S` fits/ok |", text)
        self.assertIn("### What the agent did, and the facts attention cited", text)
        self.assertIn("the nightly finishes: message \"The nightly passed.\".", text)
        self.assertIn("  - cited: this CI line says the nightly finished and passed", text)
        self.assertIn("  - not cited: Vigil told Alice it would tell her when the nightly finishes", text, "z1 and v1 are not in attention's evidence for c1")
        self.assertIn(
            "the scene has the agent's earlier line v1 (reply \"Sure, I'll tell you when it finishes.\", on z1). The live agent did this instead: "
            "reply 'Will do.' about", text,
        )
        self.assertIn("Model calls counted: agent 5, attention 7 (counted)", text)
        self.assertIn("Cost of the run: recorded 0.1 (the key's usage, which lags and counts other runs on the key), estimated 0.2", text)

    def test_a_moment_whose_setup_was_not_made_reads_precondition_not_met_beside_what_the_agent_did_and_the_scene_stopped(self):
        text = record.summary_markdown(_live_run(reply=False))
        self.assertIn("| build-finishes-after-promise | the nightly finishes | speak (pass) | `-` precondition not met |", text)
        self.assertIn("  - precondition not met: the agent's earlier line v1 (on z1) did not land: the turn ended in silence", text)
        self.assertIn("**the scene stopped** after z1, because the agent's earlier line v1 did not land", text)
        self.assertIn("**did not land**", text)
        self.assertNotIn("fits/ok", text)

    def test_a_hold_is_named_as_timing_and_a_run_that_failed_a_hard_check_is_failed_whatever_its_grades(self):
        run = _live_run(status="fail", failed=("one-room-action-per-turn",))
        run["moments"][0]["holds"] = [
            {"trigger": "z1", "kind": "unattended", "events": ["s1", "z2"], "outcome": "raced", "detail": "the agent moved first", "live": True}
        ]
        text = record.summary_markdown(run)
        self.assertIn("timing, nothing held the live agent): **raced** (the agent moved first)", text)
        self.assertTrue(text.index("**Failed:**") < text.index("## Grade matrix"))
        self.assertNotIn("Passed (reported", text)


class LegendAndRowTest(unittest.TestCase):
    """The legend lists every code a cell prints, and a Moments row agrees with its cells (run 38135715452: `E` was in no legend, and a row read `misses` over cells with no `!`)."""

    # One item for each way `score.symbol` makes a letter.
    LETTERS = {
        "E": {"result": "woken", "provider_error": True}, "-": {"result": "unsupported"}, "W": {"result": "woken"},
        "q": {"result": "stay_quiet", "by": "agent"}, "Q": {"result": "stay_quiet", "by": "attention"},
        "m": {"result": "mhm"}, "S": {"result": "speak"}, "O": {"result": "other"},
    }

    def test_the_letters_the_suite_can_print_are_the_ones_this_test_lists(self):
        from evals.behavior import score

        self.assertEqual({letter: letter for letter in self.LETTERS}, {letter: score.symbol(item) for letter, item in self.LETTERS.items()})


    def test_a_moments_row_over_a_turn_that_did_not_deliver_says_so_and_not_misses(self):
        text = record.summary_markdown(_live_run(delivered=False))
        row = next(line for line in text.splitlines() if line.startswith("| build-finishes-after-promise | directed |"))
        self.assertTrue(row.endswith("| did not fit: the turn's action did not reach the room (E) |"), row)
        self.assertNotIn("misses", row)
        # The recorded outcome is what the checks read, and it is unchanged.
        self.assertEqual(checks.MISSES, _live_run(delivered=False)["moments"][0]["outcome"])

    def test_a_row_says_misses_exactly_where_a_cell_carries_a_bang_and_otherwise_names_what_did_not_fit(self):
        from evals.behavior import score

        found = set()
        for visible in ("fits", "miss", "unlisted", "agent-decides"):
            for step1 in ("ok", "over-wake", "over-suppress", "not judged"):
                for hold in (None, "held", "unseen", "unmerged"):
                    for error in (False, True):
                        item = {"result": "woken" if error or visible == "agent-decides" else "speak", "provider_error": error, "by": None,
                                "grade": {"visible": visible, "step1": step1}, **({"hold": hold} if hold else {})}
                        clean = visible == "fits" and step1 == "ok" and hold in (None, "held") and not error
                        moment = {"outcome": checks.FITS if clean else checks.MISSES, "graded": [item]}
                        words = record._outcome_words(moment)
                        bang = "!" in score.cell([item])
                        with self.subTest(visible=visible, step1=step1, hold=hold, error=error):
                            self.assertEqual(bang, words == checks.MISSES, (score.cell([item]), words))
                            if not bang and not clean:
                                self.assertTrue(words.startswith("did not fit: "), words)
                        found.add(words)
        self.assertIn("did not fit: the turn's action did not reach the room (E)", found)
        self.assertIn("did not fit: a move the draft does not list (?)", found)
        self.assertIn("did not fit: woken, with no turn on it (W)", found)
        self.assertIn("did not fit: step 1 over-wake", found)
        self.assertIn("did not fit: hold unseen", found)
        # What is not a miss keeps its word, and a moment with no grade keeps the one it was recorded with.
        for outcome in (checks.FITS, checks.RACED, checks.PRECONDITION, checks.NOT_DELIVERED):
            self.assertEqual(outcome, record._outcome_words({"outcome": outcome, "graded": [{"grade": {"visible": "fits", "step1": "ok"}}]}))
        self.assertEqual(checks.MISSES, record._outcome_words({"outcome": checks.MISSES, "graded": []}))


def _write_run(root: Path, number: int, scene: str, column: str, run: dict | None, exit_code: int | None = 0) -> None:
    if run is not None:
        directory = root / f"pass-{number}" / scene / column
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "run.json").write_text(json.dumps(run))
    if exit_code is not None:
        with open(root / "status.tsv", "a", encoding="utf-8") as handle:
            handle.write(f"{number}\t{scene}\t{column}\t{exit_code}\n")


# -- the workflow --------------------------------------------------------------------------------------------------------


def load_default_scenes() -> str:
    return " ".join(FIRST_FOUR)


# -- the checks a live agent's own words touch ---------------------------------------------------------------------------


class ReconciledTest(unittest.TestCase):
    ACTION = lambda self, request: {"request_id": request, "kind": "message", "text": "Got it.", "delivery": "sent"}  # noqa: E731
    WRITE = {"kind": "message", "content": "Got it.", "reply_to": None}

    def test_two_actions_with_the_same_words_take_one_write_each_and_a_write_nothing_took_still_fails(self):
        action = self.ACTION
        self.assertTrue(checks.discord_writes_reconciled([action("r1"), action("r2")], [dict(self.WRITE), dict(self.WRITE)]).ok, "a live agent can say it twice")
        extra = checks.discord_writes_reconciled([action("r1")], [dict(self.WRITE), dict(self.WRITE)])
        self.assertFalse(extra.ok)
        self.assertIn("no committed action matches", extra.detail)
        missing = checks.discord_writes_reconciled([action("r1"), action("r2")], [dict(self.WRITE)])
        self.assertFalse(missing.ok)
        self.assertIn("matches 0 write(s)", missing.detail)


class RememberedTest(unittest.TestCase):
    EVENT = "discord:message:1"

    def moment(self, line: dict, memory: list[dict]) -> dict:
        """A scene whose agent made ``line`` on the first message and was handed ``memory`` at the next turn."""

        first = {"scene_event": "z1", "event_id": self.EVENT, "received": {"trigger": self.EVENT, "own_moves": []}}
        later = {"scene_event": "z2", "event_id": "discord:message:2", "received": {"trigger": "discord:message:2", "own_moves": memory}}
        return {"expect": "directed", "name": "s", "deliveries": [first, later], "turns": [], "graded": [], "lines": [{"event_id": self.EVENT, **line}]}

    def check(self, line: dict, memory: list[dict]):
        return checks.discord_addressing([self.moment(line, memory)], agent="a", writes=[])

    def test_a_scripted_line_is_remembered_as_the_scene_has_it_and_a_live_one_as_the_agent_did_it(self):
        scene_line = {"kind": "reply", "text": "The scene's words.", "actions": [{"delivered": True}]}
        self.assertTrue(self.check(scene_line, [{"kind": "reply", "about_event_id": self.EVENT}]).ok)
        self.assertFalse(self.check(scene_line, [{"kind": "reaction", "about_event_id": self.EVENT, "reaction": "\N{EAR}"}]).ok)
        # Live, the line is whatever the agent did: a nod where the scene has a reply is remembered as a nod.
        live = {**scene_line, "live": True, "actions": [{"kind": "reaction", "reaction": "\N{EYES}", "target_event_id": self.EVENT, "delivered": True}]}
        self.assertTrue(self.check(live, [{"kind": "reaction", "about_event_id": self.EVENT, "reaction": "\N{EYES}"}]).ok)
        failed = self.check(live, [{"kind": "reply", "about_event_id": self.EVENT}])
        self.assertFalse(failed.ok)
        self.assertIn("does not hold the agent's earlier reaction", failed.detail)
        # Its words, for a plain post, are the agent's own too.
        post = {"kind": "message", "text": "The scene's words.", "live": True, "actions": [{"kind": "message", "text": "Nothing to report.", "delivered": True}]}
        self.assertTrue(self.check(post, [{"kind": "message", "text": "Nothing to report."}]).ok)
        self.assertFalse(self.check(post, [{"kind": "message", "text": "The scene's words."}]).ok)




# -- review fixes: the plumbing a live scene still fails on, what a hold can prove, the reader, the spend, the workflow ------------------------


def _real_observation(trigger: str) -> dict:
    """The body of an observation receipt as a real reference run writes it."""

    return {
        "byte_count": 485, "continuity_scope_id": "discord:channel:9", "event_count": 1, "included_event_ids": [trigger],
        "schema_version": 2, "trigger_event_id": trigger,
        "coverage": {"continuity": "unknown", "has_gaps": True, "has_more_after": False, "has_more_before": False, "has_restart_gap": True},
    }


def _real_attention(trigger: str, disposition: str = "WAKE") -> dict:
    return {
        "classifier": {"model": "openai/gpt-6-luna", "name": "participant-attention", "provider": "openrouter"},
        "classifier_disposition": disposition, "effective_disposition": disposition, "evidence_event_ids": [trigger],
        "policy_provenance": "rehearsal:probe@1", "routing_audit": {"margin_status": "active", "override_cause": "none", "valve": "none"},
    }


def _real_host(*delivered: str, outcome: str = "unknown") -> dict:
    return {
        "delivered_event_ids": list(delivered), "expansion_calls": 1, "invoked": True, "outcome": outcome,
        "packet_byte_count": 485, "packet_event_count": len(delivered), "wake_source": "WAKE",
    }


class RecallTest(ReaderCase):
    """A message the pipeline judges for the memory alone, while a turn ran, gets a wake and no turn (`NunchiV2Pipeline._recall_midturn`)."""

    def request(self, request: str, trigger: str, disposition: str = "WAKE", *, host: dict | None = None, transport: str | None = None) -> None:
        self.receipt(request, "observation", **_real_observation(trigger))
        self.receipt(request, "attention", **_real_attention(trigger, disposition))
        if host is not None:
            self.receipt(request, "participant-host", **host)
        if transport:
            self.receipt(request, "transport", delivery=transport, detail="discord:message:900")

    def leg(self):
        ctx = SimpleNamespace(directed=None, options=SimpleNamespace(scripted=False, discord_python=None), original_env={}, attention={"model": "m"})
        with mock.patch.object(discord_room, "DiscordRoom"):
            leg = discord_room.ReferenceLeg(ctx)
        leg.discord = SimpleNamespace(**vars(self.room), _written=None)
        leg.live = discord_room.LiveTurns(leg.discord)
        leg._written = lambda: sum(path.stat().st_size for path in self.state.glob("*.jsonl"))
        return leg

    def test_a_recalled_wake_is_no_turn_once_the_newest_message_has_been_judged_and_it_neither_begins_nor_keeps_the_room_open(self):
        live = discord_room.LiveTurns(self.room)
        # The agent was busy on k1; m1 and m2 arrived meanwhile. m1 is judged for the memory (a wake, and no turn), m2 is the anchor.
        self.request("k1", "discord:message:K", host=_real_host("discord:message:K", outcome="sent"), transport="sent")
        self.request("m1", "discord:message:M1")
        self.assertTrue(live.begun("discord:message:M1"), "until something is judged after it, it may still be a turn about to begin")
        self.assertEqual(["m1"], live.open_requests())
        self.receipt("m2", "observation", **_real_observation("discord:message:M2"))
        self.assertIn("m1", live.open_requests(), "the anchor has not been judged yet")
        self.receipt("m2", "attention", **_real_attention("discord:message:M2"))
        self.assertEqual(["m2"], live.open_requests(), "m2's attention is back: m1 was judged for the memory alone, and m2 is the turn that comes")
        self.assertFalse(live.begun("discord:message:M1"), "no turn ever begins on a recalled message")
        self.assertTrue(live.begun("discord:message:M2"))
        self.receipt("m2", "participant-host", **_real_host("discord:message:M2", outcome="silent"))
        self.assertEqual([], live.open_requests(), "settled: the recalled wake does not hold the room open forever")
        self.assertEqual(["k1", "m2"], [turn["request_id"] for turn in live.turns()], "and it is not a turn")

    def test_a_recalled_wake_before_an_anchor_attention_suppressed_is_no_turn_either(self):
        live = discord_room.LiveTurns(self.room)
        self.request("m1", "discord:message:M1")
        self.request("m2", "discord:message:M2", "SUPPRESS")
        self.assertEqual([], live.open_requests(), "the anchor was suppressed, so no host receipt will ever come for m1 or m2")
        self.assertFalse(live.begun("discord:message:M1"))

    def test_a_woken_request_nothing_followed_is_a_turn_about_to_begin_until_a_host_could_not_still_be_taking_it(self):
        live = discord_room.LiveTurns(self.room)
        self.request("m1", "discord:message:M1")
        self.assertEqual(["m1"], live.open_requests())
        stamped = live.requests["m1"]["seen"]["attention"]
        later = discord_room._parse_stamp(stamped) + discord_room.LIVE_PARTICIPANT_TIMEOUT_SECONDS + discord_room.TRANSPORT_GRACE_SECONDS + 1
        with mock.patch.object(discord_room.time, "time", return_value=later):
            self.assertEqual([], live.open_requests(), "older than the participant's timeout and its grace: no turn is coming")
            self.assertFalse(live.begun("discord:message:M1"))

    def test_the_live_reference_settles_after_a_recall_and_a_turn(self):
        leg = self.leg()
        self.request("m1", "discord:message:M1")
        self.request("m2", "discord:message:M2", host=_real_host("discord:message:M2", outcome="sent"), transport="sent")
        self.write(content="Done.", message_id="700")
        with mock.patch.object(discord_room, "LIVE_QUIET_SECONDS", 0.3):
            started = time.monotonic()
            self.assertTrue(leg.settle(5.0), "the recalled m1 is not an open request")
            self.assertLess(time.monotonic() - started, 4.0)
        leg.refresh()
        self.assertTrue(leg.begun("discord:message:M2"))
        self.assertFalse(leg.begun("discord:message:M1"))

    def test_the_turns_record_the_first_packet_the_host_handed_the_agent(self):
        live = discord_room.LiveTurns(self.room)
        self.request("m2", "discord:message:M2", host=_real_host("discord:message:M1", "discord:message:M2", outcome="silent"))
        (turn,) = live.turns()
        self.assertEqual(["discord:message:M1", "discord:message:M2"], turn["first_packet"])


class PlumbingTest(unittest.TestCase):
    ACTION = {"request_id": "r1", "kind": "message", "text": "Hi.", "delivery": "sent", "delivered": True}
    CALL = {"tool": "room_send", "arguments": {"text": "Hi."}, "completed": True}

    def moment(self, *, observed=True, live=True):
        return {
            "expect": "directed", "name": "s", "played_live": live,
            "deliveries": [{"scene_event": "c1", "observed": True}, {"scene_event": "b1", "observed": observed, "note": "it never reached Nunchi"}],
        }

    def test_a_message_the_director_posted_that_never_reached_nunchi_fails_a_live_scene_whatever_the_grades(self):
        held = checks.live_scene_plumbing([self.moment()])
        self.assertTrue(held.ok, held.detail)
        lost = checks.live_scene_plumbing([self.moment(observed=False)])
        self.assertFalse(lost.ok)
        self.assertIn("s, b1: the director's message never reached Nunchi (it never reached Nunchi)", lost.detail)
        self.assertEqual("live-scene-plumbing", lost.name)
        # A scripted record is `directed_outcomes`'s, not this check's: with no live scene played there is nothing to hold.
        self.assertFalse(checks.live_scene_plumbing([self.moment(live=False)]).ok)

    def test_a_scene_that_stopped_posted_no_more_and_the_messages_it_did_not_post_are_not_missing(self):
        stopped = {**self.moment(), "deliveries": [{"scene_event": "c1", "observed": True}], "stopped": {"after": "c1"}}
        self.assertTrue(checks.live_scene_plumbing([stopped]).ok)

    def test_each_action_a_harness_delivered_is_backed_by_a_completed_room_tool_call_and_the_reference_passes_none(self):
        moments = [self.moment()]
        self.assertTrue(checks.live_scene_plumbing(moments, committed=[self.ACTION], room_tool_calls=[self.CALL]).ok)
        missing = checks.live_scene_plumbing(moments, committed=[self.ACTION], room_tool_calls=[])
        self.assertFalse(missing.ok)
        self.assertIn("reached the room, but the harness showed no completed room tool call for it", missing.detail)
        self.assertFalse(checks.live_scene_plumbing(moments, committed=[self.ACTION], room_tool_calls=[{**self.CALL, "completed": False}]).ok)
        # One call for one action.
        twice = [self.ACTION, {**self.ACTION, "request_id": "r2"}]
        self.assertFalse(checks.live_scene_plumbing(moments, committed=twice, room_tool_calls=[self.CALL]).ok)
        self.assertTrue(checks.live_scene_plumbing(moments, committed=twice, room_tool_calls=[self.CALL, self.CALL]).ok)
        # An action that did not reach the room needs no call; the reference passes no calls at all.
        self.assertTrue(checks.live_scene_plumbing(moments, committed=[{**self.ACTION, "delivered": False}], room_tool_calls=[]).ok)
        self.assertTrue(checks.live_scene_plumbing(moments, committed=[self.ACTION], room_tool_calls=None).ok)


    def test_a_live_run_waits_longer_for_a_message_to_reach_nunchi_than_a_scripted_one(self):
        self.assertGreaterEqual(discord_room.LIVE_REACH_SECONDS, 30.0, "a harness column can still be booting when its first message is posted")
        self.assertGreater(discord_room.LIVE_REACH_SECONDS, discord_room.REACH_SECONDS)

        def waited(scripted: bool) -> float:
            room = object.__new__(discord_room.DiscordRoom)
            room.ctx = SimpleNamespace(options=SimpleNamespace(scripted=scripted))
            room.state = Path("unused")
            clock = [0.0]

            def sleep(seconds: float) -> None:
                clock[0] += max(seconds, 1.0)

            with mock.patch.object(discord_room, "delivery_audits", return_value=[]), mock.patch.object(
                discord_room.time, "monotonic", lambda: clock[0]
            ), mock.patch.object(discord_room.time, "sleep", sleep):
                delivery = room.reach({"message_id": "1"})
            self.assertFalse(delivery["observed"])
            return clock[0]

        self.assertTrue(discord_room.REACH_SECONDS <= waited(True) < discord_room.REACH_SECONDS + 1.5)
        self.assertTrue(discord_room.LIVE_REACH_SECONDS <= waited(False) < discord_room.LIVE_REACH_SECONDS + 1.5)


class HoldProofTest(DirectorCase):
    """What a hold can prove: the turn's window, the first packet, and a column whose record shows nothing."""

    def hold(self, scene=None, **options):
        leg, spec, played = self.play(scene or _during_scene(), **options)
        self.judge(leg, spec, played)
        (hold,) = played["holds"]
        return leg, played, hold


    def test_the_judge_asks_what_the_turn_was_shown_only_until_it_moved_or_ended(self):
        leg, played, hold = self.hold(decide=_answer_after(1.2), reach_latency=0.15, shown=lambda ids, since: list(ids))
        ids, since, until = leg.shown_asked[0]
        self.assertEqual(hold["turn"]["moved_at"], until, "the turn moved: what it was shown after that is another turn's")
        self.assertEqual(hold["turn"]["started"], since)
        leg, played, hold = self.hold(decide=_answer_after(1.2, "silent"), reach_latency=0.15, shown=lambda ids, since: list(ids))
        self.assertIsNone(hold["turn"]["moved_at"])
        self.assertEqual(hold["turn"]["ended"], leg.shown_asked[0][2], "a turn that never moved is bounded by its end")

    def test_a_hold_the_columns_record_cannot_prove_is_held_on_timing_alone_and_the_matrix_and_the_summary_say_so(self):
        leg, played, hold = self.hold(decide=_answer_after(1.2), reach_latency=0.15, shown=None)
        self.assertEqual("held", hold["outcome"])
        (item,) = played["graded"]
        self.assertTrue(item["hold_unproven"])
        cell = record._matrix_cell(item)
        self.assertIn("hold held (unproven: timing alone)", cell)
        page = "\n".join(record._played_lines({"moments": [{**played, "name": "s", "expect": "directed"}]}))
        self.assertIn("**held, unproven**", page)
        # A column that shows what the turn was shown proves it, and says nothing of the kind.
        leg, played, hold = self.hold(decide=_answer_after(1.2), reach_latency=0.15, shown=lambda ids, since: list(ids))
        self.assertNotIn("hold_unproven", played["graded"][0])
        self.assertNotIn("unproven", record._matrix_cell(played["graded"][0]))

    def test_a_held_message_already_in_the_first_packet_of_the_turn_raced_it_did_not_arrive_in_the_turn(self):
        leg, played, hold = self.hold(decide=_answer_after(1.2), reach_latency=0.15, shown=None, packet=("a1",))
        self.assertEqual("raced", hold["outcome"], hold["detail"])
        self.assertIn("a1 was already in the first packet handed to the agent", hold["detail"])
        self.assertEqual(checks.RACED, played["outcome"])
        self.assertEqual(1, len(hold["turn"]["first_packet"]) - 1, "the trigger and the held message")
        # Without it in the packet, the same timing holds.
        leg, played, hold = self.hold(decide=_answer_after(1.2), reach_latency=0.15, shown=None)
        self.assertEqual("held", hold["outcome"])


class AttentionErrorTest(unittest.TestCase):
    def test_an_attention_call_that_failed_judged_nothing_so_step_1_is_not_judged_and_the_error_is_named(self):
        scene = _scene_of("bot-status-report")
        played = _live_played(scene)
        b1 = played["deliveries"][1]["event_id"]
        leg = _live_leg([{"request_id": "r1", "trigger": b1, "source": "ERROR_FALLBACK"}], [],
                        [{"trigger": b1, "error": "TimeoutError: attention model did not answer"}])
        directed.judge_scene(leg, played, scene)
        (item,) = played["graded"]
        self.assertEqual("not judged", item["grade"]["step1"], "the error fallback woke the agent; that is not attention's reading")
        self.assertEqual("TimeoutError: attention model did not answer", item["attention_error"])
        cell = record._matrix_cell(item)
        self.assertIn("fits/not judged", cell)
        self.assertIn("attention error: TimeoutError: attention model did not answer", cell)
        # A judgment that did arrive is graded as before: the same woken agent, over-wake.
        played = _live_played(scene)
        leg = _live_leg([{"request_id": "r1", "trigger": b1, "source": "WAKE"}], [], [{"trigger": b1, "disposition": "WAKE", "evidence": [b1]}])
        directed.judge_scene(leg, played, scene)
        self.assertEqual("over-wake", played["graded"][0]["grade"]["step1"])
        self.assertNotIn("attention_error", played["graded"][0])


class NotJudgedCellTest(unittest.TestCase):
    pass

class ReconciledOrderTest(unittest.TestCase):
    def test_a_sent_action_takes_its_write_before_a_failed_one_with_the_same_words_whatever_the_order(self):
        action = lambda rid, delivery: {"request_id": rid, "kind": "message", "text": "A", "delivery": delivery}  # noqa: E731
        write = {"kind": "message", "content": "A", "reply_to": None}
        for order in ((("r1", "failed"), ("r2", "sent")), (("r1", "sent"), ("r2", "failed"))):
            with self.subTest(order=order):
                done = checks.discord_writes_reconciled([action(*item) for item in order], [dict(write)])
                self.assertTrue(done.ok, done.detail)
        done = checks.discord_writes_reconciled([action("r1", "failed"), action("r2", "sent")], [])
        self.assertFalse(done.ok, "a sent action with no write at all still fails")
        done = checks.discord_writes_reconciled([action("r1", "failed"), action("r2", "sent")], [dict(write), dict(write)])
        self.assertTrue(done.ok, "a failed action whose acknowledgement was lost may match a write of its own")


class SpendRetryTest(unittest.TestCase):
    def test_the_first_reading_is_tried_again_up_to_three_times_and_every_try_is_kept(self):
        calls = []

        def opener(request, timeout=20):
            calls.append(1)
            if len(calls) < 3:
                raise urllib.error.HTTPError("u", 502, "bad gateway", {}, None)
            return _Response({"data": {"usage": 5.0}})

        watch = FastSpend("k", 2.0, opener=opener)
        entry = watch.read_first("before the first moment")
        self.assertEqual(5.0, entry["usage"])
        self.assertEqual(3, len(calls))
        self.assertEqual(["before the first moment", "before the first moment (again)", "before the first moment (again)"], [r["when"] for r in watch.readings])
        self.assertEqual(["HTTP 502", "HTTP 502"], [r["error"] for r in watch.readings[:2]])
        # It gives up after three, and a scripted run (no key) reads once.
        calls.clear()

        def down(request, timeout=20):
            calls.append(1)
            raise urllib.error.URLError("down")

        always = FastSpend("k", 2.0, opener=down)
        self.assertNotIn("usage", always.read_first("first"))
        self.assertEqual(3, len(calls))
        scripted = FastSpend(None, 2.0)
        scripted.read_first("first")
        self.assertEqual(1, len(scripted.readings), "a scripted run reads nothing and does not try again")

    def test_the_default_pause_between_tries_is_real_and_the_budget_is_finite(self):
        self.assertGreater(spend.SpendWatch.first_read_pause, 0)
        self.assertEqual(3, spend.FIRST_READ_TRIES)
        for bad in (float("nan"), float("inf"), 0, -1):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                spend.SpendWatch("k", bad)
        for bad in ("nan", "inf", "0", "-3"):
            with self.subTest(argument=bad), contextlib.redirect_stderr(io.StringIO()) as stderr:
                code = probe.main(["--harness", "reference", f"--budget-usd={bad}", "--out", "x"])
            self.assertNotEqual(0, code, bad)
            self.assertIn("--budget-usd must be a positive, finite number", stderr.getvalue())

    def test_the_check_names_the_error_of_each_failed_reading_and_a_turn_with_no_agent_call_counted_is_broken(self):
        document = {"spend": {"read": True, "readings": [{"when": "before the first moment", "error": "HTTP 502"}, {"when": "after the last moment", "usage": 3.0}],
                              "model_calls": {"agent": 2, "attention": 3}}}
        done = checks.spend_recorded(document, turns=2)
        self.assertFalse(done.ok)
        self.assertIn("HTTP 502 (before the first moment)", done.detail)
        document["spend"]["readings"][0] = {"when": "first", "usage": 1.0}
        self.assertTrue(checks.spend_recorded(document, turns=2).ok)
        document["spend"]["model_calls"]["agent"] = 0
        broken = checks.spend_recorded(document, turns=2)
        self.assertFalse(broken.ok)
        self.assertIn("2 turn(s) ran but no agent model call was counted", broken.detail)
        self.assertTrue(checks.spend_recorded(document, turns=0).ok, "no turn ran, so no call is expected")


class _Response:
    def __init__(self, document: dict) -> None:
        self._text = json.dumps(document)

    def __enter__(self):
        return io.StringIO(self._text)

    def __exit__(self, *_exc) -> None:
        return None


class ProbeReviewTest(unittest.TestCase):
    """The probe-level cases of the review: a lost message, a transient first read."""

    run_live = ProbeTest.run_live

    def test_a_director_message_that_never_reached_nunchi_fails_a_live_run_though_every_grade_is_only_reported(self):
        code, out, printed, _ = self.run_live("bot-status-report", quiet_agent, lambda raw, scene: raw["id"] == "b1", lost={"c1"})
        run = json.loads((out / "run.json").read_text())
        self.assertEqual((probe.EXIT_FAILED, "fail"), (code, run["status"]), printed)
        failed = {check["name"]: check["detail"] for check in run["checks"] if not check["ok"]}
        self.assertEqual({"live-scene-plumbing"}, set(failed))
        self.assertIn("c1: the director's message never reached Nunchi", failed["live-scene-plumbing"])
        self.assertIn("**Failed:**", (out / "summary.md").read_text())

    def test_a_transient_failure_of_the_first_usage_read_does_not_fail_the_run_and_a_figure_that_lags_never_did(self):
        def flaky(provider):
            state = {"n": 0}

            def opener(request, timeout=20):
                state["n"] += 1
                if state["n"] == 1:
                    raise urllib.error.HTTPError("u", 502, "bad gateway", {}, None)
                return provider.opener(request, timeout)

            return opener

        code, out, printed, _ = self.run_live("bot-status-report", quiet_agent, lambda raw, scene: raw["id"] == "b1", opener=flaky)
        run = json.loads((out / "run.json").read_text())
        self.assertEqual((0, "pass"), (code, run["status"]), printed)
        self.assertEqual("before the first moment (again)", run["spend"]["readings"][1]["when"])
        # A key whose usage never moves lags; the run still records it and passes.
        still = lambda provider: (lambda request, timeout=20: _Response({"data": {"usage": 1.0}}))  # noqa: E731
        code, out, printed, _ = self.run_live("bot-status-report", quiet_agent, lambda raw, scene: raw["id"] == "b1", opener=still)
        self.assertEqual(0, code, printed)

    def test_a_run_whose_key_cannot_be_read_names_why_in_the_summary(self):
        code, out, _, _ = self.run_live("bot-status-report", quiet_agent, lambda raw, scene: raw["id"] == "b1", key_status=500)
        detail = next(check["detail"] for check in json.loads((out / "run.json").read_text())["checks"] if check["name"] == "spend-recorded")
        self.assertIn("HTTP 500", detail)
        self.assertIn("HTTP 500", (out / "summary.md").read_text())


class PreflightTest(unittest.TestCase):
    def leg(self, provider: Provider):
        with mock.patch.object(discord_room, "DiscordRoom"):
            leg = discord_room.ReferenceLeg(SimpleNamespace(
                directed=None, options=SimpleNamespace(scripted=False, discord_python=None), original_env={}, attention={"model": "m"},
                profile={"instructions": "You are Vigil."}, route=SimpleNamespace(model="anthropic/claude-haiku-4.5"),
            ))
        leg.actor_id = "discord:actor:9"
        leg.participant_base_url = provider._server.base_url
        return leg

    def provider(self, answer, *, status=200):
        provider = Provider(lambda prompt: (0.0, answer), chat_status=status)
        self.addCleanup(provider.close)
        return provider

    def test_the_reference_makes_one_call_with_the_body_its_participant_sends_before_anything_starts(self):
        provider = self.provider({"kind": "silence"})
        leg = self.leg(provider)
        leg.preflight("sk-test", "0" * 64)
        (body,) = provider.bodies
        self.assertEqual("anthropic/claude-haiku-4.5", body["model"])
        self.assertEqual({"type": "json_object"}, body["response_format"], "the thing a provider may not honor")
        self.assertEqual(0.2, body["temperature"])
        self.assertEqual(["system", "user"], [message["role"] for message in body["messages"]])
        self.assertEqual("Bearer sk-test", provider.auth[0])
        self.assertEqual(1, leg.preflight_calls)
        self.assertEqual(1, leg.model_calls()["agent"], "it is a model call and is counted")
        self.assertIn("preflight", leg.model_calls()["basis"])

    def test_a_provider_that_does_not_honor_the_request_stops_the_run_with_its_answer_and_the_call_still_counts(self):
        provider = self.provider({"error": "x"}, status=400)
        leg = self.leg(provider)
        with self.assertRaises(discord_room.CouldNotRun) as caught:
            leg.preflight("sk-test", "0" * 64)
        self.assertIn("did not answer the request it will send", str(caught.exception))
        self.assertIn("HTTP 400", str(caught.exception))
        self.assertIn("response_format", str(caught.exception), "the provider's own words")
        self.assertEqual(1, leg.preflight_calls)

    def test_an_answer_that_is_not_a_json_object_stops_the_run_naming_what_came_back(self):
        leg = self.leg(self.provider("Sorry, I cannot answer in JSON."))
        with self.assertRaises(discord_room.CouldNotRun) as caught:
            leg.preflight("sk-test", "0" * 64)
        self.assertIn("not a JSON object", str(caught.exception))
        self.assertIn("Sorry, I cannot answer in JSON.", str(caught.exception))

    def prepare(self, provider: Provider, *, scripted: bool = False):
        """`ReferenceLeg.prepare` with the stand-in and the process replaced by recorders: the order things happen in."""

        events: list[str] = []
        base = Path(tempfile.mkdtemp(prefix="preflight-"))
        self.addCleanup(shutil.rmtree, base, True)
        leg = self.leg(provider)
        leg.ctx.base, leg.ctx.secrets = base, {discord_room.ATTENTION_KEY_ENV: "a", discord_room.PARTICIPANT_KEY_ENV: "p"}
        leg.ctx.route = routes.Route(discord_room.REFERENCE, "anthropic/claude-haiku-4.5", base_url="x")
        leg.directed = None
        leg.script = None
        leg.live = None if scripted else discord_room.LiveTurns(SimpleNamespace(state=base, agent="Vigil", records=[], quiet=lambda s: True))
        class Stop(Exception):
            """The test has seen what it came for: prepare would now wait for the reference to be ready."""

        def wait_ready(*_args):
            raise Stop

        leg.discord = SimpleNamespace(
            start=lambda scenes: events.append("start"), channel_id="9", agent_id="9", agent="Vigil",
            fd=SimpleNamespace(token=lambda name: "token"), launch=lambda *a, **k: events.append("launch") or SimpleNamespace(env={"HOME": "h", "TMPDIR": "t"}),
            wait_ready=wait_ready,
        )
        leg.stop = Stop

        def room_config(sections):
            events.append("room_config")
            (base / "config").mkdir(exist_ok=True)
            (base / "config" / f"{discord_room.PARTICIPANT}.profile.json").write_text("{}")
            path = base / "config" / "nunchi.json"
            path.write_text("{}")
            return {}, path

        leg.room_config = room_config
        leg.reference_install = lambda: {}
        return leg, events

    def test_a_live_prepare_makes_the_call_after_writing_the_config_and_before_launching_anything(self):
        leg, events = self.prepare(self.provider({"kind": "silence"}))
        with mock.patch.object(discord_room.LiveTurns, "start"), self.assertRaises(leg.stop):
            leg.prepare()
        self.assertEqual(["start", "room_config", "launch"], events)
        self.assertEqual(1, leg.preflight_calls, "made once, between the config and the launch")
        # A provider that refuses stops the run before the reference process exists.
        leg, events = self.prepare(self.provider({"error": "x"}, status=400))
        with self.assertRaises(discord_room.CouldNotRun):
            leg.prepare()
        self.assertEqual(["start", "room_config"], events, "the reference was never launched")

    def test_a_scripted_prepare_makes_no_call_to_any_provider(self):
        provider = self.provider({"kind": "silence"})
        leg, events = self.prepare(provider, scripted=True)
        leg.participant_endpoint = None
        with mock.patch.object(discord_room, "ScriptedParticipant", return_value=SimpleNamespace(base_url="http://127.0.0.1:1")), self.assertRaises(leg.stop):
            leg.prepare()
        self.assertEqual(["start", "room_config", "launch"], events)
        self.assertEqual([], provider.bodies)
        self.assertEqual(0, leg.preflight_calls)


class RunnerOnlyTest(unittest.TestCase):
    def test_the_discord_room_records_a_runner_not_just_ci_true(self):
        from evals.rehearsal import discord_net

        self.assertTrue(discord_net.on_a_runner({"CI": "true", "GITHUB_ACTIONS": "true"}))
        self.assertFalse(discord_net.on_a_runner({"CI": "true"}))
        with self.assertRaisesRegex(discord_room.CouldNotRun, "GITHUB_ACTIONS=true"):
            discord_room.require_online({"offline": False, "ci": False})


# -- the matrix of a halted dispatch, and the cause of a failed run ----------------------------------------------------------------------------


# -- the workflow's own scripts, run against stand-ins --------------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
