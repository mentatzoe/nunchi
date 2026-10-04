# Codex V2 room presence

`nunchi-codex-room-runner` is the dedicated shared-Discord Codex host. The
reference Discord, Matrix, Telegram, and generic channel adapters can also
host the same Codex participant backend.

It consumes `notifications/nunchi/v2/discord-event`, retains exact self and
peer events, runs the participant-bound attention model once, and wakes a
dedicated Codex task only for WAKE, both DEFER paths, bypass, or configured
error fallback. SUPPRESS makes no Codex call. Codex then contributes one action
or remains silent.

The runner owns the only Discord output seam. The Codex subprocess receives no
Nunchi, provider, or room transport credentials and is instructed not to call
Discord tools. The current supported `capability_mode` is explicitly
`reduced`: the host fixes an isolated working directory, read-only sandbox,
output schema, bounded environment, and disables effect-bearing shell,
browser, plugin, app, skill, and MCP capabilities. A configured-capability
mode is rejected until those native effects have a version-checked final-effect
bridge. This is an open product limitation tracked by issue #60, not normal
Codex parity. The validated participant action is dispatched with a short-lived
exact HMAC through the shared MCP transport. The runner uses no second social
prompt hook, pre-tool hook, configuration app, or send-time social judgment.

Persistent mode requires a pinned `runtime_identity` and binds the saved Codex
task ID to the exact executable path and digest, reported Codex version,
`CODEX_HOME`, provider, account binding, credential scope, authentication mode,
continuity generation, profile, participant, native actor, room, model, sandbox,
and reduced feature set. The subprocess is launched under that exact
`CODEX_HOME`; `codex login status` must agree with the pinned authentication
mode. For ChatGPT, API-key, or access-token modes, persistent continuity also
requires readable file-backed authentication: the stored account ID is checked
when available, otherwise a non-secret credential digest is bound. A keyring
whose account identity Codex cannot expose must use fresh mode rather than make
a false continuity claim. The runtime identity is re-attested immediately
before execution. The task ID is staged after a successful, valid participant
result and is made durable only after the shared host accepts participant
silence or reaches the output commit point. Process failure, malformed output,
expiry, cancellation, or host rejection cannot advance resumable state. Because
non-interactive Codex resume is not transactional, the runner consumes the old
pin before resuming it; an unaccepted attempt leaves a recoverable diagnostic
marker and the next opportunity starts a new task instead of reusing possibly
mutated history. An accepted attempt commits the task and clears that marker.
Corrupt or mismatched state fails safely; the probe reports the incompatibility
and a new-task repair path. Fresh mode starts an isolated task per opportunity and
never reports persistent continuity. Host-mediated context expansion may
resume the same staged task within that opportunity, but capability handles and
cursors never enter the Codex packet.

For portable hosting, `nunchi-discord`, `nunchi-matrix`, `nunchi-telegram`,
and `nunchi-channel` accept a `codex` participant block in place of
`participant_model`. They retain their native normalizer, authenticated self
check, continuity facts, transport, scheduler, participant host, and receipt
owners; only the isolated participant invocation changes to Codex. Repeated
native delivery/event IDs converge on the same durable observation
deduplication boundary.

The generic `nunchi-channel` surface additionally requires
`ingress_auth: {"source_id":"...","hmac_key_env":"..."}`. Each input line is
an envelope containing `payload` and `authorization`. Authorization version 1
binds the trusted source ID and SHA-256 of canonical compact JSON payload
bytes. Its HMAC-SHA256 material is
`nunchi.channel.ingress.v1 + NUL + source_id + NUL + payload_sha256`. The key
comes from the named environment variable, is at least 32 bytes, and is never
passed into Codex. Native adapters use provider-authenticated ingress and
reject this generic authentication block.

The runner authenticates its exact participant/room MCP session before
notifications or tools are available and verifies the gateway-attested
Discord self actor and target participant on every closed notification before
retaining facts.

The bundled `UserPromptSubmit` hook does not treat raw `<channel>` markup as a
native event. It blocks that prompt with a usable native/HMAC-adapter
alternative because current prompt-hook input cannot attest native identity,
mentions, replies, reactions, or continuity. Routing an already interactive
third-party channel session into the same Codex task therefore remains
unsupported until that channel exposes an authenticated native event seam;
the adapter host is the usable autonomous alternative. These are source
interfaces only until each installed adapter has attributable live proof.

```sh
nunchi-codex-room-runner --probe
nunchi-codex-room-runner \
  --config /secure/codex-v2.json \
  --config-sha256 "$NUNCHI_CODEX_CONFIG_SHA256"
```

The config contains exactly: `schema_version`, `binding`, pinned `profile`,
`attention`, `limits`, `state_directory`, shared MCP `transport`, and `codex`.
`codex` accepts `model`, `timeout_seconds`, `session_mode`, `capability_mode`,
and `runtime_identity`. Persistent mode requires this closed identity shape:

```json
{
  "provider": "openai",
  "account_id": "workspace-or-account-opaque-id",
  "credential_scope": "chatgpt:workspace-opaque-id",
  "auth_mode": "chatgpt",
  "codex_home": "/absolute/private/codex-home",
  "continuity_generation": 1
}
```

`auth_mode` is one of `chatgpt`, `api-key`, or `access-token` and is checked
against `codex login status`. Do not put a token or secret in `account_id` or
`credential_scope`. The pinned
top-level config SHA protects these non-secret identity claims. `--probe`
reports the configured session mode, committed task or incompatibility, runtime
digest/version, hashed account binding, disabled capabilities, and the current
reduced-mode limitation. See `docs/platform-v2.md` for the shared ownership and
conformance boundary.

Persistent mode also requires an explicit non-empty `model`; relying on a
changing runtime default cannot establish resumable identity.
