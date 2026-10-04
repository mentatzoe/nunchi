# Nunchi evidence index

This ordinary repository tree owns committed run records.

Product-behavior records outside `evidence/v2/` describe V1 or historical
pre-V2 behavior and do not prove the selected V2 attention/wake lifecycle.
Exact-candidate V2 records live under `evidence/v2/` and identify the source,
installed runtime, and scope they substantiate. Governance records are
historical provenance only.

- `verdict-suite/` — classifier replay, bake-off, performance, and room-session
  records.
- `codex/` — bounded Codex integration reviews and live smokes.
- `mcp-discord/` — bounded shared Discord-MCP transport smoke.
- `packaging/` — historical package/install smoke.
- `examples/` — captured demonstration output; illustrative, not a parity
  claim.
- `v2/contract/` — deterministic portable-contract validation records; these
  prove schema and correlation behavior, not installed runtime enforcement.
- `v2/shared-foundation-live-2026-07-24.md` — installed-wheel and live
  Discord run of the shared foundation, shared Discord transport, CLI, Codex,
  and reference adapters at `ca4404b`. It predates the PR #67 operator and ACK
  foundation and is not proof of current `main`; it covers no Hermes or
  Claude Code.
- `v2/shared-foundation-zero-margin-abort-2026-07-25.json` — an aborted live
  runner launch (configuration bytes did not match the pinned digest).
- `v2/completion-baseline-2026-07-23.md` — the repository state the V2
  completion goal started from; historical.
- `v2/normal-turn/` — normal Hermes turns on untouched installed Hermes
  0.19.0 and 0.21.5 hosts, with a loopback model and fake Discord client; not
  live-room evidence.
- `v2/attention-trust/` — Hermes attention trust-setup repair runs on
  installed hosts with loopback fixtures; not live-provider or live-room
  evidence.
- `v2/claude-code/` — review record and offline participant scenes for the
  headless Claude Code runner (PR #32), which the Claude Code gate and mod
  replaced ([#43](https://github.com/mentatzoe/nunchi/issues/43)). History,
  not evidence for the current integration; no live real-room evidence.
- `governance/` — historical workflow and ownership provenance; never current
  status or V2 runtime evidence.

The retired execution-spine record remains unchanged as history. Status words
are defined in `AGENTS.md`; ordinary code and reproducible behavior determine
what exists.

Evidence is immutable or append-only. Corrections should arrive as a dated
addendum rather than rewriting what an earlier run observed.
