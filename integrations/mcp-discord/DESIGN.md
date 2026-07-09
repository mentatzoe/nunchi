# nunchi-mcp-discord — design record

Standing MCP transport server: one server per Discord bot account, letting
any MCP-capable harness (Codex CLI, Kilo Code, Goose, ...) hear a Discord
room — including other bots — in real time, and post to it. This is the
"1 transport + N thin gate hooks" pattern: the transport carries **no gate
logic**; nunchi admission runs harness-side.

Why it exists: of ~10 surveyed Discord MCP servers, none delivered the
required conjunction of (1) bot-authored messages unfiltered *and* with
content populated, (2) real-time MCP push rather than polling, (3) a generic
MCP contract any harness can consume.

## Components

```
Discord gateway (wss)                          MCP clients (harnesses)
      |                                                ^
      v                                                | streamable HTTP (/mcp)
+-----------+   payload    +------------------+        |
| ws.py     |------------->| gateway.py       |        |
| RFC 6455  |   dicts      | sans-IO protocol |        |
| client    |<-------------| IDENTIFY/RESUME/ |        |
| (stdlib)  |   actions    | heartbeat state  |        |
+-----------+              +------------------+        |
      ^                        | Dispatch(MESSAGE_CREATE)
      | connect/reconnect      v                       |
+-----------+              +------------------+   +-----------------+
| runner.py |              | events.py        |   | _binding.py     |
| backoff,  |              | self-drop filter |-->| mcp SDK: tools, |
| heartbeat |              | notif schema     |   | sessions, push  |
| timing    |              +------------------+   +-----------------+
+-----------+                  | bounded queue         ^
                               v (drop-oldest)         |
                           +------------------+        |
                           | server.py        |--------+
                           | pump, in-flight  |
                           | drain, main()    |
                           +------------------+
                               |
                               v  tool calls (thread pool)
                           +------------------+   +-------------------+
                           | tools.py         |-->| rest.py + limiter |
                           | validate, shape  |   | urllib, buckets,  |
                           | backstop         |   | 429/5xx retry     |
                           +------------------+   +-------------------+
```

Layering rule: everything except `_binding.py` is import-safe stdlib
(no mcp SDK, no discord.py). The gateway is hand-rolled sans-IO — protocol
decisions (identify vs resume, heartbeat bookkeeping, close classification)
are a pure state machine, so disconnect/resume behavior is tested offline
without sockets. `_binding.py` is the only SDK-bound module and stays thin:
tool registration, session tracking, notification push, uvicorn lifecycle.

## MCP contract

- Notification `notifications/discord/message`, params:
  `guild_id (str|null), channel_id (str), message_id (str), author_id (str),
  author_name (str), author_is_bot (bool), content (str), timestamp (str|null)`.
  Snowflakes are strings (53-bit JSON consumers). Pushed on the session's
  standalone SSE stream (no related request).
- Tools: `send_message(channel_id, content)`,
  `reply_message(channel_id, message_id, content)`,
  `read_history(channel_id, limit=50, before?)`. Results reuse the
  notification field names.
- Sessions are registered when they first issue a request (standard clients
  send `tools/list` right after `initialize`); notifications begin then.

## Failure modes

| Failure | Behavior |
| --- | --- |
| Gateway connection drops (EOF, 1006, op 7 RECONNECT) | Close, reconnect with capped exponential backoff (1s..60s), RESUME with stored `session_id`/`seq`; fresh IDENTIFY only if Discord invalidates the session (op 9 d:false, close 4007/4009). |
| Missed heartbeat ACK (zombie connection) | Client closes with code 4000 (resumable) and reconnects via the same path. |
| Fatal close: 4004 bad token, 4013/4014 intents | **No retry.** `GatewayFatalError` with an operator hint (portal intent toggle / token env var); the process shuts down via SIGTERM so supervisors notice. Permanent errors must not burn retries. |
| MCP client gone (session dead mid-send) | That send fails, the session is pruned from the registry, the pump keeps running for remaining sessions. Delivery is best-effort; the transport never buffers for absent clients beyond the queue below. |
| No MCP client connected | Gateway events still drain through the queue; broadcast is a no-op. History is recoverable via `read_history`. |
| Slow MCP client / full queue | The notification queue is bounded (default 256). When full, the **oldest** event is dropped with a WARNING — for an admission gate the room's present outranks its backlog, and memory stays bounded. |
| Discord 429 on send | Per-route bucket guard sleeps out `X-RateLimit-Reset-After`; on 429 the `retry_after` (global flag honored) is respected with at most 3 retries, then a tool error. |
| Transport backstop exceeded | Tool call fails immediately with `retry in Ns` — never queued, never sent. |
| Discord 401/403 on send | Non-retryable: tool error on the first response. |
| Empty `content` with rich message data | Normalize conversational embed fields, Components V2 text displays, attachment descriptions/names, stickers, and polls into tagged, bounded text. Exclude interaction chrome such as button labels. Live notifications and history use the same normalizer. |
| Empty `content` on MESSAGE_CREATE with no rich data | Signature of a missing MESSAGE_CONTENT intent: loud WARNING with the portal remediation step; the notification is still delivered with `content: ""` (documented, tested — no silent garbage). |
| SIGTERM / SIGINT | Uvicorn graceful shutdown -> lifespan drain: stop pumping, wait for in-flight sends (default 10s), close gateway with 1000, exit. |

## Security posture

- **Token hygiene (hard requirement).** The token enters via
  `NUNCHI_DISCORD_TOKEN` only. It is excluded from `Config.__repr__`; gateway
  payloads (IDENTIFY/RESUME carry it) and HTTP headers are never logged; a
  `TokenRedactionFilter` on every root log handler rewrites any record that
  would contain it. A dedicated test serializes every tool schema, a sample
  notification, error strings, and captured log output and asserts the token
  is absent.
- **No gate logic.** The transport never decides who may speak; it drops
  exactly one author: itself (`author.id == our bot user id`). Everything
  else — human or bot — is delivered. Plain message content is unchanged;
  rich-only messages receive the documented text fallback so downstream
  admission does not mistake visible speech for an empty event.
- **One server per bot account.** Identity is the process boundary; no
  tenant mixing, no shared token store.
- **Send backstop, default on.** Sliding-window cap (5 sends / 10s per
  channel) bounds the blast radius of a runaway harness independently of
  Discord's own limits.
- **Input hardening.** Snowflake arguments must be numeric strings (guards
  the REST URL path); content is capped at Discord's 2000 chars.
- **Local by default.** Binds 127.0.0.1:3993; exposing it wider is an
  explicit operator choice (the MCP endpoint is unauthenticated).

## Non-goals

- **No gating.** No PASS/ACK/ASK/SPEAK anywhere in this package; that is the
  harness's nunchi hook.
- **No message transformation.** Content passes through verbatim, both ways.
- **No multi-tenant.** One bot token, one gateway session, one process.
- **No DM/typing/presence intents, no sharding, no voice.** GUILD_MESSAGES |
  MESSAGE_CONTENT only; DMs that still arrive are forwarded with
  `guild_id: null`.
- **No persistence.** No replay after restart; `read_history` is the
  catch-up path.

## Dependencies

`nunchi[mcp-discord]` pins `mcp>=1.9,<2` (streamable HTTP manager stabilized
in 1.9; 2.0 changes the server API). starlette/uvicorn/pydantic arrive
transitively with the SDK. Nunchi core keeps zero runtime dependencies; the
gateway client is stdlib on purpose (no discord.py) so the resume state
machine stays testable offline.
