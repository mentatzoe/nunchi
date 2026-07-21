# Hermes V2 Candidate Integration

## Status

This document describes the Slice 060 candidate implementation in
`integrations/hermes/nunchi-gate/`. It is implementation/handoff documentation,
not a claim that V2 is current, installed, accepted, released, or live-verified.
V1 remains current until the program's atomic cutover is post-merge verified.

## Components

| Component | Responsibility |
|---|---|
| `v2_runtime.py` | Exact profile/transport/self/room binding; Discord/Telegram native projection; bounded observation state; ephemeral scheduler; one-use wake tickets |
| `v2_plugin.py` | Authorization-first admission; busy/raw Discord compatibility seams; off-loop evaluation; participant and whole-process transport staging; fail-closed effects/output |
| `__init__.py::register` | Profile-aware config, effective streaming/effect-runtime attestation, exact redispatch scheduling, and V2 registration |
| `plugin.yaml` | V2 hook and `tool_execution` middleware declaration |

The active path consumes the canonical Nunchi V2 implementation under `src/nunchi`.
It does not copy schemas or implement an alternative verdict system.

## Trust boundaries

- Native adapter identity, not display text, binds self.
- Hermes authorization is required before human input enters observation,
  classification, receipts, or ticket state.
- Each scoped Telegram text update bypasses Hermes' lossy concatenation batch
  and enters as its own native `MessageEvent`, preserving that update's ID and
  entity set. The pinned Discord raw-dispatch seam snapshots literal mentions
  before Hermes mutates content, retains eligible self/peer-directed context,
  and completes that retention before ordinary dispatch continues.
- Classifier advice is untrusted annotation and is rendered separately from room facts.
- Wake tickets are host-owned, request-correlated, one-use, and restart-ephemeral.
- Continuation/wake secrets do not enter classifier input or room output.
- Each receipt stage is appended by its owning seam; participant-host precedes
  platform I/O and transport closes only after the full adapter output process.
- Ticketed tool effects without exact canonical authorization return a terminal denial without invoking Hermes `next_call`.
- Hermes processing typing/reactions/voice acknowledgements are suppressed
  before they can escape the participant rail. An explicit scoped Discord
  self-mention continues in its parent channel without entering Hermes'
  auto-thread attempt/error branch. Telegram drafts and interactive
  clarify/approval prompts are terminal output and are wrapped.
- Gateway proxy mode and `codex_app_server` are outside V2 scope because they
  bypass ordinary Hermes tool middleware. Before the participant executes,
  the candidate re-attests the configured participant, policy source and
  semantic fingerprint, authenticated self/room binding, normalized session,
  effective per-session runtime, streaming rail, and effect rail.

## Runtime sequence

```mermaid
sequenceDiagram
    participant T as Native transport
    participant H as Hermes authorization/admission
    participant O as Observation/scheduler
    participant A as Attention worker
    participant P as Hermes participant turn
    participant S as Adapter output process

    T->>H: native event
    H->>H: authorize before Nunchi state
    H->>O: exact native projection + ordered retain
    H-->>T: skip first dispatch
    O->>A: one attention opportunity (off event loop)
    A->>A: write observation + attention receipts
    alt effective SUPPRESS
        A-->>O: complete; no participant
    else WAKE / DEFER / bypass / error fallback
        A->>H: one-use exact-event ticket + redispatch
        H->>P: normal turn with I-010C facts
        P->>P: act naturally or remain silent
        P->>A: participant-host receipt
        alt final message
            P->>S: response after participant-host receipt
            S->>S: all text/media terminal methods
            S->>A: one conservative transport receipt after process closure
        else silence
            P-->>A: complete without transport
        end
    end
    A->>O: promote newest pending anchor only
```

## Evidence grades

| Case | Current evidence |
|---|---|
| HM-01 exact identity | Deterministic |
| HM-02 disposition routing and receipts | Deterministic |
| HM-03 later hearing/restart semantics | Deterministic |
| HM-04 shared Discord | Deterministic synthetic only; no live claim |
| HM-05 Telegram | Deterministic synthetic only; no live claim |
| HM-06 installed provenance | Installed-source inspection plus candidate registration against installed Hermes classes at `0.19.0` / `f657840…`; no deployed-plugin/provider claim |

The committed JSONL rows carry `evidence_grade` on every scene. Missing live
capability is an explicit limitation, not silently upgraded to proof.

## Known limitations

1. The plugin uses narrow version-pinned Hermes wrappers because public hooks do
   not expose pre-queue busy admission, raw filtered Discord context, whole-turn
   completion, or whole-process transport closure. Any host revision requires
   reinspection.
2. Streaming replies are unsupported. V2 scope requires both
   `nunchi.streaming: false` and effectively disabled Hermes profile/platform
   streaming. Any pre-participant terminal output is additionally blocked before
   platform I/O.
   Gateway proxy mode and `model.openai_runtime: codex_app_server` are likewise
   unsupported and put the room outside V2 scope.
3. The adapter truthfully exposes session-only continuity with a restart gap;
   no Discord/Telegram restart recovery is claimed by this packet.
4. Normal text and silence are verified. Privileged/effectful tool actions are
   fail-closed until exact `I-040B` request/grant mapping is supplied. Hermes
   processing reactions/typing/voice acknowledgements are suppressed; model-
   requested reactions, slash commands, TTS, cron, nested code, background,
   plugin, and MCP paths remain unsupported.
5. HM-04/HM-05 are synthetic. No genuine live Discord/Telegram/provider evidence
   was available while constructing this packet.
6. The inherited V1 implementation remains physically present as inactive
   migration material. The registered path and manifest are V2; final atomic
   integration may remove the dead material once downstream consumers no longer
   require the historical test surface.

## Commands

```sh
.venv/bin/python -m unittest tests.v2.test_hermes tests.v2.test_hermes_eval -v
.venv/bin/python -m evals.v2.hermes.runner \
  --hermes-source /Users/zmll/.hermes/hermes-agent \
  --output evidence/v2/hermes/hermes-scenes.jsonl \
  --require-complete
.venv/bin/python scripts/check_governance.py --check-cli
.venv/bin/python -m unittest
```

The first two commands are candidate-focused. The last two are repository-wide
gates and must be recorded from the frozen candidate before handoff.
