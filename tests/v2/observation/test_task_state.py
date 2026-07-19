from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.check_slice020_task_state import evaluate_task_state


TASKS = Path("spec" + "s") / "020-v2-observation" / "tasks.md"


class TestSlice020LiteralTaskState(unittest.TestCase):
    def test_current_pre_review_state_is_literal_and_only_final_gates_are_open(self):
        state = evaluate_task_state(
            TASKS,
            allowed_open=frozenset({"T103", "T140"}),
        )
        self.assertEqual(state.all_ids[0], "T001")
        self.assertEqual(state.all_ids[-1], "T140")
        self.assertEqual(
            state.superseded,
            frozenset({"T107", "T112", "T119", "T124", "T131"}),
        )
        self.assertEqual(
            state.open_ids,
            frozenset({"T103", "T140"}),
        )

    def test_unexplained_unchecked_task_fails_closed(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text("- [X] T001 done\n- [ ] T002 unexplained\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unexplained unchecked"):
                evaluate_task_state(path, allowed_open=frozenset())

    def test_missing_or_reordered_task_id_fails_closed(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text("- [X] T001 done\n- [ ] T003 gap\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ordered, and contiguous"):
                evaluate_task_state(path, allowed_open=frozenset({"T003"}))

    def test_allowed_open_must_be_literally_unchecked(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text("- [X] T001 done\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not literally unchecked"):
                evaluate_task_state(path, allowed_open=frozenset({"T001"}))


if __name__ == "__main__":
    unittest.main()
