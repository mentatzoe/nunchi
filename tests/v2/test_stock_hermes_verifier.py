"""Offline tests of the installed verifier's isolation and fail-closed checks."""
import importlib.util
import os
import shlex
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StockVerifierTests(unittest.TestCase):
    def test_source_identity_requires_exact_nonempty_project_root(self):
        import subprocess
        verifier = script('verify_stock_hermes')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL)
            git('init')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                'commit', '--allow-empty', '-m', 'empty')
            with self.assertRaisesRegex(ValueError, 'tracked project inventory'):
                verifier.source_identity(root)
            (root / 'pyproject.toml').write_text('[project]\nname="fixture"\n')
            git('add', 'pyproject.toml')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'project')
            identity = verifier.source_identity(root)
            self.assertTrue(identity['tracked_clean'])
            with self.assertRaisesRegex(ValueError, 'tracked project inventory'):
                verifier.source_identity(root, ('pyproject.toml', 'hermes_cli/__init__.py'))
            nested = root / 'archive'
            nested.mkdir()
            for dirty in (False, True):
                if dirty:
                    (root / 'pyproject.toml').write_text('# changed\n')
                # Reject before inventory/hashing; don't read the enclosing project.
                with mock.patch.object(Path, 'read_bytes', side_effect=AssertionError('unrelated read')):
                    with self.assertRaisesRegex(ValueError, 'exact Git root'):
                        verifier.source_identity(nested)

    def test_approval_target_is_new_private_fixture_data(self):
        from tests.v2.test_hermes_normal_turn import _Base
        with tempfile.TemporaryDirectory(prefix="approval home ") as tmp:
            case = _Base()
            case.home = Path(tmp)
            command, target = case.approval_command()
            self.assertTrue(target.is_relative_to(case.home.resolve()))
            self.assertEqual(["rm", "-rf", "--", str(target)], shlex.split(command))
            self.assertEqual("disposable approval fixture\n", (target / "marker").read_text())
            self.assertNotEqual(target, case.approval_command()[1])

    def test_child_environment_does_not_inherit_profile_keys_or_pythonpath(self):
        verifier = script("verify_stock_hermes")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {
            "OPENAI_API_KEY": "must-not-copy", "PYTHONPATH": "/forbidden",
            "HERMES_HOME": "/live", "PATH": "/operator/custom/bin",
        }):
            env = verifier.child_environment(Path(tmp), "discord", "startup-multiplex")
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertNotIn("PYTHONPATH", env)
            self.assertEqual(os.defpath, env["PATH"])
            self.assertTrue(Path(env["HERMES_HOME"]).is_relative_to(tmp))
            self.assertEqual("1", env["NUNCHI_PROBE_MULTIPLEX"])

    def test_network_denials_are_retained_even_if_caller_catches_exception(self):
        probe = script("stock_hermes_probe")
        attempts = []
        guard = probe.network_guard(attempts)
        for event, args in [("socket.connect", (None, ("203.0.113.1", 443))),
                            ("socket.sendto", (None, b"data", ("203.0.113.1", 53))),
                            ("socket.getaddrinfo", ("example.invalid", 443, 0, 0, 0)),
                            ("socket.gethostbyname", ("example.invalid",))]:
            with self.subTest(event=event), self.assertRaises(AssertionError):
                guard(event, args)
        self.assertEqual(4, len(attempts))
        guard("socket.connect", (None, ("127.0.0.1", 12345)))
        guard("socket.getaddrinfo", ("::1", 12345, 0, 0, 0))
        guard("socket.connect", (None, "/tmp/local.sock"))
        self.assertEqual(4, len(attempts))

    def test_lane_manifest_has_exact_no_skip_denominators(self):
        lanes = script("stock_hermes_probe").LANES
        self.assertEqual({"contract": 4, "normal-attention": 33,
                          "startup-single": 1, "startup-multiplex": 1},
                         {name: value[1] for name, value in lanes.items()})

    def test_wheel_identity_rejects_omitted_and_changed_payload(self):
        verifier = script("verify_stock_hermes")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "src" / "nunchi"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("# original\n")
            (package / "required.py").write_text("# required\n")
            wheel = root / "nunchi.whl"
            distribution = mock.Mock()
            distribution.locate_file.side_effect = lambda name: root / "src" / name
            with mock.patch.object(verifier.importlib.metadata, "distribution", return_value=distribution):
                with zipfile.ZipFile(wheel, "w") as archive:
                    archive.writestr("nunchi/__init__.py", "# original\n")
                with self.assertRaisesRegex(AssertionError, "file set mismatch"):
                    verifier.wheel_identity(wheel, root)
                with zipfile.ZipFile(wheel, "w") as archive:
                    archive.writestr("nunchi/__init__.py", "# original\n")
                    archive.writestr("nunchi/required.py", "# required\n")
                self.assertEqual(2, verifier.wheel_identity(wheel, root)["payload_files_matched"])
                (package / "required.py").write_text("# changed\n")
                with self.assertRaisesRegex(AssertionError, "installed wheel mismatch"):
                    verifier.wheel_identity(wheel, root)

    def test_fixture_selects_real_host_yaml_not_an_undeclared_dependency(self):
        from tests.v2 import hermes_normal_turn_support as support
        native = object()
        with mock.patch.object(support.importlib, "import_module", return_value=native) as load:
            self.assertIs(native, support.host_yaml())
            load.assert_called_once_with("hermes_yaml")
        missing = ModuleNotFoundError("no hermes_yaml", name="hermes_yaml")
        with mock.patch.object(support.importlib, "import_module", side_effect=[missing, native]) as load:
            self.assertIs(native, support.host_yaml())
            self.assertEqual([mock.call("hermes_yaml"), mock.call("yaml")], load.call_args_list)
        # Broken dependency inside the native module is not grounds for fallback.
        with mock.patch.object(support.importlib, "import_module",
                               side_effect=ModuleNotFoundError("no ruamel", name="ruamel")):
            with self.assertRaises(ModuleNotFoundError):
                support.host_yaml()
