# Nunchi stability and versioning contract

This document is the stability promise an integrator can build against. It
states what is part of the public contract, what may change within a major
version, and what is explicitly experimental and may shift in a minor release.

For *how* to wire Nunchi in, see [`integration.md`](integration.md). For the
classifier-quality evidence behind the default model and its known limitations,
see [`../evidence/verdict-suite/`](../evidence/verdict-suite/).
The verdict semantics live in the project [`README.md`](../README.md).

## The public contract

### Request envelope

The admission request is validated by `validate_request` in
`src/nunchi/schema.py` and modeled by `AdmissionRequest` in
`src/nunchi/models.py`. The fields:

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `trigger` | **required** | object | the triggering message |
| `trigger.content` | **required** | non-empty string | the message text |
| `trigger.id` | optional | string | defaults to `"trigger"` |
| `trigger.author` | optional | string | |
| `trigger.timestamp` | optional | string | |
| `context` | optional | list of objects | recent transcript; defaults to empty; ids must be unique |
| `context[].content` | **required** (per item) | non-empty string | |
| `context[].id` | optional | string | defaults to `context-<n>`; must be unique across the list |
| `context[].type` | optional | string | |
| `context[].author` | optional | string | |
| `context[].timestamp` | optional | string | |
| `agent` | optional | object | the agent's identity/role; passed through |
| `agent.aliases` | optional | list of strings | every other identity this one agent answers to (display names, secondary handles, platform mention tokens); entries must be non-empty strings; absent/empty ⇒ behavior identical to an alias-free request |
| `surface` | optional | object | surface descriptor; passed through |
| `request_id` | optional | string | echoed back into the result |
| `classifier` | optional | string | classifier path; the only supported value is `product` |
| `classifier_config` | optional | object | `provider`, `model`, `timeout`; **never** the API key or base URL (operator-env only) |

Only `trigger.content` (and each supplied `context[].content`) is strictly
required. Everything else is optional. The provider endpoint and API key are
deliberately **not** request fields: an untrusted envelope carries
`classifier_config`, so the base URL and key are read exclusively from operator
environment variables (`NUNCHI_CLASSIFIER_BASE_URL` / `OPENAI_BASE_URL`,
`NUNCHI_CLASSIFIER_API_KEY` / `OPENROUTER_API_KEY`). See the README security
note.

### Result / verdict surface

The result is modeled by `AdmissionResult` in `src/nunchi/models.py` and
validated by `validate_result` in `src/nunchi/schema.py`:

| Field | Always present | Type | Notes |
|-------|----------------|------|-------|
| `verdict` | yes | string | exactly one of `PASS`, `ACK`, `ASK`, `SPEAK` (`VERDICTS`) |
| `classifier` | yes | non-empty string | the selected classifier path |
| `confidences` | yes | object | **exactly** the four keys `PASS`, `ACK`, `ASK`, `SPEAK`, each numeric |
| `context_checked` | yes | list of strings | references the classifier actually consulted |
| `reasons` | yes | non-empty list of strings | audit rationale |
| `request_id` | when supplied | string | echoed from the request |
| `classifier_provider` | when known | non-empty string | provider audit field |
| `classifier_model` | when known | non-empty string | model audit field |

`confidences` must contain **all four** verdict keys and no others — `validate_result`
rejects a result that is missing any of `PASS`/`ACK`/`ASK`/`SPEAK` or carries an
extra key. `verdict` is the verdict the host obeys: `PASS` is a hard stop (no
ordinary user-visible room message); `ACK`/`ASK`/`SPEAK` warrant a turn whose
shape the host composes.

#### The forbidden-reply guarantee

Admission results never carry reply prose. The set `FORBIDDEN_REPLY_FIELDS` in
`src/nunchi/models.py` is exactly `{"message", "reply", "draft", "content"}`.
Both `result_to_dict` (`models.py`) and `validate_result` (`schema.py`) reject
any result containing one of these keys. Nunchi decides **admission, not
composition** — it tells the host *whether* and *in what shape* to speak, never
*what* to say. This guarantee is part of the major-version contract.

### CLI exit codes (`nunchi admit`)

Defined in `src/nunchi/errors.py` and used by `src/nunchi/cli.py`:

| Code | Constant | Meaning |
|------|----------|---------|
| `0` | `EXIT_SUCCESS` | successful evaluation; one JSON object written to stdout |
| `1` | `EXIT_RUNTIME` | unexpected runtime failure (e.g. provider/classifier error) |
| `2` | `EXIT_INPUT` | input source or JSON parse failure |
| `3` | `EXIT_VALIDATION` | admission request validation failure |

On success the verdict JSON is written to stdout and the process exits `0`. On
failure a diagnostic is written to stderr and no success verdict is emitted on
stdout.

### Adapter contract (`nunchi.adapters.channel`)

The channel adapter (`src/nunchi/adapters/channel.py`) is transport-neutral.
Its decision is `verdict` + `silent`:

- `verdict` — `PASS` / `ACK` / `ASK` / `SPEAK`.
- `silent` — `True` exactly when `verdict == "PASS"`.

A host branches on these directly: if `silent`, post nothing this turn;
otherwise compose one turn in the returned `run_shape`. The adapter never writes
the reply.

**Suppression-by-token is the host's convention, not Nunchi's.** A transport
that suppresses a send by recognizing a magic final-output string supplies its
own token via `ChannelGateResult.silent_token(token)` (Python) or the CLI's
`--silent-token` flag. Most hosts never need this and just branch on `silent`.

`cc-connect` is a **named preset** of that generic mechanism, with no special
status: the constant `SILENT_PASS_SENTINEL` (`"CC_CONNECT_SILENT_PASS"`), the
`cc_connect_sentinel()` helper, and `--format cc-connect` are all just one
configured value of `silent_token`/`--silent-token`. The core and verdict
surface contain nothing cc-connect-specific.

## SemVer policy

Nunchi follows semantic versioning. The promises below hold **within a major
version** (e.g. across all `1.x`).

### Stable within a major version

These do not change except in a major version bump:

- **The verdict set** is exactly `PASS`, `ACK`, `ASK`, `SPEAK` (`VERDICTS`). No
  verdict is added, removed, or renamed.
- **The result field names** and their meaning: `verdict`, `classifier`,
  `confidences` (always all four verdict keys), `context_checked`, `reasons`,
  and the optional `request_id`, `classifier_provider`, `classifier_model`.
- **The request field names**: `trigger` (+ `content`/`id`/`author`/`timestamp`),
  `context` items, `agent`, `surface`, `request_id`, `classifier`,
  `classifier_config`, and which of them are required vs optional.
- **The CLI exit codes** `0`/`1`/`2`/`3` for `nunchi admit` and their meaning.
- **The forbidden-reply guarantee**: `message`/`reply`/`draft`/`content` never
  appear in a result.
- **The adapter decision contract**: transport-neutral `verdict` + `silent`,
  with `silent == (verdict == "PASS")`.

### What a minor may add

A minor (backward-compatible) release may:

- add **new optional** request fields or result fields (existing integrations
  ignore them);
- add **new `classifier_config` keys** (today: `provider`, `model`, `timeout`);
- add **new adapters** or new adapter output formats (e.g. additional
  `--format`/`--silent-token` presets) without changing the existing ones;
- add new classifier paths beyond `product` (today `product` is the only one).

### Explicitly experimental (may change in a minor)

These are **not** part of the stable contract and may change in any minor:

- **The exact `confidences` values.** The four keys are stable; the numbers are
  a model-derived signal and will shift as the prompt or model evolves. Do not
  threshold on a hard-coded confidence; treat them as relative audit signal.
- **The `reasons` wording.** Reasons are human-readable audit text, not a
  machine contract. Their count, phrasing, and ordering may change. Parse
  `verdict`, not `reasons`.
- **The default model choice.** Today the operator must supply
  `NUNCHI_CLASSIFIER_MODEL`; the *recommended* default
  (`google/gemini-3.1-flash-lite`, chosen by the committed verdict-suite
  bake-off) is a recommendation that may be re-selected in a minor as evidence
  changes. Pin the model in your own env if you need it frozen.
- **The `run_shape` strings** from the adapter (`RUN_SHAPE` in
  `adapters/channel.py`) — guidance prose, not a contract. Branch on `verdict`,
  not on the run-shape text.

## Known limitations

### FR-005: bare resolution claim passes on every tested model

A trigger that asserts completion with **no corroborating context** — the canonical
case is `"Already handled. Resolved. No response needed."` with empty context —
is treated as legitimately PASS-able by **every** model tested in the committed
verdict-suite bake-off, including the selected default. The models treat an
explicit resolution claim as trustworthy rather than something to verify. The
test suite keeps this fixture as semantic ground truth (a bare claim *should* be
verified, not trusted) and records it as an open gap, not a fixture bug. See
[`../evidence/verdict-suite/model-selection-2026-06-13.md`](../evidence/verdict-suite/model-selection-2026-06-13.md).

**Host-side mitigation.** If your surface allows messages that claim a task is
already done/handled/resolved, do not treat a `PASS` on such a trigger as
authoritative. Treat a `PASS` on an unverified-completion trigger as needing
host-side verification (check the referenced work actually happened) before
acting on the silence. The verdict surface gives you `context_checked` and
`reasons` to detect that the classifier consulted no corroborating context.

### Provider-latency variance

Each decision is one provider round-trip; latency varies by model and provider
load (the verdict-suite evidence shows p50 ~1s but p95 spikes, and outright
timeouts for some candidates). For a per-turn gate this matters. Mitigate host-side with
the adapter's `fail_policy` and the per-call timeout:

- `fail_policy="open"` (default) degrades an unavailable gate to `SPEAK` — never
  silently drop a turn.
- `fail_policy="closed"` degrades to `PASS` — favor quiet when noise suppression
  matters more than never missing a turn.
- `fail_policy="raise"` hands the error back to the host.
- `classifier_config.timeout` (default 30s) bounds the wait per call.

A degraded result is flagged as off-surface telemetry (`degraded`, `error` on
`ChannelGateResult`); the failure reason never enters the room. To catch
provider/model drift over time, run the manual live-smoke job
(`.github/workflows/live-smoke.yml`) and the verdict-suite corpus against the
configured model at release time.
