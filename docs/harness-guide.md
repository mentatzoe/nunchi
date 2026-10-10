# Harness guide

How to make a harness use Nunchi: Claude Code, Codex, Hermes, or one Nunchi
has not met yet. This guide covers the library's side. Your harness's own
documentation covers its side.

**Status:** written in step 9d of [#94](https://github.com/mentatzoe/nunchi/issues/94),
before the Hermes and Codex adapters (9e). Each adapter is built from this
guide alone. Where the guide falls short, the guide is fixed. Two tests so
far: separate agents built the Hermes plugin and the Codex app-server
integration from it, and this version carries what they found.

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
- **Secrets stay out of the room.** Keep Nunchi's credentials out of the
  agent's view. Every room action passes the secret guard, in the agent's
  turn and again at the room's host.

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

**Whatever else the harness posts.** People in the room should see only what
the agent chose to do. In final-answer posting the library sees only what
reaches your output hook. List everything the harness can show by itself:

- streamed drafts, text the model writes beside a tool call, tool progress
  lines, reasoning, status and error notices;
- text it adds to the final answer after your output hook, such as a footer
  or an explanation, even after a silence marker;
- text it puts in place of an answer the model never gave, such as a notice
  that the run produced nothing;
- typing indicators and processing reactions;
- its own prompts (clarifying questions, approvals), scheduled posts, command
  replies, busy notices and restart notices.

Turn each off for the room in the harness's configuration, document it as
operator setup with the reason, and test both the harness's default and the
room's setting. Never hand `finish` the harness's stand-in for a missing
answer: report what the model wrote (`model_text`, step 4), so the library
fails the turn instead of posting or remembering it. If your output hook
fails, end the turn as failed and return the harness's silence; some
harnesses post the raw draft when a hook raises. Whatever no setting or hook
can stop goes into the integration's known gaps. Hermes's list is in
[`integrations/hermes-plugin/README.md`](../integrations/hermes-plugin/README.md).
The conformance kit counts what the harness shows in the scenarios it
plays (Prove it); what it shows on people's messages, its prompts and
command replies belong in your own tests.

**Whatever the harness drops or does before your ingress hook.** The room
should hear the whole conversation, and a harness-hosted plugin hears only
what reaches its hook. List what the harness does to a message before then:

- what it drops: mention gates (a group message that does not name the
  bot), user and channel allowlists, ignored channels, filters for other
  bots. Open each for the room;
- what it does first: opening a thread for the message, processing
  reactions, typing. Turn each off; no hook can take it back;
- what it merges: batching quick messages, or one session shared by
  everyone in a thread, can turn several people's messages into one under
  the first one's id and author. Give each person their own session and
  turn batching off where the harness allows;
- what it queues: a message that arrives while the harness still handles
  the sender's previous one. Check that each reaches your ingress hook on
  its own, in order, and with the facts your other hooks note; Hermes runs
  some without its dispatch hook.

Places nested in the room, such as the threads under a channel or the
topics in a group, belong to the room unless its binding says
`threads_in_room: false` (step 1). Consume their messages too, with
the thread each is in (`thread_root_event_id`, step 7); a harness left to
answer them bypasses the room. With the setting off, still consume them: it
only keeps them out of the room, so the harness does not answer them itself.
A setting that opens the room's channel may open its threads too, as
Hermes's Discord `free_response_channels` does: the
plugin that holds them must ship with that setting or before it, never
after. Test the harness's defaults and the room's setting through its real
ingress, as the Hermes kit's Discord lane does with Hermes's stock Discord
adapter.

## The pieces

All are in the core package, `nunchi`, standard library only.

| Piece | Module | What it is |
|---|---|---|
| `RoomSettings` | `nunchi.room` | The shared config sections, checked once. |
| `Room` | `nunchi.room` | Everything the library owns for one participant in one room. |
| `TurnParticipant` | `nunchi.turn` | The participant the library invokes. It builds a `Turn` per opportunity and hands it to your driver. |
| `TurnDriver` | `nunchi.turn` | What you write: `start(turn)` and `interrupt(turn)`. |
| `Turn` | `nunchi.turn` | One opportunity: `text`, `wake_id`, `cancelled`, and `tool_names`, the room tools this turn offers. |
| `SecretGuard` | `nunchi.turn` | Refuses a room action that carries a withheld value, or text matching a credential pattern. Values under 12 characters are ignored. The match is exact: an encoded or split secret gets past it. |
| `room_guard` | `nunchi.room` | Builds the room's one `SecretGuard` from the config and the transport. Give it to your participant and your `Room`. |
| `HarnessDelivery` | `nunchi.turn` | The transport for final-answer posting: the harness posts the message itself. |
| `Finish` | `nunchi.turn` | What becomes of a final answer: `deliver`, `continue`, or `silent`, with `text`. |
| `HostTextAttentionModel`, `HostStructuredAttentionModel` | `nunchi.attention` | Attention on the harness's own model. |
| `TurnServer` | `nunchi.turn_server` | The same turn calls as JSON over a private socket, for code outside Python. |
| `keep_private` | `nunchi.private_process` | From the call on, other processes of its OS user cannot read a library-hosted runner's process (Linux). Call it first in `main`. It does not cover start-up (step 2). |
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
- `binding.threads_in_room` (optional, `true` or `false`, default `true`) says
  whether the threads opened under the room's channel, and the topics of a
  forum group, are part of the room. This is the one setting, with the same
  name and meaning in every harness, so each README only points here:
  - **`true`:** the agent hears them (their messages carry
    `thread_root_event_id`, step 7), and its reply, post or reaction about a
    message in a thread lands in the thread, where the harness can place it.
  - **`false`:** their messages are not part of the room. The library keeps
    them out of the room's observation whichever way a harness delivers
    them, as long as the delivery names the thread (`thread_root_event_id`,
    step 7; the delivery audit reads `route-rejected`), so an integration
    that names the thread and does nothing else still honors it. An
    integration that can should also not fetch or deliver them, which saves
    the work: the shared Discord transport takes the setting at registration
    and sends nothing from threads, the reference adapter does not place a
    thread in its parent channel, and the Hermes plugin consumes the message
    so Hermes does not answer it itself.
  A harness-hosted plugin still consumes thread messages when the setting is
  `false` (step 7).
  **Who honors it today.** The Discord reference adapter (`nunchi-discord`),
  the shared Discord transport (the Claude Code, Codex and Codex app-server
  integrations) and the Hermes plugin (Discord threads and Telegram topics)
  name a message's thread and honor the key. The Telegram and Matrix
  reference adapters accept it and ignore it: they carry no thread facts, so a
  topic or thread message reaches the agent as an ordinary message of the
  room, and its reply goes to the room, with either setting. The channel
  adapter (`nunchi-channel`) takes its events as given, so the key works only
  for a producer that sets `thread_root_event_id`. The older
  `integrations/hermes` integration rejects the key at load, naming it.
- `profile` is pinned by its hash, and must name the same participant and
  actor. The file is JSON with exactly five fields: `profile_id`,
  `participant_id`, `actor_id`, `instructions` (who the agent is in this
  room) and `provenance`.
- `authorization` is optional: privileged actions, behind the shared
  authorization coordinator.

```python
from nunchi.room import RoomSettings

settings = RoomSettings.from_config(config, label="My harness", sections=("my_harness",))
my_settings = settings.sections["my_harness"]  # yours to check
```

### 2. The participant and the driver

```python
from nunchi.room import room_guard
from nunchi.turn import Turn, TurnParticipant

class MyDriver:
    def start(self, turn: Turn) -> None:
        """Start the agent's run with turn.text; return once it has started."""

    def interrupt(self, turn: Turn) -> None:
        """Stop the agent's run: the library cancelled the turn."""

guard = room_guard(settings, transport=transport)  # the room's transport, step 8

participant = TurnParticipant(
    profile=settings.profile,
    driver=MyDriver(),
    guard=guard,
    tool_names={"send": "room_send", "react": "room_react", "context": "room_context"},
    roles=("send", "react", "context"),
    silence_marker=None,  # or your harness's marker, for final-answer posting
    also_silent=(),       # final-answer posting: your harness's other silent answers
    model_text=False,     # final-answer posting: True when you report what the model wrote
)
```

- `tool_names` maps each room role to the name the agent sees. Choose names
  that fit your harness's conventions. Roles: `send`, `react`, `context`
  (the room view), `propose` and `withdraw` (privileged actions, only with
  `authorization`).
- With a `silence_marker`, the participant uses final-answer posting and
  offers no `send` tool. The agent is taught that marker.
- `also_silent` lists the other whole answers your harness treats as
  silence, such as `NO_REPLY`. Set it whenever your harness has any, or the
  library remembers a reply the room never saw. Only with a
  `silence_marker`.
- `model_text=True` says your integration reports what the model wrote
  (step 4). Set it whenever your harness can put its own text in place of a
  missing answer. Only with a `silence_marker`.
- `tool_names` needs a name for every role in `roles`. The default roles are
  all five.
- `room_guard` builds the secret guard. Give the `Room` the participant's
  guard (`Room(..., guard=participant.guard)`, step 8); the room's host then
  checks every action again. The participant's guard must hold at least what
  the room's holds, or the agent loses its chance to answer again: a refusal
  in its turn is a tool error it can act on, a refusal at the host is not.
  The guard withholds:
  - the value of every variable that a config key ending in `_env` names, in
    the attention model, your own sections and the authorization section. A
    key holds one name or a list of names. Such a key always names a secret:
    the guard refuses any post that quotes its value.
  - the default key variables the library's models read when the config
    names none: `NUNCHI_ATTENTION_API_KEY` and `NUNCHI_PARTICIPANT_API_KEY`;
  - what the transport holds: give your transport `withheld_values()` (its
    token or key) and `credential_patterns()` (the shapes of its platform's
    tokens);
  - `values=` and `patterns=`, for what your config does not name, such as a
    default variable your integration reads.

  Values shorter than 12 characters are ignored. Keep the agent's working
  directory outside `state_directory`.
- Library-hosted: your integration starts the harness, so keep these
  variables out of the harness's environment.
  `nunchi.room.withheld_env_names(settings)` lists them. Drop every
  `NUNCHI_*` variable too.
- Harness-hosted: the harness's own process holds whatever your config names
  there, such as a keyed attention route's key and the platform's tokens.
  The guard still withholds their values from the room. Prefer an attention
  route the host serves (its own model), so Nunchi adds no key of its own to
  that process, and say in your README which keys live there.
- If your integration is its own program (library-hosted), call
  `nunchi.private_process.keep_private()` first in its `main`, before any
  secret is read and before the harness starts. From then on, other
  processes of the same OS user cannot read your process's keys through
  `/proc`. It does not cover start-up: keys in the starting environment are
  readable by any process of that user for about a tenth of a second at
  each start (Python's start-up and your imports). An agent with an
  unsandboxed shell can leave a reader running and force a start by killing
  a supervised runner; a signal needs only the same user. Only a separation
  the agent cannot cross closes that: the harness's sandbox, if it hides
  other processes, or running the agent as its own OS user. Document the
  harness's sandbox setting in your README. Report the call's result in
  your probe (`probe_facts(status)`, plus `agent_os_user`); it does not
  mean the keys are safe. An integration that runs inside the harness's own
  process must not call it: that process is the harness's.
- If you serve `TurnServer` (see "Outside Python"), it adds its launch
  secret to the participant's guard when you build it. Build it before the
  `Room` and before the first turn, so the guard the `Room` gets holds the
  launch secret too.
- A driver may add `ready(cancel) -> bool`. The library calls it before
  starting a turn, to start the harness or wait until it is idle. Return
  False only when `cancel` is set. If the harness cannot take the turn,
  raise with the reason: the turn fails, and is never the agent's silence (a
  False without a cancel fails it too).
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
  cannot change it. Two ways:
  - **Your driver starts the run and the harness answers with its id** (a
    protocol, such as Codex's `turn/start`): bind in `start` with that id,
    and leave the marker out, so the agent never sees the wake id.
  - **A hook sees the run start:** put the core's wake marker at the start
    of the turn's text and read it there, as the Claude Code mod and the
    Hermes plugin do. Import it, do not copy it:
    `from nunchi.turn import WAKE_MARKER`, then
    `WAKE_MARKER.format(turn.wake_id) + "\n" + turn.text`. The library takes
    any wake marker out of a post, so an agent that echoes one, even an old
    one from its history, never shows it to the room.
- Check that the start really started a new run. Codex's `turn/start`, for
  one, folds the text into a run already in progress.
- Bind only when the harness also shows the room tools reached the run, for
  example its MCP server reported ready. Otherwise fail the turn: a run
  without the room actions cannot be silent.
- Two races to handle:
  - A room tool call can arrive before you have bound: let it wait until the
    start in progress finishes.
  - A quick run can end before you bind: after binding, report an end you
    already saw.
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
description, JSON input schema) with the harness. If the tools come from an
MCP server the harness starts, that server forwards each call to the
library's local protocol (`TurnServer`, see "Outside Python") with the run's
id from the call's request metadata. Give it the socket and secret through
the harness's server configuration, never the agent's view.
`nunchi.integrations.codex_app_server.mcp_bridge` is an example. Make sure
the room tools never need the harness's own approval (Codex:
`default_tools_approval_mode = "approve"`), or your rule of declining
whatever would ask a person refuses them. Forward each call:

```python
ok, text = participant.call_tool(turn_id=harness_run_id, tool=name, arguments=arguments)
# ok: return `text` as the tool's result. Not ok: return it as the tool's error.
```

The library applies the turn's rules inside `call_tool`:

- one room action per turn;
- the first post is held once if others posted meanwhile, and the agent
  decides again;
- each wake marker that stands whole on one line is taken out of a post,
  with the spaces beside it (a line of only markers and the formatting
  around them goes with its line break); nothing else changes, so a post
  that names or quotes any tag, `<thinking>` included, goes out whole; a
  post of only a marker is refused;
- the secret guard;
- the wait for the commit.

The text says what happened in words the agent can act on, including that
a marker was left out of its post and what the room got. Pass it through
unchanged.

The library does not touch the model's native reasoning in any tag: your
harness handles it (Zoe's decision). If your harness hands tool arguments
or answers over with the model's reasoning in them, strip it there.

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
| `deliver` | Let the harness post `decision.text`. The agent's `<thinking>` blocks and any wake marker are already removed, and the answer is trimmed; nothing else was changed. |
| `silent` | Replace the answer with the harness's silence marker, so nothing is posted. |
| `continue` | Keep the agent going with `decision.text` as its next input. It looks again at new messages, or answers again after a refusal. |

The library reads silence the way a harness does. The empty answer is
silence, and so is an answer with nothing left once the `<thinking>` and
any wake marker are out. So is an answer that starts with the marker, holds
it on a line of its own, or is wholly the marker or one of `also_silent`,
ignoring case, whitespace, and the punctuation or `` ` `` and `~` around
it: `**[SILENT]**`, `` `[SILENT]` `` and `[silent].` are all silence. An
answer that ends with the bare marker (in any case) after a finished
sentence is silence too: `I'll leave this to Castor. [SILENT]`, `Castorに任せます。[SILENT]`. The
marker must be the last thing, with no backtick or quote character right
before it, and the text before it must end with `.`, `!`, `?`, `…`, `。`,
`！`, `？`, `．`, `｡`, `؟`, `۔`, `।`, `॥` or `።` (closing quotes, brackets or
`*` and `_` may follow). The words beside the marker are the silence's reason. A
marker inside a sentence is a mention, and the answer is posted: `Reply
with [SILENT]`, `For example: [SILENT]`, `Done. **[SILENT]**`.

- **Report what the model wrote.** Many harnesses put their own text in
  place of an answer the model never gave: a notice that the run produced
  nothing, an iteration-limit message, an error. That text must never become
  the agent's post or its memory. With `model_text=True`, report each model
  response before you hand over the final answer:

  ```python
  participant.model_wrote(turn_id=harness_run_id, text=content)
  participant.model_wrote(turn_id=harness_run_id, text=reasoning, reasoning=True)  # if the provider returned any
  ```

  Report every response, even an empty one, in order, including a part your
  harness keeps when the length limit or a dropped stream cuts an answer.
  The final answer must then be words the model wrote: a run of words in one
  response's text, or running on across responses, as a continuation after
  the length limit does, even when the cut falls inside a tag pair such as an
  HTML snippet. Case, whitespace, punctuation, markdown and tagged
  blocks such as `<think>` do not count, so stripping them is fine. Reasoning
  and a tagged block count only as a whole: the answer must be all of one,
  as when a harness answers with the model's reasoning. An answer of one or
  two words keeps its punctuation, so a harness's `(empty)` is not the
  model's word "empty". Anything else is not the agent's: `finish` answers
  `silent`, and the turn ends as a failure, never as the agent's reply or
  silence. The empty answer is still silence. If you declare `model_text`
  and report nothing, every answer fails, so a missing report shows up at
  once. Check which model calls your harness shows plugins: Hermes shows
  most responses in `post_api_request`, the part of a cut answer in the
  next `pre_api_request`, and the summary at its iteration limit in none
  (the plugin's README, Known gaps).

- **Hand `finish` the answer as the model wrote it, `<thinking>`
  included.** The turn teaches the agent to think inside `<thinking>`; the
  library takes every such block out (in any case, closed or running to
  the end of the answer) and keeps it as the move's reason, as it always
  has. It reads no other tag: the model's native reasoning (`<think>` and
  the like) is your harness's to strip (Zoe's decision). If your harness
  strips `<thinking>` before your output hook, recover the raw text from
  an earlier hook, or the reason is lost. Hand over the raw text when
  `split_private(raw, final_answer=True)[0] == split_private(answer,
  final_answer=True)[0]`: it is the same post with the thinking in. The
  Hermes plugin reads it in `post_api_request`. If your harness also strips
  tags from words meant for the room (Hermes strips them in code too),
  that is a known gap to document.
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

A harness may take steering as new input to the running turn instead of
through a tool result (Codex's `turn/steer`). Send the update after each of
the agent's tool calls. If the run ends first, the update is lost, though it
counts as shown; the next moment catches up.

### 6. The end of the run

Report every run's end, exactly once, success or not:

```python
participant.end_turn(turn_id=harness_run_id, ok=True, detail="", note=final_message)
participant.end_turn(turn_id=None, ok=False, detail="the harness refused the run")
```

- With tool posting, pass the agent's last words as `note`: its final
  message, if the harness reports one. When the turn ends without a room
  action they are its silence's reason, which later turns see, as
  `<thinking>` is in final-answer posting. They are never posted, and words
  that hold a withheld secret are not kept.

- Use `turn_id=None` only when the run never got an id or never bound, and
  only if the harness cannot have started a newer run since: without an id,
  whatever turn is open ends.
- `ok=False` for errors, crashes, timeouts and interruptions.
- Some runs end with no end hook, such as a Hermes run whose provider
  refused for good. Report those too, from whatever hook shows the failure,
  or the turn holds up the room until the library's deadline. First wait for
  the harness to give up: never end a turn the harness may still answer, or
  the agent's answer is lost. A refusal may move to a fallback provider at
  once, so a few seconds will do; after spent retries Hermes may wait in its
  recovery ladder for up to 120 s and ask again.
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
        "thread_root_event_id": "example:message:8990",  # optional: the thread it is in
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
- `actors` describes every actor the event names, on every event: its
  author and each actor in `mentioned_actor_ids`, with what the platform
  says about them. The room forgets actors whose events left its log, and
  refuses an event naming one it does not know. The agent itself is known
  from the binding.
- Ids must be the platform's own and stable. The agent's replies and
  reactions target them. If the harness gives a message no id, use a unique
  one of your own; nothing can target that message.
- **The agent's own messages are events too.** Deliver them with
  `author_id` set to `binding.actor_id`. The library never wakes on them,
  but memory, threads and the room's pace find the agent's own moves this
  way. If the harness hides its agent's own messages from you, say so with
  `HarnessDelivery(room_shows_own_messages=False)`: the library then records
  each message it committed for the harness in the room log itself, with an
  id of its own, as a reply to the message the turn was about.
- **Harness-hosted: consume every message in the participant's room,** so
  the harness never runs its agent on one by itself. The harness then sees
  only the turns your driver starts. Consume the message even when handing it
  to the library fails: a harness that answers a person directly bypasses the
  room, and its silence marker may turn into a visible warning on a person's
  turn.
- The room includes the places nested in it: a thread under the channel, a
  topic in the group (unless `binding.threads_in_room` is `false`, step 1).
  Consume their messages and set `thread_root_event_id` to the thread's root:
  the message that started it, or the platform's own id for the thread when no
  message did. A message the harness itself moved into a new thread is that
  thread's start and stays where it was posted. Answer in the thread where the
  harness lets you: a library-hosted integration puts a reply, post or
  reaction about a message in a thread into that thread
  (`nunchi.integrations.discord_participant_transport.thread_of` for
  Discord). `dispatch` gets the turn's wake with `events` widened to every
  message the turn showed the agent (a look-again, steering, a history page,
  its memory), so a transport reads the thread of the message a move is about
  however the agent saw it. A harness-hosted plugin starts every turn in the room's main chat,
  so there the agent's answer to a thread message is posted in the main chat,
  not in the thread; record that in the integration's known gaps.
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
    guard=participant.guard,  # after the TurnServer, if you serve one (step 2)
)
```

- `transport`, library-hosted: your platform transport. Its
  `dispatch(action=..., wake=...)` posts a `message`, `reply` or `reaction`
  and returns a `TransportResult` (`nunchi.participant`): `sent`, `failed`,
  `unknown` or `unavailable`, with a detail. If it holds a secret, give it
  `withheld_values()` and `credential_patterns()` (step 2).
- `guard`: the room's host checks every action against it before dispatch.
  A refused action posts nothing, and its result is `failed`. A reason
  (`why`) that holds a secret is dropped and the move goes on: the reason
  never reaches the room. Without a guard the room builds one with
  `room_guard`.
- `transport`, harness-hosted: `HarnessDelivery(native, room_shows_own_messages=...)`.
  The harness posts messages. In final-answer posting the answer is a
  message, never a reply to a chosen message. `room_shows_own_messages` says
  whether the room events you deliver include the agent's own messages (step
  7). `native` is optional; give it if the harness lets a plugin react. It
  has three methods:
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

1. The runtime reads the config into `RoomSettings` and builds a
   `GatedParticipant` (a `TurnParticipant` whose driver writes to a dedicated
   Claude Code session).
2. It builds the gate's `TurnServer`, with a per-launch secret passed to the
   session's environment. The server adds that secret to the participant's
   guard: the agent can read it, but cannot post it. Then the runtime builds
   a `Room` with the shared Discord transport and the participant's guard,
   and the gate serves the socket when it starts.
3. The mod, at session start, calls `/v1/attach` and registers the room tools.
4. For each turn, the driver submits the core's `WAKE_MARKER` with the
   turn's wake id, then `turn.text`, to the session.
5. The mod's `turn.start` hook reads the wake id and binds with the session's
   turn id (`/v1/turn-start`).
6. The mod forwards room tool calls (`/v1/tool`). After every tool call it
   asks `/v1/news` and adds the update to the result's context.
7. The session's end of turn comes back on its stream, and the gate calls
   `turn_ended` with the session's final message as the note.

The room connection is shared: `nunchi.integrations.discord_room.DiscordRoomConnection`
registers the participant with the shared Discord transport and checks its
attestation, validates each event, marks a continuity gap after each
(re)connect, hands events to `room.deliver`, and reconnects. Build the `Room`
with `connection.transport`, `attach` the room, and call `serve`. The Claude
Code runtime and the Codex runner (`codex_app_server.runner`) both do.

**The client rule: open the stream before registering.** The transport's MCP
server keeps no event store, so a notification sent to a session whose
notification stream is not open is dropped. A client that talks to the shared
transport itself (not through `DiscordRoomConnection`) therefore does, in this
order, on every (re)connect: connect (`StreamableMCPClient.connect`), open the
notification stream (`open_stream`, which returns once the server has it),
mark a continuity gap (a fresh listener cannot know what it missed before it
was listening), register the participant, then read the stream
(`notifications(stream)`). It also treats the end of the stream, or an error
reading it, as an interruption: it marks a gap and reconnects. A client that
registers first is not silently dropped on a current transport, which fails
those deliveries and tells the next listener with a gap, but it still loses
the message.

`nunchi.integrations.codex_app_server` is the protocol-harness example: its
driver starts each run with `turn/start` and binds it from the answer, the
room tools come from a per-thread MCP server that forwards to `TurnServer`,
steering goes in with `turn/steer`, and `turn/completed` ends the run.

## Walkthrough: harness-hosted, final-answer posting

The consume-and-start shape, with hook names generic. The contract's parity
table names the Hermes hooks for each step.

`nunchi.integrations.hermes_plugin` is the worked example.

1. **Load.** The plugin reads its config into `RoomSettings` and builds a
   `TurnParticipant` with the harness's silence marker, its other silent
   answers (`also_silent`) and `model_text=True`. It registers the
   reaction and room-view tools from `participant.attach()`, and forwards
   their calls to `call_tool`. It builds the `Room`, with `HarnessDelivery`,
   on the first message the gateway admits.
2. **Ingress.** Every message in the room, and in the threads inside it,
   reaches the plugin's ingress hook, once the harness's own gates are open
   for the room (on Discord, Hermes's `free_response_channels` and its
   allowlist), except what the harness drops whatever its settings (the
   plugin's known gaps). The plugin
   hands it to `room.deliver` and tells the harness it is handled,
   with no reply, even when the hand-over failed. Give the room every fact the
   harness has: who a message mentions, the message it replies to, when it was
   sent, and whether its author is a bot. When the ingress hook's payload
   lacks them, look for an earlier hook that has them: the Hermes plugin
   notes them in `pre_gateway_dispatch`. A message whose mentions are missing
   reads as addressed to nobody.
3. **Start.** The library calls `driver.start(turn)`. The driver asks the
   harness to start a run with the core's `WAKE_MARKER` and `turn.text`, as
   the plugin's own message.
4. **Bind.** The first hook that sees the run, before the model call, reads
   the marker and binds the run if the id is the open turn's. It maps the
   session and task keys that tool handlers get to the run's id.
5. **Steering.** The tool-result hook adds `news(turn_id=…)` to each result.
6. **Finish.** The hook after each model response reports what the model
   wrote with `model_wrote`: its text, and its reasoning with
   `reasoning=True`. The hook before each model request reports the part of
   a cut answer Hermes kept. The output hook calls `finish` with the raw
   answer, thinking included, and returns `decision.text` for `deliver`, or
   the silence marker otherwise. For `continue`, it notes the fresh run to
   start.
7. **End.** The run-end hook starts the noted fresh run, which step 4 binds
   with `wake_id=None`. With none pending, it reports the end with
   `end_turn`. A harness may drop a run without its end hook, as Hermes does
   when the provider refuses for good. Watch its error hook, and end the turn
   as failed only once no new model request has started: within 5 s of an
   error Hermes will not retry (a fallback provider may take over at once),
   or within 130 s of a retryable error with its retries spent (Hermes's
   recovery ladder waits up to 120 s). Each new request cancels the wait.
   Otherwise the turn holds up the room until the library's deadline.
8. **Cancel.** Hermes cannot interrupt a plugin's run, so `interrupt` does
   nothing: the library closes the cancelled turn, `finish` answers `silent`,
   and step 6 returns the silence marker. Tools already run stay run. The
   parity table records the gap.

What the Hermes plugin cannot stop: on a failed run, Hermes posts its own
failed-turn notice, after `[SILENT]` when the output hook ran. The plugin's
README lists this and its other known gaps.

## Outside Python

`nunchi.turn_server.TurnServer(participant, socket_path=..., session_secret=...)`
serves the same calls as JSON over a Unix socket (`I-040D
LocalTurnProtocolV2@2`):

| Route | Body | Answer |
|---|---|---|
| `/v1/attach` | `{}` | `protocol`, `version`, `posting`, `silence_marker`, `model_text`, `tools` |
| `/v1/turn/bind` | `turn_id`, `wake_id` | `bound` |
| `/v1/turn/call` | `turn_id`, `tool`, `input` | `ok` with `text`, or `error` |
| `/v1/turn/after-tool` | `turn_id` | `text` or null |
| `/v1/turn/model-text` | `turn_id`, `text`, `reasoning` (optional) | `kept` |
| `/v1/turn/finish` | `turn_id`, `answer` | `finish` (`deliver`, `continue`, `silent`) and `text`; `failed` when the answer was not the model's |
| `/v1/turn/end` | `turn_id` (optional), `ok`, `detail`, `note` (optional) | `ended` |

- When `attach` answers `model_text: true`, send each model response to
  `/v1/turn/model-text` before `/v1/turn/finish` (step 4, "Report what the
  model wrote"), and its reasoning in a report of its own with
  `reasoning: true`. A `finish` answer with `failed` means the turn failed: post
  nothing, and say why in your logs.

- Every request carries the launch secret in `X-Nunchi-Session`. Others are
  refused.
- The server adds the launch secret to its participant's guard
  (`TurnParticipant.withhold`), so a room action that carries it is refused.
  A secret shorter than 16 characters is refused.
- The socket's directory is private to the integration's user.
- Requests are at most 256 KiB.
- A Unix socket's path is at most about 107 bytes (103 on macOS). Put the
  socket in a short private directory, such as one under `XDG_RUNTIME_DIR`
  or `/tmp`, never deep in a state directory.
- Offer each caller only the routes it needs. When your driver binds and
  ends turns itself, a tool bridge needs only attach, call and after-tool:
  subclass `TurnServer` and refuse the rest in `route`, as the Codex
  integration's `RoomToolServer` does.

Give the secret only to the harness process you start, through its
environment or its server configuration. Keep it out of the agent's view
where the harness lets you. Claude Code cannot: the mod reads it from the
session's environment, so the agent can read it with a shell command. Codex
gives it to the room's MCP server, whose environment a command outside
Codex's sandbox can read. The guard still keeps it out of the room.

## Prove it

Every integration joins the turn conformance kit before it replaces anything.

1. Write a `KitIntegration`: an object with `name`, `posting` (`tools` or
   `final-answer`), `participant(profile=, guard=, agent=, privileged=False)`
   and `close()`. `participant` returns your participant, wired so that each
   turn the library starts plays the scripted agent's next turn through your
   integration's own surface: your hooks, your socket, your tool
   registration.
   - Your surface implements `bind`, `read` (the turn's text as your harness
     gave it to the model), `call`, `after_tool`, `finish` and `end`.
   - Start each turn's script once. If you learn of a turn from something that
     repeats within it, such as each model request, use
     `agent.play_once(key, make_surface)` with the library's turn as the key,
     as the Hermes and Codex kits do.
   - With `privileged=True` the kit's room authorizes privileged actions:
     offer `propose` and `withdraw`, as you would with an `authorization`
     section.
   - If your harness holds a launch secret (you serve `TurnServer`), set
     `launch_secret` on your `KitIntegration` in `participant`. The
     `launch-secret` scenario then has the agent post it. Without one, that
     scenario is not applicable.
   - In final-answer posting, if your harness can end a run with its own
     text in place of an answer, set `harness_text = True` and give your
     surface `stand_in(turn_id, text, wrote)`: the model writes `wrote` ("" for
     nothing), and the harness ends the run with its own text. Use the
     harness's real path, as the Hermes kit does: a budget of one model call
     when the model wrote something, empty model replies when it wrote
     nothing. The harness's own words may stand in for `text`. Return what
     the harness posted, `("silent", "")` for nothing: the kit checks that
     it posted nothing. Without it, the `final-not-own-words` and
     `final-no-answer` scenarios are not applicable.
   - `final-silence-forms` plays the first answer your participant lists in
     `also_silent`, and skips that play when it lists none.
   - Give your `KitIntegration` a `visible()`: everything the harness itself
     showed the room in the scenario just played, outside the library's
     transport, the answers it posted for the library included. Return a
     list of `{"kind": "message", "text": ...}`,
     `{"kind": "reaction", "reaction": ...}`, `{"kind": "typing"}` and
     `{"kind": "thread"}`, with `"where"` naming the chat if you like. The
     kit calls it before `close()`. Record it where the harness would reach
     the platform, as the Hermes kit's recording adapters do. If the harness
     reaches the room only through the library's transport (your tools),
     return `[]`, as the Claude Code and Codex kits do. The kit compares it
     with what the library committed: anything else is a leak, and so is a
     committed post that names Nunchi's machinery (`machinery_in`, with the
     turn's request id and your room tools' names when they are
     identifiers, such as `room_send`). A leak fails the scenario. Without
     `visible()` committed posts are still counted, and the leak count says
     what the harness showed is `n/a`.
   - What the harness shows that nothing public can stop, declare in
     `known_gaps`, a list of `nunchi.turn_conformance.KnownGap`: the
     `reason` (why nothing stops it, and where you document it), the
     `scenarios` it shows in, its `kind`, and for a message part of its
     `text`. A declared leak makes the cell `gap`, never `pass`; anything
     else the harness shows still fails. A harness that changes the agent's
     post before your hook sees it declares a `KnownGap` of kind `post` for
     the scenarios whose checks fail because of it, with the harness's own
     change as its `transform` (for Hermes, its `strip_think_blocks`): the
     cell reads `gap` only when the room got exactly that change of the
     agent's answer, and any other change fails. Document each gap in your
     README and in the contract's candidate gaps first. `HERMES_KNOWN_GAPS`
     in `nunchi.integrations.hermes_plugin_conformance` is an example.
   - Set `model_failure = True` and give your surface `fail(turn_id)`: the
     agent's model call fails the way it does in your harness (HTTP 400
     from your model stub, a failed result on the harness's own stream), and
     the harness ends the run as it would. The kit checks that the turn ends
     as a failure before the library's deadline and that nothing reaches the
     room. Without it, `harness-failure` and `final-harness-failure` are not
     applicable.
   - Library-hosted: run the harness for real when it speaks a protocol, and
     stub only its model, as `nunchi.integrations.codex_app_server_conformance`
     does; scripting the harness process would skip the protocol under test.
     Where the harness is a session your runtime drives through its own mod,
     script the model and the session process, as
     `nunchi.integrations.claude_code_conformance` does.
   - Harness-hosted: the harness is real, and the scripted agent is its
     model. Stub the model at its API, for example a local OpenAI-compatible
     endpoint configured as the harness's provider. Do not replace the
     harness's run loop: that skips the hooks under test. Tell your agent's
     model calls apart from the harness's own, such as session titles. See
     `nunchi.integrations.hermes_plugin_conformance`.
   - The kit builds its own `Room` around the participant you return, so your
     integration must work with a room it did not build.
   - The kit calls `participant()` once per scenario on the same
     `KitIntegration`, and `close()` after each.
   - If your integration binds runs itself, the scripted agent cannot leave a
     run unbound. Play a script with no `bind` step as a real way a run goes
     unbound for your harness: the Codex kit disables the room's MCP server,
     so the room tools never arrive.
   - A model stub answers only the newest call: the harness abandons calls
     on interrupt or when its process dies.
2. Expose `conformance_integrations()` in that module.
3. Run it:

   ```sh
   nunchi-turn-conformance --integration reference --integration your.module
   ```

4. Add the command to CI on a clean install, with the harness pinned.
5. Put the generated table in [`harness-contract.md`](harness-contract.md),
   "Conformance kit". A failing cell is a gap in
   [#135](https://github.com/mentatzoe/nunchi/issues/135), not a reason to
   skip the scenario. A `gap` cell is a known gap your integration declared.

The kit owns the room, attention, the host and the checks, and builds them
with the same `Room` your integration uses. What it does not cover, test
through your harness in your own tests, as `tests/v2/test_hermes_plugin.py`
does:

- its `arrive` step records a message in the room log directly, not through
  your ingress, so its leak count never sees what your harness shows on a
  person's message (processing reactions, typing, command replies);
- its room takes reactions itself, so your harness's own reaction path goes
  untested there;
- its final-answer scenarios use no room view and no steering.

Before importing or starting the harness in a test, point its home and
temporary directories at a throwaway directory. Otherwise the harness may
write into the user's own home: Hermes writes into `~/.hermes` on import. For
a harness you run as a process, start it in its own process group and kill
the group: npm's `codex` is a launcher with a child.

## Known library gaps

- **Steering marks messages as shown before delivery.** A `turn/steer` that
  fails because the run just ended loses that update.
- **Unknown mentions.** A canonical event cannot say that its mentions or
  reply target are unknown, only that there are none.
- **One text per turn.** The turn's guide and its context come as one text
  (`turn.text`), so a harness's stable system-prompt slot cannot hold the
  guide alone.

Each is tracked in [#135](https://github.com/mentatzoe/nunchi/issues/135).

## Checklist

- [ ] Public extension points only; nothing patched.
- [ ] Everything the harness shows by itself besides the agent's own acts is
  off for the room, documented with the reason and tested; what nothing can
  stop is in the integration's known gaps, and declared to the kit
  (`known_gaps`). The kit's `visible()` reports everything the harness
  showed in the scenarios the kit plays.
- [ ] Everything the harness drops or does before your ingress hook is open
  or off for the room, tested through the harness's real ingress; threads
  and topics inside the room are consumed as the room's, and
  `binding.threads_in_room` is honored.
- [ ] No decision about whether or what the agent says.
- [ ] Every room event delivered, the agent's own included.
- [ ] Every run bound when it starts, and its end reported once, also when
  the harness drops the run without an end hook.
- [ ] Final-answer posting: every silent answer of the harness in
  `also_silent`, and what the model wrote reported (`model_text`) if the
  harness can answer for it. The output hook fails closed.
- [ ] Steering after every tool call, where the harness has a hook for it.
- [ ] The guard comes from `room_guard`. The `Room` gets the participant's
  guard, built after any `TurnServer`.
- [ ] Library-hosted: every variable the config names in a `*_env` key is
  out of the harness's environment. Harness-hosted: the README says which
  keys live in the harness's process.
- [ ] A library-hosted runner calls `keep_private()` first; an integration
  inside the harness's process does not.
- [ ] The conformance kit passes on a clean, pinned install, in CI, with the
  harness's home isolated.
- [ ] The parity table updated, and gaps filed in #135.
- [ ] The integration documents itself under `integrations/`.
