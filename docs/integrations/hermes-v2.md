# Hermes V2 integration

## Status

The Nunchi V2 Hermes adapter is **release-blocked**. It is packaged as a normal
Hermes plugin entry point, but it is not a supported or commissionable
integration until an official Hermes release provides gateway-message hook API
version 2.

Nunchi does not patch, rewrite, or otherwise mutate a Hermes source checkout.
There is no host-patch command, bundled patch, supported-commit pin, or rollback
path.

## Required public Hermes contract

The adapter requires a released Hermes API that provides:

- `PluginContext.gateway_message_hook_api_version == 2`;
- an immutable terminal `gateway_message` hook invoked after host command,
  authorization, replay, and startup controls;
- immutable normalized event and route values;
- a one-shot route-bound delivery capability whose `send`, `reply`, and
  `react` methods return adapter-authenticated native acknowledgements;
- `gateway_session_cancel` and `gateway_shutdown` lifecycle hooks;
- revocation boundaries that do not return while a started native effect is
  still live, including callbacks that suppress task cancellation;
- isolation from behavior-changing legacy pre-dispatch hooks.

Plugin registration fails closed when the versioned API is absent or when the
legacy pre-dispatch path coexists. Released Hermes versions that do not expose
this contract are unsupported; installing Nunchi must not attempt to change
them.

## Installation shape

Once a compatible Hermes release exists, install the Nunchi distribution into
the same Python environment as Hermes. Hermes discovers the adapter through the
`hermes_agent.plugins` entry point named `nunchi-v2`.

Create one closed, profile-bound configuration with:

```bash
nunchi-hermes-v2-config \
  --config /absolute/path/to/nunchi-v2.json \
  --participant-profile /absolute/path/to/participant-profile.json \
  --platform discord \
  --room-id 1234567890 \
  --participant-id aleph \
  --actor-id discord:actor:1234 \
  --hermes-profile default \
  --state-dir /absolute/private/state \
  --provenance trusted:operator-config
```

The Hermes profile is adapter-local configuration. At the shared Nunchi
boundary it maps to the platform-neutral opaque identity
`installation_id="hermes:<profile>"`.

## Verification boundary

A supported installation must bind its evidence to the exact released Hermes
version, Nunchi artifact digest, profile-bound configuration digest, and native
transport acknowledgements. Source-only tests or a private Hermes branch do not
establish released-host compatibility, installed entry-point discovery, or
live platform commissioning.
