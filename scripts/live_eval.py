#!/usr/bin/env python3
"""Live drift eval: run the 003 corpus against the configured model and report.

Reads TURNAWARE_CLASSIFIER_MODEL (+ a provider key) from the environment, runs
the verdict-test-suite corpus live, and prints pass/fail/error counts, accuracy
over the model-scored fixtures, and the headline-case pass count. Always exits 0
-- it is a report, not a gate.

Offline dry run (proves parsing without a provider call):
    TURNAWARE_CLASSIFIER_TEST_RESULT='{"verdict":"PASS","confidences":{"PASS":1,"ACK":0,"ASK":0,"SPEAK":0},"context_checked":[],"reasons":["dry"]}' \
      PYTHONPATH=src python3 scripts/live_eval.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNNER = REPO / "specs" / "003-classifier-test-suite" / "contracts" / "runner.py"

# The 7 load-bearing adversarial fixtures (see model-selection evidence).
HEADLINE = {
    "m-substring-trap-back-results",
    "m-trigger-only-pass-fake-done",
    "m-trigger-only-pass-empty-context",
    "d-suppressor-covered",
    "d-suppressor-duplicate",
    "d-mention-recipient-unaddressed",
    "d-named-ask-vigil-unaddressed",
}


def main() -> int:
    model = os.environ.get("TURNAWARE_CLASSIFIER_MODEL", "(unset)")
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", str(REPO / "src"))
    # The runner exits 1 when any fixture fails (expected); we parse its JSONL
    # regardless of exit code.
    proc = subprocess.run(
        [sys.executable, str(RUNNER), "--source", "all", "--format", "jsonl"],
        capture_output=True,
        text=True,
        env=env,
    )

    records = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    # Model-scored fixtures only (contract fixtures use a mock adapter).
    fx = [r for r in records if "status" in r and "id" in r and r.get("source_shape") != "contract"]
    if not fx:
        print("live-eval: no fixture results parsed.", file=sys.stderr)
        if proc.stderr.strip():
            print(proc.stderr.strip()[:2000], file=sys.stderr)
        return 0

    npass = sum(1 for r in fx if r["status"] == "pass")
    nfail = sum(1 for r in fx if r["status"] == "fail")
    nerr = sum(1 for r in fx if r["status"] == "error")
    n = len(fx)
    by_id = {r["id"]: r for r in fx}
    hp = sum(1 for h in HEADLINE if by_id.get(h, {}).get("status") == "pass")
    ht = sum(1 for h in HEADLINE if h in by_id)

    print(f"live-eval  model={model}")
    print(f"  fixtures (model-scored): {n}")
    print(f"  pass/fail/error: {npass}/{nfail}/{nerr}")
    print(f"  accuracy: {100 * npass / n:.1f}%")
    print(f"  headline cases: {hp}/{ht}")
    if nerr:
        print(f"  note: {nerr} adapter/provider errors (timeouts or provider issues)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
