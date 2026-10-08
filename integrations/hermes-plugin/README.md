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
| Message facts | `pre_gateway_dispatch` | For each message in the bound chat, the plugin notes what the admission payload leaves out: the message it replies to, when it was sent, who it mentions (Hermes takes the bot's own Discord mention out of the text), whether its author is a bot, and whether the platform says it was meant for the bot. Dispatch goes on unchanged. |
| Ingress | `post_gateway_admission` | Every message in the bound chat goes to the room, with those facts; Hermes runs no turn of its own on it. Messages in other chats are left to Hermes. |
| Start | `ctx.inject_message(origin=...)` | When the library gives the agent a turn, the plugin injects the turn's text into the chat as its own message. |
| Bind | `pre_llm_call` | The run whose message carries the turn's wake marker is bound to the turn. |
| Steering | `transform_tool_result` | What others posted meanwhile is added to every tool result in a bound run. |
| Room view, reactions | `room_context`, `room_react` tools | Forwarded to the library. Reactions go through `ctx.platform_actions`. |
| What the model wrote | `post_api_request` | Each model response's text and reasoning go to the library (`model_text`). Only the model's own words can be the agent's post. Text Hermes puts in place of a missing answer, such as `(empty)` or "I reached the iteration limit and couldn't generate a summary.", fails the turn: it is never posted or remembered. |
| Finish | `transform_llm_output` | The final answer goes to the library. Hermes delivers it, or `[SILENT]`. Hermes's other silent answers (`SILENT`, `NO_REPLY`, `NO REPLY` and the zh forms) and a marker in markdown are the agent's silence too, remembered as silence. When others posted meanwhile, the draft is silenced and a fresh run starts with it. If the hook fails, the turn fails and Hermes gets `[SILENT]`: Hermes posts the raw draft for a hook that raised. |
| Thinking | `post_api_request` | Hermes strips `<thinking>` before the output hook; the plugin hands the library the model's raw answer, so the agent's thinking is kept as its reason and never posted. |
| End | `on_session_end` | The run's end is reported. |
| Provider failure | `api_request_error`, `pre_api_request` | When the provider refuses for good, or Hermes's retries run out, Hermes ends the run without an end hook. Unless Hermes starts another model request within 5 s (a fallback provider, a rotated credential), the plugin ends the turn as a failure, so the room's next moment is not held up. |

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

- `attention.model` is any configured attention route, or Hermes's own
  model: `{"kind": "hermes-host", "provider": "…", "model": "…"}`. Hermes
  must allow the plugin that provider and model under
  `plugins.entries.nunchi-room.llm` (`allow_provider_override`,
  `allow_model_override`, `allowed_providers`, `allowed_models`); if it
  refuses, the judgment fails with that instruction and no other model is
  used.
- Room events use the ids `<platform>:message:<message id>` and
  `<platform>:user:<user id>`.
- `turn_user_id` is the identity Hermes runs the injected turns as.
- `withheld_env` names environment variables whose values the agent must
  never post (default: the platform bot tokens). The value of every other
  variable the config names in a `*_env` key, such as an attention route's
  `api_key_env`, is withheld too. Telegram, Discord and Slack token shapes
  are refused.
- The keys a keyed attention route reads (`api_key_env`) and the platform
  tokens live in Hermes's own process: the plugin runs there and cannot
  keep them out. The guard keeps their values out of the room. Prefer the
  `hermes-host` attention model, which needs no key of Nunchi's own.

## Hermes setup the room needs

People in the room should see only what the agent chose to do. By default
Hermes also posts and shows things of its own, which the library never
committed and the agent never remembers. These settings turn them off.

Give each Nunchi room its own Hermes profile and its own bot. Several of
these settings apply to the whole profile or the whole bot, not to one chat:
the flags at the top of `display`, `typing_indicator`, `reactions` and
`agent.disabled_toolsets`. On a profile or bot you also use elsewhere, they
change those chats too.

In the room's profile `config.yaml`:

```yaml
plugins:
  enabled: [nunchi-room]
  entries:
    nunchi-room:
      allow_gateway_injection: true        # the plugin starts the agent's turns
      settings:
        config_path: /etc/nunchi/vigil.json
display:
  file_mutation_verifier: false            # top level only, for the whole profile
  turn_completion_explainer: false
  busy_ack_enabled: false
  platforms:
    telegram:                              # the room's platform
      streaming: false
      tool_progress: "off"
      interim_assistant_messages: false
      long_running_notifications: false
      suppress_warning_notifications: true
      show_reasoning: false
telegram:                                  # the room's bot
  typing_indicator: false
  reactions: false
agent:
  disabled_toolsets: [clarify, cronjob]
```

For a Discord room, put the same keys under `display.platforms.discord` and
`discord:`, and leave the `DISCORD_REACTIONS` environment variable unset or
false: it wins over the config.

Why each key. The conformance kit and `tests/v2/test_hermes_plugin.py` run
Hermes with these settings, and a test checks that this block matches them.

| Key | Without it |
|---|---|
| `allow_gateway_injection: true` | The plugin cannot start the agent's turns. |
| `display.file_mutation_verifier: false` | After a failed `write_file` or `patch`, Hermes appends a footer with local file paths to the agent's answer, or to its silence, after the library committed it. Hermes reads this key only at the top of `display`. |
| `display.turn_completion_explainer: false` | When a run ends abnormally, Hermes adds "⚠️ No reply: …" to a short answer, `[SILENT]` included. Top level only. |
| `display.busy_ack_enabled: false` | When someone posts twice quickly, Hermes answers "⚡ Interrupting current task…". Checked with a probe; the kit does not wire Hermes's busy handler. |
| `streaming: false` | A streamed draft is visible before the library decides. |
| `tool_progress: "off"` | Hermes posts a line for each tool call. |
| **`interim_assistant_messages: false`** (required) | Hermes posts text the model writes beside a tool call straight to the chat, before any final answer. That text never reaches Nunchi: no look-again, no secret guard, no one-action rule. No plugin hook can stop it. |
| `long_running_notifications: false` | Hermes posts "still working" notes. |
| `suppress_warning_notifications: true` | Hermes posts its retry and iteration-budget status lines, and "❌ … rejected the request" when the provider refuses. |
| `show_reasoning: false` | Hermes puts the model's reasoning before the answer. Off by default; pinned because a top-level `display.show_reasoning` would turn it on for every platform (from Hermes's source). |
| `typing_indicator: false` | A typing bubble shows on each person's message and through every turn, even one that ends in silence, so people wait for an answer that never comes. For the whole bot. |
| `reactions: false` | On Discord (on by default), every message the plugin takes in gets 👀 and then ✅, a nod on every message. Telegram's default is already off. For the whole bot. |
| `agent.disabled_toolsets: [clarify, cronjob]` | `clarify` posts a numbered question form that nobody in the room is meant to answer; `cronjob` schedules a post into the room that arrives later without reading the room. For the whole profile. |

More setup:

- `turn_user_id` must be one of the platform's allowed users (for example
  `TELEGRAM_ALLOWED_USERS`). Otherwise Hermes accepts the injection and then
  drops it; Nunchi ends that turn as a failure when its run has not started
  within `start_timeout_seconds`.
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

- **No delivered message id.** Hermes reports none to plugins, and drops the
  bot's own messages before any plugin hook. The library records each message
  it committed for Hermes in the room log itself, with an id of its own, as a
  reply to the message the turn was about. So memory, threads and the room's
  pace see it, but nothing can target it on the platform.
- **Mentions under `plugins.isolation: host`.** Mentions and the bot flag come
  from the platform's own message object, which does not cross into the plugin
  host. There a message reads as mentioning nobody, and on Discord Hermes has
  taken the bot's own mention out of its text, so the room cannot tell the
  agent was named. Run the plugin in-process (the default) for mentions. The
  reply target and whether the platform said the message was meant for the bot
  still cross; the time does not, so the room uses the time it saw the
  message. Tracked on [#135](https://github.com/mentatzoe/nunchi/issues/135).
- **Telegram mentions by @username** carry no user id, so only a mention that
  names a user (Telegram's `text_mention`) counts. A Discord mention or a
  Telegram text mention of the bot addresses the agent when the binding's
  `actor_id` is `<platform>:user:<the bot's user id>`.
- **Hermes's failed-turn reply.** When a run fails (the provider refuses or
  its retries run out, a tool result is left pending, repeated errors),
  Hermes posts its own notice, such as "…Your request was not processed.
  Send it again if you still want me to carry it out." When the output hook
  ran, `[SILENT]` comes before it. No hook or setting stops this: Hermes
  honors silence only for runs that did not fail
  (`gateway/response_filters.py`). The library ends the turn as a failure
  and remembers no move, so the agent does not know the room saw the notice.
  Offering the moment again after a failure is open (decision D5).
- **Approval prompts.** When the agent runs a command Hermes wants approved
  (`terminal`, `code_execution`), Hermes asks in the room and waits for
  `/approve`. No setting removes the prompt safely: `approvals.mode: off`
  approves everything. To keep prompts out of the room, also disable the
  `terminal` and `code_execution` toolsets, and lose those tools.
- **`hermes send`.** With the `terminal` or `code_execution` tool, the agent
  can run `hermes send` and post to the room without Nunchi. Disabling those
  toolsets closes it.
- **Built-in slash commands.** Hermes answers `/help`, `/status` and its
  other commands in the room before the plugin sees the message. Nunchi sees
  neither the command nor the reply, so the agent's memory misses both. No
  setting turns built-in commands off. Later work (decision D4).
- **No interrupt.** Hermes gives plugins no way to stop a run. Nunchi closes
  a cancelled turn, so its answer is silenced; tools it already ran stay run.
- **Reactions** are add-only (Hermes's `platform_actions`) and were checked up
  to Hermes's Telegram verb with a recording adapter, not against Telegram.
- **No room history after a restart** beyond Nunchi's own log.
- **Hermes's process is not private.** The plugin runs inside Hermes's own
  process, and Nunchi leaves a stock harness's process alone: it does not
  call `nunchi.private_process.keep_private`, as its own runners do. Another
  process of the same OS user can read Hermes's starting environment and
  memory, including any key Nunchi's config names there. The plugin has no
  probe to report this. With the `hermes-host` attention model, Nunchi adds
  no key of its own to that process.
