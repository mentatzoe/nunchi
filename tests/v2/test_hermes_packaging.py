"""Installed-wheel checks for the capability-negotiated Hermes plugin."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class HermesPluginPackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls._temporary.name)
        cls.source = cls.root / "source"
        shutil.copytree(
            ROOT,
            cls.source,
            ignore=shutil.ignore_patterns(
                ".git",
                ".venv",
                ".pytest_cache",
                ".ruff_cache",
                "__pycache__",
                "build",
                "*.egg-info",
            ),
        )
        cls.wheel_dir = cls.root / "wheel"
        cls.wheel_dir.mkdir()
        build_python = None
        candidates = [
            sys.executable,
            shutil.which("python3.13"),
            shutil.which("python3.12"),
            shutil.which("python3.11"),
        ]
        for candidate in dict.fromkeys(item for item in candidates if item):
            backend = subprocess.run(
                [
                    candidate,
                    "-c",
                    (
                        "import setuptools, sys;"
                        "sys.exit(0 if setuptools.__version__ == '83.0.0' else 1)"
                    ),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if backend.returncode == 0:
                build_python = candidate
                break
        if build_python is None:
            raise AssertionError("setuptools==83.0.0 build backend is unavailable")
        result = subprocess.run(
            [
                build_python,
                "-m",
                "pip",
                "wheel",
                "--no-build-isolation",
                "--no-deps",
                "--wheel-dir",
                str(cls.wheel_dir),
                str(cls.source),
            ],
            cwd=cls.root,
            env={
                key: value
                for key, value in os.environ.items()
                if key not in {"PYTHONPATH", "PYTHONHOME"}
            },
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(
                "wheel build failed\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        wheels = sorted(cls.wheel_dir.glob("nunchi-*.whl"))
        if len(wheels) != 1:
            raise AssertionError(f"expected one Nunchi wheel, found {wheels!r}")
        cls.wheel = wheels[0]

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def test_pip_installed_entry_point_is_discoverable_and_loadable(self) -> None:
        target = self.root / "installed"
        install = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--target",
                str(target),
                str(self.wheel),
            ],
            cwd=self.root,
            env={
                key: value
                for key, value in os.environ.items()
                if key not in {"PYTHONPATH", "PYTHONHOME"}
            },
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            0,
            install.returncode,
            f"stdout:\n{install.stdout}\nstderr:\n{install.stderr}",
        )
        probe = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                (
                    "import importlib.metadata as m, json, sys;"
                    "root=sys.argv[1];sys.path.insert(0,root);"
                    "eps=[ep for dist in m.distributions(path=[root]) "
                    "for ep in dist.entry_points "
                    "if ep.group=='hermes_agent.plugins' and ep.name=='nunchi-v2'];"
                    "doctors=[ep for dist in m.distributions(path=[root]) "
                    "for ep in dist.entry_points "
                    "if ep.group=='console_scripts' "
                    "and ep.name=='nunchi-hermes-v2-doctor'];"
                    "module=eps[0].load() if len(eps)==1 else None;"
                    "doctor=doctors[0].load() if len(doctors)==1 else None;"
                    "print(json.dumps({'count':len(eps),"
                    "'doctor_count':len(doctors),"
                    "'doctor_main':callable(doctor),"
                    "'value':eps[0].value if len(eps)==1 else None,"
                    "'register':callable(getattr(module,'register',None))}))"
                ),
                str(target),
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            0,
            probe.returncode,
            f"stdout:\n{probe.stdout}\nstderr:\n{probe.stderr}",
        )
        self.assertEqual(
            {
                "count": 1,
                "doctor_count": 1,
                "doctor_main": True,
                "value": "nunchi_hermes_v2",
                "register": True,
            },
            json.loads(probe.stdout),
        )

    def test_wheel_has_no_obsolete_hermes_host_patch_artifacts_or_script(self) -> None:
        with zipfile.ZipFile(self.wheel) as archive:
            members = archive.namelist()
            hermes_members = [
                name for name in members if name.startswith("nunchi_hermes_v2/")
            ]
            entry_points_name = next(
                name
                for name in members
                if name.endswith(".dist-info/entry_points.txt")
            )
            metadata_name = next(
                name
                for name in members
                if name.endswith(".dist-info/METADATA")
            )
            entry_points = archive.read(entry_points_name).decode("utf-8")
            metadata = archive.read(metadata_name).decode("utf-8")

        self.assertNotIn("nunchi-hermes-v2-host-patch", entry_points)
        self.assertFalse(
            [
                name
                for name in hermes_members
                if "host_patch" in name
                or "host-patch" in name
                or name.endswith(".patch")
            ]
        )
        self.assertIn("[hermes_agent.plugins]", entry_points)
        self.assertIn("nunchi-v2 = nunchi_hermes_v2", entry_points)
        self.assertIn("[console_scripts]", entry_points)
        self.assertIn(
            "nunchi-hermes-v2-doctor = nunchi_hermes_v2.doctor:main",
            entry_points,
        )
        self.assertNotIn("Requires-Dist: hermes-agent", metadata)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
