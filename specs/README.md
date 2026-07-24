# V2 reference definitions

This directory preserves detailed product requirements and technical designs
for the V2 program and its eleven implementation areas.

The useful artifacts are:

- `spec.md`: required behavior, interfaces, edge cases, and acceptance scenes;
- `plan.md`: intended architecture, integration seams, tests, evidence, and
  documentation impact; and
- umbrella `research.md`: design background.

These are reference documents, not an executable workflow. Historical
SpecKit, lifecycle, assignment, worktree, candidate, handoff, and acceptance
language inside them is non-authoritative and must not be followed. There are
no generated task lists or requirement checklists.

Use [`docs/v2-delivery.md`](../docs/v2-delivery.md) for implementation order,
ownership, status language, and review. Use
[`docs/v2-completion-goal.md`](../docs/v2-completion-goal.md) for completion.

| Area | Outcome |
|---|---|
| `010-v2-contract` | Portable V2 schemas and validation |
| `020-v2-observation` | Truthful bounded current-room observation |
| `030-v2-core-attention` | Participant-shaped pre-attention |
| `040-v2-participant-wake` | Direct participant turn, coalesced opportunities, and action guard |
| `050-v2-discord-transport` | Shared Discord ingress, continuity, and transport closure |
| `060-v2-hermes` | Hermes integration |
| `070-v2-claude-code` | Claude Code integration |
| `080-v2-codex` | Codex integration |
| `090-v2-channel-adapters` | Generic, Matrix, Telegram, and standalone Discord adapters |
| `100-v2-security-provenance` | Security and installed-runtime assurance |
| `110-v2-parity-cutover` | Cross-platform parity, packaging, and atomic cutover |
