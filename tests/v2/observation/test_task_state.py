from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.check_slice020_task_state import ACTIVE_OPEN_OPTIONS, evaluate_task_state


TASKS = Path("spec" + "s") / "020-v2-observation" / "tasks.md"
EXPECTED_SUPERSEDED = frozenset(
    {"T107", "T112", "T119", "T124", "T131", "T140", "T146", "T153"}
)


class TestSlice020LiteralTaskState(unittest.TestCase):
    def test_current_pre_review_state_has_exact_terminal_manifest_and_open_gates(self):
        state = evaluate_task_state(TASKS)
        self.assertEqual(state.all_ids, tuple(f"T{number:03d}" for number in range(1, 161)))
        self.assertEqual(state.superseded, EXPECTED_SUPERSEDED)
        self.assertIn(state.open_ids, ACTIVE_OPEN_OPTIONS)
        self.assertEqual(len(state.checked), 160 - len(state.open_ids))

    def test_every_checkbox_shaped_row_must_be_canonical(self):
        original = TASKS.read_text(encoding="utf-8")
        for malformed in (
            "- [ ] TASK161 unresolved release blocker\n",
            "- [ ] T 161 hidden malformed task\n",
            "- [done] T161 malformed mark\n",
        ):
            with self.subTest(malformed=malformed), TemporaryDirectory() as directory:
                path = Path(directory) / "tasks.md"
                path.write_text(original + malformed, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "invalid task format"):
                    evaluate_task_state(path)

    def test_missing_or_added_terminal_task_fails_closed(self):
        original = TASKS.read_text(encoding="utf-8")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(
                original.replace("- [ ] T160", "- [ ] T161", 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError, "sequential from T001|exactly T001 through T160"
            ):
                evaluate_task_state(path)
            path.write_text(original + "\n- [X] T161 extra task\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exactly T001 through T160"):
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

    def test_superseded_gate_requires_checked_exact_successor_and_rejection_truth(self):
        original = TASKS.read_text(encoding="utf-8")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(
                original.replace("superseded by T160", "superseded by T159", 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "superseded gate T153"):
                evaluate_task_state(path)
            path.write_text(
                original.replace("remains rejected", "was reviewed", 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "rejected/not-approved semantics"):
                evaluate_task_state(path)


if __name__ == "__main__":
    unittest.main()
