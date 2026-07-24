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
and Codex room presence. Hermes and Claude Code are explicitly excluded: this
candidate does not implement, repair, arm, install, or live-test their V2
integrations.

There is no executable V1 `admit` command, PASS/ACK/ASK/SPEAK consumer,
translation bridge, prompt hook, send-time social reclassifier, or fallback.

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

The first command runs the V2 schema oracle plus adversarial runtime,
authorization, scheduling, transport, Codex, adapter, and installed-artifact
coverage. Historical V1 tests remain as a visible retirement ledger and are
not part of the executable V2 product suite.

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
