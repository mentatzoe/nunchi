# Delivering Nunchi V2

This is the implementation entrypoint. The target is the product described in
`v2-completion-goal.md`: agents that read the room in a live multi-party,
multi-turn conversation. Checked tasks, labels, and planning artifacts are not
the target.

## Current truth (2026-10-04)

V2 is partial and not live-verified. Since Zoe's 2026-10-04 decision, `main` is
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
| Hermes | **merged, unverified** (PRs #36, #83, #84) | offline tests; installed stock-Hermes CI on 0.19.0, 0.21.5, and current Hermes `main`: contract lanes for Discord and Telegram, normal-attention and startup lanes for Discord | live acceptance ([#38](https://github.com/mentatzoe/nunchi/issues/38)); receipt/deadline/restart boundaries ([#42](https://github.com/mentatzoe/nunchi/issues/42)); supported-surface parity ([#44](https://github.com/mentatzoe/nunchi/issues/44)) |
| Codex | **merged, unverified**, reduced: Discord only, Codex tools, skills, plugins, and MCP disabled | offline tests; clean-install probe | continuity binding and other adapters in draft PR [#71](https://github.com/mentatzoe/nunchi/pull/71) (**implemented, unverified**); parity gaps #59–#65; live proof |
| Claude Code | headless runner (PR #32) **merged, unverified** and superseded; the selected mod design ([#43](https://github.com/mentatzoe/nunchi/issues/43)) is **missing** on `main` | offline tests and clean-install probe of the headless runner only | the mod and per-room gate (#43); every adapter ([#57](https://github.com/mentatzoe/nunchi/issues/57)); install and supervision ([#58](https://github.com/mentatzoe/nunchi/issues/58)); live acceptance ([#39](https://github.com/mentatzoe/nunchi/issues/39)) |

No unverified platform (Hermes, Codex, or Claude Code) may be described as
done, live, or parity-ready until its open gates pass.

Hermes reuses Nunchi's shared observation, attention, scheduling, wake, and
receipt behavior around the stock Hermes participant. Ordinary tools run
through the stock Hermes registry and approval flow with plugin-owned guards;
Hermes stays authoritative, and a journal `finish` records the callback result,
not confirmation of an external effect. Auto-title, stock typing, voice input,
native `/thread`, detached commands, and handoff into configured rooms stay
disabled; media and reaction ingress and other platforms are incomplete. The
stopped profile lifecycle archives V1 and V2 state and supports guarded
restoration; it does not convert V1 social history. See the
[verification record](v2-verification.md) for exact runs.

The Claude Code design selected by Zoe is a Claude Code mod plus one Python gate
per room, with a dedicated Claude Code session for each room (#43). The headless
subprocess runner (`nunchi-claude-code-room-runner`) and the channel-plugin
designs (PR #72, issue #77) are superseded. The runner stays in the tree until
the mod PR replaces it.

Open gates:

- [#38 Hermes live-platform acceptance](https://github.com/mentatzoe/nunchi/issues/38);
- [#39 Claude Code live and release acceptance](https://github.com/mentatzoe/nunchi/issues/39);
- [#41 combined V2 final acceptance](https://github.com/mentatzoe/nunchi/issues/41);
- [#42 Hermes receipt, deadline, and restart boundaries](https://github.com/mentatzoe/nunchi/issues/42);
- [#43 Claude Code mod and dedicated session](https://github.com/mentatzoe/nunchi/issues/43);
- [#44 Hermes supported-surface parity](https://github.com/mentatzoe/nunchi/issues/44);
- [#57 Claude Code on every Nunchi adapter](https://github.com/mentatzoe/nunchi/issues/57);
- [#58 Claude Code install and supervision](https://github.com/mentatzoe/nunchi/issues/58);
- [#66 freeze one exact release candidate](https://github.com/mentatzoe/nunchi/issues/66);
- [#78 Zoe grants: a persistent host machine for live rooms and services](https://github.com/mentatzoe/nunchi/issues/78);
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
`v2-completion-goal.md` is true for one frozen, installable candidate and Zoe
accepts that exact result. Until then, report what is missing in plain words.
