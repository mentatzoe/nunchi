# Nunchi V2 integration

Use [the platform interface](platform-v2.md). Integrations do not implement a
second gate.

A draft contract that replaces the paths below, so every harness gets the
same behavior, is in [`harness-contract.md`](harness-contract.md) (#94 step
9a, for review).

Every integration constructs one exact `ParticipantBinding`, retains native
observations through `ObservationProvider`, runs `AttentionEngine` with that
participant's pinned profile and delegated model, and schedules with
`ConversationOpportunityScheduler`. It then takes one of two paths for the
participant turn.

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

Some hosts run their own participant pipeline, as Hermes does today. They do
not use `ParticipantTurnHost`, so they miss the behaviors the shared turn
carries (memory, catching up, looking again, steering). That gap is a design
problem, not the intended shape: see "One library, every harness" in
[`AGENTS.md`](../AGENTS.md) and step 9 of
[#94](https://github.com/mentatzoe/nunchi/issues/94), which replaces this path
with a plugin on Hermes's public hooks. Instead they wrap their own turn with the shared
owners: observation, attention, the scheduler, shared opportunity preparation
and wake facts (`nunchi.pipeline.prepare_opportunity`), and shared receipts (`participant_host_receipt_body`). Nunchi decides before the
host starts visible work, hands an admitted turn the bounded wake facts, and
records the lifecycle facts the host exposes. The host keeps its own prompt,
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
