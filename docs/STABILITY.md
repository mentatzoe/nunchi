# V2 stability boundary

The stable public boundary is the closed V2 contract in
`docs/contracts/nunchi-v2.md`, the runtime validators in
`nunchi.v2_contracts`, and these installed commands:

- `nunchi attention|validate|probe`
- `nunchi-install init|verify|probe`
- `nunchi-channel`
- `nunchi-discord`
- `nunchi-matrix`
- `nunchi-telegram`
- `nunchi-mcp-discord`
- `nunchi-codex-room-runner`
- `nunchi-conformance`
- `nunchi-hermes-v2-config`
- `nunchi-hermes-v2-host-patch`

The Hermes host-patch command is stable only for the exact bundled manifest and
the untouched `hermes-agent==0.19.0` runtime distribution built from Hermes
`v2026.7.20` commit
`3ef6bbd201263d354fd83ec55b3c306ded2eb72a`; host drift fails closed. The seam
is a Nunchi-owned private compatibility layer shipped in the wheel, not an
upstream Hermes API guarantee.

No V1 request, verdict, hook, responder, configuration, or exit-code contract
is stable or executable.

## Compatibility rules

- Contract documents are closed; unknown fields fail validation.
- Native IDs remain strings and canonical IDs are platform-qualified.
- `self.actor_id` is exact transport/host binding, independent of aliases,
  names, and roles.
- Attention results are `SUPPRESS`, `WAKE`, or `DEFER`; bypass and operational
  error are distinct non-social statuses.
- Receipt ownership and ordering are immutable.
- Continuation authority is host-only, bound, bounded, expiring, and discarded
  on restart.
- Privileged authorization binds the exact requester origin, participant,
  route, capability, resource, operation digest, policy revision, expiry,
  approval, revocation state, and one-use effect commit.
- Platform-native absences are explicit capability facts, never invented.

A change to any of these requires a contract version change, conformance
updates, and downstream review.
