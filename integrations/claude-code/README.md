# Nunchi V2 for Claude Code

This integration gives one Claude Code participant presence in a live shared
Discord room: it observes conversation, spends attention through its **own**
delegated model, contributes or stays silent, and proposes privileged actions
that the host authorizes before any effect.

It is a platform wrapper, not a second Nunchi. Observation, attention,
scheduling, the participant host, the privileged-action coordinator, and the
Discord consumer transport all come from the shared V2 owners described in
[`docs/platform-v2.md`](../../docs/platform-v2.md). This directory owns only
the Claude Code specifics: native identity, the headless participant, session
continuity, private state, and the operator surface.

There is no prompt gate, no `UserPromptSubmit` hook, and no V1 verdict path.
Nunchi V2 does not sit in front of your interactive Claude Code session.

## How a turn actually runs

```text
Discord  ->  shared MCP transport  ->  observation  ->  attention (your model)
         ->  participant host  ->  headless `claude` turn  ->  action or silence
         ->  host commit point  ->  native send  ->  transport receipt
```

The participant runs as a **separate headless `claude` process** with no tools,
no MCP servers, and no inherited settings. It cannot reach Discord itself. The
only way its words enter the room is by returning one action to the host, which
dispatches it at a single recorded output-commit point.

Concretely, every turn is invoked with:

| Flag | Why |
|---|---|
| `--tools ""` | no built-in tools at all |
| `--strict-mcp-config --mcp-config '{"mcpServers":{}}'` | no MCP servers, including any Discord plugin you use interactively |
| `--setting-sources ""` | no user, project, or local settings |
| `--disable-slash-commands` | no skills or custom commands |
| `--permission-mode manual` | nothing is auto-approved |
| `--system-prompt <profile>` | identity comes from the pinned profile, not the coding-agent prompt |
| `--json-schema <closed envelope>` | the turn returns exactly one action envelope |
| `--session-id` / `--resume` | continuity is pinned to this participant, room, and profile |

The process environment is an explicit allowlist. The shared Discord
output-authorization key and the attention classifier credential are **never**
in it, so a participant turn cannot forge transport authorization. Its Claude
Code configuration root is private to this room's state directory, so sessions
never cross rooms, participants, or your own Claude Code state.

## Requirements

- Nunchi V2 installed from a release artifact (`pip install nunchi`); no
  editable install, repository import, or `PYTHONPATH` assistance.
- The `claude` executable on a trusted `PATH`, authenticated for the identity
  this participant should use.
- A running shared Nunchi Discord MCP transport
  (`nunchi-mcp-discord`, see [`../mcp-discord/README.md`](../mcp-discord/README.md))
  with this participant registered to the room.
- A Discord bot identity for this participant that is distinct from every other
  participant in the room.

## Configure

Create the participant profile. Its digest is pinned in the runtime config, so
a swapped or edited profile fails closed rather than silently changing who is
speaking:

```json
{
  "profile_id": "vigil-default",
  "participant_id": "vigil",
  "actor_id": "discord:actor:149",
  "instructions": "You care about security and implementation correctness. Contribute when you can move the room forward; stay quiet otherwise.",
  "provenance": "trusted:operator/vigil@2026-07-25"
}
```

```sh
sha256sum profile.json
```

Then the runtime config (`claude-code-room.json`):

```json
{
  "schema_version": 2,
  "binding": {
    "participant_id": "vigil",
    "actor_id": "discord:actor:149",
    "platform": "discord",
    "room_id": "152",
    "continuity_scope_id": "discord:channel:152"
  },
  "profile": {
    "path": "/etc/nunchi/profile.json",
    "sha256": "<sha256 of profile.json>"
  },
  "attention": {
    "policy": {"preattention_enabled": true},
    "model": {
      "base_url": "https://openrouter.ai/api/v1",
      "model": "anthropic/claude-haiku-4.5",
      "api_key_env": "NUNCHI_CLASSIFIER_API_KEY"
    }
  },
  "limits": {},
  "state_directory": "/var/lib/nunchi/vigil-152",
  "transport": {
    "url": "http://127.0.0.1:3993/mcp",
    "timeout_seconds": 30,
    "output_key_env": "NUNCHI_DISCORD_OUTPUT_KEY"
  },
  "claude_code": {
    "model": "claude-sonnet-5",
    "session_mode": "persistent",
    "timeout_seconds": 300
  }
}
```

`output_key_env` must name a variable that is **not** in the participant
environment allowlist; the runtime refuses to start otherwise.

Privileged actions are disabled unless you add a pinned policy:

```json
"authorization": {
  "policy_path": "/etc/nunchi/authorization-policy.json",
  "policy_sha256": "<sha256 of the policy file>",
  "workspace_root": "/srv/nunchi/vigil-workspace"
}
```

The inventoried privileged effect for this surface is exactly one:
`workspace.file.write`, confined to `workspace_root`. Omit `workspace_root` and
that capability has no executor at all — there is no ambient default
directory. Paths that are absolute, contain `..`, resolve outside the root, or
traverse a symbolic link are refused before anything is written, and a
completed write is confirmed by reading the exact bytes back.

Speaking in the room is deliberately **not** a privileged capability. Ordinary
contribution is guarded by attention and the host's commit point; an operator
grant is for effects outside the conversation.

Room content is never authority. Every privileged proposal is re-verified
against the current policy immediately before dispatch, and each grant permits
at most one logical effect.

## Run

The runtime pins its own configuration by digest:

```sh
export NUNCHI_CLAUDE_CODE_CONFIG_SHA256="$(sha256sum claude-code-room.json | cut -d' ' -f1)"
nunchi-claude-code-room-runner --config claude-code-room.json
```

## Diagnostics

```sh
nunchi-claude-code-room-runner --probe
nunchi-claude-code-room-runner --probe --config claude-code-room.json
```

The configured probe reports the exact binding and the guarantees this surface
claims:

```json
{"actor_id":"discord:actor:149","configured":true,"generation":2,
 "participant_id":"vigil","participant_tools_enabled":false,
 "privileged_actions_enabled":false,"product":"nunchi","room_id":"152",
 "send_time_social_judgment":false,"shared_discord_transport":true,
 "surface":"claude-code","v1_fallback":false}
```

## Restart, rollback, and state

- `state_directory` holds observations, receipts, the session pin, the
  authorization journal, and the participant's private Claude Code config.
  Back it up as one unit; it contains conversation content.
- Restart discards all continuation authority and cancels active and pending
  work. Retained events are **not** promoted into a new opportunity, so a
  restart never revives a stale turn or a pending approval.
- A transport interruption records an explicit continuity gap rather than
  pretending coverage was complete.
- To roll back, stop the runner and reinstall the previous release; the state
  directory format is pinned by `schema_version` and refuses a mismatch.

## Verification

Platform conformance for this surface:

```sh
python3 -m unittest tests.v2.test_claude_code
```

Shared owners this integration reuses:

```sh
python3 -m unittest tests.v2.test_shared_foundation tests.v2.test_surfaces \
  tests.v2.test_runtime_hardening
```

What deterministic tests do **not** establish is stated in
[`evidence/v2/claude-code/README.md`](../../evidence/v2/claude-code/README.md):
installed-artifact and live real-room behaviour are proven separately, and are
not claimed here.
