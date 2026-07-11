# Contract: TurnAware Admission CLI and Core

> **Historical archive:** superseded product document relocated from retired
> SpecKit feature `001`. Do not use as current integration guidance.

## Command

```text
turnaware admit [--input PATH]
```

- Without `--input`, the command reads one JSON admission request from stdin.
- With `--input PATH`, the command reads one JSON admission request from the named file.
- On success, stdout contains one JSON admission result and the process exits `0`.
- On failure, stderr contains a diagnostic, stdout does not contain a success verdict, and the process exits non-zero.

## Request Object

```json
{
  "request_id": "optional-correlation-id",
  "trigger": {
    "id": "trigger-1",
    "author": "zoe",
    "content": "Can turnaware-vigil take this?"
  },
  "context": [
    {
      "id": "ctx-1",
      "type": "message",
      "author": "peer",
      "content": "I already handled the requested fix."
    }
  ],
  "agent": {
    "id": "turnaware-vigil",
    "role": "developer"
  },
  "surface": {
    "type": "issue-thread"
  }
}
```

### Request Rules

- `trigger.content` is required and must be a non-empty string.
- `context` is optional; when present, it must be a list.
- Each context item must have non-empty string `content`.
- Caller-provided context IDs must be unique.
- Additional fields may be accepted but must not be required for MVP evaluation.

## Success Result Object

```json
{
  "request_id": "optional-correlation-id",
  "verdict": "PASS",
  "confidences": {
    "PASS": 0.82,
    "ACK": 0.06,
    "ASK": 0.04,
    "SPEAK": 0.08
  },
  "context_checked": ["trigger:trigger-1", "context:ctx-1"],
  "reasons": [
    "Supplied context indicates the requested matter is already handled."
  ]
}
```

### Success Rules

- `verdict` is exactly one of `PASS`, `ACK`, `ASK`, `SPEAK`.
- `confidences` contains all four verdict keys with numeric values.
- `context_checked` contains only inspected trigger/context references from the request.
- `reasons` is a non-empty list of audit strings.
- The result never contains `message`, `reply`, `draft`, or final response `content`.

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Successful evaluation |
| `1` | Unexpected runtime failure |
| `2` | Input source or JSON parse failure |
| `3` | Admission request validation failure |

## Internal Core

The internal callable core exposes the same semantic boundary:

```text
evaluate(request) -> admission result
```

The core accepts an already parsed admission request object and returns the same result fields as the CLI. It does not read files, parse command-line arguments, write stdout/stderr, or exit the process.
