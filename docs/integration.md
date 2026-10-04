# Nunchi V2 integration

Use [the platform interface](platform-v2.md). Integrations do not implement a
second gate.

The host constructs one exact `ParticipantBinding`, retains native observations
through `ObservationProvider`, runs `AttentionEngine` with that participant's
pinned profile and delegated model, schedules with
`ConversationOpportunityScheduler`, and invokes the normal participant through
`ParticipantTurnHost`.

The participant returns one ordinary room action, one privileged proposal, or
silence. The host validates origin visibility and current opportunity state.
Ordinary output crosses one transport commit point. Privileged effects cross
the same cancellation boundary and then the execution-time authorization
coordinator.

Integrations must never:

- infer self from names, aliases, roles, or room text;
- translate V1 envelopes or consume PASS/ACK/ASK/SPEAK as lifecycle control;
- treat events as reply obligations or queue every event as work;
- expose continuation handles, cursors, binding material, secrets, or approval
  challenges to the participant model;
- let a participant call native room tools around the host;
- classify composed output socially at send time;
- revive pending work or approvals after restart.

The generic reference runtime in `nunchi.adapters.runtime` is the shortest
portable implementation. Codex uses the same owners with a Codex-specific
participant process and the shared Discord transport.
