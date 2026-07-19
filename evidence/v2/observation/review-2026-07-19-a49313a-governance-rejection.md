# Independent governance review — rejected Phase 26 object

**Date**: 2026-07-19
**Verdict**: REJECT
**Reviewed base**: `fc60858a3810e2f53d9574cce1eb9589bd19b55b`
**Reviewed target**: `a49313a5354259346e1089e759184b9f08735b37`
**Tree**: `d90f47c3e3639a47fbefa1d94cbec2576654e595`
**Parent**: `038900a607bbe60b02660fd4c70ba3aad6525cbd`
**Review lane**: independent read-only governance/task/evidence/lifecycle reviewer

This report preserves the complete blocking substance returned by delegation
`deleg_9bc4f85f`. The parallel implementation reviewer was blocked by the model
provider safety filter and supplied no verdict.

## HIGH-1 — advisory task oracle permits a false lifecycle transition

The slice-owned checker was not invoked by shared governance. It accepted
caller-selected `--allow-open` values, did not validate supersession targets,
accepted noncanonical/missing/extra terminal manifests, and left shared manifest
output labelling every normalized task ID completed.

Observed false-negative probes included:

```text
noncanonical_no_descriptions              PASS (should reject)
noncanonical_checkbox_ignored             PASS (should reject)
terminal_T146_missing                     PASS total=145 (should reject)
arbitrary_checked_T147_added               PASS total=147 (should reject)
bogus_allowed_open_T102                    PASS (should reject)
arbitrary_superseded_key T999              PASS (should reject)
stale successor T107->T999                 PASS (should reject)
```

In a disposable exact-target clone the reviewer removed T146, checked T001–T145,
added candidate-attempt-2 `Tasks complete: YES`, and changed declarations to
`CONVERGED`. Both validators accepted:

```text
SLICE020_TASK_STATE OK total=145 checked=145 superseded=- open=-
governance boundary: OK (SpecKit 0.12.11)
```

The opposite honest path deadlocked because shared lifecycle required every
historical unchecked superseded task literally checked.

Required correction: enforce literal completion and exact terminal graph at the
shared lifecycle authority boundary; distinguish normalized graph identity from
literal completed IDs; close obsolete review gates with truthful checked
supersession text and validate the exact successor.

## HIGH-2 — advertised whole-range scanner omitted changed paths

The exact scan of the reviewed object reported CLEAN over 71 scoped files, but
`scripts/check_slice020_task_state.py`, planning files, and shared changes were
outside its allowlist. A generated matcher-shaped value committed only in the
omitted task checker produced:

```text
SLICE020_SECRET_SCAN CLEAN files=0 additions=0 matchers=4
scanner_scope_probe_exit=0
full_diff_matcher_hits=1
```

Required correction: scan every changed path in the explicit committed
base/head range, retaining redacted findings and no source-controlled bypass.

## HIGH-3 — ordinary handoff history was rewritten and current packet was stale

`evidence/v2/observation/handoff.md` claimed append-only history, but four Git
transitions were non-prefix rewrites:

```text
418432a50815 -> 77a94cf1f56e
cd61dfd649b8 -> 75ff65fa98a3
75ff65fa98a3 -> 247e28202399
ff3c5a2e71bb -> cd8917c56f0d
```

The current packet also stopped at Phase 25 and said T140 was the final gate,
while the reviewed graph used T146. T145's claim that all evidence had been
regenerated was therefore false.

Required correction: do not erase or deny the historical rewrite; record it,
demote the original append-only claim, establish and enforce a new immutable
recovery baseline, and append the current packet state without rewriting the
baseline prefix.

## LOW — exact committed-range diff whitespace

`git diff --check fc60858a..a49313a` reported trailing whitespace in
`evidence/v2/observation/review-2026-07-19-80c1de2-late-rejection.md` lines
3, 4, and 6.

## Passing controls at rejected target

- full repository: 1,446 tests, 4 optional skips;
- Observation: 197 tests;
- governance: 64 tests;
- standard evidence: 53 rows, 0 FAIL;
- adversarial evidence: 34 rows, 0 FAIL;
- verdict inventory: 60;
- Ruff and Bandit clean;
- current declarations ACTIVE; no acceptance record;
- dependency/corpus provenance resolved and byte-identical.

This is rejection evidence only. It grants no candidate, handoff, acceptance,
integration, deployment, release, promotion, or cutover authority.
