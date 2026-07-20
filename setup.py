"""Setuptools hook that prevents stale deleted modules from entering wheels."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from setuptools import setup
from setuptools.command.build import build


class IsolatedBuild(build):
    """Use a fresh build-lib directory for every package build.

    Setuptools otherwise reuses ``build/lib`` without removing files that were
    deleted from ``src``. A wheel built after the V2 cutover could therefore
    resurrect old V1 modules. A unique sibling avoids that state without a
    build hook recursively deleting a potentially redirected directory.
    """

    def finalize_options(self) -> None:
        super().finalize_options()
        build_parent = Path(self.build_lib).parent
        self.build_lib = str(build_parent / f"lib-nunchi-{uuid4().hex}")


setup(cmdclass={"build": IsolatedBuild})
