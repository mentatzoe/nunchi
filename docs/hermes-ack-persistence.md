# Hermes ACK persistence boundaries

ACK selection remains in AttentionEngine. The Hermes integration reserves the
shared stable ACK key, records participant-host handoff, and uses one exact
native reaction permit. It never retries a reaction after an uncertain result.

## Cancellation and stage ownership

Reservation and handoff form one owned preparation task that cannot dispatch.
Parent cancellation waits for that task and the terminal closure, then propagates
the original cancellation (including its message). The in-flight handoff writer
is observed once, not restarted. Cancellation before native entry makes no native
call; cancellation after native entry still cancels/owns the native child.

Settlement and transport receipt writing similarly have one owned finalization.
Cancellation does not start a second transport write. If persistence has already
confirmed an on-time sent outcome, cancellation cannot undo that observed fact;
the transport receipt remains sent. An unconfirmed settlement is abandoned and
closes unknown. Immutable stage receipts are never rewritten.

## Deadline, I/O and durability

Thread-lock and process-flock waits use the opportunity's absolute deadline.
Conservative settlement cleanup uses that deadline plus two seconds, not a new
budget for each lock. If a lock remains held beyond cleanup, reserved plus an
unknown transport receipt is an accepted no-retry outcome.

The deadline is also checked after journal file setup, write and fsync. A final
settlement completing late or abandoned is withdrawn back to the preceding
journal prefix under both journal locks. This preserves the durable reservation.
Cleanup may then append unknown if its lock budget has not expired. A tiny
non-I/O confirmation callback at the durable commit point resolves the race
between confirmation and caller abandonment; a normal worker return alone is
not proof of on-time persistence.

Python cannot safely kill an arbitrary blocked filesystem call in an executor
thread. Such a worker, including any truncate/fsync needed to withdraw an
uncertain append, remains owned until it really finishes. `ack_effects_quiescent`
therefore stays false, and a bounded `drain_ack_ownership` can return false while
I/O is active. Preparation and receipt closure may wait beyond the opportunity
deadline to observe an active write exactly once; they cannot grant fresh native
authority. A final ACK settlement can return unknown while its writer is still
owned. Lock-wait bounds are not bounds on active I/O occupancy.

Withdrawal is not a crash-atomic transaction between ACK JSONL and immutable
receipts. Bytes from an unconfirmed append can be visible to a raw file reader
while write/fsync is still in flight; supported journal operations acquire the
process lock before consuming records. After finite I/O completes successfully,
a late sent append is withdrawn before those locks are released. A process crash
or storage failure during withdrawal can leave uncertain bytes. The durable
reservation still fences replay; this change does not claim crash-atomic audit
agreement or repair failing storage. Do not infer quiescence from caller return,
and do not truncate, delete or replay an active journal operationally.

## Regression coverage

`tests/v2/test_hermes_ack_boundaries.py` uses real JSONL writes with finite,
event-controlled stalls at reservation completion, handoff, final open,
write/fsync completion and transport receipt writing. It also covers repeated
parent cancellation and on-time commit with delayed worker return. The existing
ACK suite retains permit binding, native-child lifetime, deduplication and
thread/process-lock responsiveness checks. Installed normal-turn evidence is
separate from source tests and from direct-method boundary probes.
