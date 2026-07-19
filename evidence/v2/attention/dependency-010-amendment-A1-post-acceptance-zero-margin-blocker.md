# Slice 030 post-amendment dependency blocker — zero-width active margin

**Consumer slice**: `030-v2-core-attention`

**Upstream slice**: `010-v2-contract`

**Status**: `OPEN`

**Severity**: `CRITICAL`

**Discovered by**: codex-session-1

**Discovered on**: 2026-07-19

**Accepted dependency commit**:
`817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`

**Upstream acceptance decision commit**:
`30aba09f13a6752b4c24811da0d8ec772a9d9682`

**Consumer acceptance reference**:
`evidence/v2/attention/dependency-010-amendment-A1-acceptance.md`

**Resolution owner**: `v2-contract-owner`

## Finding

The fresh bound slice-030 analysis independently compared the accepted
dependency with the Zoe-selected technical design at `c834e8c` and found a
separate I-010B representation conflict. The selected
`EffectiveAttentionPolicy` explicitly permits an active
`transition_defer_margin` that is finite within `[0,1]`. The retained inclusive
transition rule therefore routes an exact zero-difference candidate
suppression through `margin-defer` when the configured active margin is `0`.

Accepted `I-010B AttentionDecisionV2@1`, unchanged by amendment A1, requires an
applied `routing_audit.effective_margin` but validates that field only in
`(0,1]`. The schema and stdlib mirror consequently reject the exact
`effective_margin: 0` audit required to represent that selected-policy case.
A direct stdlib-validator probe reproduced:

`routing_audit.effective_margin: must be a finite number within (0, 1]`

Reproduction commands:

```sh
git -C /Volumes/T9/github/aleph-vault show \
  c834e8c:projects/shared/nunchi/technical-design.md | sed -n '777,779p'
rg -n 'within this margin \(inclusive\)|exactly on the boundary|<=' \
  integrations/claude-code/README.md tests/test_defer.py \
  integrations/claude-code/nunchi_prompt_gate.py
python3 -c 'from tests.v2.contract.schema_helpers import make_decision_ok, validate_attention_decision; d=make_decision_ok("SUPPRESS", "DEFER", "margin-defer"); d["routing_audit"]["effective_margin"]=0; print("\n".join(validate_attention_decision(d)))'
```

The authority command prints the selected `[0,1]` domain. The ordinary-path
implementation and retained test/documentation contract show the inclusive
comparison, including the exact-boundary DEFER case. The validator command
prints the rejection above.

This is not resolved by I-010E `@2`; amendment A1 correctly fixes receipt
policy provenance and the explicit `NO_WAKE` override, while leaving I-010B
unchanged. The consumer's amendment acceptance remains valid and immutable for
those exact A1 changes. This later record supersedes only its statement that no
other accepted-dependency blocker remained for slice 030.

## Required resolution

`v2-contract-owner` must provide an authority-conformant, versioned I-010B
resolution that can represent the selected zero-inclusive active-margin policy,
or Zoe must durably narrow that selected policy. Slice 030 must not locally
broaden the accepted schema, silently reject a design-valid zero margin, change
the inclusive comparison, or misreport the route as another valve.

After an exact candidate and acceptance decision exist, slice 030 must
independently review and accept that dependency update and start another fresh
bound planning run.

## Lifecycle effect

Slice 030 remains `PLANNED`; its implementation tasks remain `DORMANT` and
`evidence/v2/attention/slice-activation.md` remains absent. This CRITICAL
contract conflict prevents the zero-CRITICAL/HIGH readiness prerequisite and
therefore prevents `READY` and all later lifecycle states.
