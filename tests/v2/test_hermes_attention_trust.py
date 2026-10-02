from __future__ import annotations

import json
import importlib
from copy import deepcopy
import sys
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace, ModuleType
from unittest.mock import patch

from nunchi.attention import AttentionEngine, AttentionModelSelection, HostStructuredAttentionModel, ParticipantProfile
from nunchi.errors import ValidationError
from nunchi.integrations.hermes_attention_trust import attention_trust_status
from nunchi.integrations import hermes_dashboard_store as store
from tests.v2.contract.schema_helpers import make_receipt, make_request

from nunchi.integrations.hermes_dashboard_store import (
    read_dashboard_snapshot,
    write_config_document,
)
from tests.v2.test_hermes_dashboard import _document, _write_config


class AttentionTrustSetupTests(unittest.TestCase):
    def test_injected_environment_without_home_cannot_select_real_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, document, env = _write_config(root)
            before = read_dashboard_snapshot("default", environ=env)
            env.pop("HERMES_HOME")
            # Trap fallback before any host path can be read or written.
            with patch.object(Path, "home", side_effect=AssertionError("ambient home selected")):
                with self.assertRaisesRegex(store.DashboardConfigError, "HERMES_HOME"):
                    write_config_document("default", document=document,
                                          expected_revision=before.revision, environ=env)
            self.assertFalse((root / "config.yaml").exists())

    def test_editing_trust_does_not_mutate_aliased_unrelated_yaml_nodes(self):
        from nunchi.integrations.hermes_attention_trust import _llm_entry
        shared = {"llm": {"allow_model_override": False}}
        document = {"plugins": {"entries": {"nunchi": shared, "other": shared}}}
        _llm_entry(document)["allow_model_override"] = True
        self.assertIs(document["plugins"]["entries"]["other"]["llm"]["allow_model_override"], False)

    def test_interrupted_first_save_restores_host_bytes_or_absence(self):
        for raw in (None, b'{"plugins":{"entries":{"nunchi":{"llm":{"allow_model_override":false}}}}}\n'):
            with self.subTest(existing=raw is not None), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary)
                path = home / "config.yaml"
                if raw is not None:
                    path.write_bytes(raw)
                env = {"HERMES_HOME": str(home)}
                before = read_dashboard_snapshot("default", environ=env)
                original = store._publish_complete_file_exclusive

                def interrupted(source, destination, **kwargs):
                    if destination.suffix == ".sha256":
                        raise OSError("injected digest publication failure")
                    return original(source, destination, **kwargs)

                with patch.object(store, "_publish_complete_file_exclusive", side_effect=interrupted):
                    with self.assertRaisesRegex(OSError, "injected"):
                        write_config_document("default", document=_document(home),
                                              expected_revision=before.revision, environ=env)
                self.assertEqual(raw, path.read_bytes() if path.exists() else None)
                self.assertTrue(read_dashboard_snapshot("default", environ=env).bootstrap_required)

    def test_invalid_and_symlinked_host_config_do_not_activate_rooms(self):
        for kind in ("invalid", "symlink", "nonmapping"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary)
                path = home / "config.yaml"
                target = home / "unrelated.json"
                target.write_text('{"untouched":true}')
                if kind == "symlink":
                    path.symlink_to(target)
                else:
                    path.write_text("plugins: [broken" if kind == "invalid" else '{"plugins":false}')
                original = path.read_bytes()
                env = {"HERMES_HOME": str(home)}
                before = read_dashboard_snapshot("default", environ=env)
                with self.assertRaises(ValidationError):
                    write_config_document("default", document=_document(home),
                                          expected_revision=before.revision, environ=env)
                self.assertEqual(original, path.read_bytes())
                self.assertFalse(before.source.write_path.exists())
                self.assertEqual('{"untouched":true}', target.read_text())

    def test_allowlists_follow_multiple_rooms_and_route_removal(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            env = {"HERMES_HOME": str(home)}
            document = _document(home)
            other = deepcopy(document["rooms"][0])
            other["binding"]["room_id"] = "43"
            other["attention"]["model"] = {"provider": "other-provider", "model": "other-model"}
            document["rooms"].append(other)
            before = read_dashboard_snapshot("default", environ=env)
            saved = write_config_document("default", document=document,
                                          expected_revision=before.revision, environ=env)
            self.assertTrue(attention_trust_status(home, saved.config)["ready"])
            path = home / "config.yaml"
            llm = json.loads(path.read_text())["plugins"]["entries"]["nunchi"]["llm"]
            self.assertEqual(["other-provider", "test-provider"], llm["allowed_providers"])
            document["rooms"].pop()
            saved = write_config_document("default", document=document,
                                          expected_revision=saved.revision, environ=env)
            host = json.loads(path.read_text())
            llm = host["plugins"]["entries"]["nunchi"]["llm"]
            self.assertEqual(["test-model"], llm["allowed_models"])
            llm["allowed_models"] = ["not-the-configured-model"]
            path.write_text(json.dumps(host))
            status = attention_trust_status(home, saved.config)
            self.assertFalse(status["ready"])
            self.assertIn("allowed_models", status["missing"])
            self.assertFalse(status["runtime_verified"])

    def test_ui_discloses_permission_write_and_allows_unchanged_config_repair(self):
        from importlib.resources import files
        source = files("nunchi.integrations.hermes_dashboard_assets").joinpath("index.js").read_text()
        self.assertIn("Save & allow attention models", source)
        self.assertIn("snapshot.attention_trust", source)
        self.assertIn("!dirty && !needsTrustRepair && andRestart", source)

    def test_dashboard_reports_missing_trust_without_granting_it(self):
        fastapi = ModuleType("fastapi")
        router = SimpleNamespace(get=lambda *a, **kw: lambda f: f,
                                 put=lambda *a, **kw: lambda f: f)
        fastapi.APIRouter = lambda: router
        fastapi.Query = lambda default=None, **kw: default
        fastapi.HTTPException = RuntimeError
        name = "nunchi.integrations.hermes_dashboard_api"
        with patch.dict(sys.modules, {"fastapi": fastapi}):
            sys.modules.pop(name, None)
            api = importlib.import_module(name)
        try:
            with tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary)
                _, _, _, env = _write_config(home)
                env["HERMES_HOME"] = str(home)
                result = api._config_response("default", environ=env)
                self.assertIsInstance(result.get("attention_trust"), dict)
                self.assertFalse(result["attention_trust"]["ready"])
                self.assertIn("allow_provider_override", result["attention_trust"]["detail"])
                self.assertFalse((home / "config.yaml").exists())
        finally:
            sys.modules.pop(name, None)

    def test_host_permission_failure_is_actionable_without_leaking_exception_text(self):
        request = make_request()
        profile = ParticipantProfile(
            profile_id="trust-test", participant_id=request["self"]["participant_id"],
            actor_id=request["self"]["actor_id"], instructions="Be useful.",
            provenance="test", sha256="a" * 64,
        )
        calls = []

        def denied(**kwargs):
            calls.append(kwargs)
            raise PermissionError("SECRET_SENTINEL raw provider detail")

        model = HostStructuredAttentionModel(SimpleNamespace(complete_structured=denied),
                                             AttentionModelSelection(provider="exact-provider", model="exact-model"))
        engine = AttentionEngine(profile=profile, model=model)
        engine.receipts.append(make_receipt("observation"), writer="observation-provider")
        result = engine.judge(request)
        self.assertEqual("error", result["status"])
        self.assertEqual("host-permission-denied", result["error"]["code"])
        self.assertIn("allow_provider_override", result["error"]["detail"])
        self.assertIn("allow_model_override", result["error"]["detail"])
        self.assertNotIn("SECRET_SENTINEL", json.dumps(result))
        self.assertNotIn("classifier_disposition", result)
        self.assertEqual("exact-provider", calls[0]["provider"])
        self.assertEqual("exact-model", calls[0]["model"])
        self.assertEqual(result["error"], engine.receipts.records(request["request_id"])[1]["body"]["error"])

    def test_explicit_save_grants_only_selected_routes_and_preserves_host_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            original = {
                "model": {"provider": "participant-provider", "default": "participant-model"},
                "plugins": {"enabled": ["nunchi", "other"], "entries": {
                    "other": {"enabled": True},
                    "nunchi": {"llm": {"allow_profile_override": False}, "custom": 17},
                }},
            }
            raw = (json.dumps(original) + "\n").encode()
            (home / "config.yaml").write_bytes(raw)
            env = {"HERMES_HOME": str(home)}
            before = read_dashboard_snapshot("default", environ=env)
            saved = write_config_document("default", document=_document(home),
                                          expected_revision=before.revision, environ=env)
            self.assertIsNotNone(saved.config)
            result = json.loads((home / "config.yaml").read_text())
            llm = result["plugins"]["entries"]["nunchi"]["llm"]
            self.assertIs(llm.get("allow_provider_override"), True)
            self.assertIs(llm.get("allow_model_override"), True)
            self.assertEqual(["test-provider"], llm["allowed_providers"])
            self.assertEqual(["test-model"], llm["allowed_models"])
            self.assertIs(llm["allow_profile_override"], False)
            self.assertEqual(original["model"], result["model"])
            self.assertEqual(original["plugins"]["enabled"], result["plugins"]["enabled"])
            self.assertEqual(original["plugins"]["entries"]["other"], result["plugins"]["entries"]["other"])
            backups = list(home.glob("config.yaml.nunchi-backup-*"))
            self.assertEqual(1, len(backups))
            self.assertEqual(raw, backups[0].read_bytes())
            self.assertEqual(0o600, backups[0].stat().st_mode & 0o777)


if __name__ == "__main__":
    unittest.main()
