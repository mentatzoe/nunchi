#!/usr/bin/env bash
# Cloud environment setup for Nunchi agent sessions.
#
# Paste this into the Claude Code cloud environment's setup script field, or
# run it from a checkout. It installs the GitHub CLI and reports, precisely,
# which external services this session can and cannot reach.
#
# It never fails the session: every step is best-effort and the script always
# exits 0. A session that starts with a clear capability report is more useful
# than one that refuses to start.

set -uo pipefail

say() { printf '  %-8s %s\n' "$1" "$2"; }

echo "== Nunchi cloud session setup =="

# ---------------------------------------------------------------- github cli
# gh ships in Ubuntu 24.04 universe (2.45.0). Use it rather than cli.github.com,
# which is not reachable from this environment.
if command -v gh >/dev/null 2>&1; then
  say "ok" "gh already present ($(gh --version 2>/dev/null | head -1))"
else
  if apt-get install -y -qq gh >/dev/null 2>&1 || \
     { apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq gh >/dev/null 2>&1; }; then
    say "ok" "gh installed ($(gh --version 2>/dev/null | head -1))"
  else
    say "MISSING" "gh could not be installed; use the GitHub MCP tools instead"
  fi
fi

# ------------------------------------------------------------- reachability
# Report what works. Do not try to route around anything that does not:
# a 403 from the proxy or the relay is a policy decision, not a transient error.
probe() { curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$2" 2>/dev/null; }

api=$(probe github https://api.github.com/repos/mentatzoe/nunchi)
case "$api" in
  200) say "ok"     "GitHub API reachable; gh and curl can read and write issues" ;;
  403) say "BLOCKED" "GitHub API refused. The Claude GitHub App is not connected"
       say ""        "for this organization. An org admin connects it at"
       say ""        "claude.ai Settings > Connectors. Until then use the"
       say ""        "GitHub MCP tools, which take a different path." ;;
  *)   say "BLOCKED" "GitHub API unreachable (HTTP ${api:-none})" ;;
esac

orr=$(probe openrouter https://openrouter.ai/api/v1/models)
case "$orr" in
  200|401) say "ok"      "openrouter.ai reachable; attention route can be exercised" ;;
  *)       say "BLOCKED" "openrouter.ai not allowed by egress policy. The shipped"
           say ""        "attention route cannot be called from this session."
           say ""        "Allowlist it in the cloud environment, or land the"
           say ""        "Anthropic-native attention provider, which needs no"
           say ""        "network change since api.anthropic.com is reachable." ;;
esac

# git push works through the credential proxy regardless of the above.
say "note" "git fetch/push work via the credential proxy; commits author as Claude"

echo "== setup complete =="
exit 0
