# Install and operate Nunchi V2

## Artifact installation

Build and install the exact candidate into a new environment:

```sh
python3 -m build
python3 -m venv /tmp/nunchi-v2-clean
/tmp/nunchi-v2-clean/bin/python -m pip install --no-deps \
  dist/nunchi-2.0.0-py3-none-any.whl
/tmp/nunchi-v2-clean/bin/nunchi probe
/tmp/nunchi-v2-clean/bin/nunchi-install probe
```

The wheel is the review subject. A source checkout on `PYTHONPATH` is not
installed-artifact evidence.

Initialize stable operator-owned directories:

```sh
nunchi-install init \
  --config-root "$NUNCHI_CONFIG_ROOT" \
  --state-root "$NUNCHI_STATE_ROOT"
nunchi-install verify --config-root "$NUNCHI_CONFIG_ROOT"
```

Both roots must be private to the operator (`0700`). Runtime journals and
markers are created `0600`. The installer has no repository discovery and no
Hermes or Claude Code artifact operations.

## Trusted configuration

Every configured adapter uses a JSON file whose exact bytes are pinned by
`--config-sha256` or `NUNCHI_ADAPTER_CONFIG_SHA256`. The Codex runner uses
`NUNCHI_CODEX_CONFIG_SHA256`. The profile entry contains its own exact
`path`/`sha256` pin.

Trusted configuration owns:

- exact participant, native self actor, platform, room, and continuity scope;
- participant profile and delegated attention model;
- attention suppression/recovery/margin/error policy;
- bounded retention, snapshot, age, continuation, and expiry limits;
- participant model or fixed Codex model/session settings;
- stable state directory and optional pinned privileged-action policy;
- native transport endpoint and credential environment-variable names.

Room text cannot supply or override any of these values.

## Shared Discord transport

Install `nunchi[mcp-discord]`, then set:

```text
NUNCHI_DISCORD_TOKEN
NUNCHI_DISCORD_PARTICIPANT_ROUTES
NUNCHI_DISCORD_OUTPUT_HMAC_KEY
NUNCHI_DISCORD_STATE_DIRECTORY
```

`NUNCHI_DISCORD_PARTICIPANT_ROUTES` is a closed JSON object such as
`{"codex":["123456789"]}`. It defines exact participant/room pairs, never a
participant-by-room cross product.

`NUNCHI_DISCORD_OUTPUT_HMAC_KEY` must be at least 32 bytes and shared only
between the host-owned participant runner and transport. Output/history tool
calls require a short-lived, exact-operation HMAC. Accepted nonces are fsynced
before native dispatch and remain replay-blocked across restart.

The transport requests message, reaction, membership, and message-content
gateway intents. Each MCP session must authenticate one exact route before it
can receive notifications or invoke tools. Notifications carry the
gateway-attested bot actor and exact target participant. The bounded queue
never replaces an accepted event. If an event or one participant delivery is
lost, a durable per-route audit is written; after restart, that route receives
an explicit continuity gap before any later event.

## Restart and recovery

Restart:

1. cancels active and pending conversation opportunities;
2. discards continuation handles and pending approvals;
3. retains bounded canonical observations as context only;
4. retains receipt, authorization, output-nonce, and transport audits;
5. never promotes retained events into new wake work.

Corrupt or uncertain observation, receipt, authorization, nonce, session, or
continuity state fails closed. Operator recovery uses a new state directory or
an evidence-backed repair; the runtime never silently rewrites untrusted state.

## Rollback

Stop V2 processes before changing artifacts. Rollback is an atomic deployment
choice: do not run V1 and V2 participants in one room/session. Retain the V2
state directory for audit, but do not feed V2 journals to a V1 runtime.
