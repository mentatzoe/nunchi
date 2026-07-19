# Slice 030 Activation

**Slice**: `030-v2-core-attention`

**Status**: READY

**Assigned participant / source**: codex-session-1 — evidence/governance/assignments/codex-session-1-v2-core-owner-2026-07-16.md

**Authority record**: `evidence/governance/v2-implementation-authorization.md`

**Accepted dependencies**: `010`

**Dependency commits**: `010=26a6b531fa146ba1f1f5fcd1c4d191041b141301`

**Dependency acceptance references**: `010=evidence/v2/attention/dependency-010-amendment-A2-acceptance.md`

**Analysis result**: PASS — zero CRITICAL/HIGH findings

**Branch**: `v2/core-attention`

**Worktree**: `.worktrees/v2-core-attention/`

**Starting commit**: `cd95c4157cb03ac6fd53dd79f751679d5fd812ed`

**Interfaces**: I-010A, I-010B, I-010D, I-010E, I-030A

**Acceptance scenes**: S04, S05, S06, S08, S09, S16, 030-CLI

**Evidence targets**: `evidence/v2/attention/README.md`, `evidence/v2/attention/core-cli-parity.jsonl`, `evidence/v2/attention/defer-canary/protocol.md`, `evidence/v2/attention/handoff.md`, `evidence/v2/attention/model-comparison/results.jsonl`, `evidence/v2/attention/s04-suppression-scars/results.jsonl`, `evidence/v2/attention/s05-governed-suppress.jsonl`, `evidence/v2/attention/s08-defer-transition/results.jsonl`, `evidence/v2/attention/verification.md`

**Documentation scope**: `CHANGELOG.md`, `README.md`, `docs/INSTALL.md`, `docs/STABILITY.md`, `docs/adapters.md`, `docs/architecture/v2-selected-design.md`, `docs/attention/v2.md`, `docs/contracts/channel-adapter-v1.md`, `docs/contracts/verdict-suite-data-model-v1.md`, `docs/contracts/verdict-suite-requirements-v1.md`, `docs/evaluations/verdict-suite-runner.md`, `docs/evaluations/verdict-suite.md`, `docs/integration.md`, `integrations/claude-code/DEFER_EVAL.md`, `integrations/claude-code/README.md`, `integrations/codex/README.md`, `integrations/hermes/README.md`, `integrations/mcp-discord/DESIGN.md`, `integrations/mcp-discord/README.md`

**Initial task IDs**: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027

**Initial tasks SHA256**: d6bd19d5cfdc9c3a5f33b4e43493acadbfcea2d1c88b9c5edb4f6f4d3f4a6f2a

## Prerequisite Attestation

- The non-symlink assignment record contains exactly one `Assignee`, `Lane`,
  `Assigned by`, `Assigned on`, and `Authority reference`. Zoe is the assigner,
  so no delegated-assigner fields are required.
- The implementation-authority record is `AUTHORIZED`, names Zoe, was recorded
  by `v2-program-owner`, and enumerates exactly all eleven slices `010` through
  `110`. It copies the external grant; it does not grant authority itself.
- Slice 010 terminally accepted its attempt-6 candidate, and the canonical
  append-only amendment ledger then records accepted A1 and A2. This consumer's
  separate A2 acceptance binds exact effective candidate
  `26a6b531fa146ba1f1f5fcd1c4d191041b141301`, carrying I-010A @1, I-010B @2,
  I-010D @1, and I-010E @2. Earlier consumer acceptances and blockers remain
  immutable history.
- Fresh bound planning run `nunchi-plan-030-20260719T114955523641Z`
  (`claude`) completed. Analysis evidence at
  `evidence/v2/attention/analysis-2026-07-19.md` reports zero scoped
  CRITICAL/HIGH findings. All 190 requirement-quality items are checked, the
  47-path documentation denominator is intact, and T001–T027 remain unchecked.
- The amendment-aware dependency resolution is recorded at
  `evidence/v2/attention/dependency-010-amendment-A2-readiness-validator-resolution.md`.
  The separate stale program interface registry remains the recorded
  `NON_BLOCKING_HANDOFF` to `v2-program-owner`; this slice neither edits nor
  claims completion of it.
- Zoe's narrow identity-separation waiver is durably copied at
  `evidence/v2/attention/identity-separation-waiver.md`. It permits the assigned
  owner to perform planning/readiness reviews but waives no other gate.
- The sink-persistence rule is conservative: `not-persisted` is limited to a
  closed-contract pre-write rejection whose semantics guarantee no durable
  side effect; generic, unrecognized typed, timeout/cancellation, and post-
  dispatch failures are `unknown`; an `unknown` result never triggers a non-
  idempotent retry.
- The interface enumeration includes I-010D because the bound plan names the
  downstream continuation contract while explicitly excluding it from the
  slice-030 engine input. The consumed interfaces are I-010A/B/E, and I-030A is
  the only planned produced interface.

## Frozen Baseline and Change Boundary

At starting commit `cd95c4157cb03ac6fd53dd79f751679d5fd812ed`:

- `python3 scripts/check_governance.py --check-cli` — PASS,
  `governance boundary + CLI: OK (SpecKit 0.12.11)`;
- `python3 -m unittest` — PASS, 1261 tests, 11 skipped, 0 failures;
- `python3 -m unittest tests.test_governance` — PASS, 72 tests;
- `python3 -m evals.verdict_suite.runner --list` — PASS, 60 fixtures;
- `python3 scripts/check_governance.py --task-manifest specs/030-v2-core-attention`
  — T001–T027, no completed IDs, task hash equal to the initial hash above; and
- `git diff --check` — PASS.

The ordered tracked pre-030 test inventory contains 59 files. The canonical
index command

```sh
git ls-files -s 'tests/**' ':!tests/v2/attention/**' | sort | env LC_ALL=C LANG=C shasum -a 256
```

hashes to
`d6f2e03d120423c771da98353b692d50c089d22bab757719c7d9f3144297249a`.
The ordered paths are:

```text
tests/__init__.py
tests/fixtures/.gitkeep
tests/fixtures/ack.json
tests/fixtures/ask.json
tests/fixtures/false_ack_comment_back.json
tests/fixtures/false_pass_contradicted_done.json
tests/fixtures/false_pass_no_corroboration.json
tests/fixtures/invalid_classifier.json
tests/fixtures/pass.json
tests/fixtures/speak.json
tests/fixtures/speak_cli_precedence.json
tests/fixtures/speak_with_classifier.json
tests/hook_sandbox.py
tests/provider_helpers.py
tests/test_adapter_channel.py
tests/test_classifiers.py
tests/test_claude_code_prompt_gate.py
tests/test_cli.py
tests/test_codex_config_app.py
tests/test_codex_plugin_bundle.py
tests/test_codex_prompt_gate.py
tests/test_codex_room_runner.py
tests/test_codex_runtime_state.py
tests/test_codex_send_gate.py
tests/test_codex_smoke_evidence.py
tests/test_core.py
tests/test_dashboard_asset_safety.py
tests/test_defer.py
tests/test_discord_adapter.py
tests/test_docs_truthfulness.py
tests/test_governance.py
tests/test_hermes_integration.py
tests/test_hermes_nunchi_gate_quiet_chatter.py
tests/test_hermes_state.py
tests/test_history_buffer.py
tests/test_install.py
tests/test_integration_entrypoints.py
tests/test_matrix_adapter.py
tests/test_mcp_discord_gateway.py
tests/test_mcp_discord_server.py
tests/test_no_home_writes.py
tests/test_no_second_judgment.py
tests/test_pass_corroboration.py
tests/test_provider_classifier.py
tests/test_provider_redirection.py
tests/test_schema.py
tests/test_send_backstop.py
tests/test_sentinel_forgery.py
tests/test_slash_command_authz.py
tests/test_slice_workflow_runner.py
tests/test_telegram_adapter.py
tests/test_verdict_suite.py
tests/v2/__init__.py
tests/v2/contract/__init__.py
tests/v2/contract/schema_helpers.py
tests/v2/contract/test_attention_decision.py
tests/v2/contract/test_attention_request.py
tests/v2/contract/test_context_and_receipt.py
tests/v2/contract/test_participant_wake.py
```

The allowed slice-030 product change boundary is:

- `src/nunchi/core.py`, `src/nunchi/cli.py`,
  `src/nunchi/classifiers.py`, `src/nunchi/models.py`, and
  `src/nunchi/schema.py`;
- `tests/v2/attention/`;
- `evals/v2/attention/`;
- `evidence/v2/attention/`; and
- the eight exact `UPDATE` paths in the frozen documentation matrix below.

Contract schemas under `schemas/v2/`, pre-030 tests, adapters/harnesses,
`src/nunchi/__init__.py`, and every `NO_IMPACT` or `HANDOFF` path below remain
outside this slice's implementation write boundary. Only slice 110 may publish
I-030A through current public exports or atomically cut over V2.

## Frozen Documentation Matrix

### UPDATE — 8

- `evidence/README.md`
- `evidence/verdict-suite/README.md`
- `evidence/v2/attention/README.md`
- `docs/attention/v2.md`
- `docs/contracts/verdict-suite-data-model-v1.md`
- `docs/contracts/verdict-suite-requirements-v1.md`
- `docs/evaluations/verdict-suite.md`
- `docs/evaluations/verdict-suite-runner.md`

### NO_IMPACT — 17

- `evidence/v2/contract/README.md`
- `docs/archive/v1/README.md`
- `docs/archive/v1/admission-classifier/contract.md`
- `docs/archive/v1/admission-classifier/data-model.md`
- `docs/archive/v1/admission-classifier/quickstart.md`
- `docs/archive/v1/core-cli/contract.md`
- `docs/archive/v1/core-cli/data-model.md`
- `docs/archive/v1/core-cli/quickstart.md`
- `docs/contracts/nunchi-v2.md`
- `docs/governance/execution-spine.md`
- `docs/integrations/hermes-core-patch.md`
- `docs/integrations/hermes-core-patch-test-plan.md`
- `integrations/claude-code/transport-patch/README.md`
- `integrations/codex/nunchi-codex/.mcp.json`
- `integrations/hermes/nunchi-gate/dashboard/manifest.json`
- `integrations/mcp-discord/DESIGN.md`
- `integrations/mcp-discord/README.md`

### HANDOFF — 22

- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `CHANGELOG.md`
- `docs/INSTALL.md`
- `docs/STABILITY.md`
- `docs/adapters.md`
- `docs/architecture/v2-selected-design.md`
- `docs/contracts/channel-adapter-v1.md`
- `docs/integration.md`
- `examples/loader-snippet.md`
- `examples/generic_host_demo.py`
- `examples/read_the_room_demo.py`
- `profiles/open-floor.md`
- `integrations/claude-code/DEFER_EVAL.md`
- `integrations/claude-code/README.md`
- `integrations/claude-code/nunchi-gate.env.example`
- `integrations/codex/README.md`
- `integrations/codex/nunchi-codex/.codex-plugin/plugin.json`
- `integrations/codex/nunchi-codex/hooks/hooks.json`
- `integrations/hermes/README.md`
- `integrations/hermes/nunchi-gate/plugin.yaml`

## State Boundary

This immutable record establishes slice `READY` only. Every implementation
checkbox remains unchecked and dormant. The assigned participant must start a
fresh bound delivery workflow and separately declare `ACTIVE` before T001 or
any product edit. This record establishes no candidate, convergence,
documentation freshness, handoff readiness, recipient acceptance, integration,
cutover, release, or promotion.
