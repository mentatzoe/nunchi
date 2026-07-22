# V1 Contract: Read-the-Room Channel Adapter

**Historical origin**: retired SpecKit feature `004-read-the-room-adapter`

**Created**: 2026-06-13

**Status**: Historical V1 contract (refined by `005`); no live V2-candidate
runtime or entry point implements this contract.

> **Relocated 2026-07-11; retired from the source candidate 2026-07-21:** This
> preserves the published V1 channel-adapter design for release-history and
> regression research. It is not an active SpecKit plan, an installable
> compatibility surface, or a description of the implemented V2 candidate.
> The current `nunchi-channel` command is the closed V2 JSON-lines host in
> [`../adapters-v2.md`](../adapters-v2.md).

> **Historical reconciliation 2026-06-14:** the adapter's default contract was
> made transport-neutral — `gate()` returns `verdict` + `silent`, and the CLI
> prints a JSON directive for every verdict. The `CC_CONNECT_SILENT_PASS`
> sentinel is now opt-in (CLI `--format cc-connect`, or
> `ChannelGateResult.cc_connect_sentinel()`), not the default PASS output, so no
> consumer depends on cc-connect. References below to "emit the sentinel on PASS"
> describe that opt-in mode.

**Tier**: Adapter (Constitution VI). This is the first adapter; it depends on the
core admission contract and never the reverse.

## Why this exists

The V1 core decides admission and `evals/verdict_suite/` measures its quality,
but nothing yet lets a real participant agent *consume* a verdict. The two
sibling surfaces — pilot-bot and peer-coordination/cc-connect — already define
the exact contract a consumer needs:

- pilot-bot `before-you-respond.md` is the human-readable rubric of the same
  PASS/ACK/ASK/SPEAK gate, run channel-locally before any visible output.
- cc-connect `core/message.go` intercepts a literal sentinel
  `CC_CONNECT_SILENT_PASS` as a final response and suppresses the outbound send.

A participant agent therefore needs a bridge that takes its channel-local inputs
(the triggering message, the recent transcript, its own identity), produces a
verdict, and routes it: emit the sentinel on PASS, otherwise hand back a
run-shape the agent fills in. This feature is that bridge.

## Scope

In scope:

- Map a channel-local message shape (cc-connect / pilot-bot style) to a core
  `AdmissionRequest`, preserving the signals the classifier needs: speaker role
  per transcript line (operator / peer / self), the agent's own `id` and
  `mention_id`, and optional channel governance (pinned rules) as context.
- Route the verdict: PASS → emit `CC_CONNECT_SILENT_PASS`; SPEAK/ASK/ACK →
  return a structured run-shape directive (no composed reply).
- A configurable fail policy for classifier failures (open → SPEAK,
  closed → PASS, raise), with the error kept off the conversation surface.
- Two consumption surfaces: an in-process Python API (`gate`, `build_request`)
  and the `nunchi-channel` CLI giving non-Python hosts a JSON-in / JSON-out
  subprocess contract, with an opt-in cc-connect sentinel format.

Out of scope (honest tiering):

- No live Discord connection, no cc-connect process changes, no transport code.
  The adapter produces the sentinel string; an existing cc-connect deployment
  suppresses it unchanged. Wiring it into a running bot is the consumer's step.
- No reply composition. The adapter returns a verdict and a run-shape only.

## User Scenarios

### US1 — Participant agent gates a turn before replying (Priority: P1)

A peer agent (`dalgos`) receives a channel trigger plus recent messages. It
calls the adapter with its identity. On PASS it receives `silent=true` and stays
silent; on SPEAK/ASK/ACK it composes its own turn within the returned run-shape.

**Acceptance**:

1. Given a trigger addressed to another participant, the adapter returns PASS
   and `silent` is true.
2. Given a peer message that already covers the agent's point, the adapter
   returns PASS (Covered) — the agent does not pile on.
3. Given a direct substantive ask, the adapter returns SPEAK and `silent` is
   false, leaving the agent to write the reply.

### US2 — Non-Python host calls the gate as a subprocess (Priority: P2)

A non-Python host shells out to `nunchi-channel` with a JSON payload and reads
one JSON directive from stdout. A cc-connect host may explicitly select the
sentinel compatibility format.

**Acceptance**:

1. A PASS payload prints a JSON directive with `silent=true` and exits 0; with
   `--format cc-connect`, it prints exactly `CC_CONNECT_SILENT_PASS`.
2. A SPEAK payload prints a JSON directive (`verdict`, `run_shape`, `reasons`,
   `confidences`, `context_checked`) and exits 0.
3. A malformed payload exits non-zero with a stderr message and no stdout
   directive.

### US3 — Gate stays safe when the classifier is unavailable (Priority: P2)

If the provider is down or misconfigured, the agent must not be silently
dropped. The default fail-open policy degrades to SPEAK and records the error as
off-surface telemetry; a noise-sensitive deployment may choose fail-closed.

## Requirements

- **FR-001**: Map trigger + transcript + identity (+ optional pinned rules) to a
  valid `AdmissionRequest`; transcript lines carry a normalized role and the
  agent's own lines are tagged `self`.
- **FR-002** (as refined by `005`): PASS routes to a transport-neutral
  `silent=true` decision; the literal `CC_CONNECT_SILENT_PASS` sentinel is an
  opt-in cc-connect compatibility output. Original text:
  PASS routes to the literal `CC_CONNECT_SILENT_PASS` sentinel
  (matching cc-connect `SilentPassSentinel`); SPEAK/ASK/ACK route to a run-shape
  directive carrying no reply prose.
- **FR-003**: The CLI is a stable JSON-in / sentinel-or-JSON-out subprocess
  contract with documented exit codes.
- **FR-004**: Fail policy is configurable (open/closed/raise); classifier errors
  never enter the conversation surface.
- **FR-005**: The core must not import the adapter tier (enforced by test).

## Success Criteria

- **SC-001**: All adapter behavior is covered by offline tests
  (`python3 -m unittest tests.test_adapter_channel`) using a stubbed/fixture
  classifier — no live provider needed for the suite.
- **SC-002**: A committed end-to-end example (`examples/read_the_room_demo.py`)
  runs a realistic multi-turn channel scenario through the live classifier and
  shows the verdict + routing per turn.
- **SC-003**: Documentation (`README` adapter section + this spec) states
  exactly what is implemented vs. left to the consumer (no implicit Discord
  claims).
