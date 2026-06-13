"""Self-tests for the verdict test suite runner.

These exercise loader correctness, report shape, the adapter contract, and
the runner plumbing. They do NOT exercise classifier judgment — the
classifier is provider-backed, so every test that actually invokes it
injects a deterministic fixture-provider result via
TURNAWARE_CLASSIFIER_TEST_RESULT and asserts that the runner observes and
reports exactly that verdict. Self-tests run offline in milliseconds.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

_SPEC_CONTRACTS = (
    Path(__file__).resolve().parent.parent
    / "specs"
    / "003-classifier-test-suite"
    / "contracts"
)
if str(_SPEC_CONTRACTS) not in sys.path:
    sys.path.insert(0, str(_SPEC_CONTRACTS))

import adapters  # noqa: E402
import loader  # noqa: E402
import report  # noqa: E402
import runner  # noqa: E402

from tests.provider_helpers import provider_env  # noqa: E402

FIXTURES_ROOT = _SPEC_CONTRACTS / "fixtures"


def _inject_provider_result(verdict: str, checked: list[str]):
    """patch.dict context manager injecting a deterministic classifier result.

    The injected payload is what `turnaware.core.evaluate` (and the CLI)
    return instead of calling a live provider, keeping self-tests offline.
    """
    return mock.patch.dict(os.environ, provider_env(verdict, checked=checked))


def _run_main_capturing_stdout(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exit_code = runner.main(argv)
    return exit_code, buf.getvalue()


class LoaderTests(unittest.TestCase):
    def test_loader_discovers_all_fixtures_and_validates_pairs(self):
        fixtures = loader.discover_fixtures(FIXTURES_ROOT)
        self.assertGreaterEqual(len(fixtures), 19)
        # Every fixture id has both envelope and meta files
        for f in fixtures:
            with self.subTest(fixture=f.id):
                self.assertTrue(f.envelope_path.exists())
                self.assertTrue(f.meta_path.exists())
                self.assertEqual(f.meta_path.name, f.envelope_path.stem + ".meta.json")
        # Sorted by id (FR-015 determinism)
        ids = [f.id for f in fixtures]
        self.assertEqual(ids, sorted(ids))

    def test_loader_source_filter_partitions_correctly(self):
        multica = loader.discover_fixtures(FIXTURES_ROOT, source="multica")
        discord = loader.discover_fixtures(FIXTURES_ROOT, source="discord")
        contract = loader.discover_fixtures(FIXTURES_ROOT, source="contract")
        all_ = loader.discover_fixtures(FIXTURES_ROOT)
        self.assertEqual(len(multica) + len(discord) + len(contract), len(all_))
        self.assertTrue(all(f.source_shape == "multica" for f in multica))
        self.assertTrue(all(f.source_shape == "discord" for f in discord))
        self.assertTrue(all(f.source_shape == "contract" for f in contract))


class VerdictSurfaceContractTests(unittest.TestCase):
    """FR-020 verdict-surface checks, exercised via the MockAdapter."""

    def test_subprocess_adapter_rejects_sentinel_leak_3_underscores(self):
        mock_adapter = adapters.MockAdapter("__CC_CONNECT_SILENT_PASS___")
        result = mock_adapter.classify({"trigger": {"content": "x"}})
        self.assertIs(result["ok"], False)
        self.assertEqual(result["error_kind"], "sentinel-leak")

    def test_subprocess_adapter_rejects_sentinel_leak_4_underscores(self):
        mock_adapter = adapters.MockAdapter("__CC_CONNECT_SILENT_PASS____")
        result = mock_adapter.classify({"trigger": {"content": "x"}})
        self.assertIs(result["ok"], False)
        self.assertEqual(result["error_kind"], "sentinel-leak")

    def test_subprocess_adapter_rejects_bare_pass_string(self):
        mock_adapter = adapters.MockAdapter("PASS")
        result = mock_adapter.classify({"trigger": {"content": "x"}})
        self.assertIs(result["ok"], False)
        # bare "PASS" trips the sentinel-leak path because it matches the
        # CC_CONNECT_SILENT_PASS marker substring, OR the malformed-output path
        # because it isn't JSON. Either is a contract violation.
        self.assertIn(result["error_kind"], ("sentinel-leak", "malformed-output"))

    def test_subprocess_adapter_accepts_typed_verdict_object(self):
        mock_adapter = adapters.MockAdapter(
            '{"verdict": "PASS", "confidences": {"PASS": 0.85, "ACK": 0.05, '
            '"ASK": 0.05, "SPEAK": 0.05}, "context_checked": ["trigger"]}'
        )
        result = mock_adapter.classify({"trigger": {"content": "x"}})
        self.assertIs(result["ok"], True)
        self.assertEqual(result["verdict"], "PASS")


class InProcessAdapterTests(unittest.TestCase):
    """Runner plumbing through the InProcessAdapter.

    The classifier is provider-backed; these tests inject a chosen verdict
    via TURNAWARE_CLASSIFIER_TEST_RESULT and assert the adapter/runner
    observed and scored exactly that verdict. They verify suite machinery,
    not classifier judgment.
    """

    def test_in_process_adapter_against_a_known_fixture(self):
        fixtures = loader.discover_fixtures(FIXTURES_ROOT, source="multica")
        baseline = next(f for f in fixtures if f.id == "m-baseline-pass-adapter-resolved")
        adapter = adapters.InProcessAdapter()
        with _inject_provider_result(
            "PASS", checked=["trigger:ping-msg", "context:ctx-pass-handled"]
        ):
            result = adapter.classify(baseline.envelope)
        self.assertIs(result["ok"], True)
        self.assertEqual(result["verdict"], "PASS")

    def test_run_one_fixture_handles_contract_fixture_via_mock_adapter(self):
        fixtures = loader.discover_fixtures(FIXTURES_ROOT, source="contract")
        f3 = next(
            f for f in fixtures if f.id == "c-verdict-surface-sentinel-leak-3-underscores"
        )
        adapter = adapters.InProcessAdapter()
        response, status, observed, detail = runner._run_one_fixture(
            f3, adapter, deterministic_time=True
        )
        self.assertEqual(status, "pass")
        self.assertEqual(response["error_kind"], "sentinel-leak")

    def test_run_one_fixture_handles_known_false_ack(self):
        # m-substring-trap-back-results expects SPEAK; inject the historical
        # false-ACK verdict and assert the runner reports the mismatch as a
        # fail with observed=ACK (runner plumbing, not classifier judgment).
        fixtures = loader.discover_fixtures(FIXTURES_ROOT, source="multica")
        f = next(f for f in fixtures if f.id == "m-substring-trap-back-results")
        adapter = adapters.InProcessAdapter()
        with _inject_provider_result(
            "ACK", checked=["trigger:comment-c8a85931-dfdc-48ab-8121-bc3c4d072f54"]
        ):
            response, status, observed, detail = runner._run_one_fixture(
                f, adapter, deterministic_time=True
            )
        self.assertEqual(status, "fail")
        self.assertEqual(observed, "ACK")
        self.assertIn("SPEAK", detail)

    def test_run_one_fixture_passes_when_injected_verdict_matches_expected(self):
        # Complement of the false-ACK case: injecting the expected verdict
        # must be scored as a pass with the same fixture.
        fixtures = loader.discover_fixtures(FIXTURES_ROOT, source="multica")
        f = next(f for f in fixtures if f.id == "m-substring-trap-back-results")
        adapter = adapters.InProcessAdapter()
        with _inject_provider_result(
            "SPEAK", checked=["trigger:comment-c8a85931-dfdc-48ab-8121-bc3c4d072f54"]
        ):
            response, status, observed, detail = runner._run_one_fixture(
                f, adapter, deterministic_time=True
            )
        self.assertEqual(status, "pass")
        self.assertEqual(observed, "SPEAK")


class ReportTests(unittest.TestCase):
    def test_report_jsonl_round_trips(self):
        fixtures = loader.discover_fixtures(FIXTURES_ROOT, source="multica")
        f = next(f for f in fixtures if f.id == "m-baseline-pass-adapter-resolved")
        response = {
            "ok": True,
            "verdict": "PASS",
            "confidences": {"PASS": 0.85, "ACK": 0.05, "ASK": 0.05, "SPEAK": 0.05},
            "context_checked": ["trigger", "ctx-pass-handled"],
        }
        rec = report.fixture_result_record(
            f, response, "pass", "PASS", None, "test-adapter", 12.3
        )
        serialized = json.dumps(rec, sort_keys=True)
        parsed = json.loads(serialized)
        self.assertEqual(parsed["id"], f.id)
        self.assertEqual(parsed["status"], "pass")
        self.assertEqual(parsed["observed_verdict"], "PASS")

    def test_summary_record_partitions_by_source_and_evidence(self):
        records = [
            {"kind": "fixture-result", "status": "pass", "source_shape": "multica", "evidence": "runtime"},
            {"kind": "fixture-result", "status": "fail", "source_shape": "discord", "evidence": "runtime"},
            {"kind": "fixture-result", "status": "fail", "source_shape": "discord", "evidence": "predicted"},
        ]
        summary = report.summary_record(records, duration_ms=100.0, adapter_name="x")
        self.assertEqual(summary["fixture_count"], 3)
        self.assertEqual(summary["pass_count"], 1)
        self.assertEqual(summary["fail_count"], 2)
        self.assertEqual(summary["by_source_shape"]["discord"]["fail"], 2)
        self.assertEqual(summary["by_evidence"]["predicted"]["fail"], 1)


class RunnerEndToEndTests(unittest.TestCase):
    """Full runner.main invocations over the bundled fixtures.

    These cover every fixture with the in-process adapter, so they inject a
    single deterministic provider result. context_checked is empty because it
    must be a valid reference subset for every fixture envelope at once; the
    empty list is the only universally valid value.
    """

    def setUp(self):
        patcher = mock.patch.dict(os.environ, provider_env("PASS", checked=[]))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_determinism_two_in_process_runs_byte_identical(self):
        """FR-015: two consecutive runs produce byte-identical JSONL output."""
        argv = ["--adapter", "in-process", "--format", "jsonl", "--deterministic-time"]
        exit1, out1 = _run_main_capturing_stdout(argv)
        exit2, out2 = _run_main_capturing_stdout(argv)
        self.assertEqual(exit1, exit2)
        self.assertEqual(out1, out2)

    def test_source_filter_union_equals_unfiltered_run(self):
        """FR-019: unioned --source runs match the unfiltered run per-fixture."""
        _, out = _run_main_capturing_stdout(
            ["--adapter", "in-process", "--format", "jsonl", "--deterministic-time"]
        )
        all_lines = [l for l in out.splitlines() if '"kind": "fixture-result"' in l]
        all_ids = {json.loads(l)["id"] for l in all_lines}

        union = set()
        for source in ("multica", "discord", "contract"):
            with self.subTest(source=source):
                _, out = _run_main_capturing_stdout([
                    "--adapter", "in-process",
                    "--format", "jsonl",
                    "--source", source,
                    "--deterministic-time",
                ])
                for l in out.splitlines():
                    if '"kind": "fixture-result"' in l:
                        union.add(json.loads(l)["id"])
        self.assertEqual(union, all_ids)


if __name__ == "__main__":
    unittest.main()
