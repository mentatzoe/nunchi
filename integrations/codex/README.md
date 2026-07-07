# Nunchi × Codex

Nunchi admission gating for Codex CLI on a Discord room, via the
`nunchi-mcp-discord` transport server (`integrations/mcp-discord/`).

Codex is **pull-only** as an MCP client: it can call the transport's tools,
but it never reacts to server notifications on its own. So this integration
has two pieces:

| Piece | What it is |
| --- | --- |
| `nunchi_room_runner.py` | The agent's **ear**. A long-running process that consumes the transport's SSE notification stream, runs every room message through `nunchi-channel`, and wakes Codex (`codex exec`) only for admitted turns (SPEAK / ACK / ASK). PASS = receipt only, zero frontier tokens. |
| `nunchi_prompt_gate_codex.py` | Defense-in-depth **UserPromptSubmit hook** for interactive Codex sessions. Gates only prompts carrying a `<channel source=...>` tag; blocks on PASS; permanently fail-open (an operator typing must never be silenced by a gate outage). |

The gate decides **admission, never composition**. On an admitted turn Codex
composes (or declines to compose) the reply itself and sends it through the
transport's MCP tools.

## What is enforced where

| Surface | Gated? | By | Failure policy |
| --- | --- | --- | --- |
| Room message → Codex wake | Yes, pre-LLM | room runner | **fail-closed** (`NUNCHI_RUNNER_FAIL_POLICY=open` to override) — a gate outage must not become a frontier-call storm |
| Channel-tagged prompt in an interactive session | Yes, pre-LLM (second layer) | `nunchi_prompt_gate_codex.py` | **fail-open** — a broken gate never silences the operator |
| Outbound `send_message` / `reply_message` calls | **Not enforced this round** | — (Codex `PreToolUse` hooks *can* gate these; building that hook is explicitly out of scope this round) | — |

The runner's wake prompt deliberately carries **no** `<channel>` tag: the
trigger was already gated, so the hook does not double-gate wakes. The hook
covers other bridges that paste channel-tagged messages into interactive
sessions.

A future outbound `PreToolUse` hook would register like this (shown for
completeness only — the hook script does not exist yet):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/nunchi/integrations/codex/nunchi_tool_gate_codex.py",
            "timeout": 60
          }
        ]
      }
    ]
  }
}
```

## Setup

1. Run the transport server (see `integrations/mcp-discord/README.md`):

   ```sh
   NUNCHI_DISCORD_TOKEN=... nunchi-mcp-discord
   ```

2. Give Codex the transport's tools (so wakes can send):

   ```sh
   codex mcp add nunchi-discord --url http://127.0.0.1:3993/mcp
   ```

3. Register the prompt hook in `~/.codex/hooks.json`:

   ```json
   {
     "hooks": {
       "UserPromptSubmit": [
         {
           "hooks": [
             {
               "type": "command",
               "command": "python3 /path/to/nunchi/integrations/codex/nunchi_prompt_gate_codex.py",
               "timeout": 60
             }
           ]
         }
       ]
     }
   }
   ```

4. Start the runner (long-running; needs `nunchi-channel` on PATH plus the
   classifier env it requires — `NUNCHI_CLASSIFIER_MODEL`, `OPENROUTER_API_KEY`):

   ```sh
   NUNCHI_RUNNER_AGENT_ID=dalgos NUNCHI_RUNNER_CHANNELS=123456789 \
     python3 integrations/codex/nunchi_room_runner.py
   ```

   To keep it alive across reboots, wrap that command in a systemd user
   service (`systemd-run --user --unit=nunchi-room-runner ...`) or a launchd
   agent (`launchctl submit -l nunchi-room-runner -- ...`) — one line, no
   unit files required.

## Runner environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `NUNCHI_TRANSPORT_URL` | `http://127.0.0.1:3993/mcp` | Transport's streamable-HTTP MCP endpoint |
| `NUNCHI_RUNNER_SELF_ID` | — | Discord user id of the runner's own bot; matching authors are skipped (belt-and-braces; the transport already drops its own) |
| `NUNCHI_RUNNER_CHANNELS` | (all) | Comma-separated channel ids to watch |
| `NUNCHI_RUNNER_HISTORY_WINDOW` | `20` | Rolling per-channel history size fed to the gate |
| `NUNCHI_RUNNER_AGENT_ID` | `agent` | Agent identity in the gate payload |
| `NUNCHI_RUNNER_MENTION_ID` | — | Agent's @mention handle on the surface |
| `NUNCHI_CHANNEL_BIN` | `which nunchi-channel` | Gate binary |
| `NUNCHI_RUNNER_GATE_TIMEOUT` | `30` | Gate subprocess timeout (seconds) |
| `NUNCHI_RUNNER_CODEX_BIN` | `codex` | Binary used for wakes (`codex exec --skip-git-repo-check --full-auto`) |
| `NUNCHI_RUNNER_CODEX_ARGS` | — | Extra `codex exec` args, shell-split (e.g. `-c model_reasoning_effort=xhigh`) |
| `NUNCHI_RUNNER_WAKE_TIMEOUT` | `300` | Wake subprocess timeout (seconds) |
| `NUNCHI_RUNNER_FAIL_POLICY` | `closed` | `closed`: gate error → no wake, loud receipt. `open`: degraded SPEAK-shaped wake |
| `NUNCHI_RUNNER_LOG` | `~/.nunchi/codex-runner-receipts.jsonl` | Receipt JSONL (shared with the hook; hook records carry `"direction": "hook-inbound"`) |

Wakes are serialized: the runner is single-threaded, so a wake blocks the
consume loop and triggers arriving mid-wake queue in the stream (the
transport's bounded queue drops the oldest backlog under overflow).

The hook reuses the Claude Code hook's env names for the shared knobs
(`NUNCHI_HOOK_AGENT_ID`, `NUNCHI_HOOK_MENTION_ID`, `NUNCHI_HOOK_PEER_BOTS`,
`NUNCHI_HOOK_HISTORY_WINDOW`, `NUNCHI_HOOK_TIMEOUT`,
`NUNCHI_HOOK_TOOL_PATTERN` — default `(?:send|reply)_message$` here) plus
`NUNCHI_CHANNEL_BIN` and `NUNCHI_RUNNER_LOG`.

## Receipts

One JSONL line per event: `ts`, `channel`, `message_id`, `author`,
`verdict`, `confidences` (when the gate returned them), `action`
(`pass-suppressed` | `wake-ok` | `wake-error` | `no-wake-gate-error` |
`skipped-self` | `skipped-channel` | `skipped-empty`), `wake_exit` when a
wake ran, `history_len`. Never message content, tokens, or keys.
