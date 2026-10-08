# Nunchi for Hermes: the `nunchi-room` plugin

**Status: implemented, verified offline against Hermes main `a50406d9` (#94
step 9e); not yet run live on Telegram or Discord.** The turn conformance kit
and `tests/v2/test_hermes_plugin.py` run the plugin inside a real Hermes
gateway, loaded from a throwaway `HERMES_HOME` through Hermes's own plugin
discovery, with only the model scripted. On Discord they use Hermes's stock
Discord adapter with fake discord.py channels, threads and messages, as
Hermes's own tests do. It replaces the older Hermes
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
| Message facts | `pre_gateway_dispatch` | For each message in the bound chat, the plugin notes what the admission payload leaves out: the message it replies to, when it was sent, who it mentions (Hermes takes the bot's own Discord mention out of the text), whether its author is a bot, and whether the platform says it was meant for the bot. Dispatch goes on unchanged. A message Hermes runs from its busy queue without this hook reaches the room without them; on Discord the plugin reads its time from its id (Known gaps, Quick messages). |
| Ingress | `post_gateway_admission` | Every message Hermes admits in the bound chat goes to the room, with those facts; Hermes runs no turn of its own on it. Threads inside the room are part of it: on Discord the threads under a bound channel, on Telegram the topics of a forum group. Their messages go to the room too, marked with their thread (`thread_root_event_id`). Messages in other chats are left to Hermes. What Hermes drops before this hook never reaches the room (Hermes setup, Known gaps). |
| Start | `ctx.inject_message(origin=...)` | When the library gives the agent a turn, the plugin injects the turn's text into the chat as its own message. |
| Bind | `pre_llm_call` | The run whose message carries the turn's wake marker is bound to the turn. |
| Steering | `transform_tool_result` | What others posted meanwhile is added to every tool result in a bound run. |
| Room view, reactions | `room_context`, `room_react` tools | Forwarded to the library. Reactions go through `ctx.platform_actions`. |
| What the model wrote | `post_api_request`, `pre_api_request` | Each model response's text, and apart its reasoning, go to the library (`model_text`). When the length limit or a dropped stream cuts an answer, Hermes keeps the part it got and asks the model to go on; no `post_api_request` shows that part, so the plugin reports it from `pre_api_request`. Only the model's own words can be the agent's post. Text Hermes puts in place of a missing answer, such as `(empty)` or "I reached the iteration limit and couldn't generate a summary.", fails the turn: it is never posted or remembered, also when the model wrote the word "empty". The summary the model writes at Hermes's iteration limit reaches no hook, so it fails the turn too (Known gaps). |
| Finish | `transform_llm_output` | The final answer goes to the library. Hermes delivers it, or `[SILENT]`. Hermes's other silent answers (`SILENT`, `NO_REPLY`, `NO REPLY` and the zh forms) and a marker in markdown are the agent's silence too, remembered as silence. When others posted meanwhile, the draft is silenced and a fresh run starts with it. If the hook fails, the turn fails and Hermes gets `[SILENT]`: Hermes posts the raw draft for a hook that raised. |
| Thinking | `post_api_request` | Hermes strips `<thinking>` before the output hook; the plugin hands the library the model's raw answer, so the agent's thinking is kept as its reason and never posted. |
| End | `on_session_end` | The run's end is reported. |
| Provider failure | `api_request_error`, `pre_api_request` | When Hermes gives up on a run it ends it without an end hook, so the plugin ends the turn as a failure once Hermes has stopped asking the model. If the provider refused (Hermes marks the error not retryable), Hermes moves to a fallback provider or a rotated credential at once, or gives up: the wait is 5 s. If a retryable error used up Hermes's retries, Hermes may still rebuild its client, or wait in its auto-recovery ladder (on by default: up to 5 cycles of 15 to 60 s, or the provider's Retry-After up to 120 s) and ask again: the wait is 130 s, so an answer after an outage is still posted. Each new model request cancels the wait. |

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
  `<platform>:user:<user id>`. A message in a Discord thread has the thread
  as `thread_root_event_id`: `discord:message:<thread id>`, which is the
  message that started the thread when one did. A message in a Telegram
  forum topic has `telegram:message:<topic id>`, the topic's first message;
  General is the group's main chat.
- On Discord, `chat_id` is the channel's id and `thread_id` is null: the room
  is the channel and every thread under it. To bind one thread only, set both
  to the thread's id.
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
thread_sessions_per_user: true             # top level: one session per person in a thread too
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
  busy_input_mode: interrupt               # Hermes's default, pinned
  platforms:
    telegram:                              # the room's platform
      streaming: false
      tool_progress: "off"
      interim_assistant_messages: false
      long_running_notifications: false
      suppress_warning_notifications: true
      show_reasoning: false
      runtime_footer: {enabled: false}
telegram:                                  # the room's bot
  typing_indicator: false
  reactions: false
agent:
  disabled_toolsets: [clarify, cronjob]
```

Leave the `TELEGRAM_REACTIONS`, `HERMES_TURN_COMPLETION_EXPLAINER` and
`HERMES_FILE_MUTATION_VERIFIER` environment variables unset or false: each
wins over the config. Leave `display.busy_text_mode` and
`HERMES_GATEWAY_BUSY_TEXT_MODE` unset: set to `queue`, that older setting
wins over `busy_input_mode` for text. Discord has its own (On Discord).

Leave `agent.max_turns` unset (Hermes's default: no limit) and the
`HERMES_MAX_ITERATIONS` environment variable unset. At that limit Hermes asks
the model for a summary outside every plugin hook, so the turn fails and the
summary is not posted (Known gaps).

Why each key. The conformance kit and `tests/v2/test_hermes_plugin.py` run
Hermes with these settings, and a test checks that this block matches them.

| Key | Without it |
|---|---|
| `allow_gateway_injection: true` | The plugin cannot start the agent's turns. |
| **`thread_sessions_per_user: true`** (required for threads) | Hermes keeps one session for everyone in a thread: a Discord thread under the room, a Telegram forum topic (in a forum group every message is in one, General included). Its text batching is keyed by session, so two people posting there close together reach the room as one message, under the first person's name and id: the room credits Kim's words to Sam, and Kim's message never exists. Its busy queue is keyed by session too (Known gaps, Quick messages). Top level only, for the whole profile. |
| `display.file_mutation_verifier: false` | After a failed `write_file` or `patch`, Hermes appends a footer with local file paths to the agent's answer, or to its silence, after the library committed it. Hermes reads this key only at the top of `display`. |
| `display.turn_completion_explainer: false` | When a run ends abnormally, Hermes adds "⚠️ No reply: …" to a short answer, `[SILENT]` included. Top level only. |
| `display.busy_ack_enabled: false` | When someone posts twice quickly, Hermes answers "⚡ Interrupting current task…" in the room. Top level only. |
| `display.busy_input_mode: interrupt` | Hermes's default, pinned because it applies to the whole profile; a room member's `/busy queue` rewrites it (Known gaps, Built-in slash commands). Messages a person sends while Hermes still hands their previous one to the plugin (a fraction of a second) wait in Hermes's busy queue, each on its own. With `queue`, Hermes merges them into one, under the last one's id: the earlier ones never exist for the room, and their @mentions (the agent's own too) and reply targets are lost. `steer` acts as `interrupt` here, since no agent runs on a person's message. Top level only. |
| `streaming: false` | A streamed draft is visible before the library decides. |
| `tool_progress: "off"` | Hermes posts a line for each tool call. |
| **`interim_assistant_messages: false`** (required) | Hermes posts text the model writes beside a tool call straight to the chat, before any final answer. That text never reaches Nunchi: no look-again, no secret guard, no one-action rule. No plugin hook can stop it. |
| `long_running_notifications: false` | Hermes posts "still working" notes. |
| `suppress_warning_notifications: true` | Hermes posts its retry and iteration-budget status lines, and "❌ … rejected the request" when the provider refuses. |
| `show_reasoning: false` | Hermes puts the model's reasoning before the answer. Off by default; pinned because a top-level `display.show_reasoning` would turn it on for every platform (from Hermes's source). A room member's `/reasoning show` still turns it on (Known gaps). |
| `runtime_footer: {enabled: false}` | Hermes appends a footer with the model, context use and working directory to every post. Off by default; pinned because it outranks the top-level setting a room member's `/footer on` writes. |
| `typing_indicator: false` | A typing bubble shows on each person's message and through every turn, even one that ends in silence, so people wait for an answer that never comes. For the whole bot. A look-again run still shows typing (Known gaps). |
| `reactions: false` | On Discord (on by default), every message the plugin takes in gets 👀 and then ✅, a nod on every message. Telegram's default is already off. For the whole bot. |
| `agent.disabled_toolsets: [clarify, cronjob]` | `clarify` posts a numbered question form that nobody in the room is meant to answer; `cronjob` schedules a post into the room that arrives later without reading the room. For the whole profile. |

More setup:

- Hermes must allow everyone the room should hear. It drops anyone else
  before any plugin hook, so the room never hears them. On Telegram that is
  `TELEGRAM_ALLOWED_USERS`, which also lets them talk to the bot in a direct
  message, where Hermes answers itself, outside Nunchi; Hermes's group-only
  lists (`TELEGRAM_GROUP_ALLOWED_USERS`, `TELEGRAM_GROUP_ALLOWED_CHATS`) do
  not, but the kit does not test them. On Discord, see On Discord.
- `turn_user_id` must be allowed too: on Telegram in
  `TELEGRAM_ALLOWED_USERS`, on Discord in `GATEWAY_ALLOWED_USERS` (On
  Discord). Otherwise Hermes accepts the injection and then drops it; Nunchi
  ends that turn as a failure when its run has not started within
  `start_timeout_seconds`.
- Keep Hermes's default per-user group sessions (`group_sessions_per_user`).
  With shared group sessions, a message that arrives during a turn skips the
  admission hook ([harness contract](../../docs/harness-contract.md), Runtime
  checks), and people's messages merge as in threads.
- `plugins.hook_callback_timeout` (default 30 s) must stay above the
  plugin's wait for the library's commit (20 s). If the output hook times
  out, Hermes delivers the raw draft.
- Hermes's tool search (default on) hides plugin tools behind `tool_search` and
  `tool_call`. The room tools work through that bridge;
  `tools.tool_search.enabled: off` shows them to the model directly.

### On Discord

For a Discord room, put the same display keys under
`display.platforms.discord`, and give the bot a `discord:` block in place of
the `telegram:` one:

```yaml
discord:                                   # the room's bot
  typing_indicator: false
  reactions: false
  free_response_channels: ["<bound channel id>"]   # the hermes section's chat_id
  free_response_auto_thread: false
```

**Use these keys only with this plugin from the commit that added this
section, or later.** `free_response_channels` also makes every thread under
the channel free-response. An earlier plugin does not hold those threads as
part of the room, so Hermes would answer every message in them itself,
outside Nunchi. Install the plugin and the `nunchi` package from the same
commit (Install, steps 1 and 2).

| Key | Without it |
|---|---|
| **`free_response_channels: ["<bound channel id>"]`** (required) | Hermes's default (`require_mention: true`) drops every message in the channel that does not @mention the bot, before any plugin hook: the room hears only what is said to the agent. Hermes also drops a message that @mentions someone else and not the bot. |
| `free_response_auto_thread: false` | Hermes's default. With `true`, Hermes opens a thread from every message that is not a reply, before the plugin sees it. The message stays in the channel; people see the thread. |

`typing_indicator` and `reactions` are as in the table above; on Discord
both are on by default.

In the profile's `.env`:

```sh
DISCORD_ALLOWED_ROLES=<the room's role id>     # everyone in the room has the role
DISCORD_ALLOWED_USERS=                          # empty, so Hermes refuses their direct messages
GATEWAY_ALLOWED_USERS=nunchi-turns              # the hermes section's turn_user_id
HERMES_DISCORD_TEXT_BATCH_DELAY_SECONDS=0
```

| Variable | Without it |
|---|---|
| **`DISCORD_ALLOWED_ROLES=<the room's role id>`** with `DISCORD_ALLOWED_USERS` empty (required: everyone in the room allowed) | Hermes drops a person it does not allow before any plugin hook, in the channel and in its threads: the room never hears them. With the room's role, Hermes hears everyone who has it, in the channel and its threads, and refuses their direct messages, unless `discord.dm_role_auth_guild` is set. The costs: the bot needs Discord's Server Members privileged intent (Developer Portal, Bot), or Discord refuses its connection; and everyone in the room needs the role. The other ways open direct messages, where Hermes answers itself, outside Nunchi: `DISCORD_ALLOWED_USERS` with everyone's user id opens them to those users, and `*` to anyone who shares a server with the bot (who are then all heard in the room too). With user ids, use ids: at each connect Hermes keeps only entries that are ids or a guild member's username. Whichever way, everyone allowed can run Hermes's commands in the room (Known gaps, `group_allow_admin_from`). |
| **`GATEWAY_ALLOWED_USERS=<turn_user_id>`** (required) | Hermes refuses every turn the library starts, so the agent never speaks, though the room still hears the channel. `turn_user_id` names no Discord user, so it has no role, and at each connect Hermes drops every `DISCORD_ALLOWED_USERS` entry that names no guild member and rewrites the variable. It leaves `GATEWAY_ALLOWED_USERS` alone. |
| `HERMES_DISCORD_TEXT_BATCH_DELAY_SECONDS=0` | Hermes's default (0.6 s, 2 s after a long message) merges a person's messages sent that close together into the first: the room gets one message with the first one's id, mentions and reply target. The later messages' ids, mentions (the agent's own @mention too, which Hermes has already taken out of the text) and reply targets are lost. The cost of `0`: each quick message reaches the room on its own, which the room reads as one moment anyway; and with `allow_bots: mentions`, a tagged bot's follow-up messages that do not mention the bot are dropped. Hermes reads it only from the environment, for the whole profile. |

The kit's Discord lane runs Hermes with this block and these variables (the
room's role, and no user allowlist), and runs Hermes's connect-time
allowlist check; a test checks that they match. Tests pin who the role lets
in and that it keeps direct messages out, and the direct messages a user
list, `*` or `dm_role_auth_guild` opens.

More setup on Discord:

- Do not set `require_mention: false` instead. Hermes then still drops a
  message that @mentions someone else and not the bot, and `auto_thread` (on
  by default) opens a thread from every other message that is not a reply,
  before the plugin sees it. In a free-response channel with
  `free_response_auto_thread: false`, Hermes opens no threads.
- Keep the channel out of `discord.ignored_channels`, and in
  `discord.allowed_channels` when that is set. Hermes drops messages in either
  case before any plugin hook, in the channel and in its threads.
- `DISCORD_ALLOWED_CHANNELS`, `DISCORD_IGNORED_CHANNELS`,
  `DISCORD_FREE_RESPONSE_AUTO_THREAD`, `DISCORD_REACTIONS`,
  `DISCORD_REQUIRE_MENTION` and `DISCORD_AUTO_THREAD` in the profile's `.env`
  (or Hermes's environment) win over `config.yaml`. Leave them unset, or keep
  the two channel lists as above; the last two do not matter for a
  free-response channel. `DISCORD_FREE_RESPONSE_CHANNELS` does not win:
  `free_response_channels` in `config.yaml` replaces it, so list there every
  channel the bot should hear freely.
- If Hermes still opens a thread for a message in the room, the plugin takes
  the message in and logs an error naming these keys. The thread stays.
- Peer agents' bots are not heard by default (Known gaps).

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
  its retries and recovery waits run out, a tool result is left pending,
  repeated errors), Hermes posts its own notice, such as "…Your request was
  not processed. Send it again if you still want me to carry it out." When
  the output hook ran, `[SILENT]` comes before it. No hook or setting stops
  this: Hermes honors silence only for runs that did not fail
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
  setting turns built-in commands off. Room members can also change display
  settings with them, for the whole profile: `/reasoning show` makes Hermes
  post the agent's private thinking with each answer, unchecked by the secret
  guard, and `/busy queue` makes Hermes merge a person's quick messages.
  Until the slash-command work (decision D4), list the room's admins in
  `group_allow_admin_from` under the platform's block (`telegram:`,
  `discord:`) so only they can run commands other than `/help` and
  `/whoami`. A denied command still gets Hermes's reply in the room.
- **The summary at Hermes's iteration limit.** With `agent.max_turns` or
  `HERMES_MAX_ITERATIONS` set, a run that uses up its budget ends with a
  summary Hermes asks the model for outside its model-request hooks. No hook
  shows the plugin that text, so the turn fails and the summary is not
  posted, though the model wrote it. The room settings leave both unset.
  Closing it needs a hook from Hermes (an issue here first, per `AGENTS.md`).
  Likewise, when the length limit cuts the same answer four times, Hermes
  stops asking and keeps what it got: the last part reaches no hook, so the
  turn fails.
- **Typing on a look-again run.** When others posted while the agent
  composed, the fresh run the plugin starts runs as Hermes's queued
  follow-up, which sends typing whatever `typing_indicator` says: one typing
  action on Telegram, typing for the whole run on Discord. No setting stops
  it.
- **No interrupt.** Hermes gives plugins no way to stop a run. Nunchi closes
  a cancelled turn, so its answer is silenced; tools it already ran stay run.
- **Reactions** are add-only (Hermes's `platform_actions`) and were checked up
  to Hermes's Telegram verb with a recording adapter, and through Hermes's
  Discord verb to a fake discord.py message, not against either platform. A
  reaction to a message in a Discord thread goes through the thread; after a
  restart the room's log names the thread. One exception: the first message
  of a Discord forum post, whose id is the thread's own, cannot be reacted to
  after a restart.
- **Answers to a thread land in the main chat.** The room hears a thread
  under the bound Discord channel, or a topic in the bound Telegram group,
  and knows which thread each message is in. But the agent's turns run in
  the main chat, so its answer to a thread message is posted in the channel
  (on Telegram, in General), not in the thread, until the library can place
  an answer in a thread.
- **Messages that name another bot.** Hermes drops a Discord message that
  @mentions another bot and not this one, before any plugin hook, whatever
  the settings. That includes a reply to a peer agent's message: Discord's
  Reply pings the replied-to author by default, which counts as a mention.
  The room never hears a person ask a peer agent by @mention, or answer one
  with Reply, unless they turn the ping off. No setting changes this; it
  needs a hook from Hermes (harness contract, candidate gap 12).
- **A message that is only an @mention of the agent.** Hermes takes the
  bot's own mention out of a Discord message and drops a message left
  empty, before any plugin hook: always in the bound channel, and in a
  thread or a reply when Hermes's history fetch finds nothing. The room
  never learns the agent was called; the person's next message arrives
  without it. No setting changes this in a free-response channel (candidate
  gap 12).
- **Peer agents on Discord.** Hermes drops messages from other bots
  (`discord.allow_bots: none` by default). To hear peer agents, set
  `discord.allow_bots: all` and `discord.bots_require_inline_mention: false`.
  Both apply to the whole profile and every channel the bot can see, which is
  one more reason to give each room its own bot. With `allow_bots: mentions`,
  only a bot message that @mentions this one is heard. Hermes's bot loop
  guard (`gateway.bot_loop_guard`, on by default) also counts bot messages
  per chat, the channel and each thread apart: once bots post 20 there
  within 5 minutes, it drops every bot message there for 10 minutes, before
  the room hears it (`max_events: 20`, `window_seconds: 300`,
  `cooldown_seconds: 600` in `gateway/bot_loop_guard.py`). Raising
  `max_events` or turning the guard off (`enabled: false`) applies to the
  whole profile. In the room Hermes never answers a bot itself, so the guard
  protects nothing there; without it, the agents' own reading of the room is
  what keeps them from looping.
- **Quick messages.** With Hermes's Discord text batching on (its default),
  a person's messages sent less than 0.6 s apart reach the room as one, with
  the first one's id, mentions and reply target (On Discord). The room setup
  turns it off. On Telegram, batching cannot be turned off
  (`HERMES_TELEGRAM_TEXT_BATCH_DELAY_SECONDS` is at least 0.08 s).
  Messages a person sends while Hermes still hands their previous one to the
  plugin (a fraction of a second) wait in Hermes's busy queue, each on its
  own (`busy_input_mode: interrupt`). Because the plugin takes every message
  in, Hermes never moves the third and later of them up that queue; it runs
  the oldest when the person's next message starts, in that message's
  place, without its dispatch hook. Such a message reaches the room with no
  mentions (the agent's own @mention too, which Hermes has taken out of a
  Discord message's text), no reply target and no bot flag, and the plugin
  logs a warning. On Discord the plugin reads the message's time from its
  id, so the room files it in order; on Telegram the room files it when it
  arrives, after messages sent later. No setting changes this, and no
  public hook gives the plugin those facts (candidate gap 13). Without
  `thread_sessions_per_user`, everyone in a thread shares one such queue.
- **Hermes's notices while it restarts or stops.** While Hermes drains for a
  restart or a stop, it answers each message in the room itself, before any
  plugin hook: "⏳ Gateway is restarting and is not accepting new work right
  now.", or "…not accepting another turn…" for a quick second message. The
  room never hears those messages, and the agent does not know the room saw
  the notices. A restart (`/restart`, `hermes gateway restart`) drains until
  the runs in flight end, up to `agent.restart_after_turn_timeout` (30
  minutes by default). No setting stops the notices (candidate gap 14).
- **No room history after a restart** beyond Nunchi's own log.
- **Hermes's process is not private.** The plugin runs inside Hermes's own
  process, and Nunchi leaves a stock harness's process alone: it does not
  call `nunchi.private_process.keep_private`, as its own runners do. Another
  process of the same OS user can read Hermes's starting environment and
  memory, including any key Nunchi's config names there. The plugin has no
  probe to report this. With the `hermes-host` attention model, Nunchi adds
  no key of its own to that process.
