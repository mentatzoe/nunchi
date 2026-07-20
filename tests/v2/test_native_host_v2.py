from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from nunchi.adapters.native_host_v2 import (
    DurableCursorStoreV2,
    NativeHostV2Error,
    build_native_runtime,
)
from tests.v2.security.helpers import clone_policy, write_policy


class DurableCursorStoreCases(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.root.chmod(0o700)
        self.path = self.root / "matrix.json"

    def test_cursor_is_bound_and_atomically_replaceable(self):
        store = DurableCursorStoreV2(
            self.path,
            platform="matrix",
            room_id="!one:example.test",
            cursor_type=str,
        )
        self.addCleanup(store.close)
        self.assertIsNone(store.load())
        store.save("s1")
        store.save("s2")
        self.assertEqual(store.load(), "s2")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            {path.name for path in self.root.iterdir()},
            {"matrix.json"},
        )

    def test_wrong_binding_permissions_and_symlink_are_rejected(self):
        store = DurableCursorStoreV2(
            self.path,
            platform="matrix",
            room_id="!one:example.test",
            cursor_type=str,
        )
        store.save("s1")
        store.close()
        with self.assertRaises(NativeHostV2Error):
            other = DurableCursorStoreV2(
                self.path,
                platform="matrix",
                room_id="!other:example.test",
                cursor_type=str,
            )
            self.addCleanup(other.close)
            other.load()
        self.path.chmod(0o640)
        with self.assertRaises(NativeHostV2Error):
            DurableCursorStoreV2(
                self.path,
                platform="matrix",
                room_id="!one:example.test",
                cursor_type=str,
            )
        self.path.unlink()
        target = self.root / "target.json"
        target.write_text("{}", encoding="utf-8")
        target.chmod(0o600)
        self.path.symlink_to(target)
        with self.assertRaises(NativeHostV2Error):
            DurableCursorStoreV2(
                self.path,
                platform="matrix",
                room_id="!one:example.test",
                cursor_type=str,
            )

    def test_integer_cursor_rejects_boolean_and_negative_values(self):
        store = DurableCursorStoreV2(
            self.root / "telegram.json",
            platform="telegram",
            room_id="42",
            cursor_type=int,
        )
        self.addCleanup(store.close)
        for value in (True, -1, "1"):
            with self.subTest(value=value):
                with self.assertRaises(NativeHostV2Error):
                    store.save(value)


class NativeRuntimeConstructionCases(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.receipts = self.root / "receipts"
        self.receipts.mkdir(mode=0o700)
        document = clone_policy()
        document["recoverability"]["continuity_scope_id"] = "matrix:room:one"
        document["receipt_sink"]["directory"] = str(self.receipts)
        self.policy = write_policy(self.root, document)

    def arguments(self):
        return argparse.Namespace(
            policy=self.policy,
            participant_id="vigil",
            participant_name="Vigil",
            participant_workspace=None,
            participant_timeout=30,
            participant_env=[],
            silent_participant=True,
            participant_command=None,
        )

    def test_host_refuses_unsupported_recoverability_claim(self):
        with self.assertRaises(NativeHostV2Error):
            build_native_runtime(
                self.arguments(),
                participant_actor_id="matrix:user:@vigil:example.test",
                platform="matrix",
                room_id="one",
                continuity_scope_id="matrix:room:one",
                continuity="session-only",
                has_restart_gap=True,
                event_visibility={"message": "history-and-live"},
                action_sink_factory=lambda _sink: lambda _request, _action: None,
            )

    def test_host_builds_when_suppression_is_not_claimed_recoverable(self):
        document = clone_policy()
        document["recoverability"]["continuity_scope_id"] = "matrix:room:one"
        document["recoverability"]["eligible"] = False
        document["receipt_sink"]["directory"] = str(self.receipts)
        write_policy(self.root, document)
        native = build_native_runtime(
            self.arguments(),
            participant_actor_id="matrix:user:@vigil:example.test",
            platform="matrix",
            room_id="one",
            continuity_scope_id="matrix:room:one",
            continuity="session-only",
            has_restart_gap=True,
            event_visibility={"message": "history-and-live"},
            action_sink_factory=lambda _sink: lambda _request, _action: None,
        )
        native.close()


if __name__ == "__main__":
    unittest.main()
