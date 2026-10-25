# Nunchi V2 integration

**Status: current implementation reference, under architecture review.**
The supplied integrations build a `Room` containing observation, attention,
scheduling and a turn host. The [harness contract](harness-contract.md),
[harness guide](harness-guide.md) and [platform reference](platform-v2.md)
describe that code. Library-owned agents and compulsory sending paths are
gaps against the [architecture goal](../AGENTS.md#architecture-goal-and-current-gap).

The two paths below explain existing mechanisms, not choices a new integration
must adopt. Public harness hooks and channel capabilities need to be assessed
against the goal before implementation.

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

The removed Hermes integration wrapped the native host pipeline; the parked
plugin instead injects turns through `Room`, bypassing Hermes's native
thread, session and identity settings. Neither establishes a required shape
for the new integration. The [recorded hook limitations](harness-contract.md#topologies)
are evidence to check against the chosen harness version.

The current [host-owned pipeline interface](platform-v2.md#host-owned-participant-pipelines)
exposes observation, attention, opportunity preparation and receipts. The
architecture review needs to establish which capabilities can be consumed
without taking over the agent's lifecycle or communications.

## Never

Integrations must never:

- infer self from names, aliases, roles, or room text;
- translate V1 envelopes or consume PASS/ACK/ASK/SPEAK as lifecycle control;
- treat events as reply obligations or queue every event as work;
- expose continuation handles, cursors, binding material, secrets, or approval
  challenges to the participant model;
- classify composed output socially at send time;
- revive pending work or approvals after restart.
