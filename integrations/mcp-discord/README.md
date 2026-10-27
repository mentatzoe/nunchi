# Shared Discord MCP transport

This optional transport supplies Discord events and authenticated tools for
reading and acting in a room. It makes no social judgments. There are currently
no supplied agent harness integrations; the standalone Discord reference adapter
uses this transport's shared helpers.

The protocol below describes the current implementation. It does not require
future library consumers to use this connector or give Nunchi control of an
agent's turns. See the [architecture goal](../../AGENTS.md#architecture-goal-and-current-gap).

## Configuration

Install the `mcp-discord` extra, configure the environment, then run
`nunchi-mcp-discord`. Required environment variables:

```text
NUNCHI_DISCORD_TOKEN
NUNCHI_DISCORD_PARTICIPANT_ROUTES
NUNCHI_DISCORD_OUTPUT_HMAC_KEY
NUNCHI_DISCORD_STATE_DIRECTORY
```

Routes are a JSON object, such as `{"example":["123456789"]}`. The gateway
accepts events from those channels; delivery and tool authorization remain
bound to each participant and channel pair. Enable Discord message content
and member privileged intents for the configured bot.

Optional settings:

| Environment variable | Default |
|---|---|
| `NUNCHI_MCP_DISCORD_HOST` | `127.0.0.1` |
| `NUNCHI_MCP_DISCORD_PORT` | `3993` |
| `NUNCHI_MCP_DISCORD_QUEUE_MAXSIZE` | `256` notifications |
| `NUNCHI_MCP_DISCORD_BACKSTOP_MAX_SENDS` | `5` sends per channel per window |
| `NUNCHI_MCP_DISCORD_BACKSTOP_WINDOW_SECONDS` | `10` seconds |
| `NUNCHI_MCP_DISCORD_DRAIN_TIMEOUT_SECONDS` | `10` seconds |
| `NUNCHI_DISCORD_MEMBERSHIP_ROOM_IDS` | All routed channels; otherwise a comma-separated subset |

One bot account uses one gateway, REST client, authorization secret, bounded
notification queue and durable state directory. The endpoint binds locally by
default. Exposing it requires an operator-managed network and authentication
boundary; the protocol assumes a trusted local caller plus authorization for
each operation.

## Events and missing context

The notification method is `notifications/nunchi/v2/discord-event`. Its params
are a closed object:

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
    "discord:actor:789": {"display_name": "Alice", "kind": "human"}
  },
  "continuity_gap": false,
  "target_participant_id": "example",
  "transport_self_actor_id": "discord:actor:999"
}
```

Messages, reaction additions and removals, and membership events use the
[canonical event shapes](../../docs/contracts/nunchi.md). The transport delivers
self-authored messages too; observation retains them as context without waking
that same participant.

When events may be missing, the next delivered event is preceded by a gap
notification: `event: null`, `actors: {}`, `continuity_gap: true`. This happens
after queue overflow, failed client delivery, a non-resumable gateway session,
or restart with unconfirmed deliveries. If the gap itself cannot be delivered,
the event behind it is recorded as lost and the gap remains pending. A fresh
process has no persisted gateway resume session, so it starts with a gap.

Clients must open their notification stream before registering:

1. Connect and open `GET /mcp`.
2. Mark a gap in local observation state.
3. Register the participant and begin reading notifications.

The MCP SDK does not retain notifications for clients without an open stream.
The server tracks stream requests and records delivery as failed when no stream
is open. A disconnected connection may only be detected on the next write; the
following event then carries the gap. The shared client implements this order
in `StreamableMCPClient.open_stream` and `DiscordRoomConnection.serve`.

## Tools and authorization

The transport exposes:

- `register_participant`
- `send_message`, `reply_message`
- `add_reaction`, `remove_reaction`, `reaction_capability`
- `read_history`

Registration is required before notifications or other tools. Every call needs
`_nunchi_authorization`: a one-use HMAC covering the request, participant, room,
tool, exact arguments, issue time and nonce. Checks include the configured and
authenticated session routes, expiry, future timestamps, argument mutation,
MAC and replay. Nonce consumption is durably written before REST dispatch and
reloaded after restart. Rate limits provide an additional bound on sends; they
do not replace authorization.

The remaining shared participant host calls these tools after committing an
action. The redesign removes that host's ownership of sending. Silence is not
a Discord operation and has no transport tool.

`reaction_capability` is a read-only probe for the registered bot and room. It
reads guild membership, roles and channel overwrites. Missing, denied, malformed
or mismatched facts report reactions as unsupported. The probe does not fully
model guild owners, member timeouts or thread permissions; see
[reference adapter limits](../../docs/adapters.md#errors).

## Threads

`threads_in_room` is a participant binding setting and registration argument.
It defaults to `true`:

- When enabled, a thread under a routed channel is part of that room. Message
  events carry `thread_root_event_id`; replies and reactions to thread messages
  are routed back to the thread.
- When disabled, the transport omits thread events for that participant.
  Observation also rejects events marked with a thread root, even if another
  caller supplies them. Participants sharing a transport can choose differently.

The transport looks up and caches the parent of an unfamiliar channel through
Discord REST. The gateway loop waits at most three seconds. A failed or late
lookup records a gap, and later messages from that channel do not wait again.
It does not yet use gateway thread-list events to avoid this lookup. Reaction
capability is measured on the room channel, not separately on each thread.

## Credentials and records

The transport audit records participant, delivery and room IDs, not message
content or bot tokens. Token redaction is installed before network startup.

On Linux, startup calls `nunchi.private_process.keep_private` to prevent other
processes of the same OS user from reading its `/proc` environment and memory.
That protection begins after Python starts and imports Nunchi. It does not
protect the initial environment, other processes given the same keys, credential
files, or access by root. An unsandboxed agent of the same OS user can also
signal the server and trigger a supervised restart.

A consumer must account for those limits in its credential and sandbox setup.
A separate process alone does not establish credential isolation. No retired
harness integration's sandbox claim establishes protection for a new consumer.

## Verification

The `mcp-discord` extra requires `mcp>=1.10,<2`. CI runs transport gap tests
with MCP 1.10.0 and 1.28.1, covering stream ordering, queue loss and restart
behavior. Isolated channel tests check messages, replies, reactions and gateway
reconnects against a local test server. They do not run conversations or measure
social behavior.

```sh
python3 -m unittest tests.v2.test_mcp_discord_gaps tests.v2.test_discord_wire
```
