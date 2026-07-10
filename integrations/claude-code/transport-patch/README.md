# Transport patch: let allowlisted peer bots reach the session

This directory carries the operator-applied patch for the **official Claude
Code Discord plugin** (`anthropics/claude-plugins-official`,
`external_plugins/discord/server.ts`). Without it, the plugin drops every
bot-authored message before its own access control runs, so a peer agent can
never be heard — and the nunchi inbound gate never gets anything to gate.

The patch is carried here because peer hearing exists to feed the nunchi
Claude Code gate (`../nunchi_prompt_gate.py`). Apply it together with the
gate, not instead of it.

## Patch file

- `0001-allow-bot-messages-allowfrom.patch`

**Verified against upstream HEAD as of 2026-07-09** — built from and
`git apply --check`-verified against `server.ts` blob `0595fc7` (the patch's
`index 0595fc7..6cfda9b` line pins that exact base; upstream `main` last
pushed 2026-07-08). If upstream has moved since, see
[If the patch no longer applies](#if-the-patch-no-longer-applies).

## The bug it fixes

The plugin's `messageCreate` handler discards bot authors unconditionally,
*before* `gate()` — the plugin's own access-control function — ever runs:

```ts
client.on('messageCreate', msg => {
  if (msg.author.bot) return
  handleInbound(msg).catch(e => process.stderr.write(`discord: handleInbound failed: ${e}\n`))
})
```

Consequence: even a peer bot whose user ID the operator has **explicitly
allowlisted** is silently dropped. Multi-agent rooms where several Claude Code
instances coordinate over Discord cannot work at all.

Upstream reports (both open as of 2026-07-09):

- [anthropics/claude-plugins-official#1153](https://github.com/anthropics/claude-plugins-official/issues/1153) — allow bot-to-bot communication (configurable)
- [anthropics/claude-plugins-official#1559](https://github.com/anthropics/claude-plugins-official/issues/1559) — messages from allowlisted bots are silently dropped

Community reference: the [chenjr0719 fork](https://github.com/chenjr0719/claude-plugins-official),
branch `fix/allow-bot-messages` (commit `e0474df`). This patch is the same
minimal delta, rebased onto current upstream HEAD.

## What it changes

One guard. The unconditional bot-drop becomes a self-only drop (plus an
explanatory comment):

```ts
client.on('messageCreate', msg => {
  // Drop only our own messages (echo-loop guard). Peer bots are NOT dropped
  // here: gate()/allowFrom in access.json remains the authorization layer,
  // and a bot sender must be allowlisted exactly like a human before its
  // messages are delivered. Upstream: anthropics/claude-plugins-official
  // issues #1153 and #1559.
  if (msg.author.id === client.user?.id) return
  handleInbound(msg).catch(e => process.stderr.write(`discord: handleInbound failed: ${e}\n`))
})
```

The self-drop preserves the original purpose of the line (the bot never
processes its own messages, so it cannot echo-loop on itself). Everything
else — including which bots are heard — is decided by the plugin's existing
access control, described next.

## Why this is safe: allowFrom / access.json is the second layer

The patch does **not** open the transport to all bots. Every message that
survives the self-drop still goes through the plugin's `gate()` function,
which reads `~/.claude/channels/discord/access.json` (managed by the
`/discord:access` skill) on every inbound message. After the patch, bot
senders are authorized exactly like humans:

- **DMs** — the sender's user ID (snowflake) must be in `allowFrom`.
  Unknown senders hit the pairing flow (`dmPolicy: pairing`) or are dropped
  (`allowlist` / `disabled`). Bots won't usefully complete interactive
  pairing — add a peer bot's snowflake directly:
  `/discord:access allow <peer-bot-user-id>`.
- **Guild channels** — the channel must be opted in
  (`/discord:access group add <channel-id>`). If the group's `allowFrom` list
  is non-empty, the sender must be in it. With `requireMention: true` (the
  default), the sender must also @mention the bot, reply to one of its
  messages, or match a `mentionPatterns` regex.

So the composed policy for hearing a peer bot in a channel is:

```
/discord:access group add <channel-id> --allow <your-user-id>,<peer-bot-user-id>
```

Two honest caveats:

1. **Empty group `allowFrom` means "anyone who mentions".** In an opted-in
   channel whose group policy has no `allowFrom` list, any sender that
   satisfies the mention requirement is delivered — after this patch, that
   includes any bot and any webhook (webhook authors also have
   `author.bot === true`). In rooms where peer bots operate, set an explicit
   `--allow` list rather than relying on mention gating alone.
2. **The echo-loop guard only covers self.** Two patched bots that reply to
   each other can still loop at the conversation layer. That failure mode is
   precisely what the nunchi gate exists to stop — the `UserPromptSubmit`
   gate PASSes low-value peer chatter before the LLM ever runs (and DEFERs to
   the agent's own judgment when unsure). Run the patch and the gate
   together.

## How to apply

1. **Locate your plugin copy.** Claude Code keeps installed marketplace
   plugins under `~/.claude/plugins/`:

   ```sh
   find ~/.claude/plugins -path '*discord*' -name server.ts
   ```

   Alternatively, work from a fresh checkout of
   `anthropics/claude-plugins-official` and point your plugin install at it.

2. **Dry-run, then apply.** From the root of a `claude-plugins-official`
   git checkout:

   ```sh
   git apply --check /path/to/nunchi/integrations/claude-code/transport-patch/0001-allow-bot-messages-allowfrom.patch
   git apply         /path/to/nunchi/integrations/claude-code/transport-patch/0001-allow-bot-messages-allowfrom.patch
   ```

   Against an installed plugin directory that is not a git checkout (the
   directory containing `server.ts`):

   ```sh
   cd "$(dirname "$(find ~/.claude/plugins -path '*discord*' -name server.ts | head -1)")"
   patch -p3 --dry-run < /path/to/0001-allow-bot-messages-allowfrom.patch
   patch -p3           < /path/to/0001-allow-bot-messages-allowfrom.patch
   ```

   (`-p3` strips `a/external_plugins/discord/` from the patch paths.)

3. **Restart the plugin.** The plugin runs as an MCP server via Bun
   (`.mcp.json` launches `bun run --cwd ${CLAUDE_PLUGIN_ROOT} start`). The
   patched `server.ts` is only loaded on process start — restart the Claude
   Code session (or reconnect its MCP servers) after applying.

Note: reinstalling or updating the plugin will overwrite the patched file;
re-apply after updates until the upstream fix lands.

## If the patch no longer applies

Upstream has moved past blob `0595fc7`. The delta is a single guard: find
`if (msg.author.bot) return` in the `client.on('messageCreate', ...)` handler
of `external_plugins/discord/server.ts` and replace it with
`if (msg.author.id === client.user?.id) return`. Confirm that `gate()` (the
`access.json` check) is still called on every inbound message in
`handleInbound` before relying on it as the authorization layer, then update
this directory's patch from your rebased edit.

## Live verification recipe

Goal: prove a peer-bot message reaches the Claude Code session, and that a
non-allowlisted bot still does not.

1. **Collect snowflakes.** Enable Discord Developer Mode, right-click the
   peer bot → **Copy User ID**; right-click the test channel →
   **Copy Channel ID**.
2. **Authorize the peer bot** in the test channel:

   ```
   /discord:access group add <channel-id> --allow <your-user-id>,<peer-bot-user-id>
   ```

   `access.json` is re-read per message — no restart needed for this step.
3. **(Optional) Unpatched control.** Before applying the patch, have the peer
   bot post `@your-bot ping` in the channel. Expected: nothing reaches the
   session. That silence is the bug.
4. **Apply the patch and restart** the session (steps above).
5. **Peer-bot message.** Have the peer bot post `@your-bot ping` again
   (`requireMention` defaults to true, so the mention matters). Expected:
   the session receives a `<channel source="discord" ...>` prompt whose
   `user`/`user_id` are the peer bot's. With `../nunchi_prompt_gate.py`
   installed, a receipt line lands in `~/.claude/nunchi-gate-receipts.jsonl`
   with `"direction": "inbound"` and `trigger_author` set to the peer bot's
   username — proof the transport delivered and the nunchi gate ruled.
6. **Negative check.** Have a bot **not** on the group `allowFrom` list post
   `@your-bot ping` in the same channel. Expected: no prompt in the session
   and no receipt — `gate()` dropped it at the transport.

## Status

- Nunchi Claude Code gate (`UserPromptSubmit`, one judgment at wake): merged in this repo.
- This transport patch: **local operator step** — apply it to your own plugin
  checkout; it ships here only as a `.patch` + instructions.
- Upstream fix: **pending** (#1153, #1559 open as of 2026-07-09). When
  upstream merges bot hearing in any form, prefer the upstream mechanism and
  retire this patch.
