# Lifecycle conformance (obsolete)

This entry point calls `nunchi.conformance`, which checks the obsolete
pipeline that runs participant turns, with fixed inputs and model results. It
does not run a conversation or measure social behavior, and its scenarios
are not requirements for the new design.

The [approved scenes](scenes/README.md) await evaluation design.

## Run

```sh
python3 -m evals.verdict_suite.runner --list
python3 -m evals.verdict_suite.runner
python3 -m evals.verdict_suite.runner --format jsonl
```

`--list` prints the current set. These checks
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
