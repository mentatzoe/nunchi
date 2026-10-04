# V2 lifecycle conformance

The repository-owned evaluation entry point exercises the installed V2
lifecycle plumbing. It does not judge social quality: whether an agent reads
the room well needs behavioral evaluation across realistic multi-turn
conversations, which is not built yet
([#86](https://github.com/mentatzoe/nunchi/issues/86)). The V1 fixtures under
`evals/verdict_suite/fixtures/` are kept as seed material for that work. They
are not an executable product path and this runner does not use them.

## Run

```sh
python3 -m evals.verdict_suite.runner --list
python3 -m evals.verdict_suite.runner
python3 -m evals.verdict_suite.runner --format jsonl
```

The eleven deterministic scenarios cover SUPPRESS; ACK, plus disabled and
unsupported ACK widening to DEFER; WAKE with contribution; WAKE with silence;
classifier DEFER; margin DEFER; trusted bypass; wake-on-error; and explicit
no-wake error handling. `--list` prints the authoritative set. They use the
same public V2 pipeline as installed adapters, with a scripted model, and
require no provider or network.

Exit code `0` means every scenario passed. JSONL output is one object per
scenario with `scenario`, `status`, `expected`, and `observed`; there is no
summary line. `--scenario NAME` runs one scenario.

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
