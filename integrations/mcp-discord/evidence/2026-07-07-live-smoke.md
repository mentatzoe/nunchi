# nunchi-mcp-discord — first live smoke (2026-07-07)

Operator-sanctioned run (Zoe, 2026-07-07). Server run from this branch
(`feat/mcp-discord-transport`, editable install with the `mcp-discord` extra)
against real Discord, bot identity **Dalgos** (`1494761296686481509`), room
`#nunchi-room` (`1522258711047831653`). Trigger messages posted by a second
bot, **Vigil** (`1494822530643398827`), via plain REST — bot-authored by
construction. No gate logic anywhere in this path (transport only).

## Verified live

| # | Claim | Evidence |
|---|---|---|
| 1 | Gateway handshake completes: HELLO → IDENTIFY → READY | probe run using this branch's `WSClient`+`GatewayProtocol`: `READY as Dalgos session=a184b7b2…` |
| 2 | **Bot-authored message delivered with content populated** (the load-bearing claim) | `MESSAGE_CREATE author=Vigil bot=True content='probe trigger 2'` (probe); MESSAGE_CONTENT intent active on the app (`GATEWAY_MESSAGE_CONTENT_LIMITED` flag) |
| 3 | Real-time push over streamable-HTTP SSE with the documented schema | raw SSE tap: `data: {"method":"notifications/discord/message","params":{"guild_id":"1484971544512958597","channel_id":"1522258711047831653","message_id":"1523874271112200438","author_id":"1494822530643398827","author_name":"Vigil","author_is_bot":true,"content":"raw sse probe trigger","timestamp":"2026-07-07T02:12:18.448000+00:00"}}` |
| 4 | `send_message` posts as the transport's bot | tool result: message `1523874634049650769`, author Dalgos, `author_is_bot: true` |
| 5 | `read_history` returns recent messages, same schema | tool result contains #4's message and the Vigil triggers |
| 6 | Self-echo suppressed (drop exactly self) | the tap that received Vigil's messages saw **0** notifications for Dalgos's own send |
| 7 | Broken MCP client pruned, pump continues | server log: `dropping MCP session after failed send:` followed by healthy delivery to the raw tap |
| 8 | Long-lived session stays healthy | single gateway TCP connection held >5 min (heartbeat/ACK path live) |

## Finding (design-relevant): standard SDK clients drop the vendor notification

The official `mcp` Python SDK **client** receives `notifications/discord/message`
but discards it at pydantic validation — the method is not in the SDK's closed
`ServerNotification` union. The notification is provably on the wire (#3); a raw
or permissive client consumes it fine. Consequence for harness integrations
(Codex/Kilo/Goose consume MCP via their own client stacks): either (a) each
harness's notification handling must be verified empirically, or (b) the
transport additionally offers a spec-native envelope (e.g., MCP logging
notifications, whose `data` is free-form) behind a config flag. Decision owed
in the Codex integration step.

## Not yet verified live

- Gateway resume after a real network interruption (offline-tested only).
- Rate-limit backstop under real 429 pressure (offline-tested only).
- A real harness (Codex/Kilo) consuming the push — next step.

## Diagnostic note for the logbook

First smoke attempt looked dead: server logged only `gateway connected
(identifying)` and nothing after. Cause: the runner logs nothing at READY or
per-dispatch, so a healthy session is indistinguishable from a wedged one at
INFO level. The gateway was in fact healthy the whole time (probe #1/#2), and
the missing notifications were the SDK-client validation drop (#finding).
Follow-up queued: one INFO line at READY (`ready as <bot> (session …)`) and a
DEBUG line per dispatched event.
