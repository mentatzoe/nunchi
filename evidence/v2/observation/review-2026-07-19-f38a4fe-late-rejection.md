# Late immutable review of `f38a4fe` — rejection and current adjudication

**Date received**: 2026-07-19
**Exact review object**: `f38a4fe4cf98fd4d63887e0baf735db7427298f6`
**Verdict**: REJECT
**Method**: immutable Git-object reads, in-memory probes compiled from the exact
object, and tests in a disposable exact-SHA clone. Reviewer side effects: none.

This verdict arrived after later remediation had advanced. It remains pinned to
`f38a4fe`; its mechanisms are adjudicated separately against the current tree.

## HIGH H1 — hard snapshot bytes and false-PASS evidence

The reviewed object included an oversized mandatory trigger, reported
`truncated_by=["bytes"]`, and still marked a budget row PASS despite 156 accepted
bytes under a configured cap of 1.

**Current disposition**: closed by T083–T084. Oversized triggers now reject;
the evaluator handles rejection and unconditionally fails any accepted overrun.

## HIGH H2 — one-shot cursors were not atomic

Two concurrent consumers of one cursor both received the same page and
successor because validation and cursor replacement were not serialized.

**Current disposition**: closed by T089–T090. Provider-owned `RLock` coverage and
barrier-controlled concurrency tests serialize complete continuation transitions.

## HIGH H3 — one-event pagination performed quadratic transient work

The reviewed cursor path copied and scanned the full remaining suffix on every
page. Instrumented operation counts grew by approximately 4× when N doubled.

**Current disposition**: closed by T091–T093. Cursor replay uses a retained
identity map, immutable shared window tuple, numeric position, and O(1)
eviction-frontier check. N=64/128 retained-deque replay visits are 0/0 after
initial window creation.

## HIGH H4 — comparator omitted semantic differences

The comparator mapped events by ID and thereby ignored authoritative order. It
compared only event keys present on both sides, ignored all coverage fields
except continuity, and did not compare actor maps. Exact-object probes returned
`equivalent: true` for reversed order, a one-sided native fact, divergent
coverage/budgets/gaps, and actor divergence.

**Current disposition**: OPEN and reproduced after Phase 20. Bound as Phase 21
T108–T112.

## HIGH H5 — mutable packet contradicted append-only preservation prose

Git history proved non-prefix edits to `handoff.md` despite a claim that earlier
packet text remained exactly recorded.

**Current disposition**: closed by T094/T097. The packet now explicitly labels
itself mutable append-superseded evidence and distinguishes the genuinely
append-only `slice-candidate.md` and `slice-handoff.md` lifecycle ledgers.

## Exact reviewed receipts

The reviewer reproduced 52 focused continuation tests, 127 Observation tests,
46 aggregate rows, 202/202 attempt-6 corpus accounting, 1,376 full-suite tests
with four optional skips, 60 fixtures, clean Ruff/Bandit/governance/diff checks,
and graph hash
`94e0ab99732a95c983dfdc587612e5bd516238ad64fddabd5adc63f0cd89c22d`.
Those nominal passes did not cover H1–H5.

The review also confirmed accepted dependency provenance and the exact eight
downstream lanes plus separate slice-030 projection obligation.

This record is review input only. It is not acceptance, handoff approval,
integration, deployment, release, promotion, or cutover authority.
