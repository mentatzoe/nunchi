# Install and configure Nunchi

**The package currently supplies no agent harness integrations.** The code
is under [architecture review](../AGENTS.md#architecture-goal-and-current-gap).

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

## Configure attention and the existing runtime

The attention model block is the part of today's configuration that the
architecture goal keeps:

```json
{
  "kind": "openai-compatible",
  "base_url": "https://llm.example/v1",
  "model": "provider/attention-model",
  "api_key_env": "NUNCHI_ATTENTION_API_KEY"
}
```

OpenAI-compatible routes require an explicit `base_url`. The other routes are
`decisions-api`, `messages-api` and `responses-api`; see
[model connections](platform.md#model-connections). Configuration records
credential environment-variable names, not their values.

The operator tools (`nunchi setup`, `config`, `diagnose`, `dashboard`,
`service`) and the reference adapters configure a runtime in which Nunchi
runs a participant model and sends for it. That runtime follows the design
under architecture review, so it is not documented here as a setup path.
Each command's `--help` describes its options.

## Optional Discord transport

The [transport guide](../integrations/mcp-discord/README.md) covers its
configuration, events and limits. It is optional; the intended library does
not require it.
