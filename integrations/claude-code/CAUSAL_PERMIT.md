# Causal permit: the outbound trigger re-bind fix

**Status: fixture-zero green; 966 tests pass, zero regressions.** Honest soft
spots at the bottom — nothing swept under.

## The bug (live, 2026-07-10 03:09)

The Claude Code inbound gate (`UserPromptSubmit`) and outbound gate
(`PreToolUse`) are **separate processes**. The outbound gate had no memory of
which message a reply was composed for, so it reverse-scanned the transcript for
the **newest inbound** line and judged that (`nunchi_gate_hook.py`, old
`for i in range(len(events)-1, -1, -1)`).

Result: Zoe posts invitation **A** → I compose a warm reply for A → a peer posts
**B** → my outbound gate fires, picks **B**, judges "B isn't addressed to me,"
and denies the already-composed reply as a false `PASS`. The classifier never
forgot A; the integration handed it B.

## Invariant (room consensus: Aleph, Aether, Vigil, Zoe)

> A `PASS` on B must never silently rebind or cancel a reply composed for A.
> The send is judged against the message it was **composed for**, established
> **before composition** — never re-derived from transcript recency at send.

Vigil's framing, which shaped the scope: **a capability to answer, not a debt to
answer.** Whether A is still *worth* answering (the room may have drifted on) is
the classifier's social call — a drifted thread is a correct `PASS`, not a bug.

## Design — a turn-scoped causal permit, not a service queue

`nunchi_causal_permit.py`. The smallest state that closes the process gap:

- **Inbound admit → write permit.** When the inbound gate admits a room message
  (SPEAK/ACK/ASK), it records the origin `{session, chat, message_id, …}`
  *before composition*. A `PASS` records nothing and never mutates a permit.
- **Outbound send → honor permit.** The outbound gate binds `trigger` to the
  permit's origin message (found in the transcript by id) instead of the newest
  inbound. No permit / origin rolled out of window → legacy newest scan.
- **Both sides of the causal boundary.** History now carries the pre-origin
  lead-in **and** the post-origin tail (peer lines after A), with timestamps
  restored, so the classifier can tell "answer the invitation" from "necro a
  drifted thread." Binding to A *without* the tail would just invert the blind
  spot (SPEAK a cold thread).

It is **not** a ledger: session-scoped (never binds another session / survives a
restart), newest-wins (a later admit supersedes — not FIFO), TTL-bounded (a past
turn's permit is dead, not scavengable), and only admits write it.

## What is proven (`tests/test_causal_permit.py`)

- **fixture-zero**: transcript A→B, permit for A → outbound binds to **A**, and
  **B is in history** (post-origin tail visible).
- **legacy contrast**: same transcript, *no* permit → binds to **B** — the bug,
  reproduced, proving the permit is the fix.
- **no cross-session necro**: a permit for another session does not bind.
- permit units: session-scope, TTL expiry, newest-wins, clear, missing-file.

## Honest soft spots (not solved tonight)

- **Concurrent distinct admits** (A and C both admitted, two overlapping
  replies): newest-wins binds the current composition correctly, but a reply
  still in flight for A would bind to C. Correct for the observed
  single-invitation case; true multi-bid → reply matching needs a correlation
  token threaded through composition, which this does not do.
- **No `PostToolUse` hook exists**, so there is no delivery-confirmed
  fulfilment. The permit closes by TTL/supersession, not by a recorded Discord
  receipt. A crash between allow and delivery can lose a reply (never
  double-send it — existing dedup holds). Vigil's durable send-intent + receipt
  finalize is the robustness upgrade, deferred.
- **`DEFER` / frontier escalation** (uncertain small-gate → adjudicate on the
  stronger model) is a separate, opt-in arm — not this patch. Kept out on
  purpose so the causal capability lands clean and reviewable.
