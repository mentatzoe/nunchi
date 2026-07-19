# Independent dual rejection — Phase 27 object `abad8d85`

**Date**: 2026-07-19
**Verdict**: REJECT
**Reviewed base**: `fc60858a3810e2f53d9574cce1eb9589bd19b55b`
**Reviewed target**: `abad8d85e8150bfd2716ab77ebb3791827591bf1`
**Tree**: `89718e3787592cc9f51d7414387221d664947c70`
**Parent**: `a49313a5354259346e1089e759184b9f08735b37`
**Review lanes**: independent implementation/robustness and governance/lifecycle

Both exact-object reviewers rejected the Phase 27 object. Their independent
passing controls agreed on immutable identity, 49-commit activation range, 82
changed paths, clean exact scan, clean full test matrix, normalized graph hash,
current ACTIVE declarations, open T103/T153, absence of acceptance evidence, and
working handoff recovery-prefix enforcement.

## Blocking findings

### P28-H1 — malformed checkbox-shaped task rows remain invisible

`_validated_task_entries()` considered only malformed lines matching
`^- \[[^]]*\]\s+T?\d`. Rows such as:

```text
- [ ] TASK154 unresolved release blocker
- [ ] T 154 hidden malformed task
```

were absent from the parsed manifest. Depending on the probe, shared lifecycle,
the standalone diagnostic, or `--task-manifest` could still return success. One
reviewer reproduced:

```text
malformed_extra_parsed_count=153
malformed_extra_candidate_errors=[]
malformed_extra_converged_policy=[]
```

### P28-H2 — exact terminal identity is not bound to the candidate commit

Current-tree policy enforced exact T001–T153, but candidate validation only
required every task in whatever referenced manifest it parsed to be checked.
All-checked candidate commits with T001–T152 or T001–T154 returned no candidate
completion error. A later candidate record could therefore point away from the
terminal graph supposedly reviewed.

### P28-H3 — supersession truth remains outside shared lifecycle authority

Only `check_slice020_task_state.py` validated exact supersession targets. Shared
`CONVERGED` policy accepted T107 rewritten from `superseded by T153` to T152 or
T999. The disposable full-transition probe returned:

```text
python3 scripts/check_governance.py
# exit 0: governance boundary OK

python3 scripts/check_slice020_task_state.py --tasks ...
# exit 1: superseded gate T107 must name exact successor T153
```

Shared policy must validate the exact key/target chain, ordering, checked state,
and durable “object not approved” semantics.

### P28-H4 — referenced rejection evidence can be erased

Replacing `review-2026-07-19-a49313a-governance-rejection.md` with two lines and
committing still left governance green. Review rejection records were neither
registered nor replayed as immutable evidence.

The Phase 27 object also changed three trailing-space bytes in
`review-2026-07-19-80c1de2-late-rejection.md`. Its semantic verdict survived,
but the byte rewrite was not disclosed while T147 claimed exact preservation.
That historical violation requires an explicit recovery baseline rather than
retroactive immutability claims.

## Non-blocking finding

The scanner docstring still said `slice020-secret-fixture` suppressed its own
line. The implementation and regression correctly provide no suppression.

## Passing controls

- full repository: 1,452 tests, OK, 4 skips;
- Observation: 200 tests, OK;
- governance/scanner/task/docs: 91 tests, OK;
- exact all-path scanner: 82/82 changed paths, 13,259 additions, clean;
- secret finding content remained redacted;
- exact-range whitespace, Ruff, Bandit, pinned governance CLI: clean;
- handoff recovery baseline rejected rewrites and accepted prefix appends;
- standard/adversarial evidence: 53 + 34 rows, zero failures.

This rejection applies only to exact `abad8d85e8150bfd2716ab77ebb3791827591bf1`.
It grants no candidate, handoff, acceptance, integration, deployment, release,
promotion, or cutover authority.
