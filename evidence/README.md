# Nunchi evidence index

This ordinary repository tree owns committed run records. It is independent of
the disposable SpecKit control plane.

All product-behavior records currently present describe V1 or historical pre-V2
behavior. They do not prove the selected V2 attention/wake lifecycle. Governance
records may prove Goal 1 planning/tooling state only. Future Goal 2 product
records will live under `evidence/v2/` and must identify the exact candidate and
installed runtime they substantiate.

- `verdict-suite/` — classifier replay, bake-off, performance, and room-session
  records.
- `codex/` — bounded Codex integration reviews and live smokes.
- `mcp-discord/` — bounded shared Discord-MCP transport smoke.
- `packaging/` — historical package/install smoke.
- `examples/` — captured demonstration output; illustrative, not a parity
  claim.
- `governance/` — execution-spine, repository-boundary, and baseline proof;
  never V2 runtime evidence.

Evidence is immutable or append-only. Corrections should arrive as a dated
addendum rather than rewriting what an earlier run observed.
