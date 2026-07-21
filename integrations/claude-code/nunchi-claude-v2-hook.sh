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
#     crash cannot leak an admission. exit 0 alone does not prove the gate
#     produced a real decision: an empty/truncated gate FILE executes without
#     error and prints nothing, and brace-wrapped text is not proof either —
#     {not-json}, an unsupported {"decision":"allow"}, and a duplicate-key
#     object can all look brace-shaped while being invalid or semantically
#     wrong (duplicate JSON keys silently resolve to the LAST value). A
#     configured user-prompt-submit therefore validates stdout with strict
#     JSON parsing (rejecting duplicate keys and non-finite constants) against
#     the gate's own exact output contract — only a real block decision or a
#     real UserPromptSubmit hookSpecificOutput context, with exact keys and
#     types, passes; every other successful configured path already emits one
#     of those two shapes, so anything else can only mean the gate did not
#     really produce a decision, and is treated exactly like a crash.
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
  # Strict, independent validation of the gate's stdout — not the gate's own
  # json.dumps call, which a compromised or buggy gate need not have used.
  # Accepts ONLY an exact block decision or an exact UserPromptSubmit
  # hookSpecificOutput context, by exact key set and type; python3 is already
  # a hard dependency at this point (used above to run the gate itself).
  if ! printf '%s' "$OUTPUT" | python3 -c '
import json
import sys


def _no_duplicate_keys(pairs):
    seen = set()
    result = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("duplicate key")
        seen.add(key)
        result[key] = value
    return result


def _reject_constant(name):
    raise ValueError("non-finite constant")


def _is_block(value):
    return (
        isinstance(value, dict)
        and set(value) == {"decision", "reason"}
        and value["decision"] == "block"
        and isinstance(value["reason"], str)
    )


def _is_context(value):
    if not isinstance(value, dict) or set(value) != {"hookSpecificOutput"}:
        return False
    hso = value["hookSpecificOutput"]
    return (
        isinstance(hso, dict)
        and set(hso) == {"hookEventName", "additionalContext"}
        and hso["hookEventName"] == "UserPromptSubmit"
        and isinstance(hso["additionalContext"], str)
    )


try:
    parsed = json.loads(
        sys.stdin.read(),
        object_pairs_hook=_no_duplicate_keys,
        parse_constant=_reject_constant,
    )
except Exception:
    sys.exit(1)

sys.exit(0 if (_is_block(parsed) or _is_context(parsed)) else 1)
'
  then
    gate_unavailable "gate produced empty, malformed, or unsupported output"
  fi
fi
printf '%s' "$OUTPUT"
exit 0
