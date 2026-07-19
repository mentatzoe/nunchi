# Independent rejection — `2b10abb`

**Verdict**: REJECT
**Target**: `2b10abb0b9b7d4dff802e08b36030995263cf520`
**Tree**: `a98b6fb8d34c647bcc27bf42de0c4b7a701860bd`
**Review mode**: read-only exact-range review in detached worktree with independent checks
**Boundary**: review input only; not acceptance, convergence, handoff, integration, deployment, release, promotion, or cutover authority.

## MEDIUM — blocking: S13 validates before final mutation

`evals/v2/observation/run_scenes.py` validates synthesized continuation pages before applying page mutations. `CAP-S13-008` then assigns `next_cursor=null`, which is invalid when the field is present, and passes that invalid object to `compare_pages()`.

Observed at the comparison seam:

```text
left=[]
right=['next_cursor: must be a non-empty string']
```

Required correction: encode cursor absence with mutation `{"op":"remove"}` and validate both final mutated pages immediately before comparison.

## MEDIUM — blocking: relation target priority depends on hash seed

Snapshot assembly converts the ordered trigger relation list into a `set`. With a cap admitting only one of reply and thread targets, identical input selects different targets across `PYTHONHASHSEED` values:

```text
1 reply-target,trigger
2 thread-target,trigger
3 reply-target,trigger
4 thread-target,trigger
```

Required correction: preserve `_relation_closure_ids()` order and maintain a separate membership set for deduplication.

## Passing mechanisms

- receipt private-copy/atomicity checks;
- snapshot relation gap and event/byte/age cause truth apart from nondeterministic target priority;
- continuation relation gap and event/byte cause truth;
- normalized restart-gap coverage;
- S05 wire-field assertions;
- 187 Observation tests and exact-range diff hygiene.

## Source

Full independent report:
`/Users/zmll/.hermes/cache/delegation/subagent-summary-0-20260719_145205_428379.txt`.
