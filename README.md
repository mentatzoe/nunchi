# TurnAware

Pre-reply judgment for turn-aware agents.

TurnAware is a portable CLI/library for deciding whether an agent should visibly
participate on an unstructured shared surface before ordinary reply generation.
It returns an auditable admission verdict:

- `PASS` — hard stop; no ordinary visible reply
- `ACK` — brief acknowledgement is warranted
- `ASK` — clarification is warranted
- `SPEAK` — substantive contribution is warranted

## Status

The current classifier slice exposes a product/default admission classifier path
and a separate explicit `deterministic` path for offline/CI evidence. Successful
results include the selected classifier identity, verdict, confidence
distribution, checked context, and reasons.

Downstream adapters, live Discord/cc-connect integration, central orchestration,
broad benchmarks, launch claims, and reply composition remain out of scope for
this slice.

## Quickstart

Evaluate a request from stdin through the product/default classifier:

```sh
PYTHONPATH=src python3 -m turnaware admit < tests/fixtures/speak.json
```

Evaluate a request from a file through the deterministic evidence path:

```sh
PYTHONPATH=src python3 -m turnaware admit --classifier deterministic --input tests/fixtures/pass.json
```

Evaluate with classifier selection in the envelope, or override it from the CLI:

```sh
PYTHONPATH=src python3 -m turnaware admit --input tests/fixtures/speak_with_classifier.json
PYTHONPATH=src python3 -m turnaware admit --classifier product --input tests/fixtures/speak_cli_precedence.json
```

Run the verification suite:

```sh
python3 -m unittest
```

## Product contract

The core output contract is:

- `classifier`
- `verdict`
- `confidences`
- `context_checked`
- `reasons`

Successful CLI evaluations write one JSON object to stdout and exit `0`.
Failures write diagnostics to stderr and do not emit a success verdict on
stdout.

Exit codes:

- `0` — successful evaluation
- `1` — unexpected runtime failure
- `2` — input source or JSON parse failure
- `3` — admission request validation failure

TurnAware owns admission, not composition. It does not draft the final reply and
it does not prescribe speech shape beyond the admission verdict.

## Classifier selection

The documented default classifier path is `product`. It is the main admission
classifier path used when no classifier is supplied. In this slice it is backed
by the named local model boundary `turnaware-local-admission-v1`, which scores
competing PASS/ACK/ASK/SPEAK hypotheses over the supplied envelope. It is not a
relabelled deterministic verifier.

`deterministic` is an explicit offline evidence path for local and CI
verification. It is not the product default and is never selected silently as a
fallback for invalid or unavailable product configuration.

Classifier selection can be supplied by:

- envelope field: `"classifier": "deterministic"`
- CLI flag: `--classifier deterministic`

If both are present, the CLI flag takes precedence. Optional
`classifier_config` / `--classifier-config` must be a JSON object. Unsupported
classifier names or config keys fail clearly without emitting a success result.

## Python API

The in-process core is available without shelling out:

```python
import os
import sys
sys.path.insert(0, os.path.abspath("src"))

from turnaware import evaluate

result = evaluate({
    "trigger": {"content": "turnaware-vigil, please implement the CLI MVP."},
    "context": [],
})
```

`result["classifier"]` identifies the selected path and `result["verdict"]` is
one of `PASS`, `ACK`, `ASK`, or `SPEAK`.

## Development method

This repository uses Spec Kit. The constitution at
`.specify/memory/constitution.md` is the source of governance for all specs,
plans, tasks, implementation, documentation, and release claims.

For production work, use:

```text
constitution -> specify -> clarify -> plan -> checklist -> tasks -> analyze -> implement
```

A product spec should prove an end-to-end runnable path from supplied
conversation context to a verdict a harness can obey.

## License

TurnAware is dual-licensed under MIT OR Apache-2.0, at your option. See
`LICENSE-MIT` and `LICENSE-APACHE`.
