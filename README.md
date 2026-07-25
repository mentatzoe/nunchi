# Nunchi V2

Nunchi is a portable pre-attention gate for turn-aware participants in shared
conversation. V2 has one path:

`native event -> canonical observation -> participant-bound attention ->
participant wake -> contribution or silence -> host-owned transport`

Conversation events are observations, not reply obligations. Only the exact
participant's delegated attention model may make the social suppression
judgment. Deterministic host code owns identity, routing, context bounds,
scheduling, cancellation, receipts, authorization, and the single output or
effect commit point.

## Current candidate scope

This candidate implements the shared foundation, generic/Discord/Matrix/
Telegram reference adapters, shared Discord MCP transport, CLI, packaging,
Codex room presence, and incomplete Hermes and Claude Code V2 platform
integrations. The Hermes source reuses Nunchi's shared observation, attention,
scheduling, wake, and receipt behavior around the stock participant. It
currently accepts only Hermes 0.19.0 and configured Discord or Telegram rooms.
Other Hermes platforms remain outside Nunchi and keep stock behavior; attempts
to add them to a Nunchi config are rejected.

On configured Hermes rooms, generic Hermes tools are blocked because Hermes
0.19.0 has no final effect hook that can enforce Nunchi's authority checks.
Hermes auto-title is also disabled there because its background work can
outlive the turn. Native typing, voice input, `/thread`, detached participant
commands, and handoff into configured rooms are also disabled where Hermes
0.19.0 cannot keep them inside the admitted opportunity. Reactions after the
participant starts remain guarded; Hermes's pre-model 👀 is blocked until the
shared ACK path owns that signal and its receipt. These are explicit product
gaps, not supported behavior.

Hermes source and focused tests exist, but its installed-runtime and live
platform gates remain open. Earlier Hermes evidence belongs to a superseded
implementation and is not current proof. Hermes gaps are tracked in
[issues #38](https://github.com/mentatzoe/nunchi/issues/38) and
[#42](https://github.com/mentatzoe/nunchi/issues/42), with supported-surface
parity tracked in [#44](https://github.com/mentatzoe/nunchi/issues/44).
Claude Code passes source, deterministic, and clean-installed-artifact checks;
its live real-room evidence and supported-surface closure remain open in
[#39](https://github.com/mentatzoe/nunchi/issues/39) and
[#43](https://github.com/mentatzoe/nunchi/issues/43). See
`evidence/v2/claude-code/README.md` for exactly what is and is not proven.

Shared ACK remains open in [#40](https://github.com/mentatzoe/nunchi/issues/40),
and combined acceptance remains open in
[#41](https://github.com/mentatzoe/nunchi/issues/41). This candidate is partial
and is not verified, release-ready, or V2-complete.

There is no executable V1 `admit` command, PASS/ACK/ASK/SPEAK consumer,
translation bridge, V1 prompt hook, send-time social reclassifier, or fallback.

## Install and inspect

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/nunchi probe
.venv/bin/nunchi-install probe
.venv/bin/nunchi-install init \
  --config-root /secure/operator/config \
  --state-root /secure/operator/state
.venv/bin/nunchi-install verify \
  --config-root /secure/operator/config
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
```

The package metadata exposes a `nunchi` Hermes plugin without adding Hermes as
a Nunchi dependency. When Hermes loads it, the plugin installs its
authenticated dashboard tab automatically for room configuration and V2
receipts without changing Hermes package files. First-time room setup and
private profile-config creation happen in that tab; no separate setup command
is required. Package and installed-runtime acceptance remain separate gates.
See [`integrations/hermes/README.md`](integrations/hermes/README.md).

Configured runtimes require exact SHA-256 pins for participant profiles and
runtime configuration. Credentials are named only by trusted environment
variable names in configuration; room payloads cannot redirect models,
identity, routes, policy, receipt destinations, or output authority.

## Verify

```sh
python3 -m unittest
python3 -m evals.verdict_suite.runner --list
python3 -m evals.verdict_suite.runner
```

The first command runs source-level V2 schema, runtime, authorization,
scheduling, transport, Codex, and adapter coverage. It does not prove a built
package or installed runtime; those require a fresh package build and isolated
installation. Historical V1 tests remain as a visible retirement ledger and
are not part of the executable V2 product suite.

## Product and integration documentation

- [Completion outcome](docs/v2-completion-goal.md)
- [Selected design](docs/architecture/v2-selected-design.md)
- [Portable V2 contract](docs/contracts/nunchi-v2.md)
- [Install and operate](docs/INSTALL.md)
- [Platform interface and conformance](docs/platform-v2.md)
- [Reference adapters](docs/adapters.md)
- [Verification and evidence](docs/v2-verification.md)

Source review, clean-wheel installation, configured probes, deterministic
tests, live provider evaluation, real-room evidence, integration, and release
are distinct claims. The verification record states exactly which have passed.
The final no-completion-before-verification gate is
[issue #41](https://github.com/mentatzoe/nunchi/issues/41).
