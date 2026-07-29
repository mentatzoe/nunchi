# Hermes V2 capability integration

## Status

The Nunchi plugin implementation consumes Hermes participant-host API major 2.
That public interface is implemented in a separate Hermes candidate but must
land in a Hermes release before ordinary users can activate Nunchi V2. No
upstream merge, release, acceptance, installed-runtime verification, live
commissioning, or Nunchi integration is claimed here.

## Capability contract

Hermes passes a `PluginContext` to the ordinary `hermes_agent.plugins` entry
point. Nunchi reads `ctx.participant_host_api_version` before loading
configuration or registering anything.

- Major `2` is supported.
- A missing, unreadable, malformed, older, or future incompatible umbrella
  major rejects activation.
- A compatible host receives registrations for `gateway_message`,
  `gateway_session_cancel`, and `gateway_shutdown`.
- Nunchi does not inspect Hermes source identity, require an exact Hermes
  package version, write Hermes files, or install a wrapper process.

The umbrella major covers every host surface Nunchi consumes: lifecycle hooks,
routed profiles and sessions, native delivery receipts, structured LLM calls,
tool dispatch, command registration, and plugin loading/failure state.
`ctx.gateway_message_hook_api_version` is retained as narrower redacted
provenance, but it is not an activation authority.

Backward-compatible additions remain API major 2. A future incompatible
contract uses another major and stays inactive until Nunchi explicitly supports
it.

## Incompatible host behavior

Registration raises before any hook or command is registered. The diagnostic
states that Nunchi was not activated, names
`PluginContext.participant_host_api_version`, and tells the operator to run
`hermes update` or upgrade `hermes-agent`, then retry.

Do not work around this failure by enabling a broad message claimant. Older
Hermes installations retain their unrelated stock behavior while Nunchi
remains inactive.

## Installation and verification

Once Hermes publishes participant-host API major 2:

1. Run `hermes update`, or upgrade `hermes-agent` in the Hermes environment.
2. Install the reviewed Nunchi wheel into that same environment.
3. Generate, inspect, digest-check, and install the private profile-bound
   configuration described in `integrations/hermes/README.md`.
4. Run `nunchi-hermes-v2-doctor`; a nonzero exit blocks activation.
5. Run `hermes plugins enable nunchi-v2`.
6. Restart Hermes only through operator-controlled service management.
7. Run `nunchi-hermes-v2-doctor --check-activation`; it consumes
   `hermes plugins list --json` and requires `nunchi-v2` to be enabled and
   active without a registration error.
8. Run `/nunchi-v2 probe`.

The probe reports the observed and supported umbrella major, the narrower hook
major, Nunchi artifact identity, contract versions, and aggregate configuration
identity. It does not expose route bindings, profile names, state paths, or
capability names.

Package provenance still matters for evidence: record the installed Hermes and
Nunchi package versions and artifacts used by each run. Those identities
describe the tested subject; they do not replace runtime capability
negotiation or become a compatibility pin.

## Rollback

Restore mention/command-only admission for each bound room, run
`hermes plugins disable nunchi-v2`, and restore the prior reviewed Nunchi
package. Restart Hermes only through operator-controlled service management if
needed, and retain the Nunchi state directory for audit. Nunchi never changes
Hermes package files, so rollback has no Hermes source restoration step.
Hermes itself continues normally after a failed Nunchi registration because
that failure claims no hooks or commands.
