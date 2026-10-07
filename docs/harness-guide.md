# Harness guide

How to make a harness use Nunchi: Claude Code, Codex, Hermes, or one Nunchi
has not met yet. This guide covers the library's side. Your harness's own
documentation covers its side.

**Status:** written in step 9d of [#94](https://github.com/mentatzoe/nunchi/issues/94),
before the Hermes and Codex adapters (9e). Each adapter is built from this
guide alone. Where the guide falls short, the guide is fixed. The first test:
a separate agent built the Hermes plugin from it, and this version carries
what it found.

Read first:

- [`AGENTS.md`](../AGENTS.md), "One library, every harness": why the library
  holds the behavior.
- [`harness-contract.md`](harness-contract.md): what the library owns, what an
  integration supplies, and the parity table for known harnesses.

## What you build

An integration is a thin adapter. It connects three things the harness
already has to three things the library already has:

| The harness has | The library has | The integration connects them |
|---|---|---|
| A way to run the agent | `Turn`, one per opportunity | Start the agent with the turn's text, and report when its run ends. |
| Tools, or a final answer | The room actions and their rules | Forward each room tool call, or hand over the final answer. |
| A room connection, or the library's | `Room`: observation, attention, scheduling, memory | Hand every room event to the `Room`, and post what it commits. |

Everything that decides behavior stays in the library: when the agent gets a
turn, what it reads, looking again, steering, silence, memory, the secret
guard. An adapter that decides any of that is a bug, even when it works.

## The rules

- **Public extension points only.** Use the harness's documented hooks,
  plugins, protocols, or APIs. Never patch, monkeypatch, or wrap its
  internals.
- **No social logic in the adapter.** If the adapter wants to decide whether
  or what the agent says, the library is missing something. Open an issue
  here.
- **A missing extension point is an issue here first**, with the alternatives
  considered. Nobody asks a harness's maintainers for a change without Zoe's
  decision.
- **Clean, pinned installs.** Prove the adapter against a fresh install of a
  pinned harness version, never against anyone's own setup.
- **Secrets stay out.** The agent never receives Nunchi's credentials, and
  every room action passes the secret guard.

## Choose a shape

Answer two questions about the harness.

**Who owns the room connection?**

| | Library-hosted | Harness-hosted |
|---|---|---|
| Room connection | Nunchi's transport (the shared Discord transport, the reference adapters) | The harness's own gateway |
| Who starts the agent's turns | The library calls your driver | Your plugin, when the library says so |
| Room events reach the library | From Nunchi's transport | From your plugin's ingress hook |
| Examples | Claude Code, Codex | Hermes |

A harness-hosted integration must **consume and start**: it takes every room
message before the harness runs its agent on it, hands it to the library, and
starts the agent's turn itself when the library decides. Gating the harness's
own runs loses silence and looking again (see the contract's "Topologies").

**How does the agent act in the room?**

| | Tool posting | Final-answer posting |
|---|---|---|
| The agent posts by | Calling a room tool | Its final answer |
| Silence | Ending a bound turn without an action | The harness's silence marker, such as `[SILENT]` |
| Choose it when | The harness lets an integration add tools and does not post the final answer itself | The harness always posts the agent's final answer |

Reactions, the room view, and privileged actions are tools in both styles.

**Whatever else the harness posts.** In final-answer posting the library sees
only what reaches your output hook. List everything the harness can post by
itself besides the final answer: streamed drafts, text the model writes beside
a tool call, tool progress lines, status notices. Turn each off for the room
in the harness's configuration, document it as operator setup, and test both
the harness's default and the room's setting. Hermes needs four such settings
([`integrations/hermes-plugin/README.md`](../integrations/hermes-plugin/README.md)).

## The pieces

All are in the core package, `nunchi`, standard library only.

| Piece | Module | What it is |
|---|---|---|
| `RoomSettings` | `nunchi.room` | The shared config sections, checked once. |
| `Room` | `nunchi.room` | Everything the library owns for one participant in one room. |
| `TurnParticipant` | `nunchi.turn` | The participant the library invokes. It builds a `Turn` per opportunity and hands it to your driver. |
| `TurnDriver` | `nunchi.turn` | What you write: `start(turn)` and `interrupt(turn)`. |
| `Turn` | `nunchi.turn` | One opportunity: `text`, `wake_id`, `cancelled`, and `tool_names`, the room tools this turn offers. |
| `SecretGuard` | `nunchi.turn` | Refuses a room action that carries a withheld value, or text matching a credential pattern the integration names. |
| `HarnessDelivery` | `nunchi.turn` | The transport for final-answer posting: the harness posts the message itself. |
| `Finish` | `nunchi.turn` | What becomes of a final answer: `deliver`, `continue`, or `silent`, with `text`. |
| `HostTextAttentionModel`, `HostStructuredAttentionModel` | `nunchi.attention` | Attention on the harness's own model. |
| `TurnServer` | `nunchi.turn_server` | The same turn calls as JSON over a private socket, for code outside Python. |
| `KitIntegration` | `nunchi.turn_conformance` | How your adapter joins the conformance kit. |

## Step by step

### 1. Configuration

An integration's config has the shared sections and one section of its own:

```json
{
  "schema_version": 2,
  "binding": {
    "participant_id": "vigil",
    "actor_id": "example:user:1234",
    "platform": "example",
    "room_id": "room-1",
    "continuity_scope_id": "example:room-1",
    "names": ["Vigil"]
  },
  "profile": {"path": "/etc/nunchi/vigil.profile.json", "sha256": "…"},
  "attention": {"policy": {"preattention_enabled": true}, "model": {"kind": "…"}},
  "limits": {},
  "state_directory": "/var/lib/nunchi/vigil",
  "my_harness": {"…": "your integration's own settings"}
}
```

- `binding.actor_id` is the agent's own identity on the platform, exactly as
  room events name it. The library never guesses who the agent is from names.
- `profile` is pinned by its hash, and must name the same participant and
  actor.
- `authorization` is optional: privileged actions, behind the shared
  authorization coordinator.

```python
from nunchi.room import RoomSettings

settings = RoomSettings.from_config(config, label="My harness", sections=("my_harness",))
my_settings = settings.sections["my_harness"]  # yours to check
```

### 2. The participant and the driver

```python
from nunchi.turn import SecretGuard, Turn, TurnParticipant

class MyDriver:
    def start(self, turn: Turn) -> None:
        """Start the agent's run with turn.text; return once it has started."""

    def interrupt(self, turn: Turn) -> None:
        """Stop the agent's run: the library cancelled the turn."""

participant = TurnParticipant(
    profile=settings.profile,
    driver=MyDriver(),
    guard=SecretGuard(withheld_values),
    tool_names={"send": "room_send", "react": "room_react", "context": "room_context"},
    roles=("send", "react", "context"),
    silence_marker=None,  # or your harness's marker, for final-answer posting
)
```

- `tool_names` maps each room role to the name the agent sees. Choose names
  that fit your harness's conventions. Roles: `send`, `react`, `context`
  (the room view), `propose` and `withdraw` (privileged actions, only with
  `authorization`).
- With a `silence_marker`, the participant uses final-answer posting and
  offers no `send` tool.
- `tool_names` needs a name for every role in `roles`. The default roles are
  all five.
- `withheld_values` are the secret values your integration holds and the agent
  must never post: transport keys, model API keys, anything in the
  environment the agent should not see. Values shorter than 12 characters are
  ignored. Add the shape of your platform's tokens as compiled patterns:
  `SecretGuard(values, patterns=[re.compile(...)])`.
- A driver may add `ready(cancel) -> bool`. The library calls it before
  starting a turn; return False if the harness cannot take one.
- Set `bind_timeout_seconds` if the harness may accept a turn and then never
  run it. Hermes, for one, drops an injected turn whose identity is not
  allowed, and tells no plugin. A run that has not bound in time fails the
  turn.

The library runs one turn at a time per participant. The adapter never
queues turns:

- After its room action, the agent's run may still be finishing. The next
  turn waits until you report that run's end (step 6). If the end never
  comes, the library closes the previous turn as a failure after
  `previous_turn_grace_seconds` (30 s by default).
- When the library cancels a turn, it calls `interrupt` and closes the turn.
  Whatever the run does later finds it closed: `finish` answers `silent`, a
  room tool call is refused, and `end_turn` for it returns False.

### 3. Binding the agent's run to its wake

A turn counts as silent only if the agent's run was bound to its wake: that
shows the agent really received the turn and its room actions. Bind when
the harness shows that the run started with the turn's text:

```python
participant.bind_turn(turn_id=harness_run_id, wake_id=turn.wake_id)
```

- `turn_id` is any id your harness gives that run. Every later call for the
  run passes the same id. If some hooks or tool calls carry a different key,
  such as a session or task id, keep a map from that key to the run's id,
  filled when you bind. A harness that runs one turn at a time per session
  makes the map unambiguous.
- `wake_id` must reach the binding from the turn itself, where the agent
  cannot change it. Put `<nunchi_wake id="…"/>` at the start of the turn's
  text and read it in the hook that sees the run start, as the Claude Code mod
  and the Hermes plugin do.
- **Harness-hosted: your hooks see runs that are not yours:** other chats,
  direct messages, the harness's own command line. Bind only a run whose
  input carries the open turn's wake id. A run that carries a Nunchi marker
  but did not bind belongs to a closed turn: answer it with the silence
  marker.
- A later run in the same open turn binds with `wake_id=None`. It continues
  the turn, for example after a `continue` in final-answer posting.

A run that never binds cannot act in the room, and when it ends the turn is a
failure, never silence.

### 4. Room actions

**Tool posting.** Register the tools from `participant.attach()` (name,
description, JSON input schema) with the harness. Forward each call:

```python
ok, text = participant.call_tool(turn_id=harness_run_id, tool=name, arguments=arguments)
# ok: return `text` as the tool's result. Not ok: return it as the tool's error.
```

The library applies the turn's rules inside `call_tool`:

- one room action per turn;
- the first post is held once if others posted meanwhile, and the agent
  decides again;
- the secret guard;
- the wait for the commit.

The text says what happened in words the agent can act on. Pass it through
unchanged.

You register the tools once, but each turn offers only some: `turn.tool_names`
lists this turn's. A call to a tool the turn does not offer returns an error
the agent can read. A harness may also hide plugin tools behind a search step
(Hermes's `tool_search`); they still work.

**Final-answer posting.** Hand the agent's final answer to the library
before the harness posts it:

```python
decision = participant.finish(turn_id=harness_run_id, answer=final_answer)
```

| `decision.kind` | Do this |
|---|---|
| `deliver` | Let the harness post `decision.text`. Thinking in `<thinking>` tags is already removed. |
| `silent` | Replace the answer with the harness's silence marker, so nothing is posted. |
| `continue` | Keep the agent going with `decision.text` as its next input. It looks again at new messages, or answers again after a refusal. |

- **Hand `finish` the answer as the model wrote it, thinking included.** The
  library keeps `<thinking>` as the move's reason and never posts it. If your
  harness strips thinking before your output hook, recover the raw text from
  an earlier hook, or the reason is lost. The Hermes plugin reads it in
  `post_api_request`.
- `finish` waits up to `result_wait_seconds` for the host's commit. Keep that
  below your harness's own hook timeout. Hermes abandons an output hook after
  30 s and posts the raw draft, so the plugin waits 20 s.
- **If the harness cannot continue a run,** answer with the silence marker.
  When the current run ends, start a fresh run in the same turn, with
  `decision.text` as its input and the same wake marker. It binds with
  `wake_id=None`, so keep a note that it is a continuation. The text carries
  the draft, so the fresh run does not need the old one's history. Do not
  report the turn's end in between.

### 5. Steering

After each tool call the agent makes in a bound run, room tool or not, ask
for the room's news and add it to that tool's result:

```python
update = participant.news(turn_id=harness_run_id)
if update:
    result = result + "\n\n" + update  # or the harness's own context field
```

The agent then folds a message that arrived mid-turn into what it is doing.
Each message is shown once. Without a hook after tool calls, steering rides on
the next room tool call's result, and the parity table shows the gap.

### 6. The end of the run

Report every run's end, exactly once, success or not:

```python
participant.end_turn(turn_id=harness_run_id, ok=True, detail="")
participant.end_turn(turn_id=None, ok=False, detail="the harness refused the run")
```

- Use `turn_id=None` only when the run never got an id or never bound, and
  only if the harness cannot have started a newer run since: without an id,
  whatever turn is open ends.
- `ok=False` for errors, crashes, timeouts and interruptions.
- In final-answer posting with a pending fresh run (step 4), report the end
  only after that run ends.

### 7. Room events in

Each room event goes to the `Room` as a closed, canonical event with its
actors:

```python
room.deliver(
    delivery_id="example:delivery:9001",  # unique per delivery; repeats are ignored
    event={
        "id": "example:message:9001",
        "type": "message",
        "author_id": "example:user:42",
        "text": "Can someone look at the failing deploy?",
        "mentioned_actor_ids": [],
        "mentions_room": False,
        "timestamp": "2026-10-07T18:00:00Z",       # optional
        "reply_to_event_id": "example:message:9000",  # optional
    },
    actors={"example:user:42": {"kind": "human", "display_name": "Sam"}},
)
```

- `deliver` returns at once. Any turn it starts runs on the library's worker.
- Event types: `message`, `reaction` (`author_id`, `target_event_id`,
  `reaction`, `operation`: `add` or `remove`) and `membership`. The full
  shape is `I-010A` in [`contracts/nunchi-v2.md`](contracts/nunchi-v2.md),
  checked by `nunchi.v2_contracts.validate_canonical_event`.
- Actor `kind`: `human`, `bot`, `system`, or `unknown`. Never invent a kind
  you do not know.
- Ids must be the platform's own and stable. The agent's replies and
  reactions target them. If the harness gives a message no id, use a unique
  one of your own; nothing can target that message.
- **The agent's own messages are events too.** Deliver them with
  `author_id` set to `binding.actor_id`. The library never wakes on them,
  but memory finds the agent's own moves this way. If the harness hides its
  agent's own messages from plugins, the library remembers each message
  `HarnessDelivery` committed by its text and time instead, until the room
  shows it (`I-010C@14`).
- **Harness-hosted: consume every message in the participant's room,** so
  the harness never runs its agent on one by itself. The harness then sees
  only the turns your driver starts. Consume the message even when handing it
  to the library fails: a harness that answers a person directly bypasses the
  room, and its silence marker may turn into a visible warning on a person's
  turn.
- Other chats and direct messages are not this participant's room. A
  harness-hosted plugin leaves them to the harness. A library-hosted
  transport that sees another channel delivers it with
  `authorized_route=False`: recorded, never woken on.
- When the harness's payload is thin, send what you know and nothing more:
  empty `mentioned_actor_ids`, no `reply_to_event_id`, actor kind `unknown`.
- `deliver` returns a `DeliveryOutcome`. Its `observation` says whether the
  event was recorded and whether it may wake the agent.

### 8. The room

```python
from nunchi.room import Room
from nunchi.adapters.model_apis import ATTENTION_KINDS

room = Room(
    settings,
    participant=participant,
    transport=transport,
    event_visibility={"message": "history-and-live", "reaction": "live-only", "membership": "unavailable"},
    state_prefix="my-harness-",
    attention_kinds=ATTENTION_KINDS,
)
```

- `transport`, library-hosted: your platform transport. Its
  `dispatch(action=..., wake=...)` posts a `message`, `reply` or `reaction`
  and returns a `TransportResult` (`nunchi.participant`): `sent`, `failed`,
  `unknown` or `unavailable`, with a detail.
- `transport`, harness-hosted: `HarnessDelivery(native)`. The harness posts
  messages. In final-answer posting the answer is a message, never a reply
  to a chosen message. `native` is optional; give it if the harness lets a
  plugin react. It has three methods:
  - `dispatch(action=..., wake=...) -> TransportResult` for a reaction:
    `{"kind": "reaction", "origin_event_id": …, "target_event_id": …,
    "reaction": …, "operation": "add"}` (or `"remove"`);
  - `ordinary_action_capabilities() -> list[str]`, such as `["reaction"]`;
  - `reaction_capability() -> ReactionCapability` (`nunchi.reactions`): the
    operations and reactions the platform allows. The library offers the
    react tool on a turn only when this allows it.
- `event_visibility` says honestly what the harness shows for each event
  type: `history-and-live`, `live-only`, or `unavailable`.
- `attention_kinds` are the attention routes your integration installs. To
  let attention use the harness's own model, pass `attention_model=` instead,
  from `nunchi.attention`:
  - `HostTextAttentionModel(complete)` for a plain-text completion, called as
    `complete(system=..., prompt=..., timeout_seconds=...)`;
  - `HostStructuredAttentionModel(client, AttentionModelSelection(provider=..., model=...))`
    for a client with `complete_structured`.
- `privileged_executors` are the native privileged actions your harness can
  perform, used only with `authorization`.
- `participant_timeout_seconds` bounds one turn.
- `room.cancel()` cancels the running turn; `room.restart()` starts over
  after the room connection restarts; `room.drain(timeout)` waits until no
  turn runs.
- **Harness-hosted: build the `Room` in the process that owns the room
  connection, on first use.** Harnesses often load plugins in every process
  (Hermes loads them in its command line too), and only the gateway should
  open the room's state.
- Install the library into the harness's own Python environment.

### 9. Turns to expect

- **Catching up.** A message the agent already saw mid-turn, through
  steering or looking again, may still get a turn of its own afterwards, when
  it was the newest message waiting. Attention judges it with the agent's
  memory, which holds what the agent said. Tests should expect that turn.
- **Looking again after a pause, and outcome turns.** The library starts
  these itself, through the same `start`.

## Walkthrough: library-hosted, tool posting

The Claude Code integration, in order (`nunchi.integrations.claude_code_v2`,
`claude_code_gate`, and the mod in `claude_code_mod/hooks/register.ts`):

1. The runtime reads the config into `RoomSettings`, builds a
   `GatedParticipant` (a `TurnParticipant` whose driver writes to a dedicated
   Claude Code session), and builds a `Room` with the shared Discord
   transport.
2. The gate serves `TurnServer` on a private socket, with a per-launch secret
   passed to the session's environment.
3. The mod, at session start, calls `/v1/attach` and registers the room tools.
4. For each turn, the driver submits `<nunchi_wake id="…"/>` and `turn.text`
   to the session.
5. The mod's `turn.start` hook reads the wake id and binds with the session's
   turn id (`/v1/turn-start`).
6. The mod forwards room tool calls (`/v1/tool`). After every tool call it
   asks `/v1/news` and adds the update to the result's context.
7. The session's end of turn comes back on its stream, and the gate calls
   `turn_ended`.

## Walkthrough: harness-hosted, final-answer posting

The consume-and-start shape, with hook names generic. The contract's parity
table names the Hermes hooks for each step.

`nunchi.integrations.hermes_plugin` is the worked example.

1. **Load.** The plugin reads its config into `RoomSettings` and builds a
   `TurnParticipant` with the harness's silence marker. It registers the
   reaction and room-view tools from `participant.attach()`, and forwards
   their calls to `call_tool`. It builds the `Room`, with `HarnessDelivery`,
   on the first message the gateway admits.
2. **Ingress.** Every message in the room reaches the plugin's ingress hook.
   The plugin hands it to `room.deliver` and tells the harness it is handled,
   with no reply, even when the hand-over failed.
3. **Start.** The library calls `driver.start(turn)`. The driver asks the
   harness to start a run with `<nunchi_wake id="…"/>` and `turn.text`, as
   the plugin's own message.
4. **Bind.** The first hook that sees the run, before the model call, reads
   the marker and binds the run if the id is the open turn's. It maps the
   session and task keys that tool handlers get to the run's id.
5. **Steering.** The tool-result hook adds `news(turn_id=…)` to each result.
6. **Finish.** The output hook calls `finish` with the raw answer, thinking
   included, and returns `decision.text` for `deliver`, or the silence marker
   otherwise. For `continue`, it notes the fresh run to start.
7. **End.** The run-end hook starts the noted fresh run, which step 4 binds
   with `wake_id=None`. With none pending, it reports the end with
   `end_turn`.
8. **Cancel.** Hermes cannot interrupt a plugin's run, so `interrupt` does
   nothing: the library closes the cancelled turn, `finish` answers `silent`,
   and step 6 returns the silence marker. Tools already run stay run. The
   parity table records the gap.

## Outside Python

`nunchi.turn_server.TurnServer(participant, socket_path=..., session_secret=...)`
serves the same calls as JSON over a Unix socket (`I-040D
LocalTurnProtocolV2@1`):

| Route | Body | Answer |
|---|---|---|
| `/v1/attach` | `{}` | `protocol`, `version`, `posting`, `silence_marker`, `tools` |
| `/v1/turn/bind` | `turn_id`, `wake_id` | `bound` |
| `/v1/turn/call` | `turn_id`, `tool`, `input` | `ok` with `text`, or `error` |
| `/v1/turn/after-tool` | `turn_id` | `text` or null |
| `/v1/turn/finish` | `turn_id`, `answer` | `finish` (`deliver`, `continue`, `silent`) and `text` |
| `/v1/turn/end` | `turn_id` (optional), `ok`, `detail` | `ended` |

- Every request carries the launch secret in `X-Nunchi-Session`. Others are
  refused.
- The socket's directory is private to the integration's user.
- Requests are at most 256 KiB.

Give the secret only to the harness process you start, through its
environment. Never put it in the agent's view.

## Prove it

Every integration joins the turn conformance kit before it replaces anything.

1. Write a `KitIntegration`: an object with `name`, `posting` (`tools` or
   `final-answer`), `participant(profile=, guard=, agent=)` and `close()`.
   `participant` returns your participant, wired so that starting its agent
   plays the scripted agent's steps through your integration's own surface:
   your hooks, your socket, your tool registration.
   - Library-hosted: script only the model and the harness process. See
     `nunchi.integrations.claude_code_conformance`.
   - Harness-hosted: the harness is real, and the scripted agent is its
     model. Stub the model at its API, for example a local OpenAI-compatible
     endpoint configured as the harness's provider. Do not replace the
     harness's run loop: that skips the hooks under test. Tell your agent's
     model calls apart from the harness's own, such as session titles. See
     `nunchi.integrations.hermes_plugin_conformance`.
   - The kit builds its own `Room` around the participant you return, so your
     integration must work with a room it did not build.
2. Expose `conformance_integrations()` in that module.
3. Run it:

   ```sh
   nunchi-turn-conformance --integration reference --integration your.module
   ```

4. Add the command to CI on a clean install, with the harness pinned.
5. Put the generated table in [`harness-contract.md`](harness-contract.md),
   "Conformance kit". A failing cell is a gap in
   [#135](https://github.com/mentatzoe/nunchi/issues/135), not a reason to
   skip the scenario.

The kit owns the room, attention, the host and the checks, and builds them
with the same `Room` your integration uses. What it does not cover, test
through your harness in your own tests, as `tests/v2/test_hermes_plugin.py`
does:

- its `arrive` step records a message in the room log directly, not through
  your ingress;
- its final-answer scenarios use no tools, so steering, the room view and
  reactions go untested there.

Before importing the harness in a test, point its home and temporary
directories at a throwaway directory. Otherwise the harness may write into
the user's own home: Hermes writes into `~/.hermes` on import.

## Known library gaps

- **The agent's own message, when the harness never shows it.** Memory
  keeps it by its text and time, but the room log does not have it. So the
  question it answered still shows no response, and the room's pace misses
  it (Hermes).
- **Unknown mentions.** A canonical event cannot say that its mentions or
  reply target are unknown, only that there are none.
- **One text per turn.** The turn's guide and its context come as one text
  (`turn.text`), so a harness's stable system-prompt slot cannot hold the
  guide alone.
- **Conformance scenes still to add:** the behavior scenes through each
  integration, and pause and outcome turns (step 9d).

Each is tracked in [#135](https://github.com/mentatzoe/nunchi/issues/135).

## Checklist

- [ ] Public extension points only; nothing patched.
- [ ] Everything the harness posts besides the final answer is off for the
  room, documented and tested.
- [ ] No decision about whether or what the agent says.
- [ ] Every room event delivered, the agent's own included.
- [ ] Every run bound when it starts, and its end reported once.
- [ ] Steering after every tool call, where the harness has a hook for it.
- [ ] The secret guard holds every value the integration withholds.
- [ ] The conformance kit passes on a clean, pinned install, in CI, with the
  harness's home isolated.
- [ ] The parity table updated, and gaps filed in #135.
- [ ] The integration documents itself under `integrations/`.
