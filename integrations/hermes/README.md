# Hermes integration — Nunchi V2

`nunchi-v2` is a normally installed Hermes plugin packaged in the Nunchi wheel.
It is not an admission gate and it does not modify Hermes source.

## Current support state

The adapter is **not currently commissionable**. It requires public Hermes
gateway-message hook API version 2, and no official Hermes release currently
contains that interface. A private branch, local patch, or source checkout is
not a supported substitute.

When the required API ships, the plugin will:

1. receive only host-admitted ordinary messages through an immutable terminal
   hook;
2. record the native event in Nunchi's shared V2 observation provider;
3. apply the participant's delegated attention exactly once;
4. invoke one ordinary participant turn for WAKE, DEFER, trusted bypass, or the
   configured operational fallback;
5. dispatch ordinary output only through a host-owned, route-bound delivery
   capability with authenticated native acknowledgement;
6. fence routed work through public session-cancel and gateway-shutdown hooks.

There is no V1 classifier, normal-agent fallback, private adapter access,
session-store access, or checkout-patching path.

## Required released Hermes API

The installed Hermes distribution must expose:

- `PluginContext.gateway_message_hook_api_version == 2`;
- `gateway_message`, `gateway_session_cancel`, and `gateway_shutdown` hooks;
- immutable normalized event and route values;
- isolated terminal dispatch after command, authorization, replay, startup, and
  other host control paths;
- route-bound `send`, `reply`, and `react` capabilities that return native,
  adapter-authenticated acknowledgement evidence;
- revocation settlement that does not return while a started native effect is
  still live, including when a callback suppresses task cancellation.

Registration fails closed if the versioned API is absent. The public probe also
fails closed if a behavior-changing legacy pre-dispatch hook coexists.

## Installation shape after a compatible release

Install one exact Nunchi wheel into the same Python environment as the released
Hermes distribution. Hermes discovers the `nunchi-v2` entry point in the
`hermes_agent.plugins` group. No repository checkout or editable install counts
as clean installation evidence.

Generate a closed profile-bound configuration:

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

The adapter's Hermes profile maps into shared core as the opaque,
platform-neutral `installation_id="hermes:<profile>"`. A multiplexed gateway
loads one fail-closed Nunchi instance per immutable routed profile.

Suppression remains disabled unless private live-recovery evidence binds the
exact released Hermes version, Nunchi artifact digest, profile, participant,
actor, room, continuity scope, and a verified later-hearing scene.

## Verification boundary

Before this integration can be described as supported, the exact same candidate
must pass all of these independent gates:

- upstream API accepted and shipped in an official Hermes release;
- reproducible Nunchi wheel build;
- clean installation into that released Hermes environment;
- host entry-point discovery and versioned API registration;
- deterministic and adversarial lifecycle/receipt suites;
- exact-current independent review;
- separately authorized live Discord and Telegram commissioning with native
  ingress and acknowledgement identities.

Source tests establish source behavior only. They do not establish release
availability, clean installation, live transport parity, or commissioning.
