# Data Model: Core CLI MVP

> **Historical archive:** superseded product document relocated from retired
> SpecKit feature `001`. Do not use as the current public data contract.

## AdmissionRequest

Represents one request to decide whether the current agent should visibly participate.

| Field | Required | Description | Validation |
|-------|----------|-------------|------------|
| `trigger` | Yes | Trigger being evaluated | Must be an object with non-empty `content`; optional `id`, `author`, and `timestamp` |
| `context` | No | Supplied shared-conversation context items | If present, must be a list of objects |
| `agent` | No | Identity or role of the current agent | If present, must be an object |
| `surface` | No | Host or conversation surface metadata | If present, must be an object |
| `request_id` | No | Caller-provided correlation ID | If present, must be a string |

## Trigger

| Field | Required | Description | Validation |
|-------|----------|-------------|------------|
| `content` | Yes | Message or event text to evaluate | Non-empty string |
| `id` | No | Stable trigger identifier | String if supplied; defaults to `trigger` for checked-context references |
| `author` | No | Speaker or source name | String if supplied |
| `timestamp` | No | Caller-provided time reference | String if supplied |

## ContextItem

| Field | Required | Description | Validation |
|-------|----------|-------------|------------|
| `id` | No | Stable context identifier | String if supplied; generated positional reference if absent |
| `type` | No | Context category such as message, issue, handoff, or note | String if supplied |
| `content` | Yes | Context content available to inspect | Non-empty string |
| `author` | No | Context author/source | String if supplied |
| `timestamp` | No | Caller-provided time reference | String if supplied |

Context item IDs must be unique after defaults are assigned. Duplicate caller-provided IDs are validation errors because `context_checked` would otherwise be ambiguous.

## AdmissionResult

| Field | Required | Description | Validation |
|-------|----------|-------------|------------|
| `verdict` | Yes | Admission verdict | Exactly `PASS`, `ACK`, `ASK`, or `SPEAK` |
| `confidences` | Yes | Per-verdict confidence distribution | Contains numeric values for all four verdicts |
| `context_checked` | Yes | References actually inspected | Each value must refer to the trigger or a supplied context item |
| `reasons` | Yes | Audit reasons for the verdict | Non-empty list of strings |
| `request_id` | No | Echoed caller correlation ID | Present only when supplied |

`AdmissionResult` must not contain final reply prose fields such as `message`, `reply`, `draft`, or `content`.

## ErrorResult

Errors are communicated through stderr and non-zero process exit status rather than successful stdout verdict JSON.

| Category | Exit Code | Description |
|----------|-----------|-------------|
| Input error | 2 | Input source is missing, unreadable, or not valid JSON |
| Validation error | 3 | JSON is syntactically valid but not a valid admission request |
| Runtime error | 1 | Unexpected failure during evaluation |

## State Transitions

1. Raw input is read from stdin or a named file.
2. JSON is parsed into an `AdmissionRequest`.
3. Request fields are validated and context item references are normalized.
4. The internal core evaluates the request and records inspected references.
5. The CLI emits either a successful `AdmissionResult` on stdout or a diagnostic on stderr.
