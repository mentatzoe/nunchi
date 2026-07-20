#!/bin/sh
# nunchi-claude-v2-hook.sh — wrapper for the Nunchi V2 Claude Code hooks.
# Installed to ~/.claude/hooks/ by the operator; settings entries pass the
# hook event as $1 (user-prompt-submit | stop | pre-tool | post-tool).
#
# Failure direction is per event and deliberate:
#   * user-prompt-submit / stop / post-tool fail OPEN — a broken gate must
#     never deafen or trap the participant; attention errors widen toward
#     hearing and the missing receipts stay an honest gap.
#   * pre-tool fails CLOSED — a configured privileged-action guard that
#     cannot run must deny, not silently wave privileged tools through.
set -u
HOOK_EVENT="${1:-}"
GATE="${NUNCHI_CLAUDE_V2_GATE:-$HOME/.claude/hooks/nunchi_claude_v2.py}"
[ -f "$HOME/.claude/nunchi-claude-v2.env" ] && . "$HOME/.claude/nunchi-claude-v2.env"

fail_exit() {
  if [ "$HOOK_EVENT" = "pre-tool" ] && [ -n "${NUNCHI_CLAUDE_V2_POLICY:-}" ]; then
    echo "nunchi-claude-v2: action guard unavailable; failing closed" >&2
    exit 2
  fi
  exit 0
}

command -v python3 >/dev/null 2>&1 || fail_exit
[ -f "$GATE" ] || fail_exit
python3 "$GATE" "$HOOK_EVENT"
STATUS=$?
if [ "$STATUS" -ne 0 ]; then
  if [ "$HOOK_EVENT" = "pre-tool" ]; then
    exit "$STATUS"
  fi
  exit 0
fi
exit 0
