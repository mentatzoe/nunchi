# Hermes integration — Nunchi V2

`nunchi-v2` is a wheel-distributed Hermes plugin discovered through the
`hermes_agent.plugins` entry-point group. It uses Hermes's versioned public
participant-host API. Nunchi does not modify, replace, or wrap Hermes files.

## Supported host

Nunchi requires
`PluginContext.participant_host_api_version == 2`. This umbrella major covers
the lifecycle hooks, immutable routed profiles and sessions, native delivery
receipts, structured LLM calls, tool dispatch, command registration, and
plugin loading/failure status that Nunchi consumes.

The capability major is authoritative; Nunchi does not pin an exact Hermes
release or source identity. Backward-compatible Hermes changes keep major 2.
The narrower `PluginContext.gateway_message_hook_api_version` remains visible
in redacted probes and recovery evidence, but it is not sufficient to activate
Nunchi. A missing, unreadable, malformed, old, or future umbrella major fails
before configuration is loaded or any hook or command is registered.

This interface exists in the separate Hermes implementation candidate and must
land in a Hermes release before ordinary users can activate this integration.
Ordinary users cannot activate it until then. This repository does not claim an
upstream merge, release, or acceptance.

When that release is available, update Hermes and install the reviewed Nunchi
wheel into the same Python environment:

```bash
hermes update
# or
python -m pip install --upgrade hermes-agent
python -m pip install --upgrade /absolute/path/to/reviewed-nunchi.whl
```

Hermes discovers the `nunchi-v2` entry point through ordinary package metadata.
If the umbrella capability check fails, registration reports `Nunchi was not
activated`, tells the operator to run `hermes update` or upgrade
`hermes-agent`, and asks them to retry. No Nunchi hook or command is registered
in that state, so unrelated stock Hermes behavior remains active.

## Install and activate

Generate one closed profile-bound config:

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

Verify the generated config and participant-profile files are private `0600`
regular files. Compare their SHA-256 digests with the generator output, inspect
the exact profile, participant, actor, room/topic, state root, and enabled
capabilities, then export the printed profile-scoped environment keys in the
Hermes runtime environment.

Run the capability preflight before enabling the plugin:

```bash
nunchi-hermes-v2-doctor
hermes plugins enable nunchi-v2
```

Restart Hermes only through the operator's normal service controls. The doctor
does not restart a gateway. After that restart, require the activation health
check to pass:

```bash
nunchi-hermes-v2-doctor --check-activation
```

That flag runs `hermes plugins list --json` and requires the `nunchi-v2` row to
be both configured as `enabled` and runtime `active`, with no registration
error. Then run `/nunchi-v2 probe`.

Adapter-local profile names map to the shared platform-neutral opaque identity
`installation_id="hermes:<profile>"`.

The probe must report `participant_host_api_version: 2`,
`supported_participant_host_api_major: 2`,
`gateway_message_hook_api_version: 2`,
`supported_gateway_message_hook_api_major: 2`, `generation: 2`,
`v1_fallback: false`, and `operational: true` before opening ordinary
unmentioned room traffic.

## Commissioning boundary

The current source implementation is not merged, released, installed-runtime
verified, or commissioned. No repository checkout or editable install counts
as clean artifact evidence. Before claiming a deployed room works, one exact
Nunchi wheel, a released Hermes package exposing participant-host API major 2,
and the exact configuration must pass clean-install entry-point discovery,
deterministic lifecycle and receipt tests, independent review, and separately
authorized native Discord/Telegram canaries.

## Rollback

First restore mention/command-only admission for every bound room. Disable
Nunchi, restart Hermes through the operator's normal controls if needed, and
restore the prior reviewed Nunchi wheel:

```bash
hermes plugins disable nunchi-v2
python -m pip install --force-reinstall /absolute/path/to/prior-nunchi.whl
```

Retain Nunchi state for audit. There is no Hermes source restoration step.
Hermes itself continues normally when Nunchi registration fails because the
failed registration claims no hooks or commands.

See [`docs/integrations/hermes-v2.md`](../../docs/integrations/hermes-v2.md)
for the interface, failure, lifecycle, and rollback boundaries.
