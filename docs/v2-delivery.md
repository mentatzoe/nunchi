# Delivering Nunchi V2

This is the implementation entrypoint. The target is the product described in
`v2-completion-goal.md`: agents that read the room in a live multi-party,
multi-turn conversation. Checked tasks, labels, and planning artifacts are not
the target.

## Current truth (2026-10-04)

V2 is partial and not live-verified. Since the maintainer's 2026-10-04 decision, `main` is
the working branch and holds V2; `integration/v2` is retired. Work merges into
`main` as it lands, before live proof, so a current `main` is not a claim that
V2 is complete. No surface has passed a live real-room check since PR
[#67](https://github.com/mentatzoe/nunchi/pull/67) replaced the shared core.
There is no V2 release tag; the last tag is `v0.2.0`.

Status words follow `AGENTS.md`:

- **missing**: required product behavior is absent.
- **implemented, unverified**: code exists, but it is not on `main`.
- **merged, unverified**: the code is on `main`, but named checks have not
  passed (live checks, at least).
- **verified**: the code passed its tests, installed-runtime checks, and live
  checks.

Nothing below is **verified**.

| Surface | Status | Checks passed on `main` | Outstanding |
|---|---|---|---|
| Shared core, operator CLI/dashboard/services, packaging | **merged, unverified** (PR #67, plus #88, #89, #90, #91) | CI: offline suite and contract corpus on Python 3.11–3.13, clean wheel install with entry-point probes; local: 11/11 lifecycle scenarios | live proof; combined acceptance ([#41](https://github.com/mentatzoe/nunchi/issues/41)); agnostic-core follow-up ([#85](https://github.com/mentatzoe/nunchi/issues/85)) |
| Reference adapters (generic channel, Discord, Matrix, Telegram) and shared Discord MCP transport | **merged, unverified** | offline tests; clean-install probes | live proof per platform |
| Hermes plugin (parked 2026-10-10; the old integration was removed 2026-10-11) | **merged, unverified**, parked | offline: the turn conformance kit and the plugin's tests inside a clean install of pinned stock Hermes, the Discord stand-in lane and the scripted rehearsal probe, all in the `hermes-plugin` CI job | live proof; unparking ([plugin README, Before unparking](../integrations/hermes-plugin/README.md#before-unparking)) |
| Codex app-server runner | **merged, unverified**: `nunchi-codex-app-server-runner` through `codex app-server`, with the user's own Codex model, sandbox, tools, MCP servers and skills; Discord only | offline: the turn conformance kit and `tests/v2/test_codex_app_server.py` against a clean, pinned Codex CLI 0.160.1 (the `codex-app-server` CI job); clean-install probe | live proof |
| Codex room runner (older) | **merged, unverified**, reduced: Discord only, Codex tools, skills, plugins, and MCP disabled; stays until the app-server runner passes live checks | offline tests; clean-install probe | retirement after the app-server runner's live proof; draft PR [#71](https://github.com/mentatzoe/nunchi/pull/71) and parity gaps #59–#65 cover this runner |
| Claude Code | **merged, unverified**: per-room gate, dedicated session, and Nunchi mod ([#43](https://github.com/mentatzoe/nunchi/issues/43)); Discord only | offline tests, including a stub session over the real gate socket; `claude plugin validate --strict` and `claude plugin test` on Claude Code 2.1.289; clean-install probe | every adapter ([#57](https://github.com/mentatzoe/nunchi/issues/57)); install and supervision ([#58](https://github.com/mentatzoe/nunchi/issues/58)); live acceptance ([#39](https://github.com/mentatzoe/nunchi/issues/39)) |

No unverified platform (Hermes, Codex, or Claude Code) may be described as
done, live, or parity-ready until its open gates pass.

Hermes has no supported path today. The maintainer removed the old Hermes integration on
2026-10-11 ("delete, for now"): it patched Hermes at runtime, which breaks the
rule that an integration follows each harness's own plugin rules and never
patches or reimplements the harness. The Hermes plugin stays parked, with its
code and CI lane, until it is unparked; its README says what it does and what
it lacks. The Hermes issues [#38](https://github.com/mentatzoe/nunchi/issues/38),
[#42](https://github.com/mentatzoe/nunchi/issues/42) and
[#44](https://github.com/mentatzoe/nunchi/issues/44) tracked the removed
integration's gates and gate nothing here until the plugin is unparked.

Claude Code follows the design the maintainer selected (#43): one Python gate per room,
a dedicated Claude Code session per room that keeps the user's configuration,
and a Nunchi mod in that session for the room tools. It replaced the headless
subprocess runner (PR #32); the channel-plugin designs (PR #72, issue #77) are
superseded. `nunchi-claude-code-room-runner` now starts the gate.

Open gates:

- [#39 Claude Code live and release acceptance](https://github.com/mentatzoe/nunchi/issues/39);
- [#41 combined V2 final acceptance](https://github.com/mentatzoe/nunchi/issues/41);
- [#43 Claude Code mod and dedicated session](https://github.com/mentatzoe/nunchi/issues/43);
- [#57 Claude Code on every Nunchi adapter](https://github.com/mentatzoe/nunchi/issues/57);
- [#58 Claude Code install and supervision](https://github.com/mentatzoe/nunchi/issues/58);
- [#66 freeze one exact release candidate](https://github.com/mentatzoe/nunchi/issues/66);
- [#78 the maintainer grants: a persistent host machine for live rooms and services](https://github.com/mentatzoe/nunchi/issues/78);
- [#85 agent- and provider-agnostic core](https://github.com/mentatzoe/nunchi/issues/85);
- [#86 behavioral evaluations](https://github.com/mentatzoe/nunchi/issues/86);
- [#87 decision-model exploration](https://github.com/mentatzoe/nunchi/issues/87).

Merging lets the product be assembled and tested as a whole. It is not
verification, support, release readiness, or completion.

## Working agreement

1. Start from current `main`. Pick the earliest missing behavior the product
   needs. Specs under `specs/` are reference; check their claims
   against the selected design and current source.
2. Work on a short-lived branch. Change the behavior, tests, evaluation hooks,
   installation or runtime code, and affected documentation together.
3. Open a PR into `main`. State the observable outcome, the exact checks run,
   what they prove, and what is still missing.
4. Scale review to the size and risk of the change. A self-review with
   subagents is acceptable; say plainly that it is one. Cross-family
   independent review is not required for day-to-day delivery.
5. Merge when CI is green, then delete the branch. Do not keep long-lived side
   branches.
6. When a shared interface changes, run every consumer's tests in the same PR
   and fix or flag what breaks.

A release (a `v*` tag) still follows `v2-completion-goal.md`, including its
frozen candidate and independent non-author review.

## Platform work

Platform integrations plug into the shared core through neutral interfaces and
own their host text, paths, configuration, and lifecycle. Before changing one:

1. Read `docs/platform-v2.md` for the shared-owner and platform seam.
2. Read `docs/contracts/nunchi-v2.md` for the portable contracts.
3. Run the shared suite under `tests/v2/contract` and the platform's runtime
   commands before adding native cases.
4. Implement only the platform-owned wrapper and native identity, transport,
   cancellation, persistence, and live-proof obligations. Do not fork social
   judgment or authority semantics into the integration.

Default owners are listed in `AGENTS.md`; they are not gates.

## Build order

The original dependency order, kept as reference:

```text
010 contract
  ├─ 020 observation
  └─ 030 attention core
       └─ 040 participant host, scheduling, and action guard
020 ──└─ 050 shared Discord transport
010–050 ── 060 Hermes / 070 Claude Code / 080 Codex / 090 reference adapters
010–090 ── 100 security assurance
010–100 ── 110 parity, packaging, live mixed-agent proof, and atomic cutover
```

`060` and `070` are platform-owned. Since 2026-10-04, `110`'s atomic cutover
governs the release tag, not the merge to `main`.

## Review standard

Review the code and reproduce the behavior. Look specifically for hidden V1
paths, fail-open errors, identity or authorization confusion, stale
conversation revival, cancellation races, output escape paths, cross-room or
profile leakage, dishonest coverage, and installed-byte drift.

Evidence is useful only when it records a passing observable outcome against
the exact code. A packet, label, test file, or report does not pass merely by
existing.

## Completion

The project is complete only when every end condition in
`v2-completion-goal.md` is true for one frozen, installable candidate and the maintainer
accepts that exact result. Until then, report what is missing in plain words.
