# Transport patches for the Claude Code Discord plugin

Two operator-applied patches for the **official Claude Code Discord plugin**
(`claude-plugins-official`, plugin `discord`, version **0.0.4**, file
`server.ts`). They are transport-layer fact plumbing only: no social logic, no
filtering beyond the plugin's own `gate()`/`allowFrom` authorization.

| Patch | What it does |
|---|---|
| `0001-allow-bot-messages-allowfrom.patch` | Replaces the unconditional bot-drop in `messageCreate` with a self-only echo guard, so **allowlisted peer bots** flow into the plugin's own access control like any other sender (upstream issues anthropics/claude-plugins-official#1153/#1559; community reference `chenjr0719` branch `fix/allow-bot-messages`, commit `e0474df`). |
| `0002-native-fact-sidecar.patch` | Appends one JSON line per **delivered** message to `STATE_DIR/nunchi-native-events.jsonl` with the exact native facts the rendered channel tag omits: author ID, bot flag, mention IDs, `mention_everyone`, guild ID, and the reply-to message ID. Facts the transport does not synchronously hold (the referenced message's author/content) stay absent. Size-capped with one rotation generation (`.1`). |

Without `0001` a peer agent can never be heard; without `0002` the hook has no
exact author identity to bind (the channel tag carries only a display name)
and every room event is honestly unroutable. Apply both, in order.

## Exact provenance

- **Base**: `server.ts` from installed plugin `discord@claude-plugins-official`
  version `0.0.4`, SHA-256
  `c3c79c6519e23470fcc5f07e38415e50b4f054e42e670e89bd037fa64659e135`.
- **Result** after `0001` + `0002`, SHA-256
  `e26b6d2316413f2fb886a54346364e44c1c29dbffc6136dbfeb357b69198f115`.

Both digests are pinned inside `apply-transport-patch.sh`; the patches
themselves were generated with `git format-patch` against that exact base.

## Applying — fail closed

```sh
./apply-transport-patch.sh <plugin-dir>            # apply both patches
./apply-transport-patch.sh <plugin-dir> --verify   # report state, change nothing
./apply-transport-patch.sh <plugin-dir> --rollback # restore the pristine base
```

`<plugin-dir>` is the installed plugin root, e.g.
`~/.claude/plugins/cache/claude-plugins-official/discord/0.0.4`.

The script refuses to touch a `server.ts` that is neither the exact pinned
base nor the exact expected result (exit 2). If the plugin has been upgraded
and the upstream file changed, that refusal is the intended outcome: an
unreviewed upstream is never patched by fuzzy matching. Re-review the new
upstream, regenerate both patches against it, and update the pinned digests —
then apply. The pristine base is preserved at `server.ts.orig-0.0.4` for
rollback.

After applying or rolling back, restart the Claude Code session so the plugin
process reloads.

## What this deliberately does not do

- It does not bypass `gate()`: a peer bot must still satisfy `dmPolicy` /
  `allowFrom` (DMs) or the per-channel group policy before delivery, exactly
  like a human sender.
- It does not deliver reactions, membership events, or messages that arrive
  while no Claude session is running (cold wake) — those remain honest
  transport limitations, recorded in the integration's evidence.
- It does not fetch the replied-to message: only the reference ID that the
  gateway payload already carries is recorded.
