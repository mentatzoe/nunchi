# Slice 020 immutable review — closed host-binding rejection

**Date received**: 2026-07-19
**Review object**: exact commit `55620049a4abd63672951ea2bd221558846fe1df`
**Parent**: `aa0da7a81810f82f7b8904d54e948bb1109818cd`
**Verdict**: REJECT

This verdict arrived after Phase 17 and Phase 18 work had advanced. It remains
pinned to `5562004`; each mechanism is separately adjudicated against the
current tree.

## Finding 1 — exact-expiry boundary

The reviewed target used `fetch_time > expires_at`, so equality still served.
This is stale against current scope: Phase 17 T080–T082 changed the predicate to
`>=`, added exact-boundary unit/eval coverage, and proved handle reclamation.
The current finding remains rejection history and is not promoted into a new
current defect.

## Finding 2 — HIGH — host binding is not a closed exact context

`check_binding_expiry` validates four values individually but does not validate
the host context as the closed four-field continuation binding. A context with
all correct binding values plus `unexpected_tenant="other"` is accepted. This
diverges from `_check_continuation_binding` and the accepted I-010 reference
validator, which require the exact closed shape and exact dictionary equality.

Current-tree owner reproduction on 2026-07-19:

```text
CLOSED_BINDING_PROBE=SERVED ['e1']
```

The reproduction used the dirty Phase 18 implementation atop `5e2380a`; it
therefore applies now and blocks candidate preparation.

Required correction:

1. validate `host_context` through `_check_continuation_binding`;
2. compare the complete validated object exactly with issued `bound_to`;
3. reject before serving or committing cursor state;
4. add unit/eval coverage for additional, missing, malformed, and exact contexts;
5. rerun the complete matrix and obtain a fresh immutable review.

This record is review input only. It is not acceptance or authority for
integration, cutover, deployment, release, or promotion.
