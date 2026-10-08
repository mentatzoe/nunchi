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
- `reaction_capability`
- `remove_reaction`
- `read_history`

The registration call is mandatory before notifications or any other tool.
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
