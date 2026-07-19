# Slice 020 convergence review — attempt 4 authority, instance identity, coverage, and retained-state findings

**Date**: 2026-07-19
**Review object**: independent verdict pinned to `75ff65fa98a3a69219a980311a4112a471410574`; applicability reproduced against current tip `dbe220d4b665b51def378398553c55c042f22d1d`
**Review mode**: independent fail-closed stateful/security review plus owner-side current-tip probes
**Verdict**: REJECT

The Phase 15 cursor-memory correction remains valid and closed. The following
independent findings survive it and block candidate preparation.

## S020-A4-01 — HIGH / security — expiry enforcement fails open

An expired capability served when `fetch_time` was omitted or malformed, and
`issue()` accepted an unparseable `expires_at`. Expiring authority must require
parseable timezone-aware issuance and fetch timestamps and reject absent or
invalid fetch time when expiry exists.

## S020-A4-02 — HIGH / security — returned capability mutates host authority

`issue()` stores and returns the same dictionary. Mutating the returned room
binding, expiry, direction flag, and event cap rewrote internal enforcement and
served an otherwise unauthorized three-event page. Internal authority state
must be private and immutable relative to the returned wire document.

## S020-A4-03 — HIGH / contract — cursor provenance contaminates I-010A

Minting a cursor appends a fixture-only `cursors` property to that same returned
capability. Reusing it in an attention request fails the closed accepted schema.
Cursor provenance must remain entirely internal.

## H020-A4-04 — HIGH / identity — evicted ID replacement impersonates remainder

A cursor bound to original remainder `e1` served a later event also named `e1`
after eviction and reingestion. IDs alone do not establish immutable event
instance identity across bounded retention. Cursor state must bind a host-owned
monotonic ingestion generation alongside each event ID and anchor.

## H020-A4-05 — HIGH / coverage — final pages hide later arrivals

An `after` cursor correctly excluded later `e6` from its original remainder but
reported `has_more_after=false` after original `e5`. Retention-shifted `around`
windows have the analogous stale-boundary failure. Cursor metadata must retain
snapshot-generation and side-omission facts so later known arrivals remain
truthfully disclosed without entering the fixed remainder.

## S020-A4-06 — HIGH / security — auxiliary retention state is unbounded

With `retention_max_events=3`, ingesting 100 unique events left 100 entries in
both `_seen_delivery_ids` and `_actors`. Duplicate-delivery and actor registries
must be coupled to retained event instances; unrelated supplied actor facts must
not create durable state. Cursor instance generations provide replacement safety
without requiring unbounded event-ID tombstones.

## Required correction

1. Add RED tests for all six findings, including malformed/absent time,
   authority-copy isolation, closed-wire stability, evicted-ID replacement,
   later-arrival side coverage, and retention-coupled auxiliary counts.
2. Separate private authority/cursor provenance from deep-copied returned wire
   documents; fail closed on invalid expiry semantics.
3. Assign every accepted event a monotonic host generation and bind cursor
   anchors/windows to `(event_id, generation)` pairs.
4. Persist snapshot-generation and immutable side-omission facts in cursor state.
5. Remove evicted delivery IDs/generations, retain actor facts only for actors
   referenced by retained events or self, and add delivery IDs only after a
   candidate validates successfully.
6. Add adversarial eval receipts, regenerate evidence, and rerun independent
   review before any candidate/handoff claim.

The append-only Phase 12/14 history correction is already closed by `247e282`.
This record does not accept the slice or authorize integration, cutover,
deployment, release, or promotion.
