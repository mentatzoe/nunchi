# Transport patches for the Claude Code Discord plugin

Two operator-applied patches for the **official Claude Code Discord plugin**
(`claude-plugins-official`, plugin `discord`, version **0.0.4**, file
`server.ts`). They are transport-layer fact plumbing only: no social logic, no
filtering beyond the plugin's own `gate()`/`allowFrom` authorization.

| Patch | What it does |
|---|---|
| `0001-allow-bot-messages-allowfrom.patch` | Replaces the unconditional bot-drop in `messageCreate` with a self-only echo guard, so **allowlisted peer bots** flow into the plugin's own access control like any other sender (upstream issues anthropics/claude-plugins-official#1153/#1559; community reference `chenjr0719` branch `fix/allow-bot-messages`, commit `e0474df`). |
| `0002-native-fact-sidecar.patch` | Appends one JSON line per message to an **owner-only** sidecar at `STATE_DIR/nunchi-v2/native-events.jsonl` with the exact native facts the rendered channel tag omits: author ID, bot flag, mention IDs, `mention_everyone`, guild ID, the reply-to message ID, and the **exact content delivered to Claude** (attachment placeholders and voice transcripts included, not raw `msg.content`). Facts the transport does not synchronously hold (the referenced message's author/content) stay absent. **Self-authored** messages are recorded here as retained context *before* the waking-path drop, so a V2 consumer keeps them as `SELF_RETAINED_NO_WAKE` without a recursive wake. |

Without `0001` a peer agent can never be heard; without `0002` the hook has no
exact author identity to bind (the channel tag carries only a display name)
and every room event is honestly unroutable. Apply both, in order.

### Sidecar confidentiality (patch `0002`)

The sidecar carries verbatim room content, so the transport writes it into an
owner-only `0700` subdirectory, creates the file `0600`, opens it with
`O_NOFOLLOW`, and validates on every write that the descriptor is an
owner-owned regular file with no group/other bits. An unsafe target (symlink,
shared, or non-regular) is refused fail-closed rather than written, and an
unserializable record is dropped rather than partially written. The consumer
reads the sidecar the same way (no-follow, owner-only) and treats a malformed
matching record as unroutable, never binding a partial actor.

If a prior install left a world-readable `native-events.jsonl` behind, delete
it before arming V2 — the hardened writer refuses to append to a file whose
mode is not owner-only.

## Exact provenance

- **Base**: `server.ts` from installed plugin `discord@claude-plugins-official`
  version `0.0.4`, SHA-256
  `c3c79c6519e23470fcc5f07e38415e50b4f054e42e670e89bd037fa64659e135`.
- **Result** after `0001` + `0002`, SHA-256
  `67900f7e0275debcfd9deabb0345c92e879b25047ce00777e3fbd9552b19bd8a`.

Both digests are pinned inside `apply-transport-patch.sh`; the patches
themselves were generated with `git format-patch` against that exact base and
the patched result transpiles cleanly under `bun build`.

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
