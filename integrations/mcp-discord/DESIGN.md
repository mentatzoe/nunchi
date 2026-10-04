# Shared Discord V2 transport design

One bot account owns one gateway, REST client, output-authority secret, bounded
notification queue, and durable transport state directory.

```text
Discord gateway
  -> sans-I/O session/resume/heartbeat protocol
  -> configured room filter
  -> canonical V2 message/reaction/membership normalization
  -> durable queue admission audit
  -> bounded queue
  -> MCP V2 notification broadcast

Host-owned participant runner
  -> exact one-use HMAC tool authorization
  -> transport replay journal
  -> argument and route validation
  -> send backstop
  -> Discord REST
```

The transport preserves exact self events and never makes a participant
relevance decision. The host uses exact self to prevent self-wake while
retaining factual context.

Queue overflow rejects the newest unaccepted delivery; it never erases an
already accepted event. Missing client delivery is also a gap. Both are
audited, and the next accepted event for that room is preceded by an explicit
`continuity_gap: true` notification.

Native tools require a MAC over request ID, participant, room, tool, canonical
argument digest, issue time, and nonce. Verification checks allowlists,
mutation, expiry/future time, MAC, and replay. Nonce consumption is fsynced
before REST dispatch and survives restart. Rate limiting is an additional
blast-radius bound, not authorization.

The MCP endpoint binds locally by default. Exposing it requires an operator
network/authentication boundary; the application protocol itself assumes a
trusted local host plus the per-operation HMAC.
