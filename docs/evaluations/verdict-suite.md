# V2 lifecycle conformance

This entry point calls `nunchi.conformance` to check the current core pipeline
with fixed inputs and model results. It does not run a conversation or measure
social behavior. The pipeline itself remains under
[architecture review](../../AGENTS.md#architecture-goal-and-current-gap).

The [approved scenes](scenes/README.md) await evaluation design. The unrelated
V1 fixture corpus and old conversation runners have been removed; Git retains
them.

## Run

```sh
python3 -m evals.verdict_suite.runner --list
python3 -m evals.verdict_suite.runner
python3 -m evals.verdict_suite.runner --format jsonl
```

The nine checks cover suppression, a nod recommendation, wake with
contribution or silence, model defer, margin defer, trusted bypass, wake on
error and no-wake error handling. `--list` prints the current set. These checks
need no provider or network.

Exit code `0` means every scenario passed. JSONL output is one object per
scenario with `scenario`, `status`, `expected`, and `observed`; there is no
summary line. `--scenario NAME` runs one scenario.

## Full deterministic verification

```sh
python3 -m unittest
python3 -m evals.verdict_suite.runner --list
python3 -m evals.verdict_suite.runner
```

See [current runtime components](../platform.md) for implementation details.

Provider-backed and real-room runs are separate, attributable evidence. They
must identify the exact installed artifact, participant, route, model, and
native result; an offline conformance pass does not establish live behavior.
