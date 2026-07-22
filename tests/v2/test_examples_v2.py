from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]


class V2ExampleCases(unittest.TestCase):
    def run_example(self, name: str) -> str:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(ROOT / "src")
        completed = subprocess.run(
            [sys.executable, str(ROOT / "examples" / name)],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout

    def test_generic_example_runs_the_v2_lifecycle(self):
        output = self.run_example("generic_host_demo.py")
        self.assertIn("reference:event:1: WAKE", output)
        self.assertIn("reference:event:2: SUPPRESS", output)
        self.assertIn("reference:event:3: DEFER", output)
        self.assertIn("trusted bypass: status=bypass; model_calls=0", output)
        self.assertIn(
            "deterministic transport rejection: disposition=unroutable; "
            "model_or_participant_results=0",
            output,
        )

    def test_live_room_example_coalesces_instead_of_queueing(self):
        output = self.run_example("read_the_room_demo.py")
        self.assertIn("reference:event:1: SUPPRESS; participant_invoked=False", output)
        self.assertIn("reference:event:5: WAKE; participant_invoked=True", output)
        self.assertIn(
            "5 deliveries -> 2 judgments -> 1 participant turn -> 1 action",
            output,
        )
        self.assertIn("self echo: self-retained-no-wake; new_opportunity=False", output)

    def test_current_examples_do_not_import_or_teach_the_v1_gate(self):
        surfaces = (
            ROOT / "examples" / "generic_host_demo.py",
            ROOT / "examples" / "read_the_room_demo.py",
            ROOT / "examples" / "loader-snippet.md",
        )
        joined = "\n".join(path.read_text(encoding="utf-8") for path in surfaces)
        self.assertNotIn("nunchi.adapters.channel", joined)
        self.assertNotIn("NUNCHI_CLASSIFIER_TEST_RESULT", joined)
        self.assertNotIn("silent_token", joined)
        self.assertNotIn("CC_CONNECT_SILENT_PASS", joined)


if __name__ == "__main__":
    unittest.main()
