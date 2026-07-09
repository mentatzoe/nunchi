#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="${NUNCHI_CODEX_SMOKE_VENV:-/tmp/nunchi-codex-smoke-venv}"
LOG_DIR="${NUNCHI_CODEX_SMOKE_LOG_DIR:-$ROOT/.tmp/codex-smoke-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$LOG_DIR"

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    printf 'missing required env: %s\n' "$name" >&2
    exit 2
  fi
}

require_env NUNCHI_DISCORD_TOKEN
require_env NUNCHI_CLASSIFIER_MODEL
require_env OPENROUTER_API_KEY

if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install -U pip setuptools wheel >/dev/null
"$VENV/bin/python" -m pip install -e "$ROOT[discord,mcp-discord]" >/dev/null

export PATH="$VENV/bin:$PATH"
export NUNCHI_TRANSPORT_URL="${NUNCHI_TRANSPORT_URL:-http://127.0.0.1:3993/mcp}"
export NUNCHI_RUNNER_CHANNELS="${NUNCHI_RUNNER_CHANNELS:-1522258711047831653}"
export NUNCHI_RUNNER_SELF_ID="${NUNCHI_RUNNER_SELF_ID:-1494822530643398827}"
export NUNCHI_RUNNER_AGENT_ID="${NUNCHI_RUNNER_AGENT_ID:-vigil}"
export NUNCHI_RUNNER_MENTION_ID="${NUNCHI_RUNNER_MENTION_ID:-$NUNCHI_RUNNER_SELF_ID}"
export NUNCHI_RUNNER_ALIASES="${NUNCHI_RUNNER_ALIASES:-Vigil,Codex}"
export NUNCHI_RUNNER_FAIL_POLICY="${NUNCHI_RUNNER_FAIL_POLICY:-closed}"
export NUNCHI_CHANNEL_BIN="${NUNCHI_CHANNEL_BIN:-$VENV/bin/nunchi-channel}"
export NUNCHI_RUNNER_LOG="${NUNCHI_RUNNER_LOG:-$LOG_DIR/codex-runner-receipts.jsonl}"
export NUNCHI_RUNNER_CODEX_ARGS="${NUNCHI_RUNNER_CODEX_ARGS:---dangerously-bypass-approvals-and-sandbox --dangerously-bypass-hook-trust -c model_reasoning_effort=xhigh}"
export NUNCHI_HOOK_AGENT_ID="${NUNCHI_HOOK_AGENT_ID:-$NUNCHI_RUNNER_AGENT_ID}"
export NUNCHI_HOOK_MENTION_ID="${NUNCHI_HOOK_MENTION_ID:-$NUNCHI_RUNNER_MENTION_ID}"
export NUNCHI_HOOK_ALIASES="${NUNCHI_HOOK_ALIASES:-$NUNCHI_RUNNER_ALIASES}"
export NUNCHI_HOOK_FAIL_POLICY="${NUNCHI_HOOK_FAIL_POLICY:-closed}"

codex plugin marketplace add "$ROOT" --json >"$LOG_DIR/codex-marketplace-add.json"
codex plugin list >"$LOG_DIR/codex-plugin-list.before.txt"
codex plugin add nunchi-codex@local-repo --json >"$LOG_DIR/codex-plugin-add.json"
codex plugin list >"$LOG_DIR/codex-plugin-list.after.txt"

probe_transport() {
  "$VENV/bin/python" - "$NUNCHI_TRANSPORT_URL" <<'PY'
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

url = sys.argv[1]
body = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "nunchi-codex-smoke-probe", "version": "0"},
    },
}
req = urllib.request.Request(
    url,
    data=json.dumps(body).encode("utf-8"),
    method="POST",
    headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
)
try:
    resp = urllib.request.urlopen(req, timeout=2)
except urllib.error.HTTPError as exc:
    if exc.code not in (307, 308) or not exc.headers.get("Location"):
        raise
    location = urllib.parse.urljoin(req.full_url, exc.headers["Location"])
    exc.close()
    retry = urllib.request.Request(
        location,
        data=req.data,
        method=req.get_method(),
        headers=dict(req.header_items()),
    )
    resp = urllib.request.urlopen(retry, timeout=2)
with resp:
    if not resp.headers.get("mcp-session-id"):
        raise SystemExit(1)
PY
}

TRANSPORT_PID=""
if ! probe_transport >/dev/null 2>&1; then
  nunchi-mcp-discord >"$LOG_DIR/nunchi-mcp-discord.log" 2>&1 &
  TRANSPORT_PID="$!"
  cleanup() {
    if [[ -n "$TRANSPORT_PID" ]] && kill -0 "$TRANSPORT_PID" >/dev/null 2>&1; then
      kill "$TRANSPORT_PID" >/dev/null 2>&1 || true
    fi
  }
  trap cleanup EXIT

  for _ in $(seq 1 60); do
    if probe_transport >/dev/null 2>&1; then
      break
    fi
    if ! kill -0 "$TRANSPORT_PID" >/dev/null 2>&1; then
      printf 'nunchi-mcp-discord exited before becoming reachable; see %s\n' "$LOG_DIR/nunchi-mcp-discord.log" >&2
      exit 1
    fi
    sleep 0.5
  done
fi

if ! probe_transport >/dev/null 2>&1; then
  printf 'transport never became reachable at %s; see %s\n' "$NUNCHI_TRANSPORT_URL" "$LOG_DIR" >&2
  exit 1
fi

cat >"$LOG_DIR/smoke-summary.txt" <<EOF
Codex Vigil smoke started.
channel_ids=$NUNCHI_RUNNER_CHANNELS
agent_id=$NUNCHI_RUNNER_AGENT_ID
mention_id=$NUNCHI_RUNNER_MENTION_ID
aliases=$NUNCHI_RUNNER_ALIASES
transport_url=$NUNCHI_TRANSPORT_URL
receipts=$NUNCHI_RUNNER_LOG
plugin=nunchi-codex@local-repo
venv=$VENV
evidence_command=$VENV/bin/python integrations/codex/summarize_vigil_smoke.py --log "$NUNCHI_RUNNER_LOG" --out integrations/codex/evidence/$(date -u +%Y-%m-%d)-vigil-live-smoke.md
EOF

printf 'Vigil smoke runner ready. Ask in Discord channel %s; receipts: %s\n' "$NUNCHI_RUNNER_CHANNELS" "$NUNCHI_RUNNER_LOG"
printf 'After a successful wake and send, summarize evidence with:\n'
printf '  %s/bin/python integrations/codex/summarize_vigil_smoke.py --log %q --out integrations/codex/evidence/%s-vigil-live-smoke.md\n' "$VENV" "$NUNCHI_RUNNER_LOG" "$(date -u +%Y-%m-%d)"

if [[ -n "${NUNCHI_RUNNER_CONFIG:-}" ]]; then
  exec nunchi-codex-room-runner --config "$NUNCHI_RUNNER_CONFIG"
fi
exec nunchi-codex-room-runner
