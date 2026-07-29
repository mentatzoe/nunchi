from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from nunchi.integrations import hermes_v2
from nunchi.integrations.hermes_dashboard_install import (
    DashboardInstallError,
    install_dashboard,
    verify_dashboard,
)
from nunchi.integrations.hermes_dashboard_store import (
    DashboardConfigConflict,
    DashboardConfigReadOnly,
    channel_directory,
    read_config_snapshot,
    read_receipts,
    write_config_document,
)


def _document(root: Path) -> dict:
    return {
        "schema_version": 2,
        "hermes_profile": "default",
        "state_directory": str(root / "state"),
        "rooms": [
            {
                "binding": {
                    "participant_id": "participant",
                    "actor_id": "discord:actor:999",
                    "platform": "discord",
                    "room_id": "42",
                    "continuity_scope_id": "discord-room-42",
                    "names": ["Nunchi"],
                    "room_kind": "group",
                    "provenance": "test:dashboard",
                },
                "profile": {
                    "document": {
                        "profile_id": "participant-profile",
                        "participant_id": "participant",
                        "actor_id": "discord:actor:999",
                        "instructions": "Be useful and concise.",
                        "provenance": "test:dashboard",
                    }
                },
                "attention": {
                    "policy": {
                        "suppression_enabled": True,
                        "suppression_recovery_verified": False,
                    }
                },
                "limits": {},
                "participant": {
                    "timeout_seconds": 300,
                    "max_expansions": 3,
                },
            }
        ],
    }


def _write_config(root: Path) -> tuple[Path, Path, dict, dict[str, str]]:
    document = _document(root)
    config_path = root / "hermes-v2.json"
    config_path.write_text(
        json.dumps(document, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    config_path.chmod(0o600)
    digest = hashlib.sha256(config_path.read_bytes()).hexdigest()
    digest_path = root / "hermes-v2.json.sha256"
    digest_path.write_text(f"{digest}\n", encoding="ascii")
    digest_path.chmod(0o600)
    environ = {
        "NUNCHI_HERMES_V2_CONFIG": str(config_path),
        "NUNCHI_HERMES_V2_CONFIG_SHA256_FILE": str(digest_path),
    }
    return config_path, digest_path, document, environ


class HermesDashboardConfigTests(unittest.TestCase):
    def test_inline_profile_is_pinned_by_outer_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path, _, _, environ = _write_config(root)
            source = hermes_v2.resolve_config_source("default", environ=environ)
            loaded = hermes_v2.load_pinned_config(
                config_path,
                expected_sha256=source.expected_sha256,
                hermes_profile="default",
            )
            profile = loaded.rooms[0].profile
            self.assertEqual("participant-profile", profile.profile_id)
            self.assertEqual("participant", profile.participant_id)
            self.assertRegex(profile.sha256, r"^[0-9a-f]{64}$")

    def test_sidecar_config_round_trip_and_conflict(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path, digest_path, document, environ = _write_config(root)
            before = read_config_snapshot("default", environ=environ)
            changed = json.loads(json.dumps(document))
            changed["rooms"][0]["profile"]["document"]["instructions"] = (
                "Answer only when the participant should contribute."
            )
            after = write_config_document(
                "default",
                document=changed,
                expected_sha256=before.sha256,
                environ=environ,
            )
            self.assertNotEqual(before.sha256, after.sha256)
            self.assertEqual(after.sha256, digest_path.read_text().strip())
            self.assertEqual(0, config_path.stat().st_mode & 0o077)
            self.assertEqual(0, digest_path.stat().st_mode & 0o077)
            self.assertEqual(changed, after.document)
            with self.assertRaises(DashboardConfigConflict):
                write_config_document(
                    "default",
                    document=changed,
                    expected_sha256=before.sha256,
                    environ=environ,
                )

    def test_invalid_change_does_not_replace_config_or_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path, digest_path, document, environ = _write_config(root)
            before = read_config_snapshot("default", environ=environ)
            config_bytes = config_path.read_bytes()
            digest_bytes = digest_path.read_bytes()
            invalid = json.loads(json.dumps(document))
            invalid["rooms"] = []
            with self.assertRaisesRegex(Exception, "at least one room"):
                write_config_document(
                    "default",
                    document=invalid,
                    expected_sha256=before.sha256,
                    environ=environ,
                )
            self.assertEqual(config_bytes, config_path.read_bytes())
            self.assertEqual(digest_bytes, digest_path.read_bytes())

    def test_literal_digest_is_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path, _, document, sidecar_environ = _write_config(root)
            digest = hashlib.sha256(config_path.read_bytes()).hexdigest()
            environ = {
                "NUNCHI_HERMES_V2_CONFIG": str(config_path),
                "NUNCHI_HERMES_V2_CONFIG_SHA256": digest,
            }
            snapshot = read_config_snapshot("default", environ=environ)
            self.assertFalse(snapshot.source.dashboard_writable)
            with self.assertRaises(DashboardConfigReadOnly):
                write_config_document(
                    "default",
                    document=document,
                    expected_sha256=snapshot.sha256,
                    environ=environ,
                )
            self.assertTrue(
                hermes_v2.resolve_config_source(
                    "default",
                    environ=sidecar_environ,
                ).dashboard_writable
            )

    def test_literal_and_digest_file_are_rejected_together(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path, digest_path, _, _ = _write_config(root)
            digest = hashlib.sha256(config_path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(Exception, "either a literal"):
                hermes_v2.resolve_config_source(
                    "default",
                    environ={
                        "NUNCHI_HERMES_V2_CONFIG": str(config_path),
                        "NUNCHI_HERMES_V2_CONFIG_SHA256": digest,
                        "NUNCHI_HERMES_V2_CONFIG_SHA256_FILE": str(digest_path),
                    },
                )

    def test_receipts_are_bounded_and_room_attributed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, _, environ = _write_config(root)
            snapshot = read_config_snapshot("default", environ=environ)
            room = snapshot.config.rooms[0]
            state = hermes_v2.room_state_directory(
                snapshot.config.state_directory,
                profile="default",
                binding=room.binding,
            )
            state.mkdir(mode=0o700, parents=True)
            receipts_path = state / "receipts.jsonl"
            receipts_path.write_text(
                '{"event":"older","created_at":"2026-01-01T00:00:00Z"}\n'
                '{"event":"newer","created_at":"2026-01-02T00:00:00Z"}\n',
                encoding="utf-8",
            )
            receipts_path.chmod(0o600)
            result = read_receipts("default", limit=1, environ=environ)
            self.assertEqual("newer", result["receipts"][0]["event"])
            self.assertEqual(
                {
                    "platform": "discord",
                    "room_id": "42",
                    "participant_id": "participant",
                },
                result["receipts"][0]["_nunchi_room"],
            )

    def test_channel_directory_uses_hermes_discovery_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            (home / "channel_directory.json").write_text(
                json.dumps(
                    {
                        "platforms": {
                            "telegram": [{"id": "7", "name": "Zoe"}],
                            "discord": [
                                {"id": "42", "name": "general", "guild": "Nunchi"}
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                [
                    {
                        "platform": "discord",
                        "id": "42",
                        "name": "general",
                        "guild": "Nunchi",
                    },
                    {
                        "platform": "telegram",
                        "id": "7",
                        "name": "Zoe",
                        "guild": "",
                    },
                ],
                channel_directory(environ={"HERMES_HOME": str(home)}),
            )


class HermesDashboardInstallTests(unittest.TestCase):
    def test_install_and_verify_packaged_dashboard(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            installed = install_dashboard(hermes_home=home)
            dashboard = (
                home / "plugins" / "nunchi-v2-dashboard" / "dashboard"
            )
            self.assertTrue(installed["ok"])
            self.assertEqual(installed, verify_dashboard(hermes_home=home))
            manifest = json.loads(
                (dashboard / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual("nunchi-v2", manifest["name"])
            self.assertEqual("plugin_api.py", manifest["api"])
            self.assertFalse(
                (home / "plugins" / "nunchi-v2-dashboard" / "plugin.yaml").exists()
            )
            self.assertIn(
                "nunchi.integrations.hermes_dashboard_api",
                (dashboard / "plugin_api.py").read_text(encoding="utf-8"),
            )

    def test_verify_rejects_modified_asset(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            install_dashboard(hermes_home=home)
            path = (
                home
                / "plugins"
                / "nunchi-v2-dashboard"
                / "dashboard"
                / "index.js"
            )
            path.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(DashboardInstallError, "changed"):
                verify_dashboard(hermes_home=home)

    def test_ui_uses_authenticated_plugin_api_and_restart(self):
        path = (
            Path("src")
            / "nunchi"
            / "integrations"
            / "hermes_dashboard_assets"
            / "index.js"
        )
        source = path.read_text(encoding="utf-8")
        self.assertIn('var API = "/api/plugins/nunchi-v2"', source)
        self.assertIn("restart_endpoint", source)
        self.assertIn("Save & restart", source)
        self.assertIn("React.createElement", source)
        self.assertNotIn("innerHTML", source)

    def test_project_declares_dashboard_command_and_package_data(self):
        source = Path("pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("nunchi-hermes-dashboard", source)
        self.assertIn("hermes_dashboard_assets", source)


if __name__ == "__main__":
    unittest.main()
