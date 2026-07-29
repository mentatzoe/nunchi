# V2 verification record

This file is updated only with attributable commands and artifacts. A green
source suite is not installed or live evidence.

## Candidate scope

Included: shared V2 foundation, CLI, packaging, generic/Discord/Matrix/Telegram
reference adapters, shared Discord MCP transport, Codex, and the Hermes source,
wheel, dashboard, installed runtime, and configured Discord evaluation.

Pending: the remaining Hermes live matrix in
[issue #38](https://github.com/mentatzoe/nunchi/issues/38); Claude Code
implementation and proof in
[issue #39](https://github.com/mentatzoe/nunchi/issues/39); shared ACK behavior
in [issue #40](https://github.com/mentatzoe/nunchi/issues/40); and the combined
acceptance gate in
[issue #41](https://github.com/mentatzoe/nunchi/issues/41).

## Required evidence

| Claim | Required proof | Current candidate |
|---|---|---|
| source and contract | exact commit; clean tree; V2 full suite; eval list/run; diff check | verified at repaired implementation commit `c5f5e6c0c7e2fd6af1bf888ca9a86a7a8f4d7e63`; 319 source tests, 218 pinned dual-validator tests with zero skips, 8/8 lifecycle evaluations, clean diff check |
| clean artifact | wheel hash; new venv; installed probes; no checkout imports; installed smoke | verified; two exact-source builds produced byte-identical wheel SHA-256 `f2852390c7e4fc8beff03091e6a9478ff22186c7030846f319c5b241d00eb9c1`; clean Python 3.14 install, installer init/verify, all entry-point probes, and MCP 1.28.1 construction passed |
| deterministic lifecycle | SUPPRESS, WAKE contribution, WAKE silence, both DEFER paths, bypass, both error policies | verified offline 8/8 against source and the installed artifact |
| adversarial safety | identity, malformed input, route, replay, mutation, cancellation, coalescing, isolation, bounded context, gaps, restart, corrupt persistence | verified; full suite plus 101 focused cases against source and again against the installed wheel, including actor-byte, deadline, receipt-fsync, stale-approval, post-commit authority, malformed acknowledgement, lost acknowledgement, and no-duplicate-retry probes |
| real room | attributable delivery/receipt IDs for SUPPRESS, WAKE, both DEFER paths, bypass, error, contribution, silence | verified on exact installed evidence candidate `755091b749876fa0954b42a9d5e86e2424c37b8b` and wheel SHA-256 `f2852390c7e4fc8beff03091e6a9478ff22186c7030846f319c5b241d00eb9c1`; see `evidence/v2/shared-foundation-live-2026-07-24.md` |
| downstream readiness | platform interface and portable/runnable conformance suite | verified by installed conformance and interface probes |
| Hermes compatibility | dependency-free wheel; Hermes 0.19.0 and current-head shape checks; dashboard; unchanged Hermes hashes; V2 platform tests | implementation `b6ee0c2dbe918140fcc77f19320402bb35b44b75` passes source, package, installed-runtime, dashboard, and partial live Discord checks; live Discord DEFER/silence and Telegram acceptance remain open in issue #38 |
| independent review | fresh non-author Codex review of exact final commit with no blocker | verified; non-author reviewer `/root/foundation_final_candidate_review` (Dirac; OpenAI `gpt-5.6-sol`) approved exact evidence candidate `8296e11d6cb3018e68d2904765a7e1d61f218bd9` with no unresolved blocker; this record-only successor changes only that attribution |

Do not reinterpret `pending` as failure or success. Final acceptance requires
every row in scope to name immutable evidence.

## Hermes gate, package, and compatibility

Implementation `b6ee0c2dbe918140fcc77f19320402bb35b44b75` makes Nunchi a
pre-attention gate around the stock Hermes participant:

- `SUPPRESS` stops before Hermes typing, reactions, tools, or model work.
- `WAKE`, `DEFER`, bypass, and error-wake call the original Hermes handler
  once. Hermes keeps its prompt, main model, memory, tools, reactions,
  cancellation, delivery, and platform adapter.
- Nunchi uses Hermes's public pre-LLM hook only to add bounded turn facts.
- Checked process-local wrappers cover ingress, result, lifecycle, send,
  shutdown, configured-room Discord admission, and Telegram batch identity.
  They change no Hermes checkout or installed package file.
- The wheel has no Hermes dependency. It installs the Nunchi dashboard bridge
  only in Hermes's user-plugin directory.

The exact wheel SHA-256 is
`dda7c634eaae399f0d62bbef8229a8548b9c03fa37a4ca8a3866dc4286611642`.
The source suite passed 368 tests with four optional JSON-Schema skips; all
eight lifecycle evaluations passed. Shape probes passed against released
Hermes 0.19.0 at
`3ef6bbd201263d354fd83ec55b3c306ded2eb72a` and the maintained checkout at
`022a175e0ad5eb71fef0892dcf1d7f558d73f8b6`. Both probes confirmed stock
participant execution plus the ingress, result, lifecycle, processing-hook,
send, and shutdown wrappers.

The wheel was installed without dependencies in the `fiction-writer` Hermes
0.19.0 environment. Its 16-file Hermes distribution digest was
`a9e341b8b3214b853b04d7ac8c17a4bac31723f83851e756edc03e56ff0779bd`
before and after installation, and the maintained Hermes checkout stayed
clean. The installed dashboard assets verified as:

- `index.js`: `d23fd571648a5f21aa7a8e6fb075b2b61314c21201be0a348ec979512b3ccbc0`
- `manifest.json`: `d87e5c56a2659c58ca750992e473aed7f3b67cd0fd5da66b9cad549a631b9d63`
- `plugin_api.py`: `56fec259232e2d6df017b2ab66fd1bde470f664ac3e7309539cf01d567091000`

## Hermes live Discord evidence

The exact wheel above ran in profile `fiction-writer`, configured channel
`1530259309802295316`, with Hermes main model `nous/x-ai/grok-4.5`,
Nunchi attention model `nous/deepseek/deepseek-v4-flash`, and
`DISCORD_ALLOW_BOTS=none`.

- Vigil `/nunchi probe` message `1532134187002236998` received response
  `1532134191272169713`. It reported `process-local-gate`, `stock-hermes`,
  Hermes 0.19.0, no Hermes dependency or modified files, exact configured-room
  bot admission, and the pinned configuration digest
  `0af0470730ed9041413f5097268d3c2f5d7a6f583f1801f1708fe1c3694846eb`.
- Unmentioned Vigil message `1532134240865484810` produced Nunchi request
  `discord:1530259309802295316:a1f7ac85-2410-4a1c-962d-f1dca28b13cd`.
  Attention used `deepseek-v4-flash`; stock Hermes used `grok-4.5`, injected
  the bounded Nunchi facts, and sent response `1532134339448410224`.
  Participant and transport receipts both settled as `sent`.
- Routine message `1532134584530239651` produced request
  `discord:1530259309802295316:4cb15f86-4386-4edf-96c9-4248972fddad`
  with effective `SUPPRESS`. It had no reaction, Hermes turn, participant
  receipt, transport receipt, or response.
- Long turn `1532134736003072082` showed Hermes's `👀` reaction. Vigil `/stop`
  message `1532134842362368130` received stock confirmation
  `1532134844266451128`; request
  `discord:1530259309802295316:d8343b16-a704-41c5-9065-668948d3db89`
  settled with no stale response and a cancelled delivery receipt.
- Tool request `1532135103109665031` showed `👀`, used Hermes's terminal tool
  once under `grok-4.5`, returned exact output in response
  `1532135235008073738`, and finished with `✅`. Request
  `discord:1530259309802295316:490f3b3a-d02d-499b-bc85-215c97aa41ef`
  settled participant and transport as `sent`.
- While the gateway was stopped, Vigil sent recovery carrier
  `1532135404675924260`. Restart backfilled it into observations without an
  attention decision, Hermes turn, reaction, receipt, or response. New
  unmentioned message `1532135683374714930` then received exact stock response
  `1532135791457865910`.
- The installed dashboard API performed a validated idempotent save of two
  rooms, read 24 discovered channels and recent receipts, reported
  configured-room bot admission with no mention or profile-wide fallback, and
  kept the same pinned digest. Hermes restarted and both Discord and Telegram
  reconnected under launchd.

Automated Hermes tests separately cover participant silence, failed
processing, active-plus-newest scheduling, incompatible host shapes, and
unconfigured rooms. Telegram room `670011474` is configured and connected,
but no live Telegram acceptance is claimed.

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
