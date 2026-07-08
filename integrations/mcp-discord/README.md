# nunchi-mcp-discord

A standing Discord transport server speaking MCP (streamable HTTP). One
server per bot account: any MCP-capable harness can hear a Discord room —
**including other bots** — in real time and post to it. Transport only; run
your nunchi admission gate harness-side.

Status: implemented — offline test suite in
`tests/test_mcp_discord_gateway.py` and `tests/test_mcp_discord_server.py`;
design record in [DESIGN.md](DESIGN.md).

## Install

```bash
pip install nunchi[mcp-discord]
```

The Discord gateway client is stdlib; the extra pins the official `mcp` SDK
(`mcp>=1.9,<2`). Nunchi core stays dependency-free.

## Discord Developer Portal setup (one-time)

1. <https://discord.com/developers/applications> -> your application -> **Bot**.
2. Under **Privileged Gateway Intents**, enable **MESSAGE CONTENT INTENT**.
   Without it the gateway refuses the connection (close code 4014) or
   delivers empty `content` — the server logs a loud warning either way.
3. Copy the bot token. Invite the bot to your server with at least
   *View Channel*, *Send Messages*, and *Read Message History*.

## Run

```bash
export NUNCHI_DISCORD_TOKEN="<bot token>"   # env var only; never logged
nunchi-mcp-discord
# serving MCP on http://127.0.0.1:3993/mcp
```

| Env var | Default | Meaning |
| --- | --- | --- |
| `NUNCHI_DISCORD_TOKEN` | (required) | Bot token. |
| `NUNCHI_MCP_DISCORD_HOST` | `127.0.0.1` | Bind host. The endpoint is unauthenticated — keep it local. |
| `NUNCHI_MCP_DISCORD_PORT` | `3993` | Bind port. |
| `NUNCHI_MCP_DISCORD_QUEUE_MAXSIZE` | `256` | Notification queue bound (oldest dropped when full). |
| `NUNCHI_MCP_DISCORD_BACKSTOP_MAX_SENDS` | `5` | Max sends per channel per window (backstop, default on). |
| `NUNCHI_MCP_DISCORD_BACKSTOP_WINDOW_SECONDS` | `10` | Backstop window. |
| `NUNCHI_MCP_DISCORD_DRAIN_TIMEOUT_SECONDS` | `10` | SIGTERM drain timeout for in-flight sends. |

## MCP contract

Every non-self message (human or bot) arrives as an unsolicited notification:

```json
{
  "method": "notifications/discord/message",
  "params": {
    "guild_id": "777888999",
    "channel_id": "444555666",
    "message_id": "111222333",
    "author_id": "777",
    "author_name": "peer-bot",
    "author_is_bot": true,
    "content": "ping",
    "timestamp": "2026-07-06T10:00:00.000000+00:00"
  }
}
```

Tools: `send_message(channel_id, content)`,
`reply_message(channel_id, message_id, content)`,
`read_history(channel_id, limit=50, before?)`.

Notifications begin after the client's first request (standard clients send
`tools/list` immediately after `initialize`, which registers the session).

## Harness configuration

Codex CLI (`~/.codex/config.toml`):

```toml
[mcp_servers.nunchi-discord]
url = "http://127.0.0.1:3993/mcp"
```

Goose (`~/.config/goose/config.yaml`):

```yaml
extensions:
  nunchi-discord:
    type: streamable_http
    uri: http://127.0.0.1:3993/mcp
    enabled: true
```

Kilo Code (MCP settings JSON):

```json
{ "mcpServers": { "nunchi-discord": { "url": "http://127.0.0.1:3993/mcp" } } }
```

Check your harness version's docs for streamable-HTTP MCP support; the
snippets above follow each harness's current remote-server syntax. The gate
hook itself (subscribing to the notification, calling `nunchi admit`,
obeying PASS) is harness-specific and intentionally out of scope here.

## Tests

```bash
python3 -m unittest tests.test_mcp_discord_gateway tests.test_mcp_discord_server
```

Offline-only: gateway resume after simulated disconnect, the load-bearing
bot-delivered/self-dropped filter, MESSAGE_CONTENT warning behavior, exact
notification schema against a mock MCP client, 429/backstop enforcement, and
token hygiene. Tests that need the `mcp` SDK are skipped with a reason when
it is not installed (same pattern as the discord.py-gated tests).
