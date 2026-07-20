# Codex V2 integration

Codex is a normal room participant behind the shared V2 lifecycle. It does not
receive a V1 verdict or permission to call Discord tools.

```mermaid
sequenceDiagram
    participant Discord
    participant Source as "Discord V2 source"
    participant Runtime as "Shared live-room runtime"
    participant Attention as "Participant-shaped attention"
    participant Codex as "Codex participant"
    participant Transport as "Bound Discord action sink"
    Discord->>Source: "Native message or reaction"
    Source->>Runtime: "Exact IDs and literal relations"
    Runtime->>Attention: "Current bounded facts"
    alt "SUPPRESS"
        Attention-->>Runtime: "Stop wake"
    else "WAKE, DEFER, bypass, or error fallback"
        Runtime->>Codex: "Fresh ParticipantWakeV2"
        Codex-->>Runtime: "Structured action or null"
        Runtime->>Transport: "Request-correlated action"
        Transport-->>Discord: "Send, reply, or react"
    end
```

Codex uses a persistent exact thread for conversational continuity, while the
room scheduler remains ephemeral. After restart, history may be restored as
context, but pending response work is discarded. The output schema permits a
message, a reaction, or silence. It does not permit admission commentary or a
free-form tool call.

See [operator instructions](../operators/v2.md) and the
[security model](../security/v2.md).
