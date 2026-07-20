# Integrating Nunchi V2

Nunchi V2 is a portable pre-attention and participant-host lifecycle, not a
PASS/ACK/ASK/SPEAK reply gate. A host provides exact native facts and trusted
bindings; Nunchi observes a bounded current room, makes at most one stochastic
social judgment for the opportunity, wakes the participant when required, and
accepts one structured action or silence.

Use these ordinary-path references:

- [`architecture/v2-selected-design.md`](architecture/v2-selected-design.md) — system boundary, sequence, classes, contracts, freshness, and security.
- [`adapters-v2.md`](adapters-v2.md) — generic, Discord, Matrix, and Telegram host bindings.
- [`integrations/codex-v2.md`](integrations/codex-v2.md) — direct tool-empty Codex participant.
- [`security/v2.md`](security/v2.md) — identity, authorization, credentials, receipts, and approval boundaries.
- [`operators/v2.md`](operators/v2.md) — install and operation commands.

The old generic admission API and its `nunchi admit` command are absent. The
historical classifier corpus is list-only under
[`evaluations/verdict-suite.md`](evaluations/verdict-suite.md). Hermes and
Claude Code must arrive as accepted V2 packets against the shared interfaces;
their inherited V1 artifacts are not compatibility implementations.
