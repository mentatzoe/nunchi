# Transport patches for the Claude Code Discord plugin

Three operator-applied patches for the **official Claude Code Discord plugin**
(`claude-plugins-official`, plugin `discord`, version **0.0.4**, file
`server.ts`). They are transport-layer fact plumbing and bound-room safety
only: no social logic, no filtering beyond the plugin's own
`gate()`/`allowFrom` authorization.

| Patch | What it does |
|---|---|
| `0001-allow-bot-messages-allowfrom.patch` | Replaces the unconditional bot-drop in `messageCreate` with a self-only echo guard, so **allowlisted peer bots** flow into the plugin's own access control like any other sender (upstream issues anthropics/claude-plugins-official#1153/#1559; community reference `chenjr0719` branch `fix/allow-bot-messages`, commit `e0474df`). |
| `0002-native-fact-sidecar.patch` | Appends one JSON line per message to an **owner-only** sidecar at `STATE_DIR/nunchi-v2/native-events.jsonl` with the exact native facts the rendered channel tag omits: author ID, bot flag, mention IDs, `mention_everyone`, guild ID, the reply-to message ID, and the **exact content delivered to Claude** (attachment placeholders and voice transcripts included, not raw `msg.content`). Facts the transport does not synchronously hold (the referenced message's author/content) stay absent. **Self-authored** messages are recorded here as retained context *before* the waking-path drop, so a V2 consumer keeps them as `SELF_RETAINED_NO_WAKE` without a recursive wake. |
| `0003-nunchi-bound-room-safety.patch` | Reads an optional `NUNCHI_CLAUDE_V2_CHANNEL_ID` (null unless the operator sets it in this plugin's own `.env`). For the exact bound room only, skips the plugin's "yes/no `<code>`" room-text permission-reply intercept (ordinary room text must never satisfy a privileged approval outside Nunchi's own `I-040B` contract) and the pre-attention typing indicator + configured ack reaction (so an effective `SUPPRESS` produces zero room-visible bot activity). Every other room is byte-for-byte unaffected. |

Without `0001` a peer agent can never be heard; without `0002` the hook has no
exact author identity to bind (the channel tag carries only a display name)
and every room event is honestly unroutable; without `0003` the bound room
gets the unpatched plugin's pre-attention Discord activity and room-text
permission bypass. Apply all three, in order.

### Sidecar confidentiality (patch `0002`)

The sidecar carries verbatim room content, so both writer and reader keep it
owner-only:

- **Directory** — mode `0700`, caller-owned, non-symlink. Before every write
  the transport validates the containing directory with a no-follow `lstat`
  and refuses fail-closed if it is a symlink, not a directory, not
  caller-owned, or has any group/other bits. A pre-existing unsafe directory
  (`0755`, `0777`, symlinked, or non-directory) is **rejected, never silently
  reused or re-moded**.
- **File** — mode `0600`, created with that mode, opened `O_NOFOLLOW`, and
  validated on every write as an owner-owned regular file with no group/other
  bits. An unserializable record is dropped rather than partially written.

The consumer reads the sidecar the same way — it validates the parent
directory (owner-only, non-symlink) and opens the file no-follow/owner-only —
and treats a malformed or unsafe matching record as unroutable, never binding
a partial actor.

If a prior install left a sidecar at the **old** path
`~/.claude/channels/discord/nunchi-native-events.jsonl`, it is not reused (the
hardened path is `~/.claude/channels/discord/nunchi-v2/native-events.jsonl`).
Review and move the old file aside explicitly if you want it gone; the
installer never deletes it for you.

## Exact provenance

- **Base**: `server.ts` from installed plugin `discord@claude-plugins-official`
  version `0.0.4`, SHA-256
  `c3c79c6519e23470fcc5f07e38415e50b4f054e42e670e89bd037fa64659e135`.
- **Result** after `0001` + `0002` + `0003`, SHA-256
  `46420d46dcff14bf486a7291e6790e91c4bb09a887c1fe29ada9f3e5f9106775`.

Both digests are pinned inside `apply-transport-patch.sh`; the patches
themselves were generated with `git format-patch` against that exact base and
the patched result transpiles cleanly under `bun build`.

## Applying — fail closed

```sh
./apply-transport-patch.sh <plugin-dir>            # apply all three patches
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

The installer is itself fail-closed against filesystem substitution: it
rejects a symlinked target or backup (never following it to modify a referent
elsewhere), requires the target and backup to be caller-owned regular files,
verifies both resolve to a path inside the supplied plugin directory, and
replaces the file atomically (sibling temp file, then rename).

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
- It does not touch the plugin's DM/button native permission-approval path
  (`interactionCreate`, answering Claude Code's own interactive
  tool-permission prompts): that surface is reached only via direct message,
  keyed by a short code with no room/turn provenance, and is not room-scoped
  by construction — patching it would require threading Nunchi turn context
  through the plugin's own permission-request notification payload, which
  this transport-layer patch does not attempt. Reported, not claimed safe.
