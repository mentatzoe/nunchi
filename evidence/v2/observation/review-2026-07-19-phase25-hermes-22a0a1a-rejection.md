# Independent rejection — `22a0a1a`

**Verdict**: REJECT
**Target**: `22a0a1ab9a996e82ec625ce73e301023889209e4`
**Tree**: `ea186b389424f761a1cc5cbac8faac32f8c28484`
**Review mode**: immutable Git-object reads and detached direct probes; no
repository writes.
**Boundary**: review input only; not acceptance, convergence, handoff,
integration, deployment, release, promotion, or cutover authority.

## HIGH — receipt caller-memory TOCTOU

`build_observation_receipt()` validates and compares caller-owned `request`, then
computes the receipt from that same mutable object. A barrier mutation after the
equality check changed issued event bytes from 102 to an attested 301 and
consumed the pending receipt. Existing tests did not call the public method with
the mutable object across the barrier.

## HIGH — relation-gap truth is trigger-only and absent from continuation

Snapshot relation closure and gap computation inspect only the trigger event. A
nearby included reply/thread/reaction can therefore reference an unavailable
target while `has_gaps` remains false. Continuation pages use only provider
retention eviction for `has_gaps` and never inspect relation targets. Direct
probes reproduced both missing-target and budget-excluded continuation pages as
falsely gap-free.

## MEDIUM — known restart gaps remain evaluator side-channel state

The `known-gap` reference provider stores dropped IDs only in
`known_gap_event_ids`, while the normalized snapshot continues to report
`has_restart_gap: false`. S05 validates the side channel instead of the wire
coverage, contradicting FR-007/SC-005.

## MEDIUM — exact activation-range diff check was not clean

The Phase 25 receipt recorded `git diff --check` as clean after checking only the
working tree. Exact activation-to-candidate range checking found trailing
whitespace in `review-2026-07-19-80c1de2-late-rejection.md` and exited 2.

## Nonblocking nit

CAP-S13 page fixtures omit required closed-page `room_id`,
`continuity_scope_id`, and `actors`, so the evidence row does not itself exercise
a closed I-010D page even though production pages self-validate.

## Otherwise-confirmed receipts

The reviewer independently confirmed 31 focused tests, 182 Observation tests,
53 aggregate PASS rows, 19 adversarial PASS rows, corpus 202/202 with exact
digest, 13 docs tests, 1,431 repository tests with four optional skips, 60
fixtures, Ruff, production Bandit, governance, scanner cleanliness, task graph,
and push identity. Those green receipts do not override the findings above.

Full raw review output is retained by Hermes at
`/Users/zmll/.hermes/cache/delegation/subagent-summary-0-20260719_140341_653300.txt`.
