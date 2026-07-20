"""Historical V1 corpus remains inspectable but cannot execute a V1 runtime."""

from __future__ import annotations

import contextlib
import io
import unittest

from evals.verdict_suite import loader, runner


class ArchivedVerdictCorpusCases(unittest.TestCase):
    def test_bundled_corpus_remains_well_formed_and_partitioned(self):
        fixtures = loader.discover_fixtures(runner.DEFAULT_FIXTURES_ROOT)
        self.assertGreaterEqual(len(fixtures), 19)
        self.assertEqual([fixture.id for fixture in fixtures], sorted(f.id for f in fixtures))
        self.assertTrue(all(fixture.envelope_path.is_file() for fixture in fixtures))
        self.assertTrue(all(fixture.meta_path.is_file() for fixture in fixtures))

    def test_list_command_is_available_for_historical_traceability(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = runner.main(["--list", "--source", "discord"])
        self.assertEqual(result, 0)
        self.assertIn("archived V1 fixture", output.getvalue())
        self.assertIn("discord", output.getvalue())

    def test_execution_is_explicitly_unavailable(self):
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            result = runner.main([])
        self.assertEqual(result, 2)
        self.assertIn("list-only", error.getvalue())
        self.assertIn("evals.v2", error.getvalue())


if __name__ == "__main__":
    unittest.main()
