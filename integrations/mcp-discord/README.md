# nunchi-mcp-discord V2

This is the shared Discord source/action transport for Nunchi V2. One process
owns one Discord bot account, one participant identity, and one exact channel. It
normalizes gateway facts and exposes room-bound transport actions; it never
makes a social attention decision.

V1 mode no longer exists. Setting `NUNCHI_MCP_DISCORD_MODE` is a configuration
error rather than a compatibility switch.

## Install and run

The published V1 release does not contain the V2 MCP transport. From this
candidate source checkout, install the local project and optional SDK stack:

```sh
python3 -m pip install '.[mcp-discord]'

export NUNCHI_DISCORD_TOKEN='<Discord bot token>'
export NUNCHI_MCP_DISCORD_CHANNELS='123456789012345678'
export NUNCHI_MCP_DISCORD_AUTH_TOKEN='<separate random secret, at least 32 ASCII characters>'
export NUNCHI_MCP_DISCORD_PARTICIPANT_ID='vigil'
export NUNCHI_MCP_DISCORD_SELF_ACTOR_ID='<Discord bot user snowflake>'
export NUNCHI_MCP_DISCORD_STATE_DIR="$PWD/.nunchi-discord-state"
nunchi-mcp-discord
```

Enable Discord's **MESSAGE CONTENT INTENT** for the bot. The V2 gateway also
requests guild-message-reaction events. The default endpoint is
`http://127.0.0.1:3993/mcp`.

Every MCP HTTP request must carry:

```text
Authorization: Bearer <NUNCHI_MCP_DISCORD_AUTH_TOKEN>
```

Missing, wrong and duplicate Authorization headers receive `401` before the MCP
application runs. The MCP credential must be different from the Discord token;
both are excluded from configuration representations and installed as log
redaction secrets. Configure the bearer header in the consuming MCP client via
its secret/environment-header facility rather than committing it to a project
file.

| Environment variable | Default | Meaning |
|---|---:|---|
| `NUNCHI_DISCORD_TOKEN` | required | Discord bot credential; gateway/REST only. |
| `NUNCHI_MCP_DISCORD_CHANNELS` | required | Exactly one trusted channel snowflake for this process and credential. |
| `NUNCHI_MCP_DISCORD_AUTH_TOKEN` | required | Separate MCP bearer credential, at least 32 printable non-whitespace ASCII characters. |
| `NUNCHI_MCP_DISCORD_PARTICIPANT_ID` | required | Exact portable participant ID bound to this MCP process. |
| `NUNCHI_MCP_DISCORD_SELF_ACTOR_ID` | required | Exact Discord bot user snowflake; READY must attest the same identity. |
| `NUNCHI_MCP_DISCORD_STATE_DIR` | required | Existing owner-only directory for durable request claims. Never share it across unrelated bindings. |
| `NUNCHI_MCP_DISCORD_BLOCKED_ACTORS` | empty | Exact actor snowflakes made unroutable by transport policy. |
| `NUNCHI_MCP_DISCORD_HOST` | `127.0.0.1` | Loopback HTTP bind only: `127.0.0.1`, `::1`, or `localhost`. |
| `NUNCHI_MCP_DISCORD_PORT` | `3993` | HTTP bind port. |
| `NUNCHI_MCP_DISCORD_QUEUE_MAXSIZE` | `256` | Bounded live-notification queue; overflow terminates the transport session instead of hiding a gap. |
| `NUNCHI_MCP_DISCORD_BACKSTOP_MAX_SENDS` | `5` | Maximum transport effects per channel/window. |
| `NUNCHI_MCP_DISCORD_BACKSTOP_WINDOW_SECONDS` | `10` | Local send-backstop window. |
| `NUNCHI_MCP_DISCORD_DRAIN_TIMEOUT_SECONDS` | `10` | Graceful in-flight tool drain deadline. |

## V2 MCP contract

The sole notification method is:

```text
notifications/nunchi/v2/discord/event
```

Its params contain `schema_version: 2`, `platform: "discord"`, exact guild and
channel IDs, gateway session/sequence, the READY-attested self user ID, and one closed `native_input`. That input is either a trusted
`candidate-event` with canonical message/reaction and actor facts, or an
`unroutable` audit record with no candidate payload. Display names and content
never bind identity or routing. Self-authored messages are retained so the
observation owner can record the exact deterministic no-wake fact.

After opening the GET/SSE stream, a client must call `subscribe_events({})`
once. The response binds participant, room, self actor and capabilities and
returns a bounded history snapshot. Registration occurs before that snapshot
is read, closing the backfill/live race; events arriving during or after the
snapshot are stored for SSE replay. Other tools fail before subscription.

The closed tool set is:

- `subscribe_events()`
- `send_message(request_id, channel_id, content, mention_user_ids?)`
- `reply_message(request_id, channel_id, message_id, content, mention_user_ids?)`
- `add_reaction(request_id, channel_id, message_id, reaction)`
- `read_history(request_id, handle_id, direction, max_events, max_bytes, anchor_event_id?, cursor?)`

Every channel argument must be in the startup allowlist. Message mentions are
closed by default and only exact `mention_user_ids` may ping. Replies fail when
their exact target is absent. Discord route limits and the local send backstop
apply to every effect; no effect is queued for later social reconsideration.
Every mutation reserves `request_id` durably before the native effect. Message
POSTs carry an enforced Discord nonce derived from that request ID; ambiguous
non-idempotent POSTs are otherwise never retried. `read_history` accepts only a
signed participant/room/continuity/trigger-bound I-010D capability and returns
a coverage-honest byte/event-bounded page and signed next cursor. Its projection retains exact native
snowflake strings, bot and room-mention booleans, replies, and structured user
mentions; coercible or malformed API identity/addressing fields make the tool
call fail instead of disappearing from the returned context.

The notification queue is deliberately not a durable obligation queue. When it
fills, the new event is refused and the transport session terminates; it never
drops one event and then delivers a falsely continuous successor.
Reconnect/resume preserves Discord's gateway session when possible and rejects
any non-contiguous sequence before a successor is delivered. Fresh identity or
unverifiable lineage emits an explicit continuity-boundary notification.
The bounded MCP event store replays a disconnected SSE stream within the live
process; process restart is reported honestly through the subscription binding
and history snapshot rather than claimed gap-free. A known gateway restart gap
also remains set in signed history-handle/page coverage; REST history cannot by
itself prove that every missed gateway event was recovered. Each new process
starts conservatively gap-tainted, and invalid-session or close-code paths that
require fresh IDENTIFY project a boundary before the new session's successor.
No current path upgrades those epochs to `restart-safe`. Event-limit
truncation uses a one-extra bounded probe and is reported as `events`, while
byte truncation is reported independently. Replay-store exhaustion raises a
supervised global health failure and terminates the transport even though the
pinned MCP SDK catches its router-task exception internally. Notification
writes are concurrent and individually bounded: a stalled client is evicted
without delaying healthy clients or the Discord gateway; a global broadcast
failure terminates the transport instead of hiding a delivery hole.
Ambiguous raw gateway JSON (duplicate keys or non-finite numbers) also closes
the socket and resumes from the last attested Discord sequence; the transport
never drops that frame and then admits a falsely continuous successor.

## Security boundary

- Room input cannot alter the channel allowlist, bearer credential, bot
  identity, endpoint, backstop or blocked-actor policy.
- The bot token is used only for Discord IDENTIFY/RESUME and REST Authorization.
- Credential-bearing gateway Resume connects only to `wss` on
  `gateway.discord.gg` or a Discord-owned subdomain; Ready-event URLs with
  userinfo, custom ports, paths, fragments, or nonstandard queries are refused.
- The separate MCP token authenticates machine clients before MCP dispatch.
- Tool errors are generic and never copy Discord response bodies or secrets.
- Snowflake values are validated before URL construction; tool schemas reject
  unknown fields and oversized content.
- The built-in plaintext server is loopback-only. Bearer authentication remains
  mandatory; remote access requires a separately secured TLS proxy.
- There is no conversational classifier, participant roster, social ledger or
  V1 verdict path in this transport.

## Verification

```sh
python3 -m unittest \
  tests.test_mcp_discord_gateway \
  tests.test_mcp_discord_server \
  tests.v2.test_discord_transport \
  tests.v2.test_mcp_transport_client_v2
```

The offline suite covers gateway identify/resume, strict raw-JSON recovery,
exact self retention,
collision-free reaction identity, newest-preserving backpressure, channel
scoping, bearer denial/acceptance, credential separation, rate limits,
backstops, token hygiene and SDK-optional import behavior.
The client-side suite also rejects malformed/uncorrelated MCP handshakes and
bounds multi-line SSE framing overhead.

Run the SDK-bound wiring tests in an environment with the declared extra:

```sh
python3 -m venv /tmp/nunchi-mcp-test
/tmp/nunchi-mcp-test/bin/pip install '.[mcp-discord]'
PYTHONPATH=src /tmp/nunchi-mcp-test/bin/python -m unittest -v \
  tests.test_mcp_discord_server tests.v2.test_discord_transport
```

See `docs/transport/discord-v2.md` for the operator lifecycle and failure model.
