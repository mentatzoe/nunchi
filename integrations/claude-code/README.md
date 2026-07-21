# Nunchi V2 — Claude Code integration

This directory is the Claude Code V2 integration: one reactive Discord room
binding driven by Claude Code's native hook events, consuming the canonical
Nunchi V2 runtime. The V1 admission gate (`nunchi_prompt_gate.py`, the
`PASS/ACK/ASK/SPEAK` verdict flow, in-band admission notes, and the
`NUNCHI_DEFER*`/`NUNCHI_CLASSIFIER_*`/`NUNCHI_HOOK_*` environment surface) is
removed, not bridged.

Canonical behavior documentation lives at
[docs/integrations/claude-code-v2.md](../../docs/integrations/claude-code-v2.md).
This README is the operator install/verify guide.

## Contents

| Path | Role |
|---|---|
| `nunchi_claude_v2.py` | The integration: `user-prompt-submit`, `stop`, `pre-tool`, `post-tool`, `post-tool-failure` subcommands plus `print-settings` |
| `nunchi-claude-v2-hook.sh` | Hook wrapper. Enforces fail direction at the process boundary, not only inside the Python gate: a configured `user-prompt-submit` whose gate cannot run (missing `python3`, missing gate file, import/startup crash, killed by signal, any nonzero exit) blocks the room prompt rather than admitting it; `pre-tool` fails closed (exit 2); `stop`/`post-tool`/`post-tool-failure` fail open. Unconfigured (no policy) is inert and fails open everywhere. |
| `nunchi-claude-v2.env.example` | Trusted operator environment template |
| `nunchi-claude-v2-tools.example.json` | Deterministic tool classification map (room-action tools + privileged capabilities) |
| `transport-patch/` | Digest-pinned patches for the upstream Discord plugin and the fail-closed installer (see [transport-patch/README.md](transport-patch/README.md)) |
| `DEFER_EVAL.md` | The dual-DEFER contract and its evaluation plan |

## Install

Prerequisites: Python 3.11+, the `nunchi` package importable by the hook's
`python3` (install the built wheel, or set `PYTHONPATH` to the source layout
inside the env file), and the supported Claude Code Discord plugin.

1. **Patch the installed Discord plugin** (fail-closed; see
   [transport-patch/README.md](transport-patch/README.md)):

   ```sh
   transport-patch/apply-transport-patch.sh \
     ~/.claude/plugins/cache/claude-plugins-official/discord/0.0.4
   ```

2. **Copy the integration and wrapper**:

   ```sh
   install -m 0755 nunchi_claude_v2.py ~/.claude/hooks/nunchi_claude_v2.py
   install -m 0755 nunchi-claude-v2-hook.sh ~/.claude/hooks/nunchi-claude-v2-hook.sh
   ```

3. **Create the trusted configuration** (owner-only):

   ```sh
   install -m 0600 nunchi-claude-v2.env.example ~/.claude/nunchi-claude-v2.env
   # edit: policy path, state dir, exact channel and self snowflakes,
   # participant binding, optional tools map
   ```

   The operator policy JSON (attention budgets, `transition_defer_margin`,
   trusted preattention bypass, `error_action`, authorization grants,
   classifier endpoint/model/credential, receipt-sink directory) is the same
   canonical policy shape used by every V2 surface; keep it `0600` and
   owner-only, with the receipt directory `0700`.

   Also add `NUNCHI_CLAUDE_V2_CHANNEL_ID=<the same exact channel snowflake>`
   to the Discord plugin's OWN environment file
   (`~/.claude/channels/discord/.env`). The plugin process and the gate's
   hook process do not share an environment, so this exact value is
   configured twice; the transport patch reads it to skip two plugin-native
   behaviors for the bound room only (see
   [docs/integrations/claude-code-v2.md](../../docs/integrations/claude-code-v2.md#identity-hearing-and-honest-limits)).
   Leaving it unset keeps the patched plugin byte-for-byte behavior-identical
   to unpatched for every room.

4. **Register the hooks** — merge the output of

   ```sh
   python3 nunchi_claude_v2.py print-settings
   ```

   into `~/.claude/settings.json` (`UserPromptSubmit`, `Stop`, `PreToolUse`,
   `PostToolUse`, `PostToolUseFailure`).

5. **Restart the Claude Code session** so the patched plugin process and the
   hooks load together, then verify:

   ```sh
   transport-patch/apply-transport-patch.sh <plugin-dir> --verify
   ```

## Upgrade and rollback

Upgrading the plugin replaces `server.ts` with a new upstream base: re-run the
apply script, which refuses (exit 2) unless the base matches the pinned
digest — an unreviewed upstream never gets patched silently. Roll back with
`--rollback` (restores the pristine backup) and remove the five hook entries
from `settings.json` to disable the integration; state, receipts, and policy
files are operator data and are never deleted by install or rollback.

## Behavior in one paragraph

An authorized human or allowlisted-bot room event arrives reactively (no
polling), is bound to its exact native author through the transport sidecar,
uses Claude Code 2.1.215's exact `source="plugin:discord:discord"` envelope,
and becomes at most one conversation opportunity: one canonical attention call
(`SUPPRESS`/`WAKE`/both `DEFER` forms; trusted bypass makes zero classifier
calls; operational errors widen by policy) and, on every waking route, one
normal Claude turn that replies, reacts, or ends silently. There is no
send-time social judgment, no prose filter, no admission meta-answer, and no
per-message response queue: bursts coalesce to one fresh successor, whether
they arrive while a turn is active or are already fully recorded in the
sidecar before the first queued prompt's own hook even runs. A woken
turn's reply or reaction is reserved atomically at `PreToolUse` — bound to the
exact `tool_use_id`, tool name, and input — and only `PostToolUse` or
`PostToolUseFailure` reporting that same `tool_use_id` can close it; if `Stop`
finds an open reservation neither hook closed, the turn's outcome is honestly
`unknown`, never silently reported as silence. Every other native Discord
tool (`edit_message`, `download_attachment`, and anything the plugin adds
later) is denied by default for a room-caused turn — only `fetch_messages`
(read-only, room-scoped) and the reply/react reservation are supported.
Suppressed and self events stay retained for later hearing; restarts drop
pending wake work and keep retained context. Privileged tool actions in
room-caused turns require a deterministic guard decision derived from the
transport-attested requester.

## Verification

```sh
python3 -m unittest tests.v2.test_claude_code
python3 -m unittest            # full offline baseline
python3 scripts/check_governance.py
```

Deterministic conformance lives in `tests/v2/test_claude_code.py` with
fixtures in `tests/fixtures/v2/claude_code/` and replay corpora in
`evals/v2/claude_code/`. Live-room evidence and installed provenance land
under `evidence/v2/claude-code/`.

## Known limitations

- **Cold wake**: the plugin delivers only to a live session; nothing wakes
  Claude Code from a dead process, and undelivered events are recoverable only
  through bounded native history.
- **Session restart**: pending coalesced anchors are dropped by design; an
  interrupted turn's participant-host stage stays honestly absent.
- **Reactions/membership**: not delivered by this transport; declared
  unavailable rather than synthesized.
- **Reply context**: the sidecar records the replied-to message ID; the
  referenced author and content are not synchronously known to the transport
  and stay honestly absent.
- **Guard coverage**: only tools named in the configured privileged map are
  guarded; unlisted tools, sessions with hooks disabled, and hook-bypassing
  host features are unenforced paths and are reported as such in evidence.
- **Reservation coverage**: the one-reservation-per-turn and
  `PostToolUse`/`PostToolUseFailure` correlation only see room-action tools
  named by `room_action_tools.reply_pattern`/`react_pattern`, and only when
  `PreToolUse` actually ran (a session with `PreToolUse` disabled but
  `PostToolUse` still registered cannot bind a reservation, so an unreserved
  send is reported as an unattested action, not "sent" — this is the same
  disabled-hooks limitation as guard coverage, not a separate gap).
- **Suppression surface**: an effectively suppressed prompt is blocked with an
  empty reason; the Claude Code host may still render a generic blocked-prompt
  marker in the local session transcript. The room never sees it.
- **Native permission DM/button approval**: the plugin's own
  `notifications/claude/channel/permission_request` bridge (Discord DM +
  button click, answering Claude Code's native interactive tool-permission
  prompt) is a separate, cross-session surface reached only via DM and is
  not scoped to the Nunchi-bound room by construction — a `pendingPermissions`
  request is keyed only by a short code, with no room/turn provenance
  attached. The transport patch disables the room-TEXT leg of this bridge
  (`yes/no <code>` typed in the bound room) but the DM/button leg remains
  outside this integration's control; it is reported, not claimed safe.
