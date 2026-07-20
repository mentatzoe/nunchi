# CC-06 — Installed runtime provenance (Claude Code V2)

**Recorded**: 2026-07-20 by the `v2-claude-owner` lane (Station,
standing Claude Code agent). Secrets are excluded by construction: no
credential exists in any file this record names.

## Host and harness

| Component | Exact value |
|---|---|
| Host OS | macOS 15.3.1 (Darwin 24.3.0, build 24D70) |
| Claude Code | `2.1.215` |
| Session model | `claude-fable-5` |
| Python (hook runtime) | `3.14.3` (Homebrew) |
| Bun (plugin runtime) | `1.3.11` |
| Nunchi package | `0.2.0` at source commit `4e46b3907d4bb27b30275160ca8fb2b9e763ad24` (candidate lineage; final candidate commit recorded in `handoff.md`) |

## Discord plugin (transport base)

| Fact | Exact value |
|---|---|
| Plugin | `discord@claude-plugins-official`, version `0.0.4` |
| Install path | `/Users/zmll/.claude/plugins/cache/claude-plugins-official/discord/0.0.4` |
| Pristine base `server.ts.orig-0.0.4` SHA-256 | `c3c79c6519e23470fcc5f07e38415e50b4f054e42e670e89bd037fa64659e135` (matches the packet's pinned patch base exactly) |
| Current installed `server.ts` SHA-256 | `b025d1c2aa7df54a03fb2b03d403276902959cc13f7327d559a96eb2a91f358b` |
| Current installed state | An earlier, functionally equivalent wording of patch `0001` (self-only bot guard) applied on 2026-07-09; patch `0002` (native-fact sidecar) **not yet applied** |
| Canonical patched target SHA-256 | `e26b6d2316413f2fb886a54346364e44c1c29dbffc6136dbfeb357b69198f115` (base + `0001` + `0002`, verified reproducible from the pinned base in this packet's patch-build check) |
| MCP registration | `.mcp.json`: `bun run --cwd ${CLAUDE_PLUGIN_ROOT} --shell=bun --silent start` (stdio) |
| Delivery mechanism | Discord gateway (WebSocket push) → `messageCreate` → `gate()` authorization → MCP notification `notifications/claude/channel` → host-rendered `<channel>` prompt. Reactive; no polling path exists. A legacy `discord-poller.sh` exists on disk but is registered nowhere (settings/launchd/cron all checked) and is not running. |

## Staged V2 integration components (installed this session)

| Path | SHA-256 | Notes |
|---|---|---|
| `/Users/zmll/.claude/hooks/nunchi_claude_v2.py` | `2bad44244b94bfc51c00ad8f05a8cecda09b5f912184ecb3a09fec2e50a40421` | Exact copy of `integrations/claude-code/nunchi_claude_v2.py` |
| `/Users/zmll/.claude/hooks/nunchi-claude-v2-hook.sh` | `e76ff4a9deb2dcf17c397ef7b225e1e41a22e3d3767827659fe7013a90a3cc83` | Exact copy of `integrations/claude-code/nunchi-claude-v2-hook.sh` |
| `/Users/zmll/.claude/nunchi-claude-v2.env` | `8b7c9d23012061b96b561a6caaf8e8e538409cae478fa8232b11a40c8c5ba29d` | Room binding: channel `1522258711047831653`, self `1484970897893752902`, participant `station`; no credential |
| `/Users/zmll/.claude/nunchi/claude-v2-policy.json` | `c4a74571b1d5d7f372c2558ab6f9ea05110bc2a70f10302873039b6a086c4973` | Trusted-bypass posture: `preattention_enabled=false`, `social_suppression_enabled=false`, `error_action=WAKE`, empty authorization grants, receipt sink `/Users/zmll/.claude/nunchi/claude-v2-receipts` (0700) |
| `/Users/zmll/.claude/nunchi/claude-v2-tools.json` | `d48ef9c965ea6f53dc3218e39a43c747fdb99a97b3246bb572da8ff891daaa15` | Room-action tool patterns + privileged map (`Bash`, `Write/Edit/NotebookEdit`); with empty grants every privileged room-caused proposal is denied |
| `/Users/zmll/.claude/nunchi/runtime/` | manifest `29b6a55dec552c7e6b16907cee7d52aa7e44c584daea6ebcc6e91c95910724b2` | Copy-with-manifest deployment of `src/nunchi` (43 files, per-file SHA-256 in `DEPLOY-MANIFEST.json`, source commit recorded); no symlinks |

## Hook registration state — NOT yet armed

`~/.claude/settings.json` still registers the **V1** `UserPromptSubmit` hook
(`/Users/zmll/.claude/hooks/nunchi-user-prompt-submit.sh`, status message
"nunchi: is this my turn?"). The V2 registration (four events, produced by
`python3 nunchi_claude_v2.py print-settings`) was **deliberately not merged**
in this session, for two reasons recorded honestly:

1. This autonomous session's permission boundary denied self-modification of
   the installed transport (`apply-transport-patch.sh` against the plugin
   directory) and of `settings.json`. That denial is correct: those are
   operator-gated actions.
2. Registering the V2 gate before patch `0002` is applied would make the
   bound room deaf (every delivery would be honestly unroutable without the
   native-fact sidecar). Fail-closed ordering requires the patch first.

## Installed-hook probes (executed against the staged components)

1. **Non-channel prompt, unconfigured environment** — wrapper exit `0`, no
   output, no filesystem writes under `$HOME` (also enforced repo-wide by
   `tests/test_no_home_writes.py`).
2. **Bound-channel prompt with no sidecar record** (patch-drift condition) —
   installed gate produced
   `{"decision": "block", "reason": ""}` with stderr
   `unroutable channel event (Discord delivery lacked an exact native
   message, channel, or author ID); verify the transport native-fact patch is
   installed`, and appended an unroutable quarantine row to
   `/Users/zmll/.claude/nunchi/claude-v2-state/events.jsonl`. This is the
   live fail-closed behavior for an incompletely patched transport: no
   identity is guessed and no social result is fabricated.

## Remaining operator steps to arm the live V2 runtime

```sh
cd <repo>/integrations/claude-code
transport-patch/apply-transport-patch.sh \
  ~/.claude/plugins/cache/claude-plugins-official/discord/0.0.4
python3 nunchi_claude_v2.py print-settings   # merge into ~/.claude/settings.json,
                                             # REPLACING the V1 UserPromptSubmit entry
# optional, for ordinary classifier-routed attention:
#   set classifier endpoint/model/api_key in ~/.claude/nunchi/claude-v2-policy.json
#   and flip attention.preattention_enabled to true
# then start a fresh Claude Code session (plugin + hooks reload together)
```

Rollback: `transport-patch/apply-transport-patch.sh <plugin-dir> --rollback`
plus restoring the previous `settings.json` hook entry; operator state,
receipts, and policy files are never deleted by install or rollback.

## V1 residue on this host (reported, not hidden)

`~/.claude/hooks/nunchi_prompt_gate.py`, `nunchi-user-prompt-submit.sh`
(still registered), `~/.claude/nunchi-gate.env`, the retired send-time
surface's orphaned env file under `~/.claude/`, and the
unregistered `discord-poller.sh` remain on disk from the V1/turnaware
installation (recorded in `~/.claude/hooks/nunchi-source.txt`). They are
superseded by this packet; removal happens with the operator's registration
switch above.
