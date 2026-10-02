"""Profile lifecycle tests use disposable homes; never the operator's resolver."""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


class LifecycleTests(unittest.TestCase):
    def test_named_lifecycle_install_does_not_touch_machine_dashboard(self):
        import sys
        from unittest.mock import patch
        from nunchi.integrations import hermes_lifecycle as lifecycle
        from nunchi.integrations.hermes_dashboard_install import install_dashboard_for_profile
        from nunchi.integrations.hermes_dashboard_store import default_config_paths
        from tests.v2.test_hermes_dashboard import _document
        from tests.v2.test_hermes_dashboard_profile_install import HermesDashboardProfileInstallTests
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            home = root / 'profiles/worker'
            home.mkdir(parents=True)
            (home / 'config.yaml').write_text('plugins:\n  enabled: []\n')
            doc = _document(home)
            doc['hermes_profile'] = 'worker'
            doc['state_directory'] = str(default_config_paths('worker', hermes_home=home).state_directory)
            supplied = root / 'supplied.json'
            supplied.write_text(json.dumps(doc))
            supplied.chmod(0o600)
            plan = lifecycle.plan(home=home, mode='activate', profile='worker', config=supplied,
                                  config_sha256=hashlib.sha256(supplied.read_bytes()).hexdigest())
            lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)
            modules, calls = HermesDashboardProfileInstallTests()._modules(root=root, profile_home=home)
            with patch.dict(sys.modules, modules), patch.dict('os.environ', {'HERMES_HOME': str(home)}):
                result = install_dashboard_for_profile(profile='worker')
            self.assertEqual(calls, [])
            self.assertFalse((root / 'plugins').exists())
            self.assertEqual(result['scope'], 'lifecycle-selected-profile')

    def test_lock_contends_and_parent_swap_never_writes_outside(self):
        from unittest.mock import patch
        from nunchi.integrations import hermes_lifecycle as lifecycle
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve() / 'home'
            home.mkdir()
            original = b'plugins:\n  enabled: [nunchi]\n'
            (home / 'config.yaml').write_bytes(original)
            plan = lifecycle.plan(home=home, mode='retire', profile='default')
            with lifecycle._home(home) as root, lifecycle._locked(root):
                with self.assertRaisesRegex(lifecycle.LifecycleError, 'another lifecycle'):
                    lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)
            outside = Path(directory).resolve() / 'outside'
            outside.mkdir()
            (outside / 'config.yaml').write_bytes(b'untouched')
            moved = home.with_name('moved')
            def swap(stage):
                home.rename(moved)
                home.symlink_to(outside, target_is_directory=True)
            with patch.object(lifecycle, '_checkpoint', side_effect=swap):
                with self.assertRaisesRegex(lifecycle.LifecycleError, 'binding changed'):
                    lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)
            self.assertEqual((outside / 'config.yaml').read_bytes(), b'untouched')
            home.unlink()
            moved.rename(home)
            transaction = next(p.name for p in (home / lifecycle.STORE).iterdir() if p.is_dir())
            lifecycle.rollback(home=home, transaction=transaction, digest=lifecycle.digest(plan), stopped=True)
            self.assertEqual((home / 'config.yaml').read_bytes(), original)

    def test_owned_dashboard_with_changed_asset_is_not_archived(self):
        from nunchi.integrations import hermes_lifecycle as lifecycle
        from nunchi.integrations.hermes_dashboard_install import install_dashboard
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / 'config.yaml').write_text('plugins:\n  enabled: []\n')
            install_dashboard(hermes_home=home)
            asset = home / 'plugins/nunchi-dashboard/dashboard/index.js'
            asset.write_text('operator-edited-private-asset')
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.plan(home=home, mode='retire', profile='default')
            self.assertEqual(asset.read_text(), 'operator-edited-private-asset')

    def test_runtime_config_redirects_are_not_silently_ignored(self):
        from unittest.mock import patch
        from nunchi.integrations import hermes_lifecycle as lifecycle
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / 'config.yaml').write_text('plugins:\n  enabled: []\n')
            with patch.dict('os.environ', {'NUNCHI_HERMES_V2_CONFIG': '/elsewhere/private.json'}):
                with self.assertRaises(lifecycle.LifecycleError):
                    lifecycle.plan(home=home, mode='retire', profile='default')

    def test_flow_root_configuration_is_refused(self):
        from nunchi.integrations import hermes_lifecycle as lifecycle
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            original = b'{model: untouched}\n'
            (home / 'config.yaml').write_bytes(original)
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.plan(home=home, mode='retire', profile='default')
            self.assertEqual((home / 'config.yaml').read_bytes(), original)

    def test_cli_requires_explicit_interpreter_and_plan_digest(self):
        from nunchi.integrations import hermes_lifecycle as lifecycle
        self.assertTrue(callable(getattr(lifecycle, 'main', None)), 'operator entry point is missing')
        with self.assertRaises(SystemExit):
            lifecycle.main(['apply'])

    def test_retirement_is_dry_then_reversible_and_preserves_private_config(self):
        name = 'nunchi.integrations.hermes_lifecycle'
        self.assertIsNotNone(importlib.util.find_spec(name), 'wheel needs a profile lifecycle API')
        lifecycle = importlib.import_module(name)
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = b'# private\nmodel: untouched\nplugins:\n  enabled: [other, nunchi]\nattention_trust: secret-sentinel\n'
            (home / 'config.yaml').write_bytes(config)
            plan = lifecycle.plan(home=home, mode='retire', profile='default')
            self.assertEqual((home / 'config.yaml').read_bytes(), config)
            self.assertEqual(set(home.iterdir()), {home / 'config.yaml'})
            self.assertNotIn('secret-sentinel', json.dumps(plan))
            receipt = lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)
            self.assertEqual(receipt['status'], 'applied')
            after = (home / 'config.yaml').read_bytes()
            self.assertIn(b'attention_trust: secret-sentinel\n', after)
            self.assertIn(b'model: untouched\n', after)
            self.assertTrue(lifecycle.verify(home=home, transaction=receipt['transaction'])['ok'])
            result = lifecycle.rollback(home=home, transaction=receipt['transaction'], digest=lifecycle.digest(plan), stopped=True)
            self.assertEqual(result['status'], 'rolled_back')
            self.assertEqual((home / 'config.yaml').read_bytes(), config)

    def test_activate_and_retire_archive_owned_state_and_dashboard(self):
        from nunchi.integrations import hermes_lifecycle as lifecycle
        from nunchi.integrations.hermes_dashboard_store import default_config_paths
        from tests.v2.test_hermes_dashboard import _document
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / 'profile'
            home.mkdir()
            (home / 'config.yaml').write_text('plugins:\n  enabled: [other]\n')
            paths = default_config_paths('default', hermes_home=home)
            document = _document(home)
            document['state_directory'] = str(paths.state_directory)
            supplied = Path(directory) / 'supplied.json'
            supplied.write_text(json.dumps(document))
            supplied.chmod(0o600)
            approved = hashlib.sha256(supplied.read_bytes()).hexdigest()
            plan = lifecycle.plan(home=home, mode='activate', profile='default', config=supplied, config_sha256=approved)
            receipt = lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)
            self.assertEqual(paths.config.read_bytes(), supplied.read_bytes())
            self.assertTrue((home / 'plugins/nunchi-dashboard/dashboard/manifest.json').is_file())
            paths.state_directory.mkdir()
            state = paths.state_directory / 'history.jsonl'
            state.write_text('private-social-state')
            retired = lifecycle.plan(home=home, mode='retire', profile='default')
            retirement = lifecycle.apply(home=home, plan=retired, digest=lifecycle.digest(retired), stopped=True)
            self.assertFalse(paths.config.exists())
            self.assertFalse(state.exists())
            self.assertFalse((home / 'plugins/nunchi-dashboard').exists())
            self.assertNotIn('private-social-state', json.dumps(retirement))
            lifecycle.rollback(home=home, transaction=retirement['transaction'], digest=lifecycle.digest(retired), stopped=True)
            self.assertEqual(state.read_text(), 'private-social-state')
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.rollback(home=home, transaction=receipt['transaction'], digest=lifecycle.digest(plan), stopped=True)

    def test_unknown_predecessor_is_never_archived(self):
        from nunchi.integrations import hermes_lifecycle as lifecycle
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / 'config.yaml').write_text('plugins:\n  enabled: [nunchi-gate]\n')
            unknown = home / 'plugins/renamed'
            unknown.mkdir(parents=True)
            (unknown / 'plugin.yaml').write_text('name: nunchi-gate\n')
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.plan(home=home, mode='retire', profile='default')
            self.assertTrue(unknown.is_dir())

    def test_failure_restores_every_path_and_created_parents(self):
        from unittest.mock import patch
        from nunchi.integrations import hermes_lifecycle as lifecycle
        from nunchi.integrations.hermes_dashboard_store import default_config_paths
        from tests.v2.test_hermes_dashboard import _document
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve() / 'profile'
            home.mkdir()
            original = b'plugins:\n  enabled: [other]\n'
            (home / 'config.yaml').write_bytes(original)
            supplied = Path(directory).resolve() / 'config.json'
            doc = _document(home)
            doc['state_directory'] = str(default_config_paths('default', hermes_home=home).state_directory)
            supplied.write_text(json.dumps(doc))
            supplied.chmod(0o600)
            plan = lifecycle.plan(home=home, mode='activate', profile='default', config=supplied,
                                  config_sha256=hashlib.sha256(supplied.read_bytes()).hexdigest())
            for failure_at in range(1, 2 * len(plan['operations']) + 1):
                with self.subTest(failure_at=failure_at):
                    steps = iter(range(1, 2 * len(plan['operations']) + 1))
                    def fail(stage):
                        if next(steps) == failure_at:
                            raise RuntimeError('failure')
                    with patch.object(lifecycle, '_checkpoint', side_effect=fail):
                        with self.assertRaises(RuntimeError):
                            lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)
                    self.assertEqual((home / 'config.yaml').read_bytes(), original)
                    self.assertFalse((home / 'nunchi').exists())
                    self.assertFalse((home / 'plugins').exists())
                    self.assertFalse((home / '.nunchi-lifecycle-active.json').exists())

    def test_receipt_is_bound_to_the_selected_home_and_digest(self):
        import shutil
        from nunchi.integrations import hermes_lifecycle as lifecycle
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / 'a'
            home.mkdir()
            (home / 'config.yaml').write_text('plugins:\n  enabled: [nunchi]\n')
            plan = lifecycle.plan(home=home, mode='retire', profile='default')
            receipt = lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)
            other = Path(directory) / 'b'
            shutil.copytree(home, other)
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.verify(home=other, transaction=receipt['transaction'])

    def test_post_plan_new_predecessor_is_drift(self):
        from nunchi.integrations import hermes_lifecycle as lifecycle
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / 'config.yaml').write_text('plugins:\n  enabled: []\n')
            plan = lifecycle.plan(home=home, mode='retire', profile='default')
            path = home / 'plugins/foreign'
            path.mkdir(parents=True)
            (path / 'plugin.yaml').write_text('name: foreign\n')
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)

    def test_home_alias_works_but_descendant_link_and_edits_refuse(self):
        from nunchi.integrations import hermes_lifecycle as lifecycle
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / 'real'
            home.mkdir()
            alias = Path(directory) / 'alias'
            alias.symlink_to(home, target_is_directory=True)
            (home / 'config.yaml').write_text('plugins:\n  enabled: [nunchi]\n')
            plan = lifecycle.plan(home=alias, mode='retire', profile='default')
            receipt = lifecycle.apply(home=alias, plan=plan, digest=lifecycle.digest(plan), stopped=True)
            (home / 'config.yaml').write_text('later: edit\n')
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.rollback(home=alias, transaction=receipt['transaction'], digest=lifecycle.digest(plan), stopped=True)
            (home / 'plugins').symlink_to(Path(directory), target_is_directory=True)
            with self.assertRaises((lifecycle.LifecycleError, OSError)):
                lifecycle.plan(home=alias, mode='retire', profile='default')

    def test_hard_exit_journal_recovers_and_blocks_new_transaction(self):
        import multiprocessing
        from nunchi.integrations import hermes_lifecycle as lifecycle
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            original = b'plugins:\n  enabled: [nunchi]\n'
            (home / 'config.yaml').write_bytes(original)
            plan = lifecycle.plan(home=home, mode='retire', profile='default')
            ctx = multiprocessing.get_context('fork')
            process = ctx.Process(target=_crash_apply, args=(str(home), plan))
            process.start()
            process.join(10)
            self.assertEqual(process.exitcode, 71)
            transactions = [p for p in (home / lifecycle.STORE).iterdir() if p.is_dir()]
            self.assertEqual(len(transactions), 1)
            transaction = transactions[0].name
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.verify(home=home, transaction=transaction)
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)
            lifecycle.rollback(home=home, transaction=transaction, digest=lifecycle.digest(plan), stopped=True)
            self.assertEqual((home / 'config.yaml').read_bytes(), original)
            self.assertTrue(lifecycle.verify(home=home, transaction=transaction)['ok'])


def _crash_apply(home, plan):
    import os
    from nunchi.integrations import hermes_lifecycle as lifecycle
    lifecycle._checkpoint = lambda stage: os._exit(71)
    lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)


if __name__ == '__main__':
    unittest.main()
