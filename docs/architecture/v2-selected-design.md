# Nunchi V2 selected-design diagrams

> **Status:** these diagrams describe the selected V2 target from Aleph Vault
> PR 67 (`bdd1ebb`), as clarified by PR 68 (`c834e8c`). The repository still
> implements V1 until the separately authorized Goal 2 performs an atomic
> cutover.

The diagrams are explanatory views of the selected design. Canonical interface
names and slice dependencies come from the V2 program; future machine-readable
contracts belong under `schemas/v2/`, not in this document.

## System boundaries

This view shows where deterministic transport handling stops, where the single
social judgment occurs, and where the participant regains control.

```mermaid
flowchart TB
    Room["Shared conversation"]

    subgraph Observe["Truthful observation"]
        direction TB
        Event["Native event"]
        Native{"Novel, constructable,<br/>and routable?"}
        NonEvent["No wake<br/>exact duplicate or<br/>unroutable event"]
        Provider["I-020A<br/>ObservationProviderV2"]
        Self{"Exact self binding?"}
        SelfEvent["Retain observation<br/>do not wake its author"]
        Request["I-010A<br/>bounded factual context"]
    end

    subgraph Attention["One pre-attention judgment"]
        direction TB
        Engine["I-030A<br/>AttentionEngineV2"]
        Enabled{"Trusted preattention<br/>enabled?"}
        Model["Participant-shaped model"]
        Suppress["SUPPRESS"]
        NoTurn["No participant turn<br/>nothing emitted to room"]
        Wake["WAKE with optional advice"]
        Defer["classifier-DEFER or<br/>margin-DEFER"]
        Bypass["status: bypass<br/>preattention-disabled"]
        Error["Operational ERROR"]
    end

    subgraph Contribution["Normal participant turn"]
        direction TB
        Host["I-040A<br/>ParticipantTurnHostV2"]
        Expand["Optional bounded expansion<br/>host-owned authority"]
        Participant["Participant decides<br/>what to do"]
        Action{"Room action?"}
        Send["Operational send safety<br/>no social reclassification"]
        Silence["Send nothing"]
    end

    Room --> Event
    Event --> Native
    Native -->|"No"| NonEvent
    Native -->|"Yes"| Provider
    Provider --> Self
    Self -->|"Yes"| SelfEvent
    Self -->|"No"| Request
    Request --> Engine
    Engine --> Enabled
    Enabled -->|"No; zero model calls"| Bypass
    Enabled -->|"Yes"| Model
    Model --> Suppress
    Model --> Wake
    Model --> Defer
    Engine --> Error
    Wake --> Host
    Defer --> Host
    Bypass --> Host
    Error -->|"wake by default"| Host
    Suppress --> NoTurn
    Host --> Participant
    Participant -.->|"request more context"| Expand
    Expand -.-> Participant
    Participant --> Action
    Action -->|"Yes"| Send
    Action -->|"No"| Silence
    Send --> Room
```

Only the participant-shaped model can make the social `SUPPRESS` judgment.
Deterministic handling is confined to transport-proven non-events. Trusted
bypass still traverses the engine seam but makes no classifier call and creates
no fabricated model disposition or advice.

## Canonical interface model

These UML-style class views show interface ownership and the separation between
classifier-visible facts, host-only continuation authority, and singly owned
receipt stages.

### Data and service contracts

```mermaid
classDiagram
    direction TB
    class AttentionRequestV2 {
        +ExactSelfBinding exactSelf
        +NativeEvent trigger
        +List~NativeEvent~ context
        +List~ObservedActor~ actors
        +Coverage coverage
        +bool expansionAvailable
    }

    class AttentionDecisionV2 {
        +Status ok_or_bypass
        +Disposition optionalDisposition
        +Advice optionalAdvice
        +BypassCause optionalBypassCause
    }

    class OperationalError {
        +ErrorKind kind
        +String requestId
    }

    class ParticipantWakeV2 {
        +WakeSource source
        +AttentionRequestV2 observation
        +Advice optionalAdvice
    }

    class ContextContinuationV2 {
        +OpaqueHandle hostOnlyHandle
        +BindingToken hostOnlyBinding
        +Cursor hostOnlyCursor
        +Expiry hostOnlyExpiry
        +Coverage returnedCoverage
    }

    class DiscordEventSourceV2 {
        <<I-050A>>
        +observeNativeEvent()
    }
    class ObservationProviderV2 {
        <<I-020A>>
        +buildBoundedObservation()
        +expandContext()
    }
    class AttentionEngineV2 {
        <<I-030A>>
        +judgeAttention()
    }
    class ParticipantTurnHostV2 {
        <<I-040A>>
        +runNormalTurn()
    }

    DiscordEventSourceV2 --> ObservationProviderV2 : supplies native facts
    ObservationProviderV2 --> AttentionRequestV2 : constructs
    ObservationProviderV2 --> ContextContinuationV2 : hosts
    AttentionEngineV2 --> AttentionRequestV2 : consumes projection
    AttentionEngineV2 --> AttentionDecisionV2 : produces
    AttentionEngineV2 --> OperationalError : reports separately
    ParticipantTurnHostV2 --> AttentionDecisionV2 : routes outcome
    ParticipantTurnHostV2 --> ParticipantWakeV2 : delivers
    ParticipantTurnHostV2 --> ContextContinuationV2 : controls authority

```

The classifier projection contains factual coverage and whether expansion is
available. It never receives the continuation handle, binding token, cursor,
expiry, or fetch authority shown on the host side.

### Receipt-stage ownership

```mermaid
classDiagram
    direction TB
    class AttentionReceiptV2 {
        <<interface>>
        +String requestId
        +ReceiptStage stage
        +Owner attestedBy
        +appendOnly()
    }

    class ObservationStage {
        +Owner observationOwner
    }
    class AttentionStage {
        +Owner attentionOwner
    }
    class ParticipantHostStage {
        +Owner participantHostOwner
    }
    class TransportStage {
        +Owner transportOwner
    }

    AttentionReceiptV2 <|-- ObservationStage
    AttentionReceiptV2 <|-- AttentionStage
    AttentionReceiptV2 <|-- ParticipantHostStage
    AttentionReceiptV2 <|-- TransportStage
```

Each stage is immutable and request-correlated. Its named owner appends only
that stage and cannot pre-fill or mutate another owner's facts.

## End-to-end interaction

The normal path and its safety-widening alternatives share one participant
turn. Suppression is the only path that does not wake the participant.

```mermaid
sequenceDiagram
    autonumber
    actor Room as Shared room
    participant Transport as Transport/Event source
    participant Observation as Observation provider
    participant Engine as Attention engine
    participant Model as Participant-shaped model
    participant Host as Participant-turn host
    participant Agent as Participant
    participant Receipts as Off-surface receipts

    Room->>Transport: Native event
    alt Exact duplicate or unroutable event
        Transport->>Receipts: Append only its owned immutable stage
        Transport-->>Room: No participant wake
    else Novel, constructable, routable event
        Transport->>Observation: Native facts and exact self binding
        Observation->>Receipts: Append observation stage
        alt Exact self event
            Observation-->>Room: Retain observation and do not wake its author
        else Wake candidate
            Observation->>Engine: AttentionRequestV2

            alt Trusted preattention disabled
                Note over Engine,Model: I-030A is traversed and Model receives zero calls
                Engine->>Host: status:bypass, preattention-disabled
            else Preattention enabled
                Engine->>Model: Classifier-safe factual projection
                alt Valid model judgment
                    Model-->>Engine: SUPPRESS, WAKE(advice), or classifier-DEFER
                    Engine->>Engine: Apply independent margin-DEFER valve
                    Engine->>Receipts: Append attention stage
                    alt Effective SUPPRESS
                        Engine-->>Host: No wake
                    else WAKE or either DEFER
                        Engine->>Host: ParticipantWakeV2
                    end
                else Validation, provider, runtime, or malformed-result failure
                    Model-->>Engine: Operational failure
                    Engine->>Receipts: Append owned operational record
                    Engine->>Host: ERROR fallback wake
                end
            end

            opt WAKE, DEFER, bypass, or error fallback
                Host->>Agent: Normal room turn with compact factual context
                opt Participant requests bounded expansion
                    Agent->>Host: Expansion request
                    Host->>Observation: Bound continuation request with host-only authority
                    Observation-->>Host: Bounded page and updated coverage
                    Host-->>Agent: Additional factual context
                end
                Agent-->>Host: Room action or silence
                Host->>Receipts: Append participant-host stage
                alt Participant produced a room action
                    Note over Host,Transport: Operational send safety only and no social reclassification
                    Host->>Transport: Action
                    Transport->>Receipts: Append transport stage
                    Transport->>Room: Send action
                else Participant chose silence
                    Host-->>Room: Send nothing
                end
            end
        end
    end
```

## Lifecycle state machine

```mermaid
stateDiagram-v2
    direction TB
    [*] --> NativeEvent
    NativeEvent --> TransportNoWake: exact duplicate or unroutable
    NativeEvent --> Observed: novel, constructable, routable event
    Observed --> SelfNoWake: exact self binding
    Observed --> AttentionEngine: wake candidate
    AttentionEngine --> Bypass: preattention disabled
    AttentionEngine --> ModelJudgment: preattention enabled
    AttentionEngine --> OperationalError: validation, provider, or runtime failure
    ModelJudgment --> Suppressed: SUPPRESS
    ModelJudgment --> ParticipantTurn: WAKE
    ModelJudgment --> ParticipantTurn: classifier-DEFER
    ModelJudgment --> ParticipantTurn: margin-DEFER
    Bypass --> ParticipantTurn: PREATTENTION_BYPASS
    OperationalError --> ParticipantTurn: wake by default
    ParticipantTurn --> ExpandedContext: bounded expansion requested
    ExpandedContext --> ParticipantTurn: factual page returned
    ParticipantTurn --> Sent: participant action
    ParticipantTurn --> Silent: no contribution
    TransportNoWake --> [*]
    SelfNoWake --> [*]
    Suppressed --> [*]
    Sent --> [*]
    Silent --> [*]
```

There is no state for a social handled/open ledger, an obligation queue, an
inferred roster, an admission meta-answer, or a second send-time judgment.

## V2 execution waves

This graph makes the safe parallelism visible. It shows sequencing rather than
repeating every transitive dependency; the program's dependency table remains
normative.

```mermaid
flowchart TB
    subgraph Wave0["Wave 0 — contract"]
        S010["010 · V2 contract<br/>v2-contract-owner"]
    end

    subgraph Wave1["Wave 1 — parallel foundations"]
        S020["020 · Observation<br/>v2-observation-owner"]
        S030["030 · Core attention<br/>v2-core-owner"]
    end

    subgraph Wave2["Wave 2 — host and transport"]
        S040["040 · Participant wake<br/>v2-wake-owner"]
        S050["050 · Discord transport<br/>v2-transport-owner"]
    end

    subgraph Wave3["Wave 3 — parallel surfaces"]
        S060["060 · Hermes<br/>v2-hermes-owner"]
        S070["070 · Claude Code<br/>v2-claude-owner"]
        S080["080 · Codex<br/>v2-codex-owner"]
        S090["090 · Channel adapters<br/>v2-adapters-owner"]
    end

    subgraph Wave4["Wave 4 — blocking assurance"]
        S100["100 · Security and provenance<br/>v2-security-owner"]
    end

    subgraph Wave5["Wave 5 — sole integration sink"]
        S110["110 · Parity and atomic cutover<br/>v2-integrator"]
    end

    S010 --> S020
    S010 --> S030
    S020 --> S040
    S030 --> S040
    S020 --> S050
    S040 --> S060
    S040 --> S070
    S040 --> S080
    S040 --> S090
    S050 --> S070
    S050 --> S080
    S060 --> S100
    S070 --> S100
    S080 --> S100
    S090 --> S100
    S100 --> S110
```

`020` and `030` can start together after `010`; the four surface lanes can run
in parallel after their declared foundations. `100` is a blocking audit, and
`110` alone owns cross-surface assembly and the atomic cutover.
