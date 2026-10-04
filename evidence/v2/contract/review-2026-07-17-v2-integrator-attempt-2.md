# v2-integrator review — slice 010 attempt-2 candidate rejection

**Slice**: `010-v2-contract`

**Candidate commit**: `001fdf85acd5098264c4975559c97114aa7278af`

**Handoff packet commit**: `5383e9f3a5e9c20c08ab54395f4ff370128f03de`

**Reviewed by**: v2-integrator

**Reviewed on**: 2026-07-17

**Decision**: REJECTED

## Decision basis

Attempt 2 repairs the three blockers from the first rejection: the full packet
baseline is green, I-010B now carries the conditional legacy-confidence rule
and routing audit, and I-010E rejects a forged per-record stage/writer pairing.
The candidate still cannot be accepted because the public contracts do not
encode the higher-authority selected V2 contract, and the exact packet is not
commit-consistent.

### R4 — the five public interfaces do not encode the selected V2 contract (CRITICAL)

The Zoe-selected Aleph Vault technical design at `c834e8c` defines the clean
V2 request, continuation, participant-wake, decision, and staged-receipt
contracts. The proposed `@1` schemas replace required facts and capabilities
with materially narrower local shapes:

- `schemas/v2/attention-request.schema.json` cannot represent the selected
  room platform/name/kind facts, actor map, typed message/reaction/membership
  event union, reaction add/remove operation, membership subject/causal actor
  and literal membership scope, or the selected coverage facts
  (`has_more_before`, `has_more_after`, `has_gaps`, `truncated_by`,
  `has_restart_gap`, and per-event-type visibility). It instead invents a
  generic event with `kind: reply|thread`, requires author/mention fields on
  every event, and collapses coverage into unrelated enums. This loses native
  structure rather than preserving it.
- `schemas/v2/context-continuation.schema.json` does not define the selected
  continuation capability (`handle_id`, exact `bound_to`, before/after/around
  capabilities, per-fetch caps, optional expiry). Its fetch request has no
  direction or anchor semantics, and its page omits the selected room and
  continuity-scope identity, direction, anchor, actor map, and page binding.
- `schemas/v2/participant-wake.schema.json` wraps the classifier-safe request
  projection as `observation` but has no host-only continuation capability for
  the woken participant. The selected contract instead materializes self,
  room, actors, events, trigger, coverage, optional continuation authority,
  and a separate `attention` object in the wake packet.
- `schemas/v2/attention-receipt.schema.json` omits required staged telemetry.
  The observation stage lacks schema/trigger/continuity IDs, snapshot sizes,
  coverage, and included event IDs; the attention stage lacks classifier
  identity/evidence and transition-valve facts; the participant-host stage
  lacks wake source, packet sizes, delivered event IDs, expansion calls, and
  invocation/unknown outcome; the transport stage lacks transport hygiene and
  routing/send facts. The stage/writer fix is necessary but not sufficient.
- `schemas/v2/attention-decision.schema.json` retains incompatible local
  field shapes as the public contract (`interface`/`version`, `routing`,
  `legacy_confidence`, restricted classifier audit, mandatory request ID on
  error) rather than the selected `routing_audit`,
  `legacy_verdict_confidences`, classifier `name`/provider/model audit, and
  optional request ID on pre-validation error. Attempt 2 fixed R2 inside the
  local shape but did not reconcile the whole interface with its authority.

Targeted stdlib-adapter probes confirmed that representative selected-design
documents are rejected: the selected `AttentionRequestV2` produced 41 errors,
the selected directional `ContextFetch` was rejected, the selected
`ParticipantWake` produced 16 errors, and representative selected observation
and participant-host receipt stages produced 13 and 11 errors. A self-consistent
corpus for the narrowed schemas does not establish conformance to the selected
contract.

### R5 — the attempt-2 packet names three incompatible commit identities (CRITICAL)

The attempt-2 section of `evidence/v2/contract/handoff.md` names
`2ab95be81e193d01b91ff078decfc586cf4bf357` as the exact candidate and leaves
the handoff packet commit as a future value. The lifecycle candidate and
handoff streams instead name
`001fdf85acd5098264c4975559c97114aa7278af`, while the actual delivered packet
is commit `5383e9f3a5e9c20c08ab54395f4ff370128f03de`.

This violates the exact-candidate and complete-packet requirements in the
constitution, program handoff contract, and slice SC-005. Product bytes happen
to be unchanged between the first two commits, but exact evidence identity is
the acceptance boundary and cannot be inferred from tree similarity.

### R6 — the handoff declaration contradicts its own execution status (HIGH)

All three slice declarations say `Slice state: HANDOFF_READY`, but
`specs/010-v2-contract/tasks.md` says `Execution status: EXECUTABLE — the slice
is ACTIVE`. That claim is false at the exact packet commit and will become
false again at every future handoff if left state-specific. The task graph,
declarations, and lifecycle evidence must agree before acceptance.

## Verification performed

- At packet commit `5383e9f3a5e9c20c08ab54395f4ff370128f03de`:
  `python3 -m unittest` — PASS, 1225 tests, 11 skipped.
- At the same packet commit:
  `uv run --offline --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'`
  — PASS, 167 tests, 0 skipped.
- `python3 scripts/check_governance.py --check-cli` — PASS, SpecKit 0.12.11.
- `python3 -m evals.verdict_suite.runner --list` — PASS, 60 V1 fixtures
  discovered.
- `git diff --check` for activation-to-candidate and candidate-to-packet —
  PASS.
- Attempt-1 blockers R1, R2, and R3 were re-probed and are fixed in attempt 2.
- Manual contract comparison and targeted stdlib-adapter probes against the
  exact selected Vault shapes — FAIL as described in R4.

## Required rework path

The source owner must return the slice declarations to `ACTIVE` and start a
new bound `run speckit` for `specs/010-v2-contract`; the completed attempt-2
handoff run must not be resumed. Preserve both prior attempts and both
rejections.

The new run must append tasks that reconcile all five interfaces with the
exact selected design before updating schemas, runtime validators, corpora,
evidence, and `docs/contracts/nunchi-v2.md`. Add authority-conformance cases
that validate the selected request example and cover the complete typed event,
coverage, continuation capability/fetch/page, participant-wake, decision, and
four-stage receipt fields; these must fail before the schema repair and pass
after it. Then append a new packet whose lifecycle candidate, packet input,
corpus revision, and actual handoff packet commit are explicitly and
consistently pinned, and whose execution-status wording agrees with the live
handoff state.
