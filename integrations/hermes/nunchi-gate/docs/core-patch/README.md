# Core Patch: channel-scoped gateway display overrides

This directory contains the optional Hermes core patch required for nunchi-room to quiet gateway/tool chatter only in the nunchi lane.

The patch is carried by the `nunchi-gate` plugin because the behavior exists to support nunchi-room channel hygiene. Do not put this patch in unrelated plugin lanes.

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

From the Hermes source checkout:

```bash
cd "$HERMES_HOME/hermes-agent"
git apply --check "$HERMES_HOME/plugins/nunchi-gate/docs/core-patch/0001-channel-scoped-display-overrides.patch"
git apply "$HERMES_HOME/plugins/nunchi-gate/docs/core-patch/0001-channel-scoped-display-overrides.patch"
scripts/run_tests.sh tests/gateway/test_display_config.py
```

After applying code changes, ask Zoe to `/restart` the affected gateway. Do **not** `launchctl kickstart` from inside the running gateway session.

## Test plan

See `test-plan.md`.
