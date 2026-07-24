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

Matrix's first `/sync` batch and Telegram's first `getUpdates` batch are
recorded as context and offset/token state, not scheduled as fresh work.
Restart never schedules retained observations. Discord gateway resume
continuity is transport-attested; a bounded queue or client-delivery loss
produces an explicit persistent gap.

## Errors

Malformed or unconstructable native input is audited without a fabricated
social decision. Wrong routes, exact duplicates, and exact self are not wake
eligible. Provider errors follow the configured `WAKE` or `NO_WAKE` operational
policy and remain `status: error`.
