# Nunchi for Codex: through `codex app-server`

**Status: implemented, verified offline against Codex CLI 0.160.1 (#94 step
9e); a live runner, `nunchi-codex-app-server-runner`, but no live room yet.** The turn conformance kit and
`tests/v2/test_codex_app_server.py` run the integration against a real
`codex app-server` from a clean, pinned npm install, with a throwaway `HOME`,
`CODEX_HOME` and `TMPDIR`, and only the model scripted (a local Responses API
endpoint configured as the throwaway user's model provider). It is meant to
replace the older Codex integration under `integrations/codex/`, which runs
Codex with its tools turned off; that one stays until this one has passed
live checks.

The integration uses the app-server's public JSON-RPC protocol only. Nothing
in Codex is patched, and the user's Codex configuration is never written.

## What it does

Library-hosted, tool posting ([`docs/harness-guide.md`](../../docs/harness-guide.md)):
Nunchi owns the room connection and starts each of the agent's turns; the
agent acts in the room through room tools.

| Step | Codex surface | What happens |
|---|---|---|
| Thread | `thread/start` (or `thread/resume`) with `cwd` and `config` | One thread per participant, with the user's own model, sandbox, approvals, instructions, MCP servers and skills. The thread's own `config` adds the room's MCP server and the project's trust level. |
| Start | `turn/start` | The turn's text is the input. |
| Bind | `turn/start`'s answer | The run is bound to the wake when Codex answers with its turn id and the thread's room server has reported `ready`. The wake id never reaches the agent. |
| Room tools | `mcp_servers.nunchi_room` in the thread's `config` | A stdio MCP server (`mcp_bridge.py`) forwards each call to the library over a private socket, with the Codex turn id from the call's `_meta`. The model sees the tools as `room_send`, `room_react` and `room_context` in the `mcp__nunchi_room` namespace. |
| Steering | the room tool's result; `turn/steer` | The room's news goes with every room tool result, and after any other tool call (commands, file changes, the user's MCP tools) it goes to the running turn with `turn/steer`. |
| End | `turn/completed` | `completed` ends the turn; `interrupted` and `failed` end it as a failure. A turn that ends bound and without a room action is silence, and the agent's last message in the run is its reason, never posted. |
| Cancel | `turn/interrupt` | The library cancels; the run is interrupted. |
| Approvals | `item/*/requestApproval`, `mcpServer/elicitation/request` | Declined: nobody is at the terminal. |

Why the room tools go through the library's local protocol
(`nunchi.turn_server`) rather than an MCP server inside Nunchi's process:

- Codex speaks MCP to a process it starts; the bridge is the smallest such
  process, imports only the standard library, and holds no turn rules.
- The socket lives in a private directory (`0700`), so no other local user can
  reach it; a localhost HTTP server would be reachable by every local user and
  rest on a token alone.
- The protocol is the one the Claude Code mod already uses, so every harness
  reaches its turn through the same interface. The socket offers only attach,
  call and after-tool; the integration binds and ends turns itself.

## Config

The shared sections ([harness guide](../../docs/harness-guide.md), step 1),
plus a `codex` section:

```json
"codex": {
  "working_directory": "/srv/vigil/work",
  "project_trust_level": "trusted",
  "executable": null,
  "withheld_env": ["DISCORD_BOT_TOKEN"],
  "resume_thread": true,
  "start_timeout_seconds": 120
}
```

- `working_directory` is where the agent works. It must be outside
  `state_directory`.
- `project_trust_level` (`trusted` or `untrusted`) is passed in the thread's
  own config when the user's Codex config has no trust decision for the
  working directory. Without it, starting a thread in a project with a
  writable sandbox writes `trust_level = "trusted"` into the user's
  `config.toml` (contract, gap 5). A trust decision the user already made
  stands. `trusted` is what Codex itself would record; `untrusted` makes Codex
  skip the project's `AGENTS.md` and project config and, unless the user's
  config sets an approval policy, ask before most commands, which a room then
  declines.
- `executable` defaults to `codex` on `PATH`.
- `withheld_env` names variables the agent must never see or post (default:
  `DISCORD_BOT_TOKEN`). Every other variable the config names in a `*_env`
  key, such as the transport's `output_key_env` or an attention route's
  `api_key_env`, is withheld the same way. Every `NUNCHI_*` variable is kept
  out of Codex's environment. The rest of the environment, including the
  agent's own model credentials, is the user's.
- A room action that carries a withheld value, the room tools' launch secret
  or a Discord bot token's shape is refused; Codex sees a tool error and can
  act again without it.
- `resume_thread` keeps the thread id in `state_directory/codex-thread.json`
  and resumes it after Codex or Nunchi restarts.

## Run it

`nunchi-codex-app-server-runner` runs one participant in one Discord room. The
room comes from the shared Discord transport (`nunchi.integrations.discord_room`,
the same connection the Claude Code runtime uses), the library decides each
turn, and Codex takes the turns. Its config adds a `transport` section to the
one above:

```json
"transport": {
  "url": "http://127.0.0.1:3993/mcp",
  "timeout_seconds": 30,
  "output_key_env": "NUNCHI_DISCORD_OUTPUT_KEY"
}
```

The binding's platform must be `discord`, and its `actor_id` the bot's
`discord:actor:<id>`. The output key authorizes this participant's posts on
the transport; it never reaches Codex, and the room refuses any post that
carries it.

```sh
nunchi-codex-app-server-runner --config /srv/nunchi/codex.json --config-sha256 <sha256> --probe
nunchi-codex-app-server-runner --config /srv/nunchi/codex.json --config-sha256 <sha256>
```

`--probe` reports what is configured without connecting, whether the
runner's process is private (`process_private`, below) and that Codex runs
as the runner's OS user (`agent_os_user: "same"`).

In your own code,
`nunchi.integrations.codex_app_server.build_integration(config, transport=transport)`
returns the room settings and the integration. Build the `Room` around
`integration.participant` with the same transport and
`guard=integration.participant.guard`.

- The guard withholds what the transport declares (`withheld_values()` and
  `credential_patterns()`). Without a transport, it refuses the Discord
  token shape.
- A transport's declarations keep its secret out of the room, not out of
  Codex's environment. Name the variable it reads in `withhold` too
  (`build_integration(..., withhold=["MY_PLATFORM_TOKEN"])`).

## Keep the agent's commands in Codex's sandbox

Codex runs as your OS user, the same user as the runner. The runner holds
the transport's output key and the attention model's key; with them, a
process could post to the room without the library.

- On Linux the runner makes its own process private first thing in `main`
  (`nunchi.private_process.keep_private`). From then on another process of
  your user gets `PermissionError` on its `/proc/<pid>/environ` and
  `/proc/<pid>/mem`. `nunchi-mcp-discord` does the same.
- `process_private: true` does not mean the keys are safe from a command
  outside a sandbox. At every start, any process of your user can read the
  keys in the runner's or the transport's starting environment for about a
  tenth of a second (Python's start-up and Nunchi's imports). A command can
  leave a reader running and force a start: a signal needs only the same
  user, so it can kill a supervised runner, and the supervisor starts it
  again. Codex's `workspace-write` or `read-only` sandbox closes this (below).
  Running the agent as its own OS user would close it too; that is not
  supported yet.
- It does not cover other programs started from the shell that exported the
  keys, environment files, a systemd unit's `Environment=` lines, macOS, or
  root either (see
  [the Claude Code README](../claude-code/README.md#nunchis-processes-and-the-agents-bash)).
- The rest is Codex's sandbox. In `$CODEX_HOME/config.toml`:

  ```toml
  sandbox_mode = "workspace-write"   # or "read-only"

  [sandbox_workspace_write]
  network_access = false             # the default
  ```

  With either mode, Codex 0.160.1 on Linux runs each command in its own
  process namespace: the command sees only its sandbox's processes, not the
  runner, the transport or your shell. It can still read every file your
  user can read. With the network off it cannot send what it reads over
  the network, and the room tools' guard refuses Nunchi's keys. The sandbox
  uses bubblewrap and needs user namespaces; where it cannot start one, the
  command fails rather than run unsandboxed.
- `sandbox_mode = "danger-full-access"` runs commands with no sandbox. They
  see every process of your user and can read the starting environment and
  memory of any that is not private, Nunchi's own during start-up included.
  They can read the room tools' launch secret from the room's MCP server,
  read and write every file your user can (Nunchi's state and config,
  environment files), and use the network.
- When Codex reports the thread's sandbox as `dangerFullAccess`, or
  `externalSandbox` (Codex adds none of its own), the runner logs a warning
  and `CodexRoomRunner.status()` reports it (`codex_sandbox`,
  `codex_sandbox_warning`). It still runs: whether to refuse is not decided.

`tests/v2/test_codex_app_server.py` checks both against the pinned Codex:
the warning under `danger-full-access` and none by default, and, under
`danger-full-access`, that a command that scans `/proc` finds no key in a
runtime that has already made itself private, while the turn still posts.
It does not test the start-up window.

## Codex setup the room needs

None in Codex's own config. The integration needs:

- A Codex the app-server protocol of 0.160.1 accepts (`turn/steer` and
  per-thread `config` are stable there). CI pins 0.160.1.
- No MCP server named `nunchi_room` in the user's config. If one disables
  that name, the room tools never reach the agent, and every turn fails.
- The user's login or API key, as for any Codex use. The app-server runs with
  the user's default profile (contract, gap 6: it rejects `--profile`).

What the user's own rules would ask a person about is declined, so a room
agent works within what the rules allow without asking. In particular, Codex
asks before calling an MCP tool that has no read-only annotation, unless the
server sets `default_tools_approval_mode`; such tools of the user's are
declined in a room.

## Known gaps

- **Not run in a live room yet.** The runner is tested against a stub of the
  shared transport, and the integration against a real `codex app-server`;
  the two have not met a real Discord room.
- **Steering after Codex's own tools can come late.** `turn/steer` adds the
  room's news to the run's next model call; if the run ends first, the update
  is lost for that run, though the library already counts it as shown. The
  next turn's catch-up covers it. Room tool results carry the news directly.
- **Nunchi's state is readable.** The agent cannot write to Nunchi's state
  directory under a workspace sandbox, but Codex's sandbox lets it read
  everywhere; the Claude Code integration denies those reads with its
  permission rules.
- **The agent runs as the runner's OS user.** The runner's own process is
  private once it has started, but its start-up, and every other file and
  process of that user, are as open as Codex's sandbox leaves them.
- **The guide in the turn text.** Codex's stable instruction slot
  (`developerInstructions`) would replace the user's own, so the guide goes
  with every turn's text (library gap: one text per turn).

## Test it

```sh
mkdir -p /tmp/codex && npm install --prefix /tmp/codex @openai/codex@0.160.1
export NUNCHI_CODEX_BIN=/tmp/codex/node_modules/.bin/codex
nunchi-turn-conformance --integration reference --integration nunchi.integrations.codex_app_server_conformance
python3 -m unittest tests.v2.test_codex_app_server -v
```

Without `NUNCHI_CODEX_BIN` (or `codex` on `PATH`) the Codex tests skip.
