# Contract: Admission Classifier Selection

## Public CLI

Command:

```sh
turnaware admit [--classifier PATH] [--classifier-config JSON_OR_PATH] [--input PATH]
```

Input may still be read from stdin or `--input PATH`. This slice supports one classifier path: the documented product/default classifier path, `product`. The product/default path is backed by a configured OpenAI-compatible provider/model. Deterministic offline/CI evidence is implemented through a fixture provider behind the product path, not through a selectable `deterministic` classifier. Classifier selection may be supplied by CLI flags and/or envelope fields; if both are present, the CLI `--classifier` flag takes precedence over the envelope `classifier` field. If the product/default path or provider configuration is unavailable, TurnAware fails clearly rather than silently falling back to local or deterministic behavior.

### Successful stdout payload

Successful evaluations write JSON to stdout and exit 0:

```json
{
  "classifier": "product",
  "classifier_provider": "openai-compatible",
  "classifier_model": "<configured-model>",
  "verdict": "SPEAK",
  "confidences": {
    "PASS": 0.05,
    "ACK": 0.10,
    "ASK": 0.10,
    "SPEAK": 0.75
  },
  "context_checked": ["trigger:root", "context:assignment"],
  "reasons": ["Assignment context asks this agent to perform substantive work."],
  "request_id": "optional-correlation-id"
}
```

Required invariants:
- `classifier` is present for every successful result.
- `classifier_provider` and `classifier_model` identify the provider/model used for every successful result.
- `verdict` is exactly one of PASS, ACK, ASK, SPEAK.
- `confidences` includes all four verdict keys.
- `context_checked` references only inspected supplied trigger/context material.
- No successful result contains reply prose or draft-message fields.

### Failure semantics

Invalid or unavailable classifier/provider configuration must:
- write a clear error to stderr,
- exit non-zero,
- produce no successful admission result on stdout,
- avoid silently evaluating with a different classifier.

## Callable Core

The core callable remains the implementation boundary used by CLI and tests:

```python
from turnaware.core import evaluate

result = evaluate(request)
```

The callable core must accept the same classifier/provider configuration semantics as the CLI after parsing and must return a contract-equivalent result for the same valid envelope.

## Required classifier evidence

The product classifier path must support auditable admission results for supplied envelopes. Deterministic provider-fixture verification must cover:
- known false ACK: `comment back with results` assignment -> `SPEAK`, not `ACK`;
- known false PASS: resolved/no-response trigger with contradictory missing-work context -> non-PASS with contradiction checked;
- representative PASS, ACK, ASK, SPEAK;
- invalid classifier configuration -> clear failure/no fallback;
- public CLI/core contract equivalence over the fixture set.

## Out of scope for this contract

- Reply composition, suggested message text, or final room-message content.
- Discord/cc-connect or other adapter implementation.
- Broad benchmark claims or launch/marketing copy.
- Exposing deterministic/offline fixture behavior as a public classifier path.
