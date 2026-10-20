# Nunchi V2 integration

Use [the platform interface](platform-v2.md). Integrations do not implement a
second gate.

The harness contract in [`harness-contract.md`](harness-contract.md) (#94
step 9, accepted 2026-10-07) replaces the paths below, so every harness gets
the same behavior. Until each replacement passes the conformance kit, the
paths below are what runs.

To build a new integration, follow the [harness guide](harness-guide.md).

Every integration builds the library's side through one `Room`
(`nunchi.room`): the exact `ParticipantBinding`, observation, attention with
the participant's pinned profile and delegated model, the scheduler, and the
turn host. The Hermes plugin builds a `Room` too, and is parked (2026-10-10).
The older Hermes integration wired these itself and was removed on 2026-10-11
(decided). An integration then takes one of two paths for the participant turn.

## Nunchi-owned participant

The host invokes the normal participant through `ParticipantTurnHost`. The
participant returns one ordinary room action, one privileged proposal, or
silence. The host validates origin visibility and current opportunity state.
Ordinary output crosses one transport commit point. Privileged effects cross
the same cancellation boundary and then the execution-time authorization
coordinator.

The generic reference runtime in `nunchi.adapters.runtime` is the shortest
portable implementation. The Codex runner uses the same owners with a
Codex-specific participant process and the shared Discord transport.

A participant can also act through tools inside its own agent loop. The core
renders that turn (`participant_tool_turn_text`) and turns each tool call into
one bound action (`participant_tool_action`, `participant_tool_expansion`).
The Claude Code gate works this way: its participant writes the wake into a
dedicated Claude Code session, and the room tool call it receives back becomes
the action `ParticipantTurnHost` commits. See
[`integrations/claude-code/README.md`](../integrations/claude-code/README.md).

## Native host pipeline

Some hosts run their own participant pipeline, as the older Hermes
integration did (removed on 2026-10-11). They do not use
`ParticipantTurnHost`, so they miss the behaviors the shared turn carries
(memory, catching up, looking again, steering, and telling the agent of a
gap). That gap is a design problem, not the intended shape: see "One library,
every harness" in [`AGENTS.md`](../AGENTS.md) and step 9 of
[#94](https://github.com/mentatzoe/nunchi/issues/94), which replaced this path
with a plugin on Hermes's public hooks. That plugin consumes each message and
starts the turn itself (consume and inject), and it is parked since
2026-10-10; gating the harness's own native turn is the open redesign (the
[harness contract](harness-contract.md#topologies)). Until then, such hosts
wrap their own turn with the shared owners: observation, attention, the
scheduler, shared opportunity preparation and wake facts
(`nunchi.pipeline.prepare_opportunity`), and shared receipts
(`participant_host_receipt_body`). Nunchi decides before the host starts
visible work, hands an admitted turn the bounded wake facts, and records the
lifecycle facts the host exposes. The host keeps its own prompt,
model, tools, and delivery behind Nunchi's guards. See
[Host-owned participant pipelines](platform-v2.md#host-owned-participant-pipelines).

## Never

Integrations must never:

- infer self from names, aliases, roles, or room text;
- translate V1 envelopes or consume PASS/ACK/ASK/SPEAK as lifecycle control;
- treat events as reply obligations or queue every event as work;
- expose continuation handles, cursors, binding material, secrets, or approval
  challenges to the participant model;
- let a participant call native room tools around the host;
- classify composed output socially at send time;
- revive pending work or approvals after restart.
