# Archived V1 verdict corpus

This corpus records the historical PASS/ACK/ASK/SPEAK classifier contract and
its captured evidence. It is not an executable Nunchi V2 gate and must not be
used to claim V2 semantics, model quality, parity, or release readiness.

The fixtures remain listable for provenance and regression research:

```sh
python3 -m evals.verdict_suite.runner --list
python3 -m evals.verdict_suite.runner --list --source discord
```

Any invocation without `--list` exits `2` and directs the operator to
`evals.v2`. The old subprocess and in-process adapters were removed with the V1
runtime, so there is no hidden `nunchi admit` compatibility path.

Use [`v2.md`](v2.md) for deterministic V2 mechanics, repeated stochastic
social evaluation, installed provenance, real-room evidence, and independent
review. Historical schemas remain explicitly labeled V1 under
[`../contracts/`](../contracts/) and captured runs remain under
[`../../evidence/verdict-suite/`](../../evidence/verdict-suite/).
