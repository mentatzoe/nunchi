# Hermes integration — Nunchi V2

`nunchi-v2` is a wheel-distributed Hermes plugin discovered through the
`hermes_agent.plugins` entry-point group. It uses Hermes's versioned public
gateway participant hooks. Nunchi does not modify, replace, or wrap Hermes
files.

## Supported host

Nunchi requires
`PluginContext.gateway_message_hook_api_version == 2`. API major 2 supplies the
public `gateway_message`, `gateway_session_cancel`, and `gateway_shutdown`
hooks, immutable admitted message/route facts, the host-owned structured LLM
facade, and one-shot route-bound delivery.

The capability major is authoritative; Nunchi does not pin an exact Hermes
release or source identity. Backward-compatible Hermes changes keep major 2.
An incompatible host major fails registration before Nunchi registers any
message hook.

This interface exists in the separate Hermes implementation candidate and must
land in a Hermes release before ordinary users can activate this integration.
Ordinary users cannot activate it until then. This repository does not claim an
upstream merge, release, or acceptance.

When that release is available, run `hermes update` in the environment that
will run the plugin (or upgrade the package directly):

```bash
hermes update
# or
python -m pip install --upgrade hermes-agent
```

Then install the reviewed Nunchi wheel into that same Python environment.
Hermes discovers the `nunchi-v2` entry point through ordinary package metadata.
If the capability is missing, older, newer-incompatible, or malformed,
registration fails with a diagnostic beginning `Nunchi V2 was not activated`,
names the observed or missing capability, and tells the operator to update
Hermes and retry. No Nunchi hook is registered in that state, so unrelated
stock Hermes behavior remains active.

## Configure the plugin

After installing a compatible Hermes release, generate one closed
profile-bound config:

```bash
nunchi-hermes-v2-config \
  --hermes-profile default \
  --platform discord \
  --room-id 1234567890 \
  --actor-id discord:actor:1234 \
  --participant-id aleph \
  --profile-id aleph \
  --instructions-file /absolute/path/to/participant-instructions.md \
  --output-dir /absolute/private/config \
  --state-root /absolute/private/state \
  --provenance trusted:operator-config
```

Adapter-local profile names map to the shared platform-neutral opaque identity
`installation_id="hermes:<profile>"`. Enable the `nunchi-v2` entry point,
export the printed profile-scoped configuration environment key, restart
Hermes, and run `/nunchi-v2 probe`.

The probe must report `gateway_message_hook_api_version: 2`,
`supported_gateway_message_hook_api_major: 2`, `generation: 2`,
`v1_fallback: false`, and `operational: true` before opening ordinary
unmentioned room traffic.

## Commissioning boundary

The current source implementation is not merged, released, installed-runtime
verified, or commissioned. No repository checkout or editable install counts
as clean artifact evidence. Before claiming a deployed room works, one exact
Nunchi wheel, a released Hermes package exposing API major 2, and the exact
configuration must pass clean-install entry-point discovery, deterministic
lifecycle and receipt tests, independent review, and separately authorized
native Discord/Telegram canaries.

See [`docs/integrations/hermes-v2.md`](../../docs/integrations/hermes-v2.md)
for the interface, failure, lifecycle, and rollback boundaries.
