# Harness contract

**Status: draft for review ([#94](https://github.com/mentatzoe/nunchi/issues/94),
step 9a). Nothing here is built yet.** Cells marked *to verify* are checked
against the harnesses themselves in step 9b, before this contract is frozen.

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
| Events in, turn skipped | harness-hosted only | Hand each room event to the library before the harness acts on it, and skip the agent's run when the library says so. | — |
| After each tool call | no | Add the library's room update to what the agent reads next (steering). | Updates ride on the result of the agent's next room tool call. |
| Continue before posting | no | In final-answer posting, keep the agent going when new messages arrived while it composed (looking again). | The answer is delivered; what arrived meanwhile becomes the next moment. The parity table shows the gap. |
| Start a turn unprompted | harness-hosted only | Start a turn with no inbound message, for pauses and outcomes. | No pause or outcome turns; the parity table shows the gap. |
| Reactions | no | Let the agent react as itself. | The react tool is not offered. |
| Stable guide slot | no | Keep the guide in a stable part of the prompt, such as a system section. | The guide goes with each turn's text. |
| Host model for attention | no | Let attention use the harness's own model and credentials. | A configured attention route. |
| Delivered message id | harness-hosted only | Report the id of the message the harness posted. | Memory records the move by text until the room shows the message. *To verify.* |

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
- Looking again needs "continue before posting". Otherwise the answer goes
  out and the next moment catches up.
- Reactions, room views, and privileged actions are still tools.

## Topologies

**Library-hosted.** The library owns the room connection through its platform
transport. It observes, decides, and calls the integration's `start` for each
turn. The integration only runs the harness.

**Harness-hosted.** The harness owns the room connection:

- The integration feeds each event to `Room.admit`, before the harness acts
  on it.
- When there is no turn, it skips the agent's run.
- When there is one, it gives the agent the turn's guide and context through
  the harness's hooks and wires the tools.
- The library still decides at the commit point. The harness then performs
  delivery, and the receipt says so: the effect is reported as the harness
  delivered it, not confirmed by Nunchi.

## Expected parity

What each integration should use after step 9e. *To verify* cells are
checked in 9b. A gap becomes an issue here, with the alternatives
considered, before anyone asks a harness's maintainers.

| Behavior | Claude Code | Codex (app-server) | Hermes (plugin) | One-reply |
|---|---|---|---|---|
| Topology, posting | library-hosted, tools | library-hosted, tools | harness-hosted, final answer | library-hosted, tools |
| Gate before the agent runs | library | library | `post_gateway_admission` returns `handled` | library |
| Guide | session prompt | developer instructions *(to verify)* | `register_system_prompt_section` | request |
| Turn context | turn text | `turn/start` input | `pre_llm_call` | request |
| Room view | mod tool | dynamic tool or MCP | `register_tool` | room-view action |
| Reaction | mod tool | dynamic tool | tool calling `platform_actions`, if the user grants it | action |
| Silence | a bound turn ends without an action | a turn ends without an action | `[SILENT]` | silence action |
| Look again before posting | send tool holds | send tool holds | **gap**: `pre_verify` fires only after code edits | action held |
| Steering | mod, after each tool call | *to verify*; fallback on room tool results | `transform_tool_result`, or native `busy_input_mode: steer` | between room views |
| Pause and outcome turns | library | library | `inject_message`, if the user grants it | library |
| Catching up | library | library | library, through `admit` | library |
| Cancel | stream-json interrupt | `turn/interrupt` *(to verify)* | *to verify* | drop the reply |
| Attention routes | all | all | all, plus the host's model through `ctx.llm` | all |
| Runs without patching the harness | yes | yes | yes, also under `plugins.isolation: host` | yes |

## Conformance kit (step 9d)

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

Each becomes an issue here in step 9b, with the alternatives considered.
None goes to a harness's maintainers without Zoe's decision.

1. **Hermes, looking again before a final answer.** `pre_verify` can keep the
   agent going but fires only after code edits. Alternatives to weigh:
   - native `busy_input_mode: steer`, which covers turns that call tools;
   - `transform_llm_output` to silence the answer, then `inject_message` to
     start a fresh turn that sees the new messages;
   - accepting the gap for answers composed without tool calls.
2. **Hermes, the id of the message it delivered.** Hooks expose no delivery
   handle; Hermes describes an outbound-delivery contract as future work.
   Memory needs a pointer to the agent's own message.
3. **Hermes, interrupting a running agent from a plugin.**
   `agent_loop_stopped` only observes.
4. **Hermes, room history after a restart.** Does a plugin have a public way
   to read recent channel history?
5. **Codex, steering a running turn.** Does the app-server accept input
   mid-turn? The fallback is updates on room tool results.

## What this replaces (step 9e)

| Today | After |
|---|---|
| Turn rules inside the Claude Code gate | The library's `Turn`; the gate keeps only the session and the mod |
| `ParticipantTurnProtocol` as a separate turn | The one-reply driver of the same `Turn` |
| The Hermes integration's shims over Hermes internals | A plugin on Hermes's public hooks |
| Codex with its tools turned off | The app-server with the user's own configuration and room tools |

Each current integration stays until its replacement passes the conformance
kit. It is then removed, with migration notes.

## Open question

**Where integrations live.** I recommend this repository for now, with one
package and one optional install per harness, and the Hermes plugin also
installable as a subdirectory with `hermes plugins install`. That keeps one
source of truth for the contract and the conformance kit. An integration
can move out later if its harness's ecosystem calls for it, for example
Hermes's reviewed plugin catalog.
