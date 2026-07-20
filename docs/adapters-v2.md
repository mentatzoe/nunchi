# Nunchi V2 adapter facts and capability parity

V2 adapters normalize transport facts into the common observation provider;
they do not decide who should speak. Equivalent facts use exact platform actor,
room and event identities. Missing facts remain missing.

| Surface | Message/reply | Reaction | Membership | History/restart |
|---|---|---|---|---|
| Generic reference host | Host-attested | Host-attested | Host-attested | Host declares truthfully |
| Shared Discord | Messages, replies, exact user/room mentions; thread root only when supplied by trusted metadata | Live add/remove with gateway session+sequence identity | Unavailable in current source | Bounded REST message history; restart gap remains declared |
| Matrix reference | Native messages, replies and thread roots | Native `m.annotation` add | Native join/leave | Sync token plus bounded history; full restart safety not claimed |
| Telegram reference | Messages, replies, structured `text_mention` user IDs | Unavailable without prior-state diff | Chat-member join/leave | Bot API history unavailable; known restart gap |

Telegram `@username` text does not establish a user ID. Matrix display names do
not establish an MXID. Discord display names do not establish a snowflake.
These are deliberate security and parity properties, not missing convenience
features.

All surfaces feed `LiveRoomRuntime`: one active attention/participant turn, one
replaceable newest pending anchor, a fresh current-tail participant view, and no
send-time social reclassification.

## Generic JSON-lines host

`nunchi-channel` is the V2 generic reference entrypoint. The operator binds the
participant, platform, room, continuity scope and recoverability facts on the
command line; room input cannot change them. Each stdin line is one closed host
delivery with `delivery_id`, exact boolean `authorized`, `routing_room_id`,
canonical `event`, and optional actor facts. Duplicate JSON keys, non-finite
numbers, unknown fields and non-boolean authorization claims are rejected.

```sh
nunchi-channel \
  --policy /absolute/path/to/nunchi-policy.json \
  --participant-id vigil \
  --participant-actor-id reference:user:vigil \
  --participant-name Vigil \
  --platform reference \
  --room-id room-1 \
  --continuity-scope-id reference:room:1 \
  --continuity restart-safe \
  --restart-gap false \
  --participant-workspace /absolute/owner-only/empty-workspace \
  --participant-env PARTICIPANT_API_KEY \
  --participant-command /absolute/path/to/participant --json-stdio
```

`--participant-command` and its argv must be last. One waking turn is written
to that process as a complete `ParticipantWakeV2` JSON document; it returns one
message action, reaction action, or `null`. Nunchi uses no shell, sets the child
home/current directory to the absolute owner-only workspace, supplies a minimal
environment, and passes only operator-named extra variables. Platform tokens,
classifier credentials, Python path/home controls and Codex home are reserved
and cannot be passed through this interface. Use a distinct participant-only
credential name if the participant requires a provider key.
Participant output is strict JSON: duplicate keys and non-finite values are
rejected. Nunchi terminates the whole participant process group on timeout or
while it exceeds the one-MiB stdout or 64-KiB stderr capture budget; child
stderr is never copied into room output or generic operator errors.

`--silent-participant` is an explicit observation/attention-only mode and cannot
be combined with a command. The generic command intentionally exposes no
privileged executor: an embedding host that supports privileged actions must
construct the shared authorization coordinator and authenticated operator
surface described in [`security/v2.md`](security/v2.md).

Stdout uses two versioned record types. An actual participant action is emitted
immediately as `type: "action"` with its request ID; a later
`type: "delivery-result"` reports the normalized delivery and runtime outcome.
The action is written only after the participant-host receipt and receives its
own transport receipt after the stream flush. Request IDs are at-most-once and
capacity-bounded without eviction or queueing.

## Matrix

`nunchi-matrix` binds one Matrix room and one operator policy per process. This
keeps exact self identity, the trusted room, the recoverability claim and every
receipt under one closed binding; run another process with another policy for a
second room. The Matrix access token is read from `NUNCHI_MATRIX_TOKEN` by
default and is never placed in room, classifier or participant projections.
HTTPS is mandatory unless the operator explicitly supplies
`--allow-insecure-http` for a controlled development homeserver.

```sh
install -d -m 700 /absolute/operator-state
nunchi-matrix \
  --homeserver https://matrix.example.test \
  --room-id '!room:example.test' \
  --state /absolute/operator-state/matrix-room.json \
  --policy /absolute/path/to/nunchi-policy.json \
  --participant-id vigil \
  --participant-name Vigil \
  --participant-workspace /absolute/owner-only/empty-workspace \
  --participant-command /absolute/path/to/participant --json-stdio
```

The policy continuity scope for that example is exactly
`matrix:room:!room:example.test`. The first `/sync` batch is retained as bounded
context and never wakes the participant. Each later batch records all exact
native events and creates at most one opportunity at its newest observed event.
The room-bound sync cursor is atomically checkpointed before a participant turn,
so a crash does not replay a batch as queued social work. Full restart coverage
is not proven, therefore this adapter declares `session-only` continuity with a
restart gap and refuses a policy that claims social suppression is recoverable.

Messages, exact replies, exact Matrix-user mentions and `m.annotation`
reactions are sent directly from the participant action without a second social
judgment. Matrix transaction IDs are deterministically derived from the Nunchi
request ID, transport sends have a local backstop, and the transport receipt is
written after the API effect. As with the generic adapter, no privileged
executor is exposed on this room surface.
