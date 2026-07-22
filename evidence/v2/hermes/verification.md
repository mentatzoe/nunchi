# Hermes V2 pre-activation draft verification — 2026-07-22

## Draft identity and scope

- Candidate base: `8e64746970f9910d03b372291c5aa173883e869f`
- Branch: `v2/hermes`
- Final draft commit: assigned by Git after this record and the complete
  manifest are frozen; reported externally with the manifest SHA-256.
- Installed Hermes source: `/Users/zmll/.hermes/hermes-agent`
- Installed Hermes commit: `279be8211d8347cc3500b9a78c6a0f8cb4d92a6a`
- Installed Hermes version: `0.19.0`

The branch incorporates the exact current `origin/codex/v2-integration` tip and
its merged 040/050 state. This is a technical draft-review object, not a
canonical Slice 060 candidate or handoff. It does not claim installation,
activation, transport delivery, or lifecycle authority.

## Independent-review remediation

A predecessor staged candidate failed independent review. Its disposition is
not reused. This successor adds focused regression coverage and implementation
repairs for every reported blocker:

1. Gateway authorization exceptions and truthy non-booleans now fail closed.
   Literal `False` preserves ordinary Hermes denial only before Nunchi owns a
   dispatch; redispatch revocation aborts its reserved ticket, scheduler
   generation, host-delivery record, and deferred work before returning skip.
2. Participant-host receipts record immutable `unknown` before adapter-native
   transport. They no longer claim `sent` before the transport owner knows it.
3. Public tool middleware contains Nunchi failures only before downstream
   execution. Native executor failures retain Hermes' original error semantics
   after exactly one invocation; zero-argument and payload-taking executors both
   preserve their host signatures.
4. Global pending-approval capacity is reserved atomically before coordinator
   proposal/audit persistence. Capacity rejection cannot leave a phantom
   `APPROVAL_REQUIRED` record, including under a forced two-thread interleaving.
5. Installed-source provenance binds version, host commit, and candidate base to
   exact named fields, rejects role swaps and contradictory commit identities,
   verifies package version, and rejects tracked drift or any untracked path
   other than the acknowledged `.install_method` marker.
6. Telegram configuration/scope lookup is tri-state. The exact-event wrapper
   honors installed teardown/drop fencing and applies installed topic recovery
   before deciding scope, then rechecks the teardown fence inside its scheduled
   coroutine immediately before dispatch. Recovered in-scope events cannot enter
   lossy text batching or outlive a teardown that wins the next event-loop turn.
7. Every required host class is snapshotted before mutation. Any later wrapper
   or registration failure restores the complete class patch set and the exact
   installed plugin-manager hook/middleware lists before the error escapes.
   Public hooks and middleware register only after all wrappers.

The author reports observing focused cases RED before the corresponding
implementation changes and GREEN afterward; the frozen packet preserves only
the final regression tests, not independently auditable RED-run receipts. The
concurrency test durably forces an in-flight capacity reservation before the
second proposal.

## Fresh command results

- Complete Hermes implementation plus evaluation: `Ran 119 tests in 3.589s` —
  `OK`.
- Repository-wide controlled unittest discovery under Python 3.11, temporary
  `HOME`, empty `HERMES_HOME`, and `PYTHONDONTWRITEBYTECODE=1`:
  `Ran 1139 tests in 39.786s` — `OK (skipped=9)`.
- HM-01 through HM-06 regenerated from the pinned installed source: all `PASS`.
- Installed private-seam pytest selection: `83 passed in 10.81s`.
- Draft-owned Ruff selection: `All checks passed!`.
- Governance boundary and CLI:
  `governance boundary + CLI: OK (SpecKit 0.12.11)`.
- `git diff --check`: `OK`.
- Installed fixture identity recheck: expected commit and version, clean tracked
  status.

The draft packet verifier is run only after the manifest is regenerated;
its exact result and the final manifest digest are reported with the immutable
review request rather than predeclared in this self-hashed record.

## HM-01 through HM-06

All six installed-source scenes returned `PASS`:

- HM-01 exact identity
- HM-02 disposition routing
- HM-03 later-hearing restart
- HM-04 shared Discord
- HM-05 Telegram capability, including absent-timestamp projection
- HM-06 installed provenance, registration and late-failure rollback against
  actual installed `PluginManager._load_plugin`/`PluginContext`, with registry
  and pre-existing target-name callback-list identity/content preservation;
  fail-closed containment; and
  native downstream-error preservation through installed middleware

The committed JSONL rows carry the evidence grade for each scene. HM-04 and
HM-05 remain deterministic synthetic evidence, not live transport claims.

## Installed Hermes seams

The installed checkout was inspected and tested without copying candidate code
into it, modifying its production virtual environment, changing a profile, or
restarting a gateway. Its tracked source remained clean; full status validation
confirmed `.install_method` as the only untracked path. See
`installed-runtime.md` for the exact test scope and method.

## Lifecycle boundary

Slice 060 remains `PLANNED`. Accepted 060-owned upstream dependency records and
canonical activation/candidate/handoff records are absent; under the governing
contract, this implementation has no integration authority. No task checkbox
or lifecycle state is changed by this packet. Review is requested only as draft
technical feedback from Codex. Program/integrator reconciliation and canonical
activation remain mandatory before this work can become a governed candidate.
