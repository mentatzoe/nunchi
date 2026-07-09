# Nunchi × Codex

Nunchi admission gating for Codex CLI on a Discord room, via the shared
`nunchi-mcp-discord` transport server.

Current branch status: this branch contains the Codex-side runner, inbound
UserPromptSubmit hook, outbound PreToolUse send gate, configurable runner
TOML/env loading, startup history backfill for configured channels, a
repo-installable Codex plugin bundle at
[`nunchi-codex/`](./nunchi-codex/), offline tests, and one committed Vigil
live-smoke evidence file. Sustained live Discord participation still requires
the shared `nunchi-mcp-discord` transport, Discord credentials, the installed
Codex plugin, and the long-running room runner.

Codex is **pull-only** as an MCP client: it can call the transport's tools,
but it never reacts to server notifications on its own. So this integration
has three pieces:

| Piece | What it is |
| --- | --- |
| `nunchi-codex-room-runner` (`nunchi_room_runner.py`) | The agent's **ear**. A long-running process that consumes the transport's SSE notification stream, runs every room message through `nunchi-channel`, and wakes Codex (`codex exec`) only for admitted turns (SPEAK / ACK / ASK). PASS = receipt only, zero frontier tokens. |
| `nunchi-codex-prompt-gate` (`nunchi_prompt_gate_codex.py`) | Defense-in-depth **UserPromptSubmit hook** for interactive Codex sessions. Gates only prompts carrying a `<channel source=...>` tag; blocks on PASS; fail-open on gate errors (an operator typing must never be silenced by a gate outage). |
| `nunchi-codex-send-gate` (`nunchi_send_gate_codex.py`) | **PreToolUse hook** for outbound room sends. Re-checks supported `send_message`/`reply_message` MCP tool calls against Nunchi immediately before the tool runs. Matching sends without current runner-provided Nunchi room context are denied, as is a second room send for the same admitted context. |

The gate decides **admission, never composition**. On an admitted turn Codex
composes (or declines to compose) the reply itself and sends it through the
transport's MCP tools.

## What is enforced where

| Surface | Gated? | By | Failure policy |
| --- | --- | --- | --- |
| Room message → Codex wake | Yes, pre-LLM | room runner | **fail-closed** (`NUNCHI_RUNNER_FAIL_POLICY=open` to override) — a gate outage must not become a frontier-call storm |
| Channel-tagged prompt in an interactive session | Yes, pre-LLM (second layer) | `nunchi_prompt_gate_codex.py` | **fail-open** — a broken gate never silences the operator |
| Outbound `send_message` / `reply_message` calls | Yes, pre-tool for supported send paths | `nunchi-codex-send-gate` plus transport-side send backstop | **fail-closed** by default (`NUNCHI_HOOK_FAIL_POLICY=open` to override for drills). Matching sends without current Nunchi room context, or after a prior send for the same context, are denied |
| Direct Discord-ish Bash send commands | Denied, not gated | `nunchi-codex-send-gate` | Denies direct Discord channel-message API calls, Discord webhook API calls, and `nunchi-discord` shell sends. Use the Nunchi Discord MCP send tools so the hook and transport backstop can see the send |

The runner's wake prompt deliberately carries **no** `<channel>` tag: the
trigger was already gated, so the inbound prompt hook does not double-gate
wakes. It does include a compact `<nunchi_context>` JSON block for the
outbound send gate. That block is the hook's admission context, not prose for
reply composition. The send gate accepts only a context block on the latest
user turn and denies a second room send after one send has already been
recorded for that same context.

Residual risk: Codex hooks are a guardrail surface, not a complete runtime
sandbox. This integration's parity claim is for the configured Nunchi Discord
MCP send path plus the direct-send denials above. Do not expose alternate
Discord tokens, webhook tools, browser sessions, or send-capable MCP servers
to the room runner profile unless they have their own Nunchi gate.

## Codex plugin bundle

The checked-in plugin bundle lives at
[`integrations/codex/nunchi-codex/`](./nunchi-codex/). The repo marketplace at
[`/.agents/plugins/marketplace.json`](../../.agents/plugins/marketplace.json)
exposes it as `nunchi-codex@local-repo`.

The plugin bundles:

- `hooks/hooks.json`: `UserPromptSubmit` runs `nunchi-codex-prompt-gate`;
  `PreToolUse` runs `nunchi-codex-send-gate`.
- `.mcp.json`: a `nunchi-discord` streamable-HTTP MCP server at
  `http://127.0.0.1:3993/mcp`, limited to `read_history`, `send_message`,
  and `reply_message`.

The hook commands are installed console scripts. The plugin deliberately does
not point hooks at checkout-specific `.py` files; absolute checkout paths are
brittle across branches and were the class of failure seen in the July 9 hook
screenshot.

## Setup

1. Install Nunchi from this checkout so Codex can find the hook and runner
   console scripts, and so the shared MCP transport can import its SDK:

   ```sh
   python3 -m pip install -e ".[discord,mcp-discord]"
   ```

2. Add this repo as a Codex plugin marketplace and install the plugin:

   ```sh
   codex plugin marketplace add /path/to/nunchi-repo
   codex plugin add nunchi-codex@local-repo
   ```

   Restart Codex after install. Review and trust the bundled hooks in `/hooks`
   before relying on them; changed hook definitions require re-review.

3. Run the shared transport server:

   ```sh
   NUNCHI_DISCORD_TOKEN=... nunchi-mcp-discord
   ```

   The plugin already contributes the Codex MCP server entry for that local
   endpoint. Manual `codex mcp add nunchi-discord --url ...` setup is only
   needed when running without the plugin.

4. If you are running without the plugin, register equivalent hooks in
   `~/.codex/hooks.json`:

   ```json
   {
     "hooks": {
       "UserPromptSubmit": [
         {
           "hooks": [
             {
               "type": "command",
               "command": "nunchi-codex-prompt-gate",
               "timeout": 60
             }
           ]
         }
       ],
       "PreToolUse": [
         {
           "hooks": [
             {
               "type": "command",
               "command": "nunchi-codex-send-gate",
               "timeout": 60
             }
           ]
         }
       ]
     }
   }
   ```

5. Start the runner (long-running; it refuses to start unless `nunchi-channel`
   resolves to an executable, and the gate still needs its classifier env —
   `NUNCHI_CLASSIFIER_MODEL`, `OPENROUTER_API_KEY`):

   ```sh
   nunchi-codex-room-runner --config ~/.nunchi/codex-runner.toml
   ```

   Example config:

   ```toml
   [runner]
   transport_url = "http://127.0.0.1:3993/mcp"
   channels = ["123456789012345678"]
   self_id = "1494822530643398827"
   agent_id = "vigil"
   mention_id = "1494822530643398827"
   aliases = ["Vigil", "Codex"]
   fail_policy = "closed"
   codex_args = [
     "--dangerously-bypass-approvals-and-sandbox",
     "-c",
     "model_reasoning_effort=xhigh",
   ]
   ```

   To keep it alive across reboots, wrap that command in a systemd user
   service (`systemd-run --user --unit=nunchi-room-runner ...`) or a launchd
   agent (`launchctl submit -l nunchi-room-runner -- ...`) — one line, no
   unit files required.

## Vigil live smoke helper

For the nunchi-room smoke, [`run_vigil_smoke.sh`](./run_vigil_smoke.sh)
sets up the current checkout in a venv, installs `nunchi-codex@local-repo`,
starts `nunchi-mcp-discord` if the local transport is not already reachable,
and then execs `nunchi-codex-room-runner`.

Required environment:

```sh
export NUNCHI_DISCORD_TOKEN=...
export NUNCHI_CLASSIFIER_MODEL=...
export OPENROUTER_API_KEY=...
integrations/codex/run_vigil_smoke.sh
```

Defaults are the current smoke lane and bot identity:
`NUNCHI_RUNNER_CHANNELS=1522258711047831653`,
`NUNCHI_RUNNER_AGENT_ID=vigil`,
`NUNCHI_RUNNER_SELF_ID=1494822530643398827`,
`NUNCHI_RUNNER_MENTION_ID=1494822530643398827`, and
`NUNCHI_RUNNER_ALIASES=Vigil,Codex`. Override any of those environment
variables for another lane or bot. The helper also sets
`NUNCHI_RUNNER_CODEX_ARGS` to include
`--dangerously-bypass-hook-trust` because the script has just installed and
validated the local plugin bundle; use `/hooks` and remove that flag for a
persistent operator setup.

After the runner has observed a successful admitted wake and outbound hook
allow, summarize the receipt log into committed evidence:

```sh
/tmp/nunchi-codex-smoke-venv/bin/python integrations/codex/summarize_vigil_smoke.py \
  --log .tmp/<smoke-dir>/codex-runner-receipts.jsonl \
  --out integrations/codex/evidence/YYYY-MM-DD-vigil-live-smoke.md
```

The summarizer fails unless the log proves both `wake-ok` and outbound
`allow-speak`/`allow-ask`/`allow-ack` for the configured channel. It omits
message bodies.

## Runner environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `NUNCHI_RUNNER_CONFIG` | — | Optional TOML config path. Equivalent to `--config`; environment variables below override file values |
| `NUNCHI_TRANSPORT_URL` | `http://127.0.0.1:3993/mcp` | Transport's streamable-HTTP MCP endpoint |
| `NUNCHI_RUNNER_SELF_ID` | — | Discord user id of the runner's own bot; matching authors are skipped (belt-and-braces; the transport already drops its own) |
| `NUNCHI_RUNNER_CHANNELS` | (all) | Comma-separated channel ids to watch |
| `NUNCHI_RUNNER_HISTORY_WINDOW` | `20` | Rolling per-channel history size fed to the gate |
| `NUNCHI_RUNNER_AGENT_ID` | `agent` | Agent identity in the gate payload |
| `NUNCHI_RUNNER_MENTION_ID` | — | Agent's @mention handle on the surface. This is the **platform mention token** — on Discord the numeric snowflake (e.g. `1496355876234199040`) — **not** the display name. A display name here makes the gate blind to real @-mentions: a direct `@<snowflake>` mention reads as "someone else" and PASSes (observed live 2026-07-08). Names belong in `NUNCHI_RUNNER_ALIASES` |
| `NUNCHI_RUNNER_ALIASES` | — | Comma-separated additional identities this agent answers to (display names, nicknames, secondary handles, extra mention tokens, e.g. `Vigil,Codex,Aether`) → `agent.aliases`. Absent means behavior is unchanged |
| `NUNCHI_CHANNEL_BIN` | `which nunchi-channel` | Gate binary; the runner refuses startup if it is missing or not executable |
| `NUNCHI_RUNNER_GATE_TIMEOUT` | `30` | Gate subprocess timeout (seconds) |
| `NUNCHI_RUNNER_CODEX_BIN` | `codex` | Binary used for wakes (`codex exec --skip-git-repo-check --full-auto`) |
| `NUNCHI_RUNNER_CODEX_ARGS` | — | Extra `codex exec` args, shell-split (e.g. `-c model_reasoning_effort=xhigh`) |
| `NUNCHI_RUNNER_WAKE_TIMEOUT` | `300` | Wake subprocess timeout (seconds) |
| `NUNCHI_RUNNER_FAIL_POLICY` | `closed` | `closed`: gate error → no wake, loud receipt. `open`: degraded SPEAK-shaped wake |
| `NUNCHI_RUNNER_LOG` | `~/.nunchi/codex-runner-receipts.jsonl` | Receipt JSONL (shared with the hook; hook records carry `"direction": "hook-inbound"`) |

Wakes are serialized: the runner is single-threaded, so a wake blocks the
consume loop and triggers arriving mid-wake queue in the stream (the
transport's bounded queue drops the oldest backlog under overflow).

History fed to the gate is the runner's rolling per-channel history. On each
transport connection, configured channels are backfilled through the shared
transport's `read_history` tool (newest-first from Discord, reversed to
oldest-first before gating). If `NUNCHI_RUNNER_CHANNELS` / `channels` is empty
(`watch all`), startup backfill is skipped because there is no finite channel
list to fetch.

The hook reuses the Claude Code hook's env names for the shared knobs
(`NUNCHI_HOOK_AGENT_ID`, `NUNCHI_HOOK_MENTION_ID`, `NUNCHI_HOOK_ALIASES`,
`NUNCHI_HOOK_PEER_BOTS`, `NUNCHI_HOOK_HISTORY_WINDOW`, `NUNCHI_HOOK_TIMEOUT`,
`NUNCHI_HOOK_TOOL_PATTERN`) plus `NUNCHI_CHANNEL_BIN` and
`NUNCHI_RUNNER_LOG`. The outbound send gate defaults
`NUNCHI_HOOK_FAIL_POLICY=closed`; the inbound prompt gate is fail-open for
operator safety. The same mention-token warning applies:
`NUNCHI_HOOK_MENTION_ID` is the snowflake, display names go in
`NUNCHI_HOOK_ALIASES`.

## Receipts

Runner receipts write one JSONL line per event: `ts`, `channel`, `message_id`, `author`,
`verdict`, `confidences` (when the gate returned them), `action`
(`pass-suppressed` | `wake-ok` | `wake-error` | `no-wake-gate-error` |
`skipped-self` | `skipped-channel` | `skipped-empty`), `wake_exit` when a
wake ran, `history_len`. Never message content, tokens, or keys.

Hook receipts share the same file. Inbound prompt records use
`"direction": "hook-inbound"` with `block-pass`, `allow-speak`, `allow-ack`,
`allow-ask`, or `allow-gate-error`. Outbound send records use
`"direction": "hook-outbound"` with `deny-untriggered`, `deny-pass`,
`allow-speak`, `allow-ack`, `allow-ask`, `deny-gate-error`, or
`allow-gate-error`.
