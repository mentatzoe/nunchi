# V2 verification record

This file is updated only with attributable commands and artifacts. A green
source suite is not installed or live evidence.

## Candidate scope

Included: shared V2 foundation, CLI, packaging, generic/Discord/Matrix/Telegram
reference adapters, shared Discord MCP transport, and Codex.

Excluded: Hermes and Claude Code implementation, repair, arming, installation,
and live evaluation.

## Required evidence

| Claim | Required proof | Current candidate |
|---|---|---|
| source and contract | exact commit; clean tree; V2 full suite; eval list/run; diff check | verified at implementation commit `ca4404b7fb3c04b96ae80319eeb22723a5d7f8b2`; 314 source tests, 218 pinned dual-validator tests with zero skips, 8/8 lifecycle evaluations, clean diff check |
| clean artifact | wheel hash; new venv; installed probes; no checkout imports; installed smoke | verified; clean wheel SHA-256 `36975d5f1e863e41db0b9a70d3057ae0b05c87276eec38c0ed52ce15da1b0d82`; clean Python 3.14 install, installer init/verify, all entry-point probes, MCP 1.28.1 registration, and the live matrix passed |
| deterministic lifecycle | SUPPRESS, WAKE contribution, WAKE silence, both DEFER paths, bypass, both error policies | verified offline 8/8 against source and the installed artifact |
| adversarial safety | identity, malformed input, route, replay, mutation, cancellation, coalescing, isolation, bounded context, gaps, restart, corrupt persistence | verified; full suite plus 96 focused cases against source and again against the installed wheel, including actor-byte, deadline, receipt-fsync, stale-approval, and post-commit authority probes |
| real room | attributable delivery/receipt IDs for SUPPRESS, WAKE, both DEFER paths, bypass, error, contribution, silence | verified on the exact installed implementation candidate; see `evidence/v2/shared-foundation-live-2026-07-24.md` |
| downstream readiness | platform interface and portable/runnable conformance suite | verified by exact-candidate review; installed conformance and platform interface are sufficient for downstream owners |
| independent review | fresh non-author Codex review of exact final commit with no blocker | pending fresh review of the `ca4404b` implementation and this live-evidence successor |

Do not reinterpret `pending` as failure or success. Final acceptance requires
every row in scope to name immutable evidence.

## Exact source/artifact evidence

The frozen implementation candidate is
`ca4404b7fb3c04b96ae80319eeb22723a5d7f8b2`, based on
`51421eddbb6a8708a91716e65cbdfba602921856`. The worktree was clean and the
baseline-to-candidate diff under `integrations/hermes` and
`integrations/claude-code` was empty.

Build and installation reproduced:

- 314 source tests passing; the four baseline-interpreter skips were only the
  optional JSON-Schema side when `jsonschema` was absent;
- all 218 contract cases passing with zero skips under pinned
  `jsonschema==4.26.0`;
- all eight installed lifecycle scenarios passing;
- a clean wheel with SHA-256
  `36975d5f1e863e41db0b9a70d3057ae0b05c87276eec38c0ed52ce15da1b0d82`;
- installed imports from `site-packages`, all shipped CLI/adapter/Codex
  probes, installer init/verify, explicit V1 `admit` rejection, and MCP 1.28.1
  server construction;
- 96 focused lifecycle, hardening, and transport tests against both exact
  source and the installed wheel, plus installed post-commit expiry and
  actor-byte probes;
- the complete attributable real-room matrix in
  `evidence/v2/shared-foundation-live-2026-07-24.md`.

The prior non-author reviewer `/root/final_b97_exact_review` approved
`b97f0d50ac3855e9b279db21a60fe4a6ed28ecd6` and its documentation-only
successor. That is historical input, not approval of `ca4404b`: live
installation exposed an MCP endpoint redirect and a provider-incompatible
Codex output schema, fixed by `887747e` and `ca4404b` with regression tests.
A fresh exact-successor review is required before the independent-review row
can pass.

## Live-room verification

On 2026-07-24, the exact installed `ca4404b` artifact ran an isolated
Codex-only route as Vigil in Discord channel `1530259309802295316`. The
participant-bound Nous `openai/gpt-5.6-luna` attention model demonstrated
SUPPRESS, WAKE, direct classifier DEFER, and margin DEFER. Trusted bypass
invoked no classifier. A deliberately unavailable attention endpoint produced
an operational error and explicit `ERROR_FALLBACK`, not a fabricated social
result. Codex `gpt-5.6-luna`, using its authenticated OAuth session, both
contributed and remained silent.

The run also demonstrated restart-gap rejection without stale replay,
target-attested sends, exact one-use authorization, immutable stage receipts,
and zero transport stages for SUPPRESS and participant silence. The
content-bounded record names every request and native message ID:
`evidence/v2/shared-foundation-live-2026-07-24.md`.

Vigil's temporary Server Members intent was restored to its exact original
application flags, the temporary HMAC key was deleted, temporary V2 processes
were stopped, and the pre-existing Vigil launch agents were restored. Hermes
and Claude Code were not installed, repaired, armed, or exercised.
