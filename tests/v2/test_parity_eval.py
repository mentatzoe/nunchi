from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from evals.v2.parity import runner


class SceneCatalogCases(unittest.TestCase):
    def test_catalog_is_exactly_ordered_s01_through_s18(self):
        catalog = runner.load_catalog()
        self.assertEqual(
            tuple(scene["scene_id"] for scene in catalog["scenes"]),
            runner.EXPECTED_SCENE_IDS,
        )
        self.assertEqual(len(catalog["scenes"]), 18)

    def test_external_only_scenes_cannot_be_reported_complete_offline(self):
        record = runner.run(
            selected_ids=("S12", "S14"),
            deterministic_time=True,
        )
        self.assertEqual(record["summary"]["mechanics_failed"], [])
        self.assertEqual(record["summary"]["incomplete"], ["S12", "S14"])
        self.assertFalse(record["summary"]["candidate_complete"])
        self.assertEqual(
            [scene["mechanics"] for scene in record["scenes"]],
            ["not-applicable", "not-applicable"],
        )

    def test_selected_mechanics_scene_runs_its_existing_tests(self):
        record = runner.run(selected_ids=("S17",), deterministic_time=True)
        self.assertEqual(record["scenes"][0]["mechanics"], "passed")
        self.assertIn("S17", record["summary"]["incomplete"])


class RunnerBoundaryCases(unittest.TestCase):
    def test_output_is_exclusive_and_record_is_valid_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evidence.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                first = runner.main(
                    ["--scene", "S12", "--deterministic-time", "--output", str(output)]
                )
                second = runner.main(
                    ["--scene", "S12", "--deterministic-time", "--output", str(output)]
                )
            self.assertEqual(first, 0)
            self.assertEqual(second, 2)
            document = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(document["summary"]["incomplete"], ["S12"])

    def test_unknown_scene_is_a_usage_error(self):
        with redirect_stderr(StringIO()):
            self.assertEqual(runner.main(["--scene", "S99"]), 2)


if __name__ == "__main__":
    unittest.main()
