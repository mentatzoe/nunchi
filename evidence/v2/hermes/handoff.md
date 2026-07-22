# Hermes V2 pre-activation source-review packet — not a canonical handoff

## Object identity

- Installed Hermes version: `0.19.0`
- Installed Hermes commit: `279be8211d8347cc3500b9a78c6a0f8cb4d92a6a`
- Candidate base: `8e64746970f9910d03b372291c5aa173883e869f`
- Branch: `v2/hermes`
- Final draft commit: assigned by Git after this record and the complete
  manifest are frozen; reported externally with the manifest SHA-256.

## Scope handed off

This packet contains the implementation, documentation, tests, evals,
regenerated HM evidence, installed-runtime provenance, verification record,
deletion tombstones, and a draft-owned manifest. The manifest hashes every
changed path except its self-referential manifest file and records every removed
path as `DELETE`; the review request reports the manifest's own SHA-256
separately.

The successor adds focused regressions for strict authorization uncertainty,
redispatch revocation cleanup, pre-transport `unknown` participant receipts,
native downstream error preservation, globally atomic approval admission and
audit persistence, semantically bound installed-source provenance, installed
version and full-status allowlisting, tri-state Telegram scope failure, host
teardown/topic-recovery ordering plus an execution-time teardown recheck,
transactional rollback of every class patch and public callback registration,
zero-argument host executors, and concurrent approval capacity reservation.

## Runtime disposition

Installed Hermes `0.19.0` at
`279be8211d8347cc3500b9a78c6a0f8cb4d92a6a` was used as an immutable
verification source. The production venv was not modified. The gateway was not
restarted, the plugin was not armed, and no profile or live room was changed.

The exact isolated installed private-seam run is GREEN (`83 passed`). HM-06
drives the actual installed `PluginManager._load_plugin`/`PluginContext` path and
proves late class-wrapper and after-append callback rollback preserves registry
and pre-existing target-name list identity/content before successful exact
registration. It also proves
the draft's fail-closed containment and preservation of native downstream
executor errors through installed Hermes middleware.

## Review boundary

Review the entire exact diff from
`8e64746970f9910d03b372291c5aa173883e869f` to the externally reported final
draft commit, and verify `evidence/v2/hermes/candidate-files.sha256` against
that object. Any write invalidates the review and requires a new manifest and
review request. Historical rejected tree identities remain evidence only; this
successor requires fresh technical review on its exact immutable object.

This packet is not a governed candidate or handoff and does not claim lifecycle
activation, installed cutover, or acceptance. Slice 060 remains `PLANNED`;
dependency acceptance and canonical activation/candidate/handoff records remain
absent. It exists only to request technical draft review from Codex. It must not
be integrated or promoted until the program/integrator lane reconciles those
canonical lifecycle gates.
