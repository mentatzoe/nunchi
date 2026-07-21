"""Closed installed V2 entry-point contract."""

from __future__ import annotations

import importlib
import json
import pathlib
import tomllib
import unittest


_ROOT = pathlib.Path(__file__).resolve().parent.parent


class InstalledV2SurfaceCases(unittest.TestCase):
    def test_package_metadata_describes_preattention_not_a_v1_reply_gate(self):
        project = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
            "project"
        ]
        description = project["description"].lower()
        keywords = set(project["keywords"])
        self.assertIn("pre-attention", description)
        self.assertIn("pre-attention", keywords)
        self.assertNotIn("admission-gate", keywords)
        self.assertNotIn("moderation", keywords)
        self.assertNotIn("should this agent speak", description)

    def test_pyproject_matches_the_closed_surface_contract(self):
        project = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        contract = json.loads(
            (_ROOT / "evals" / "v2" / "provenance" / "surfaces.json").read_text(
                encoding="utf-8"
            )
        )
        scripts = project["project"]["scripts"]
        self.assertEqual(scripts, contract["required_scripts"])
        self.assertFalse(set(scripts) & set(contract["removed_scripts"]))

    def test_every_required_target_is_importable_and_callable(self):
        project = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        for script, target in project["project"]["scripts"].items():
            module_name, attribute = target.split(":", 1)
            with self.subTest(script=script):
                module = importlib.import_module(module_name)
                self.assertTrue(callable(getattr(module, attribute, None)))


if __name__ == "__main__":
    unittest.main()
