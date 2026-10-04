# V2 lifecycle conformance runner

`python3 -m evals.verdict_suite.runner` is a stable compatibility entry point
for the installed V2 conformance runner in `nunchi.conformance`.

It has no V1 classifier adapter, `admit` subprocess, or fixture-driven verdict
fallback. The authoritative scenario list is printed by:

```sh
python3 -m evals.verdict_suite.runner --list
```

The runner is deterministic and offline. It verifies the shared lifecycle
plumbing; provider-backed and real-platform behavior require separately
attributable evidence.
