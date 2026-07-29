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
plugin, then restart Hermes:

```sh
python -m pip install nunchi
hermes plugins enable nunchi-v2
```

The wheel exposes the `nunchi-v2` entry point in the
`hermes_agent.plugins` group. No plugin files need to be copied into a Hermes
checkout.

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
        "path": "/absolute/private/path/participant-profile.json",
        "sha256": "<64 lowercase hex>"
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

The config and participant profile must be owned by the Hermes user and mode
`0600`. Set `suppression_recovery_verified` to `true` only after an
attributable live restart and later-message recovery run has passed. Until
then, leave it `false`; Nunchi widens attempted suppression to `DEFER`.

Set:

```sh
NUNCHI_HERMES_V2_CONFIG=/absolute/private/path/hermes-v2.json
NUNCHI_HERMES_V2_CONFIG_SHA256=<64 lowercase hex>
```

For a named Hermes profile, use
`NUNCHI_HERMES_V2_CONFIG_<PROFILE>` and
`NUNCHI_HERMES_V2_CONFIG_SHA256_<PROFILE>`, with non-alphanumeric characters
replaced by `_`.

Hermes continues to control its existing platform credentials, allowlists,
pairing, mention rules, and `DISCORD_ALLOW_BOTS` policy.

## Verify

In an authorized chat, run:

```text
/nunchi-v2 probe
```

The probe reports the installed Nunchi and Hermes versions, selected
compatibility mode, pinned configuration digest, and configured bindings. It
also states that Hermes files were not modified.

Source tests and a successful probe do not prove live platform behavior. Live
acceptance still requires attributable suppress, wake, defer, silence,
delivery, cancellation, restart, and later-message recovery runs on each
enabled platform.
