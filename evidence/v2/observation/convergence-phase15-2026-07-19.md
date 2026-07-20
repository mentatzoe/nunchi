# Slice 020 convergence review — attempt 3 cursor-state resource finding

**Date**: 2026-07-19
**Candidate reviewed**: `cd61dfd649b8f03f340b553ac3864183d42fe567`; applicability rechecked against current tip `247e28202399d3962db2711e664b81df120c06b5`
**Review mode**: independent fail-closed stateful-system review plus owner-side reproduction
**Verdict**: REJECT

## S020-A3-01 — HIGH / security — cursor bookkeeping grows quadratically and is never reclaimed

The retention-safe cursor fix stores a new copy of every remaining event ID for
each minted page and retains every consumed cursor indefinitely. One ordinary
one-event-per-page chain over 500 events retained 498 cursor records containing
124,251 event-ID references. The same shape over 2,000 events retained roughly
1,999,000 references. The current monotonic-token and identity-binding fixes
close collision and reindexing defects but do not change this resource shape.

Because handles, active cursor records, capability cursor lists, and cursor
window metadata have no enforced bounds or lifecycle cleanup, a long-lived host
can be exhausted through ordinary repeated pagination/issuance. Describing this
as non-blocking hardening is no longer truthful.

## Required correction

1. Add RED tests proving one pagination chain retains O(window + active-cursor)
   state rather than O(pages × suffix), consumed tokens are deliberately
   one-shot, and exhaustion releases active cursor state.
2. Store one immutable ordered event-ID tuple per active sequence and a position
   cursor into that tuple; reuse it across pages rather than copying suffixes.
3. Enforce configurable global handle and per-handle active-cursor bounds; add
   explicit host revocation and expiry cleanup without changing the accepted
   I-010A/I-010D wire shapes.
4. Add an adversarial eval/resource receipt, regenerate evidence, and rerun the
   complete verification/review matrix before restoring planning PASS claims.

The earlier collision, fixed-window, retention-identity, and evidence-count
findings in the stale `cd61dfd` reviews are already closed by `75ff65f` and
`247e282`; they are not reopened here.

This review does not accept the slice or authorize integration, cutover,
deployment, release, or promotion.
