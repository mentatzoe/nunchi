from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.check_slice020_task_state import ACTIVE_OPEN_OPTIONS, evaluate_task_state


TASKS = Path("spec" + "s") / "020-v2-observation" / "tasks.md"
EXPECTED_SUPERSEDED = frozenset(
    {"T107", "T112", "T119", "T124", "T131", "T140", "T146"}
)


class TestSlice020LiteralTaskState(unittest.TestCase):
    def test_current_pre_review_state_has_exact_terminal_manifest_and_open_gates(self):
        state = evaluate_task_state(TASKS)
        self.assertEqual(state.all_ids, tuple(f"T{number:03d}" for number in range(1, 154)))
        self.assertEqual(state.superseded, EXPECTED_SUPERSEDED)
        self.assertIn(state.open_ids, ACTIVE_OPEN_OPTIONS)
        self.assertEqual(len(state.checked), 153 - len(state.open_ids))

    def test_noncanonical_checkbox_fails_closed(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(
                "# Tasks\n\n**Slice state**: `ACTIVE`\n\n"
                "- [X] T001 valid\n"
                "- [done] T002 malformed\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "invalid task format"):
                evaluate_task_state(path)

    def test_missing_terminal_or_added_task_fails_closed(self):
        original = TASKS.read_text(encoding="utf-8")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(
                original.replace("- [ ] T153", "- [ ] T154", 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError, "sequential from T001|exactly T001 through T153"
            ):
                evaluate_task_state(path)

    def test_arbitrary_open_gate_fails_closed(self):
        original = TASKS.read_text(encoding="utf-8")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(
                original.replace("- [X] T102", "- [ ] T102", 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "literal open task IDs"):
                evaluate_task_state(path)

    def test_superseded_gate_requires_checked_explicit_successor(self):
        original = TASKS.read_text(encoding="utf-8")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(
                original.replace("- [X] T146", "- [ ] T146", 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "superseded gate T146"):
                evaluate_task_state(path)


if __name__ == "__main__":
    unittest.main()
