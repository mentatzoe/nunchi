# Claude Code in a Nunchi room

Your own Claude Code agent takes part in one shared room. Nunchi watches
every room event and decides when the agent should spend attention. When it
wakes the agent, the agent sees the bounded room facts and decides for itself
whether to post, react, or stay silent. Everything it posts passes Nunchi's one
output commit point.

The agent keeps your Claude Code configuration: model, `CLAUDE.md` and memory,
tools, MCP servers, plugins, skills, and permission rules.

**Status: merged, unverified.** Source, deterministic tests, and the mod's
own `claude plugin` checks pass. It has not run in a real room
([#39](https://github.com/mentatzoe/nunchi/issues/39)). Install and
supervision are [#58](https://github.com/mentatzoe/nunchi/issues/58); rooms
beyond Discord are [#57](https://github.com/mentatzoe/nunchi/issues/57). The
design is [#43](https://github.com/mentatzoe/nunchi/issues/43).

## How it works

Three parts:

- **The gate**, `nunchi-claude-code-room-runner`: one Python process per room.
  It owns the room transport (the shared Discord MCP server), observation,
  attention, scheduling, authority, and receipts.
- **A dedicated Claude Code session** per room, which the gate starts on the
  first wake. It is not your everyday terminal session. The gate runs
  `claude -p --input-format stream-json --output-format stream-json --verbose
  --plugin-dir <mod>` in the configured working directory and writes each wake
  into it as one user turn.
- **The Nunchi mod**, shipped inside the Python package at
  `nunchi/integrations/claude_code_mod`. It runs inside that session,
  registers the room tools, binds each model turn to the wake that started
  it, and forwards room tool calls to the gate over a private Unix socket.
  In any session the gate did not start, it does nothing.

One wake, step by step:

1. A room event arrives. Attention decides SUPPRESS, WAKE, or DEFER. A
   judgment that leans to a "mhm" is DEFER: the agent gets the turn and
   nods itself if it wants to.
2. On a wake, the gate writes one turn into the session: a wake marker, the
   participant prompt with your profile's instructions, and the room facts.
3. The agent may call `mcp__nunchi__room_context` for more history. To take
   part it calls `mcp__nunchi__room_send` (a message, or a reply) or
   `mcp__nunchi__room_react` once. `mcp__nunchi__room_propose` exists only
   when privileged actions are configured.
4. The gate hands that one action to the shared host. The host commits it and
   the result goes back to the tool call, so the agent knows what happened.
5. The agent's own reply text never reaches the room.

How a turn is recorded:

| The turn | Recorded as |
|---|---|
| ends with a room action | the transport's result (`sent`, `failed`, `unknown`) |
| ends normally without one, and the mod bound it | silence |
| was never bound by the mod (mod missing or disabled) | failure, never silence |
| ends in an error or refusal, or the session exits | failure, never silence |
| is cancelled (gap, restart, deadline) | interrupted; closed work |

Wakes go one at a time. The next wake waits until the previous turn ends,
because prompts written during a running turn would merge into it.

## Native tools and permissions

Native tools follow your Claude Code permission rules. Nobody is present to
answer a permission prompt in this headless session, so a tool call that
would ask is denied. Allow what the agent should be able to do in your Claude
Code settings. `disallowed_tools` adds deny rules for this session only.

Room tools never prompt: the mod answers them itself, and if it fails the
call errors. Subagents cannot act in the room.

## Secrets

- Nunchi's secrets are not in the session's environment. The gate removes the
  transport output key, every `*_env` variable named in the attention model
  config, every name in `withhold_env`, and every `NUNCHI_*` variable.
- By default the session's Read and Edit tools are denied on Nunchi's state
  directory (`protect_nunchi_files`), which holds the journals and receipts.
  The runner config holds no secret values, and editing it breaks its pin, so
  the gate refuses to restart rather than run changed settings. Deny rules
  are not a sandbox: Bash can still read any file your OS user can read.
- The gate refuses a room action that contains a withheld secret or a
  bot-token-shaped string. The agent is told nothing was posted.
- For stronger isolation, run the gate and its session as a separate OS user.

## Configuration

The runner reads a pinned JSON config (see [`docs/INSTALL.md`](../../docs/INSTALL.md)
for the shared fields). Its `claude_code` block:

| Field | Default | Meaning |
|---|---|---|
| `executable` | `claude` on `PATH` | absolute path to Claude Code 2.1.287 or later |
| `working_directory` | `<state_directory>-workspace`, beside the state directory | where the session runs; its `CLAUDE.md` and project settings apply. Must be outside the state directory while `protect_nunchi_files` is on |
| `model` | your Claude Code default | passed as `--model` |
| `timeout_seconds` | `300` | budget for one participant turn |
| `session_mode` | `persistent` | `persistent` resumes the same session after a restart; `fresh` starts a new one |
| `disallowed_tools` | `[]` | extra deny rules for this session |
| `protect_nunchi_files` | `true` | deny Read and Edit on Nunchi's state directory |
| `withhold_env` | `[]` | more variable names to keep out of the session |

```sh
nunchi-claude-code-room-runner --config /srv/nunchi/claude-code.json --probe
NUNCHI_CLAUDE_CODE_CONFIG_SHA256=<64 hex> \
  nunchi-claude-code-room-runner --config /srv/nunchi/claude-code.json
```

The probe reports the binding, the Claude Code version found, the mod version,
the room tools, and the deny rules. The runner refuses to start on Claude Code
older than 2.1.287. Starting Claude Code with `--tools ""`, `--safe-mode`, or
`--bare` would disable mods; the gate passes none of them.

[`docs/claude-code-live-run.md`](../../docs/claude-code-live-run.md) is the
procedure for a live run.

## Limits

- Discord only, through the shared Discord MCP transport (#57).
- No installer or service supervision yet (#58), and no live proof (#39).
- The attention model needs an OpenAI-compatible endpoint. Running attention
  on your Claude plan through the mod is not built.
- One room action per opportunity.
- A turn that keeps working after it acts delays the next wake.
- A room tool waits at most 25 seconds for the room's answer, because the
  mod's HTTP calls are capped at 30 seconds. After that the agent is told the
  action is unconfirmed and must not repeat it.
- Claude Code still labels the mods API early access (2.1.289).

There is no V1 verdict path here: no prompt hook, no transport patch, and no
send-time gate.

## Checks

```sh
python3 -m unittest tests.v2.test_claude_code tests.v2.test_participant_tool_turn
claude plugin validate --strict src/nunchi/integrations/claude_code_mod
claude plugin test src/nunchi/integrations/claude_code_mod
```

CI runs all three; the last two run against the pinned Claude Code version.
