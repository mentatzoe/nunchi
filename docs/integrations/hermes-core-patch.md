# Core Patch: channel-scoped gateway display overrides

This guide covers the optional Hermes core patch used to quiet gateway/tool
chatter only in the Nunchi lane.

The deployment asset lives at
`integrations/hermes/core-patches/0001-channel-scoped-display-overrides.patch`.
It is carried by the Nunchi repository because the behavior exists to support
Nunchi room hygiene. It is not runtime plugin code and is not copied into an
installed `nunchi-gate` plugin.

## Patch file

- `0001-channel-scoped-display-overrides.patch`

## What it does

Adds support for:

```yaml
display:
  channel_overrides:
    discord:
      "<channel-id>":
        tool_progress: off
        interim_assistant_messages: false
        long_running_notifications: false
        busy_ack_detail: false
        show_reasoning: false
        thinking_progress: false
        streaming: false
```

Resolution order becomes:

1. `display.channel_overrides.<platform>.<channel_id>.<setting>`
2. `display.platforms.<platform>.<setting>`
3. `display.<setting>`
4. built-in platform defaults
5. built-in global defaults

The gateway threads `source.chat_id` into display resolution so one Discord channel can be quiet while other Discord lanes keep normal progress visibility.

## How to apply

From a Nunchi source checkout, with the Hermes source at
`$HERMES_HOME/hermes-agent`:

```bash
PATCH="$PWD/integrations/hermes/core-patches/0001-channel-scoped-display-overrides.patch"
git -C "$HERMES_HOME/hermes-agent" apply --check "$PATCH"
git -C "$HERMES_HOME/hermes-agent" apply "$PATCH"
(cd "$HERMES_HOME/hermes-agent" && scripts/run_tests.sh tests/gateway/test_display_config.py)
```

After applying code changes, ask Zoe to `/restart` the affected gateway. Do **not** `launchctl kickstart` from inside the running gateway session.

## Test plan

See the [core-patch test plan](hermes-core-patch-test-plan.md).
