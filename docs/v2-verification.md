# V2 verification record

This file is updated only with attributable commands and artifacts. A green
source suite is not installed or live evidence.

## Candidate scope

Included: shared V2 foundation, CLI, packaging, generic/Discord/Matrix/Telegram
reference adapters, shared Discord MCP transport, Codex, and the Hermes V2
source and wheel entry point.

Excluded: configured Hermes installation and live Hermes platform evaluation;
Claude Code implementation, installation, and live evaluation.

## Required evidence

| Claim | Required proof | Current candidate |
|---|---|---|
| source and contract | exact commit; clean tree; V2 full suite; eval list/run; diff check | verified at repaired implementation commit `c5f5e6c0c7e2fd6af1bf888ca9a86a7a8f4d7e63`; 319 source tests, 218 pinned dual-validator tests with zero skips, 8/8 lifecycle evaluations, clean diff check |
| clean artifact | wheel hash; new venv; installed probes; no checkout imports; installed smoke | verified; two exact-source builds produced byte-identical wheel SHA-256 `f2852390c7e4fc8beff03091e6a9478ff22186c7030846f319c5b241d00eb9c1`; clean Python 3.14 install, installer init/verify, all entry-point probes, and MCP 1.28.1 construction passed |
| deterministic lifecycle | SUPPRESS, WAKE contribution, WAKE silence, both DEFER paths, bypass, both error policies | verified offline 8/8 against source and the installed artifact |
| adversarial safety | identity, malformed input, route, replay, mutation, cancellation, coalescing, isolation, bounded context, gaps, restart, corrupt persistence | verified; full suite plus 101 focused cases against source and again against the installed wheel, including actor-byte, deadline, receipt-fsync, stale-approval, post-commit authority, malformed acknowledgement, lost acknowledgement, and no-duplicate-retry probes |
| real room | attributable delivery/receipt IDs for SUPPRESS, WAKE, both DEFER paths, bypass, error, contribution, silence | verified on exact installed evidence candidate `755091b749876fa0954b42a9d5e86e2424c37b8b` and wheel SHA-256 `f2852390c7e4fc8beff03091e6a9478ff22186c7030846f319c5b241d00eb9c1`; see `evidence/v2/shared-foundation-live-2026-07-24.md` |
| downstream readiness | platform interface and portable/runnable conformance suite | verified by installed conformance and interface probes |
| Hermes compatibility | dependency-free wheel; Hermes 0.19.0 and current-head shape checks; dashboard; unchanged Hermes hashes; V2 platform tests | source, clean wheel, dashboard discovery, and installed dashboard bridge verified against released 0.19.0 and upstream `main` `22492f0c46a7ea7dd567fbeded58691b921170fc`; configured gateway and live Discord/Telegram acceptance remain pending |
| independent review | fresh non-author Codex review of exact final commit with no blocker | verified; non-author reviewer `/root/foundation_final_candidate_review` (Dirac; OpenAI `gpt-5.6-sol`) approved exact evidence candidate `8296e11d6cb3018e68d2904765a7e1d61f218bd9` with no unresolved blocker; this record-only successor changes only that attribution |

Do not reinterpret `pending` as failure or success. Final acceptance requires
every row in scope to name immutable evidence.

## Hermes source and package check

The current Hermes addition:

- installs from the Nunchi wheel through `hermes_agent.plugins` without a
  required Hermes dependency;
- reuses stock Discord and Telegram adapters;
- uses a checked runtime monkeypatch on Hermes 0.19.0 and on current `main`,
  without changing Hermes files;
- retains and processes each native Telegram update even when Hermes batches
  adjacent text;
- packages an authenticated dashboard tab for room configuration and V2
  receipts, with validated digest-sidecar writes and explicit restart;
- installs that tab only in Hermes's supported user-plugin directory, not its
  source or installed package;
- passes the shared V2 lifecycle plus Hermes-specific identity, routing,
  silence, cancellation, coalescing, restart, and delivery tests.

The reproducible clean-wheel SHA-256 for this worktree is
`044ca63898faa44b72aebffc76d26f77a3c69dea9b13be487f5b880e5d45cba6`.
Two builds with `SOURCE_DATE_EPOCH=1700000000` matched byte-for-byte. A clean
Python 3.14 environment installed that wheel without dependencies, installed
and verified the dashboard bridge, and imported only from `site-packages`.
The source suite passed 357 tests with four optional JSON-Schema skips; all
eight lifecycle evaluations passed. Hermes 0.19.0 verified 958 distribution
records unchanged, and the current upstream checkout remained clean. Both
dashboard loaders discovered the tab and imported its four API routes. This is
source and clean-package evidence, not configured gateway or live-platform
acceptance.

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

That reviewer then reproduced the repaired implementation and installed-wheel
checks at exact candidate
`755091b749876fa0954b42a9d5e86e2424c37b8b`, finding no implementation
blocker. It rejected one remaining proof boundary because the native matrix
still named predecessor wheel `36975d5f...` while the successful
acknowledgement path had changed. The attributable exact-successor run below
closes that stated boundary.

The same reviewer then rejected exact evidence commit `85553e2` solely because
its zero-margin chronology falsely said the discarded configuration received
no event. Retained artifacts instead prove one failed configuration-pin launch
and one later zero-margin SUPPRESS execution. The append-only correction names
that execution and keeps it outside the acceptance matrix; the ordinary
active-`0.12` natural SUPPRESS remains the matrix result. The exact aborted-run
command, wrong supplied pin, timestamps, runtime identity, runner exit `3`,
unredacted output, and raw-transcript record hash are retained in
`evidence/v2/shared-foundation-zero-margin-abort-2026-07-25.json`.

The reviewer approved exact clean evidence candidate
`8296e11d6cb3018e68d2904765a7e1d61f218bd9` with no unresolved blocker after
matching that record to the raw transcript and rechecking the installed,
native-room, recovery, cleanup, exclusion, and platform-interface boundaries.
This documentation-only successor records that external disposition; it does
not self-approve.

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

On 2026-07-25, exact installed candidate `755091b` and wheel
`f2852390c7e4fc8beff03091e6a9478ff22186c7030846f319c5b241d00eb9c1`
repeated the native matrix after the reviewer rejected differential-only
proof. Under pinned, attributable configurations it produced natural
effective SUPPRESS, WAKE with a target-attested contribution, direct
classifier DEFER with participant silence, margin DEFER with participant
silence, trusted bypass with zero classifier invocation, and provider-error
fallback with a target-attested contribution. A fresh source gap rejected its
carrier and was delivered before the first admitted scene. The append-only
evidence record names every exact trigger, request, output, and configuration
hash.

Vigil's temporary Server Members intent was restored to its exact original
application flags, the temporary HMAC key was deleted, temporary V2 processes
were stopped, and the pre-existing Vigil launch agents were restored. Hermes
and Claude Code were not installed, repaired, armed, or exercised.
