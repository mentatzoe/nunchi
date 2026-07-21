# Hermes V2 successor handoff candidate — 2026-07-21

## Object identity

- Canonical base: `a03eeb95c7d569895e1171993c7a5748fc250bd8`
- Branch: `codex/v2-hermes-successor-08`
- Final candidate commit: assigned by Git after this record and the complete
  manifest are frozen; reported externally with the manifest SHA-256.

## Scope handed off

This is the complete canonical-base-to-successor packet: implementation,
documentation, tests, evals, generated HM evidence, installed-runtime
provenance, verification record, deletion tombstones, and a successor-owned
manifest. The manifest hashes every present candidate path and records every
removed path as `DELETE`.

The original HIGH findings and follow-up receipt, identity, reload,
dispatch-activation, tool authorization, native reaction, and V1-residue
findings have focused adversarial regressions. Fresh lifecycle, eval,
repository-wide unittest, governance, installed-runtime, and residue checks
are recorded in `verification.md`.

## Runtime disposition

Installed Hermes `0.19.0` at
`f657840e06e03b9552cf2d28175a1e4e4af0210b` was used as an immutable
verification source. The production venv was not modified. The gateway was not
restarted, the plugin was not armed, and no profile or live room was changed.

The installed roles/DM-scope suite is GREEN (`15 passed in 0.18s`) when the
test environment unsets only inherited `DISCORD_ALLOWED_CHANNELS` and
`DISCORD_IGNORED_CHANNELS`. The earlier positive-control failure was environment
contamination and is not preserved as an upstream limitation.

## Review boundary

Review the entire exact diff from
`a03eeb95c7d569895e1171993c7a5748fc250bd8` to the externally reported final
candidate commit, and verify `evidence/v2/hermes/candidate-files.sha256` against
that object. Any write invalidates the review and requires a new manifest and
review request.

This handoff does not claim lifecycle activation, installed cutover, or
acceptance. The packet owner requests independent review and must not accept or
integrate its own packet.
