# Nunchi V2 adapters

> Candidate documentation. V2 is not the verified current release until the
> exact atomic successor is accepted and post-merge verified.

All installed adapters use the portable V2 lifecycle: exact native facts,
bounded observation, one participant-shaped pre-attention judgment, fresh
one-active/one-newest-pending scheduling, a normal participant act-or-silence
turn, request-correlated receipts, and no send-time social reclassification.

The detailed command, identity, event, action, restart, and parity contract is
[`adapters-v2.md`](adapters-v2.md). The shared Discord source/action transport
is documented in
[`../integrations/mcp-discord/README.md`](../integrations/mcp-discord/README.md),
and the direct Codex participant in
[`../integrations/codex/README.md`](../integrations/codex/README.md).

| Surface | Candidate evidence tier | Important declared limitation |
|---|---|---|
| Generic JSONL host | Offline deterministic coverage | Host must attest every identity/routing/recoverability fact |
| Standalone Discord | Offline deterministic coverage | Session continuity; restart gap; no collision-free inbound reaction ID |
| Shared Discord MCP | Offline deterministic and clean-wheel help coverage | Session delivery is not durable replay; membership unavailable |
| Matrix reference | Offline deterministic coverage | Session continuity; restart gap |
| Telegram reference | Offline deterministic coverage | Live-only context; restart gap; no exact outbound mention entity synthesis |
| Codex | Offline deterministic coverage | Live mixed-room evidence still required |
| Hermes | Awaiting accepted Aleph V2 packet | Inherited V1 plugin is not V2 parity |
| Claude Code | Awaiting accepted Claude V2 packet | Inherited V1 hook is not V2 parity |

Status labels in this table are evidence tiers, not release promises. Earlier
Codex V1 bounded live-smokes evidenced only the historical runner and cannot be
promoted into V2 proof. Current live and installed evidence obligations are in
[`evaluations/v2.md`](evaluations/v2.md).
