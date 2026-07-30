from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from nunchi.integrations import hermes_dashboard_store, hermes_v2
from nunchi.integrations.hermes_dashboard_install import (
    DashboardInstallError,
    default_hermes_home,
    install_dashboard,
    verify_dashboard,
)
from nunchi.integrations.hermes_dashboard_store import (
    DashboardConfigConflict,
    DashboardConfigError,
    DashboardConfigReadOnly,
    active_hermes_profile,
    channel_directory,
    default_config_paths,
    discord_runtime_status,
    read_config_snapshot,
    read_dashboard_snapshot,
    read_receipts,
    write_config_document,
)


def _save_dashboard_config_in_process(
    home: str,
    expected_revision: str,
    start: object,
    results: object,
) -> None:
    """Attempt one first save from an independent dashboard process."""

    try:
        start.wait(timeout=10)
        write_config_document(
            "default",
            document=_document(Path(home)),
            expected_revision=expected_revision,
            environ={"HERMES_HOME": home},
        )
    except Exception as exc:
        results.put(("error", type(exc).__name__, str(exc)))
    else:
        results.put(("ok", "", ""))


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
                    "model": {
                        "provider": "test-provider",
                        "model": "test-model",
                    },
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
    def test_first_run_bootstrap_creates_private_profile_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            home.mkdir(mode=0o700)
            environ = {"HERMES_HOME": str(home)}

            before = read_dashboard_snapshot("default", environ=environ)

            self.assertTrue(before.bootstrap_required)
            self.assertIsNone(before.sha256)
            self.assertRegex(before.revision, r"^absent:[0-9a-f]{64}$")
            self.assertEqual([], before.document["rooms"])
            paths = default_config_paths("default", environ=environ)
            self.assertEqual(paths.config, before.source.path)
            self.assertEqual(paths.digest, before.source.digest_path)
            self.assertEqual(
                str(paths.state_directory),
                before.document["state_directory"],
            )

            document = _document(paths.config.parent)
            after = write_config_document(
                "default",
                document=document,
                expected_revision=before.revision,
                environ=environ,
            )

            self.assertFalse(after.bootstrap_required)
            self.assertRegex(after.sha256 or "", r"^[0-9a-f]{64}$")
            self.assertEqual(after.sha256, paths.digest.read_text().strip())
            self.assertEqual(0, paths.config.stat().st_mode & 0o077)
            self.assertEqual(0, paths.digest.stat().st_mode & 0o077)
            self.assertEqual(0, paths.config.parent.stat().st_mode & 0o077)
            self.assertEqual(document, after.document)
            self.assertTrue(after.response()["configuration_loadable"])
            self.assertNotIn("configuration_active", after.response())
            with patch.dict(os.environ, environ, clear=True):
                source = hermes_v2.resolve_config_source("default")
                restarted = hermes_v2._default_config_loader("default")
            self.assertEqual(paths.config, source.path)
            self.assertEqual(paths.digest, source.digest_path)
            self.assertEqual(after.sha256, source.expected_sha256)
            self.assertEqual("default", restarted.hermes_profile)
            with self.assertRaises(DashboardConfigConflict):
                write_config_document(
                    "default",
                    document=document,
                    expected_revision=before.revision,
                    environ=environ,
                )

    def test_invalid_first_save_creates_no_config_or_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            home.mkdir(mode=0o700)
            environ = {"HERMES_HOME": str(home)}
            before = read_dashboard_snapshot("default", environ=environ)
            paths = default_config_paths("default", environ=environ)

            with self.assertRaisesRegex(Exception, "at least one room"):
                write_config_document(
                    "default",
                    document=before.document,
                    expected_revision=before.revision,
                    environ=environ,
                )

            self.assertFalse(paths.config.exists())
            self.assertFalse(paths.digest.exists())

    def test_first_save_stop_before_config_publication_leaves_bootstrap(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            home.mkdir(mode=0o700)
            environ = {"HERMES_HOME": str(home)}
            before = read_dashboard_snapshot("default", environ=environ)
            paths = default_config_paths("default", environ=environ)
            real_publish = (
                hermes_dashboard_store._publish_complete_file_exclusive
            )

            def stop_before_config(source, destination, *, label):
                if Path(destination) == paths.config:
                    raise KeyboardInterrupt("simulated process stop")
                return real_publish(source, destination, label=label)

            with patch.object(
                hermes_dashboard_store,
                "_publish_complete_file_exclusive",
                side_effect=stop_before_config,
            ):
                with self.assertRaisesRegex(
                    KeyboardInterrupt,
                    "simulated process stop",
                ):
                    write_config_document(
                        "default",
                        document=_document(paths.config.parent),
                        expected_revision=before.revision,
                        environ=environ,
                    )

            self.assertFalse(paths.config.exists())
            self.assertFalse(paths.digest.exists())
            recovered = read_dashboard_snapshot("default", environ=environ)
            self.assertTrue(recovered.bootstrap_required)
            self.assertFalse(recovered.bootstrap_recovery)

    def test_first_save_stop_before_digest_publication_is_repairable(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            home.mkdir(mode=0o700)
            environ = {"HERMES_HOME": str(home)}
            before = read_dashboard_snapshot("default", environ=environ)
            paths = default_config_paths("default", environ=environ)
            document = _document(paths.config.parent)
            real_publish = (
                hermes_dashboard_store._publish_complete_file_exclusive
            )

            def stop_before_digest(source, destination, *, label):
                if Path(destination) == paths.digest:
                    raise KeyboardInterrupt("simulated process stop")
                return real_publish(source, destination, label=label)

            with patch.object(
                hermes_dashboard_store,
                "_publish_complete_file_exclusive",
                side_effect=stop_before_digest,
            ):
                with self.assertRaisesRegex(
                    KeyboardInterrupt,
                    "simulated process stop",
                ):
                    write_config_document(
                        "default",
                        document=document,
                        expected_revision=before.revision,
                        environ=environ,
                    )

            self.assertTrue(paths.config.is_file())
            self.assertFalse(paths.digest.exists())
            recovered = read_dashboard_snapshot("default", environ=environ)
            self.assertTrue(recovered.bootstrap_required)
            self.assertTrue(recovered.bootstrap_recovery)
            self.assertEqual(document, recovered.document)

            repaired = write_config_document(
                "default",
                document=document,
                expected_revision=recovered.revision,
                environ=environ,
            )
            self.assertFalse(repaired.bootstrap_required)
            self.assertEqual(repaired.sha256, paths.digest.read_text().strip())

    def test_concurrent_first_saves_allow_one_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            home.mkdir(mode=0o700)
            environ = {"HERMES_HOME": str(home)}
            before = read_dashboard_snapshot("default", environ=environ)
            document = _document(home)

            def save():
                try:
                    return write_config_document(
                        "default",
                        document=document,
                        expected_revision=before.revision,
                        environ=environ,
                    )
                except Exception as exc:
                    return exc

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: save(), range(2)))

            self.assertEqual(
                1,
                sum(not isinstance(result, Exception) for result in results),
            )
            failures = [
                result for result in results if isinstance(result, Exception)
            ]
            self.assertEqual(1, len(failures))
            self.assertIsInstance(failures[0], DashboardConfigConflict)

    @unittest.skipUnless(
        "spawn" in multiprocessing.get_all_start_methods(),
        "requires multiprocessing spawn",
    )
    def test_cross_process_first_saves_allow_one_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            home.mkdir(mode=0o700)
            before = read_dashboard_snapshot(
                "default",
                environ={"HERMES_HOME": str(home)},
            )
            context = multiprocessing.get_context("spawn")
            start = context.Event()
            results = context.Queue()
            processes = [
                context.Process(
                    target=_save_dashboard_config_in_process,
                    args=(str(home), before.revision, start, results),
                )
                for _ in range(2)
            ]
            for process in processes:
                process.start()
            start.set()
            for process in processes:
                process.join(timeout=15)
                self.assertFalse(process.is_alive())
                self.assertEqual(0, process.exitcode)
            outcomes = [results.get(timeout=5) for _ in processes]
            results.close()
            results.join_thread()

            self.assertEqual(1, sum(result[0] == "ok" for result in outcomes))
            failures = [result for result in outcomes if result[0] == "error"]
            self.assertEqual(1, len(failures))
            self.assertEqual("DashboardConfigConflict", failures[0][1])

    def test_partial_default_config_is_recoverable(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            home.mkdir(mode=0o700)
            environ = {"HERMES_HOME": str(home)}
            paths = default_config_paths("default", environ=environ)
            paths.config.parent.mkdir(mode=0o700, parents=True)
            paths.config.parent.parent.parent.chmod(0o700)
            paths.config.parent.parent.chmod(0o700)
            paths.config.parent.chmod(0o700)
            document = _document(paths.config.parent)
            paths.config.write_text(
                json.dumps(document, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            paths.config.chmod(0o600)

            interrupted = read_dashboard_snapshot("default", environ=environ)

            self.assertTrue(interrupted.bootstrap_required)
            self.assertTrue(interrupted.bootstrap_recovery)
            self.assertRegex(
                interrupted.revision,
                r"^uncommitted:[0-9a-f]{64}$",
            )
            status = discord_runtime_status(interrupted, environ=environ)
            self.assertFalse(status["configuration_loadable"])
            self.assertEqual([], status["configured_room_ids"])
            repaired = write_config_document(
                "default",
                document=document,
                expected_revision=interrupted.revision,
                environ=environ,
            )
            self.assertFalse(repaired.bootstrap_required)
            self.assertTrue(paths.digest.exists())
            self.assertEqual(repaired.sha256, paths.digest.read_text().strip())

    def test_orphan_default_digest_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            home.mkdir(mode=0o700)
            environ = {"HERMES_HOME": str(home)}
            paths = default_config_paths("default", environ=environ)
            paths.config.parent.mkdir(mode=0o700, parents=True)
            paths.digest.write_text("0" * 64 + "\n", encoding="ascii")
            paths.digest.chmod(0o600)

            with self.assertRaisesRegex(
                DashboardConfigError,
                "orphan digest",
            ):
                read_dashboard_snapshot("default", environ=environ)

    def test_runtime_and_dashboard_share_hermes_home_resolver(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes-home"
            home.mkdir(mode=0o700)
            with (
                patch.dict(os.environ, {}, clear=True),
                patch(
                    "nunchi.integrations.hermes_dashboard_store."
                    "default_hermes_home",
                    return_value=home,
                ),
            ):
                before = read_dashboard_snapshot("fiction-writer")
                paths = default_config_paths("fiction-writer")
                document = _document(paths.config.parent)
                document["hermes_profile"] = "fiction-writer"
                after = write_config_document(
                    "fiction-writer",
                    document=document,
                    expected_revision=before.revision,
                )
                source = hermes_v2.resolve_config_source("fiction-writer")

            self.assertEqual(paths.config, source.path)
            self.assertEqual(paths.digest, source.digest_path)
            self.assertEqual(after.sha256, source.expected_sha256)

    def test_active_profile_resolution_fails_closed(self):
        package = types.ModuleType("hermes_cli")
        package.__path__ = []
        profiles = types.ModuleType("hermes_cli.profiles")
        profiles.get_active_profile_name = lambda: ""
        package.profiles = profiles
        with patch.dict(
            sys.modules,
            {
                "hermes_cli": package,
                "hermes_cli.profiles": profiles,
            },
        ):
            with self.assertRaisesRegex(
                DashboardConfigError,
                "could not be resolved",
            ):
                active_hermes_profile()

    def test_placeholder_actor_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            home.mkdir(mode=0o700)
            environ = {"HERMES_HOME": str(home)}
            before = read_dashboard_snapshot("default", environ=environ)
            document = _document(home)
            document["rooms"][0]["binding"]["actor_id"] = (
                "discord:actor:replace-me"
            )
            document["rooms"][0]["profile"]["document"]["actor_id"] = (
                "discord:actor:replace-me"
            )

            with self.assertRaisesRegex(Exception, "exact authenticated Hermes bot"):
                write_config_document(
                    "default",
                    document=document,
                    expected_revision=before.revision,
                    environ=environ,
                )
            paths = default_config_paths("default", environ=environ)
            self.assertFalse(paths.config.exists())
            self.assertFalse(paths.digest.exists())

    def test_interrupted_update_serves_prior_revision_and_is_repairable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path, digest_path, document, environ = _write_config(root)
            before = read_config_snapshot("default", environ=environ)
            changed = json.loads(json.dumps(document))
            changed["rooms"][0]["profile"]["document"]["instructions"] = (
                "Changed after the active revision."
            )
            real_replace = os.replace

            def interrupt_digest_replace(source, destination):
                if Path(destination) == digest_path:
                    raise OSError("simulated interruption")
                return real_replace(source, destination)

            with patch(
                "nunchi.integrations.hermes_dashboard_store.os.replace",
                side_effect=interrupt_digest_replace,
            ):
                with self.assertRaisesRegex(OSError, "simulated interruption"):
                    write_config_document(
                        "default",
                        document=changed,
                        expected_revision=before.revision,
                        environ=environ,
                    )

            recovered = read_dashboard_snapshot("default", environ=environ)
            runtime_source = hermes_v2.resolve_config_source(
                "default",
                environ=environ,
            )
            self.assertTrue(recovered.update_recovery)
            self.assertEqual(document, recovered.document)
            self.assertNotEqual(config_path, recovered.source.path)
            self.assertEqual(config_path, recovered.source.write_path)
            self.assertEqual(recovered.source.path, runtime_source.path)
            self.assertEqual(before.sha256, runtime_source.expected_sha256)
            self.assertEqual(before.sha256, digest_path.read_text().strip())

            repaired = write_config_document(
                "default",
                document=changed,
                expected_revision=recovered.revision,
                environ=environ,
            )

            self.assertFalse(repaired.update_recovery)
            self.assertEqual(changed, repaired.document)
            self.assertEqual(repaired.sha256, digest_path.read_text().strip())
            self.assertFalse(recovered.source.path.exists())

    def test_interleaved_reader_sees_prior_revision_during_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path, digest_path, document, environ = _write_config(root)
            before = read_config_snapshot("default", environ=environ)
            changed = json.loads(json.dumps(document))
            changed["rooms"][0]["profile"]["document"]["instructions"] = (
                "A new committed revision."
            )
            observed = []
            real_replace = os.replace

            def observe_after_replace(source, destination):
                result = real_replace(source, destination)
                if Path(destination) == config_path:
                    observed.append(
                        read_dashboard_snapshot("default", environ=environ)
                    )
                return result

            with patch(
                "nunchi.integrations.hermes_dashboard_store.os.replace",
                side_effect=observe_after_replace,
            ):
                updated = write_config_document(
                    "default",
                    document=changed,
                    expected_revision=before.revision,
                    environ=environ,
                )

            self.assertEqual(1, len(observed))
            self.assertTrue(observed[0].update_recovery)
            self.assertEqual(document, observed[0].document)
            self.assertEqual(changed, updated.document)
            self.assertEqual(updated.sha256, digest_path.read_text().strip())

    def test_reader_retries_if_selected_revision_is_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, digest_path, document, environ = _write_config(root)
            before = read_config_snapshot("default", environ=environ)
            changed = json.loads(json.dumps(document))
            changed["rooms"][0]["profile"]["document"]["instructions"] = (
                "The newly committed revision."
            )
            selected = threading.Event()
            resume = threading.Event()
            result: dict[str, object] = {}
            calls = 0
            real_read = hermes_dashboard_store._read_source_snapshot

            def pause_first_read(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    selected.set()
                    if not resume.wait(timeout=5):
                        raise RuntimeError("reader retry test timed out")
                return real_read(*args, **kwargs)

            def read_during_update():
                try:
                    result["snapshot"] = read_config_snapshot(
                        "default",
                        environ=environ,
                        allow_invalid=True,
                    )
                except BaseException as exc:
                    result["error"] = exc

            with patch.object(
                hermes_dashboard_store,
                "_read_source_snapshot",
                side_effect=pause_first_read,
            ):
                reader = threading.Thread(target=read_during_update)
                reader.start()
                self.assertTrue(selected.wait(timeout=5))
                updated = write_config_document(
                    "default",
                    document=changed,
                    expected_revision=before.revision,
                    environ=environ,
                )
                resume.set()
                reader.join(timeout=5)

            self.assertFalse(reader.is_alive())
            self.assertNotIn("error", result)
            observed = result["snapshot"]
            self.assertEqual(updated.sha256, observed.sha256)
            self.assertEqual(changed, observed.document)
            self.assertEqual(updated.sha256, digest_path.read_text().strip())

    def test_runtime_loader_retries_one_concurrent_revision_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path, _, _, environ = _write_config(root)
            source = hermes_v2.resolve_config_source(
                "default",
                environ=environ,
            )
            expected = hermes_v2.load_pinned_config(
                config_path,
                expected_sha256=source.expected_sha256,
                hermes_profile="default",
            )
            with (
                patch.object(
                    hermes_v2,
                    "resolve_config_source",
                    side_effect=(source, source),
                ) as resolve,
                patch.object(
                    hermes_v2,
                    "load_pinned_config",
                    side_effect=(
                        hermes_v2.ValidationError(
                            "revision changed while opening config"
                        ),
                        expected,
                    ),
                ),
            ):
                loaded = hermes_v2._default_config_loader("default")

            self.assertEqual(expected, loaded)
            self.assertEqual(2, resolve.call_count)

    def test_stale_pre_replace_backup_does_not_block_next_save(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path, _, document, environ = _write_config(root)
            before = read_config_snapshot("default", environ=environ)
            changed = json.loads(json.dumps(document))
            changed["rooms"][0]["profile"]["document"]["instructions"] = (
                "Committed after retry."
            )
            backup = hermes_v2._config_backup_path(
                config_path,
                before.sha256,
            )
            real_replace = os.replace

            def crash_before_config_replace(source, destination):
                if Path(destination) == config_path:
                    raise KeyboardInterrupt("simulated process stop")
                return real_replace(source, destination)

            with patch(
                "nunchi.integrations.hermes_dashboard_store.os.replace",
                side_effect=crash_before_config_replace,
            ):
                with self.assertRaisesRegex(
                    KeyboardInterrupt,
                    "simulated process stop",
                ):
                    write_config_document(
                        "default",
                        document=changed,
                        expected_revision=before.revision,
                        environ=environ,
                    )

            self.assertTrue(backup.is_file())
            self.assertEqual(config_path.read_bytes(), backup.read_bytes())

            updated = write_config_document(
                "default",
                document=changed,
                expected_revision=before.revision,
                environ=environ,
            )

            self.assertEqual(changed, updated.document)
            self.assertFalse(backup.exists())

    def test_backup_stop_before_atomic_link_does_not_block_next_save(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path, _, document, environ = _write_config(root)
            before = read_config_snapshot("default", environ=environ)
            changed = json.loads(json.dumps(document))
            changed["rooms"][0]["profile"]["document"]["instructions"] = (
                "Committed after an interrupted backup publication."
            )
            backup = hermes_v2._config_backup_path(
                config_path,
                before.sha256,
            )
            real_link = os.link

            def stop_before_backup_link(source, destination, **kwargs):
                if Path(destination) == backup:
                    raise KeyboardInterrupt("simulated process stop")
                return real_link(source, destination, **kwargs)

            with patch(
                "nunchi.integrations.hermes_dashboard_store.os.link",
                side_effect=stop_before_backup_link,
            ):
                with self.assertRaisesRegex(
                    KeyboardInterrupt,
                    "simulated process stop",
                ):
                    write_config_document(
                        "default",
                        document=changed,
                        expected_revision=before.revision,
                        environ=environ,
                    )

            self.assertFalse(backup.exists())
            unchanged = read_config_snapshot("default", environ=environ)
            self.assertEqual(before.sha256, unchanged.sha256)

            updated = write_config_document(
                "default",
                document=changed,
                expected_revision=before.revision,
                environ=environ,
            )
            self.assertEqual(changed, updated.document)

    def test_explicit_dashboard_write_requires_private_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, document, environ = _write_config(root)
            root.chmod(0o755)
            before = read_config_snapshot("default", environ=environ)

            with self.assertRaisesRegex(
                DashboardConfigError,
                "config directory must not be accessible",
            ):
                write_config_document(
                    "default",
                    document=document,
                    expected_revision=before.revision,
                    environ=environ,
                )

    def test_receipts_are_empty_before_first_setup(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            home.mkdir(mode=0o700)
            result = read_receipts(
                "default",
                environ={"HERMES_HOME": str(home)},
            )

            self.assertEqual([], result["receipts"])
            self.assertTrue(result["bootstrap_required"])

    def test_default_paths_are_exact_profile_scoped_and_traversal_safe(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            default = default_config_paths("default", hermes_home=home)
            fiction = default_config_paths("fiction-writer", hermes_home=home)
            hostile = default_config_paths("../../fiction-writer", hermes_home=home)

            self.assertNotEqual(default.config, fiction.config)
            self.assertNotEqual(fiction.config, hostile.config)
            for paths in (default, fiction, hostile):
                self.assertEqual(home.resolve(), paths.config.parents[3])
                self.assertEqual("nunchi", paths.config.parents[2].name)
                self.assertEqual("profiles", paths.config.parents[1].name)
                self.assertRegex(
                    paths.config.parent.name,
                    r"^[a-z0-9-]+-[0-9a-f]{12}$",
                )
                self.assertEqual(
                    paths.config.parent / "state",
                    paths.state_directory,
                )

    def test_explicit_env_config_precedes_default_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path, _, _, configured = _write_config(root)
            home = root / "hermes"
            home.mkdir(mode=0o700)
            environ = {**configured, "HERMES_HOME": str(home)}

            snapshot = read_dashboard_snapshot("default", environ=environ)

            self.assertEqual(config_path, snapshot.source.path)
            self.assertFalse(snapshot.bootstrap_required)
            self.assertFalse(
                default_config_paths("default", environ=environ).config.exists()
            )

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

    def test_dashboard_can_upgrade_a_pinned_legacy_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, document, environ = _write_config(root)
            legacy = json.loads(json.dumps(document))
            del legacy["rooms"][0]["attention"]["model"]
            config_path = Path(environ["NUNCHI_HERMES_V2_CONFIG"])
            digest_path = Path(environ["NUNCHI_HERMES_V2_CONFIG_SHA256_FILE"])
            config_path.write_text(
                json.dumps(legacy, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            digest_path.write_text(
                hashlib.sha256(config_path.read_bytes()).hexdigest() + "\n",
                encoding="ascii",
            )

            with self.assertRaisesRegex(Exception, "missing or unexpected"):
                read_config_snapshot("default", environ=environ)
            before = read_config_snapshot(
                "default",
                environ=environ,
                allow_invalid=True,
            )
            self.assertIsNone(before.config)
            self.assertIn("missing or unexpected", before.validation_error)
            status = discord_runtime_status(before, environ=environ)
            self.assertFalse(status["configuration_loadable"])
            self.assertEqual([], status["configured_room_ids"])

            upgraded = json.loads(json.dumps(before.document))
            upgraded["rooms"][0]["attention"]["model"] = {
                "provider": "nous",
                "model": "deepseek/deepseek-v4-flash",
            }
            after = write_config_document(
                "default",
                document=upgraded,
                expected_sha256=before.sha256,
                environ=environ,
            )

            self.assertIsNotNone(after.config)
            self.assertIsNone(after.validation_error)
            self.assertEqual(
                "deepseek/deepseek-v4-flash",
                after.document["rooms"][0]["attention"]["model"]["model"],
            )

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

    def test_discord_runtime_status_is_room_scoped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, _, environ = _write_config(root)
            snapshot = read_config_snapshot("default", environ=environ)
            status = discord_runtime_status(
                snapshot,
                environ={**environ, "DISCORD_ALLOW_BOTS": "all"},
            )
            self.assertEqual(["42"], status["configured_room_ids"])
            self.assertTrue(status["configuration_loadable"])
            self.assertEqual(
                "configured-rooms",
                status["bot_admission_after_restart"],
            )
            self.assertEqual(
                "configured-rooms",
                status["missed_message_recovery_after_restart"],
            )
            self.assertTrue(status["natural_conversation_after_restart"])
            self.assertFalse(status["mention_required_after_restart"])
            self.assertEqual(
                "bypassed",
                status["auto_threading_after_restart"],
            )
            self.assertTrue(status["profile_wide_fallback_active"])


class HermesDashboardInstallTests(unittest.TestCase):
    def test_hermes_home_resolver_failure_does_not_silently_fallback(self):
        package = types.ModuleType("hermes_cli")
        package.__path__ = []
        config = types.ModuleType("hermes_cli.config")

        def fail():
            raise RuntimeError("profile store unavailable")

        config.get_hermes_home = fail
        package.config = config
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.dict(
                sys.modules,
                {
                    "hermes_cli": package,
                    "hermes_cli.config": config,
                },
            ),
        ):
            with self.assertRaisesRegex(
                DashboardInstallError,
                "Hermes home could not be resolved",
            ):
                default_hermes_home()

    def test_dashboard_api_maps_profile_errors_and_rejects_non_string_profile(self):
        fastapi = types.ModuleType("fastapi")

        class HTTPException(Exception):
            def __init__(self, *, status_code, detail):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        class APIRouter:
            def get(self, *args, **kwargs):
                del args, kwargs
                return lambda function: function

            put = get

        fastapi.APIRouter = APIRouter
        fastapi.HTTPException = HTTPException
        fastapi.Query = lambda default=None, **kwargs: default
        module_name = "nunchi.integrations.hermes_dashboard_api"
        sys.modules.pop(module_name, None)
        try:
            with patch.dict(sys.modules, {"fastapi": fastapi}):
                api = importlib.import_module(module_name)
            with patch.object(
                api,
                "active_hermes_profile",
                side_effect=DashboardConfigError(
                    "Hermes active profile could not be resolved"
                ),
            ):
                with self.assertRaises(HTTPException) as failure:
                    api.get_health(None)
                self.assertEqual(422, failure.exception.status_code)
            with self.assertRaises(HTTPException) as failure:
                api.put_config(
                    {
                        "profile": 7,
                        "expected_revision": "revision",
                        "document": {},
                    }
                )
            self.assertEqual(422, failure.exception.status_code)
            for invalid_profile in ("", "x" * 129):
                with self.assertRaises(HTTPException) as failure:
                    api.get_health(invalid_profile)
                self.assertEqual(422, failure.exception.status_code)
        finally:
            sys.modules.pop(module_name, None)

    def test_install_and_verify_packaged_dashboard(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            installed = install_dashboard(hermes_home=home)
            dashboard = (
                home / "plugins" / "nunchi-dashboard" / "dashboard"
            )
            self.assertTrue(installed["ok"])
            self.assertEqual(installed, verify_dashboard(hermes_home=home))
            manifest = json.loads(
                (dashboard / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual("nunchi", manifest["name"])
            self.assertEqual("plugin_api.py", manifest["api"])
            self.assertFalse(
                (home / "plugins" / "nunchi-dashboard" / "plugin.yaml").exists()
            )
            self.assertIn(
                "nunchi.integrations.hermes_dashboard_api",
                (dashboard / "plugin_api.py").read_text(encoding="utf-8"),
            )
            self.assertNotIn(
                "actor:replace-me",
                (dashboard / "index.js").read_text(encoding="utf-8"),
            )
            source = (dashboard / "index.js").read_text(encoding="utf-8")
            for field_name in (
                "actor_id",
                "room_id",
                "continuity_scope_id",
                "room_name",
            ):
                self.assertIn(
                    f'base.concat(["binding", "{field_name}"]), ""',
                    source,
                )
            self.assertNotIn("value + actor.slice", source)

    def test_verify_rejects_modified_asset(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            install_dashboard(hermes_home=home)
            path = (
                home
                / "plugins"
                / "nunchi-dashboard"
                / "dashboard"
                / "index.js"
            )
            path.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(DashboardInstallError, "changed"):
                verify_dashboard(hermes_home=home)

    def test_install_migrates_the_previous_bridge_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            install_dashboard(hermes_home=home)
            plugins = home / "plugins"
            current = plugins / "nunchi-dashboard"
            legacy = plugins / "nunchi-v2-dashboard"
            (current / ".nunchi-dashboard.json").replace(
                current / ".nunchi-v2-dashboard.json"
            )
            current.replace(legacy)

            result = install_dashboard(hermes_home=home)

            self.assertTrue(result["ok"])
            self.assertFalse(legacy.exists())
            self.assertTrue(
                (
                    plugins
                    / "nunchi-dashboard"
                    / "dashboard"
                    / "manifest.json"
                ).is_file()
            )

    def test_reinstall_removes_only_generated_plugin_api_bytecode(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            install_dashboard(hermes_home=home)
            cache = (
                home
                / "plugins"
                / "nunchi-dashboard"
                / "dashboard"
                / "__pycache__"
            )
            cache.mkdir()
            (cache / "plugin_api.cpython-311.pyc").write_bytes(b"generated")

            result = install_dashboard(hermes_home=home)

            self.assertTrue(result["ok"])
            self.assertFalse(cache.exists())

    def test_reinstall_rejects_unmanaged_bytecode(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            install_dashboard(hermes_home=home)
            cache = (
                home
                / "plugins"
                / "nunchi-dashboard"
                / "dashboard"
                / "__pycache__"
            )
            cache.mkdir()
            unexpected = cache / "other.cpython-311.pyc"
            unexpected.write_bytes(b"unmanaged")

            with self.assertRaisesRegex(
                DashboardInstallError,
                "unmanaged Nunchi dashboard directory",
            ):
                install_dashboard(hermes_home=home)
            self.assertTrue(unexpected.is_file())

    def test_ui_uses_authenticated_plugin_api_and_restart(self):
        path = (
            Path("src")
            / "nunchi"
            / "integrations"
            / "hermes_dashboard_assets"
            / "index.js"
        )
        source = path.read_text(encoding="utf-8")
        self.assertIn('var API = "/api/plugins/nunchi"', source)
        self.assertIn("restart_endpoint", source)
        self.assertIn("Save & restart", source)
        self.assertIn("After Hermes restarts", source)
        self.assertNotIn('"Nunchi listens without mentions', source)
        self.assertIn("admit bot messages", source)
        self.assertIn("profile-wide bot fallback", source)
        self.assertIn("Attention provider", source)
        self.assertIn("Attention model", source)
        self.assertIn('DEFAULT_ATTENTION_PROVIDER = "nous"', source)
        self.assertIn(
            'DEFAULT_ATTENTION_MODEL = "deepseek/deepseek-v4-flash"',
            source,
        )
        self.assertIn(
            "This is separate from the participant's main model",
            source,
        )
        self.assertIn("First-time setup", source)
        self.assertIn("expected_revision: snapshot.revision", source)
        self.assertIn(
            "Total deadline for observation, attention, the admitted Hermes turn, and final settlement.",
            source,
        )
        self.assertNotIn(
            "Maximum time for Nunchi's attention decision",
            source,
        )
        self.assertIn("The plugin cannot grant itself that permission", source)
        self.assertIn("React.createElement", source)
        self.assertNotIn("innerHTML", source)

    def test_project_declares_dashboard_command_and_package_data(self):
        source = Path("pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("nunchi-hermes-dashboard", source)
        self.assertIn("hermes_dashboard_assets", source)
        self.assertIn('nunchi = "nunchi.integrations.hermes_v2"', source)


if __name__ == "__main__":
    unittest.main()
