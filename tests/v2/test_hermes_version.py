"""Fail-closed host identity without a private Hermes version stamp."""
from __future__ import annotations

import importlib.metadata
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from nunchi.errors import ValidationError
from nunchi.integrations.hermes_version import hermes_version


class HermesVersionTests(unittest.TestCase):
    def test_released_metadata_wins_without_importing_host(self):
        for version in ("0.19.0", "0.19.0.post1", "0.21.5", "1.0.0+vendor.1"):
            with self.subTest(version=version), mock.patch(
                "importlib.metadata.version", return_value=version
            ), mock.patch("importlib.import_module") as load:
                self.assertEqual(version, hermes_version())
                load.assert_not_called()

    def test_invalid_or_below_floor_metadata_never_uses_fallback(self):
        for version in ("unknown", "0.18.9", "0.19.0rc1", "0.19.0.dev1", "0.0.0+fake", "v0.21.5", "0.21", "2026.9.24junk"):
            with self.subTest(version=version), mock.patch(
                "importlib.metadata.version", return_value=version
            ), mock.patch("importlib.import_module") as load:
                with self.assertRaises(ValidationError):
                    hermes_version()
                load.assert_not_called()

    def test_missing_distribution_fails_closed(self):
        with mock.patch("importlib.metadata.version", side_effect=importlib.metadata.PackageNotFoundError):
            with self.assertRaises(ValidationError):
                hermes_version()

    def _source(self, root, **changes):
        fields = dict(base_version="0.21.5", derived_version="0.21.5+17.gabcdef1", distance=17,
                      commit="abcdef1" + "2" * 33, source="git", dirty=False)
        fields.update(changes)
        return SimpleNamespace(__file__=str(root / "hermes_cli/version_info.py"),
                               get_version_info=lambda: SimpleNamespace(**fields))

    def _resolve(self, module, commit=None):
        with mock.patch("importlib.metadata.version", return_value="0.0.0"), mock.patch("subprocess.run", return_value=SimpleNamespace(
            returncode=0, stdout=commit or "abcdef1" + "2" * 33
        )), mock.patch("importlib.import_module", return_value=module):
            return hermes_version()

    def test_clean_source_uses_official_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            self.assertEqual("0.21.5+17.gabcdef1", self._resolve(self._source(root)))

    def test_unrelated_home_git_cannot_identify_installed_wheel(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValidationError):
                self._resolve(self._source(Path(tmp)))

    def test_official_build_identity_and_exact_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for source in ("build", "commit-build", "ci", "docker", "local", "nix"):
                with self.subTest(source=source):
                    module = self._source(root, source=source, derived_version="0.21.5+17")
                    self.assertEqual("0.21.5+17", self._resolve(module))
            (root / ".git").mkdir()
            module = self._source(root, distance=0, derived_version="0.21.5")
            self.assertEqual("0.21.5", self._resolve(module))

    def test_missing_provenance_fields_fail_closed(self):
        with self.assertRaises(ValidationError):
            self._resolve(SimpleNamespace(get_version_info=lambda: object()))

    def test_bad_provenance_fails_closed(self):
        mutations = (
            {"source": "unknown"}, {"source": "fallback"}, {"source": "future-shape"},
            {"base_version": "unknown"}, {"base_version": "0.18.9"},
            {"base_version": "0.19.0rc1"}, {"commit": None}, {"commit": "0" * 40},
            {"commit": "abc"}, {"dirty": True}, {"dirty": "false"},
            {"distance": None}, {"distance": -1}, {"distance": True},
            {"derived_version": "0.99.0+17.gabcdef1"},
            {"derived_version": "0.21.5+17.g0000000"},
            {"derived_version": "0.21.5+18.gabcdef1"},
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            for changes in mutations:
                with self.subTest(changes=changes), self.assertRaises(ValidationError):
                    self._resolve(self._source(root, **changes))
            with self.assertRaises(ValidationError):
                self._resolve(self._source(root), commit="f" * 40)

    def test_unavailable_official_api_fails_closed(self):
        for error in (ImportError("absent"), RuntimeError("bad stamp")):
            with mock.patch("importlib.metadata.version", return_value="0.0.0"), mock.patch(
                "importlib.import_module", side_effect=error
            ), self.assertRaises(ValidationError):
                hermes_version()


if __name__ == "__main__":
    unittest.main()
