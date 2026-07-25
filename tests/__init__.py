"""Test package setup for source-layout imports."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def load_tests(loader, _standard_tests, pattern):
    """Atomic V2 suite.

    Top-level ``tests/test_*.py`` files are retained only as the historical V1
    coverage ledger. They are intentionally not executable product tests after
    the V2 cutover. Current tests live under ``tests/v2``.
    """
    return loader.discover(
        str(ROOT / "tests" / "v2"),
        pattern=pattern or "test*.py",
        top_level_dir=str(ROOT),
    )
