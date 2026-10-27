# Current runtime components

**Implementation reference, under architecture review.** No Claude Code,
Codex or Hermes integration is currently supplied. This page describes the
shared code that remains, including the turn ownership that still needs to
change. It is not a recipe for rebuilding the removed integrations.

The [agreed goal](../AGENTS.md#architecture-goal-and-current-gap) leaves agent
lifecycle and turns with the harness, communication with the agent, and
channel choice with the user. Context and social attention belong in core.

## Components

| Component | Current responsibility | Source |
|---|---|---|
| Observation | Retain events and actor facts; build bounded context with honest coverage | [`observation.py`](../src/nunchi/observation.py) |
| Attention | Ask the participant's delegated model to read the room; validate its answers | [`attention.py`](../src/nunchi/attention.py) |
| Conversation memory | Record moves and message relationships | [`memory.py`](../src/nunchi/memory.py) |
| Room (obsolete) | Assemble observation, attention, scheduling, authorization and a participant host | [`room.py`](../src/nunchi/room.py) |
| Participant host and turn (obsolete) | Invoke a participant, mediate room actions and record the outcome | [`participant.py`](../src/nunchi/participant.py), [`turn.py`](../src/nunchi/turn.py) |
| Transport | Supply authenticated events; in the obsolete design, also send for the participant | [Reference adapters](adapters.md), [Discord MCP](../integrations/mcp-discord/README.md) |

`Room`, the participant host and the turn protocol are coupled to
library-owned execution. Reference adapters construct a plain model
participant through this machinery.

## Inputs and configuration

The existing runtime uses a `ParticipantBinding` for the exact participant,
actor, platform, room and continuity scope, plus a matching pinned
`ParticipantProfile`. It receives an attention provider, participant,
transport, state paths and optional authorization policy.

`RoomSettings` reads the shared configuration sections: `binding`, `profile`,
`attention`, limits, state directory and optional authorization. Configuration
is trusted input; room content cannot replace identity, provider routes,
credentials or policy. See [data contracts](contracts/nunchi.md) for the field
definitions.

There is no implemented replacement harness interface yet. The architecture
review must decide which current capabilities can be consumed independently
without taking over the agent.

## Model connections

`attention_model_from_config(config, host_kinds=...)` selects a provider by
`kind`. Provider and model names are labels, but protocol separation is still
incomplete: the Chat Completions client lives in core (`attention.py`). The
other provider API routes live in adapters.

| Route | Configuration and behavior |
|---|---|
| `openai-compatible` | Default kind; requires `base_url`, supports `temperature` and `extra_body` |
| `decisions-api` | Registered by reference adapters; a typed decision model, with optional explicit `url` |
| `messages-api` | Explicit `base_url`; Messages API; `auth` is `x-api-key` or `bearer` |
| `responses-api` | Explicit `base_url`; Responses API; asks the provider not to store the response |
| Host text completion | `HostTextAttentionModel` wraps `complete(system, prompt, timeout_seconds)` |
| Host structured completion | `HostStructuredAttentionModel` wraps structured output and a host-specific permission-denial check |

Messages and Responses routes accept model, credential-variable name,
`temperature`, `effort`, `max_tokens` and `extra_body`. Provider responses are
available as `last_response` for usage/model auditing. Host adapters must state
whether they can attest which model was served; a missing model label is not
invented. Unknown kinds and malformed answers fail explicitly.

Chat and typed providers answer the same two attention steps. Their context
is not yet identical: the typed attention-state builder omits conversation
memory that the chat prompt includes. Treat that as an implementation gap
when comparing providers.

## Room context

Observation retains events independently of the context window sent to a
model. Limits cover events, age and bytes, including actor metadata.
Coverage records gaps and unknown visibility. Keeping these facts in core is
intentional; complete context CRUD and prompt configuration remain unfinished.

The existing `RoomView` reads retained messages in four directions:
`before`, `after`, `around` and `new`. Pages omit internal handles and cursors,
state their limits and identify missing history. Reaching a page limit returns
a note rather than silently pretending the room is complete.

A continuation handle is a separate host-only capability for bounded context
fetches. It is bound to a participant, room, scope and trigger, expires, and is
discarded on restart. The [contract reference](contracts/nunchi.md#more-context)
describes its validation.

## Code that runs the agent's turn

`room.py`, `pipeline.py`, `participant.py`, `participant_model.py`,
`turn.py`, `turn_server.py`, `turn_conformance.py`, `reactions.py` and
`conformance.py` schedule turns, start the participant, give it room tools,
send for it, and check that behavior. They are marked obsolete: the
architecture goal leaves turns and sending with the agent and its harness.
They stay until the review decides what replaces them; do not extend them
or treat their protocols as interfaces to keep.

## Check these components

```sh
python3 -m unittest discover -s tests/v2/contract -p 'test_*.py'
python3 -m unittest tests.v2.test_shared_foundation tests.v2.test_runtime_hardening tests.v2.test_agnostic_core
python3 -m evals.verdict_suite.runner
```

These are implementation checks. Installed-package checks and realistic
behavioral evaluation establish different things and must be reported
separately. The [approved scenes](evaluations/scenes/README.md) do not become
executed evaluations by passing these tests.
