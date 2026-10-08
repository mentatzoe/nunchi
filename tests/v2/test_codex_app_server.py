"""The Codex app-server integration (#94 step 9e): library-hosted, tool posting.

The first group needs no Codex: the room tools' MCP bridge, the restricted
socket it calls, the thread's own config, and the answers to Codex's approval
requests. The second group runs a real `codex app-server` from a clean, pinned
install (``NUNCHI_CODEX_BIN``, or ``codex`` on PATH) with a throwaway HOME,
CODEX_HOME and TMPDIR, and only the model scripted
(`nunchi.integrations.codex_app_server_conformance`); it skips when Codex is
not installed.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import secrets
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from nunchi.attention import AttentionPolicy, ParticipantProfile
from nunchi.conformance import fixture_attention_model, fixture_binding, fixture_profile
from nunchi.integrations.codex_app_server import mcp_bridge
from nunchi.integrations.codex_app_server.client import ServerRequestError
from nunchi.integrations.codex_app_server.integration import (
    BRIDGE_PATH,
    MCP_SERVER_NAME,
    TOKEN_PATTERNS,
    CodexRoomIntegration,
    CodexSettings,
    _ending,
    agent_environment,
    build_integration,
    project_keys,
    withheld_values,
)
from nunchi.errors import ValidationError
from nunchi.integrations.codex_app_server_conformance import (
    CodexHarness,
    CodexKitIntegration,
    codex_available,
    codex_executable,
)
from nunchi.observation import ObservationLimits
from nunchi.participant import TransportResult
from nunchi.room import Room, RoomSettings
from nunchi.turn import SecretGuard
from nunchi.turn_conformance import SCENARIOS, run_scenario

PROFILE = ParticipantProfile(
    profile_id="vigil-profile",
    participant_id="vigil",
    actor_id="example:user:bot-7",
    instructions="Participate directly and preserve uncertainty.",
    provenance="test:offline",
    sha256="0" * 64,
)


def _settings(directory: Path, **overrides) -> CodexSettings:
    values = {"working_directory": directory, "project_trust_level": "trusted", "executable": "/nonexistent/codex"}
    values.update(overrides)
    return CodexSettings(**values)


def _integration(base: Path, **overrides) -> CodexRoomIntegration:
    work = base / "work"
    work.mkdir(exist_ok=True)
    return CodexRoomIntegration(
        profile=PROFILE,
        guard=SecretGuard([]),
        settings=_settings(work),
        environment={"PATH": os.environ.get("PATH", "")},
        runtime_directory=base / "r",
        **overrides,
    )


class SettingsTest(unittest.TestCase):
    def test_section_is_checked(self):
        settings = CodexSettings.from_section(
            {"working_directory": "/srv/vigil", "project_trust_level": "untrusted", "withheld_env": ["X_TOKEN"]}
        )
        self.assertEqual(settings.working_directory, Path("/srv/vigil"))
        self.assertEqual(settings.project_trust_level, "untrusted")
        self.assertEqual(settings.withheld_env, ("X_TOKEN",))
        self.assertTrue(settings.resume_thread)
        for section in (
            {"project_trust_level": "trusted"},
            {"working_directory": "relative", "project_trust_level": "trusted"},
            {"working_directory": "/srv/vigil", "project_trust_level": "maybe"},
            {"working_directory": "/srv/vigil", "project_trust_level": "trusted", "profile": "work"},
            "codex",
        ):
            with self.assertRaises(ValueError):
                CodexSettings.from_section(section)

    def test_the_agent_never_gets_what_nunchi_withholds(self):
        environ = {"PATH": "/bin", "OPENAI_API_KEY": "the-agent-own-key", "DISCORD_BOT_TOKEN": "nunchi-discord-secret"}
        self.assertEqual(
            agent_environment(environ, ["DISCORD_BOT_TOKEN"]),
            {"PATH": "/bin", "OPENAI_API_KEY": "the-agent-own-key"},
        )
        self.assertEqual(withheld_values(environ, ["DISCORD_BOT_TOKEN", "MISSING"]), ["nunchi-discord-secret"])
        guard = SecretGuard([], patterns=TOKEN_PATTERNS)
        token = "MTA" + "x" * 21 + ".GaBcDe." + "y" * 30
        self.assertIsNotNone(guard.refusal({"kind": "message", "text": f"the token is {token}"}))

    def test_trust_is_looked_up_where_codex_looks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            sub = root / "service"
            sub.mkdir(parents=True)
            (root / ".git").mkdir()
            keys = project_keys(sub)
            self.assertEqual(keys[0], os.path.realpath(sub))
            self.assertIn(os.path.realpath(root), keys)

    def test_a_config_builds_the_integration_and_withholds_nunchis_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            profile = {
                "profile_id": "vigil-profile",
                "participant_id": "vigil",
                "actor_id": "discord:user:7",
                "instructions": "Participate directly.",
                "provenance": "test:offline",
            }
            raw = json.dumps(profile).encode()
            (base / "profile.json").write_bytes(raw)
            config = {
                "schema_version": 2,
                "binding": {
                    "participant_id": "vigil",
                    "actor_id": "discord:user:7",
                    "platform": "discord",
                    "room_id": "room-1",
                    "continuity_scope_id": "discord:room-1",
                    "names": ["Vigil"],
                },
                "profile": {"path": str(base / "profile.json"), "sha256": hashlib.sha256(raw).hexdigest()},
                "attention": {"policy": {}, "model": {"kind": "example", "api_key_env": "ATTENTION_KEY"}},
                "limits": {},
                "state_directory": str(base / "state"),
                "codex": {"working_directory": str(base / "work"), "project_trust_level": "trusted"},
            }
            environ = {
                "PATH": "/bin",
                "OPENAI_API_KEY": "the-agent-own-model-key",
                "ATTENTION_KEY": "nunchi-attention-model-key",
                "DISCORD_BOT_TOKEN": "nunchi-discord-bot-secret",
                "NUNCHI_ANYTHING": "nunchi-own",
            }
            settings, integration = build_integration(config, environ=environ)
            self.assertEqual(settings.binding.participant_id, "vigil")
            self.assertEqual(integration.environment, {"PATH": "/bin", "OPENAI_API_KEY": "the-agent-own-model-key"})
            for secret in ("nunchi-attention-model-key", "nunchi-discord-bot-secret"):
                self.assertIsNotNone(integration.participant.guard.refusal({"kind": "message", "text": secret}))
            # The bridge's launch secret: Codex holds it for the room's server.
            self.assertIsNotNone(
                integration.participant.guard.refusal({"kind": "message", "text": f"x {integration._secret}"})
            )
            token = "MTA" + "x" * 21 + ".GaBcDe." + "y" * 30
            self.assertIsNotNone(integration.participant.guard.refusal({"kind": "message", "text": token}))
            self.assertIsNone(integration.participant.guard.refusal({"kind": "message", "text": "On it."}))
            self.assertEqual(integration.thread_store, base / "state" / "codex-thread.json")
            self.assertLessEqual(len(str(integration.server.socket_path)), 107)
            inside = dict(config, codex={"working_directory": str(base / "state" / "work"), "project_trust_level": "trusted"})
            with self.assertRaisesRegex(ValidationError, "outside state_directory"):
                build_integration(inside, environ=environ)
            with self.assertRaisesRegex(ValidationError, "project_trust_level"):
                build_integration(dict(config, codex={"working_directory": str(base / "work")}), environ=environ)

            # Another platform's transport declares what it holds and its
            # tokens' shape; the turn's guard holds them, in place of the
            # Discord shape. Its variable stays out of Codex's environment
            # only when named in ``withhold``.
            class Transport:
                def withheld_values(self):
                    return ("held-by-the-transport-0123",)

                def credential_patterns(self):
                    return (re.compile(r"tok_[a-z]{8}"),)

            environ["OTHER_PLATFORM_TOKEN"] = "held-by-the-transport-0123"
            _settings, other = build_integration(
                config, environ=environ, transport=Transport(), withhold=("OTHER_PLATFORM_TOKEN",)
            )
            guard = other.participant.guard
            for text in ("held-by-the-transport-0123", "a token tok_abcdefgh", f"x {other._secret}"):
                with self.subTest(text=text[:12]):
                    self.assertIsNotNone(guard.refusal({"kind": "message", "text": text}))
            self.assertIsNone(guard.refusal({"kind": "message", "text": token}))
            self.assertNotIn("OTHER_PLATFORM_TOKEN", other.environment)
            other.close()

    def test_a_codex_run_ends_ok_only_when_completed(self):
        self.assertEqual(_ending({"status": "completed"}), (True, "completed"))
        self.assertEqual(
            _ending({"status": "failed", "error": {"message": "stream disconnected"}}),
            (False, "failed: stream disconnected"),
        )
        self.assertEqual(_ending({"status": "interrupted"}), (False, "interrupted"))


class ThreadConfigTest(unittest.TestCase):
    def test_the_bridges_launch_secret_is_withheld_from_the_room(self):
        with tempfile.TemporaryDirectory() as directory:
            integration = _integration(Path(directory))
            secret = integration._secret
            self.assertIn(secret, json.dumps(integration.thread_config(None)["mcp_servers"]))
            self.assertNotIn(secret, integration.environment.values())
            self.assertIsNotNone(integration.participant.guard.refusal({"kind": "message", "text": f"x {secret}"}))

    def test_the_room_tools_and_the_projects_trust_ride_in_the_threads_own_config(self):
        with tempfile.TemporaryDirectory() as directory:
            integration = _integration(Path(directory))
            config = integration.thread_config("trusted")
            server = config["mcp_servers"][MCP_SERVER_NAME]
            self.assertEqual(server["command"], sys.executable)
            self.assertEqual(server["args"], ["-I", str(BRIDGE_PATH)])
            self.assertEqual(server["env"][mcp_bridge.SOCKET_ENV], str(integration.server.socket_path))
            self.assertTrue(server["env"][mcp_bridge.SECRET_ENV])
            # Without the room tools no thread starts; nobody approves them.
            self.assertIs(server["required"], True)
            self.assertEqual(server["default_tools_approval_mode"], "approve")
            work = os.path.realpath(Path(directory) / "work")
            self.assertEqual(config["projects"], {work: {"trust_level": "trusted"}})
            # The user's own decision stands: nothing is passed.
            self.assertNotIn("projects", integration.thread_config(None))

    def test_a_socket_path_too_long_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "too deep for a Unix socket"):
                CodexRoomIntegration(
                    profile=PROFILE,
                    guard=SecretGuard([]),
                    settings=_settings(Path(directory)),
                    environment={},
                    runtime_directory=Path(directory) / ("d" * 120),
                )


class _FakeRoom:
    def __init__(self, answers=None, fail=False):
        self.posts: list[tuple[str, dict]] = []
        self.answers = answers or {}
        self.fail = fail

    def post(self, route, body):
        self.posts.append((route, dict(body)))
        if self.fail:
            raise OSError("connection refused")
        return self.answers.get(route, {})


def _call(params):
    return {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": params}


class BridgeTest(unittest.TestCase):
    def test_initialize_answers_in_the_clients_version(self):
        bridge = mcp_bridge.Bridge(_FakeRoom())
        for requested, expected in (("2025-03-26", "2025-03-26"), ("2099-01-01", "2025-06-18")):
            answer = bridge.handle({"id": 1, "method": "initialize", "params": {"protocolVersion": requested}})
            self.assertEqual(answer["result"]["protocolVersion"], expected)
            self.assertIn("tools", answer["result"]["capabilities"])

    def test_tools_are_the_rooms(self):
        tools = [{"name": "room_send", "description": "Post.", "inputSchema": {"type": "object"}}]
        bridge = mcp_bridge.Bridge(_FakeRoom({"/v1/attach": {"tools": tools}}))
        answer = bridge.handle({"id": 2, "method": "tools/list", "params": {}})
        self.assertEqual(answer["result"]["tools"], tools)

    def test_a_call_carries_codexs_turn_and_the_rooms_news(self):
        room = _FakeRoom(
            {
                "/v1/turn/call": {"ok": True, "text": "Done: the room accepted this action."},
                "/v1/turn/after-tool": {"text": "Room update: 1 new message(s) arrived."},
            }
        )
        bridge = mcp_bridge.Bridge(room)
        for meta in (
            {"x-codex-turn-metadata": {"turn_id": "codex-turn-1", "thread_id": "t"}},
            {"x-codex-turn-metadata": json.dumps({"turn_id": "codex-turn-1"})},
        ):
            room.posts.clear()
            answer = bridge.handle(_call({"name": "room_send", "arguments": {"text": "On it."}, "_meta": meta}))
            self.assertEqual(
                room.posts,
                [
                    ("/v1/turn/call", {"turn_id": "codex-turn-1", "tool": "room_send", "input": {"text": "On it."}}),
                    ("/v1/turn/after-tool", {"turn_id": "codex-turn-1"}),
                ],
            )
            result = answer["result"]
            self.assertIs(result["isError"], False)
            self.assertEqual(
                result["content"][0]["text"],
                "Done: the room accepted this action.\n\nRoom update: 1 new message(s) arrived.",
            )

    def test_a_refusal_is_an_error_result_with_the_librarys_words(self):
        room = _FakeRoom({"/v1/turn/call": {"ok": False, "error": "Refused: secret."}})
        answer = mcp_bridge.Bridge(room).handle(_call({"name": "room_send", "arguments": {}}))
        self.assertIs(answer["result"]["isError"], True)
        self.assertEqual(answer["result"]["content"][0]["text"], "Refused: secret.")
        # Without Codex's turn id the room cannot place the call; it refuses it.
        self.assertIsNone(room.posts[0][1]["turn_id"])

    def test_an_unreachable_room_posts_nothing(self):
        answer = mcp_bridge.Bridge(_FakeRoom(fail=True)).handle(_call({"name": "room_send", "arguments": {}}))
        self.assertIs(answer["result"]["isError"], True)
        self.assertEqual(answer["result"]["content"][0]["text"], mcp_bridge.UNREACHABLE)

    def test_notifications_ping_and_unknown_methods(self):
        bridge = mcp_bridge.Bridge(_FakeRoom())
        self.assertIsNone(bridge.handle({"method": "notifications/initialized"}))
        self.assertEqual(bridge.handle({"id": 3, "method": "ping"})["result"], {})
        self.assertEqual(bridge.handle({"id": 4, "method": "resources/list"})["error"]["code"], -32601)

    def test_stdio_is_one_message_per_line(self):
        out = io.StringIO()
        mcp_bridge.serve(
            mcp_bridge.Bridge(_FakeRoom()),
            io.StringIO('{"jsonrpc":"2.0","method":"notifications/initialized"}\n\nnot json\n{"id":5,"method":"ping"}\n'),
            out,
        )
        lines = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual([line.get("id") for line in lines], [None, 5])
        self.assertEqual(lines[0]["error"]["code"], -32700)

    def test_it_needs_its_socket_and_secret(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(mcp_bridge.main(environ={}), 2)
        self.assertIn(mcp_bridge.SOCKET_ENV, err.getvalue())


class RoomSocketTest(unittest.TestCase):
    """The bridge against the integration's real socket, without Codex."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.integration = _integration(Path(self.directory.name))
        self.integration.server.start()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.integration.server.close)
        config = self.integration.thread_config(None)["mcp_servers"][MCP_SERVER_NAME]["env"]
        self.room = mcp_bridge.TurnSocket(config[mcp_bridge.SOCKET_ENV], config[mcp_bridge.SECRET_ENV], timeout=10)

    def test_the_bridge_lists_the_room_tools_and_a_call_outside_a_turn_is_refused(self):
        bridge = mcp_bridge.Bridge(self.room)
        tools = bridge.handle({"id": 1, "method": "tools/list"})["result"]["tools"]
        self.assertEqual({tool["name"] for tool in tools}, {"room_send", "room_react", "room_context"})
        answer = bridge.handle(
            _call({"name": "room_send", "arguments": {"text": "hi"}, "_meta": {"x-codex-turn-metadata": {"turn_id": "x"}}})
        )
        self.assertIs(answer["result"]["isError"], True)
        self.assertIn("No room opportunity is open", answer["result"]["content"][0]["text"])

    def test_binding_and_ending_are_not_offered_on_the_socket(self):
        for route in ("/v1/turn/bind", "/v1/turn/end", "/v1/turn/finish", "/v1/turn-start"):
            self.assertIn("not offered", self.room.post(route, {"turn_id": "x", "wake_id": "y"})["error"])

    def test_only_the_launch_secret_gets_in(self):
        intruder = mcp_bridge.TurnSocket(str(self.integration.server.socket_path), "wrong", timeout=10)
        with self.assertRaises(OSError):
            intruder.post("/v1/attach", {})

    def test_the_socket_is_private(self):
        socket_path = self.integration.server.socket_path
        self.assertEqual(stat.S_IMODE(os.stat(socket_path.parent).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(socket_path).st_mode), 0o600)


class AppServerGenerationTest(unittest.TestCase):
    def test_a_late_exit_of_an_old_process_leaves_the_new_one_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            integration = _integration(Path(directory))
            current = object()
            integration._generation = 2
            integration._app, integration._thread_id = current, "thread-1"
            integration._mcp_status[("thread-1", MCP_SERVER_NAME)] = "ready"
            integration._on_exit(1, -9)
            self.assertIs(integration._app, current)
            self.assertEqual(integration.thread_id, "thread-1")
            self.assertEqual(integration._mcp_status, {("thread-1", MCP_SERVER_NAME): "ready"})
            integration._on_exit(2, -9)
            self.assertIsNone(integration._app)
            self.assertIsNone(integration.thread_id)
            self.assertEqual(integration._mcp_status, {})


class ServerRequestTest(unittest.TestCase):
    def test_codex_asking_a_person_is_answered_no(self):
        with tempfile.TemporaryDirectory() as directory:
            integration = _integration(Path(directory))
            answer = integration._on_server_request
            self.assertEqual(answer("item/commandExecution/requestApproval", {}), {"decision": "decline"})
            self.assertEqual(answer("item/fileChange/requestApproval", {}), {"decision": "decline"})
            self.assertEqual(answer("item/permissions/requestApproval", {}), {"permissions": {}, "scope": "turn"})
            self.assertEqual(answer("mcpServer/elicitation/request", {})["action"], "decline")
            self.assertIs(answer("item/tool/call", {})["success"], False)
            with self.assertRaises(ServerRequestError):
                answer("item/tool/requestUserInput", {})


# -- a real codex app-server --------------------------------------------------------------------


class _Recording:
    def __init__(self):
        self.actions = []

    def dispatch(self, *, action, **_):
        self.actions.append(dict(action))
        return TransportResult("sent", "test room")


def _room(harness: CodexHarness) -> tuple[Room, _Recording]:
    binding = fixture_binding()
    settings = RoomSettings(
        binding=binding,
        profile=fixture_profile(binding),
        attention=AttentionPolicy(),
        attention_model=None,
        limits=ObservationLimits(),
        state_directory=harness.base / "state",
    )
    transport = _Recording()
    room = Room(
        settings,
        participant=harness.integration.participant,
        transport=transport,
        event_visibility={"message": "history-and-live", "reaction": "history-and-live", "membership": "live-only"},
        state_prefix="codex-test-",
        attention_model=fixture_attention_model("WAKE"),
        participant_timeout_seconds=60,
    )
    return room, transport


def _person(room: Room, event_id: str, text: str, *, observe_only: bool = False):
    event = {
        "id": event_id,
        "type": "message",
        "author_id": "test:person",
        "text": text,
        "mentioned_actor_ids": [],
        "mentions_room": False,
    }
    actors = {"test:person": {"kind": "human", "display_name": "Sam"}}
    if observe_only:
        room.observation.observe(delivery_id=f"d:{event_id}", event=event, actors=actors)
        return None
    outcome: dict = {}

    def deliver():
        outcome["value"] = room.pipeline.handle_delivery(delivery_id=f"d:{event_id}", event=event, actors=actors)

    thread = threading.Thread(target=deliver, daemon=True)
    thread.start()
    return thread, outcome


def _wait(condition, timeout=30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


_USER_MCP = r'''
import json, sys
for line in sys.stdin:
    m = json.loads(line)
    if "id" not in m:
        continue
    if m["method"] == "initialize":
        r = {"protocolVersion": m["params"]["protocolVersion"], "capabilities": {"tools": {}},
             "serverInfo": {"name": "user-tools", "version": "0"}}
    elif m["method"] == "tools/list":
        r = {"tools": [{"name": "echo", "description": "Echo.", "inputSchema": {"type": "object"}}]}
    elif m["method"] == "tools/call":
        r = {"content": [{"type": "text", "text": "echo"}]}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32601, "message": "no"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": r}), flush=True)
'''


# A runtime process as the runner starts: keep_private first, then the
# integration with the throwaway user's own Codex config (argv 1). The keys
# are in its starting environment and in its memory. The scripted model asks
# Codex to run a command that looks for them in every process, and in the
# runtime's memory, then posts once.
_PRIVATE_RUNTIME = r'''
import ctypes, hashlib, json, os, sys
from nunchi.private_process import keep_private
private = keep_private()
from nunchi.conformance import fixture_binding, fixture_profile
from nunchi.turn import SecretGuard
from nunchi.integrations.codex_app_server_conformance import CodexHarness
from tests.v2.test_codex_app_server import _room, _person, _wait

names = ["TEST_ROOM_OUTPUT_KEY", "TEST_ATTENTION_KEY"]
held = ctypes.create_string_buffer(os.environ[names[0]].encode())
digests = {name: hashlib.sha256(os.environ[name].encode()).hexdigest() for name in names}
reader = f"""
import hashlib, json, os
digests, runtime, address = {json.dumps(digests)}, "{os.getpid()}", {ctypes.addressof(held)}
found, environ_error = [], None
for pid in [p for p in os.listdir("/proc") if p.isdigit()]:
    try:
        raw = open(f"/proc/{{pid}}/environ", "rb").read()
    except OSError as exc:
        environ_error = type(exc).__name__ if pid == runtime else environ_error
        continue
    for entry in raw.split(b"\\0"):
        name, _, value = entry.partition(b"=")
        if hashlib.sha256(value).hexdigest() == digests.get(name.decode(errors="replace")):
            found.append(name.decode())
try:
    with open(f"/proc/{{runtime}}/mem", "rb", buffering=0) as handle:
        handle.seek(address)
        mem = "read" if handle.read(64).split(b"\\0")[0] else "empty"
except OSError as exc:
    mem = type(exc).__name__
print("PROBE " + json.dumps({{"found": found, "environ": environ_error, "mem": mem}}))
"""
harness = CodexHarness(profile=fixture_profile(fixture_binding()), guard=SecretGuard([]), user_config=sys.argv[1])
try:
    (harness.work / "reader.py").write_text(reader)
    room, transport = _room(harness)
    model = harness.model
    thread, outcome = _person(room, "test:message:1", "Can someone look at the failing deploy?")
    assert _wait(lambda: model.count() >= 1, 60), "Codex never asked the model"
    model.reply({"tool": "exec_command", "namespace": None, "call_id": "call-probe",
                 "arguments": {"cmd": f"{sys.executable} -I reader.py"}})
    assert _wait(lambda: model.count() >= 2, 60), "the command never ran"
    probe = None
    for item in model.latest().get("input", []):
        if isinstance(item, dict) and item.get("call_id") == "call-probe" and item.get("type") == "function_call_output":
            output = item.get("output")
            text = output if isinstance(output, str) else "\n".join(
                part.get("text", "") for part in output or [] if isinstance(part, dict))
            lines = [line for line in text.splitlines() if line.startswith("PROBE ")]
            probe = json.loads(lines[-1][6:]) if lines else text[-300:]
    model.reply({"tool": "room_send", "call_id": "call-send", "arguments": {"text": "Looking at it now."}})
    assert _wait(lambda: model.count() >= 3, 60), "the room tool never answered"
    model.reply({"text": "Done."})
    thread.join(60)
    print(json.dumps({"private": private, "probe": probe, "sandbox": harness.integration.sandbox,
                      "warned": harness.integration.sandbox_warning is not None,
                      "posted": [action.get("text") for action in transport.actions]}))
finally:
    harness.close()
'''


def _without_ptrace_capability() -> list[str] | None:
    """A command prefix that drops CAP_SYS_PTRACE, which reads any process; None when impossible."""

    status = Path("/proc/self/status").read_text(encoding="utf-8")
    effective = next(int(line.split()[1], 16) for line in status.splitlines() if line.startswith("CapEff:"))
    if not effective >> 19 & 1:
        return []
    setpriv = shutil.which("setpriv")
    return [setpriv, "--inh-caps=-all", "--bounding-set=-all"] if setpriv else None


@unittest.skipUnless(codex_available(), "Codex is not installed (set NUNCHI_CODEX_BIN to a pinned codex)")
class CodexKitTest(unittest.TestCase):
    def test_every_tool_posting_scenario_passes_through_codex(self):
        for name, scenario in SCENARIOS.items():
            if scenario.posting != "tools":
                continue
            with self.subTest(scenario=name):
                result = run_scenario(name, CodexKitIntegration())
                self.assertEqual(result["status"], "pass", result.get("failures"))


@unittest.skipUnless(codex_available(), "Codex is not installed (set NUNCHI_CODEX_BIN to a pinned codex)")
class CodexRoomTest(unittest.TestCase):
    def _harness(self, **kwargs) -> CodexHarness:
        harness = CodexHarness(profile=fixture_profile(fixture_binding()), guard=SecretGuard([]), **kwargs)
        self.addCleanup(harness.close)
        return harness

    def test_room_tools_join_the_users_own_and_steering_follows_their_tools(self):
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        (base / "user_mcp.py").write_text(_USER_MCP, encoding="utf-8")
        harness = self._harness(
            user_config=f'\n[mcp_servers.user_tools]\ncommand = "{sys.executable}"\nargs = ["-I", "{base / "user_mcp.py"}"]\n'
        )
        room, transport = _room(harness)
        model = harness.model
        thread, outcome = _person(room, "test:message:1", "Can someone look at the failing deploy?")
        self.assertTrue(_wait(lambda: model.count() >= 1), "Codex never asked the model")
        first = model.latest()
        namespaces = {tool["name"] for tool in first["tools"] if tool.get("type") == "namespace"}
        self.assertTrue({"mcp__nunchi_room", "mcp__user_tools"} <= namespaces, namespaces)
        turn = harness.integration.participant.active
        self.assertIsNotNone(turn.turn_id)
        # The wake id stays with Nunchi; the agent's input never carries it.
        self.assertNotIn(turn.wake_id, json.dumps(first))
        _person(room, "test:message:2", "Please use the staging box.", observe_only=True)
        model.reply({"tool": "echo", "namespace": "mcp__user_tools", "call_id": "call-user", "arguments": {}})
        self.assertTrue(_wait(lambda: harness.integration.steered), "no turn/steer after the user's tool")
        # The update reaches the model in this run, as Codex delivers steered input.
        seen = False
        for _ in range(3):
            self.assertTrue(_wait(lambda: model.count() >= 2 or turn.ended.is_set()))
            requests = list(model.requests)
            seen = any("Please use the staging box." in json.dumps(request["input"]) for request in requests[1:])
            if seen or turn.ended.is_set():
                break
            count = model.count()
            model.reply({"text": "Nothing to add."})
            _wait(lambda: model.count() > count or turn.ended.is_set(), 10)
        self.assertTrue(seen, "the room's news never reached the model")
        model.reply({"text": "Nothing to add."})
        thread.join(30)
        self.assertIsNone(outcome["value"].opportunities[0].transport, "a bound turn without an action is silence")
        self.assertEqual(transport.actions, [])
        # Codex asked to approve the user's own unannotated tool; nobody is there.
        self.assertIn("mcpServer/elicitation/request", harness.integration.declined)
        self.assertTrue(harness.user_config_unchanged())

    def test_what_would_prompt_a_person_is_declined(self):
        harness = self._harness()
        room, _ = _room(harness)
        model = harness.model
        thread, outcome = _person(room, "test:message:1", "Can someone look at the failing deploy?")
        self.assertTrue(_wait(lambda: model.count() >= 1))
        model.reply(
            {
                "tool": "exec_command",
                "namespace": None,
                "call_id": "call-shell",
                "arguments": {
                    "cmd": "touch escalated.txt",
                    "sandbox_permissions": "require_escalated",
                    "justification": "make a file",
                },
            }
        )
        self.assertTrue(_wait(lambda: model.count() >= 2))
        model.reply({"text": "Nothing to add."})
        thread.join(30)
        self.assertIn("item/commandExecution/requestApproval", harness.integration.declined)
        self.assertEqual(harness.integration.tool_items["call-shell"].get("status"), "declined")
        self.assertFalse((harness.work / "escalated.txt").exists())
        self.assertIsNone(outcome["value"].opportunities[0].transport)

    def test_trust_is_never_written_and_the_users_own_decision_stands(self):
        for users_own, passed in ((None, "trusted"), ("untrusted", None)):
            with self.subTest(users_own=users_own):
                harness = self._harness()
                if users_own is not None:
                    harness.user_config += (
                        f'\n[projects."{os.path.realpath(harness.work)}"]\ntrust_level = "{users_own}"\n'
                    )
                    (harness.codex_home / "config.toml").write_text(harness.user_config, encoding="utf-8")
                calls = []
                original = harness.integration.thread_config
                harness.integration.thread_config = lambda trust: (calls.append(trust), original(trust))[1]
                self.assertTrue(harness.integration.ready(threading.Event()))
                self.assertEqual(calls, [passed])
                self.assertTrue(harness.user_config_unchanged(), "Codex wrote into the user's config")

    def test_a_run_that_dies_fails_and_the_thread_resumes(self):
        harness = self._harness(resume_thread=True)
        room, transport = _room(harness)
        model = harness.model
        thread, outcome = _person(room, "test:message:1", "Can someone look at the failing deploy?")
        self.assertTrue(_wait(lambda: model.count() >= 1))
        first_thread = harness.integration.thread_id
        harness.integration._app.kill()
        thread.join(30)
        result = outcome["value"].opportunities[0].transport
        self.assertIsNotNone(result, "a run that died was taken for silence")
        self.assertEqual(result.delivery, "failed")
        # The next turn starts Codex again on the same thread.
        thread, outcome = _person(room, "test:message:2", "Anyone?")
        self.assertTrue(_wait(lambda: model.count() >= 2), "Codex did not come back")
        self.assertEqual(harness.integration.thread_id, first_thread)
        model.reply({"text": "Nothing to add."})
        thread.join(30)
        self.assertIsNone(outcome["value"].opportunities[0].transport)
        self.assertEqual(transport.actions, [])

    def test_codex_s_sandbox_is_recorded_and_an_uncontained_one_warned_about(self):
        harness = self._harness()
        with self.assertNoLogs("nunchi.codex_app_server", "WARNING"):
            self.assertTrue(harness.integration.ready(threading.Event()))
        self.assertEqual("workspaceWrite", harness.integration.sandbox["type"])
        self.assertFalse(harness.integration.sandbox["networkAccess"])
        self.assertIsNone(harness.integration.sandbox_warning)

        harness = self._harness(user_config='sandbox_mode = "danger-full-access"')
        with self.assertLogs("nunchi.codex_app_server", "WARNING") as logs:
            self.assertTrue(harness.integration.ready(threading.Event()))
        self.assertEqual({"type": "dangerFullAccess"}, harness.integration.sandbox)
        self.assertIn("dangerFullAccess", harness.integration.sandbox_warning)
        self.assertIn("dangerFullAccess", "\n".join(logs.output))
        # Codex still runs; the user's choice is reported, not refused.
        self.assertTrue(harness.user_config_unchanged())

    @unittest.skipUnless(sys.platform.startswith("linux"), "keep_private acts on Linux only")
    def test_the_agent_cannot_read_a_private_runtime_even_without_a_sandbox(self):
        prefix = _without_ptrace_capability()
        if prefix is None:
            self.skipTest("this process can read any process (CAP_SYS_PTRACE), and setpriv is not installed")
        base = Path(tempfile.mkdtemp(prefix="nkp-"))
        self.addCleanup(shutil.rmtree, base, True)
        (base / "home").mkdir()
        (base / "t").mkdir()
        source = Path(mcp_bridge.__file__).resolve().parents[3]
        root = Path(__file__).resolve().parents[2]
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(base / "home"),
            "TMPDIR": str(base / "t"),
            "PYTHONPATH": os.pathsep.join([str(source), str(root)]),
            "NUNCHI_CODEX_BIN": codex_executable(),
            "TEST_ROOM_OUTPUT_KEY": "room-output-" + secrets.token_hex(24),
            "TEST_ATTENTION_KEY": "attention-" + secrets.token_hex(24),
        }
        completed = subprocess.run(
            [*prefix, sys.executable, "-c", _PRIVATE_RUNTIME, 'sandbox_mode = "danger-full-access"'],
            env=environment,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(0, completed.returncode, completed.stderr[-2000:])
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual("private", result["private"])
        self.assertEqual({"type": "dangerFullAccess"}, result["sandbox"])
        self.assertTrue(result["warned"])
        # The agent's command sees every process, yet reads no key out of the runtime.
        self.assertEqual({"found": [], "environ": "PermissionError", "mem": "PermissionError"}, result["probe"])
        # And Codex works normally under a private parent: the turn posts.
        self.assertEqual(["Looking at it now."], result["posted"])


if __name__ == "__main__":
    unittest.main()
