# Hermes attention ACK repair — 2 October 2026

Repairs the three ACK defects found in the review of `c3fd271`. This is not a
complete V2 release, a live adoption, or a fix for the separate native-tool
journal timeout or the plugin-loader deadlock.

The selected design is unchanged. AttentionEngine still selects and widens
ACK. One permit still authorises one method, adapter, target, and emoji.
Shared AckJournal, AckPolicy, and receipts remain the owners. The native
await still happens outside the scheduler and room locks.

What changed is the commit boundary:

- The permit binds the current opportunity and absolute deadline. The wrapped
  native method consumes that authority under the scheduler lock, before the
  network await. A cancelled, expired, or unbound context fails closed and
  does not fall through as ordinary traffic.
- Cancelling the parent cancels the native child and revokes authority that
  has not yet committed. A child that ignores cancellation stays owned until
  it exits, including through room shutdown. The result stays unknown and is
  not retried.
- ACK journal reservation and settlement run off the gateway loop. A lock
  that is not acquired within the remaining deadline refuses dispatch. A late
  reservation is settled failed and tracked, so replay does not emit a second
  reaction. Settlement that misses the deadline is tracked to a bounded
  cleanup and is not recorded sent.

## Source

Parent `c3fd2712cd544163ceb3bda2ba15e67327c1cc08`. Base
`9734564c102c693eb1b0f3fd87bb8661b3346104`. Native tool, approval, loader,
and lifecycle code was not changed. Host Hermes source was not edited.

## Executed checks

- `PYTHONPATH=src python3 -m unittest tests.v2.test_hermes_ack tests.v2.test_hermes_portable`:
  108 tests, OK. The seven new cases cover pre-native cancellation and
  expiry with zero calls, parent cancellation, resistant-child shutdown
  ownership, and reservation plus settlement contention with another room
  still progressing.
- Canonical `PYTHONPATH=src python3 -m unittest`: 678 tests, OK, 8 expected
  skips. The count is the previous 671 plus those seven regressions.
- This repair did not re-run the installed Hermes 0.19.0 wheel harness or
  current Hermes 0.21.5. The 0.21.5 register deadlock remains held. A direct
  method check is not a plugin-load pass, and none is claimed here.

No GitHub write, live profile write, or gateway restart was performed.
