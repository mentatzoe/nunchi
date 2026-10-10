# Shared Discord V2 MCP transport

The transport owns Discord gateway/REST facts only. It never makes a social
judgment.

## Inbound notification

Method: `notifications/nunchi/v2/discord-event`

Closed params:

```json
{
  "schema_version": 2,
  "delivery_id": "discord:gateway:41:MESSAGE_CREATE:123",
  "room_id": "456",
  "event": {
    "id": "discord:message:123",
    "type": "message",
    "author_id": "discord:actor:789",
    "text": "hello",
    "mentioned_actor_ids": [],
    "mentions_room": false
  },
  "actors": {
    "discord:actor:789": {"display_name": "Zoe", "kind": "human"}
  },
  "continuity_gap": false,
  "target_participant_id": "codex",
  "transport_self_actor_id": "discord:actor:999"
}
```

Message, reaction add/remove, and membership events use the canonical V2 event
shapes. Exact self messages are delivered; participant-specific observation
retains them as context without self-waking.

A gap notification has `event: null`, `actors: {}`, and
`continuity_gap: true`. It tells the participant that something before the
next event may be missing, so it can read history. Gaps make subsequent
coverage continuity `unknown`.

## What reaches the participant

Every message reaches the participant, or the participant is told plainly
that something may have been missed. The rules, and what pins each:

- **A gap goes ahead of the next event, and the event follows it.** After a
  queue rejection, a lost delivery, a stream that ended, a source gap (a
  non-resumable gateway session marks every configured route uncertain, so a
  fresh process always starts with one), or a restart with unconfirmed
  deliveries in the journal, the next event for that exact route is queued
  behind a gap notification. The event is rejected (`queue-rejected`) only
  when the queue has no slot left, and then the gap that stands for it is
  still pending. An event queued behind a gap whose delivery failed is not
  delivered without it: it is recorded lost, and the next event queues a
  fresh gap. (Before 2026-10-10 the event itself was dropped and only the gap
  was delivered, so a person's first message after the transport started never
  reached the agent.) Tests: `tests/v2/test_runtime_hardening.py`
  (`TransportGapTests`) and `tests/v2/test_mcp_discord_gaps.py`.
- **The stream first, then registration.** The MCP SDK keeps no event store
  here: a notification sent to a session whose notification stream
  (`GET /mcp`) is not open is dropped, with no error
  (`SdkDropTests` pins that behavior for the pinned `mcp` version). A client
  must connect, open the stream, mark a gap of its own, register, and only
  then read (`StreamableMCPClient.open_stream`, `DiscordRoomConnection.serve`;
  [harness guide](../../docs/harness-guide.md), "Room events in"). The
  transport does not rely on the client alone: it sees each `GET /mcp` begin
  and end (`nunchi.mcp_discord._binding.track_streams`, standard ASGI, no SDK
  internals) and records a notification as delivered only while the session's
  stream is open. A notification for a session whose stream is not open, a
  client that registers first, or a runner whose stream has died while its
  session stays registered, is a failed delivery (`client-delivery-lost`),
  and a stream that ends marks its route uncertain. The next listener on the
  route is told with a gap. Before 2026-10-10 such messages were journaled as
  delivered and never arrived.
- **Threads are part of the room, by default.** A message or reaction in a
  thread under a routed channel carries the thread's own id as its channel.
  The transport asks Discord once for each channel that is not routed
  (`GET /channels/{id}`, remembered; `nunchi.mcp_discord.threads`) and, when it
  is a thread of a routed channel, delivers the event with `room_id` set to
  the routed channel and, for a message, `thread_root_event_id` set to
  `discord:message:<thread id>`. The first message of a forum post, whose id is
  the thread's own, starts the thread and names no other. When Discord cannot
  say what a channel is, the transport declares a source gap instead of
  dropping the event quietly. A reply, a post or a reaction about a message in
  a thread goes to the thread (`nunchi.integrations.discord_participant_transport.thread_of`),
  whichever way the agent saw the message: the host gives the transport the
  wake's events and every message the turn showed (a look-again, a steering
  or history page; a message its memory points at is read from the room's
  log), so the message's `thread_root_event_id` is there when the move goes
  out. The host's authorization for a room covers the threads under it
  (`ToolAuthorizer`). The setting is below.

Limits that remain:

- The transport knows a stream ended when its HTTP request ends, which for a
  connection that dies without a close (a network partition) is when the next
  write to it fails, not at once. Anything sent in between is covered by the
  gap the transport then marks, so the participant learns of it on its next
  event, not before.
- Each thread's parent comes from a REST lookup, once per channel that is not
  routed. The gateway's read loop waits for it at most 3 seconds
  (`ThreadDirectory.parent_within`): while Discord's REST API is slow or down,
  a late or failed lookup declares a gap (one record while the route is already
  pending) and the next message from that channel does not wait again. Taking
  the parents from the gateway's own events (`THREAD_CREATE`,
  `THREAD_LIST_SYNC` and the guild's thread list, which need the `GUILDS`
  intent) would spare the lookup and its wait. That is a follow-up, not done.
- The extra needs `mcp>=1.10,<2`. CI runs this transport's gap tests on 1.10.0
  and on the pinned newest release.
- Reaction capability is measured on the room channel, not on a thread.
- The probe's Discord room pins these (`evals/rehearsal/discord_room.py`,
  [docs/rehearsal.md](../../docs/rehearsal.md)): the first message and a
  thread remark read `reached` on every column, and a question asked in a
  thread must be answered there.

## Tools

- `register_participant`
- `send_message`
- `reply_message`
- `add_reaction`
- `reaction_capability`
- `remove_reaction`
- `read_history`

The registration call is mandatory before notifications or any other tool.
It takes the participant, its channel and, optionally, `threads_in_room` (a
boolean; see "Threads" below).
Every call requires `_nunchi_authorization`: a one-use HMAC over request,
participant, room, tool, exact argument digest, issue time, and nonce. The
transport checks the exact configured participant/room route, authenticated
session route, expiry, future time, operation mutation, MAC, and replay. It
fsyncs nonce consumption before REST dispatch and reloads the journal after
restart.

`reaction_capability` is a read-only, exact-route probe. It authenticates the
registered bot identity, reads the configured guild channel, member roles, and
permission overwrites, and returns only the effective add-reaction capability
plus a non-secret permission revision. Missing, denied, malformed, or
mismatched facts fail closed: the participant's turn offers no reaction.

## Threads

Whether a thread opened under a routed channel is part of the room is one
setting, the same in every harness: `threads_in_room` in the participant's
`binding` ([harness guide](../../docs/harness-guide.md), step 1). It is `true`
unless the config says `false`.

- **`true` (the default).** The participant hears the thread (a message
  carries `thread_root_event_id`), and its reply, post or reaction about a
  message in a thread lands in the thread.
- **`false`.** Thread messages are not part of the room: the participant
  neither hears them nor acts in them. The runner tells the transport at
  registration (`register_participant` with `threads_in_room: false`, inside
  the authorized arguments), so the transport sends that participant nothing
  from threads, and asks Discord about no channel at all while every route
  has said so. The library also refuses a thread message, which the transport
  marks with its thread (`thread_root_event_id`), in the participant's
  observation (`route-rejected`) whichever way a harness delivered it
  (`ParticipantBinding.threads_in_room`), so a harness that never tells the
  transport still gets the setting.

The transport's own configuration (below) has no such setting: one transport
can serve participants whose rooms differ. A participant that has not
registered yet counts as `true`, since leaving a message out is the worse
mistake.

## Configuration

Required:

```text
NUNCHI_DISCORD_TOKEN
NUNCHI_DISCORD_PARTICIPANT_ROUTES
NUNCHI_DISCORD_OUTPUT_HMAC_KEY
NUNCHI_DISCORD_STATE_DIRECTORY
```

Routes are a JSON object, for example `{"codex":["123456789"]}`. The union of
those numeric channels is the gateway allowlist, while authorization and
delivery remain bound to each exact pair.

Optional queue, backstop, host, port, and drain settings are documented by
`nunchi-mcp-discord --help`. Enable Discord message content and member
privileged intents for the configured bot.

The transport audit contains participant, delivery, and room IDs, never room
content or bot tokens. Logging installs token redaction before network startup.

On Linux the server makes its own process private first thing in `main`
(`nunchi.private_process.keep_private`). From then on another process of the
same OS user, such as an agent's shell command, gets `PermissionError` on its
`/proc/<pid>/environ` and `/proc/<pid>/mem`.

That does not make the token and the HMAC key safe from an agent of the same
OS user:

- At every start, any process of that user can read them in the server's
  starting environment for about a tenth of a second (Python's start-up and
  Nunchi's imports, before the call).
- An agent with an unsandboxed shell can leave a reader running and force a
  start: a signal needs only the same user, so it can kill the supervised
  server, and the supervisor starts it again.
- Other programs started with the same variables, environment files and
  root are not covered.

What closes the first two is a separation the agent cannot cross: Claude
Code's Bash sandbox (a fresh `/proc`), Codex's `workspace-write` or
`read-only` sandbox (its own process namespace), or running the agent as its
own OS user, which is not supported yet.
