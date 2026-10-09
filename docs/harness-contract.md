# Harness contract

**Status: accepted by Zoe, 2026-10-07 ([#94](https://github.com/mentatzoe/nunchi/issues/94),
steps 9a and 9b). Step 9c built the library's side.** The `Turn` is in the
core (`nunchi.turn`), with both posting styles, and its local protocol is
`nunchi.turn_server` (`I-040D`). The Claude Code gate and the one-reply style
(the behavior eval, Codex) drive it, and the eval measures final-answer
posting with `--agent-posting final-answer`. Step 9d has started: the turn
conformance kit runs in CI (see "Conformance kit"), every library-hosted
integration builds its side through one `Room` (`nunchi.room`), and the
[harness guide](harness-guide.md) is written. The adapters (9e) come next,
built from the guide alone. The harness
facts were checked against upstream source on 2026-10-07: Hermes main
`a50406d9` and Codex `a513012`. The key Hermes and Codex behaviors were then
run (see "Runtime checks"). The conformance kit (step 9d) checks the cells
marked *to verify*. A cell that fails becomes a gap in
[#135](https://github.com/mentatzoe/nunchi/issues/135), and this contract
changes with it.

## Why

Nunchi is a library that any agent harness can use
([`AGENTS.md`](../AGENTS.md), "One library, every harness"). Today the
library owns everything up to the agent's turn, but not the turn itself:

- How the agent acts inside its turn is implemented twice: once in the shared
  one-reply protocol (`ParticipantTurnProtocol`) and once in the Claude Code
  gate (`GatedParticipant`). The gate's copy has more: steering, turn binding,
  and the rule that silence counts only for a bound turn.
- Hermes skips the shared turn and patches Hermes internals instead, so it
  misses memory, catching up, looking again, steering, outcome turns, and the
  newer attention routes.
- The behavior eval measures the shared protocol, not what Claude Code runs.

This contract moves the turn into the library, as one object every harness
drives, and keeps everything harness-specific in a thin integration.

## Words

| Word | Meaning |
|---|---|
| Harness | The program that runs the agent: Claude Code, Codex, Hermes, a plain model call. |
| Integration | The adapter between one harness and the library. |
| Turn | One opportunity for the agent to act, from the moment Nunchi gives it to the moment it ends. |
| Library-hosted | Nunchi owns the room connection and starts the harness's turns (Claude Code, Codex). |
| Harness-hosted | The harness owns the room connection; Nunchi runs inside it as a plugin (Hermes). |
| Tool posting | The agent acts in the room by calling room tools. |
| Final-answer posting | The agent's final answer is what gets posted, as in Hermes, where plugins cannot send. |

## What the library owns

Everything that decides behavior, once, for every harness:

- **Observation**: the room log, actors, history, coverage.
- **Attention**: steps 1 and 2 on any configured route.
- **Scheduling**: one turn at a time per participant; waiting; looking again
  after a pause; catching up after a busy turn; the turn an approved action's
  outcome starts.
- **Memory**: the agent's own moves and reasons, and who asked what.
- **The turn's content**: a stable guide (how a socially aware participant
  behaves) and this turn's context (the reading, memory, pace, missed
  messages, an outcome).
- **The room actions and their rules**:
  - look at more of the room;
  - post a message or a reply;
  - react;
  - propose or withdraw a privileged action;
  - stay silent.

  The rules: one room action per turn; look again once before the first post
  or reaction; steering updates while the agent works; a turn counts as
  silent only if it was bound to its wake; secret values are never posted;
  privileged actions go through authorization.
- **The secret guard**: one per room (`nunchi.room.room_guard`), built from
  the config's `*_env` keys and what the transport holds. The agent's turn
  refuses a secret and tells the agent, so it can answer again; the room's
  host refuses it again before anything leaves. A reason that holds a secret
  is dropped and the move kept, since a reason is never posted. A harness's
  launch secret, which its room tools call the library with, is withheld
  too.
- **The commit point and receipts**: whether a post may go out (the turn is
  still current, not cancelled, its action valid), and the record of what
  happened.

## What an integration supplies

| Capability | Required | What it does | When the harness lacks it |
|---|---|---|---|
| Start a turn | yes | Give the agent the turn's guide and context and let it act. | — |
| Room actions | yes | Either expose the room tools (tool posting) or hand the agent's final answer to the library (final-answer posting). | — |
| Turn end | yes | Tell the library when the agent's turn ends, and how: finished, failed, interrupted. | — |
| Cancel | yes | Stop the agent when the library cancels the turn. | — |
| Events in | harness-hosted only | Hand each room event to the library before the harness acts on it, and keep the harness from running its agent on it. | — |
| After each tool call | no | Add the library's room update to what the agent reads next (steering). | Updates ride on the result of the agent's next room tool call. |
| Continue before posting | no | In final-answer posting, keep the agent going when new messages arrived while it composed (looking again). | Silence the draft and start a fresh turn that carries it. Failing that, the answer is delivered and what arrived meanwhile becomes the next moment; the parity table shows the gap. |
| Silent answers | final-answer posting | Name every whole answer the harness treats as silence besides its marker (`also_silent`). | — |
| What the model wrote | final-answer posting, when the harness can put its own text in place of an answer | Report every model response's text, and apart its reasoning (`model_wrote`), so only the model's own words are posted. A response the harness hides from its hooks cannot be reported, and an answer built from it fails the turn: record it as a gap. | The harness's text for a run that gave no answer can become the agent's reply and memory; the parity table shows the gap. |
| Start a turn itself | harness-hosted only | Start the agent's turn with the library's text, without an inbound message. | Without it, the integration must gate the harness's own runs, which loses silence and looking again on harnesses like Hermes (see Topologies). |
| Reactions | no | Let the agent react as itself. | The react tool is not offered. |
| Stable guide slot | no | Keep the guide in a stable part of the prompt, such as a system section. | The guide goes with each turn's text. |
| Host model for attention | no | Let attention use the harness's own model and credentials. | A configured attention route. |
| Delivered message id | harness-hosted only | Report the id of the message the harness posted. | Memory records the move by its text and time until the room shows the message. |
| Native tool approvals | library-hosted | Answer the harness's own tool-approval requests in a room turn. | — (the rule is the same everywhere: the user's harness rules apply, and anything that would prompt a person is declined, since nobody is at the terminal) |

## The turn interface

A sketch, to be settled in step 9c. The `Turn` is passive: whichever side
runs the agent drives it. When the library hosts, it calls the integration's
`start`. When the harness hosts, the harness's own hooks call into the turn.

```python
class Turn:
    guide: str                 # stable for a session
    context: str               # this turn only
    tools: list[RoomTool]      # for tool posting; the integration picks the names
    cancelled: threading.Event

    def call(self, role: str, arguments: Mapping) -> ToolResult: ...
    def after_tool_call(self) -> str | None: ...   # a room update, or nothing
    def model_wrote(self, text: str, *, reasoning: bool = False) -> None: ...  # final-answer posting: what the model wrote
    def finish(self, answer: str) -> Finish: ...   # final-answer posting: deliver, continue, or silent
    def end(self, status: str, detail: str = "") -> None: ...


class Integration(Protocol):
    capabilities: Capabilities
    def start(self, turn: Turn) -> None: ...       # library-hosted
    def interrupt(self, turn: Turn) -> None: ...


class Room:                                        # harness-hosted entry point
    def admit(self, event: Mapping) -> Turn | None: ...   # None: skip the agent's run
```

- `call` does what the Claude Code gate does today, once, for everyone:
  - it refuses a call outside a bound, current turn;
  - it holds the first post when others posted meanwhile;
  - it takes any wake marker out of the post (`split_private`);
  - it refuses a post with nothing else in it, which is never posted empty;
  - it refuses secret values: the room's guard, plus the launch secret of
    the socket it serves (`TurnServer`);
  - it waits for the commit and describes the result; when it took a
    marker out, the result says so and quotes what the room got.
- One commit check, `Turn.prepare`, serves every commit point: `call`,
  `finish`, and the one-reply style. It removes only what belongs to
  Nunchi, never words the agent meant for the room:
  - **every posting style:** each wake marker that stands whole on one line
    (`</?nunchi_wake\b[^<>\n]*/?>`, any case). A line that holds only
    markers, spaces, tabs and the formatting around them (`*`, `_`, `~`,
    backticks, quotes, `>`) goes with its line break; a marker inside a
    line goes with the spaces and tabs beside it, one space stays between
    the words around it if there was space, a line keeps its indentation,
    and the lines around it stay apart. Code is not special. "<nunchi_wake" named in prose, with no `>`
    after it on its line, is not a marker. Removal is one pass, for the
    markers an agent echoes: a marker that forms only once another is
    removed is crafted text, and is posted.
  - **final-answer posting only**, where the turn teaches `<thinking>`:
    every `<thinking>` block, as before this change
    (`<thinking>(.*?)(?:</thinking>|\Z)`, any case): closed, or running to
    the end of the answer, read on the answer as written. Its words become
    the move's reason; the markers then go from the answer and the reason,
    and the answer is posted trimmed. So what is posted is what
    `model_text` attributes to the model, without its markers.

  Nothing else in a post changes. Native reasoning in other tags
  (`<think>`, `<reasoning>`, `<thought>`) is the harness's job (Zoe's
  decision), so the core reads no other tag and no code: a post that
  names or quotes a tag, in prose or code, is posted as written, and in
  tool and one-reply posting so is `<thinking>`. The turn's own tag
  (`<nunchi_participant_turn_v1>`) and its field names are posted as
  written too; whether the library refuses the turn's tag is open (D6,
  Zoe). `machinery_in` counts leaks for the conformance kit and the
  behavior eval; it never refuses a post. `finish` splits the answer once
  and hands `prepare` what is left.
- In the one-reply style a reply is one move, with no result to read
  after it: a post loses its markers the same way, and the agent's later
  turns show it as posted (`own_moves`). A message of only a marker is
  refused once; a second, or one after any other refusal, is silence (with
  the reason the agent gave, if any).
- `finish` is the final-answer counterpart:
  - **deliver**: the integration posts the answer through the harness;
  - **continue**: the integration keeps the agent going with the library's
    message, so the agent looks again;
  - **silent**: the integration uses the harness's own silence, such as
    Hermes's `[SILENT]`. An answer with nothing left after the commit
    check is silence. So is an answer that ends with the bare marker, in
    any case, after a finished sentence ("I'll leave this to Castor.
    [SILENT]"): the marker is the last thing, after trailing whitespace; no backtick or
    quote character stands right before it; and the text before it ends
    with `.`, `!`, `?`, `…`, `。`, `！`, `？`, `．`, `｡`, `؟`, `۔`, `।`, `॥`
    or `።`, after optional closing quotes, brackets or markdown emphasis
    (`*`, `_`). That text is the silence's reason. "Reply with [SILENT]"
    and "For example: [SILENT]" are posted as written: no sentence ends
    before the marker. Only the last character is read, so
    "e.g. [SILENT]" is silence too.
  - With `model_text`, an answer that is not words the model wrote is
    **silent** too, and the turn fails: it is never the agent's reply, its
    silence, or its memory.
- The one-reply style becomes one more way to drive a `Turn`: the library
  sends one request to a model and feeds its JSON reply to `call`.
  `ParticipantTurnProtocol` and the gate's copy merge into this.
- **Language-neutral protocol.** The same calls are available as versioned
  JSON over a private local socket, for harnesses outside Python. It
  generalizes the routes the Claude Code mod already speaks:

  | Today's route | Becomes |
  |---|---|
  | `/v1/attach` | `attach` |
  | `/v1/turn-start` | `turn/bind` |
  | `/v1/tool` | `turn/call` |
  | `/v1/news` | `turn/after-tool` |
  | none | `turn/finish` and `turn/end` |
  | none | `turn/model-text` (@2), with `reasoning` for reasoning |

  The protocol joins `v2_contracts.INTERFACE_VERSIONS` like the others, as
  `I-040D LocalTurnProtocolV2@2`.

## Posting styles

**Tool posting** (Claude Code, Codex, the one-reply style):

- One room action per turn.
- The first post or reaction is held once if others posted while the agent
  composed. The agent then sends it as is, changes it, or drops it.
- Ending the turn without an action is silence, but only when the turn was
  bound to its wake. Any other ending is a failure.

**Final-answer posting** (Hermes):

- The agent's final answer is the post. The library decides at `finish`.
- Silence uses the harness's own markers: the one the agent is taught, with
  any formatting around it, at the start or on a line of its own, or bare
  after a finished sentence at the end; and the harness's other silent
  answers (`also_silent`), as the whole answer.
- Only words the agent's model wrote can be the post. The integration
  reports them (`model_wrote`). Text the harness puts in their place, such as
  a notice that the run produced nothing, fails the turn.
- Looking again needs "continue before posting", or else a way to silence
  the draft and start a fresh turn that carries it (the Hermes route).
  Without either, the answer goes out and the next moment catches up.
- Reactions, room views, and privileged actions are still tools.

## Topologies

**Library-hosted.** The library owns the room connection through its platform
transport. It observes, decides, and calls the integration's `start` for each
turn. The integration only runs the harness.

**Harness-hosted.** The harness owns the room connection. Two shapes are
possible:

- **Gate the harness's runs.** The integration lets the harness start its
  agent on a message unless the library says skip, and adds the turn's
  context through hooks.
- **Consume and start.** The integration consumes every room message before
  the harness runs on it, hands it to the library, and starts the agent's
  turn itself, with the library's text, when the library decides. The
  harness still delivers the answer and keeps its own model, tools, memory,
  and settings.

Hermes needs the second shape (checked in source, `a50406d9`):

- Messages that arrive while a session is busy skip both gateway hooks
  (`gateway/run_busy.py`), so gating runs would miss them, and by default
  each user in a channel gets a separate session, so runs overlap.
- A bare `[SILENT]` stays silent only on a turn the gateway counts as
  machinery, such as a plugin-injected turn. On a turn a person started, it
  is replaced by a visible warning (`gateway/response_filters.py`).

With consume and start, people's messages never start runs of their own, so
the hooks see every message, one turn runs at a time, and silence works.

In either shape the library still decides at the commit point. The harness
then performs delivery, and the receipt says so: the effect is reported as
the harness delivered it, not confirmed by Nunchi.

## Expected parity

What each integration should use after step 9e, checked against upstream
source. The conformance kit checks the *to verify* cells. A gap becomes an issue
here, with the alternatives considered, before anyone asks a harness's
maintainers.

| Behavior | Claude Code | Codex (app-server) | Hermes (plugin) | One-reply |
|---|---|---|---|---|
| Topology, posting | library-hosted, tools | library-hosted, tools | harness-hosted (consume and start), final answer | library-hosted, tools |
| Gate before the agent runs | library | library | `post_gateway_admission` consumes every message Hermes admits in the bound chat and in the threads inside it (a Discord thread under the channel, a Telegram forum topic), each with its thread (`handled`, no reply), with the reply target, time, mentions and bot flag noted at `pre_gateway_dispatch` (mentions and bot flag in-process only); the library starts turns with `inject_message`. Hermes's own gates run first and need the operator setup below; what they drop regardless is in gap 12. A message Hermes rescues from its busy queue reaches `post_gateway_admission` without `pre_gateway_dispatch`, so without those facts (gap 13) | library |
| Guide | session prompt | with every turn's text (`developerInstructions` would replace the user's own; the library gives one text per turn) | `register_system_prompt_section` | request |
| Turn context | turn text | `turn/start` input | the injected turn text, plus `pre_llm_call` | request |
| Room view | mod tool | per-thread MCP server in `thread/start` config (stable); client tools need an experimental opt-in | `register_tool` | room-view action |
| Reaction | mod tool | the same MCP server | a tool calling `platform_actions.add_reaction`, if the user grants it | action |
| Silence | a bound turn ends without an action; its final message is the reason | a bound turn ends without an action (bound from `turn/start`'s answer once the room server is ready); its last agent message is the reason | `[SILENT]` on the injected turn; its `<thinking>` is the reason; Hermes's other silent answers (`SILENT`, `NO_REPLY`, `NO REPLY` and the zh forms) as `also_silent`, checked against the installed Hermes (verified offline, `a50406d9`) | silence action, with its `why` |
| Only the model's words are posted | n/a (tools) | n/a (tools) | `post_api_request` reports each response's content and, apart, its reasoning (from the provider data too, as under `plugins.isolation: host`); `pre_api_request` reports the part of an answer the length limit or a dropped stream cut (`model_wrote`). Hermes's own text for a run that gave no answer (`(empty)`, its iteration-limit notice) fails the turn, also when the model wrote the word "empty" (verified offline, `a50406d9`). The summary at Hermes's iteration limit reaches no hook and fails the turn (gap 9). A failed run still shows Hermes's failed-turn notice (gap 7) | n/a: the model's reply is the answer |
| Look again before posting | send tool holds | send tool holds | `transform_llm_output` silences the draft; the plugin injects a fresh run with the draft and the new messages (verified offline, `a50406d9`). Needs streaming off: Discord's default, while Telegram streams unless `display.platforms.telegram.streaming` is false | action held |
| Steering | mod, after each tool call | with each room tool's result; `turn/steer` after every other tool call | `transform_tool_result` | between room views |
| Pause and outcome turns | library | library | `inject_message`, like every turn | library |
| Catching up | library | library | library | library |
| Cancel | stream-json interrupt | `turn/interrupt` | no plugin interrupt: the library silences the answer at `transform_llm_output`; tools already run stay run | drop the reply |
| Own message in memory | transport id | transport id | the library records it in the room log with an id of its own (no delivery id; Hermes drops the bot's own messages before hooks) | transport id |
| Attention routes | all | all | all, plus the host's model through `ctx.llm` | all |
| Native tool approvals | user's rules; prompts declined | user's rules; approval requests declined | Hermes's own approvals, whose prompts reach the room (gap 8) | — |
| Secret guard (the room's, from `room_guard`; the host checks every action again) | plus the launch secret, which the session's environment holds, so the agent can read it | plus the bridge's launch secret, which the room's MCP server holds; the agent can read it when Codex runs commands without a sandbox | plus Hermes's platform tokens (Telegram, Discord, Slack) when the config names none | the room's guard (old Codex runner, reference adapters) |
| Runs without patching the harness | yes | yes | yes, also under `plugins.isolation: host` (a turn verified offline, `a50406d9`) | yes |
| Operator setup needed | none | the project's trust level, used when the user's config has none (see gap 5); no MCP server named `nunchi_room` | `allow_gateway_injection`; the injected turns' identity allowed (on Telegram in `TELEGRAM_ALLOWED_USERS`; on Discord in `GATEWAY_ALLOWED_USERS`, because at each connect Hermes drops `DISCORD_ALLOWED_USERS` entries that name no guild member); every person the room should hear allowed, since Hermes drops anyone else before any hook, in the chat and its threads: on Telegram in `TELEGRAM_ALLOWED_USERS`, which also opens direct messages, where Hermes answers itself; on Discord the room's role in `DISCORD_ALLOWED_ROLES` with `DISCORD_ALLOWED_USERS` empty, which refuses the role members' direct messages unless `discord.dm_role_auth_guild` is set, at the cost of Discord's Server Members privileged intent and the role for everyone in the room (a user list opens direct messages to those users, `*` to anyone who shares a server with the bot); per-user group sessions (Hermes's default) and per-user thread sessions (top-level `thread_sessions_per_user: true`; Hermes's default shares a thread, and then merges different people's quick messages into one); `gateway.platform_actions` for reactions. So that people see only what the agent chose: for the room's platform, `streaming`, `tool_progress`, `interim_assistant_messages`, `long_running_notifications`, `show_reasoning` and `runtime_footer` off and `suppress_warning_notifications` on; for the whole profile, `display.file_mutation_verifier`, `display.turn_completion_explainer` and `display.busy_ack_enabled` off, `display.busy_input_mode` `interrupt` (with `queue` Hermes merges a person's quick messages; gap 13) and the `clarify` and `cronjob` toolsets disabled; for the whole bot, `typing_indicator` and `reactions` off. On Discord, so that the room hears the channel and Hermes opens no threads: `discord.free_response_channels` set to the bound channel and `discord.free_response_auto_thread` false, with the channel outside `ignored_channels` and inside `allowed_channels` when that is set; `DISCORD_ALLOWED_CHANNELS`, `DISCORD_IGNORED_CHANNELS`, `DISCORD_FREE_RESPONSE_AUTO_THREAD` and `DISCORD_REACTIONS` unset; `HERMES_DISCORD_TEXT_BATCH_DELAY_SECONDS=0`, so that Hermes does not merge a person's quick messages (gap 13). That setting makes every thread under the channel free-response, so it needs a plugin that holds those threads (this one or later). The agent's answer to a thread message is still posted in the main chat, until the library can place an answer in a thread. Peer bots are heard only with `discord.allow_bots: all` and `bots_require_inline_mention: false`, for the whole profile, and Hermes's bot loop guard then drops every bot message in a chat for 10 minutes once bots posted 20 there within 5 minutes (`gateway.bot_loop_guard`). `agent.max_turns` and `HERMES_MAX_ITERATIONS` unset (gap 9), and the environment variables that override these keys unset. A dedicated profile and bot per room, with `group_allow_admin_from` set (gap 11). The kit runs with exactly these settings, on Telegram and on Discord; it installs Hermes's adapter handlers, its busy handler among them, as Hermes does before it connects, and runs Hermes's connect-time Discord allowlist check | none |

## Conformance kit (step 9d)

`nunchi-turn-conformance` (`nunchi.turn_conformance`) runs it. A scripted
agent plays each scenario's turns through an integration's real path, and the
kit owns the room, attention, the host, and the checks. Two scenarios per
posting style have a second turn that the library starts itself, with no new
message: one after a pause, and one about an approved action's outcome. An integration takes
part with a `KitIntegration`: the participant the host invokes, wired so that
starting its agent plays the script through the integration's own surface.
The kit builds the room with the same `Room` the integrations use.
`nunchi.integrations.claude_code_conformance` is the first: the script binds,
calls the room tools and asks for steering over the gate's socket, as the mod
does. CI runs the kit on a clean install.

**The leak count.** In every scenario the room must receive only what the
library committed, and nothing that names Nunchi's machinery: the wake
marker, the turn's tag, its field names, the silence marker, thinking tags
and internal names (the turn's request id, and the names the integration
gave its room tools, such as `room_send`). After each scenario the kit takes
what reached the room: what the library's own transport sent, and what the
harness itself showed, which the integration reports (`visible()`:
messages, reactions, typing, threads it opened). Anything the harness
showed that is not a committed action is a leak, and so is a committed post
that `nunchi.turn.machinery_in` says names machinery, except a real post a
scenario says the agent meant as written (`real-post`, `final-real-post`,
whose checks require it committed exactly). A leak fails the scenario,
unless the integration declares it as a known gap (`KnownGap`, with the
reason and where it is documented); the cell then reads `gap`, never
`pass`. A harness that changes the agent's post before the library reads
it can declare that too (`KnownGap` of kind `post`, with the harness's
own change as its `transform`): the checks it fails are the gap when what
was committed and shown is exactly that change of the agent's answer, and
any other change still fails. The table's last row counts every leak per integration. An
integration that cannot report what its harness showed still has its
committed posts counted, and the row says that what its harness showed is
`n/a`. The count covers what the scenarios play: a person's message
reaches the kit's room directly, not through the harness's ingress, so what
a harness shows on people's messages (processing reactions, typing, command
replies) is checked in the integration's own tests.

Reference (tools), Claude Code and Codex reach the room only through the
library's transport, so the harness half of their count is 0 by
construction; the committed-post half is a real check. Reference
(final-answer) posts what the library commits for it and reports it, and
Hermes posts final answers itself, so their counts compare what the harness
showed with what was committed. For Hermes the kit records what the
gateway hands the adapter: on Telegram a recording adapter's send, typing
and reactions; on Discord the stock Discord adapter's send boundary (its
send is replaced by a recording one), typing, reactions and the threads it
opens. Formatting, chunking, edits and DMs are not recorded; no scenario
plays them. It finds two known leaks, each in the scenarios named: Hermes's
failed-turn notice (gap 7, `final-harness-failure`), and typing on the
fresh run the plugin starts for the agent to answer again (gap 10,
`final-look-again` and `final-secret`). The second was documented only for
looking again until the kit found it after a refused answer too. It also
shows gap 15 in `final-real-post`: Hermes strips thinking-tag names from a
real answer before the plugin sees it.

Seven scenarios check what the agent writes that the room must, or must
not, read. In tool posting, `leak` sends an echoed wake marker on its own
line before the words: only the words are posted, and the tool result tells
the agent the marker was left out and what the room got. `leak-markup`
sends only a wake marker, which is refused, and the agent's next post goes
out. `real-post` sends, one at a time, real posts that name or quote tags
or the wake marker (`<think>`, `<thinking>`, `<reasoning>` and `<thought>`
in prose, inline code and fenced code, a JSX `<Reasoning>`, Japanese text,
a post that starts with "<reasoning> tags are", "<nunchi_wake" named in
prose), and each is posted exactly as written. In final-answer posting,
`final-leak` answers with a `<thinking>` block, an echoed wake marker and
the words: only the words are posted, and the thinking is the post's
reason; `final-leak-markup` answers with only `<thinking>` and a wake
marker, which is silence with the thinking as its reason;
`final-real-post` answers with the real posts that hold no `<thinking>`
(another tag, in prose or code, or the marker named in prose), each posted
as written by the library; `final-trailing-silence` answers "Castor was asked, not me. [SILENT]",
which is silence with those words as its reason. A post that quotes the
turn's own tag is still posted (D6, open), so no scenario plays one. The
reason kept for a tool post is checked in the core's tests, not by the kit:
the host strips it before its transport, and the kit's room never shows a
tool post back.

`harness-failure` and `final-harness-failure` fail the agent's model call:
the reference harness's call raises; Claude Code ends the run with a failed
`result` (`is_error: true`), read by the gate's own stream-json reader;
Codex and Hermes get HTTP 400 from the scripted model. The turn must end as a
failure before the library's deadline (15 s in the kit), with nothing
committed and no move remembered.

Today's table, generated by `nunchi-turn-conformance --integration reference
--integration nunchi.integrations.claude_code_conformance --integration
nunchi.integrations.hermes_plugin_conformance --integration
nunchi.integrations.codex_app_server_conformance` (the Hermes columns on
Hermes main `a50406d9`, in a real gateway: on Telegram with a recording
adapter, on Discord with Hermes's stock Discord adapter and fake discord.py
channels and messages; the Codex column on Codex CLI 0.160.1, a real
`codex app-server` from a clean npm install; only the model scripted in
all):

| Scenario | reference (tools) | reference (final-answer) | Claude Code gate | Hermes plugin (Telegram) | Hermes plugin (Discord) | Codex app-server (codex-cli 0.160.1) |
|---|---|---|---|---|---|---|
| post: one post goes to the room, and the tool call says so | pass | n/a | pass | n/a | n/a | pass |
| bound-silence: a bound turn that ends without an action is silence, remembered | pass | n/a | pass | n/a | n/a | pass |
| silence-reason: a silent turn's last words are its reason, remembered and never posted | pass | n/a | pass | n/a | n/a | pass |
| mhm: the agent's own mhm is one reaction on the message, through its react tool | pass | n/a | pass | n/a | n/a | pass |
| unbound-failure: a turn never bound to its wake is a failure, not silence | pass | n/a | pass | n/a | n/a | pass |
| look-again: the first post is held once when someone posted meanwhile | pass | n/a | pass | n/a | n/a | pass |
| steering: a message that arrives mid-turn is shown once after a tool call, and can be answered | pass | n/a | pass | n/a | n/a | pass |
| one-action: one room action per turn | pass | n/a | pass | n/a | n/a | pass |
| secret: a withheld secret never reaches the room | pass | n/a | pass | n/a | n/a | pass |
| launch-secret: the launch secret the harness holds never reaches the room, and the agent can post without it | n/a | n/a | pass | n/a | n/a | pass |
| cancel: a cancelled turn posts nothing | pass | n/a | pass | n/a | n/a | pass |
| pause: after a pause the library starts a turn with no new message, which remembers why the agent waited | pass | n/a | pass | n/a | n/a | pass |
| outcome: an approved action's outcome starts a turn, and the agent reports it | pass | n/a | pass | n/a | n/a | pass |
| leak: a post loses an echoed wake marker, and the agent is told | pass | n/a | pass | n/a | n/a | pass |
| leak-markup: a post of only a wake marker is refused, and the agent writes again | pass | n/a | pass | n/a | n/a | pass |
| real-post: a real post that names or quotes tags in prose or code, or names the wake marker, is posted as written | pass | n/a | pass | n/a | n/a | pass |
| harness-failure: a failed model call ends the turn as a failure promptly, and nothing reaches the room | pass | n/a | pass | n/a | n/a | pass |
| final-deliver: the final answer is the post, committed for the harness to deliver, and remembered | n/a | pass | n/a | pass | pass | n/a |
| final-silence: the silence marker is silence, and the agent's thinking is its reason | n/a | pass | n/a | pass | pass | n/a |
| final-mhm: the agent's own mhm is one reaction through its react tool, and the answer after it posts nothing | n/a | pass | n/a | pass | pass | n/a |
| final-look-again: the final answer is held once when someone posted meanwhile | n/a | pass | n/a | gap | gap | n/a |
| final-thinking: thinking is never posted | n/a | pass | n/a | pass | pass | n/a |
| final-secret: a withheld secret is refused once, and the agent answers again | n/a | pass | n/a | gap | gap | n/a |
| final-cancel: a cancelled turn's final answer is silent | n/a | pass | n/a | pass | pass | n/a |
| final-pause: after a pause the library starts a turn with no new message, which remembers why the agent waited | n/a | pass | n/a | pass | pass | n/a |
| final-outcome: an approved action's outcome starts a turn, and the agent's answer reports it | n/a | pass | n/a | pass | pass | n/a |
| final-not-own-words: text the harness puts in place of the agent's answer is never posted or remembered, and the turn fails | n/a | pass | n/a | pass | pass | n/a |
| final-no-answer: a run whose model wrote nothing, with the harness's text as its answer, posts nothing and fails | n/a | pass | n/a | pass | pass | n/a |
| final-silence-forms: a wrapped marker or the harness's other silence word is silence, remembered with its reason; a post that only looks like one goes out | n/a | pass | n/a | pass | pass | n/a |
| final-leak: an answer loses the agent's <thinking>, kept as its reason, and an echoed wake marker | n/a | pass | n/a | pass | pass | n/a |
| final-leak-markup: an answer of only <thinking> and a wake marker is silence, and the thinking is its reason | n/a | pass | n/a | pass | pass | n/a |
| final-real-post: a real answer that names or quotes another tag in prose or code, or names the wake marker, is posted as written | n/a | pass | n/a | gap | gap | n/a |
| final-trailing-silence: the silence marker after the agent's words is silence, and the words are its reason | n/a | pass | n/a | pass | pass | n/a |
| final-harness-failure: a failed model call ends the turn as a failure promptly, and nothing reaches the room | n/a | pass | n/a | gap | gap | n/a |
| **leak count**: what reached the room beyond what the library committed, or named its machinery | 0 | 0 | 0 | 3 (3 known gaps) | 3 (3 known gaps) | 0 |

Through Codex the integration binds a run itself, from `turn/start`'s answer,
so the scripted agent cannot leave it unbound: the Codex column's
`unbound-failure` runs with the throwaway user's own config disabling the room's
MCP server, and the integration fails the turn because the room tools never
reached the run.

The `launch-secret` scenario needs a secret the harness itself holds: the
per-launch secret its room tools call the library's socket with. The agent
posts it, the post is refused, and its next post goes out. Claude Code holds
one (the session's environment) and so does Codex (the room's MCP server).
The reference turn and the Hermes plugin call the library in process and hold
none, so the scenario is n/a for them.

In the pause and outcome scenarios the second turn reaches the agent through
the same `start` as the first, and the agent reads in its text that the turn
is a pause or an outcome. The pause is the library's look again, called when
due rather than after five minutes. In the outcome scenarios the room
authorizes one privileged action, so each integration offers `propose`, as it
would with an `authorization` section. An operator approves the proposal, the
action runs, and the delivery lane starts the outcome turn on its own worker.

Three final-answer scenarios check that the room and the agent's memory
hold only what the agent's own model wrote. In `final-not-own-words` the
model writes a line beside a tool call and the harness ends the run with its
own text; in `final-no-answer` the model writes nothing. Either way the
harness posts nothing, the library commits nothing, the agent's memory holds
no move, and the turn fails. They need a
harness that can answer for its model: the reference does, and so does
Hermes. Through Hermes, `final-not-own-words` gives the run a budget of one
model call (`agent.max_turns: 1`), so Hermes ends it with its own "I reached
the iteration limit and couldn't generate a summary."; in `final-no-answer`
the model answers empty each time, so Hermes retries and hands the plugin
`(empty)`. Hermes runs with the room settings from the plugin's README.
Tool-posting harnesses do not post a final answer, so the scenarios do not
apply to them.
`final-silence-forms` plays three wrapped markers (`**[SILENT]**`,
`` `[SILENT]` ``, `[silent].`), the first of the integration's own other
silent answers (`also_silent`; skipped when it lists none), and one post
that only looks like silence ("No reply from Bob yet. Want me to ping
him?"). The reference lists `NO_REPLY`; Hermes's first is `SILENT`.

The kit's room offers one reaction, the agent's own "mhm", so the `mhm`
scenarios check it through each integration's react tool. Through Hermes,
the kit's room takes the reaction itself; the plugin's own path, Hermes's
`platform_actions`, is checked by `tests/v2/test_hermes_plugin.py`, as are
steering and the room view, which the final-answer scenarios do not use.
Steering after Codex's own tools (`turn/steer`), declined approvals, trust and
resuming are checked by `tests/v2/test_codex_app_server.py`.

The behavior scenes ask an agent for four moves: speak, stay quiet, wait,
and mhm. Each now has a scenario through every integration, and so do a
scene's pause and outcome moments. Replaying every scene moment through each
harness would run the same paths again, at about four minutes per harness in
CI, so the kit does not (Claude's recommendation, 2026-10-07). The behavior
suite still measures how a model makes those moves, and counts the machinery
the model wrote apart from what was posted.

The plan for the kit, as accepted:

- A scripted agent for each posting style plays a scene's moves through the
  integration, so every result is deterministic.
- **Scenes**: the behavior scenes, plus one scene per rule:
  - looking again holds the first post once;
  - a steering update is shown once;
  - silence counts only when the turn was bound;
  - a cancelled turn posts nothing;
  - a pause turn starts, and so does an outcome turn;
  - a secret value is refused, and so is the harness's launch secret.
- **Clean installs**: each harness is installed clean and pinned in CI, as
  the stock-Hermes lanes already do; never anyone's own setup.
- **Output**: the parity table, generated from the results.

## Candidate gaps

Each confirmed gap becomes an issue here, with the alternatives considered.
None goes to a harness's maintainers without Zoe's decision.

1. **Hermes, looking again before a final answer.** No public hook can hold
   or retry every final answer: `pre_verify` fires only after `write_file` or
   `patch` changed a file in that turn (`agent/turn_stop_gates.py`).
   - Proposed: silence the draft in `transform_llm_output` and inject a fresh
     turn that carries the draft and the new messages. The cost is a second
     agent turn, only when someone posted meanwhile.
   - Requirement: streaming off in Nunchi rooms, since a streamed draft is
     already visible before the transform. Discord does not stream by
     default; Telegram does, so a Telegram room needs
     `display.platforms.telegram.streaming: false`
     (`hermes_cli/config_defaults.py`).
   - Not adopted: middleware substituting a synthetic tool call
     (undocumented, and it can't hide streamed text).
2. **Hermes, the id of the message it delivered.** There is no hook, ledger
   field or transcript field for it, and the Discord adapter drops the bot's
   own messages before any hook. Memory records the move by text and time.
   A raw Discord listener (`register_platform_handler`) would see it, but
   only in-process, with no stability guarantee.
3. **Hermes, interrupting a running agent.** `PluginContext` has no interrupt,
   `agent_loop_stopped` only observes, and injected text cannot run `/stop`.
   The fallback silences the answer; tools already run stay run.
4. **Hermes, room history after a restart.** There is no `ctx` history API.
   `ctx.dispatch_tool("discord", {"action": "fetch_messages", ...})` reads
   history, but it relies on dispatch skipping the toolset check, which is
   fragile. The library's own persisted log is the main source. *To verify.*
5. **Codex, trusting the working directory.** `thread/start` with a `cwd` and
   a writable sandbox writes `trust_level = "trusted"` into the user's own
   Codex config (`app-server/src/request_processors/thread_processor.rs`;
   reproduced, see Runtime checks). **Resolved:** the integration passes the
   project's trust level in the thread's own `config` map, which leaves the
   user's config untouched and keeps write access. It does so only when the
   user's config (`config/read`) has no trust decision for the directory; the
   user's own decision stands (`nunchi.integrations.codex_app_server`).
6. **Codex, profiles and environment keys.** The app-server rejects
   `--profile` and ignores `CODEX_API_KEY`, so it runs with the user's default
   profile and stored login. This is acceptable if documented.
7. **Hermes, its failed-turn reply.** On a failed run Hermes posts its own
   notice ("…Your request was not processed. Send it again…"), after
   `[SILENT]` when the output hook ran. No hook or setting stops it:
   `transform_llm_output` carries no failed flag, Hermes honors silence only
   for runs that did not fail (`gateway/response_filters.py`), and a provider
   failure fires no output or end hook. The library ends the turn as failed
   and remembers no move. After a provider failure the plugin ends it once
   Hermes stops asking the model: no new `pre_api_request` within 5 s of an
   error Hermes marks not retryable, or within 130 s of a retryable error
   with its retries spent, since Hermes's auto-recovery ladder (on by
   default) waits up to 120 s and asks again. Until then the room's next
   moment waits.
   The conformance kit counts the notice as a known gap
   (`final-harness-failure`).
   - Alternatives: a blank output (`' '`), which relies on undocumented
     handling; asking Hermes to let a plugin-injected turn end silently when
     it fails.
8. **Hermes, approval prompts.** A command Hermes wants approved prompts in
   the room, and `approvals.mode: off` removes the prompt only by approving
   everything. The safe route is to disable the `terminal` and
   `code_execution` toolsets. Hermes already has unattended approvals for
   webhook turns (`approvals.unattended_mode`), not for plugin-injected ones.
9. **Hermes, the summary at its iteration limit.** With `agent.max_turns` or
   `HERMES_MAX_ITERATIONS` set, a run that uses up its budget ends with a
   summary Hermes requests outside `pre_api_request` and `post_api_request`
   (`handle_max_iterations`). The plugin cannot report it, so the model's own
   summary fails the turn and is not posted. The room settings leave the
   limit unset (Hermes's default). A test pins the gap.
   - Alternatives: asking Hermes for `post_api_request` on that call; accepting
     an answer that follows Hermes's summary request, which would let other
     unreported text through.
10. **Hermes, typing on a fresh run.** The fresh run the plugin starts for
    the agent to answer again, after looking again or after a refused
    answer (it held a secret), runs as Hermes's queued follow-up, which
    calls `send_typing` directly, whatever `typing_indicator` says. No
    setting stops it. A test pins the gap, and the conformance kit counts it
    as a known gap (`final-look-again`, `final-secret`).
    - Alternatives: injecting the fresh run only after Hermes releases the
      session; asking Hermes to honor `typing_indicator` there.
11. **Hermes, built-in slash commands.** Hermes answers its commands in the
    room before any plugin hook, and a room member can change display
    settings for the whole profile with them: `/reasoning show` posts the
    agent's private thinking with each answer. Gating with
    `group_allow_admin_from` limits who can; a denied command still gets a
    reply. Dropping or rewriting built-in commands in the bound chat is
    decision D4.
12. **Hermes, Discord messages dropped before any hook.** Hermes's Discord
    adapter drops, before `pre_gateway_dispatch` and whatever the settings: a
    message that @mentions another bot and not this one, which includes a
    Reply to a peer agent's message with Discord's default reply ping; and a
    message that is only an @mention of the bot, once Hermes has taken the
    mention out, unless its history fetch adds context (it never does for a
    plain message in a free-response channel). The room never hears people
    answer a peer agent by Reply, or call the agent by name alone. Tests pin
    both.
    - Alternatives: asking Hermes for a hook, or a setting, that lets a
      plugin see messages its Discord admission drops in a free-response
      channel; a raw listener (`register_platform_handler`), in-process
      only and without a stability guarantee.
13. **Hermes, a person's quick messages.** Hermes's text batching merges
    a person's messages sent close together into the first, with its id,
    mentions and reply target (`HERMES_DISCORD_TEXT_BATCH_DELAY_SECONDS`,
    which the room setup turns off on Discord; on Telegram at least
    0.08 s). A message that arrives while Hermes still handles the sender's
    previous one goes to Hermes's busy queue, each on its own under
    `display.busy_input_mode: interrupt` (with `queue` Hermes merges them
    into one, under the last one's id). Hermes moves that queue up only
    after an agent run (`_run_agent_drain_pending`), and a message the
    plugin consumes at `post_gateway_admission` runs none. So the third and
    later messages wait until the sender's next message starts, and Hermes
    then runs the oldest in its place (`_hm_rescue_orphaned_fifo`), after
    `pre_gateway_dispatch` ran for the new one only. The rescued message
    reaches the room with no mentions (the agent's own too), no reply
    target, no time and no bot flag. The admission payload carries none of
    them and no other public surface does, so the plugin cannot recover
    them; on Discord it reads the time from the message id (a snowflake),
    which keeps the room's order. A test pins it on Discord.
    - Alternatives: asking Hermes to run `pre_gateway_dispatch` for a
      rescued message, to put the reply target, time, mentions and bot flag
      in the `post_gateway_admission` payload, or to move its busy queue up
      after a message a plugin handled; a faster admission hook, which
      narrows the window but cannot close it.
14. **Hermes, its notices while it restarts or stops.** While Hermes drains
    for a restart or a stop (`_draining`), it answers each message in the
    room itself, before any plugin hook: the idle path's "not accepting new
    work" (`_hm_dispatch_quick_and_plugin_commands`), and the busy path's
    "not accepting another turn" (`_send_busy_drain_notice`). The room never
    hears those messages, and no setting stops the notices. A restart
    drains until the runs in flight end, up to
    `agent.restart_after_turn_timeout` (30 minutes by default). A test pins
    it on Discord; Telegram takes the same path.
    - Alternatives: asking Hermes to let a plugin that consumes a chat's
      messages see them during a drain, or to skip the notice for such a
      chat.
15. **Hermes, thinking-tag names in a real answer.** Before any plugin hook,
    Hermes strips `<think>`, `<thinking>`, `<reasoning>` and `<thought>`
    (and its other reasoning tag names) from the final answer, in any case
    and inside code too (`strip_think_blocks`): closed pairs, an unclosed
    tag at a line's start through the end, and every lone tag. Stripping
    the model's native reasoning is the harness's job (Zoe's decision), but
    Hermes also strips tags from words meant for the room. An answer that
    names or quotes a tag (a code block with R1's raw `<think>` output, a
    JSX `<Reasoning>` component, "<think>plan</think> is how R1 marks its
    plan.") reaches the library changed, and Hermes posts the changed text;
    an answer that starts with such a tag ("<reasoning> tags are what the
    model hides") is stripped to nothing, and nothing is posted. Where
    Hermes removes a lone tag between Japanese or Chinese words
    ("思考は<thinking>タグの中に書きます。"), the library cannot match the
    changed text to the model's words (`model_text`), so nothing is posted
    either, and the turn fails; this predates the leak count. The library
    itself posts an answer that names any other tag as written; it takes
    out only `<thinking>`, the tag the turn teaches, as before
    (`split_private`). The conformance kit shows it as a known gap
    (`final-real-post`): the gap carries Hermes's own `strip_think_blocks`,
    and a play reads `gap` only when the room got exactly what Hermes makes
    of the answer; any other change fails.
    - Alternatives: the plugin passing the model's raw answer
      (`post_api_request`) to the library when Hermes's text differs from it
      only by stripped tags, which needs the plugin to mirror Hermes's
      stripper and cannot reach an answer Hermes stripped to nothing;
      asking Hermes for a setting that leaves tags in code alone.

Resolved during 9b:

- **Codex steering:** `turn/steer` is stable, and `turn/start` sent during a
  running turn steers it.
- **Codex room tools:** a per-thread MCP server in `thread/start`'s `config`
  is stable and sits on top of the user's own servers.

## Runtime checks (2026-10-07)

Throwaway installs only, never anyone's own setup.

**Hermes main `a50406d9`.** The tests use Hermes's own gateway test pattern:
the real `GatewayRunner` and adapter ingress with a recording transport, and
only the model call stubbed. The spike file is kept with the step 9b notes.

| Check | Result |
|---|---|
| `post_gateway_admission` returning `handled` with no reply | The person's message is consumed: no run, no reply. |
| A plugin-injected turn that answers `[SILENT]` | Nothing is sent. |
| A plugin-injected turn that answers with text | The text is delivered, and the injected turns share one session. |
| A person posts while an injected turn runs (per-user group sessions, the default) | The hook sees the message, and no run of its own starts. |
| The same with shared group sessions | The message takes the busy path and the hook never sees it. **So Nunchi rooms need per-user group sessions.** |
| An injected turn's identity outside the platform's allowed users | Hermes refuses the injection. **So that identity must be allowed.** |

Hermes's own tests show that `transform_llm_output`'s replacement is the final
answer the gateway receives and stores, and that `transform_tool_result`
replaces a tool's result. Together with the checks above, looking again
(silence the draft, then inject a fresh turn) and steering hold.

**Codex CLI 0.160.1, `codex app-server`.** `thread/start` with a fresh Codex
home and a git working directory, no model call:

| Thread start | Writes trust into the user's config |
|---|---|
| `cwd`, workspace-write sandbox | yes |
| `cwd`, read-only sandbox | no |
| no `cwd`, workspace-write | no |
| `cwd`, workspace-write, trust level `trusted` in the thread's `config` | no |
| `cwd`, workspace-write, trust level `untrusted` in the thread's `config` | no |

Still to run, in the conformance kit (step 9d), since they need real
adapters: the Hermes plugin under `plugins.isolation: host`, and reading
history through `ctx.dispatch_tool`. A Codex turn with room tools from a
per-thread MCP server now runs in the kit (Codex CLI 0.160.1): the server sits
on top of the user's own MCP servers, each call carries its Codex turn id in
`_meta`, and a user config that disables a server of the same name leaves the
thread without the room tools, which the integration treats as unbound.

## What this replaces (step 9e)

| Today | After |
|---|---|
| Turn rules inside the Claude Code gate | The library's `Turn`; the gate keeps only the session and the mod (done in step 9c) |
| `ParticipantTurnProtocol` as a separate turn | The one-reply driver of the same `Turn` (done in step 9c) |
| The Hermes integration's shims over Hermes internals | A plugin on Hermes's public hooks (built from the harness guide: `nunchi.integrations.hermes_plugin`, verified offline; not yet live) |
| Codex with its tools turned off | The app-server with the user's own configuration and room tools (built from the harness guide: `nunchi.integrations.codex_app_server`, verified offline on Codex CLI 0.160.1; its runner `nunchi-codex-app-server-runner` is on the shared room connection, not yet run live) |

Each current integration stays until its replacement passes the conformance
kit. It is then removed, with migration notes.

## Where integrations live

Decided (Zoe, 2026-10-07): in this repository for now. Each harness gets one
package and one optional install. The Hermes plugin can also be installed
from its subdirectory with `hermes plugins install`. That keeps one source of
truth for the contract and the conformance kit. An integration can move out
later if its harness's ecosystem calls for it, for example Hermes's reviewed
plugin catalog.
