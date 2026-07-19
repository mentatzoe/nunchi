# Independent Codex review — `cd8917c` rejection

**Review object**: `cd8917c56f0d051f52cdba68c177d45e7a9f1103`
**Verdict**: REJECT
**Date received**: 2026-07-19
**Method**: read-only review in a history-free archive of the exact Git tree.

## HIGH findings

1. Observation-stage receipts were not tied to provider-issued snapshots and
   request IDs were not consumed uniquely. Two receipts for one request and a
   fabricated never-observed request both validated.
2. Runtime output could violate authoritative non-decreasing parseable
   timestamp order because the checker existed but ingest/snapshot did not
   invoke it.
3. The S13 comparator discarded authoritative order and ignored room/actor/
   coverage and one-sided event differences.
4. Contradictory `unroutable` input could include authorized candidate event and
   actor fields; the provider returned `unroutable` and silently discarded the
   event instead of rejecting the malformed transport shape.
5. The exact-object matrix was stale by one scanner test (147/1396 discovered
   versus 146/1395 recorded).
6. Provenance claims were under-attested: the corpus revision was only a string,
   the recorded scanner target predated the reviewed object, and the
   history-free archive could not resolve accepted dependency commits.

## MEDIUM finding

Constructor identity/room/visibility validation was delayed until snapshot.
Invalid visibility could accept and retain an event, then fail snapshot while
leaving poisoned state.

## Current adjudication

- Finding 3 is closed by Phase 21 T109–T111.
- Finding 5 is closed by the exact Phase 21 153/52/1402 matrix.
- The scanner has no marker exemption and the post-Phase-21 exact target was
  scanned clean over 60 files and 8,789 additions.
- All five dependency commits absent from the history-free archive are present
  and resolvable in the real repository, so that subclaim was an archive-method
  artifact.
- Findings 1, 2, 4, corpus-byte identity in 6, and the MEDIUM constructor issue
  remain live and are bound by Phase 22 T114–T119.

## Other verified evidence

The reviewer reproduced aggregate and adversarial row counts, 202-case corpus
accounting, targeted continuation/security controls, append-superseded packet
history, the eight downstream lanes, and the separate slice-030 core-owner
obligation. No attempt-2 convergence or handoff claim existed.

This is independent review input only. It is not acceptance, integration,
deployment, release, promotion, or cutover authority.
