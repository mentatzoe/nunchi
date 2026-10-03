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
    def test_real_dashboard_save_can_retire_and_restore_exact_bytes(self):
        from nunchi.integrations import hermes_lifecycle as lifecycle
        from nunchi.integrations.hermes_dashboard_store import (
            default_config_paths, read_dashboard_snapshot, write_config_document,
        )
        from nunchi.integrations.hermes_attention_trust import attention_trust_status
        from tests.v2.test_hermes_dashboard import _document
        for profile in ('default', 'worker'):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                machine = root / 'machine'
                home = machine / 'profiles' / profile
                home.mkdir(parents=True)
                machine_config = machine / 'config.yaml'
                machine_config.write_bytes(b'model: machine-private\n')
                host = home / 'config.yaml'
                host.write_bytes(b'model: unchanged\nplugins:\n  enabled: [other]\n')
                doc = _document(home)
                doc['hermes_profile'] = profile
                doc['state_directory'] = str(default_config_paths(profile, hermes_home=home).state_directory)
                supplied = root / 'supplied.json'
                supplied.write_text(json.dumps(doc))
                supplied.chmod(0o600)
                plan = lifecycle.plan(home=home, mode='activate', profile=profile, config=supplied,
                                      config_sha256=hashlib.sha256(supplied.read_bytes()).hexdigest())
                receipt = lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)
                self.assertTrue(lifecycle.verify(home=home, transaction=receipt['transaction'])['ok'])
                env = {'HERMES_HOME': str(home)}
                before = read_dashboard_snapshot(profile, environ=env)
                saved = write_config_document(profile, document=doc, expected_revision=before.revision, environ=env)
                self.assertTrue(attention_trust_status(home, saved.config)['ready'])
                raw = host.read_bytes()
                self.assertIsInstance(json.loads(raw), dict)
                retire = lifecycle.plan(home=home, mode='retire', profile=profile)
                retired = lifecycle.apply(home=home, plan=retire, digest=lifecycle.digest(retire), stopped=True)
                self.assertTrue(lifecycle.verify(home=home, transaction=retired['transaction'])['ok'])
                self.assertTrue(attention_trust_status(home, saved.config)['ready'])
                lifecycle.rollback(home=home, transaction=retired['transaction'], digest=lifecycle.digest(retire), stopped=True)
                self.assertEqual(host.read_bytes(), raw)
                self.assertTrue(lifecycle.verify(home=home, transaction=retired['transaction'])['ok'])
                self.assertEqual(machine_config.read_bytes(), b'model: machine-private\n')

    def test_existing_json_preserves_non_plugin_bytes_and_host_semantics(self):
        from nunchi.integrations import hermes_lifecycle as lifecycle
        from tests.v2.hermes_normal_turn_support import host_yaml
        yaml = host_yaml()
        cases = (
            ('{', '"plugins": {"enabled":["other", "nunchi"], "custom":true}', ',"private":"雪\\u0061","number":1e+20}\n'),
            ('{ "private" : [null, false, {"yes":"no"}], ', '"plu\\u0067ins" : {}', ' }\n'),
            ('{\n  "private": "plugins: { not syntax }",\n  ', '"plugins": {"disabled":["other"]}', '\n}\n'),
            ('{ "private": "untouched" ', '', '}\n'),
            ('{"plugins": {"entries" : { "nunchi": {"llm" : {"allow_model_override":true}}}, ', '"enabled": ["nunchi"]', '}}'),
            ('{', '', '}'),
        )
        for prefix, middle, suffix in cases:
            raw = (prefix + middle + suffix).encode()
            for mode in ('activate', 'retire'):
                with self.subTest(raw=raw, mode=mode):
                    output = lifecycle._config(raw, mode)
                    self.assertTrue(output.startswith(prefix.encode()))
                    self.assertTrue(output.endswith(suffix.encode()))
                    result = json.loads(output)
                    self.assertEqual('nunchi' in result['plugins']['enabled'], mode == 'activate')
                    self.assertEqual({k: v for k, v in yaml.safe_load(raw).items() if k != 'plugins'},
                                     {k: v for k, v in yaml.safe_load(output).items() if k != 'plugins'})
                    with tempfile.TemporaryDirectory() as tmp:
                        home = Path(tmp)
                        (home / 'config.yaml').write_bytes(raw)
                        plan = lifecycle.plan(home=home, mode='retire', profile='default')
                        receipt = lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)
                        lifecycle.rollback(home=home, transaction=receipt['transaction'], digest=lifecycle.digest(plan), stopped=True)
                        self.assertEqual((home / 'config.yaml').read_bytes(), raw)

    def test_json_safety_refusals_are_read_only(self):
        from nunchi.integrations import hermes_lifecycle as lifecycle
        cases = (
            b'{"plugins": {}, "plu\\u0067ins": {}}',
            b'{"private": {"key": 1, "key": 2}}',
            b'{"private": [{"key": 1, "key": 2}]}',
            b'{"plugins": {"enabled": [false]}}', b'{"plugins": null}',
            b'{"private": NaN}', b'{"private": Infinity}',
            b'{"private": -Infinity}', b'{"private": 1,}',
            b'{"private": 1} # YAML comment', b'---\n{"private": 1}',
            b'{"plugins": &a {}}', b'{"private": 1} {}',
        )
        for raw in cases:
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                (home / 'config.yaml').write_bytes(raw)
                with self.assertRaises(lifecycle.LifecycleError):
                    lifecycle.plan(home=home, mode='retire', profile='default')
                self.assertEqual((home / 'config.yaml').read_bytes(), raw)
                self.assertFalse((home / lifecycle.STORE).exists())

    def test_yaml_safety_refusals_are_read_only(self):
        from nunchi.integrations import hermes_lifecycle as lifecycle
        cases = (
            b'plugins:\n  enabled: [nunchi]\nplugins:\n  enabled: [other]\n',
            b'plugins:\n  enabled: [nunchi]\n  enabled: [other]\n',
            b'private:\n  key: one\n  key: two\n',
            b'private: &anchor [secret]\ncopy: *anchor\n',
            b'{plugins: {enabled: [nunchi]}}\n',
            b'plugins: {enabled: [nunchi]}\n',
            b'---\nmodel: one\n---\nmodel: two\n',
            b'plugins:\n  enabled: [false]\n',
            b'plugins: null\n', b'[]\n', b'private: [\n',
        )
        for raw in cases:
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                (home / 'config.yaml').write_bytes(raw)
                with self.assertRaises(lifecycle.LifecycleError):
                    lifecycle.plan(home=home, mode='retire', profile='default')
                self.assertEqual(raw, (home / 'config.yaml').read_bytes())
                self.assertFalse((home / lifecycle.STORE).exists())

    def test_yaml_import_fallback_only_for_absent_host_api(self):
        from unittest.mock import patch, call
        from nunchi.integrations import hermes_lifecycle as lifecycle
        import importlib
        released = object()
        with patch.object(importlib, 'import_module', side_effect=[
                ModuleNotFoundError(name='hermes_yaml'), released]) as load:
            self.assertIs(released, lifecycle._host_yaml())
            self.assertEqual(load.call_args_list, [call('hermes_yaml'), call('yaml')])
        for error in (ModuleNotFoundError(name='ruamel'), ImportError('broken host')):
            with patch.object(importlib, 'import_module', side_effect=error) as load:
                with self.assertRaises(type(error)):
                    lifecycle._config(b'plugins:\n  enabled: []\n', 'activate')
                load.assert_called_once_with('hermes_yaml')

    def test_native_publication_never_replaces_a_new_destination(self):
        from itertools import product
        from unittest.mock import patch
        from nunchi.integrations import hermes_lifecycle as lifecycle
        originals = (b'plugins:\n  enabled: [nunchi]\n', b'{"plugins": {"enabled": ["nunchi"]}}\n')
        for rollback in (False, True):
            for kind, original in product(('file', 'directory', 'symlink'), originals):
                with self.subTest(rollback=rollback, kind=kind, original=original), tempfile.TemporaryDirectory() as directory:
                    home = Path(directory)
                    edit = b'late-private-edit'
                    (home / 'config.yaml').write_bytes(original)
                    outside = home / 'unrelated'
                    outside.write_bytes(edit)
                    plan = lifecycle.plan(home=home, mode='retire', profile='default')
                    receipt = None
                    if rollback:
                        receipt = lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)
                    native = lifecycle._rename_noreplace
                    def race(sp, sn, dp, dn):
                        if dn == 'config.yaml':
                            if kind == 'file':
                                (home / dn).write_bytes(edit)
                            elif kind == 'directory':
                                (home / dn).mkdir()
                            else:
                                (home / dn).symlink_to(outside)
                        return native(sp, sn, dp, dn)
                    with patch.object(lifecycle, '_rename_noreplace', side_effect=race):
                        with self.assertRaises(lifecycle.LifecycleError):
                            if rollback:
                                assert receipt is not None
                                lifecycle.rollback(home=home, transaction=receipt['transaction'], digest=lifecycle.digest(plan), stopped=True)
                            else:
                                lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)
                    if kind == 'directory':
                        self.assertTrue((home / 'config.yaml').is_dir())
                    else:
                        self.assertEqual((home / 'config.yaml').read_bytes(), edit)
                    self.assertEqual(outside.read_bytes(), edit)
                    self.assertTrue(any(p.read_bytes() == original for p in (home / lifecycle.STORE).rglob('before-*') if p.is_file()))

    def test_move_captures_source_conflict_and_refuses_restore(self):
        from unittest.mock import patch
        from nunchi.integrations import hermes_lifecycle as lifecycle
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            original = b'plugins:\n  enabled: [nunchi]\n'
            edit = b'late-private-edit'
            (home / 'config.yaml').write_bytes(original)
            plan = lifecycle.plan(home=home, mode='retire', profile='default')
            receipt = lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)
            native = lifecycle._rename_noreplace
            def race(sp, sn, dp, dn):
                if sn == 'config.yaml':
                    (home / sn).write_bytes(edit)
                return native(sp, sn, dp, dn)
            with patch.object(lifecycle, '_rename_noreplace', side_effect=race):
                with self.assertRaises(lifecycle.LifecycleError):
                    lifecycle.rollback(home=home, transaction=receipt['transaction'], digest=lifecycle.digest(plan), stopped=True)
            archive = home / lifecycle.STORE / receipt['transaction']
            self.assertEqual((archive / 'before-0').read_bytes(), original)
            self.assertEqual((archive / 'retired-0').read_bytes(), edit)
            self.assertFalse((home / 'config.yaml').exists())

    def test_hard_exit_inside_each_native_move_recovers(self):
        import multiprocessing
        from nunchi.integrations import hermes_lifecycle as lifecycle
        for restoring in (False, True):
            for move in (1, 2):
                with self.subTest(restoring=restoring, move=move), tempfile.TemporaryDirectory() as directory:
                    home = Path(directory)
                    original = b'plugins:\n  enabled: [nunchi]\n'
                    (home / 'config.yaml').write_bytes(original)
                    plan = lifecycle.plan(home=home, mode='retire', profile='default')
                    transaction = None
                    if restoring:
                        transaction = lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)['transaction']
                    process = multiprocessing.get_context('fork').Process(target=_crash_native, args=(str(home), plan, transaction, move))
                    process.start()
                    process.join(10)
                    self.assertEqual(process.exitcode, 72)
                    transaction = next(p.name for p in (home / lifecycle.STORE).iterdir() if p.is_dir())
                    lifecycle.rollback(home=home, transaction=transaction, digest=lifecycle.digest(plan), stopped=True)
                    self.assertEqual((home / 'config.yaml').read_bytes(), original)
                    self.assertTrue(lifecycle.verify(home=home, transaction=transaction)['ok'])

    def test_legacy_path_fallback_and_disabled_log_matrix(self):
        import os
        from tests.v2.hermes_normal_turn_support import host_yaml
        yaml = host_yaml()
        from unittest.mock import patch
        from nunchi.integrations import hermes_lifecycle as lifecycle
        with tempfile.TemporaryDirectory() as directory:
            user = Path(directory).resolve()
            machine = user / '.hermes'
            named = machine / 'profiles/worker'
            for home in (machine, named):
                (home / 'plugins/nunchi-gate').mkdir(parents=True)
                (home / 'nunchi-gate.state.json').write_bytes(b'private-state')
                (home / 'logs').mkdir()
                (home / 'logs/nunchi-gate.jsonl').write_bytes(b'private-log')
            alias = user / 'alias'
            alias.symlink_to(named, target_is_directory=True)
            omitted = object()
            for home in (machine, named, alias):
                for state in (omitted, None, '', False, 0, str(home / 'nunchi-gate.state.json')):
                    for log in (omitted, None, '', False, 0, ' no ', 'OFF', 'none', str(home / 'logs/nunchi-gate.jsonl')):
                        legacy = {}
                        if state is not omitted:
                            legacy['state_path'] = state
                        if log is not omitted:
                            legacy['log_path'] = log
                        raw = yaml.safe_dump({'plugins': {'enabled': ['nunchi-gate']}, 'turnaware': legacy}).encode()
                        (home / 'config.yaml').write_bytes(raw)
                        refused = home != machine and (not state or state is omitted or log is omitted)
                        with self.subTest(home=home.name, state=repr(state), log=repr(log)), \
                                patch.dict(os.environ, {'HOME': str(user), 'HERMES_HOME': str(home)}, clear=True), \
                                patch.object(lifecycle, '_predecessors', return_value=['plugins/nunchi-gate']):
                            if refused:
                                with self.assertRaisesRegex(lifecycle.LifecycleError, 'outside selected home'):
                                    lifecycle.plan(home=home, mode='retire', profile='default')
                            else:
                                plan = lifecycle.plan(home=home, mode='retire', profile='default')
                                paths = {op['path'] for op in plan['operations']}
                                self.assertIn('nunchi-gate.state.json', paths)
                                self.assertEqual('logs/nunchi-gate.jsonl' in paths, log is omitted or log == str(home / 'logs/nunchi-gate.jsonl'))
                            self.assertEqual((home / 'config.yaml').read_bytes(), raw)
                            self.assertFalse((home / lifecycle.STORE).exists())
                            self.assertEqual((machine / 'nunchi-gate.state.json').read_bytes(), b'private-state')

    def test_legacy_defaults_follow_home_not_hermes_home(self):
        import os
        from unittest.mock import patch
        from nunchi.integrations import hermes_lifecycle as lifecycle
        with tempfile.TemporaryDirectory() as directory:
            user = Path(directory).resolve()
            machine = user / '.hermes'
            home = machine / 'profiles/worker'
            (home / 'plugins/nunchi-gate').mkdir(parents=True)
            original = b'plugins:\n  enabled: [nunchi-gate]\n'
            (home / 'config.yaml').write_bytes(original)
            # Attribution has its own exact-source installed test. Isolate path
            # resolution here without shipping executable V1 fixtures.
            with patch.dict(os.environ, {'HOME': str(user), 'HERMES_HOME': str(home)}, clear=True), \
                    patch.object(lifecycle, '_predecessors', return_value=['plugins/nunchi-gate']):
                with self.assertRaisesRegex(lifecycle.LifecycleError, 'outside selected home'):
                    lifecycle.plan(home=home, mode='retire', profile='worker')
            self.assertEqual((home / 'config.yaml').read_bytes(), original)
            self.assertFalse((home / lifecycle.STORE).exists())

    def test_late_apply_edit_is_not_clobbered(self):
        from unittest.mock import patch
        from nunchi.integrations import hermes_lifecycle as lifecycle
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            original = b'plugins:\n  enabled: [nunchi]\n'
            edit = b'private_operator_edit: preserve-me\n'
            (home / 'config.yaml').write_bytes(original)
            plan = lifecycle.plan(home=home, mode='retire', profile='default')
            def late_edit(stage):
                if stage == 'backed-up':
                    (home / 'config.yaml').write_bytes(edit)
            with patch.object(lifecycle, '_checkpoint', side_effect=late_edit):
                with self.assertRaises(lifecycle.LifecycleError):
                    lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)
            self.assertEqual((home / 'config.yaml').read_bytes(), edit)
            self.assertTrue(any(p.read_bytes() == original for p in (home / lifecycle.STORE).rglob('before-*') if p.is_file()))

    def test_late_rollback_edit_is_not_clobbered(self):
        from unittest.mock import patch
        from nunchi.integrations import hermes_lifecycle as lifecycle
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            original = b'plugins:\n  enabled: [nunchi]\n'
            edit = b'private_operator_edit: preserve-me\n'
            (home / 'config.yaml').write_bytes(original)
            plan = lifecycle.plan(home=home, mode='retire', profile='default')
            receipt = lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)
            write = lifecycle._json_write
            def late_edit(fd, name, value):
                write(fd, name, value)
                if value.get('status') == 'rolling_back':
                    (home / 'config.yaml').write_bytes(edit)
            with patch.object(lifecycle, '_json_write', side_effect=late_edit):
                with self.assertRaises(lifecycle.LifecycleError):
                    lifecycle.rollback(home=home, transaction=receipt['transaction'], digest=lifecycle.digest(plan), stopped=True)
            self.assertEqual((home / 'config.yaml').read_bytes(), edit)
            self.assertEqual((home / lifecycle.STORE / receipt['transaction'] / 'before-0').read_bytes(), original)

    def test_yaml_document_boundaries_remain_valid(self):
        from tests.v2.hermes_normal_turn_support import host_yaml
        yaml = host_yaml()
        from nunchi.integrations import hermes_lifecycle as lifecycle
        for raw in (b'model: unchanged\n...\n',
                    b'---\nmodel: "private: sentinel"\n... # end\n',
                    b'---\n"plugins":\n    enabled: [other, nunchi]\n# private comment\nprivate: unchanged\n...\n',
                    b'# private comment\nmodel: unchanged', b'---\n# empty\n...\n'):
            for mode in ('retire', 'activate'):
                with self.subTest(raw=raw, mode=mode):
                    rendered = lifecycle._config(raw, mode)
                    result = yaml.safe_load(rendered)
                    before = yaml.safe_load(raw) or {}
                    self.assertEqual({k: v for k, v in result.items() if k != 'plugins'},
                                     {k: v for k, v in before.items() if k != 'plugins'})
                    self.assertEqual('nunchi' in result['plugins']['enabled'], mode == 'activate')
                    for line in raw.splitlines():
                        if line.startswith((b'model:', b'private:', b'#', b'---', b'...')):
                            self.assertIn(line, rendered)
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / 'config.yaml').write_bytes(b'model: unchanged\n...\n')
            plan = lifecycle.plan(home=home, mode='retire', profile='default')
            receipt = lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)
            self.assertIsInstance(yaml.safe_load((home / 'config.yaml').read_bytes()), dict)
            self.assertTrue(lifecycle.verify(home=home, transaction=receipt['transaction'])['ok'])

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


def _crash_native(home, plan, transaction, move):
    import os
    from nunchi.integrations import hermes_lifecycle as lifecycle
    native = lifecycle._rename_noreplace
    count = 0
    def crash(sp, sn, dp, dn):
        nonlocal count
        native(sp, sn, dp, dn)
        count += 1
        if count == move:
            os._exit(72)
    lifecycle._rename_noreplace = crash
    if transaction:
        lifecycle.rollback(home=home, transaction=transaction, digest=lifecycle.digest(plan), stopped=True)
    else:
        lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)


def _crash_apply(home, plan):
    import os
    from nunchi.integrations import hermes_lifecycle as lifecycle
    lifecycle._checkpoint = lambda stage: os._exit(71)
    lifecycle.apply(home=home, plan=plan, digest=lifecycle.digest(plan), stopped=True)


if __name__ == '__main__':
    unittest.main()
