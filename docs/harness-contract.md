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
  - it refuses secret values;
  - it waits for the commit and describes the result.
- `finish` is the final-answer counterpart:
  - **deliver**: the integration posts the answer through the harness;
  - **continue**: the integration keeps the agent going with the library's
    message, so the agent looks again;
  - **silent**: the integration uses the harness's own silence, such as
    Hermes's `[SILENT]`.
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

  The protocol joins `v2_contracts.INTERFACE_VERSIONS` like the others.

## Posting styles

**Tool posting** (Claude Code, Codex, the one-reply style):

- One room action per turn.
- The first post or reaction is held once if others posted while the agent
  composed. The agent then sends it as is, changes it, or drops it.
- Ending the turn without an action is silence, but only when the turn was
  bound to its wake. Any other ending is a failure.

**Final-answer posting** (Hermes):

- The agent's final answer is the post. The library decides at `finish`.
- Silence uses the harness's own marker.
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
| Gate before the agent runs | library | library | `post_gateway_admission` consumes every message (`handled`, no reply); the library starts turns with `inject_message` | library |
| Guide | session prompt | with every turn's text (`developerInstructions` would replace the user's own; the library gives one text per turn) | `register_system_prompt_section` | request |
| Turn context | turn text | `turn/start` input | the injected turn text, plus `pre_llm_call` | request |
| Room view | mod tool | per-thread MCP server in `thread/start` config (stable); client tools need an experimental opt-in | `register_tool` | room-view action |
| Reaction | mod tool | the same MCP server | a tool calling `platform_actions.add_reaction`, if the user grants it | action |
| Silence | a bound turn ends without an action; its final message is the reason | a bound turn ends without an action (bound from `turn/start`'s answer once the room server is ready); its last agent message is the reason | `[SILENT]` on the injected turn; its `<thinking>` is the reason | silence action, with its `why` |
| Look again before posting | send tool holds | send tool holds | `transform_llm_output` silences the draft; the plugin injects a fresh run with the draft and the new messages (verified offline, `a50406d9`). Needs streaming off: Discord's default, while Telegram streams unless `display.platforms.telegram.streaming` is false | action held |
| Steering | mod, after each tool call | with each room tool's result; `turn/steer` after every other tool call | `transform_tool_result` | between room views |
| Pause and outcome turns | library | library | `inject_message`, like every turn | library |
| Catching up | library | library | library | library |
| Cancel | stream-json interrupt | `turn/interrupt` | no plugin interrupt: the library silences the answer at `transform_llm_output`; tools already run stay run | drop the reply |
| Own message in memory | transport id | transport id | the library records it in the room log with an id of its own (no delivery id; Hermes drops the bot's own messages before hooks) | transport id |
| Attention routes | all | all | all, plus the host's model through `ctx.llm` | all |
| Native tool approvals | user's rules; prompts declined | user's rules; approval requests declined | Hermes's own approvals | — |
| Runs without patching the harness | yes | yes | yes, also under `plugins.isolation: host` (a turn verified offline, `a50406d9`) | yes |
| Operator setup needed | none | the project's trust level, used when the user's config has none (see gap 5); no MCP server named `nunchi_room` | `allow_gateway_injection`; the injected turns' identity among the platform's allowed users; per-user group sessions (Hermes's default); `interim_assistant_messages`, `tool_progress` and `long_running_notifications` off for the room's platform, or Hermes posts text the library never saw; `gateway.platform_actions` for reactions | none |

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

Today's table, generated by `nunchi-turn-conformance --integration reference
--integration nunchi.integrations.claude_code_conformance --integration
nunchi.integrations.hermes_plugin_conformance --integration
nunchi.integrations.codex_app_server_conformance` (the Hermes column on Hermes
main `a50406d9`, in a real gateway; the Codex column on Codex CLI 0.160.1, a
real `codex app-server` from a clean npm install; only the model scripted in
both):

| Scenario | reference (tools) | reference (final-answer) | Claude Code gate | Hermes plugin | Codex app-server |
|---|---|---|---|---|---|
| post: one post goes to the room, and the tool call says so | pass | n/a | pass | n/a | pass |
| bound-silence: a bound turn that ends without an action is silence, remembered | pass | n/a | pass | n/a | pass |
| silence-reason: a silent turn's last words are its reason, remembered and never posted | pass | n/a | pass | n/a | pass |
| unbound-failure: a turn never bound to its wake is a failure, not silence | pass | n/a | pass | n/a | pass |
| look-again: the first post is held once when someone posted meanwhile | pass | n/a | pass | n/a | pass |
| steering: a message that arrives mid-turn is shown once after a tool call, and can be answered | pass | n/a | pass | n/a | pass |
| one-action: one room action per turn | pass | n/a | pass | n/a | pass |
| secret: a withheld secret never reaches the room | pass | n/a | pass | n/a | pass |
| cancel: a cancelled turn posts nothing | pass | n/a | pass | n/a | pass |
| pause: after a pause the library starts a turn with no new message, and the agent can post | pass | n/a | pass | n/a | pass |
| outcome: an approved action's outcome starts a turn, and the agent reports it | pass | n/a | pass | n/a | pass |
| final-deliver: the final answer is the post, committed for the harness to deliver, and remembered | n/a | pass | n/a | pass | n/a |
| final-silence: the silence marker is silence, and the agent's thinking is its reason | n/a | pass | n/a | pass | n/a |
| final-look-again: the final answer is held once when someone posted meanwhile | n/a | pass | n/a | pass | n/a |
| final-thinking: thinking is never posted | n/a | pass | n/a | pass | n/a |
| final-secret: a withheld secret is refused once, and the agent answers again | n/a | pass | n/a | pass | n/a |
| final-cancel: a cancelled turn's final answer is silent | n/a | pass | n/a | pass | n/a |
| final-pause: after a pause the library starts a turn with no new message, and its answer is the post | n/a | pass | n/a | pass | n/a |
| final-outcome: an approved action's outcome starts a turn, and the agent's answer reports it | n/a | pass | n/a | pass | n/a |

Through Codex the integration binds a run itself, from `turn/start`'s answer,
so the scripted agent cannot leave it unbound: the Codex column's
`unbound-failure` runs with the throwaway user's own config disabling the room's
MCP server, and the integration fails the turn because the room tools never
reached the run.

In the pause and outcome scenarios the second turn reaches the agent through
the same `start` as the first, and the agent reads in its text that the turn
is a pause or an outcome. The pause is the library's look again, called when
due rather than after five minutes. In the outcome scenarios the room
authorizes one privileged action, so each integration offers `propose`, as it
would with an `authorization` section. An operator approves the proposal, the
action runs, and the delivery lane starts the outcome turn on its own worker.

The final-answer scenarios exercise no room tools, so steering, the room
view and reactions through Hermes are checked by
`tests/v2/test_hermes_plugin.py` instead. Steering after Codex's own tools
(`turn/steer`), declined approvals, trust and resuming are checked by
`tests/v2/test_codex_app_server.py`. Still to add: the behavior scenes through
each integration, and the leak count.

The plan for the kit, as accepted:

- A scripted agent for each posting style plays a scene's moves through the
  integration, so every result is deterministic.
- **Scenes**: the behavior scenes, plus one scene per rule:
  - looking again holds the first post once;
  - a steering update is shown once;
  - silence counts only when the turn was bound;
  - a cancelled turn posts nothing;
  - a pause turn starts, and so does an outcome turn;
  - a secret value is refused.
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
