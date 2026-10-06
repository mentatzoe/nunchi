from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import plistlib
import stat
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from nunchi import cli, operator as operator_module
from nunchi.attention import ParticipantProfile
from nunchi.dashboard import dashboard_handler, serve_dashboard
from nunchi.errors import ValidationError
from nunchi.install import InstallError, rollback, uninstall_state, upgrade, verify
from nunchi.integrations.codex_v2 import CodexParticipant
from nunchi.operator import (
    OperatorStore,
    ServiceManager,
    build_operator_config,
)
from nunchi.participant_model import (
    PARTICIPANT_TURN_PROTOCOL,
    PARTICIPANT_TURN_PROTOCOL_VERSION,
    OpenAICompatibleParticipant,
    ParticipantModelError,
    ParticipantTurnProtocol,
    parse_participant_action,
    participant_action_schema,
    participant_turn_text,
)


PROFILE = ParticipantProfile(
    profile_id="vigil-default",
    participant_id="vigil",
    actor_id="discord:bot:9",
    instructions="Contribute on security and implementation correctness.",
    provenance="trusted:test",
    sha256="0" * 64,
)


def wake(request_id="r1"):
    return {
        "request_id": request_id,
        "self": {"participant_id": "vigil", "actor_id": "discord:bot:9"},
        "room": {
            "platform": "discord",
            "id": "42",
            "continuity_scope_id": "discord:channel:42",
        },
        "actors": {
            "discord:bot:9": {"kind": "bot"},
            "human:zoe": {"kind": "human"},
        },
        "events": [
            {
                "id": "e1",
                "type": "message",
                "author_id": "human:zoe",
                "text": "Could you look at this?",
                "mentioned_actor_ids": [],
                "mentions_room": False,
            }
        ],
        "trigger_event_id": "e1",
        "coverage": {
            "has_more_before": False,
            "has_more_after": False,
            "has_gaps": False,
            "truncated_by": [],
            "continuity": "restart-safe",
            "has_restart_gap": False,
        },
        "attention": {"source": "WAKE"},
    }


def opportunity():
    return {
        "generation": 7,
        "lifecycle_id": "lifecycle:v1",
        "deadline_id": "deadline:v1",
        "permissions": {
            "revision": "permissions:v1",
            "ordinary_actions": ["message", "reply", "reaction"],
            "privileged_proposals": False,
        },
    }


class ParticipantProtocolTests(unittest.TestCase):
    def setUp(self):
        self.protocol = ParticipantTurnProtocol(
            profile=PROFILE,
            wake=wake(),
            opportunity=opportunity(),
        )

    def envelope(self, action):
        return {
            "protocol": deepcopy(self.protocol.request["protocol"]),
            "binding": deepcopy(self.protocol.request["binding"]),
            "action": action,
        }

    def test_one_protocol_owns_prompt_request_schema_and_parser(self):
        request = self.protocol.request
        self.assertEqual(
            {
                "name": PARTICIPANT_TURN_PROTOCOL,
                "version": PARTICIPANT_TURN_PROTOCOL_VERSION,
            },
            request["protocol"],
        )
        schema = participant_action_schema(request["binding"])
        self.assertEqual(
            request["binding"]["request_id"],
            schema["properties"]["binding"]["properties"]["request_id"]["const"],
        )
        action = {"kind": "message", "origin_event_id": "e1", "text": "On it."}
        self.assertEqual(
            action,
            parse_participant_action(
                self.envelope(action),
                request=request,
                visible_event_ids={"e1"},
            ),
        )

    def test_instructions_supply_the_action_schema_they_promise(self):
        # The prompt says "matching the supplied action schema"; every runner
        # must then supply it, bound to this turn's exact binding.
        marker = "(JSON Schema; the protocol and binding values are fixed):\n"
        for text in (
            self.protocol.instructions,
            participant_turn_text(PROFILE, self.protocol.request).split("\n\n<nunchi_participant_turn_v1>")[0],
        ):
            with self.subTest(text=text[:40]):
                schema = json.loads(text.split(marker, 1)[1])
                self.assertEqual(participant_action_schema(self.protocol.request["binding"]), schema)

    def test_a_model_that_follows_the_supplied_schema_is_accepted(self):
        bodies = []

        class Endpoint(ThreadingHTTPServer):
            pass

        from http.server import BaseHTTPRequestHandler

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                bodies.append(body)
                system = body["messages"][0]["content"]
                schema = json.loads(system.split("binding values are fixed):\n", 1)[1])
                properties = schema["properties"]
                envelope = {
                    "protocol": {
                        name: rule["const"]
                        for name, rule in properties["protocol"]["properties"].items()
                    },
                    "binding": {
                        name: rule["const"]
                        for name, rule in properties["binding"]["properties"].items()
                    },
                    "action": {
                        "kind": "reply",
                        "origin_event_id": "e1",
                        "target_event_id": "e1",
                        "text": "Looking now.",
                    },
                }
                reply = json.dumps(
                    {"choices": [{"message": {"content": json.dumps(envelope)}}]}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

            def log_message(self, *args):
                pass

        server = Endpoint(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        participant = OpenAICompatibleParticipant(
            profile=PROFILE,
            model="any/model",
            api_key="test-key",
            base_url=f"http://127.0.0.1:{server.server_address[1]}/v1",
        )
        action = participant.run_protocol(
            wake=wake(),
            opportunity=opportunity(),
            expand=None,
            cancel=threading.Event(),
        )
        self.assertEqual(
            {"kind": "reply", "origin_event_id": "e1", "target_event_id": "e1", "text": "Looking now."},
            action,
        )
        self.assertEqual(1, len(bodies))

    def test_extra_request_fields_are_configured_and_the_response_is_kept(self):
        for reserved in ("model", "messages", "response_format", "temperature"):
            with self.subTest(reserved=reserved), self.assertRaises(ValidationError):
                OpenAICompatibleParticipant(
                    profile=PROFILE,
                    model="any/model",
                    api_key="k",
                    base_url="http://localhost:1/v1",
                    extra_body={reserved: "x"},
                )
        participant = OpenAICompatibleParticipant.from_trusted_config(
            profile=PROFILE,
            config={
                "model": "any/model",
                "base_url": "http://localhost:1/v1",
                "extra_body": {"reasoning": {"effort": "low"}},
            },
            environment={"NUNCHI_PARTICIPANT_API_KEY": "k"},
        )
        sent = []
        payload = {"choices": [{"message": {"content": "{}"}}], "usage": {"cost": 0.001}}

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def urlopen(request, timeout):
            sent.append(json.loads(request.data))
            return Response(json.dumps(payload).encode())

        protocol = ParticipantTurnProtocol(profile=PROFILE, wake=wake(), opportunity=opportunity())
        with mock.patch("urllib.request.urlopen", urlopen):
            self.assertEqual("{}", participant._invoke(protocol))
        self.assertEqual({"effort": "low"}, sent[0]["reasoning"])
        self.assertEqual("any/model", sent[0]["model"])
        self.assertEqual({"cost": 0.001}, participant.last_response["usage"])

    def test_a_note_after_the_fenced_reply_is_dropped(self):
        # Models sometimes explain a silence after the closing fence (#94).
        envelope = json.dumps(self.envelope({"kind": "silence"}), indent=2)
        reply = "```json\n" + envelope + "\n```\n\nI don't know where those settings live, so I'm staying quiet."
        self.assertEqual((True, None), self.protocol.consume(reply, expand=None))

    def test_any_move_may_say_why_for_the_agents_own_memory(self):
        # #94 step 5: the reason goes to the host, which keeps it in memory.
        quiet = {"kind": "silence", "why": "Zoe asked Castor; waiting for him."}
        self.assertEqual((True, quiet), self.protocol.consume(json.dumps(self.envelope(quiet)), expand=None))
        reply = {"kind": "reply", "origin_event_id": "e1", "target_event_id": "e1", "text": "Yes.", "why": "I know it."}
        self.assertEqual(
            reply,
            parse_participant_action(self.envelope(reply), request=self.protocol.request, visible_event_ids={"e1"}),
        )
        # A malformed reason is dropped alone; it never fails the move.
        for bad in ("", "   ", 7, None):
            with self.subTest(why=bad):
                self.assertEqual(
                    (True, None),
                    self.protocol.consume(json.dumps(self.envelope({"kind": "silence", "why": bad})), expand=None),
                )
        # Looking around the room is not a move.
        expand = {"kind": "expand", "direction": "before", "max_events": 5, "max_bytes": 4096, "why": "context"}
        with self.assertRaises(ParticipantModelError):
            self.protocol.consume(json.dumps(self.envelope(expand)), expand=lambda **_: {"events": []})
        schema = participant_action_schema(self.protocol.request["binding"])
        kinds = {
            variant["properties"]["kind"]["const"]: "why" in variant["properties"]
            for variant in schema["properties"]["action"]["oneOf"]
        }
        self.assertEqual(
            {"silence": True, "expand": False, "message": True, "reply": True, "reaction": True, "privileged": True},
            kinds,
        )
        self.assertIn("Any action but expand may add why", self.protocol.instructions)

    def test_a_fence_inside_the_text_is_kept(self):
        action = {"kind": "message", "origin_event_id": "e1", "text": "Try:\n```sh\nmake test\n```"}
        fenced = "```json\n" + json.dumps(self.envelope(action)) + "\n```\nA code block answers it."
        for reply in (fenced, json.dumps(self.envelope(action))):
            with self.subTest(reply=reply[:8]):
                self.assertEqual(
                    action,
                    parse_participant_action(reply, request=self.protocol.request, visible_event_ids={"e1"}),
                )

    def test_anything_else_beside_the_reply_is_still_rejected(self):
        envelope = json.dumps(self.envelope({"kind": "silence"}))
        for reply in (
            envelope + "\nI'm staying quiet.",
            "```json\n" + envelope + "\nI'm staying quiet.\n```",
            "```json\n" + envelope + "\n" + envelope + "\n```",
            "I'm staying quiet.\n```json\n" + envelope + "\n```",
        ):
            with self.subTest(reply=reply[-30:]):
                with self.assertRaisesRegex(ParticipantModelError, "not valid JSON"):
                    self.protocol.consume(reply, expand=None)

    def test_unknown_version_and_every_stale_binding_are_rejected(self):
        unknown = self.envelope({"kind": "silence"})
        unknown["protocol"]["version"] += 1
        with self.assertRaises(ParticipantModelError):
            self.protocol.consume(unknown, expand=None)

        replacements = {
            "request_id": "other-request",
            "participant_id": "other-participant",
            "actor_id": "other-actor",
            "platform": "matrix",
            "room_id": "other-room",
            "continuity_scope_id": "other-scope",
            "trigger_event_id": "other-trigger",
            "opportunity_generation": 8,
            "lifecycle_id": "other-lifecycle",
            "deadline_id": "other-deadline",
            "permissions_revision": "other-permissions",
        }
        for field, replacement in replacements.items():
            with self.subTest(field=field):
                stale = self.envelope({"kind": "silence"})
                stale["binding"][field] = replacement
                with self.assertRaises(ParticipantModelError):
                    self.protocol.consume(stale, expand=None)

        boolean_generation = self.envelope({"kind": "silence"})
        boolean_generation["binding"]["opportunity_generation"] = True
        with self.assertRaises(ParticipantModelError):
            self.protocol.consume(boolean_generation, expand=None)

    def test_actions_are_fact_and_permission_bound_and_expansion_is_capped(self):
        invisible = self.envelope(
            {"kind": "message", "origin_event_id": "e-missing", "text": "No."}
        )
        with self.assertRaises(ParticipantModelError):
            self.protocol.consume(invisible, expand=None)

        restricted = ParticipantTurnProtocol(
            profile=PROFILE,
            wake=wake(),
            opportunity={
                **opportunity(),
                "permissions": {
                    "revision": "permissions:message-only",
                    "ordinary_actions": ["message"],
                    "privileged_proposals": False,
                },
            },
        )
        reaction = {
            "protocol": restricted.request["protocol"],
            "binding": restricted.request["binding"],
            "action": {
                "kind": "reaction",
                "origin_event_id": "e1",
                "target_event_id": "e1",
                "reaction": "👂",
                "operation": "add",
            },
        }
        with self.assertRaises(ParticipantModelError):
            restricted.consume(reaction, expand=None)

        silence_only = ParticipantTurnProtocol(
            profile=PROFILE,
            wake=wake(),
            opportunity={
                **opportunity(),
                "permissions": {
                    "revision": "permissions:silence-only",
                    "ordinary_actions": [],
                    "privileged_proposals": False,
                },
            },
        )
        self.assertEqual(
            (True, None),
            silence_only.consume(
                {
                    "protocol": deepcopy(silence_only.request["protocol"]),
                    "binding": deepcopy(silence_only.request["binding"]),
                    "action": {"kind": "silence"},
                },
                expand=None,
            ),
        )
        with self.assertRaises(ParticipantModelError):
            silence_only.consume(
                {
                    "protocol": deepcopy(silence_only.request["protocol"]),
                    "binding": deepcopy(silence_only.request["binding"]),
                    "action": {
                        "kind": "message",
                        "origin_event_id": "e1",
                        "text": "not authorized",
                    },
                },
                expand=None,
            )

        expansion = self.envelope(
            {
                "kind": "expand",
                "direction": "before",
                "anchor_event_id": "e1",
                "max_events": 4,
                "max_bytes": 1024,
            }
        )
        calls = []
        for _ in range(3):
            done, action = self.protocol.consume(
                expansion,
                expand=lambda **kwargs: calls.append(kwargs) or {"events": []},
            )
            self.assertFalse(done)
            self.assertIsNone(action)
        # Past the limit the participant is told so once, without failing
        # the turn; asking again after that fails it.
        done, action = self.protocol.consume(expansion, expand=lambda **_: {"events": []})
        self.assertEqual((False, None), (done, action))
        self.assertIn("the limit", self.protocol.pages[-1]["note"])
        with self.assertRaises(ParticipantModelError):
            self.protocol.consume(expansion, expand=lambda **_: {"events": []})
        self.assertEqual(3, len(calls))

    def test_codex_is_a_native_invoker_of_the_core_bytes(self):
        # Claude Code acts through tools; its turn uses the core tool-turn
        # text instead (tests/v2/test_claude_code.py).
        codex = object.__new__(CodexParticipant)
        codex.profile = PROFILE
        self.assertEqual(self.protocol.text, codex._prompt(self.protocol))


def operator_config(*, services=()):
    return build_operator_config(
        profile_id="vigil",
        participant_id="vigil",
        actor_id="discord:bot:9",
        display_name="Vigil",
        instructions="Contribute carefully.",
        platform="discord",
        room_id="42",
        room_name="delivery",
        continuity_scope_id="discord:channel:42",
        attention_model="attention-model",
        participant_model="participant-model",
        services=services,
    )


class OperatorSurfaceTests(unittest.TestCase):
    def test_guided_cli_and_dashboard_share_one_validated_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_root = root / "config"
            state_root = root / "state"
            output = io.StringIO()
            with redirect_stdout(output):
                code = cli.main(
                    [
                        "setup",
                        "--profile",
                        "vigil",
                        "--config-root",
                        str(config_root),
                        "--state-root",
                        str(state_root),
                        "--participant-id",
                        "vigil",
                        "--actor-id",
                        "discord:bot:9",
                        "--display-name",
                        "Vigil",
                        "--instructions",
                        "Contribute carefully.",
                        "--platform",
                        "discord",
                        "--room-id",
                        "42",
                        "--room-name",
                        "delivery",
                        "--continuity-scope-id",
                        "discord:channel:42",
                        "--attention-model",
                        "attention-model",
                        "--participant-model",
                        "participant-model",
                    ]
                )
            self.assertEqual(0, code)
            created = json.loads(output.getvalue())
            self.assertRegex(created["revision"], r"^[0-9a-f]{64}$")
            store = OperatorStore(config_root, state_root, "vigil")
            snapshot = store.snapshot()
            for field in (
                "identity",
                "rooms",
                "models",
                "attention_policy",
                "ack_policy",
                "services",
            ):
                self.assertIn(field, snapshot["config"])
            self.assertIn("discord:42", snapshot["capabilities"])
            self.assertIn("discord:42", snapshot["compatibility"])
            self.assertEqual([], snapshot["recent_receipts"])
            for path in (config_root, state_root, store.paths.config_directory):
                self.assertEqual(0, stat.S_IMODE(path.stat().st_mode) & 0o077)

            with mock.patch.dict(
                os.environ,
                {
                    "NUNCHI_ATTENTION_API_KEY": "attention-secret",
                    "NUNCHI_PARTICIPANT_API_KEY": "participant-secret",
                },
                clear=False,
            ):
                credential_snapshot = store.snapshot()
            serialized = json.dumps(credential_snapshot)
            self.assertNotIn("attention-secret", serialized)
            self.assertNotIn("participant-secret", serialized)
            self.assertEqual(
                "present",
                credential_snapshot["health"]["credentials"]["attention"]["state"],
            )

            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                dashboard_handler(store),
            )
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                connection.request("GET", "/api/v1/operator")
                response = connection.getresponse()
                dashboard_snapshot = json.loads(response.read())
                self.assertEqual(200, response.status)
                self.assertEqual(snapshot["config"], dashboard_snapshot["config"])
                self.assertEqual("DENY", response.getheader("X-Frame-Options"))

                changed = deepcopy(snapshot["config"])
                changed["ack_policy"]["enabled"] = False
                body = json.dumps(changed).encode()
                connection.request(
                    "PUT",
                    "/api/v1/operator/config",
                    body=body,
                    headers={
                        "Content-Type": "application/json",
                        "Content-Length": str(len(body)),
                        "If-Match": snapshot["revision"],
                    },
                )
                update = connection.getresponse()
                update.read()
                self.assertEqual(200, update.status)
                self.assertFalse(store.read()[0]["ack_policy"]["enabled"])

                connection.request(
                    "PUT",
                    "/api/v1/operator/config",
                    body=body,
                    headers={
                        "Content-Type": "application/json",
                        "Content-Length": str(len(body)),
                        "If-Match": snapshot["revision"],
                    },
                )
                stale = connection.getresponse()
                stale.read()
                self.assertEqual(409, stale.status)
                connection.close()
            finally:
                server.shutdown()
                server.server_close()
                worker.join(5)

    def test_dashboard_is_loopback_only(self):
        with tempfile.TemporaryDirectory() as directory:
            store = OperatorStore(
                Path(directory) / "config",
                Path(directory) / "state",
                "vigil",
            )
            store.write(operator_config())
            with self.assertRaises(ValidationError):
                serve_dashboard(store, host="0.0.0.0", port=8765)

    def test_dashboard_diagnostics_reports_install_errors_as_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = OperatorStore(root / "config", root / "state", "vigil")
            store.write(operator_config())
            (store.paths.config_root / "install.json").unlink()
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                dashboard_handler(store),
            )
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                connection.request("GET", "/api/v1/diagnostics")
                response = connection.getresponse()
                body = json.loads(response.read())
                self.assertEqual(500, response.status)
                self.assertIn("marker is absent", body["detail"])
                connection.close()
            finally:
                server.shutdown()
                server.server_close()
                worker.join(5)

    def test_dashboard_service_control_uses_current_profile_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = {
                "name": "room",
                "command": [
                    sys.executable,
                    "-c",
                    "import time; time.sleep(120)",
                ],
                "restart": "always",
                "environment": {},
            }
            store = OperatorStore(root / "config", root / "state", "vigil")
            created = store.write(operator_config(services=[service]))
            manager = ServiceManager(store)
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                dashboard_handler(store),
            )
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                connection.request(
                    "POST",
                    "/api/v1/services/room/start",
                    headers={"If-Match": "stale"},
                )
                stale = connection.getresponse()
                stale.read()
                self.assertEqual(409, stale.status)
                self.assertFalse(manager.status("room")["running"])

                connection.request(
                    "POST",
                    "/api/v1/services/room/start",
                    headers={"If-Match": created["revision"]},
                )
                started = connection.getresponse()
                started.read()
                self.assertEqual(200, started.status)
                self.assertTrue(manager.status("room")["running"])

                connection.request(
                    "POST",
                    "/api/v1/services/room/stop",
                    headers={"If-Match": created["revision"]},
                )
                stopped = connection.getresponse()
                stopped.read()
                self.assertEqual(200, stopped.status)
                self.assertFalse(manager.status("room")["running"])
            finally:
                manager.stop("room")
                connection.close()
                server.shutdown()
                server.server_close()
                worker.join(5)

    def test_profile_revisions_are_stale_write_safe_and_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = OperatorStore(root / "config", root / "state", "vigil")
            second = OperatorStore(root / "config", root / "state", "other")
            initial = first.write(operator_config())
            other_config = operator_config()
            other_config["profile_id"] = "other"
            other_config["identity"]["participant_id"] = "other"
            other_config["identity"]["actor_id"] = "discord:bot:10"
            other_config["identity"]["provenance"] = "operator:other@1"
            second.write(other_config)
            changed = first.read()[0]
            changed["identity"]["display_name"] = "Vigil Updated"
            first.write(changed, expected_revision=initial["revision"])
            with self.assertRaises(ValidationError):
                first.write(changed, expected_revision=initial["revision"])
            self.assertEqual("other", second.read()[0]["identity"]["participant_id"])

    def test_config_and_integrity_pin_commit_as_one_recoverable_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = OperatorStore(root / "config", root / "state", "vigil")
            initial = store.write(operator_config())
            envelope = json.loads(store.paths.config.read_text(encoding="utf-8"))
            self.assertEqual({"config", "digest"}, set(envelope))
            self.assertEqual(initial["revision"], envelope["digest"])
            self.assertFalse(store.paths.digest.exists())
            self.assertFalse(store.paths.profile.exists())
            self.assertFalse(store.paths.profile_digest.exists())

            changed = store.read()[0]
            changed["identity"]["display_name"] = "Committed before crash"
            original_atomic_write = operator_module._atomic_write

            def crash_after_replace(path, payload, *, mode=0o600):
                original_atomic_write(path, payload, mode=mode)
                if path == store.paths.config:
                    raise RuntimeError("simulated process crash after replace")

            with (
                mock.patch.object(
                    operator_module,
                    "_atomic_write",
                    side_effect=crash_after_replace,
                ),
                self.assertRaisesRegex(RuntimeError, "simulated process crash"),
            ):
                store.write(changed, expected_revision=initial["revision"])

            self.assertEqual(
                "Committed before crash",
                store.read()[0]["identity"]["display_name"],
            )
            rolled_back = store.rollback(initial["revision"])
            self.assertEqual("configured", rolled_back["status"])
            self.assertEqual("Vigil", store.read()[0]["identity"]["display_name"])

    def test_config_readers_never_observe_a_torn_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = OperatorStore(root / "config", root / "state", "vigil")
            store.write(operator_config())
            stopped = threading.Event()
            errors = []

            def read_repeatedly():
                while not stopped.is_set():
                    try:
                        store.read()
                    except Exception as exc:  # pragma: no cover - asserted empty below.
                        errors.append(exc)
                        stopped.set()

            reader = threading.Thread(target=read_repeatedly)
            reader.start()
            try:
                for index in range(40):
                    document, revision = store.read()
                    document["identity"]["display_name"] = f"Vigil {index}"
                    store.write(document, expected_revision=revision)
            finally:
                stopped.set()
                reader.join(5)
            self.assertFalse(reader.is_alive())
            self.assertEqual([], errors)

    def test_operator_schema_version_requires_an_exact_integer(self):
        for value in (True, 1.0):
            with self.subTest(value=value):
                config = operator_config()
                config["schema_version"] = value
                with self.assertRaisesRegex(ValidationError, "schema_version"):
                    OperatorStore(
                        Path(tempfile.gettempdir()) / "unused-config",
                        Path(tempfile.gettempdir()) / "unused-state",
                        "vigil",
                    ).write(config)


class ServiceAndInstallLifecycleTests(unittest.TestCase):
    @staticmethod
    def service(*, restart="never", environment=None):
        return {
            "name": "room",
            "command": [sys.executable, "-c", "import time; time.sleep(120)"],
            "restart": restart,
            "environment": environment or {},
        }

    def test_service_start_restart_concurrency_and_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = {
                "name": "room",
                "command": [
                    sys.executable,
                    "-c",
                    "import time; time.sleep(120)",
                ],
                "restart": "always",
                "environment": {},
            }
            store = OperatorStore(root / "config", root / "state", "vigil")
            store.write(operator_config(services=[service]))
            manager = ServiceManager(store)
            results = []
            barrier = threading.Barrier(2)

            def start():
                barrier.wait()
                results.append(manager.start("room"))

            workers = [threading.Thread(target=start) for _ in range(2)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(10)
                self.assertFalse(worker.is_alive())
            self.assertEqual(
                ["already-running", "started"],
                sorted(result["status"] for result in results),
            )
            first_pid = manager.status("room")["pid"]
            self.assertIsInstance(first_pid, int)
            restarted = manager.restart("room")
            self.assertEqual("started", restarted["status"])
            self.assertNotEqual(first_pid, restarted["pid"])

            durable = store.paths.state_directory / "ack.jsonl"
            durable.write_text("durable\n", encoding="utf-8")
            reset = manager.reset("room")
            self.assertEqual("reset", reset["status"])
            self.assertFalse(manager.status("room")["running"])
            self.assertTrue(durable.exists())

            launchd_path, launchd = manager.render_persistent_definition(
                "room",
                platform="darwin",
            )
            self.assertTrue(launchd_path.name.endswith(".plist"))
            self.assertIn(b"nunchi.service_worker", launchd)
            self.assertIn(b"--environment-file", launchd)
            self.assertFalse(plistlib.loads(launchd)["KeepAlive"])
            _, systemd = manager.render_persistent_definition(
                "room",
                platform="linux",
            )
            self.assertIn(b"Restart=no", systemd)
            self.assertIn(b"--environment-file", systemd)

    def test_persistent_install_activates_and_uninstall_deactivates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = {
                "name": "room",
                "command": [sys.executable, "-c", "pass"],
                "restart": "never",
                "environment": {},
            }
            store = OperatorStore(root / "config", root / "state", "vigil")
            store.write(operator_config(services=[service]))
            manager = ServiceManager(store)
            definition = root / "LaunchAgents" / "dev.nunchi.vigil.room.plist"
            payload = plistlib.dumps({"Label": "dev.nunchi.vigil.room"})
            completed = mock.Mock(returncode=0, stdout="")
            with (
                mock.patch.object(
                    manager,
                    "render_persistent_definition",
                    return_value=(definition, payload),
                ),
                mock.patch("nunchi.operator.sys.platform", "darwin"),
                mock.patch(
                    "nunchi.operator.subprocess.run",
                    return_value=completed,
                ) as control,
            ):
                installed = manager.install_persistent("room")
                self.assertTrue(installed["activated"])
                self.assertTrue(definition.exists())
                self.assertEqual(4, control.call_count)
                self.assertIn("bootstrap", control.call_args_list[1].args[0])

                removed = manager.uninstall_persistent("room")
                self.assertTrue(removed["deactivated"])
                self.assertFalse(definition.exists())
                self.assertIn("bootout", control.call_args_list[-1].args[0])

    def test_persistent_install_materializes_private_credentials_outside_unit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = self.service(
                environment={"API_KEY": "NUNCHI_TEST_PERSISTENT_SECRET"}
            )
            store = OperatorStore(root / "config", root / "state", "vigil")
            store.write(operator_config(services=[service]))
            manager = ServiceManager(store)
            definition = root / "LaunchAgents" / "dev.nunchi.vigil.room.plist"
            with (
                mock.patch.dict(
                    os.environ,
                    {"NUNCHI_TEST_PERSISTENT_SECRET": "private-value"},
                    clear=False,
                ),
                mock.patch.object(
                    manager,
                    "render_persistent_definition",
                    return_value=(definition, b"unit-without-secret"),
                ),
                mock.patch("nunchi.operator.sys.platform", "darwin"),
                mock.patch(
                    "nunchi.operator.subprocess.run",
                    return_value=mock.Mock(returncode=0, stdout=""),
                ),
            ):
                installed = manager.install_persistent("room")
            environment_path = Path(installed["environment"])
            self.assertEqual(
                {"NUNCHI_TEST_PERSISTENT_SECRET": "private-value"},
                json.loads(environment_path.read_text(encoding="utf-8")),
            )
            self.assertEqual(0, stat.S_IMODE(environment_path.stat().st_mode) & 0o077)
            self.assertNotIn(b"private-value", definition.read_bytes())

    def test_profile_uninstall_stops_its_supervisor_before_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = {
                "name": "room",
                "command": [
                    sys.executable,
                    "-c",
                    "import time; time.sleep(120)",
                ],
                "restart": "always",
                "environment": {},
            }
            store = OperatorStore(root / "config", root / "state", "vigil")
            store.write(operator_config(services=[service]))
            manager = ServiceManager(store)
            pid = manager.start("room")["pid"]
            self.assertTrue(manager.status("room")["running"])

            removed = store.uninstall()

            self.assertEqual("uninstalled", removed["status"])
            self.assertFalse(store.paths.config_directory.exists())
            self.assertFalse(store.paths.state_directory.exists())
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_untrusted_pidfile_cannot_target_an_unrelated_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = {
                "name": "room",
                "command": [sys.executable, "-c", "pass"],
                "restart": "never",
                "environment": {},
            }
            store = OperatorStore(root / "config", root / "state", "vigil")
            store.write(operator_config(services=[service]))
            manager = ServiceManager(store)
            manager._directory("room").mkdir(parents=True, exist_ok=True)
            manager._pidfile("room").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "pid": os.getpid(),
                        "profile_id": "someone-else",
                        "service": "room",
                        "config_revision": "0" * 64,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch("nunchi.operator.os.kill") as kill:
                result = manager.stop("room")
            self.assertEqual("already-stopped", result["status"])
            kill.assert_not_called()

    def test_stale_valid_pidfile_cannot_signal_a_recycled_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = OperatorStore(root / "config", root / "state", "vigil")
            store.write(operator_config(services=[self.service()]))
            manager = ServiceManager(store)
            manager._directory("room").mkdir(parents=True, exist_ok=True)
            manager._pidfile("room").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "pid": os.getpid(),
                        "profile_id": "vigil",
                        "service": "room",
                        "config_revision": store.read()[1],
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch("nunchi.operator.os.kill") as kill:
                result = manager.stop("room")
            self.assertEqual("already-stopped", result["status"])
            kill.assert_not_called()
            self.assertFalse(manager._pidfile("room").exists())

    def test_orphaned_child_blocks_duplicate_service_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = OperatorStore(root / "config", root / "state", "vigil")
            store.write(operator_config(services=[self.service(restart="always")]))
            manager = ServiceManager(store)
            manager._directory("room").mkdir(parents=True, exist_ok=True)
            (manager._directory("room") / "status.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "state": "running",
                        "supervisor_pid": 999999,
                        "child_pid": os.getpid(),
                        "restart_count": 0,
                        "config_revision": store.read()[1],
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch("nunchi.operator.subprocess.Popen") as popen:
                result = manager.start("room")
            self.assertEqual("orphaned-child", result["status"])
            popen.assert_not_called()

    def test_start_waits_for_supervisor_readiness_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = self.service(environment={"API_KEY": "ABSENT_TEST_API_KEY"})
            store = OperatorStore(root / "config", root / "state", "vigil")
            store.write(operator_config(services=[service]))
            result = ServiceManager(store).start("room")
            self.assertEqual("start-failed", result["status"])
            self.assertFalse(result["running"])
            self.assertTrue(any("ABSENT_TEST_API_KEY" in line for line in result["log_tail"]))

    def test_diagnostics_warns_for_absent_credentials_and_stopped_always_service(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = OperatorStore(root / "config", root / "state", "vigil")
            store.write(operator_config(services=[self.service(restart="always")]))
            diagnosis = store.diagnose()
            self.assertEqual("attention", diagnosis["status"])
            features = [item["feature"] for item in diagnosis["health"]["warnings"]]
            self.assertIn("credential", features)
            self.assertIn("service", features)

    def test_install_upgrade_rollback_and_nonpurging_uninstall(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_root = root / "config"
            state_root = root / "state"
            store = OperatorStore(config_root, state_root, "vigil")
            store.write(operator_config())
            marker = config_root / "install.json"
            old = json.loads(marker.read_text(encoding="utf-8"))
            old["product_version"] = "0.0.test"
            marker.write_text(json.dumps(old), encoding="utf-8")

            upgraded = upgrade(config_root, state_root)
            self.assertEqual("upgraded", upgraded["status"])
            self.assertEqual("verified", verify(config_root)["status"])
            rolled_back = rollback(config_root, "0.0.test")
            self.assertEqual("rolled-back", rolled_back["status"])
            self.assertEqual("0.0.test", rolled_back["product_version"])

            removed = uninstall_state(config_root, state_root, purge=False)
            self.assertFalse(removed["purged"])
            self.assertFalse(marker.exists())
            self.assertTrue(store.paths.config.exists())
            self.assertTrue(state_root.exists())

    def test_purge_rejects_broad_or_mismatched_roots_before_unregistration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_root = root / "config"
            state_root = root / "state"
            store = OperatorStore(config_root, state_root, "vigil")
            store.write(operator_config())
            marker = config_root / "install.json"
            document = json.loads(marker.read_text(encoding="utf-8"))
            document["state_root"] = str(root / "other-state")
            marker.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(InstallError, "exact state roots"):
                uninstall_state(config_root, state_root, purge=True)
            self.assertTrue(marker.exists())
            self.assertTrue(state_root.exists())

            document["state_root"] = str(state_root)
            document["schema_version"] = True
            marker.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(InstallError, "exact state roots"):
                uninstall_state(config_root, state_root, purge=True)
            self.assertTrue(marker.exists())
            self.assertTrue(state_root.exists())


if __name__ == "__main__":
    unittest.main()
