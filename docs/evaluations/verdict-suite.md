# V2 lifecycle conformance

The repository-owned evaluation entry point now exercises the installed V2
lifecycle surface. Historical V1 fixture files remain source evidence only;
they are not an executable product path and are not used by this runner.

## Run

```sh
python3 -m evals.verdict_suite.runner --list
python3 -m evals.verdict_suite.runner
python3 -m evals.verdict_suite.runner --format jsonl
```

The eight deterministic scenarios cover SUPPRESS, WAKE with contribution,
WAKE with silence, classifier DEFER, margin DEFER, trusted bypass, wake-on-error,
and explicit no-wake error handling. They use the same public V2 pipeline as
installed adapters and require no provider or network.

Exit code `0` means every scenario passed. JSONL output contains one
`scenario-result` per scenario followed by a `summary`.

## Full deterministic verification

```sh
python3 -m unittest
python3 -m evals.verdict_suite.runner --list
python3 -m evals.verdict_suite.runner
```

For downstream platform requirements and additional native checks, see
[`../platform-v2.md`](../platform-v2.md).

Provider-backed and real-room runs are separate, attributable evidence. They
must identify the exact installed artifact, participant, route, model, and
native result; an offline conformance pass does not establish live behavior.
