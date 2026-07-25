# Codex V2 room presence

`nunchi-codex-room-runner` is the only executable Codex integration.

It consumes `notifications/nunchi/v2/discord-event`, retains exact self and
peer events, runs the participant-bound attention model once, and wakes a
dedicated Codex task only for WAKE, both DEFER paths, bypass, or configured
error fallback. SUPPRESS makes no Codex call. Codex then contributes one action
or remains silent.

The runner owns the only Discord output seam. The Codex subprocess receives no
Nunchi, provider, or room transport credentials and is instructed not to call
Discord tools. The host fixes an isolated working directory, read-only
sandbox, output schema, bounded environment, and disabled shell, browser,
plugin, app, skill, and MCP capabilities; configuration cannot add arbitrary
arguments, binaries, or working directories. Its action is validated and
dispatched with a short-lived exact HMAC through the shared MCP transport.
There is no prompt hook, pre-tool hook, configuration app, or send-time social
judgment.

Persistent mode binds the saved Codex task ID to the pinned profile, exact
participant, native actor, room, continuity scope, model, sandbox, and disabled
feature set. Corrupt or mismatched state fails safely. Fresh mode starts an
isolated task per opportunity. Host-mediated context expansion may resume the
same task within that opportunity, but capability handles and cursors never
enter the Codex packet.

The runner authenticates its exact participant/room MCP session before
notifications or tools are available and verifies the gateway-attested
Discord self actor and target participant on every closed notification before
retaining facts.

The bundled plugin marker intentionally contains no tools and no hooks. It is
not required to run room presence.

```sh
nunchi-codex-room-runner --probe
nunchi-codex-room-runner \
  --config /secure/codex-v2.json \
  --config-sha256 "$NUNCHI_CODEX_CONFIG_SHA256"
```

The config contains exactly: `schema_version`, `binding`, pinned `profile`,
`attention`, `limits`, `state_directory`, shared MCP `transport`, and `codex`.
See `docs/platform-v2.md` for the shared ownership and conformance boundary.
