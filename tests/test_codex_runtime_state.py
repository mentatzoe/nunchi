"""Offline tests for Codex hot runtime policy and receipt access."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from nunchi.integrations import codex_runtime_state as runtime


class TestStatePersistence(unittest.TestCase):
    def test_missing_state_is_empty_versioned_state(self):
        with tempfile.TemporaryDirectory() as td:
            state = runtime.load_state(pathlib.Path(td) / "missing.json")
        self.assertEqual(state, {"version": runtime.STATE_VERSION})

    def test_malformed_existing_state_is_explicit_error(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "state.json"
            path.write_text("not-json", encoding="utf-8")
            with self.assertRaises(runtime.RuntimeStateError):
                runtime.load_state(path)

    def test_save_is_canonical_and_round_trips(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "nested" / "state.json"
            saved = runtime.save_state(
                path,
                {
                    "global": {"senders": "HUMANS", "model": "  deepseek/v4  "},
                    "channels": {"123": {"enabled": True}},
                },
                updated_by="test",
            )
            loaded = runtime.load_state(path)

        self.assertEqual(saved, loaded)
        self.assertEqual(loaded["global"]["senders"], "humans")
        self.assertEqual(loaded["global"]["model"], "deepseek/v4")
        self.assertEqual(loaded["updated_by"], "test")
        self.assertTrue(loaded["updated_at"])


class TestPatchSemantics(unittest.TestCase):
    def test_null_deletes_empty_scope_resets_and_unknown_keys_are_reported(self):
        current = {
            "global": {"senders": "humans", "verbosity": "debug"},
            "channels": {
                "123": {"enabled": True, "model": "old"},
                "456": {"enabled": False},
            },
        }
        updated, rejected = runtime.apply_patch(
            current,
            {
                "global": {"senders": None, "made_up": True},
                "channels": {
                    "123": {"model": "new", "nope": 1},
                    "456": {},
                },
                "root_nope": {},
            },
        )

        self.assertEqual(updated["global"], {"verbosity": "debug"})
        self.assertEqual(updated["channels"], {"123": {"enabled": True, "model": "new"}})
        self.assertEqual(
            rejected,
            ["channels.123.nope", "global.made_up", "root_nope"],
        )

    def test_invalid_values_fail_without_partial_result(self):
        for patch in (
            {"global": {"enabled": "yes"}},
            {"global": {"senders": "sometimes"}},
            {"global": {"verbosity": "verbose"}},
            {"channels": {"bad id": {"enabled": True}}},
        ):
            with self.subTest(patch=patch):
                with self.assertRaises(runtime.RuntimeStateError):
                    runtime.apply_patch({}, patch)


class TestPolicyResolution(unittest.TestCase):
    def setUp(self):
        self.baseline = {
            "enabled": True,
            "senders": "all",
            "allow_from": [],
            "verbosity": "normal",
            "model": None,
            "pinned_rules": None,
        }

    def test_finite_baseline_skips_unknown_channel_until_explicit_hot_add(self):
        self.assertIsNone(
            runtime.resolve_channel_policy(self.baseline, {}, "999", {"123"})
        )
        effective = runtime.resolve_channel_policy(
            self.baseline,
            {"channels": {"999": {"enabled": True, "senders": "humans"}}},
            "999",
            {"123"},
        )
        self.assertEqual(effective["senders"], "humans")

    def test_channel_override_layers_over_global_and_can_disable(self):
        state = {
            "global": {"senders": "humans", "model": "global-model"},
            "channels": {"123": {"senders": "allowlist", "allow_from": ["Zoe"]}},
        }
        effective = runtime.resolve_channel_policy(self.baseline, state, "123", {"123"})
        self.assertEqual(effective["model"], "global-model")
        self.assertEqual(effective["senders"], "allowlist")
        self.assertEqual(effective["allow_from"], ["Zoe"])

        state["channels"]["123"]["enabled"] = False
        self.assertIsNone(runtime.resolve_channel_policy(self.baseline, state, "123", {"123"}))

    def test_empty_baseline_channel_set_is_wildcard(self):
        effective = runtime.resolve_channel_policy(self.baseline, {}, "anything", set())
        self.assertIsNotNone(effective)

    def test_sender_policy_matches_bot_kind_name_and_id(self):
        human = {"author_id": "362", "author_name": "DecisionParalysis", "author_is_bot": False}
        bot = {"author_id": "999", "author_name": "Aether", "author_is_bot": True}
        self.assertTrue(runtime.sender_is_admitted({"senders": "humans"}, human))
        self.assertFalse(runtime.sender_is_admitted({"senders": "humans"}, bot))
        self.assertTrue(
            runtime.sender_is_admitted(
                {"senders": "allowlist", "allow_from": ["decisionparalysis"]},
                human,
            )
        )
        self.assertTrue(
            runtime.sender_is_admitted(
                {"senders": "allowlist", "allow_from": ["362"]},
                human,
            )
        )


class TestReceiptTail(unittest.TestCase):
    def test_returns_newest_first_and_skips_malformed_lines(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "receipts.jsonl"
            path.write_text(
                json.dumps({"message_id": "one"})
                + "\nmalformed\n"
                + json.dumps({"message_id": "two"})
                + "\n",
                encoding="utf-8",
            )
            receipts = runtime.tail_receipts(path, limit=10)
        self.assertEqual([item["message_id"] for item in receipts], ["two", "one"])


if __name__ == "__main__":
    unittest.main()
