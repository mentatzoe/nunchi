# Slice 020 evidence manifest

Scene-to-record manifest for `020-v2-observation`, generated at the same
candidate tree as `evidence/v2/observation/handoff.md`. Every aggregate
JSONL row below carries a mandatory `scene_id`; this manifest maps every
applicable scene from the plan's Acceptance Scenes and Evidence table to
its exact records and reproduction command, so scene coverage is never
implicit.

## I-020A capability rules (summary)

- **Identity (FR-002)**: `self.actor_id` is bound once at construction from
  a transport-/host-attested identity; no name, alias, role, or message
  text ever establishes authorship.
- **Transport hygiene (FR-004)**: the only three mechanical no-wake
  dispositions are `duplicate-retained`, `self-retained-no-wake`, and
  `unroutable`; every other authorized event is `observed`. Authorization
  is never derived from payload content.
- **Bounded snapshot (FR-006, FR-007)**: trigger, then exact relation
  closure, then nearby fill, under hard `max_events`/`max_bytes`/optional
  `max_age_seconds` caps, in authoritative (ingestion) order; `coverage`
  reports every limit that actually excluded a candidate.
- **Continuation (FR-008, FR-009)**: optional, host-owned, opaque,
  bound to participant/room/continuity-scope/trigger; a fetch request
  carries no inline binding fields — the host's actual call context is
  checked independently against the issued capability's `bound_to`. Cursor
  tokens are one-shot, each active sequence shares one immutable ordered
  `(event_id, host_generation)` window, handles and active cursors have
  host-configurable hard bounds, returned wire documents cannot mutate private
  authority, expiry fails closed, and exhausted/expired/revoked state is
  reclaimed. Snapshot-generation facts keep later known arrivals visible in
  side coverage without admitting them to the fixed remainder.
- **Retention (FR-010)**: bounded (`retention_max_events`) and
  outcome-neutral; retained delivery IDs, event generations, and actor facts are
  pruned with deque eviction, and no prior attention/social outcome ever changes
  retention behavior.
- **Receipt (FR-015)**: exactly one immutable `observation`-stage `I-010E`
  record per request, correlated by `request_id`, attesting only
  snapshot/coverage facts; no token field, no later-stage fact.

## Scene-to-record manifest

| Scene | Required observation | Evidence file | Command |
|---|---|---|---|
| S01 Exact self and alias collision | Exact attested self wins; names never establish authorship | `identity-and-hygiene.jsonl` (`ID-S01-*`, 2 rows) | `PYTHONPATH=src:. python3 -m evals.v2.observation.run_scenes` |
| S02 Native relations | Actor-targeted vs. room-wide mentions distinct; reply/thread/reaction/membership survive | `identity-and-hygiene.jsonl` (`ID-S02-*`, 2 rows) | same |
| S03 Bounded context and tail | Trigger, relation closure, tail, bytes/events, immutable event instances, later-arrival side coverage, gaps truthful | `budget-sweep.jsonl` (`BUD-S03-*`, 3 rows), `continuation.jsonl` (`CONT-S03-*`, 13 rows) | same |
| S04 False-suppression scars | Referential mention/resolution/other-addressee/class-address never enter deterministic hygiene | `identity-and-hygiene.jsonl` (`ID-S04-*`, 2 rows) | same |
| S05 Governed suppression recoverability | Earlier events remain ordinarily available under claimed continuity; unsupported eligibility explicit | `s05-recoverability.jsonl` (`CAP-S05-*`, 4 rows) | same |
| S11 Transport hygiene | Exact duplicate, exact self, unroutable are the only mechanical no-wake classes | `identity-and-hygiene.jsonl` (`ID-S11-*`, 2 rows) | same |
| S13 Adapter equivalence | Equivalent supplied facts normalize equivalently; capability-only differences explained | `s13-equivalence.jsonl` (`CAP-S13-*`, 3 rows) | same |
| S15 Context budget | Snapshot/fetch hard caps enforced with `I-010E` byte telemetry; authority, expiry, cursor, delivery, generation, and actor state remain isolated/bounded; `utf8-bytes-ceil-div4@1` proxy is evidence only | `budget-sweep.jsonl` (`BUD-S15-*`, 4 rows), `continuation.jsonl` (`CONT-S15-*`, 9 rows) | same |
| S16 No registry or ledger | No roster inference, outcome registry, obligation queue, or handled/open state | `identity-and-hygiene.jsonl` (`ID-S16-*`, 1 row) | same |

Total: 45 aggregate rows across the 5 evidence files, all `PASS` (0 FAIL),
regenerated 2026-07-19.

## Exact-attempt-6 corpus conformance (I-010A/I-010D/I-010E)

`evidence/v2/observation/handoff.md` §"Attempt-6 corpus conformance
(T037)" carries the full accounting: 202 cases from the identical
`bff6b463a44c1b9066fc654691042f9550da6c64` corpus revision, 100 consumed
(0 mismatches), 102 explicitly non-consumed (`I-010B`/`I-010C`, never
silently skipped). Reproduce with:

```sh
PYTHONPATH=src:. python3 -m unittest tests.v2.observation.test_attempt6_corpus_conformance
```

## Downstream comparator/recoverability obligations

The S05 and S13 evidence above proves the reusable reference mechanics and
comparator contract only. Slices `050` and `060`–`090` must each run their
own real transport binding against `evals/v2/observation/replay.py`,
`evals/v2/observation/compare.py`, and
`evals/v2/observation/capabilities/reference_provider.py` before claiming
social-suppression eligibility or real-surface parity; slice `110` alone
owns the final cross-surface parity claim. A reference pass recorded here
is never citable as proof for an installed surface.

## The accepted-I-010E token-field limitation

The accepted `I-010E` observation body is closed with no token field.
Every evidence row's `token_proxy` object (`estimator_id:
"utf8-bytes-ceil-div4@1"`, `estimated_tokens`, `serialized_bytes`,
`model_id: null`) is separate evidence, never written onto any receipt
record. See `evidence/v2/observation/handoff.md` for the full limitation
statement handed to `v2-contract-owner` and `v2-integrator`.

## The exact slice-030 classifier-projection handoff

Slice 020 emits the accepted `I-010A` `continuation` capability unredacted.
Slice `030` alone implements classifier-safe projection/redaction (down to
coverage plus expansion-capability booleans) in `src/nunchi/core.py`
before any classifier is invoked. No test or evidence in this slice
exercises that redaction — it is explicitly out of scope here (plan
§"Explicit Exclusions").

## The reference-only suppression-eligibility boundary

No reference variant, comparator result, or aggregate evidence row in this
directory establishes real-surface conformance, restart-safety,
social-suppression eligibility, or cross-surface parity for any installed
transport. Each downstream surface owner must independently pass the
restart/backfill scene and the comparator against its own real binding
before making that claim (FR-011, FR-012).
