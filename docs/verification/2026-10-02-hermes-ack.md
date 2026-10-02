# Hermes attention ACK — 2 October 2026

Implemented and locally verified on the frozen native-tool source. This is not
a complete V2 release, a live adoption, or a fix for the separate native-tool
journal timeout.

A model ACK is no longer always widened to DEFER. After stock ingress
authorisation, Nunchi reads current permission facts for the exact adapter
bot, room, and trigger. Discord uses the shipped `_add_reaction` method and
discord.py channel permissions for the authenticated client bot. Telegram uses
the shipped `_set_reaction` method and authenticated `available_reactions`
facts. An omitted Telegram list means the installed standard reaction set, not
the default ACK emoji. Missing or failed facts stay unavailable. AttentionEngine
widens that ACK to DEFER. Message text and display names are not capability
facts.

When the facts allow the configured reaction, Nunchi reserves the shared ACK
journal, rechecks the permission revision, cancellation, and the one total
deadline, then adds exactly one reaction. The native wait does not hold the
scheduler lock or the room runtime lock. A lost or late result is unknown and
is not retried. The permit authorises that one method, adapter, target, and
emoji. It does not let other configured-route effects through.

The participant and main model are not invoked for an authorised ACK.

## Source

Base `9734564c102c693eb1b0f3fd87bb8661b3346104`. Its product bytes match
`b83352e`; the only parent delta is the reviewed deadline-fixture
reconstruction. Native tool, approval, loader, and lifecycle code was not
changed. Host Hermes source was not edited.

## Executed checks

- `python3 -m unittest tests.v2.test_hermes_ack tests.v2.test_hermes_portable`:
  101 tests, OK.
- Canonical `python3 -m unittest`: 671 tests, OK, 8 expected skips. The extra
  skip is the new installed-host ACK class, which runs only when
  `NUNCHI_REQUIRE_HERMES_NORMAL_TURN=1`.
- Wheel `nunchi-2.0.0-py3-none-any.whl`, SHA256
  `3e5617fac64ea8e71e89be8dd9b98c5751c6dc8cb57073be8745e8202a0cd069`.
- Minimum host 0.19.0, Python 3.11, non-editable wheel, `python -I`, loopback
  model double and fake Discord client, no live credentials. All six
  `NunchiAttentionAck` probes passed: one native 👂, no participant; replay
  after plugin restart did not repeat it; denied permission widened to DEFER
  and woke the participant with no reaction; a permission change after the
  decision produced `unavailable` and no participant; cancellation and a late
  native result were not recorded sent; rollback removed the ingress shim and
  a following stock turn added no Nunchi reaction.
- The same minimum run also passed the existing stock baseline and the
  configured-route turns that were already green. The two known minimum
  baselines remain: default attention trust refusal, and the stock session
  guard leak. They are outside this card.
- Current host 0.21.5, Python 3.13: stock baseline 6/6 passed. Every Nunchi
  probe, including ACK, stopped at `register()` with `load timed out after
  10s`. That is the separate loader deadlock. This card did not change
  loader or lifecycle code. A direct call through the installed wheel to the
  current shipped `DiscordAdapter._add_reaction` did add 👂 and returned
  `sent`. Current `TelegramAdapter._set_reaction` still has the
  `(chat_id, message_id, emoji)` signature this path calls. That is not a
  plugin-load pass.

No GitHub write, live profile write, or gateway restart was performed.
