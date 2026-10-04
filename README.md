# Nunchi V2

Nunchi is a portable pre-attention gate for turn-aware participants in shared
conversation. V2 has one path:

`native event -> canonical observation -> participant-bound attention ->
SUPPRESS, ACK, or one shared participant turn -> host-owned transport`

Conversation events are observations, not reply obligations. Only the exact
participant's delegated attention model may make the social suppression
judgment. Deterministic host code owns identity, routing, context bounds,
scheduling, cancellation, receipts, authorization, and the single output or
effect commit point.

## Current state

V2 is on `main` and is partial: **merged, unverified**. Deterministic tests and
installed stock-Hermes checks pass in CI. No surface has passed a live
real-room check since the shared core was replaced in
[PR #67](https://github.com/mentatzoe/nunchi/pull/67). V2 is not release-ready
or complete, and there is no V2 release tag. Combined acceptance is tracked in
[issue #41](https://github.com/mentatzoe/nunchi/issues/41).

`main` contains the shared core; the operator CLI, dashboard, and service
supervisor; packaging; generic/Discord/Matrix/Telegram reference adapters; the
shared Discord MCP transport; and incomplete Hermes, Codex, and Claude Code
integrations.

The shared core has first-class ACK and one versioned participant protocol.
ACK adds one exact `👂` reaction without running the participant; unsupported
ACK widens to DEFER. The attention model is chosen by configuration (`kind`),
so the core names no agent host, chat platform, or model vendor.

**Hermes.** The Hermes integration reuses Nunchi's shared observation,
attention, scheduling, wake, and receipt behavior around the stock participant.
It supports Hermes 0.19.0 or newer when its checked host capability contract
passes, for configured Discord or Telegram rooms. Other Hermes platforms remain
outside Nunchi and keep stock behavior; attempts to add them to a Nunchi config
are rejected.

On configured Hermes rooms, ordinary tools run through the stock Hermes
registry and native approval flow, with plugin-owned guards at native invocation.
Hermes remains authoritative for tools and approvals. This boundary does not
claim atomic, universal authority over external effects: a journal `finish`
records the callback result, not independent confirmation of the external effect.
Hermes auto-title is disabled there because its background work can
outlive the turn. Native typing, voice input, `/thread`, detached participant
commands, and handoff into configured rooms are also disabled where Hermes
0.19.0 cannot keep them inside the admitted opportunity. Hermes's stock
processing reactions run only after the participant starts. These are explicit
product gaps, not supported behavior.

On every push to `main` and every PR into it, CI installs stock Hermes 0.19.0,
0.21.5, and current Hermes `main`. It runs the host-contract lane for Discord
and Telegram, and normal-attention and startup lanes for Discord. The
normal-attention lane covers normal turns, ordinary tools, native approval,
ACK, and attention setup. These lanes use a loopback model and captured
platform output, so they are installed-runtime checks, not live ones. Live
platforms, Telegram normal turns, release, and running-profile adoption remain
unverified. Historical Hermes evidence is not current proof. See the
[verification record](docs/v2-verification.md). Remaining Hermes gaps are
tracked in [issues #38](https://github.com/mentatzoe/nunchi/issues/38) and
[#42](https://github.com/mentatzoe/nunchi/issues/42), with supported-surface
parity tracked in [#44](https://github.com/mentatzoe/nunchi/issues/44).

**Codex.** `nunchi-codex-room-runner` runs a Codex participant in a Discord
room in a reduced mode: Codex shell, browser, plugin, app, skill, and MCP
capabilities are disabled. Safer task continuity and the other adapters are
in draft [PR #71](https://github.com/mentatzoe/nunchi/pull/71). It has no live
proof since PR #67.

**Claude Code.** `nunchi-claude-code-room-runner` is a per-room gate. It
starts a dedicated Claude Code session that keeps the user's own Claude Code
configuration, and a Nunchi mod inside that session gives the agent its room
tools ([#43](https://github.com/mentatzoe/nunchi/issues/43)). Discord only.
Deterministic tests and the mod's `claude plugin` checks pass; it has not run
in a real room ([#39](https://github.com/mentatzoe/nunchi/issues/39)). See
[`integrations/claude-code/README.md`](integrations/claude-code/README.md).

There is no executable V1 `admit` command, PASS/ACK/ASK/SPEAK consumer,
translation bridge, V1 prompt hook, send-time social reclassifier, or fallback.

## Install and inspect

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/nunchi probe
.venv/bin/nunchi-install probe
.venv/bin/nunchi setup \
  --profile vigil \
  --participant-id vigil \
  --actor-id discord:bot:9 \
  --display-name Vigil \
  --instructions 'Contribute carefully.' \
  --platform discord \
  --room-id 42 \
  --room-name delivery \
  --continuity-scope-id discord:channel:42 \
  --attention-model provider/attention-model \
  --participant-model provider/participant-model
.venv/bin/nunchi diagnose --profile vigil
.venv/bin/nunchi dashboard --profile vigil
```

Optional installed surfaces:

```sh
python3 -m pip install '.[discord]'
python3 -m pip install '.[mcp-discord]'
nunchi-channel --probe
nunchi-discord --probe
nunchi-matrix --probe
nunchi-telegram --probe
nunchi-codex-room-runner --probe
nunchi-claude-code-room-runner --probe
```

The package metadata exposes a `nunchi` Hermes plugin without adding Hermes as
a Nunchi dependency. When Hermes loads it, the plugin installs its
authenticated dashboard tab automatically for room configuration and V2
receipts without changing Hermes package files. First-time room setup and
private profile-config creation happen in that tab; no separate setup command
is required. Package and installed-runtime acceptance remain separate gates.
See [`integrations/hermes/README.md`](integrations/hermes/README.md).

The guided operator path creates and updates exact SHA-256 pins automatically;
operators do not calculate hashes or hand-write JSON. Credentials are named
only by trusted environment variable names in configuration; room payloads
cannot redirect models, identity, routes, policy, receipt destinations, or
output authority.

## Verify

```sh
python3 -m pip install '.[test]'
python3 -m unittest
python3 -m evals.verdict_suite.runner --list
python3 -m evals.verdict_suite.runner
```

The first command runs the offline suite under `tests/v2`: V2 schemas and
contracts, runtime, attention, authorization, scheduling, transport, operator
and services, reference adapters, Codex, Hermes, Claude Code, and the guard
that keeps the shared core agent- and provider-agnostic. Tests that need an
installed Hermes host skip without one. The suite does not prove a built
package or installed runtime; those require a fresh package build and isolated
installation. Whether an agent reads the room well needs behavioral evaluation
([#86](https://github.com/mentatzoe/nunchi/issues/86)); the deterministic
scenarios do not measure it. `tests/V1-REPLACEMENT.md` maps the removed V1
tests to their V2 coverage.

## Product and integration documentation

- [Completion outcome](docs/v2-completion-goal.md)
- [Selected design](docs/architecture/v2-selected-design.md)
- [Portable V2 contract](docs/contracts/nunchi-v2.md)
- [Shared foundation and operator handoff](docs/v2-shared-foundation.md)
- [Install and operate](docs/INSTALL.md)
- [Platform interface and conformance](docs/platform-v2.md)
- [Reference adapters](docs/adapters.md)
- [Verification and evidence](docs/v2-verification.md)

Source review, clean-wheel installation, configured probes, deterministic
tests, live provider evaluation, real-room evidence, integration, and release
are distinct claims. The verification record states exactly which have passed.
The final no-completion-before-verification gate is
[issue #41](https://github.com/mentatzoe/nunchi/issues/41).
