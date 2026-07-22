# Discord V2 transport operator guide

Nunchi's Discord transport is one factual source and action boundary for one
participant in one room. It does not decide whether that participant should
speak. Run a separate process and MCP credential for every participant/room
binding.

## Startup and restart

1. Create an owner-only state directory and set the required Discord token,
   MCP bearer token, participant ID, channel ID, and expected bot user ID.
2. Start `nunchi-mcp-discord`. READY must attest the configured bot user ID;
   mismatch terminates before delivery.
3. The consumer initializes MCP, opens GET/SSE, then calls
   `subscribe_events({})`. It verifies the returned participant, room, self and
   capability binding before restoring the bounded history snapshot.
4. Live notifications carry Discord session, sequence, and READY-attested self
   identity. Sequence gaps produce an explicit continuity boundary before any
   successor. Once known, that restart gap taints signed history handles and
   page coverage until a separate bounded recovery can prove closure; bounded
   REST history alone never upgrades it to `restart-safe`.

The state directory contains exclusive request-claim files. Preserve it across
restart and backup/upgrade; deleting it reopens request IDs and is therefore a
security-sensitive operator action. Capacity exhaustion fails closed and
requires an explicit migration, never silent eviction.

## Context and actions

Live messages may carry a signed continuation capability. `read_history`
accepts only a request correlated to that handle and exact trigger, room,
participant, continuity scope, direction, and declared event/byte caps. Cursors
are opaque and signed. History is context, not a queue of response obligations.

Every send, reply, and reaction requires an immutable `request_id`. The server
claims it durably before contacting Discord. Messages use Discord's enforced
nonce facility; ambiguous non-idempotent POSTs without such protection are not
retried. The action object is closed: wake sources, social labels, foreign
receipt stages, and other control fields are rejected before an effect.

## Failure interpretation

- `unroutable` means no trustworthy candidate event could be constructed or
  the event crossed the configured routing boundary. It is not SUPPRESS.
- A continuity-boundary notification means later facts may follow a known gap;
  it is never silently converted into continuous history.
- `unknown` transport outcome means an effect may have happened but was not
  safely confirmed. Reusing the same request ID remains prohibited.
- Queue, replay-store, or durable-claim capacity exhaustion stops delivery. An
  event-store health signal terminates the whole transport even though the MCP
  SDK internally catches its router exception; later sessions are never shown
  a falsely continuous successor. An operator must restore capacity or migrate
  state before restart.
- Cancellation of the MCP await does not mark shutdown idle while its native
  worker still runs; shutdown waits for the actual worker future up to the
  configured drain deadline.
