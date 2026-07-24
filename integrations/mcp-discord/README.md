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
`continuity_gap: true`. It is emitted before the next accepted room event after
queue rejection or client-delivery loss for that exact participant route.
Pending gaps and accepted-but-unconfirmed deliveries are reconstructed after
restart. A non-resumable gateway session marks every configured route
uncertain. Gaps make subsequent coverage continuity `unknown`.

## Tools

- `register_participant`
- `send_message`
- `reply_message`
- `add_reaction`
- `remove_reaction`
- `read_history`

The registration call is mandatory before notifications or any other tool.
Every call requires `_nunchi_authorization`: a one-use HMAC over request,
participant, room, tool, exact argument digest, issue time, and nonce. The
transport checks the exact configured participant/room route, authenticated
session route, expiry, future time, operation mutation, MAC, and replay. It
fsyncs nonce consumption before REST dispatch and reloads the journal after
restart.

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
