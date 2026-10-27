# Reference adapters and channel limits

These optional examples run a plain model participant on a channel, through
the obsolete turn code. Their channel code (normalizing native events and
reporting capabilities) is what fits the
[architecture goal](../AGENTS.md#architecture-goal-and-current-gap), where
channel integrations supply context and run no agent.

All reference adapters share `ReferenceAdapterRuntime`. Native payloads are
normalized before attention and cannot alter trusted binding or policy.
The runtime still owns turns and sending; that ownership is under review.

| Surface | Ingress | Output | Retained context | Explicit native limits |
|---|---|---|---|---|
| Generic JSONL | message, reaction, membership | message, reply, reaction | bounded persisted | host attests all native facts |
| Discord | message, reaction add/remove, membership | message, reply, reaction add/remove | bounded persisted plus live gateway | configured channel routes only |
| Matrix | message, reaction add, membership | message, reply, reaction add | bounded persisted plus `/sync` | portable room-wide mention relation unavailable; reaction removal unavailable without native reaction event ID |
| Telegram | message, membership | message, reply | live-only visibility with bounded retained state | ordinary history, reactions, and portable room-wide mentions unavailable |

`--probe` without configuration reports only static installed capabilities.
Configured probes verify exact pinned configuration and required credentials
but do not claim a live connection.

## Channel compatibility

Users should be able to choose a channel connector with its limits explained.
Those limits can affect what Nunchi perceives; they do not justify requiring
Nunchi's own transport or starting an agent on the user's behalf.

For example, the official Claude Code Discord plugin was inspected at revision
`58267944f92187b7d6a1c822165c96c81c864806`:

- **Live messages from bots are filtered.** Nunchi could not observe those
  messages through that plugin's live notifications.
  [Source](https://github.com/anthropics/claude-plugins-official/blob/58267944f92187b7d6a1c822165c96c81c864806/external_plugins/discord/server.ts#L805).
- **History has different limits.** `fetch_messages` can include bot messages,
  but returns at most 100 messages, with no pagination argument. It formats
  author names rather than author IDs, so that output alone cannot establish
  exact participant identity.
  [Source](https://github.com/anthropics/claude-plugins-official/blob/58267944f92187b7d6a1c822165c96c81c864806/external_plugins/discord/server.ts#L657).
- **The connector signals receipt itself.** It sends a typing indicator and
  an optional acknowledgement reaction before forwarding the message. An
  empty `ackReaction` disables the reaction; the inspected handler has no
  equivalent switch for typing.
  [Source](https://github.com/anthropics/claude-plugins-official/blob/58267944f92187b7d6a1c822165c96c81c864806/external_plugins/discord/server.ts#L851).

These are observations about that pinned connector, not a claim that a Nunchi
integration exists or that later connector versions have the same limits.

## Platform capabilities in the operator surface

The operator surface (`nunchi setup`, `nunchi config`, `nunchi diagnose`, and
the dashboard) shows static reaction capabilities for the reference platforms.
The adapters own that data in `src/nunchi/adapters/platforms.py`; the core
registry names no platform. `channel` and `discord` declare reaction add and
remove, `matrix` declares reaction add, and `telegram` declares no reactions.

A room on any other platform name is still valid. Its compatibility is
`unregistered`, and `config show` and `diagnose` warn that its capabilities
are unknown: reactions count as unsupported, so the participant cannot react,
until the integration measures them at runtime.

## Generic JSONL

Input is one closed object per line:

```json
{
  "delivery_id": "host:delivery:1",
  "room_id": "room-1",
  "event": {
    "id": "host:message:1",
    "type": "message",
    "author_id": "host:actor:alice",
    "text": "hello",
    "mentioned_actor_ids": [],
    "mentions_room": false
  },
  "actors": {
    "host:actor:alice": {"display_name": "Alice", "kind": "human"}
  }
}
```

## Backfill

Matrix records its first `/sync` batch as context without waking participants.
Telegram reads at most 100 recent updates on startup, keeps them as context,
and discards older pending updates. It records that missing history before
long polling begins, so startup cannot keep processing an endless backlog.

Restart never schedules retained observations. A fresh Discord process has no
durable gateway resume session, so both the shared and standalone transports
declare a source gap before accepting post-start facts. Within-process resume
continuity is transport-attested; a bounded queue or client-delivery loss also
produces an explicit persistent gap.

## Errors

Input that cannot be converted to an event is audited without a fabricated
social decision. Wrong routes, exact duplicates, and an event whose exact
author or cause is transport-bound self are not wake eligible. Provider errors
follow the configured `WAKE` or `NO_WAKE` operational policy and remain
`status: error`. Matrix and Telegram report output as sent only when the native
response includes a stable message/event identity for the exact target room; a
successful HTTP envelope with a missing or mismatched native acknowledgement
remains `unknown`.

Reaction support comes from the platform's current permissions. It decides
which reactions the participant may use. The
shared Discord MCP transport measures the authenticated bot's effective guild
roles and channel overwrites. Matrix binds `whoami` to the configured actor and
compares that user with the room's `m.reaction` power level. A denial, missing
state, identity mismatch, or malformed response counts as unsupported.

The shared Discord MCP transport's probe (`src/nunchi/mcp_discord/rest.py`)
models guild text channels only. It does not model three cases:

- **Guild owner.** Discord grants the owner every permission; the probe does
  not read `owner_id`, so an owning bot behind a restrictive `@everyone` is
  reported unable to react.
- **Member timeout.** The probe ignores `communication_disabled_until`, so a
  timed-out bot can be reported able to react, and the reaction then fails
  at dispatch.
- **Threads.** A thread payload carries no `permission_overwrites`, so the
  probe errors and the participant cannot react there. This has not been checked against
  live Discord.
