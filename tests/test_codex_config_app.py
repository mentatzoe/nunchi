"""Offline security and contract tests for the Codex V2 config app."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from nunchi.integrations.codex_config_app import (
    TEMPLATE_URI,
    ConfigAppService,
    build_mcp_server,
    load_ui_html,
    main,
)
from nunchi.integrations.codex_session_v2 import save_codex_session
from nunchi.policy import load_operator_policy
from tests.v2.security.helpers import clone_policy, write_policy


class ConfigAppCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.receipts = self.root / "receipts"
        self.receipts.mkdir(mode=0o700)
        document = clone_policy()
        document["receipt_sink"]["directory"] = str(self.receipts)
        self.policy_path = write_policy(self.root, document)
        self.session_path = self.root / "session.json"

    def service(self, **kwargs):
        return ConfigAppService(
            policy_path=self.policy_path,
            session_path=self.session_path,
            **kwargs,
        )

    def test_snapshot_is_v2_and_never_returns_secret_or_paths(self):
        snapshot = self.service().snapshot()
        encoded = json.dumps(snapshot)
        self.assertEqual(snapshot["api_version"], 2)
        self.assertEqual(snapshot["policy"]["identity"]["participant_id"], "vigil")
        self.assertTrue(snapshot["policy"]["classifier"]["credential_configured"])
        self.assertNotIn("do-not-project-this-secret", encoded)
        self.assertNotIn(str(self.policy_path), encoded)
        self.assertNotIn(str(self.receipts), encoded)
        self.assertNotIn("provider.invalid", encoded)
        self.assertFalse(snapshot["capabilities"]["policy_write"])

    def test_attention_write_is_explicit_optimistic_and_closed(self):
        read_only = self.service()
        provenance = read_only.snapshot()["policy"]["provenance"]
        self.assertEqual(
            read_only.update_attention(
                {"preattention_enabled": False},
                expected_provenance=provenance,
            ),
            {"ok": False, "error": "policy-write-disabled"},
        )

        service = self.service(allow_policy_write=True)
        result = service.update_attention(
            {
                "preattention_enabled": False,
                "social_suppression_enabled": False,
                "error_action": "NO_WAKE",
                "transition_defer_margin": None,
            },
            expected_provenance=provenance,
        )
        self.assertTrue(result["ok"])
        updated = load_operator_policy(self.policy_path)
        self.assertFalse(updated.attention.preattention_enabled)
        self.assertFalse(updated.attention.social_suppression_enabled)
        self.assertEqual(updated.attention.error_action, "NO_WAKE")
        self.assertIsNone(updated.attention.transition_defer_margin)
        self.assertEqual(updated.classifier.api_key, "do-not-project-this-secret")
        self.assertEqual(len(updated.authorization.grants), 2)

        stale = service.update_attention(
            {"preattention_enabled": True},
            expected_provenance=provenance,
        )
        self.assertEqual(stale, {"ok": False, "error": "policy-stale"})
        closed = service.update_attention(
            {"participant_id": "attacker"},
            expected_provenance=updated.provenance,
        )
        self.assertEqual(closed, {"ok": False, "error": "policy-update-invalid"})

    def test_receipts_are_bounded_newest_first_and_unsafe_files_are_ignored(self):
        older = self.receipts / "attention-old.jsonl"
        newer = self.receipts / "transport-new.jsonl"
        older.write_text(json.dumps({"request_id": "old"}), encoding="utf-8")
        newer.write_text(json.dumps({"request_id": "new"}), encoding="utf-8")
        older.chmod(0o600)
        newer.chmod(0o600)
        older.touch()
        newer.touch()
        unsafe = self.receipts / "attention-unsafe.jsonl"
        unsafe.write_text(json.dumps({"request_id": "unsafe"}), encoding="utf-8")
        unsafe.chmod(0o644)
        result = self.service().receipts(limit=1)
        self.assertTrue(result["available"])
        self.assertEqual(len(result["receipts"]), 1)
        self.assertNotEqual(result["receipts"][0]["request_id"], "unsafe")

    def test_session_reset_requires_explicit_process_authority(self):
        save_codex_session(
            self.session_path,
            "019f4914-a9c7-7090-bec3-0e78fa9b84e1",
        )
        self.assertEqual(self.service().snapshot()["health"]["codex_session"]["state"], "valid")
        self.assertEqual(
            self.service().reset_session(),
            {"ok": False, "error": "session-reset-disabled"},
        )
        result = self.service(allow_session_reset=True).reset_session()
        self.assertTrue(result["ok"])
        self.assertEqual(result["snapshot"]["health"]["codex_session"]["state"], "absent")

    def test_help_is_import_safe_and_ui_has_only_v2_controls(self):
        with self.assertRaises(SystemExit) as caught:
            main(["--help"])
        self.assertEqual(caught.exception.code, 0)
        html = load_ui_html()
        for fragment in (
            "Participant-shaped pre-attention",
            "Allow model SUPPRESS",
            "update_nunchi_attention",
            "get_nunchi_receipts",
            'method:"tools/call"',
            "textContent",
        ):
            self.assertIn(fragment, html)
        self.assertNotIn("PASS", html)
        self.assertNotIn("SPEAK", html)
        self.assertNotIn("<script src=", html)
        self.assertNotIn("https://", html)


@unittest.skipUnless(importlib.util.find_spec("mcp"), "mcp extra not installed")
class MCPAppsContract(unittest.TestCase):
    def test_tools_and_ui_are_v2_and_mutations_are_app_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipts = root / "receipts"
            receipts.mkdir(mode=0o700)
            document = clone_policy()
            document["receipt_sink"]["directory"] = str(receipts)
            service = ConfigAppService(
                policy_path=write_policy(root, document),
                session_path=root / "session.json",
            )
            server = build_mcp_server(service)

            async def inspect():
                tools = {tool.name: tool for tool in await server.list_tools()}
                resources = await server.list_resources()
                content = list(await server.read_resource(TEMPLATE_URI))
                return tools, resources, content

            tools, resources, content = asyncio.run(inspect())
        self.assertEqual(
            set(tools),
            {
                "open_nunchi_config",
                "get_nunchi_config",
                "update_nunchi_attention",
                "reset_nunchi_session",
                "get_nunchi_receipts",
            },
        )
        self.assertEqual(tools["update_nunchi_attention"].meta["ui"]["visibility"], ["app"])
        self.assertEqual(tools["reset_nunchi_session"].meta["ui"]["visibility"], ["app"])
        self.assertEqual(str(resources[0].uri), TEMPLATE_URI)
        self.assertIn("Nunchi V2", content[0].content)


if __name__ == "__main__":
    unittest.main()
