# nunchi-mcp-discord V2

This is the shared Discord source/action transport for Nunchi V2. One process
owns one Discord bot account and an exact non-empty channel allowlist. It
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
| `NUNCHI_MCP_DISCORD_CHANNELS` | required | Exact comma-separated channel snowflakes available to notifications and tools. |
| `NUNCHI_MCP_DISCORD_AUTH_TOKEN` | required | Separate MCP bearer credential, at least 32 printable non-whitespace ASCII characters. |
| `NUNCHI_MCP_DISCORD_BLOCKED_ACTORS` | empty | Exact actor snowflakes made unroutable by transport policy. |
| `NUNCHI_MCP_DISCORD_HOST` | `127.0.0.1` | Loopback HTTP bind only: `127.0.0.1`, `::1`, or `localhost`. |
| `NUNCHI_MCP_DISCORD_PORT` | `3993` | HTTP bind port. |
| `NUNCHI_MCP_DISCORD_QUEUE_MAXSIZE` | `256` | Bounded live-notification queue; oldest is replaced when full. |
| `NUNCHI_MCP_DISCORD_BACKSTOP_MAX_SENDS` | `5` | Maximum transport effects per channel/window. |
| `NUNCHI_MCP_DISCORD_BACKSTOP_WINDOW_SECONDS` | `10` | Local send-backstop window. |
| `NUNCHI_MCP_DISCORD_DRAIN_TIMEOUT_SECONDS` | `10` | Graceful in-flight tool drain deadline. |

## V2 MCP contract

The sole notification method is:

```text
notifications/nunchi/v2/discord/event
```

Its params contain `schema_version: 2`, `platform: "discord"`, exact guild and
channel IDs, and one closed `native_input`. That input is either a trusted
`candidate-event` with canonical message/reaction and actor facts, or an
`unroutable` audit record with no candidate payload. Display names and content
never bind identity or routing. Self-authored messages are retained so the
observation owner can record the exact deterministic no-wake fact.

The closed tool set is:

- `send_message(channel_id, content, mention_user_ids?)`
- `reply_message(channel_id, message_id, content, mention_user_ids?)`
- `add_reaction(channel_id, message_id, reaction)`
- `read_history(channel_id, limit=50, before?)`

Every channel argument must be in the startup allowlist. Message mentions are
closed by default and only exact `mention_user_ids` may ping. Replies fail when
their exact target is absent. Discord route limits and the local send backstop
apply to every effect; no effect is queued for later social reconsideration.
`read_history` is an authenticated, allowlisted privileged read and returns
bounded factual context, never wake jobs.

The notification queue is deliberately not a durable obligation queue. When a
client falls behind, the oldest queued event is replaced by the newest and a
warning is logged. Reconnect/resume preserves Discord's gateway session when
possible, but the MCP transport promises neither persistent notification replay
nor gap-free restart continuity. Consumers backfill bounded history as context
before accepting new live opportunities.

## Security boundary

- Room input cannot alter the channel allowlist, bearer credential, bot
  identity, endpoint, backstop or blocked-actor policy.
- The bot token is used only for Discord IDENTIFY/RESUME and REST Authorization.
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
  tests.v2.test_discord_transport
```

The offline suite covers gateway identify/resume, exact self retention,
collision-free reaction identity, newest-preserving backpressure, channel
scoping, bearer denial/acceptance, credential separation, rate limits,
backstops, token hygiene and SDK-optional import behavior.
