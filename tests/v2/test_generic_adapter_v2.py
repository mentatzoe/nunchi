from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import nunchi.integrations.subprocess_participant_v2 as subprocess_v2
from nunchi.adapters.channel_v2 import (
    GenericAdapterV2Error,
    JSONLinesActionSinkV2,
    _native_document,
    _strict_json,
    build_runtime,
)
from nunchi.integrations.subprocess_participant_v2 import SubprocessParticipantV2
from nunchi.participant import ParticipantTurn
from tests.v2.security.helpers import clone_policy, write_policy


class SubprocessParticipantCases(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name) / "participant"
        self.workspace.mkdir(mode=0o700)

    def test_child_gets_exact_packet_and_minimal_explicit_environment(self):
        program = (
            "import json,os,sys; p=json.load(sys.stdin); "
            "print(json.dumps({'kind':'message','content':json.dumps({"
            "'request_id':p['request_id'],'home':os.environ.get('HOME'),"
            "'allowed':os.environ.get('PARTICIPANT_KEY'),"
            "'discord':os.environ.get('NUNCHI_DISCORD_TOKEN')},sort_keys=True)}))"
        )
        participant = SubprocessParticipantV2(
            command=[sys.executable, "-c", program],
            workspace=self.workspace,
            pass_env=("PARTICIPANT_KEY",),
            environ={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "PARTICIPANT_KEY": "participant-only",
                "NUNCHI_DISCORD_TOKEN": "must-not-cross",
            },
        )
        result = participant(
            ParticipantTurn({"request_id": "req-1", "events": []}, None)
        )
        content = json.loads(result["content"])
        self.assertEqual(content["request_id"], "req-1")
        self.assertEqual(content["home"], str(self.workspace))
        self.assertEqual(content["allowed"], "participant-only")
        self.assertIsNone(content["discord"])

    def test_reserved_secret_and_unsafe_workspace_are_rejected(self):
        with self.assertRaises(ValueError):
            SubprocessParticipantV2(
                command=[sys.executable, "-c", "print('null')"],
                workspace=self.workspace,
                pass_env=("NUNCHI_DISCORD_TOKEN",),
                environ={"NUNCHI_DISCORD_TOKEN": "secret"},
            )
        self.workspace.chmod(0o750)
        with self.assertRaises(ValueError):
            SubprocessParticipantV2(
                command=[sys.executable, "-c", "print('null')"],
                workspace=self.workspace,
            )

    def test_non_json_or_nonzero_child_fails_without_exposing_stderr(self):
        for program in (
            "import sys; print('not-json')",
            "import sys; print('sensitive', file=sys.stderr); raise SystemExit(4)",
        ):
            with self.subTest(program=program):
                participant = SubprocessParticipantV2(
                    command=[sys.executable, "-c", program],
                    workspace=self.workspace,
                )
                with self.assertRaises(RuntimeError) as caught:
                    participant(ParticipantTurn({"request_id": "req-1"}, None))
                self.assertNotIn("sensitive", str(caught.exception))

    def test_child_json_rejects_duplicate_keys_and_nonfinite_values(self):
        for output in (
            "{\"kind\":\"message\",\"content\":\"a\",\"content\":\"b\"}",
            "{\"kind\":\"message\",\"content\":NaN}",
        ):
            with self.subTest(output=output):
                participant = SubprocessParticipantV2(
                    command=[sys.executable, "-c", f"print({output!r})"],
                    workspace=self.workspace,
                )
                with self.assertRaises(RuntimeError):
                    participant(ParticipantTurn({"request_id": "req-1"}, None))

    def test_child_output_is_bounded_while_the_process_runs(self):
        participant = SubprocessParticipantV2(
            command=[
                sys.executable,
                "-c",
                "import sys,time; sys.stdout.write('x'*10000); sys.stdout.flush(); time.sleep(30)",
            ],
            workspace=self.workspace,
            timeout_seconds=10,
        )
        with mock.patch.object(subprocess_v2, "MAX_OUTPUT_BYTES", 64):
            started = __import__("time").monotonic()
            with self.assertRaisesRegex(RuntimeError, "exceeded its budget"):
                participant(ParticipantTurn({"request_id": "req-1"}, None))
            self.assertLess(__import__("time").monotonic() - started, 5)


class GenericActionSinkCases(unittest.TestCase):
    def test_action_is_written_once_before_transport_receipt(self):
        stream = io.StringIO()
        calls = []

        class RecordingStream(io.StringIO):
            def write(self, value):
                calls.append("action")
                return super().write(value)

        stream = RecordingStream()
        sink = JSONLinesActionSinkV2(
            stream=stream,
            receipt_sink=lambda receipt: calls.append(receipt["stage"]),
        )
        action = {"kind": "message", "content": "hello"}
        sink("req-1", action)
        self.assertEqual(calls, ["action", "transport"])
        self.assertEqual(json.loads(stream.getvalue())["action"], action)
        with self.assertRaises(GenericAdapterV2Error):
            sink("req-1", action)

    def test_capacity_fails_closed_without_evicting_replay_binding(self):
        sink = JSONLinesActionSinkV2(
            stream=io.StringIO(),
            receipt_sink=lambda receipt: None,
            max_request_ids=1,
        )
        sink("req-1", {"kind": "message", "content": "one"})
        with self.assertRaises(GenericAdapterV2Error):
            sink("req-2", {"kind": "message", "content": "two"})
        with self.assertRaises(GenericAdapterV2Error):
            sink("req-1", {"kind": "message", "content": "one"})


class GenericRuntimeCases(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.receipts = self.root / "receipts"
        self.receipts.mkdir(mode=0o700)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir(mode=0o700)
        document = clone_policy()
        document["attention"]["preattention_enabled"] = False
        document["recoverability"]["continuity_scope_id"] = "reference:room:1"
        document["receipt_sink"]["directory"] = str(self.receipts)
        self.policy = write_policy(self.root, document)

    def arguments(self):
        program = "import json; print(json.dumps({'kind':'message','content':'hello from participant'}))"
        return argparse.Namespace(
            policy=self.policy,
            participant_id="vigil",
            participant_actor_id="reference:user:vigil",
            participant_name="Vigil",
            platform="reference",
            room_id="room-1",
            continuity_scope_id="reference:room:1",
            continuity="restart-safe",
            restart_gap="false",
            participant_workspace=self.workspace,
            participant_timeout=30,
            participant_env=[],
            silent_participant=False,
            participant_command=[sys.executable, "-c", program],
        )

    def test_trusted_bypass_runs_direct_participant_and_writes_all_four_stages(self):
        output = io.StringIO()
        runtime, source, receipt_sink = build_runtime(self.arguments(), output=output)
        native = source.native_input(
            delivery_id="reference:delivery:1",
            authorized=True,
            routing_room_id="room-1",
            event={
                "id": "reference:event:1",
                "type": "message",
                "author_id": "reference:user:zoe",
                "text": "Vigil, can you help?",
                "mentioned_actor_ids": ["reference:user:vigil"],
                "mentions_room": False,
            },
            actors={
                "reference:user:zoe": {"display_name": "Zoe", "kind": "human"},
                "reference:user:vigil": {"display_name": "Vigil", "kind": "bot"},
            },
        )
        result = runtime.process_delivery(native)[0]
        receipt_sink.close()
        action = json.loads(output.getvalue())
        self.assertEqual(action["action"]["content"], "hello from participant")
        self.assertEqual(result["decision"]["status"], "bypass")
        self.assertEqual(result["participant"]["outcome"], "sent")
        records = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in self.receipts.iterdir()
        ]
        self.assertEqual(
            {record["stage"] for record in records},
            {"observation", "attention", "participant-host", "transport"},
        )

    def test_recoverability_claim_cannot_exceed_host_capability(self):
        arguments = self.arguments()
        arguments.continuity = "session-only"
        with self.assertRaises(GenericAdapterV2Error):
            build_runtime(arguments, output=io.StringIO())

    def test_strict_native_input_rejects_duplicates_nonfinite_and_integer_bool(self):
        with self.assertRaises(ValueError):
            _strict_json('{"x":1,"x":2}')
        with self.assertRaises(ValueError):
            _strict_json('{"x":NaN}')
        with self.assertRaises(GenericAdapterV2Error):
            _native_document(
                {
                    "delivery_id": "d1",
                    "authorized": 1,
                    "routing_room_id": "room-1",
                    "event": {},
                }
            )


if __name__ == "__main__":
    unittest.main()
