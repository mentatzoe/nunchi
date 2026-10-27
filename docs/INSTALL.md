# Install and configure Nunchi

**The package currently supplies no agent harness integrations.** These
instructions cover the remaining library, reference adapters and operator
tools, which are being
[redesigned](../AGENTS.md#architecture-goal-and-current-gap).

## Build and inspect a package

Use a clean checkout and environment to check a particular revision. Old
`build/` output can otherwise carry deleted modules into a wheel:

```sh
python3 -m pip install build
python3 -m build
python3 -m venv /tmp/nunchi-clean
/tmp/nunchi-clean/bin/python -m pip install --no-deps dist/nunchi-2.0.0-py3-none-any.whl
/tmp/nunchi-clean/bin/nunchi probe
/tmp/nunchi-clean/bin/nunchi-install probe
source /tmp/nunchi-clean/bin/activate
```

Use the wheel filename produced by the build. Record its version, the source
revision and the commands when reporting results. A source checkout on
`PYTHONPATH` does not prove that an installed package works.

## Configure the existing runtime

The operator CLI manages profiles for the existing runtime. It does not
install or configure an agent harness.

```sh
nunchi setup \
  --profile example \
  --participant-id example \
  --actor-id discord:bot:9 \
  --display-name Example \
  --instructions 'Take part in the conversation.' \
  --platform discord \
  --room-id 42 \
  --room-name lounge \
  --continuity-scope-id discord:channel:42 \
  --attention-model provider/attention-model \
  --participant-model provider/participant-model
nunchi config show --profile example
nunchi diagnose --profile example
nunchi dashboard --profile example
```

Replace the example identity, room and models with your own values. Setup
validates the configuration and records integrity hashes automatically.
`--platform` accepts any platform name; unknown platforms produce a
[capability warning](adapters.md#platform-capabilities-in-the-operator-surface).

The configuration records credential **environment-variable names**, not their
values. Set values outside the dashboard. Each model can specify `kind`,
`base_url` and an optional `credential_env`; setup defaults the credential names
to `NUNCHI_ATTENTION_API_KEY` and `NUNCHI_PARTICIPANT_API_KEY`. The CLI and
dashboard show the same configuration, health, service and receipt data.
Changes require the current profile revision.

Private configuration and state roots can also be created explicitly:

```sh
nunchi-install init --config-root "$NUNCHI_CONFIG_ROOT" --state-root "$NUNCHI_STATE_ROOT"
nunchi-install verify --config-root "$NUNCHI_CONFIG_ROOT"
```

Directories must be private to the operator (`0700`); journals use `0600`.

## Reference adapter configuration

Reference adapters use a JSON file pinned by `--config-sha256` or
`NUNCHI_ADAPTER_CONFIG_SHA256`. Its profile entry has its own `path` and
`sha256`. Trusted configuration defines the identity and room, models,
context limits, state location, transport endpoint and optional authorization
policy. Room messages cannot override these settings.

An attention model block looks like:

```json
{
  "kind": "openai-compatible",
  "base_url": "https://llm.example/v1",
  "model": "provider/attention-model",
  "api_key_env": "NUNCHI_ATTENTION_API_KEY"
}
```

OpenAI-compatible attention and participant models require an explicit
`base_url`. Other reference-adapter attention routes are `decisions-api`,
`messages-api` and `responses-api`. Messages and Responses routes require
an explicit endpoint and accept `temperature`, `effort`, `max_tokens` and
`extra_body`; the Messages route also accepts `auth: "x-api-key"` or
`"bearer"`. The Decisions route has its own default endpoint and accepts an
explicit `url`. See [model connections](platform.md#model-connections).

The reference adapters create a plain model participant. They do not attach
to an existing agent, and their results do not establish harness compatibility.

## Optional Discord transport

Install the extra with `python3 -m pip install '.[mcp-discord]'`. The transport
uses these environment variables:

```text
NUNCHI_DISCORD_TOKEN
NUNCHI_DISCORD_PARTICIPANT_ROUTES
NUNCHI_DISCORD_OUTPUT_HMAC_KEY
NUNCHI_DISCORD_STATE_DIRECTORY
```

Routes name exact participant/room pairs, for example
`{"example":["123456789"]}`. The output key must be at least 32 bytes and
shared only with the authorized consumer. Each MCP session authenticates one
route; output and history calls require a short-lived signature for that
operation. Consumed nonces remain blocked after restart.

The [transport guide](../integrations/mcp-discord/README.md) covers setup,
thread handling, notification gaps, identity checks and output receipts. This
transport is optional; it is not a requirement for the intended library.

## Service tools

Existing service tools supervise arbitrary configured commands. Their presence
does not give Nunchi ownership of agents in the target architecture.

Declare commands with repeated `--service NAME='COMMAND ...'` arguments to
setup. Use `nunchi service start|stop|restart|status|logs|reset`, or
`nunchi service install` for a launchd/systemd user definition. The worker
enforces the configured restart policy.

Service installation copies declared environment values into a private state
file. Generated service definitions and the dashboard do not expose those
values. Reinstall the service after rotating them. Profile reset preserves
receipts; `nunchi uninstall --profile NAME` stops and removes that profile.
Deleting package state requires the separate
`nunchi-install uninstall --purge-state` command.

## Recovery and rollback

The current runtime cancels active work and pending approvals on restart.
It retains observations as context but does not replay them as new turns.
Continuation handles are discarded. Uncertain or corrupt state stops the
affected operation; it is not silently rewritten.

Stop affected processes before changing installed artifacts. Keep state with
the version that wrote it unless compatibility is documented. See
[commands and compatibility](STABILITY.md).
