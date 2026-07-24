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
| source and contract | exact commit; clean tree; V2 full suite; eval list/run; diff check | verified at repaired implementation commit `c5f5e6c0c7e2fd6af1bf888ca9a86a7a8f4d7e63`; 319 source tests, 218 pinned dual-validator tests with zero skips, 8/8 lifecycle evaluations, clean diff check |
| clean artifact | wheel hash; new venv; installed probes; no checkout imports; installed smoke | verified; two exact-source builds produced byte-identical wheel SHA-256 `f2852390c7e4fc8beff03091e6a9478ff22186c7030846f319c5b241d00eb9c1`; clean Python 3.14 install, installer init/verify, all entry-point probes, and MCP 1.28.1 construction passed |
| deterministic lifecycle | SUPPRESS, WAKE contribution, WAKE silence, both DEFER paths, bypass, both error policies | verified offline 8/8 against source and the installed artifact |
| adversarial safety | identity, malformed input, route, replay, mutation, cancellation, coalescing, isolation, bounded context, gaps, restart, corrupt persistence | verified; full suite plus 101 focused cases against source and again against the installed wheel, including actor-byte, deadline, receipt-fsync, stale-approval, post-commit authority, malformed acknowledgement, lost acknowledgement, and no-duplicate-retry probes |
| real room | attributable delivery/receipt IDs for SUPPRESS, WAKE, both DEFER paths, bypass, error, contribution, silence | verified on exact installed implementation predecessor `ca4404b`; see `evidence/v2/shared-foundation-live-2026-07-24.md`. The successor changes only uncertain post-effect closure and is covered by installed differential probes; the successful room matrix was not rerun |
| downstream readiness | platform interface and portable/runnable conformance suite | verified by installed conformance and interface probes; exact-successor independent review is pending |
| independent review | fresh non-author Codex review of exact final commit with no blocker | pending fresh review of the repaired implementation and this append-only evidence successor |

Do not reinterpret `pending` as failure or success. Final acceptance requires
every row in scope to name immutable evidence.

## Exact source/artifact evidence

The repaired implementation candidate is
`c5f5e6c0c7e2fd6af1bf888ca9a86a7a8f4d7e63`, based on the same
`51421eddbb6a8708a91716e65cbdfba602921856` foundation baseline. The worktree
was clean and the baseline-to-candidate diff under `integrations/hermes` and
`integrations/claude-code` was empty.

Build and installation reproduced:

- 319 source tests passing; the four baseline-interpreter skips were only the
  optional JSON-Schema side when `jsonschema` was absent;
- all 218 contract cases passing with zero skips under pinned
  `jsonschema==4.26.0`;
- all eight installed lifecycle scenarios passing;
- two clean builds producing a byte-identical wheel with SHA-256
  `f2852390c7e4fc8beff03091e6a9478ff22186c7030846f319c5b241d00eb9c1`;
- installed imports from `site-packages`, all shipped CLI/adapter/Codex
  probes, installer init/verify, explicit V1 `admit` rejection, and MCP 1.28.1
  server construction;
- 101 focused lifecycle, hardening, and transport tests against both exact
  source and the installed wheel, including the five exact post-effect
  uncertainty regressions, plus installed post-commit expiry and actor-byte
  probes;
- the complete attributable real-room matrix in
  `evidence/v2/shared-foundation-live-2026-07-24.md`.

The fresh non-author reviewer `/root/foundation_final_candidate_review`
rejected exact evidence candidate
`4dc13f72c153699424fadc3ecf46717549d77969` for one blocker: a lost,
malformed, or server-error acknowledgement after a Discord effect could be
reported as definitively failed even though the effect might exist. The
repair at `c5f5e6c` preserves `unknown`, does not retry uncertain mutating
5xx responses, treats explicit 4xx rejection as definitive, safely shapes
malformed nested responses, and propagates the uncertainty through Codex.
The same non-author reviewer must approve the exact evidence successor before
the independent-review row can pass.

The earlier non-author reviewer `/root/final_b97_exact_review` approved
`b97f0d50ac3855e9b279db21a60fe4a6ed28ecd6` and its documentation-only
successor. That is historical input, not approval of the current candidate:
live installation later exposed an MCP endpoint redirect and a
provider-incompatible Codex output schema, fixed by `887747e` and `ca4404b`
with regression tests.

## Live-room verification

On 2026-07-24, exact installed implementation predecessor `ca4404b` ran an
isolated Codex-only route as Vigil in Discord channel
`1530259309802295316`. The participant-bound Nous
`openai/gpt-5.6-luna` attention model demonstrated SUPPRESS, WAKE, direct
classifier DEFER, and margin DEFER. Trusted bypass invoked no classifier. A
deliberately unavailable attention endpoint produced an operational error and
explicit `ERROR_FALLBACK`, not a fabricated social result. Codex
`gpt-5.6-luna`, using its authenticated OAuth session, both contributed and
remained silent.

The run also demonstrated restart-gap rejection without stale replay,
target-attested sends, exact one-use authorization, immutable stage receipts,
and zero transport stages for SUPPRESS and participant silence. The
content-bounded record names every request and native message ID:
`evidence/v2/shared-foundation-live-2026-07-24.md`.

The final repair changes only classification of uncertain Discord
acknowledgements after an attempted effect and the retry policy for mutating
5xx responses. It does not change successful ingress, attention, participant,
authorization, target-attestation, or successful-send behavior exercised by
the matrix. The repaired wheel was therefore rerun through installed
deterministic and adversarial checks, including direct lost/malformed/5xx
acknowledgement probes, rather than fabricating a real-room failure response
that Discord did not emit.

Vigil's temporary Server Members intent was restored to its exact original
application flags, the temporary HMAC key was deleted, temporary V2 processes
were stopped, and the pre-existing Vigil launch agents were restored. Hermes
and Claude Code were not installed, repaired, armed, or exercised.
