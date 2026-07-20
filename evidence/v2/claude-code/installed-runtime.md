# CC-06 — Installed runtime provenance (Claude Code V2)

**Attempt 2**, recorded 2026-07-20 by the `v2-claude-owner` lane (Station,
standing Claude Code agent). Attempt 1's version of this record is preserved
in git history at candidate `6476b58`. Secrets are excluded by construction:
no credential exists in any file this record names.

## Host and harness

| Component | Exact value |
|---|---|
| Host OS | macOS 15.3.1 (Darwin 24.3.0, build 24D70) |
| Claude Code | `2.1.215` |
| Session model | `claude-fable-5` |
| Python (hook runtime) | `3.14.3` (Homebrew) |
| Bun (plugin runtime) | `1.3.11` |
| Nunchi package | `0.2.0` at Attempt-2 candidate `199012901278777750671f4fc0731b779e91c2b8` |

## Discord plugin (transport base)

| Fact | Exact value |
|---|---|
| Plugin | `discord@claude-plugins-official`, version `0.0.4` |
| Install path | `/Users/zmll/.claude/plugins/cache/claude-plugins-official/discord/0.0.4` |
| Pristine base `server.ts.orig-0.0.4` SHA-256 | `c3c79c6519e23470fcc5f07e38415e50b4f054e42e670e89bd037fa64659e135` (matches the packet's pinned patch base exactly) |
| Current installed `server.ts` SHA-256 | `b025d1c2aa7df54a03fb2b03d403276902959cc13f7327d559a96eb2a91f358b` |
| Current installed state | An earlier, functionally partial wording of patch `0001` (self-only bot guard) applied 2026-07-09; **neither the Attempt-2 `0001` nor `0002` (hardened native-fact sidecar) is applied** |
| Canonical patched target SHA-256 (Attempt 2) | `67900f7e0275debcfd9deabb0345c92e879b25047ce00777e3fbd9552b19bd8a` (base + `0001` + `0002`, reproduced from the pinned base in this packet's patch-build check; the patched file transpiles clean under `bun build`) |
| MCP registration | `.mcp.json`: `bun run --cwd ${CLAUDE_PLUGIN_ROOT} --shell=bun --silent start` (stdio) |
| Delivery mechanism | Discord gateway (WebSocket push) → `messageCreate` → `gate()` authorization → MCP notification `notifications/claude/channel` → host-rendered `<channel>` prompt. Reactive; no polling path exists. A legacy `discord-poller.sh` exists on disk but is registered nowhere (settings/launchd/cron all checked) and is not running. |

## Staged V2 integration components (installed this session)

| Path | SHA-256 | Notes |
|---|---|---|
| `/Users/zmll/.claude/hooks/nunchi_claude_v2.py` | `3fa2e76fc9d86cbaebb4b2804f94eb672f5b54abc625eb1cfb515ee99ec009bf` | Exact copy of the Attempt-2 `integrations/claude-code/nunchi_claude_v2.py` |
| `/Users/zmll/.claude/hooks/nunchi-claude-v2-hook.sh` | `e76ff4a9deb2dcf17c397ef7b225e1e41a22e3d3767827659fe7013a90a3cc83` | Exact copy of `integrations/claude-code/nunchi-claude-v2-hook.sh` |
| `/Users/zmll/.claude/nunchi-claude-v2.env` | `311c960415837551ef885833d69deec7edaf4a4f330b4c62524bb54d5c8f7ce6` | Room binding: channel `1522258711047831653`, self `1484970897893752902`, participant `station`; sidecar path now the owner-only `…/discord/nunchi-v2/native-events.jsonl`; no credential |
| `/Users/zmll/.claude/nunchi/claude-v2-policy.json` | `c4a74571b1d5d7f372c2558ab6f9ea05110bc2a70f10302873039b6a086c4973` | Trusted-bypass posture: `preattention_enabled=false`, `social_suppression_enabled=false`, `error_action=WAKE`, empty authorization grants, receipt sink `/Users/zmll/.claude/nunchi/claude-v2-receipts` (0700) |
| `/Users/zmll/.claude/nunchi/claude-v2-tools.json` | `d48ef9c965ea6f53dc3218e39a43c747fdb99a97b3246bb572da8ff891daaa15` | Room-action tool patterns + privileged map (`Bash`, `Write/Edit/NotebookEdit`). With deny-unsupported semantics, every privileged room-caused proposal is denied regardless of grants |
| `/Users/zmll/.claude/nunchi/runtime/` | manifest `f1c3b548751ca1ed452ed60f525bba3d7f158eb297a402fd54961565e66f72f9` | Copy-with-manifest deployment of `src/nunchi` (43 files, per-file SHA-256 in `DEPLOY-MANIFEST.json`, source commit `199012901278…`); no symlinks |

## Hook registration state — NOT yet armed

`~/.claude/settings.json` still registers the **V1** `UserPromptSubmit` hook
(`/Users/zmll/.claude/hooks/nunchi-user-prompt-submit.sh`). The V2
registration (four events, from `python3 nunchi_claude_v2.py print-settings`)
was **deliberately not merged** in this session, for two reasons recorded
honestly:

1. This autonomous session's permission boundary denied self-modification of
   the installed transport (`apply-transport-patch.sh` against the plugin
   directory), of `settings.json`, and of outbound Discord sends. Those
   denials are correct: they are operator-gated.
2. Registering the V2 gate before patch `0002` is applied would make the
   bound room deaf (every delivery is honestly unroutable without the
   native-fact sidecar). Fail-closed ordering requires the patch first.

## Installed-hook probes (executed against the Attempt-2 staged components)

1. **Non-channel prompt** — wrapper exit `0`, no output, no `$HOME` writes
   (also enforced repo-wide by `tests/test_no_home_writes.py`).
2. **Bound-channel prompt with no sidecar record** (patch-drift / not-yet-armed
   condition) — the installed gate produced `{"decision": "block", "reason":
   ""}` with stderr `unroutable channel event (… lacked an exact native
   message, channel, or author ID); verify the transport native-fact patch is
   installed`, and appended an unroutable quarantine row to
   `/Users/zmll/.claude/nunchi/claude-v2-state/events.jsonl`. This is the live
   fail-closed behavior for an unpatched/partially-armed transport: no
   identity is guessed and no social result is fabricated.

## Remaining operator steps to arm the live V2 runtime

```sh
cd <repo>/integrations/claude-code
# 0. If a prior install left a world-readable sidecar, delete it first:
rm -f ~/.claude/channels/discord/nunchi-native-events.jsonl
# 1. Apply the digest-pinned transport patches (fail-closed):
transport-patch/apply-transport-patch.sh \
  ~/.claude/plugins/cache/claude-plugins-official/discord/0.0.4
# 2. Register the four V2 hooks, REPLACING the V1 UserPromptSubmit entry:
python3 nunchi_claude_v2.py print-settings   # merge into ~/.claude/settings.json
# 3. (optional) provision the classifier credential in the owner-only policy
#    and set attention.preattention_enabled=true for ordinary classifier
#    routing; the shipped posture is trusted-bypass (zero classifier calls).
# 4. Start a fresh Claude Code session so plugin + hooks reload together.
```

Rollback: `transport-patch/apply-transport-patch.sh <plugin-dir> --rollback`
plus restoring the previous `settings.json` hook entry; operator state,
receipts, and policy files are never deleted by install or rollback.

## V1 residue on this host (reported, not hidden)

`~/.claude/hooks/nunchi_prompt_gate.py`, `nunchi-user-prompt-submit.sh`
(still registered), `~/.claude/nunchi-gate.env`, the retired send-time
surface's orphaned env file under `~/.claude/`, and the unregistered
`discord-poller.sh` remain on disk from the V1/turnaware installation
(recorded in `~/.claude/hooks/nunchi-source.txt`). They are superseded by
this packet; removal happens with the operator's registration switch above.
