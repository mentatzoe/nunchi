# Test Plan: channel-scoped display overrides

Run from `$HERMES_HOME/hermes-agent` after applying
`integrations/hermes/core-patches/0001-channel-scoped-display-overrides.patch`
from the Nunchi source checkout.

## Unit test

```bash
scripts/run_tests.sh tests/gateway/test_display_config.py
```

Expected: the resolver suite passes, including `test_channel_override_wins_only_for_matching_channel`.

## Direct resolver smoke

Use a temp config dict to verify channel override precedence:

```bash
python - <<'PY'
from gateway.display_config import resolve_display_setting
cfg = {
    "display": {
        "tool_progress": "all",
        "platforms": {"discord": {"tool_progress": "new"}},
        "channel_overrides": {
            "discord": {
                "1522258711047831653": {"tool_progress": False},
            }
        },
    }
}
print(resolve_display_setting(cfg, "discord", "tool_progress", channel_id="1522258711047831653"))
print(resolve_display_setting(cfg, "discord", "tool_progress", channel_id="other"))
PY
```

Expected:

```text
off
new
```

## Gateway behavior smoke

1. Configure `display.channel_overrides.discord.1522258711047831653` for the nunchi-room quiet settings.
2. Ask Zoe to `/restart` the affected gateway; do not restart it from inside the agent.
3. In `#nunchi-room`, send a tiny message that would normally trigger a tool/progress path and verify tool/status chatter is suppressed.
4. In a non-nunchi Discord lane, trigger the same kind of path and verify normal tool progress remains visible.

If the non-nunchi lane is also quiet, check for temporary platform-wide containment values under `display.platforms.discord.*` and remove them only after confirming the live gateway process started after the patch was applied.
