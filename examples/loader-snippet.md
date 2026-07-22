# Host integration snippet: V2 act or silence

Nunchi V2 belongs in the trusted host, before a participant process is
invoked. Do **not** paste a self-gating instruction into an agent prompt: room
text must not choose policy, identity, authorization, or whether pre-attention
is enabled, and a woken participant must not return a verdict or magic
suppression sentinel.

Use [`nunchi-channel`](../docs/adapters-v2.md#generic-json-lines-host) when a
platform-specific adapter is unavailable. The operator starts one long-lived
process with an owner-only policy and an exact participant/room binding:

```sh
nunchi-channel \
  --policy /absolute/operator/nunchi-policy.json \
  --participant-id vigil \
  --participant-actor-id reference:user:vigil \
  --participant-name Vigil \
  --platform reference \
  --room-id room-1 \
  --continuity-scope-id reference:room:1 \
  --continuity restart-safe \
  --restart-gap false \
  --participant-workspace /absolute/owner-only/participant-workspace \
  --participant-command /absolute/path/to/participant --json-stdio
```

The host authenticates and authorizes a native delivery first. It then writes
one closed JSON document per line; text never substitutes for exact actor or
room identity:

```json
{
  "delivery_id": "reference:delivery:501",
  "authorized": true,
  "routing_room_id": "room-1",
  "event": {
    "id": "reference:event:501",
    "type": "message",
    "author_id": "reference:user:zoe",
    "text": "Vigil, summarize the incident timeline.",
    "mentioned_actor_ids": ["reference:user:vigil"],
    "mentions_room": false
  },
  "actors": {
    "reference:user:zoe": {"display_name": "Zoe", "kind": "human"},
    "reference:user:vigil": {"display_name": "Vigil", "kind": "bot"}
  }
}
```

The process may emit an `action` record followed by a `delivery-result`, or
only a `delivery-result` when suppression or participant silence produces no
room action. The host sends an emitted action exactly once and never asks a
second social question at send time. Invalid, unauthorized, duplicate, and
self-caused native deliveries do not become response jobs.

The participant receives one `ParticipantWakeV2` JSON document on stdin and
returns exactly one structured action or JSON `null`:

```json
{"kind":"message","content":"The incident began at 14:03 UTC."}
```

That is the entire participant-side loader contract: treat the wake as a
normal current-room turn, optionally fetch bounded context through a host-only
continuation interface when one is supplied, then contribute directly or stay
silent. Do not emit `SUPPRESS`, `WAKE`, `DEFER`, an explanation of whether to
speak, or a transport sentinel.

See [`generic_host_demo.py`](generic_host_demo.py) for all three model
dispositions plus trusted bypass and deterministic transport rejection. See
[`read_the_room_demo.py`](read_the_room_demo.py) for the one-active,
newest-pending freshness rule that prevents a burst from becoming a FIFO of
stale replies.
