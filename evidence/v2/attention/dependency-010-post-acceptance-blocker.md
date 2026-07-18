# Slice 030 post-acceptance blocker — I-010E policy provenance

**Consumer slice**: `030-v2-core-attention`

**Upstream slice**: `010-v2-contract`

**Status**: `OPEN`

**Severity**: `HIGH`

**Discovered by**: codex-session-1

**Discovered on**: 2026-07-18

**Accepted candidate commit**: `bff6b463a44c1b9066fc654691042f9550da6c64`

**Handoff packet commit**: `39deb459c7fb18cf7d64dc0edaaaadcca39eae20`

**Consumer acceptance reference**:
`evidence/v2/attention/dependency-010-acceptance.md`

**Resolution owner**: `v2-contract-owner`

## Finding

After the independent consumer acceptance was committed, the bound slice-030
planning analysis compared the accepted schemas with the higher-authority
Zoe-selected technical design at `c834e8c`. That comparison found a contract
representation gap not identified in the earlier packet review:

- the selected `EffectiveAttentionPolicy` requires the effective policy and its
  source to remain inspectable in response audit and receipts;
- an operator-selected `NO_WAKE` operational-failure action is an explicit
  override that must be separately sourced and receipted;
- accepted `I-010E AttentionReceiptV2@1` gives the classifier outcome body only
  `classifier_disposition`, `effective_disposition`, `classifier`,
  `evidence_event_ids`, and `routing_audit`;
- its error body gives only `error.code` and `error.detail`; and
- only its trusted-bypass body contains `policy_provenance`.

The accepted I-010B routing audit does not close the gap: `margin_source` is
required only for `margin-defer` and forbidden on the other routes, so it cannot
serve as general effective-policy provenance or operational-error policy.

The earlier consumer acceptance record remains immutable and is not rewritten.
This later record supersedes only its statement that no upstream acceptance
blocker remained for slice 030; it does not revoke slice 010's terminal
acceptance or authorize slice 030 to edit a 010-owned contract.

## Required resolution

`v2-contract-owner` must supply a versioned, accepted I-010E-compatible
resolution that represents both obligations without free-text conventions or
field misuse. Slice 030 must then independently review and accept the exact new
candidate and packet, update its consumed interface version, and rerun the
bound zero-CRITICAL/HIGH analysis.

Slice 030 will not add local receipt fields, encode provenance in
`error.detail`, reuse classifier identity or `margin_source` for policy
provenance, or omit the selected-design facts.

## Lifecycle effect

Slice 030 remains `PLANNED`; its implementation tasks remain `DORMANT`.
`evidence/v2/attention/slice-activation.md` is absent. This blocker prevents the
zero-CRITICAL/HIGH readiness prerequisite and therefore prevents `READY`,
`ACTIVE`, implementation, convergence, and handoff.
