# Phase 20 convergence — scanner marker bypass

**Date**: 2026-07-19
**Slice**: `020-v2-observation`
**Owner-review object**: `cd8917c56f0d051f52cdba68c177d45e7a9f1103`
**Status**: REJECTED AS FINAL CANDIDATE TARGET; remediation active

## Finding S020-A8-01 — HIGH evidence-integrity bypass

The committed static scanner defines a globally recognized
`slice020-secret-fixture` marker and skips every added line containing that
text before applying any matcher. The skip is not path-restricted and does not
prove that a line is synthetic test data. A production, evaluation, or evidence
line can therefore carry a real matched secret plus the marker and receive a
clean result.

Pinned RED probe against `cd8917c`:

```text
{'marker_bypass_findings': 0, 'expected': 1, 'red': True}
```

The probe constructed an OpenAI-style key at runtime and placed it in an added
`src/nunchi/observation.py` assignment with the marker. The scanner returned no
findings.

This invalidates the claim that every scoped added line is checked by the four
committed matchers. The prior whole-slice CLEAN receipt remains an accurate
result of that implementation, but its scanner was bypassable and therefore
cannot authorize handoff.

## Required correction

1. Remove the fixture-marker exemption from runtime scanner logic.
2. Construct synthetic scanner-test keys dynamically so no full matched token
   appears as an added repository line.
3. Add a regression proving marker text does not suppress a finding.
4. Rerun scanner unit tests, Ruff, Bandit, governance, the complete repository
   matrix, and an exact whole-slice scan against a new immutable object.
5. Obtain a fresh independent review of that exact new object.

## Lifecycle effect

`cd8917c` remains immutable review input only. It is not candidate attempt 2,
`CONVERGED`, `HANDOFF_READY`, accepted, integrated, deployed, released,
promoted, or cut over. T103 remains open; T104–T107 bind this correction.
