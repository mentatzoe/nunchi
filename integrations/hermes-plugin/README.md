# Nunchi for Hermes: the `nunchi-room` plugin

**Status: implemented, verified offline against Hermes main `a50406d9` (#94
step 9e); not yet run live on Telegram or Discord.** The turn conformance kit
and `tests/v2/test_hermes_plugin.py` run the plugin inside a real Hermes
gateway, loaded from a throwaway `HERMES_HOME` through Hermes's own plugin
discovery, with only the model scripted. It replaces the older Hermes
integration under `integrations/hermes/`, which stays until this plugin has
passed live checks and Zoe decides to remove it.

The plugin uses Hermes's public plugin surface only (hooks, tools,
`ctx.inject_message`, `ctx.platform_actions`). It patches nothing.
`hermes plugins validate` passes it, including the "no core override" check,
and it also runs under `plugins.isolation: host`.

## What it does

Nunchi reads the room for the agent in one group chat. The plugin is the
harness-hosted, consume-and-start shape with final-answer posting
([`docs/harness-guide.md`](../../docs/harness-guide.md)):

| Step | Hermes surface | What happens |
|---|---|---|
| Ingress | `post_gateway_admission` | Every message in the bound chat goes to the room; Hermes runs no turn of its own on it. Messages in other chats are left to Hermes. |
| Start | `ctx.inject_message(origin=...)` | When the library gives the agent a turn, the plugin injects the turn's text into the chat as its own message. |
| Bind | `pre_llm_call` | The run whose message carries the turn's wake marker is bound to the turn. |
| Steering | `transform_tool_result` | What others posted meanwhile is added to every tool result in a bound run. |
| Room view, reactions | `room_context`, `room_react` tools | Forwarded to the library. Reactions go through `ctx.platform_actions`. |
| Finish | `transform_llm_output` | The final answer goes to the library. Hermes delivers it, or `[SILENT]`. When others posted meanwhile, the draft is silenced and a fresh run starts with it. |
| Thinking | `post_api_request` | Hermes strips `<thinking>` before the output hook; the plugin hands the library the model's raw answer, so the agent's thinking is kept as its reason and never posted. |
| End | `on_session_end` | The run's end is reported. |

## Install

1. Install Nunchi into Hermes's Python environment, from the same commit as
   the plugin directory (Nunchi is not on PyPI, and Hermes does not manage
   direct-URL dependencies):

   ```sh
   uv pip install --python <hermes venv>/bin/python 'nunchi @ git+https://github.com/mentatzoe/nunchi@<commit>'
   ```

2. Install the plugin directory, pinned to the same commit:

   ```sh
   hermes plugins install mentatzoe/nunchi/src/nunchi/integrations/hermes_plugin --ref <commit>
   hermes plugins enable nunchi-room
   ```

   Enabling asks for `gateway.platform_actions`, which reactions need. Without
   it the agent is simply not offered reactions.

3. Write the participant's Nunchi config (JSON) and point the plugin at it.

## Config

The shared sections ([harness guide](../../docs/harness-guide.md), step 1),
plus a `hermes` section:

```json
{
  "schema_version": 2,
  "binding": {
    "participant_id": "vigil",
    "actor_id": "telegram:user:<the bot's user id>",
    "platform": "telegram",
    "room_id": "<chat id>",
    "continuity_scope_id": "telegram:<chat id>",
    "names": ["Vigil"]
  },
  "profile": {"path": "/etc/nunchi/vigil.profile.json", "sha256": "…"},
  "attention": {"policy": {"preattention_enabled": true}, "model": {"kind": "…"}},
  "limits": {},
  "state_directory": "/var/lib/nunchi/vigil",
  "hermes": {
    "platform": "telegram",
    "chat_id": "<chat id>",
    "thread_id": null,
    "turn_user_id": "nunchi-turns",
    "turn_user_name": "Nunchi",
    "withheld_env": ["TELEGRAM_BOT_TOKEN"],
    "start_timeout_seconds": 120
  }
}
```

- Room events use the ids `<platform>:message:<message id>` and
  `<platform>:user:<user id>`.
- `turn_user_id` is the identity Hermes runs the injected turns as.
- `withheld_env` names environment variables whose values the agent must
  never post (default: the platform bot tokens). Telegram and Discord token
  shapes are refused too.

## Hermes setup the room needs

In the profile's `config.yaml`:

```yaml
plugins:
  enabled: [nunchi-room]
  entries:
    nunchi-room:
      allow_gateway_injection: true        # the plugin starts the agent's turns
      settings:
        config_path: /etc/nunchi/vigil.json
display:
  platforms:
    telegram:                              # the room's platform
      streaming: false                     # a streamed draft is visible before Nunchi decides
      tool_progress: "off"
      interim_assistant_messages: false    # see below
      long_running_notifications: false
```

- **`interim_assistant_messages: false` is required.** By default Hermes posts
  text the model writes beside a tool call straight to the chat, before any
  final answer. That text never reaches Nunchi: no look-again, no secret
  guard, no one-action rule. No plugin hook can stop it (checked, see the
  tests).
- `turn_user_id` must be one of the platform's allowed users (for example
  `TELEGRAM_ALLOWED_USERS`). Otherwise Hermes accepts the injection and then
  drops it; the plugin ends that turn as a failure after
  `start_timeout_seconds`.
- Keep Hermes's default per-user group sessions (`group_sessions_per_user`).
  With shared group sessions, a message that arrives during a turn skips the
  admission hook ([harness contract](../../docs/harness-contract.md), Runtime
  checks).
- `plugins.hook_callback_timeout` (default 30 s) must stay above the
  plugin's wait for the library's commit (20 s). If the output hook times
  out, Hermes delivers the raw draft.
- Hermes's tool search (default on) hides plugin tools behind `tool_search` and
  `tool_call`. The room tools work through that bridge;
  `tools.tool_search.enabled: off` shows them to the model directly.

## Known gaps

- **The agent's own message is missing from its memory.** Hermes drops the
  bot's own messages before any plugin hook, and the library does not yet
  record a harness-delivered move by its text and time. In the agent's next
  turn its own reply is not in the room, `memory.own_moves` is empty, and the
  question it answered shows no responses. Tracked by an expected-failure
  test.
- **No delivered message id.** Hermes reports none to plugins.
- **Thin ingress.** Hermes's admission payload carries no mentions, reply
  target, timestamp, or bot flag. The plugin delivers empty mentions and actor
  kind `unknown`.
- **No interrupt.** Hermes gives plugins no way to stop a run. A cancelled
  turn's answer is silenced; tools it already ran stay run.
- **Reactions** are add-only (Hermes's `platform_actions`) and were checked up
  to Hermes's Telegram verb with a recording adapter, not against Telegram.
- **No room history after a restart** beyond Nunchi's own log.
