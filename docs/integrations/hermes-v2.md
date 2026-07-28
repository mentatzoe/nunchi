# Hermes V2 capability integration

## Status

The Nunchi plugin implementation consumes Hermes gateway participant-hook API
major 2. That public interface is implemented in a separate Hermes candidate
but must land in a Hermes release before ordinary users can activate Nunchi V2.
No upstream merge, release, acceptance, installed-runtime verification, live
commissioning, or Nunchi integration is claimed here.

## Capability contract

Hermes passes a `PluginContext` to the ordinary `hermes_agent.plugins` entry
point. Nunchi reads `ctx.gateway_message_hook_api_version` before loading
configuration or registering hooks.

- Major `2` is supported.
- A missing value, non-integer value, older major, or future incompatible major
  rejects activation.
- A compatible host receives registrations for `gateway_message`,
  `gateway_session_cancel`, and `gateway_shutdown`.
- Nunchi does not inspect Hermes source identity, require an exact Hermes
  package version, write Hermes files, or install a wrapper process.

Hermes guarantees that `gateway_message` runs after native admission,
authorization, route resolution, and control-command interception. The callback
receives immutable message and route snapshots plus a one-shot route-bound
delivery facade. Session cancellation invalidates matching active and pending
Nunchi work. Shutdown revokes delivery authority before Nunchi fences all
runtimes.

Backward-compatible additions remain API major 2. A future incompatible
contract uses another major and stays inactive until Nunchi explicitly supports
it.

## Incompatible host behavior

Registration raises before any hook or command is registered. The diagnostic
states that Nunchi V2 was not activated, names
`PluginContext.gateway_message_hook_api_version` and its missing or observed
value, and tells the operator to run `hermes update` or upgrade
`hermes-agent`, then retry.

Do not work around this failure by enabling a broad message claimant. Older
Hermes installations retain their unrelated stock behavior while Nunchi
remains inactive.

## Installation and verification

Once Hermes publishes API major 2:

1. Run `hermes update`, or upgrade `hermes-agent` in the Hermes environment.
2. Install the reviewed Nunchi wheel into that same environment.
3. Enable the `nunchi-v2` plugin entry point.
4. Generate and install the private profile-bound configuration described in
   `integrations/hermes/README.md`.
5. Restart Hermes and run `/nunchi-v2 probe`.

The probe reports the observed and supported hook API major, Nunchi artifact
identity, contract versions, and aggregate configuration identity. It does not
expose route bindings, profile names, state paths, or capability names.

Package provenance still matters for evidence: record the installed Hermes and
Nunchi package versions and artifacts used by each run. Those identities
describe the tested subject; they do not replace runtime capability
negotiation or become a compatibility pin.

## Rollback

Restore mention/command-only admission for each bound room before disabling the
plugin. Stop Hermes, disable `nunchi-v2`, and retain the Nunchi state directory
for audit. Nunchi never changes Hermes package files, so rollback has no Hermes
source restoration step.
