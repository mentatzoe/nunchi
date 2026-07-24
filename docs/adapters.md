# V2 reference adapters

All reference adapters share `ReferenceAdapterRuntime`. Native payloads are
normalized before attention and cannot alter trusted binding or policy.

| Surface | Ingress | Output | Retained context | Explicit native limits |
|---|---|---|---|---|
| Generic JSONL | message, reaction, membership | message, reply, reaction | bounded persisted | host attests all native facts |
| Discord | message, reaction add/remove, membership | message, reply, reaction add/remove | bounded persisted plus live gateway | configured channel routes only |
| Matrix | message, reaction add, membership | message, reply, reaction add | bounded persisted plus `/sync` | portable room-wide mention relation unavailable; reaction removal unavailable without native reaction event ID |
| Telegram | message, membership | message, reply | live-only visibility with bounded retained state | ordinary history, reactions, and portable room-wide mentions unavailable |

`--probe` without configuration reports only static installed capabilities.
Configured probes verify exact pinned configuration and required credentials
but do not claim a live connection.

## Generic JSONL

Input is one closed object per line:

```json
{
  "delivery_id": "host:delivery:1",
  "room_id": "room-1",
  "event": {
    "id": "host:message:1",
    "type": "message",
    "author_id": "host:actor:zoe",
    "text": "hello",
    "mentioned_actor_ids": [],
    "mentions_room": false
  },
  "actors": {
    "host:actor:zoe": {"display_name": "Zoe", "kind": "human"}
  }
}
```

Output is a host-attested JSONL action envelope only after participant
contribution. Silence produces no transport line.

## Backfill

Matrix's first `/sync` batch is recorded as context and token state, not
scheduled as fresh work. Telegram establishes a finite startup frontier with
one native negative-offset tail read (at most 100 updates): that tail is
context-only, older pending updates are deliberately forgotten, and an
explicit coverage gap is retained before ordinary long polling begins. A busy
room therefore cannot hold Telegram in backfill forever or turn stale backlog
into wake work.

Restart never schedules retained observations. A fresh Discord process has no
durable gateway resume session, so both the shared and standalone transports
declare a source gap before accepting post-start facts. Within-process resume
continuity is transport-attested; a bounded queue or client-delivery loss also
produces an explicit persistent gap.

## Errors

Malformed or unconstructable native input is audited without a fabricated
social decision. Wrong routes, exact duplicates, and exact self are not wake
eligible. Provider errors follow the configured `WAKE` or `NO_WAKE` operational
policy and remain `status: error`. Matrix and Telegram report output as sent
only when the native response includes a stable message/event identity for the
exact target room; a successful HTTP envelope with a missing or mismatched
native acknowledgement remains `unknown`.
