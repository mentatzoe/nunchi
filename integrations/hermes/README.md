# Hermes V2 integration

Nunchi installs as a normal Python package beside Hermes. It has no required
Hermes dependency and does not modify Hermes files.

The integration supports Hermes 0.19.0 and newer compatible builds:

- It uses Hermes's versioned participant hooks when they expose authenticated
  self identity before the attention decision.
- From Hermes 0.19.0 through the tested current upstream head, it installs a
  checked runtime monkeypatch around the stock gateway runner.
- The Telegram patch retains each native update that Hermes combines into one
  text batch. Nunchi then processes those updates in order.
- Discord and Telegram ingress, authorization, routing, formatting, and I/O
  remain owned by Hermes's installed adapters.
- Nunchi owns observation, attention, scheduling, the participant turn,
  cancellation, receipts, and the single delivery commit for configured rooms.
- Unknown host shapes fail activation with a repair message. They never fall
  through to a second Hermes participant turn.

The monkeypatch changes process behavior. It does not rewrite the Hermes
checkout, package, or installed files.

## Install

Install Nunchi into the same environment as Hermes, enable its discovered
runtime plugin, then restart Hermes:

```sh
python -m pip install nunchi
hermes plugins enable nunchi
```

The wheel exposes the `nunchi` entry point in the `hermes_agent.plugins`
group. When Hermes loads the plugin, Nunchi installs its three wheel-owned web
bridge files into Hermes's documented user-plugin directory because Hermes
does not scan wheel entry points for dashboard assets. It does not change the
Hermes checkout or installed package. `nunchi-hermes-dashboard verify` checks
the bridge; `nunchi-hermes-dashboard install` repairs it.

## Configure

Create a private JSON configuration and pin its SHA-256:

```json
{
  "schema_version": 2,
  "hermes_profile": "default",
  "state_directory": "/absolute/private/path/nunchi-hermes-state",
  "rooms": [
    {
      "binding": {
        "participant_id": "agent",
        "actor_id": "discord:actor:123456789",
        "platform": "discord",
        "room_id": "987654321",
        "continuity_scope_id": "discord-room-987654321",
        "names": ["Agent"],
        "room_kind": "group",
        "provenance": "operator:hermes-default"
      },
      "profile": {
        "document": {
          "profile_id": "agent-default",
          "participant_id": "agent",
          "actor_id": "discord:actor:123456789",
          "instructions": "Use the participant's role and respond concisely.",
          "provenance": "operator:hermes-default"
        }
      },
      "attention": {
        "policy": {
          "suppression_enabled": true,
          "suppression_recovery_verified": true
        }
      },
      "limits": {},
      "participant": {
        "timeout_seconds": 300,
        "max_expansions": 3
      }
    }
  ]
}
```

The config must be owned by the Hermes user and mode `0600`. An inline profile
is pinned by the outer config. A separate profile can instead use exact
`path`/`sha256` fields. Set `suppression_recovery_verified` to `true` only
after an attributable live restart and later-message recovery run has passed.
Until then, leave it `false`; Nunchi widens attempted suppression to `DEFER`.

For dashboard editing, put the digest in a private sidecar file:

```sh
NUNCHI_HERMES_V2_CONFIG=/absolute/private/path/hermes-v2.json
NUNCHI_HERMES_V2_CONFIG_SHA256_FILE=/absolute/private/path/hermes-v2.json.sha256
```

For a named Hermes profile, use
`NUNCHI_HERMES_V2_CONFIG_<PROFILE>` and
`NUNCHI_HERMES_V2_CONFIG_SHA256_FILE_<PROFILE>`, with non-alphanumeric
characters replaced by `_`. An adjacent `<config>.sha256` file is also found
automatically. Both files must be private regular files owned by the Hermes
user. A literal `NUNCHI_HERMES_V2_CONFIG_SHA256` remains supported but is
read-only in the dashboard because the dashboard cannot update an environment
variable safely.

## Dashboard

Open **Nunchi V2** in the Hermes dashboard to:

- configure Discord and Telegram rooms using Hermes's discovered channel list;
- edit exact participant identity, inline instructions, attention policy, and
  lifecycle limits;
- use advanced JSON for the complete closed V2 configuration;
- inspect the newest V2 receipts for each configured room;
- save a new pinned config and restart Hermes to activate it.

Hermes authenticates the tab and its API. Saving uses the displayed config
digest as an optimistic lock, validates the complete new config before commit,
and updates the digest and config with private atomic replacements. A stale or
invalid edit is rejected. The running gateway is unchanged until the operator
requests restart; Hermes then invokes Nunchi's normal drain and cancellation
path.

Hermes continues to control its existing platform credentials, allowlists,
pairing, mention rules, and `DISCORD_ALLOW_BOTS` policy.

## Verify

In an authorized chat, run:

```text
/nunchi probe
```

The probe reports the installed Nunchi and Hermes versions, selected
compatibility mode, pinned configuration digest, and configured bindings. It
also states that Hermes files were not modified.

Source tests and a successful probe do not prove live platform behavior. Live
acceptance still requires attributable suppress, wake, defer, silence,
delivery, cancellation, restart, and later-message recovery runs on each
enabled platform.
