# Slice 020 convergence review — Phase 18 concurrency and replay-resource extension

**Date**: 2026-07-19
**Primary review object**: immutable `dbe220d4b665b51def378398553c55c042f22d1d`
**Current reproduction object**: immutable `55620049a4abd63672951ea2bd221558846fe1df`; independently reconfirmed on `f38a4fe4cf98fd4d63887e0baf735db7427298f6`
**Verdict**: REJECT candidate readiness

## S020-A6-01 — HIGH — continuation state transitions and limits are not atomic

Barrier-controlled owner probes against `5562004` reproduced every transition
race first reported by the immutable `dbe220d` review:

- two fetches captured the same one-shot cursor state and both succeeded, returned
  the same event, and minted successors;
- two concurrent `issue()` calls under `max_handles=1` both succeeded, leaving two
  handles;
- concurrent fresh `before` and `after` fetches under
  `max_active_cursors_per_handle=1` both succeeded, leaving two active cursors.

A separate read-only stress pass on current `f38a4fe` additionally reproduced a
fetch/revoke interleaving that raised raw `KeyError`. A lock local only to one
`ContinuationProvider` is insufficient because ingestion and multiple
continuation wrappers share the provider's mutable retention state.

Required correction: one provider-owned shared `threading.RLock` must serialize
the complete `ingest`, `snapshot`, `issue`, `fetch`, and `revoke` transitions,
including limit checks, cursor consumption/successor registration, expiry
cleanup, receipt request-ID uniqueness, and retention reindexing. Deterministic
concurrent RED tests must prove linearizable outcomes and no raw exceptions or
state resurrection.

## S020-A6-02 — MEDIUM / resource security — cursor replay remains quadratic

The cursor lifecycle fix bounded retained state but every replay still copies the
full event deque, slices and scans the complete remaining tuple, and materializes
a complete candidate-index list. Owner instrumentation on a 299-page one-event
chain counted 89,400 event-index operations. Independent current-tip probes
measured 4,032 event visits at N=64 and 16,256 at N=128 (4.032x work for 2x
input), confirming O(N^2) cumulative work.

Required correction: add a retention-coupled O(1) event-by-ID map, preserve one
shared immutable `(event_id, generation)` tuple per active sequence, resolve only
the current page plus stop candidate, and replace the full-remainder scan with
an O(1) retention-frontier check. This optimization is valid only while accepted
events are append-only, generations are monotonic, retention evicts a left
prefix, and continuation windows are contiguous; those assumptions must be
executable regressions. One-event pagination across N and 2N must show near-
linear operation growth, with exhaustion still reclaiming all cursor state.

## Required integration with existing Phase 18

The untracked independent preparation review against `f38a4fe` separately found
hard snapshot-byte overflow, missing originating-request merge identity, and an
unreproducible static-scan receipt. All five applicable finding groups belong to
one Phase 18 correction and one final immutable review. None may be hidden by
serial task completion in another lane.

This record does not accept the slice or authorize integration, cutover,
deployment, release, or promotion.
