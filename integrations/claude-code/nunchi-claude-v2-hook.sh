#!/bin/sh
# nunchi-claude-v2-hook.sh — wrapper for the Nunchi V2 Claude Code hooks.
# Installed to ~/.claude/hooks/ by the operator; settings entries pass the
# hook event as $1 (user-prompt-submit | stop | pre-tool | post-tool).
#
# Failure direction is per event and deliberate, and is enforced HERE at the
# process boundary — not only inside the Python gate. "Configured" means
# NUNCHI_CLAUDE_V2_POLICY is set; when it is not, the integration is inert and
# every event fails open.
#
#   * user-prompt-submit — fails CLOSED when configured. A missing python3,
#     a missing gate file, an import/startup crash, or any signal/nonzero
#     exit must BLOCK the prompt, never admit it: the Python fail-closed
#     safeguards (foreign-room decline, degraded-marker recording, invalid
#     policy handling) run inside the gate, so a gate that cannot run must not
#     let a room prompt through. The gate's stdout is captured so a partial
#     crash cannot leak an admission. A gate that runs and exits 0 but is
#     empty or truncated (a corrupted/zero-byte gate file executes cleanly
#     and silently) is exit-status-invisible, so a configured
#     user-prompt-submit additionally requires the gate's stdout to be
#     non-empty and structurally JSON-shaped; the Python gate always emits an
#     explicit decision for every successful configured path, including a
#     plain operator prompt with nothing to add — so genuinely empty or
#     malformed output can only mean the gate itself failed to run for real,
#     and is treated exactly like a crash.
#   * pre-tool — fails CLOSED when configured: a privileged-action guard that
#     cannot run must deny (exit 2), not wave privileged tools through.
#   * stop / post-tool — fail OPEN: a broken turn-completion or observation
#     hook must not trap or deafen the participant, and neither can admit a
#     room turn on its own. Missing receipts stay an honest gap.
set -u
HOOK_EVENT="${1:-}"
GATE="${NUNCHI_CLAUDE_V2_GATE:-$HOME/.claude/hooks/nunchi_claude_v2.py}"
# set -a: bare VAR=value assignments in the env file must reach the Python
# process as real environment, not shell-local variables.
if [ -f "$HOME/.claude/nunchi-claude-v2.env" ]; then
  set -a
  . "$HOME/.claude/nunchi-claude-v2.env"
  set +a
fi

configured() { [ -n "${NUNCHI_CLAUDE_V2_POLICY:-}" ]; }

# The gate could not run to a clean decision. Fail per event direction; a
# configured user-prompt-submit failure emits the same block shape the Python
# handler uses, with an operator recovery hint, so the room prompt is never
# admitted by a broken gate.
gate_unavailable() {
  reason="$1"
  case "$HOOK_EVENT" in
    user-prompt-submit)
      if configured; then
        printf '%s' '{"decision": "block", "reason": "nunchi-v2 gate unavailable; failing closed. Fix the gate or unset NUNCHI_CLAUDE_V2_POLICY to bypass."}'
        echo "nunchi-claude-v2: user-prompt-submit gate unavailable ($reason); blocking fail-closed" >&2
      fi
      exit 0 ;;
    pre-tool)
      if configured; then
        echo "nunchi-claude-v2: action guard unavailable ($reason); failing closed" >&2
        exit 2
      fi
      exit 0 ;;
    *)
      # stop / post-tool: fail open.
      exit 0 ;;
  esac
}

command -v python3 >/dev/null 2>&1 || gate_unavailable "python3 missing"
[ -f "$GATE" ] || gate_unavailable "gate file missing"

# Capture stdout so (a) a crash cannot leak partial output as an admission and
# (b) a nonzero exit can be converted to a fail-closed block. stderr and stdin
# pass through: the gate still reads the payload and logs diagnostics.
OUTPUT=$(python3 "$GATE" "$HOOK_EVENT")
STATUS=$?
if [ "$STATUS" -ne 0 ]; then
  gate_unavailable "gate exit $STATUS"
fi
if [ "$HOOK_EVENT" = "user-prompt-submit" ] && configured; then
  # exit 0 alone does not prove the gate produced a real decision: an empty
  # or truncated gate FILE executes without error and prints nothing. The
  # Python gate always writes an explicit, non-empty, JSON-object decision
  # for every successful configured path, so empty or non-object output here
  # can only mean the gate itself did not really run — treat it exactly like
  # a crash rather than forwarding it as an implicit allow.
  case "$OUTPUT" in
    '{'*'}') : ;;
    *) gate_unavailable "gate produced empty or malformed output" ;;
  esac
fi
printf '%s' "$OUTPUT"
exit 0
