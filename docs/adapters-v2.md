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

## Telegram

`nunchi-telegram` likewise binds one exact chat and policy per process. The bot
token comes from `NUNCHI_TELEGRAM_TOKEN` by default, the API endpoint requires
HTTPS unless development mode is explicitly enabled, and the token never
crosses into participant or classifier input.

```sh
install -d -m 700 /absolute/operator-state
nunchi-telegram \
  --chat-id=-1001234567890 \
  --state /absolute/operator-state/telegram-chat.json \
  --policy /absolute/path/to/nunchi-policy.json \
  --participant-id vigil \
  --participant-name Vigil \
  --participant-workspace /absolute/owner-only/empty-workspace \
  --participant-command /absolute/path/to/participant --json-stdio
```

The matching policy continuity scope is
`telegram:chat:-1001234567890`. On first start the adapter asks Telegram for
only the newest pending update using the native negative-offset behavior,
retains that update as context, forgets older queued updates, and establishes an
owner-only checkpoint. An empty first response establishes cursor `0`, so the
next arriving message is live rather than being silently treated as another
initialization batch. Later update batches are checked for strict increasing
native IDs, coalesced into one newest opportunity and checkpointed before any
participant effect. Telegram has no Bot API room-history fetch, so the adapter
truthfully declares live-only, session continuity with a restart gap and cannot
make social suppression recoverable.

Structured inbound `text_mention` entities bind exact user IDs; textual
`@username` mentions do not. Exact replies are supported. Outbound exact user
mentions are rejected because the action contract does not provide the text
offset/entity data needed to represent them without changing participant
content. Outbound standard-emoji reactions use `setMessageReaction`; inbound
reaction deltas remain unavailable without prior-state comparison. Sends have
a local backstop and request-correlated transport receipts, but Telegram offers
no idempotency key for `sendMessage`, which remains an explicit transport
limitation rather than a false guarantee.

## Standalone Discord

`nunchi-discord` keeps `discord.py` as the optional `discord` extra, but parses
its command line before importing that dependency. A base installation is
therefore inspectable and `nunchi-discord --help` works even when the gateway
extra is absent. Runtime configuration binds one exact channel and policy per
process; the bot token comes from `NUNCHI_DISCORD_TOKEN` by default and is used
only by the gateway and room-bound REST client.

```sh
python -m pip install 'nunchi[discord]'
nunchi-discord \
  --channel-id 123456789012345678 \
  --history-limit 50 \
  --policy /absolute/path/to/nunchi-policy.json \
  --participant-id vigil \
  --participant-name Vigil \
  --participant-workspace /absolute/owner-only/empty-workspace \
  --participant-command /absolute/path/to/participant --json-stdio
```

The policy continuity scope is exactly
`discord:channel:123456789012345678`. On gateway readiness the adapter captures
up to 100 messages older than a local readiness barrier as context-only. Exact
live gateway messages then enter the shared one-active/one-newest-pending flow;
self-authored echoes remain context and cannot recursively wake the participant.
The standalone gateway has no durable sequence checkpoint and therefore
declares session continuity with a restart gap. It refuses recoverable social
suppression rather than treating history fetch as proof of gap-free continuity.

Display names and message text never bind Discord identity or routing. Native
snowflakes, exact mentions, replies and the configured channel do. Rich-only
messages receive a bounded text rendering. Outbound messages, exact replies,
closed allowed-mention user IDs and reactions use the shared request-correlated
REST action sink with Discord rate limits, a local send backstop and bounded
at-most-once request memory. The standalone `discord.py` surface does not expose
the gateway session/sequence needed for collision-free inbound reaction event
IDs, so it does not invent them; the shared MCP Discord transport has that
stronger inbound capability.
