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
| source and contract | exact commit; clean tree; V2 full suite; eval list/run; diff check | verified at implementation commit `b97f0d50ac3855e9b279db21a60fe4a6ed28ecd6`; 312 source tests, 218 pinned dual-validator tests with zero skips, 8/8 lifecycle evaluations, clean diff check |
| clean artifact | wheel hash; new venv; installed probes; no checkout imports; installed smoke | verified; two byte-identical archive builds, SHA-256 `cb24666bb1d1b779a08ce7bbb9a9403c3ba27866ab9d14424901e9bb6c1491e0`; clean Python 3.13/3.14 installs and all entry-point/MCP probes passed |
| deterministic lifecycle | SUPPRESS, WAKE contribution, WAKE silence, both DEFER paths, bypass, both error policies | verified offline 8/8 against source and the installed artifact |
| adversarial safety | identity, malformed input, route, replay, mutation, cancellation, coalescing, isolation, bounded context, gaps, restart, corrupt persistence | verified; full suite plus 94 focused cases against source and again against the installed wheel, including actor-byte, deadline, receipt-fsync, stale-approval, and post-commit authority probes |
| real room | attributable delivery/receipt IDs for SUPPRESS, WAKE, both DEFER paths, bypass, error, contribution, silence | **pending** isolated V2 Codex-only route and credentials; see blocker audit below |
| downstream readiness | platform interface and portable/runnable conformance suite | verified by exact-candidate review; installed conformance and platform interface are sufficient for downstream owners |
| independent review | fresh non-author Codex review of exact final commit with no blocker | verified: `/root/final_b97_exact_review` approved the implementation bytes and separately approved this verification-record-only successor with the product verdict unchanged |

Do not reinterpret `pending` as failure or success. Final acceptance requires
every row in scope to name immutable evidence.

## Exact source/artifact evidence

The frozen implementation candidate was
`b97f0d50ac3855e9b279db21a60fe4a6ed28ecd6`, based on
`51421eddbb6a8708a91716e65cbdfba602921856`. The worktree was clean and the
baseline-to-candidate diff under `integrations/hermes` and
`integrations/claude-code` was empty.

Independent build, installation, and review reproduced:

- 312 source tests passing; the four baseline-interpreter skips were only the
  optional JSON-Schema side when `jsonschema` was absent;
- all 218 contract cases passing with zero skips under pinned
  `jsonschema==4.26.0`;
- all eight installed lifecycle scenarios passing;
- two byte-identical wheels with SHA-256
  `cb24666bb1d1b779a08ce7bbb9a9403c3ba27866ab9d14424901e9bb6c1491e0`;
- installed imports from `site-packages`, all shipped CLI/adapter/Codex
  probes, installer init/verify, explicit V1 `admit` rejection, and MCP 1.28.1
  server construction;
- 94 focused lifecycle, hardening, and transport tests against both exact
  source and the installed wheel, plus installed post-commit expiry and
  actor-byte probes.

Fresh non-author reviewer `/root/final_b97_exact_review` returned `APPROVED`
for that exact source/artifact commit with no unresolved source or artifact
blocker. The collaboration runtime did not expose a separate model identifier.
The same reviewer separately approved the verification-record-only successor
with the product-byte verdict unchanged and no documentation blocker. Neither
verdict claimed live-room, integration, release, arming, or final product
completion.

## Live-route blocker audit

On 2026-07-24, the clean shell environment had no Discord token, participant
routes, output-HMAC key, state directory, pinned Codex configuration/digest,
or provider credential. The connected Nunchi settings surface reported only a
legacy `api_version: 1` Codex runtime. Its configured room and the other
observable room both contained active Aleph traffic; using either would test
an excluded integration and would not prove the exact installed V2 artifact.

No configuration was changed and no message was sent. Completion therefore
still requires an isolated Codex-only Discord route running the exact V2
artifact, with attributable delivery and receipt IDs for SUPPRESS, WAKE, both
DEFER paths, bypass, error handling, contribution, and silence.
