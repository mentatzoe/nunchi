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
import re
import shutil
import sys
import tempfile
import types
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


def _inject_provider_result(
    verdict: str, checked: list[str], confidences: dict[str, float] | None = None
):
    """patch.dict context manager injecting a deterministic classifier result.

    The injected payload is what `turnaware.core.evaluate` (and the CLI)
    return instead of calling a live provider, keeping self-tests offline.
    """
    return mock.patch.dict(
        os.environ, provider_env(verdict, checked=checked, confidences=confidences)
    )


def _envelope_refs(envelope: dict) -> list[str]:
    """All reference ids derivable from a fixture envelope (trigger + context)."""
    refs = [f"trigger:{envelope['trigger']['id']}"]
    refs.extend(f"context:{item['id']}" for item in envelope.get("context", []))
    return refs


def _invariant_clean_injection(fixture, verdict: str):
    """Injection that satisfies every declared structural invariant by
    construction: context_checked names the trigger and every context item
    (FR-007), and the winner confidence sits below the 0.85 baseline
    (FR-008) — so corpus statuses are driven by verdict comparison alone."""
    confidences = {v: 0.05 for v in ("PASS", "ACK", "ASK", "SPEAK")}
    confidences[verdict] = 0.8
    return _inject_provider_result(
        verdict, checked=_envelope_refs(fixture.envelope), confidences=confidences
    )


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


def _expected_status_for_injection(fixture, injected_verdict: str) -> str:
    """Mirror runner scoring for a fixture under an invariant-clean injection.

    Derived from fixture metadata (semantic ground truth), not from any
    historical classifier: the injected verdict scores `pass` iff it is in
    the fixture's expected set, or the fixture carries the FR-006
    negative-control marker (the clean injection pins the winner at 0.8,
    below the 0.85 baseline, so FR-006's low-confidence branch always
    accepts). Declared FR-005/FR-007/FR-008 invariants are satisfied by
    construction in `_invariant_clean_injection`, so they never flip the
    status here; `InvariantDispatchTests` covers the violating paths.
    """
    if injected_verdict in fixture.expected_verdicts:
        return "pass"
    if "FR-006" in fixture.fr_refs:
        return "pass"
    return "fail"


class FixtureCorpusEndToEndTests(unittest.TestCase):
    """T018/T030: run the real fixture corpus through the InProcessAdapter.

    The classifier under test is provider-backed, so a single deterministic
    verdict is injected per run and every fixture's pass/fail status is
    checked against what its own metadata says that injection must score.
    Fixture counts are discovered at runtime — adding fixtures must not
    break these tests.
    """

    def _run_pool(self, source: str, injected_verdict: str):
        fixtures = loader.discover_fixtures(FIXTURES_ROOT, source=source)
        self.assertGreater(len(fixtures), 0)
        adapter = adapters.InProcessAdapter()
        results = {}
        for f in fixtures:
            with self.subTest(fixture=f.id):
                with _invariant_clean_injection(f, injected_verdict):
                    response, status, observed, detail = runner._run_one_fixture(
                        f, adapter, deterministic_time=True
                    )
                    # (a) every fixture yields a well-formed report record with
                    # a definitive status — no adapter/classifier errors.
                    self.assertIn(status, ("pass", "fail"))
                    rec = report.fixture_result_record(
                        f, response, status, observed, detail, adapter.name, 0.0
                    )
                    self.assertEqual(rec["id"], f.id)
                    self.assertEqual(rec["status"], status)
                    # (b) status matches the metadata-derived expectation,
                    # except mock/contract-driven fixtures whose outcome is
                    # driven by mock_adapter_output rather than the injection.
                    if not (
                        f.surface_contract == "typed-verdict"
                        and f.mock_adapter_output is not None
                    ):
                        self.assertEqual(
                            status, _expected_status_for_injection(f, injected_verdict)
                        )
                        if status == "fail":
                            self.assertEqual(observed, injected_verdict)
                    results[f.id] = status
        return results

    def test_us1_multica_fixtures_load_and_run(self):
        """T018: all multica fixtures run end-to-end; spot-check known cases."""
        results = self._run_pool("multica", "SPEAK")
        # Substring-trap fixture expects SPEAK: the injected SPEAK must pass.
        self.assertEqual(results["m-substring-trap-back-results"], "pass")
        self.assertEqual(results["m-baseline-speak-assigned"], "pass")
        # Fake-done fixture expects a non-PASS verdict (SPEAK|ASK): pass too.
        self.assertEqual(results["m-trigger-only-pass-fake-done"], "pass")
        # PASS-only baseline must score fail when the verdict contradicts it.
        self.assertEqual(results["m-baseline-pass-adapter-resolved"], "fail")
        # ...and injecting the expected verdict flips it to pass.
        flipped = self._run_pool("multica", "PASS")
        self.assertEqual(flipped["m-baseline-pass-adapter-resolved"], "pass")
        self.assertEqual(flipped["m-substring-trap-back-results"], "fail")

    def test_us3_discord_fixtures_load_and_run(self):
        """T030: all discord fixtures (FR-018) run; suppressor four (FR-021)
        fail when the injected verdict contradicts their expected PASS."""
        fixtures = loader.discover_fixtures(FIXTURES_ROOT, source="discord")
        fr018 = [f for f in fixtures if "FR-018" in f.fr_refs]
        self.assertGreater(len(fr018), 0)
        suppressors = {
            "d-suppressor-self-caused",
            "d-suppressor-stale",
            "d-suppressor-duplicate",
            "d-suppressor-covered",
        }
        by_id = {f.id: f for f in fixtures}
        self.assertLessEqual(suppressors, set(by_id))
        # All four suppressor fixtures declare expected PASS in metadata —
        # the assertion below is derived from that, not from a132ccc lore.
        for sid in suppressors:
            self.assertEqual(by_id[sid].expected_verdicts, ("PASS",))

        results = self._run_pool("discord", "SPEAK")
        for sid in sorted(suppressors):
            with self.subTest(suppressor=sid):
                self.assertEqual(results[sid], "fail")


class InvariantDispatchTests(unittest.TestCase):
    """The runner must fail a fixture whose declared structural invariant is
    violated even when the observed verdict matches the expected set."""

    @classmethod
    def setUpClass(cls):
        cls.by_id = {f.id: f for f in loader.discover_fixtures(FIXTURES_ROOT)}

    def _run(self, fixture, verdict: str, *, checked, confidences):
        adapter = adapters.InProcessAdapter()
        with _inject_provider_result(verdict, checked=checked, confidences=confidences):
            return runner._run_one_fixture(fixture, adapter, deterministic_time=True)

    @staticmethod
    def _confidences(winner: str, level: float) -> dict[str, float]:
        confidences = {v: 0.05 for v in ("PASS", "ACK", "ASK", "SPEAK")}
        confidences[winner] = level
        return confidences

    def test_fr007_incomplete_context_checked_fails(self):
        fixture = self.by_id["m-contradiction-audit-both-listed"]
        verdict = fixture.expected_verdicts[0]
        refs = _envelope_refs(fixture.envelope)
        confidences = self._confidences(verdict, 0.8)
        # Trigger-only audit omits the consulted context item: invariant fails
        # even though the verdict matches the expected set.
        _, status, _, detail = self._run(
            fixture, verdict, checked=refs[:1], confidences=confidences
        )
        self.assertEqual(status, "fail")
        self.assertIn("FR-007", detail)
        # A complete audit passes.
        _, status, _, _ = self._run(fixture, verdict, checked=refs, confidences=confidences)
        self.assertEqual(status, "pass")

    def test_fr008_baseline_confidence_fails(self):
        fixture = self.by_id["m-constant-confidence-mixed-support"]
        verdict = fixture.expected_verdicts[0]
        refs = _envelope_refs(fixture.envelope)
        # Winner pinned at the 0.85 clean baseline despite mixed support:
        # the confidence-is-informative invariant fails.
        _, status, _, detail = self._run(
            fixture, verdict, checked=refs, confidences=self._confidences(verdict, 0.85)
        )
        self.assertEqual(status, "fail")
        self.assertIn("FR-008", detail)
        # A sub-baseline winner passes.
        _, status, _, _ = self._run(
            fixture, verdict, checked=refs, confidences=self._confidences(verdict, 0.6)
        )
        self.assertEqual(status, "pass")

    def test_fr005_pass_without_context_fails(self):
        # No corpus fixture both expects PASS and has empty context (that
        # combination is exactly what FR-005 forbids), so dispatch is
        # exercised on a synthetic fixture borrowing a real empty-context
        # envelope.
        base = self.by_id["m-trigger-only-pass-empty-context"]
        fixture = types.SimpleNamespace(
            id="synthetic-fr005-dispatch",
            surface_contract=None,
            mock_adapter_output=None,
            expected_verdicts=("PASS",),
            fr_refs=("FR-005",),
            failure_mode="synthetic FR-005 dispatch check",
            envelope=base.envelope,
        )
        _, status, _, detail = self._run(
            fixture,
            "PASS",
            checked=_envelope_refs(base.envelope),
            confidences=self._confidences("PASS", 0.8),
        )
        self.assertEqual(status, "fail")
        self.assertIn("FR-005", detail)


class FormatParityTests(unittest.TestCase):
    """T036 / FR-013: jsonl and text reports agree fixture-by-fixture."""

    def setUp(self):
        patcher = mock.patch.dict(os.environ, provider_env("PASS", checked=[]))
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _statuses_from_jsonl(out: str) -> dict[str, str]:
        statuses = {}
        for line in out.splitlines():
            if '"kind": "fixture-result"' in line:
                rec = json.loads(line)
                statuses[rec["id"]] = rec["status"]
        return statuses

    @staticmethod
    def _statuses_from_text(out: str) -> dict[str, str]:
        pattern = re.compile(
            r"^\s*(PASS|FAIL|ERROR)\s+\[(?:runtime|predicted)\]\s+\S+\s+(\S+)\s+expected="
        )
        statuses = {}
        for line in out.splitlines():
            m = pattern.match(line)
            if m:
                statuses[m.group(2)] = m.group(1).lower()
        return statuses

    def test_us2_format_parity(self):
        base = ["--adapter", "in-process", "--deterministic-time"]
        exit_jsonl, out_jsonl = _run_main_capturing_stdout([*base, "--format", "jsonl"])
        exit_text, out_text = _run_main_capturing_stdout([*base, "--format", "text"])
        self.assertEqual(exit_jsonl, exit_text)
        jsonl_statuses = self._statuses_from_jsonl(out_jsonl)
        text_statuses = self._statuses_from_text(out_text)
        self.assertGreater(len(jsonl_statuses), 0)
        self.assertEqual(set(jsonl_statuses), set(text_statuses))
        for fixture_id, status in jsonl_statuses.items():
            with self.subTest(fixture=fixture_id):
                self.assertEqual(text_statuses[fixture_id], status)


class AddFixtureNoRunnerChangeTests(unittest.TestCase):
    """T039 / US4: a brand-new fixture pair dropped into a --fixtures-root
    directory is discovered, run, and scored from its metadata alone — with
    zero changes to runner.py, adapters.py, loader.py, or report.py."""

    TEMP_ID = "t-us4-fresh-fixture-speak"

    def _make_temp_fixtures_root(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="turnaware-003-us4-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        # Copy the schema of a real fixture pair, re-identified as a fresh case.
        src_env = FIXTURES_ROOT / "multica" / "m-baseline-speak-assigned.json"
        src_meta = FIXTURES_ROOT / "multica" / "m-baseline-speak-assigned.meta.json"
        envelope = json.loads(src_env.read_text(encoding="utf-8"))
        meta = json.loads(src_meta.read_text(encoding="utf-8"))
        envelope["request_id"] = "fixture-" + self.TEMP_ID
        meta["id"] = self.TEMP_ID
        meta["title"] = "US4 fresh fixture — added without touching the runner"
        pool = tmp / "multica"
        pool.mkdir()
        (pool / f"{self.TEMP_ID}.json").write_text(
            json.dumps(envelope, indent=2), encoding="utf-8"
        )
        (pool / f"{self.TEMP_ID}.meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        self.expected_verdicts = tuple(
            [meta["expected"]["verdict"]]
            if isinstance(meta["expected"]["verdict"], str)
            else meta["expected"]["verdict"]
        )
        return tmp

    def _run_against(self, fixtures_root: Path, injected_verdict: str):
        argv = [
            "--adapter", "in-process",
            "--format", "jsonl",
            "--deterministic-time",
            "--fixtures-root", str(fixtures_root),
        ]
        with _inject_provider_result(injected_verdict, checked=[]):
            exit_code, out = _run_main_capturing_stdout(argv)
        records = [json.loads(l) for l in out.splitlines() if l.strip()]
        fixture_records = [r for r in records if r["kind"] == "fixture-result"]
        summary = next(r for r in records if r["kind"] == "summary")
        return exit_code, fixture_records, summary

    def test_us4_add_fixture_no_runner_change(self):
        root = self._make_temp_fixtures_root()

        # Injecting the metadata's expected verdict: the fresh fixture passes.
        matching = self.expected_verdicts[0]
        exit_code, fixture_records, summary = self._run_against(root, matching)
        self.assertEqual(summary["fixture_count"], 1)
        self.assertEqual(exit_code, 0)
        rec = fixture_records[0]
        self.assertEqual(rec["id"], self.TEMP_ID)
        self.assertEqual(rec["status"], "pass")
        self.assertEqual(rec["observed_verdict"], matching)
        self.assertEqual(rec["expected_verdict"], list(self.expected_verdicts))

        # Injecting a contradicting verdict: same fixture, metadata-driven fail.
        contradicting = next(
            v for v in ("PASS", "ACK", "ASK", "SPEAK") if v not in self.expected_verdicts
        )
        exit_code, fixture_records, summary = self._run_against(root, contradicting)
        self.assertEqual(exit_code, 1)
        self.assertEqual(fixture_records[0]["id"], self.TEMP_ID)
        self.assertEqual(fixture_records[0]["status"], "fail")
        self.assertEqual(summary["fail_count"], 1)


if __name__ == "__main__":
    unittest.main()
