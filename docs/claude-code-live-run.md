# Run the Claude Code V2 participant live

Procedure for the first live run of the Claude Code participant in a real
Discord room. Written for an operator holding a Discord bot token, a model
credential, and a room.

Source, deterministic, and clean-installed-runtime checks pass. The live leg
does not exist yet, and producing it is what this document is for. A clean run
does not by itself make the status `Verified` — see [Filing the
result](#filing-the-result).

## What the participant is

A **headless, tool-less `claude` subprocess**, spawned once per conversation
opportunity.

It is **not** the operator's interactive Claude Code session, and **not** the
Discord plugin. It runs with no tools, no MCP servers, no settings sources, no
slash commands, and no path to Discord; the host owns the single output commit
point. `session_mode: "persistent"` means the same session id is resumed with
`--resume` across turns — continuity, not the operator's own session.

This reverses the earlier plugin-based approach, which intercepted `PreToolUse`
and patched the plugin's transport. The isolation is the reason: a `CLAUDE.md`
one directory above the workspace reaches a bare turn (measured — see
`evals/v2/claude_code/participant_scenes.py`), so a participant inside the
operator's live plugin session would inherit that ambient instruction surface
along with the plugin's tools and the operator's settings. Identity would stop
coming solely from the digest-pinned profile, which is the property the
contract turns on.

Whether the plugin-session shape is wanted anyway is a product question, not a
question this document settles.

## What has never run against anything real

Watch these first; this is where a first live run realistically fails.

1. **The runner's startup loop** — `client.connect()` →
   `register_transport()` → `client.notifications()` against a real
   `nunchi-mcp-discord`. Tests drive `handle()` directly with a client double.
2. **Real participant and real transport in one process.** The subprocess has
   been exercised with a recording transport, the transport with a stub
   participant. Never both.
3. **The privileged workspace executor under a live operator policy.** Every
   confinement test constructs the coordinator directly.

Everything else — identity binding, authority, all eight dispositions,
cancellation, receipt ordering, session pinning, workspace confinement — is
deterministic and already covered.

## 1. Credential the participant

Do this first. It is the most common way a first run fails.

The participant runs under a private `CLAUDE_CONFIG_DIR`
(`<state_directory>/claude-code-participant-config`) and inherits only an
explicit environment allowlist. A credential in the operator's own shell does
not reach it.

Because that path is fixed and persistent, and because `--safe-mode` leaves
auth working normally (unlike `--bare`, which never reads OAuth or the
keychain), the participant can be credentialled **as itself**:

```sh
# The config directory does not exist until the runtime is constructed.
nunchi-claude-code-room-runner --config config.json --config-sha256 <64 hex> --probe

CLAUDE_CONFIG_DIR=<state_directory>/claude-code-participant-config claude auth login
CLAUDE_CONFIG_DIR=<state_directory>/claude-code-participant-config claude auth status
```

This is better than exporting a key into the runner's environment: the host's
own credential never becomes reachable by the participant turn at all, rather
than being withheld by an allowlist that has to stay correct.

`claude auth status` against that exact directory is the authoritative check.
Do not substitute a `claude -p 'say ok'` probe under a scratch config dir — in
a managed environment that reports success under any config dir, because the
credential arrives by injected file descriptor.

**Re-check before every session.** OAuth expiry is a routine cause of failure
and an expired login looks identical to a working one until the first wake.
The runner prints a warning at startup and `--probe` reports
`participant_credential` as `authenticated`, `logged-out`, `absent`, or
`unknown`.

Alternative, for Bedrock, Vertex, or CI: export a credential into the runner's
environment. Only these variables reach the participant — `ANTHROPIC_API_KEY`,
`ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL`,
`ANTHROPIC_CUSTOM_HEADERS`, the `ANTHROPIC_DEFAULT_*_MODEL` trio,
`CLAUDE_CODE_USE_BEDROCK`, `AWS_BEARER_TOKEN_BEDROCK`, `AWS_REGION`,
`CLAUDE_CODE_USE_VERTEX`, `GOOGLE_APPLICATION_CREDENTIALS`, `CLOUD_ML_REGION`,
`HOME`, `PATH`, `TMPDIR`, `USER`, `LOGNAME`, `LANG`, `LC_ALL`,
`SSL_CERT_FILE`, and the proxy variables.

The Discord output HMAC key and the classifier credential are withheld
deliberately. Do not add either to the allowlist; the runner refuses an
`output_key_env` naming an allowlisted variable for exactly that reason.

## 2. Install the candidate

The wheel is the subject. A source checkout on `PYTHONPATH` is not evidence.

```sh
python3 -m build
python3 -m venv /tmp/nunchi-live
/tmp/nunchi-live/bin/python -m pip install --no-deps dist/nunchi-2.0.0-py3-none-any.whl
/tmp/nunchi-live/bin/python -m pip install 'mcp>=1.9,<2'
/tmp/nunchi-live/bin/nunchi probe
/tmp/nunchi-live/bin/nunchi-claude-code-room-runner --probe
```

Record the packaged source tree, `git rev-parse HEAD:src`, as the candidate
identity. A raw wheel SHA-256 is environment-dependent and is not usable for
this; the evidence packet documents an order-independent wheel content digest
for the artifact itself.

The unconfigured probe must print `"configured": false`, `"v1_fallback":
false`, and exit 0.

## 3. Discord identity and transport

The participant needs its own bot account, distinct from any other participant
in the room; identity reuse breaks the exact-route binding. Enable the
**message content** and **server members** privileged intents, then invite it.

```sh
export NUNCHI_DISCORD_TOKEN=...
export NUNCHI_DISCORD_PARTICIPANT_ROUTES='{"vigil":["<channel id>"]}'
export NUNCHI_DISCORD_OUTPUT_HMAC_KEY=...             # >= 32 bytes
export NUNCHI_DISCORD_STATE_DIRECTORY=/srv/nunchi/discord-state   # 0700
/tmp/nunchi-live/bin/nunchi-mcp-discord
```

Listens on `http://127.0.0.1:3993/mcp` unless `NUNCHI_MCP_DISCORD_HOST` or
`NUNCHI_MCP_DISCORD_PORT` say otherwise. The routes map is a closed
participant-to-rooms map, never a cross product: its key must equal
`participant_id` and its channel id must equal `binding.room_id`.

The HMAC key is shared between transport and runner and nothing else. Give it a
name in the runner's environment that is **not** on the participant allowlist,
and point `transport.output_key_env` at that name.

## 4. Profile and pinned configuration

Profile — exactly these five non-empty string fields:

```json
{
  "profile_id": "vigil-live-1",
  "participant_id": "vigil",
  "actor_id": "discord:actor:<bot user id>",
  "instructions": "You are Vigil...",
  "provenance": "trusted:operator/live-1"
}
```

Configuration — required: `schema_version`, `binding`, `profile`, `attention`,
`limits`, `state_directory`, `transport`, `claude_code`; optional:
`authorization`.

```json
{
  "schema_version": 2,
  "binding": {
    "participant_id": "vigil",
    "actor_id": "discord:actor:<bot user id>",
    "platform": "discord",
    "room_id": "<channel id>",
    "continuity_scope_id": "discord:channel:<channel id>"
  },
  "profile": { "path": "/srv/nunchi/profile.json", "sha256": "<64 hex>" },
  "attention": {
    "policy": { "preattention_enabled": true },
    "model": { "model": "<classifier model>", "api_key_env": "NUNCHI_ATTENTION_API_KEY" }
  },
  "limits": {},
  "state_directory": "/srv/nunchi/claude-code-state",
  "transport": {
    "url": "http://127.0.0.1:3993/mcp",
    "timeout_seconds": 30,
    "output_key_env": "NUNCHI_DISCORD_OUTPUT_KEY"
  },
  "claude_code": { "session_mode": "persistent", "timeout_seconds": 180 }
}
```

- `transport` must contain exactly those three keys.
- `claude_code` accepts only `model`, `timeout_seconds`, `session_mode`
  (`persistent` or `fresh`), and `effort`.
- `attention.model` is read only when `preattention_enabled` is true, and its
  credential must be present in `api_key_env` or construction fails closed.
- `binding.actor_id` must equal the gateway-attested bot actor, and the
  profile's `actor_id` must equal it too.
- `state_directory` is created `0700`.

Pin the configuration bytes with `--config-sha256` (or
`NUNCHI_CLAUDE_CODE_CONFIG_SHA256`) and check the configured probe:

```json
{"actor_id":"...","configured":true,"generation":2,"participant_credential":"authenticated",
 "participant_id":"vigil","participant_tools_enabled":false,"persistent_session":true,
 "privileged_actions_enabled":false,"product":"nunchi","product_version":"2.0.0",
 "room_id":"...","send_time_social_judgment":false,"session_mode":"persistent",
 "shared_discord_transport":true,"surface":"claude-code","v1_fallback":false}
```

`persistent_session` reflects the configured `session_mode`; with `fresh` it
must read `false`.

## 5. Run

```sh
/tmp/nunchi-live/bin/nunchi-claude-code-room-runner \
  --config /srv/nunchi/config.json --config-sha256 <64 hex>
```

A healthy start is silent apart from the transport's `register_participant`
handshake; the runner refuses to proceed if the registration attestation does
not match its exact binding.

`Claude Code shared transport reconnect after operational error` on stderr is
the reconnect loop, backing off 1s to 30s. Each reconnect declares a continuity
gap, cancels in-flight work, and records it — correct behaviour, but a
continuous loop means the transport is unreachable or the route is wrong.

## 6. Scenes to capture

Run these in the room. After each, capture the appended lines of
`<state_directory>/claude-code-v2-receipts.jsonl` and the Discord message or
its absence. Receipt stages are `observation` → `attention` →
`participant-host` → `transport`, each appended only by its owning writer; the
ordering is part of what you are attesting.

| # | Scene | Trigger | Expect |
|---|---|---|---|
| 1 | `SUPPRESS` | ambient chatter not for the participant | attention `SUPPRESS`, no host turn, no message |
| 2 | `WAKE`, contribution | address it directly, within its brief | four-stage chain, `transport` `sent`, a real message |
| 3 | `WAKE`, silence | an open moment not worth speaking into | attention `WAKE`, `participant-host` `silent`, **no** transport stage |
| 4 | classifier `DEFER` | ambiguous moment | `DEFER` recorded, host turn taken |
| 5 | margin `DEFER` | near-threshold moment | margin-DEFER distinguishable in receipt reasons |
| 6 | `PREATTENTION_BYPASS` | restart with `preattention_enabled: false` | bypass disposition, host turn, no classifier call |
| 7 | `ERROR_FALLBACK` | point the classifier at a dead port | `ERROR_FALLBACK` per `error_action`, never a fabricated `SUPPRESS` |
| 8 | continuity | stop mid-conversation, restart, follow up | continuity gap first; retained observations are context only and never new wake work |
| 9 | privileged action | configure `authorization`, request a file write | journal entry, executor `sent` with digest, file inside the root |

Scene 3 is the one most often skipped and the most important: waking and then
choosing silence is what distinguishes this from a bot that answers everything.
Confirm the transport stage is absent, not merely that no message appeared.

For scene 9, confirm the negatives too: a path escaping the root records
`failed`, and a path whose target changed underneath the write records
`unknown`. Never `sent`.

**Scenes 1, 4, 5, and 7 need a classifier credential.** The attention model
speaks one OpenAI-compatible protocol and defaults to OpenRouter; there is no
Anthropic-native transport yet (issue #35). With `preattention_enabled: false`
the only path is `PREATTENTION_BYPASS`, which wakes the participant for every
observation, so an operator holding only Anthropic credentials cannot reach
`SUPPRESS`, either `DEFER`, or `ERROR_FALLBACK` — the four scenes carrying the
social judgment. A run without a classifier is a real result but a partial one.
Record which scenes were unreachable; do not report the remainder as a pass.

Record for each scene: the receipt lines verbatim; for anything delivered, the
native Discord message id and that it is attributable to the participant's own
bot actor in the configured room; the wall-clock time; the installed identity;
and the exact command line with configuration and profile digests.

## Failure modes

| Symptom | Meaning |
|---|---|
| digest mismatch | configuration bytes changed after hashing; re-hash, do not relax the pin |
| `output authorization key is absent or short in X` | `X` unset or under 32 bytes in the runner's environment |
| `output key must not be readable by the participant turn` | `output_key_env` names an allowlisted variable |
| `profile and exact transport self differ` | profile identity does not match the binding |
| `authenticated Discord self differs from exact binding` | the token's actor is not `binding.actor_id` |
| `notification targets another participant/room` | routes map and binding disagree |
| `executable is not installed on trusted PATH` | the runner's PATH, not the login shell's |
| participant turn times out | `claude_code.timeout_seconds` is a stage bound inside the host's total deadline; a late result is `unknown` and cannot revive the opportunity |
| transport result `unknown` | the acknowledgement was empty, stale, cross-bot, wrong-content, or malformed — the attestation checks working |

Uncertainty never becomes success anywhere in this system. When `unknown`
appears where `sent` was expected, the question is what the acknowledgement
actually said.

## Filing the result

One clean run closes most of the live gap: the lifecycle plumbing, identity,
authority, cancellation, receipts, and native transport facts are all
deterministic, so a single correct observation of them is dispositive.

It does not close social quality, especially the false-suppression rate. That
needs the release-proof profile's trial counts and its no-degenerate-pass rule.
The recorded participant scenes in the evidence packet are an existence proof
that a real headless turn returns exactly one valid action envelope, never a
quality claim.

A clean run lets the packet record the live leg. It does not by itself
authorise merge: review approval on this surface is explicitly bound to an
exact candidate and does not establish live proof, `Verified` status, a second
isolated final-candidate reviewer, or a reviewer-held challenge set.

Two rules that have already cost this surface real time:

1. Never accept a script's own success output as verification. Read the
   artifact back from git or from the installed location.
2. Measure recorded figures from a clean `git archive` of the committed head,
   not from a working tree mid-edit.
