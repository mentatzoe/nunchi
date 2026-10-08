# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nunchi V2 is on `main` and is **merged, unverified**: deterministic tests and
installed stock-Hermes checks pass, but no surface has live real-room proof
since PR #67, and V2 is not released. The last release tag is `v0.2.0`.

### Added

- The Hermes plugin tells the room who a message mentions, which message it
  replies to, when it was sent, and whether its author is a bot (#135 gaps 9
  and C). Hermes's admission payload carries none of these, and on Discord
  Hermes takes the bot's own mention out of the text, so a message naming the
  agent read as addressed to nobody. The plugin now notes them in
  `pre_gateway_dispatch`, from Hermes's `MessageEvent` and the platform's
  message (Discord mentions and `@everyone`, Telegram text mentions, the
  author's bot flag), and a message the platform says was meant for the bot
  mentions the agent. Under `plugins.isolation: host` the platform's message
  does not cross, so mentions, the bot flag and the time stay unknown there.
- The agent's own "mhm" in the turn conformance kit (#94 step 9d): the kit's
  room offers one reaction, and the `mhm` and `final-mhm` scenarios check it
  through each integration's react tool. The pause scenarios now also check
  that the turn after the pause remembers why the agent waited. The reference
  turn, the Claude Code gate, the Hermes plugin (Hermes main `a50406d9`) and
  the Codex app-server integration (Codex CLI 0.160.1) passed all 21
  scenarios the kit had then. The behavior scenes' four moves (speak, stay
  quiet, wait, mhm) and their pause and outcome moments each have a scenario
  through every integration, so the kit does not replay every scene moment.
- A silent turn's reason in tool posting (#135 gap H): `end_turn` and
  `turn_ended` take the agent's last words as `note`, and the local turn
  protocol's `/v1/turn/end` an optional `note`. When the turn ends without a
  room action they are its silence's reason, which later turns and attention
  see, as `<thinking>` is in final-answer posting; they are never posted, and
  words that hold a withheld secret are not kept. The Claude Code gate passes
  the session's final message, and the Codex app-server integration the
  run's last agent message. The tool-posting guide now asks the agent to say
  why in its last words when it stays quiet. The turn conformance kit's new
  `silence-reason` scenario passes through the reference turn, the Claude
  Code gate and Codex CLI 0.160.1.
- Pause and outcome turns in the turn conformance kit (#94 step 9d): four
  scenarios, two per posting style, in which the library starts a second
  turn with no new message, after a pause and after an operator approves an
  action the agent proposed. The agent must get the turn through the
  integration, read in its text that it is a pause or an outcome turn, and
  be able to post. The scripted agent plays one script per turn the library
  starts, surfaces report the turn's text (`read`), and `participant()`
  takes `privileged=True` for a room that authorizes privileged actions.
  The reference turn, the Claude Code gate, the Hermes plugin (Hermes main
  `a50406d9`) and the Codex app-server integration (Codex CLI 0.160.1) all
  pass. The Hermes plugin looks again after a pause, which the older Hermes
  integration never did.
- One room connection for every library-hosted integration (#94 step 9e):
  `nunchi.integrations.discord_room` registers the participant with the
  shared Discord transport and checks its attestation, validates each
  notification, hands events to the `Room`, marks a continuity gap when the
  stream is uncertain, and reconnects. The Claude Code runtime uses it
  instead of its own copy.
- A live runner for the Codex app-server integration (#94 step 9e):
  `nunchi-codex-app-server-runner` runs one participant in one Discord room on
  that shared connection, with Codex taking the turns. The transport's key is
  withheld from Codex and refused in the room. Not yet run in a live room.
- The harness guide after its second test (#94 step 9e): binding from a
  protocol's own answer without a marker, only once the room tools reached
  the run, and the two start races; room tools from an MCP server through the
  local protocol, never behind the harness's approval; steering as input;
  what to withhold; the profile file; Unix socket path limits and route
  restriction; the library-hosted room connection; and proving a protocol
  harness for real. A driver's `ready()` returning False without a cancel now
  fails the turn instead of reading as the agent's silence.
- The Codex integration through `codex app-server` (#94 step 9e,
  [`integrations/codex-app-server/`](integrations/codex-app-server/README.md)),
  built by a separate agent from the harness guide: library-hosted, tool
  posting, on the app-server's public JSON-RPC protocol only. One thread per
  participant with the user's own Codex configuration; the room tools come
  from a per-thread MCP server in the thread's own `config`, which forwards
  each call over the library's local turn protocol with Codex's turn id;
  `turn/start` starts and binds each run, `turn/steer` carries steering after
  Codex's own tools, `turn/interrupt` cancels, approval requests are
  declined, and the project's trust level rides in the thread's config, so
  Codex never writes into the user's `config.toml`. It passes every
  tool-posting scenario of the conformance kit against a real
  `codex app-server` (Codex CLI 0.160.1) with only the model scripted, and CI
  runs the kit and its tests on a clean, pinned install. No live runner yet;
  the older Codex integration stays until there is one.
- Attention on Hermes's own model in the Hermes plugin (#94 step 9e): an
  attention model of kind `hermes-host` asks Hermes (`ctx.llm`) for the
  configured provider and model, through the core's
  `HostStructuredAttentionModel`, so a Hermes room needs no separate
  attention credentials. A refusal says how to allow the model under
  `plugins.entries.nunchi-room.llm`.
- The agent's own message in the room log, when its harness never shows it
  (#94 step 9e): `HarnessDelivery` now takes `room_shows_own_messages`. When
  it is false, as for Hermes, the host records each message it committed for
  the harness as the participant's own event, with an id of the library's own
  (`nunchi:delivered:<request_id>`), in reply to the message the turn was
  about. Threads, the room's pace, attention and memory then count it, so a
  question the agent answered no longer looks open on the next turn. The
  Hermes plugin's expected failure for this gap now passes.
- The Hermes plugin (#94 step 9e, [`integrations/hermes-plugin/`](integrations/hermes-plugin/README.md)):
  `nunchi-room`, a Hermes directory plugin on Hermes's public hooks only,
  built by a separate agent from the harness guide alone. It consumes every
  message in the bound chat (`post_gateway_admission`), starts the agent's
  turns with `ctx.inject_message`, binds each run by its wake marker, adds
  steering to tool results, hands the final answer (thinking included) to the
  library, and reacts through `ctx.platform_actions`. It passes every
  final-answer scenario of the conformance kit inside a real Hermes gateway
  (main `a50406d9`) with only the model scripted, and its own tests cover
  ingress, steering, the room view, reactions, looking again with a fresh
  run, and `plugins.isolation: host`. CI runs both on a clean, pinned
  install. Not yet run live; the older Hermes integration stays until it is.
- One turn at a time, whatever the harness reports (#94 step 9e): a
  cancelled turn now closes, so the run's late calls find it closed; the
  next turn waits for the previous run's end instead of failing, and closes
  it as a failure after `previous_turn_grace_seconds` (30 s) if the end never
  comes; `bind_timeout_seconds` fails a run the harness accepted but never
  started.
- The harness guide, after its first test: what a harness may post besides
  the final answer, binding only your own runs, mapping run ids, handing
  over the raw answer, hook timeouts, the `HarnessDelivery` native
  interface, harness-model attention, where to build the `Room`, catch-up
  turns, and how to prove a harness-hosted integration.
- Cancellation in the turn conformance kit (#94 step 9d): a cancelled turn
  posts nothing, in both posting styles (`cancel`, `final-cancel`). The
  reference turn and the Claude Code gate pass.
- Memory of a message the harness posted (#94 step 9d; `I-010A@7`,
  `I-010C@14`): when a harness posts the agent's final answer itself and
  never shows that message back (Hermes hides its agent's own messages from
  plugins), the host remembers it by its text and time, after the message
  the turn was about, until the room shows it. A `message` own move may now
  lack `event_id`. The conformance kit's final-answer delivery checks it.
- The harness guide (#94 step 9d, [`docs/harness-guide.md`](docs/harness-guide.md)):
  how to make a harness use Nunchi, for either topology and either posting
  style, with the rules, each library piece, two walkthroughs, the local
  protocol, and how to prove an integration with the conformance kit.
- `nunchi.room` (#94 step 9d): `RoomSettings` checks the shared config
  sections once, and `Room` builds everything the library owns for one
  participant in one room (observation, attention, the scheduler, the turn
  host, authorization, the pipeline and the delivery lane) from the
  integration's participant, transport and event visibility. The reference
  adapters, the Claude Code and Codex runtimes and the turn conformance kit
  use it, instead of four hand-wired copies that had drifted. State files
  keep their names; a new state directory is created private (0700).
- The turn conformance kit (#94 step 9d): `nunchi-turn-conformance` plays a
  scripted agent's turn through an integration's real path and checks the
  turn's rules: one post and its result, silence only when bound, an unbound
  turn failing, looking again, steering, one action per turn, the secret
  guard, and final-answer delivery, silence, looking again, thinking and the
  secret guard. Its output is the parity table. The reference turn and the
  Claude Code gate, driven over its socket as the mod drives it, pass every
  scenario for their posting style; CI runs the kit on a clean install. A
  harness can end its agent's turn without naming it (`end_turn`, and
  `/v1/turn/end` without `turn_id`), so a turn that was never bound ends at
  once as a failure instead of waiting for the deadline.
- The local turn protocol (#94 step 9c; `I-040D LocalTurnProtocolV2@1`):
  the core `Turn` as versioned JSON over a private Unix socket, for
  harnesses outside Python. `nunchi.turn_server` serves attach, bind, call,
  after-tool, finish and end for a `TurnParticipant`, with the per-launch
  session secret on every request. The Claude Code gate's server is now
  this one, and the mod's route names remain aliases. `TurnParticipant`
  gains `attach`, `tool_specs` and `end_turn`. `I-040A` is at `@4` for the
  host's `settle`.
- Final-answer posting gives the agent a private place to think (#94 step 9c
  follow-up): text inside `<thinking></thinking>` is never posted and becomes
  the move's reason in memory, as `why` does in the envelope. In run 58, with
  nowhere else to reason, the agent put its deliberation in its post 70 times
  in 111. A silence marker on a line of its own is silence, and the behavior
  eval keeps each plain reply and counts posts that name Nunchi's machinery.
- Final-answer posting in the core `Turn` (#94 step 9c), for harnesses whose
  agent's final answer is its post, such as Hermes. `Turn.decide` and
  `Turn.finish` say whether an answer is delivered, looked at again, or
  silent; the harness posts only what the host committed for it through the
  new `HarnessDelivery` transport. `OpenAICompatibleParticipant` takes a
  `silence_marker` to post its plain reply this way, and the behavior eval
  measures the style with `--agent-posting final-answer`. The eval workflow
  gains an `agent_posting` input and accepts `agent_model: none` for an
  attention-only run, since an empty input fell back to the default agent.
- Behavioral evaluation (#86): scenes in `evals/behavior/` that judge whether
  a participant reads the room, with ranges of fitting moves instead of one
  expected verdict. Eight scenes come from `docs/behavior.md`; 57 are drafts
  converted from the V1 litmus corpus. The moves are stay quiet, mhm, wait
  and speak; speaking covers asking, so V1's ASK and SPEAK both map to
  speak. The runner drives the production
  observation and attention path against OpenAI-compatible models, reports
  per-model spread, and never writes its key. Any failed call fails the run
  and is listed first in the summary; a rejected reply is kept with its
  reason, and calls to one model at a time are capped. Each moment runs
  through Nunchi's pipeline; with `--agent-model`, a model plays the woken
  agent's turn through the shared participant protocol, its move is graded,
  and pile-ons are reported. Each agent turn records how it got its turn
  and what reading came with it, and keeps a reply the turn protocol
  rejects. `--paired` plays every turn that carried a
  reading a second time on the same wake without it, graded but never sent,
  so a run shows what the reading changed. Nunchi never nods for the agent:
  any "mhm" is the agent's own. Models named `typesafe/...` go to Jev, a typed decision model, through
  OpenRouter's Decisions API: a prototype route that answers six typed
  questions about the judged message and writes the agent's reading from
  them, so Jev's speed and fit can be compared with the LLM routes. The
  manual `behavior-eval` workflow runs it through OpenRouter, Jev included.
- Two more attention routes (#94 step 8, #87), as kinds outside the core:
  `messages-api` through the Anthropic Messages API and `responses-api`
  through the OpenAI Responses API. Both send the core's prompt, observation
  text and answer schema, ask the API to hold the reply to the schema in the
  subset structured output accepts, and hand the reply to the core's
  decoder. The adapter runtime, the Claude Code gate and the Codex runner
  offer both beside `decisions-api`; the behavior eval sends a model's
  attention through one when its name starts with `messages:` or
  `responses:`.
- Shared V2 runtime: canonical bounded observation and continuation,
  participant-shaped attention, a coalescing opportunity scheduler (one active
  opportunity plus the newest pending event), participant wake and silence,
  staged receipts, execution-time privileged authorization, the shared Discord
  MCP transport, the CLI, and generic, Discord, Matrix, and Telegram reference
  adapters.
- Shared core and operator foundation (PR #67): one versioned participant
  protocol (`nunchi.participant-turn` v1), first-class ACK that adds one exact
  reaction or widens to DEFER when unsupported, one operator schema shared by
  the CLI and dashboard, guided setup with automatic integrity pins, and
  persistent `launchd`/`systemd` service supervision.
- Hermes integration (PRs #36, #83, #84): a plugin around stock Hermes 0.19.0
  or newer for configured Discord and Telegram rooms, with stock tools and
  approvals behind plugin-owned guards, ACK, and a reversible stopped-profile
  lifecycle. CI installs stock Hermes 0.19.0, 0.21.5, and current Hermes `main`
  and runs the host-contract lanes, plus normal-attention and startup lanes on
  Discord.
- Codex room runner in a reduced mode: Discord only, with Codex tools, skills,
  plugins, and MCP disabled.
- Claude Code gate and mod (#43): one gate per room starts a dedicated Claude
  Code session that keeps the user's configuration; a Nunchi mod in that
  session registers the room tools and binds each turn to its wake. The core
  gains host-neutral helpers for participants that act through tools.
  Discord only, no live proof yet.
- Deterministic lifecycle evaluation (11 scenarios), adversarial runtime
  coverage, clean-artifact probes, and the platform interface and conformance
  contract.

### Changed

- The rules of a turn for agents that act through tools live in the core,
  in `nunchi.turn` (#94 step 9c): binding a model turn to its wake, one room
  action per turn, looking again before the first post, steering, silence
  only for a bound turn, and the secret guard. Before, they lived only in
  the Claude Code gate, so no other harness could use them. The gate now runs
  on the core `Turn` and keeps only its session, the mod's tool names, and a
  platform token's shape for the guard. `ParticipantTurnHost` tells a waiting
  participant what became of its action (`settle`), which the gate's own
  host subclass did before. Behavior is unchanged.
- The one-reply turn (`ParticipantTurnProtocol`, used by the behavior eval
  and Codex) drives the same core `Turn` (#94 step 9c), so the eval measures
  the rules every harness gets. Looking again before the first post is now
  one implementation. A one-reply participant may pass a `SecretGuard`: a
  refused action is shown to the model once, and a second refusal fails the
  turn. A failed look-again now lets the action go instead of failing the
  turn, as it already did for agents that act through tools.
- The agent's turn guide says what `docs/behavior.md` already holds: one
  clarifying question beats a guess (#94, step 6 follow-up). Both turn
  prompts now say to state only what the agent knows, to say so, ask, or
  offer to check when it has not checked, and that "not yet" answers someone
  asking for news, where silence leaves them waiting. Run 46 showed why: in
  `asked-while-busy`, 8 of 10 replies on one route stated a fact the agent
  could not know. And in `mention-in-busy-room` the agent often stayed quiet
  for lack of findings.
- The Claude Code participant hears what others post while it works (#94,
  step 6; Zoe, 2026-10-06). After each tool call the main session makes in
  a room turn, the mod asks the gate what others posted since the session
  last looked, and a new message rides that tool's result as context the
  model reads. The core's room view gains a host-only `news` direction, like
  `new` but never counted against the participant's own checks and never
  offered to a model. Each message is shown once, may be answered, and no
  longer holds the first post. Before, the session saw such a message only
  when it was about to post. Codex and the generic runtime do not steer yet,
  and how a live session takes the update needs a live run
  (`docs/claude-code-live-run.md`, scene 7a).
- The newest message after a busy turn is judged with the messages it
  replaced, as one moment (#94, step 6; Zoe, 2026-10-06: a person catching
  up reads the newest message and glances back). The attention request lists
  them newest first (`unattended_event_ids`, `I-010A AttentionRequestV2@6`),
  and attention answers one more question, only then: which of them still
  calls for the participant (`calls_for_participant`, `I-010B
  AttentionDecisionV2@8`), on the chat and the typed route alike. Step 1
  never hides a moment that names one, the reading names that message first,
  and the turn lists them too (`I-010C ParticipantWakeV2@12`) and may reply
  to any. Run 45 showed why: in `asked-while-busy`, with only Zoe's "Thanks!"
  judged as the moment, Vigil answered Sam's mid-turn question 3 or 4 times
  in 10. Scenes can now mark events as `unattended`, and the suite feeds them
  through the scheduler while a turn runs.
- Messages that arrive while the agent is mid-turn are judged for its memory
  (#94, step 6). Only the newest still gets the next opportunity, but before
  it is judged, up to 3 of the messages it replaced are judged for the memory
  alone (`MIDTURN_RECALL_LIMIT`), so a question Sam asks while Vigil is
  answering Zoe starts a thread that the newest message's judgment and
  Vigil's turn both see. Before, those messages were never judged and started
  no thread. Together they get one attention timeout, so a slow provider
  delays the newest by at most that. A failed judgment is skipped, and cancel
  and restart forget them. The behavior suite already judged every earlier
  message as if live, so this brings the runtime in line with what the suite
  measured; a new scene, `asked-while-busy`, measures the case (74 scenes).
- A participant's result needs only its request's `request_id` in
  `binding`; the host fills in the rest from the turn's own binding (#94,
  step 3). A binding field the result does carry must still match exactly,
  and an unknown one is refused. Runs 20 to 39 lost 16 agent turns, 15 of
  them posts, because the model dropped a field of its own turn's binding or
  garbled one of its long IDs. Seven were the report Vigil owed Zoe in
  `build-finishes-long-after-promise`. The turn prompt and
  action schema now ask only for `request_id`; `nunchi.participant-turn`
  stays version 1, since every full binding is still accepted. They also
  say what `origin_event_id` is: the message that prompted the action,
  usually the trigger. Without the trigger in the binding to copy from, a
  model put the `request_id` there in 2 of 486 moments (run 41).
- Attention reads a message with the agent's memory (#94, step 6). The
  attention request carries the same memory the agent's turn gets
  (`I-010A AttentionRequestV2@5`), for every judgment including recalled
  ones, and the attention prompt explains it only when it is there. A typed
  model does not get it yet: with it, Jev's own top move fit fell from 186
  to 175 of 231 moments (run 37), and it still hid the promised CI line. Each of the agent's moves about a message now
  also says who wrote that message and what it said (`about_author_id`,
  `about_text`; `I-010C ParticipantWakeV2@11`), so "I'll tell you when it
  finishes" still makes sense after Zoe's request has left the window. An
  action may reply or react to a message the turn's memory points at, as
  to one in its window: run 38 showed an agent replying to the request it
  remembered and being refused.
- Step 1 no longer hides what the judgment itself would speak to (#94,
  step 6). A "not conversation" answer suppresses only when the judgment's
  most likely move is not to speak. Run 35 showed why: a CI line saying the
  nightly passed, which Vigil had promised to report to Zoe, was read as
  not conversation (about 0.1) while the most likely move was to speak
  (0.8 to 0.9), so all 20 judgments hid it from the agent. Two scenes
  measure it, `build-finishes-after-promise` (the promise in the window)
  and `build-finishes-long-after-promise` (the promise only in the agent's
  memory, 73 scenes).
- The agent reports an approved action's outcome itself (#94, plan step 6;
  Zoe, #90 decision 2 on #94). When an operator's approval settles a
  privileged action after the agent's turn about it ended (done, failed,
  unknown, or denied at the recheck), the authorization coordinator tells
  its outcome listeners, and the delivery lane gives the agent a turn about
  the message it proposed the action for, with `occasion: "outcome"`
  (`I-010A AttentionRequestV2@4`, `I-010C ParticipantWakeV2@10`), as soon
  as nothing else is running. Attention reads the room as advice; a
  SUPPRESS or ACK judgment widens to DEFER with the new `outcome-turn`
  cause (`I-010B AttentionDecisionV2@7`, `I-010E AttentionReceiptV2@4`),
  and an attention error still gives the turn. Nunchi never reports the
  outcome in the room. Only a participant that may propose hears about
  outcome turns in its prompt, which names each way an action can end
  (done, failed, unknown, denied), says nobody in the room has been told,
  and asks that what the agent says match how it ended; the outcome turn
  itself also says in a plain sentence how that proposal ended ("the
  operator approved it; it was tried and the action itself failed").
  Attention's prompt
  explains a pause or an outcome only to the judgment that has one, so
  ordinary judgments carry no occasion text. The behavior suite adds outcome moments and
  the `approval-comes-through` scene (71 scenes); `nunchi probe` reports
  the new versions.
- Nunchi looks again after a pause (#94, plan step 6, second part). When a
  judgment's most likely move is to wait, for the addressee or for the
  speaker to finish, and nothing new is said for five minutes
  (`look_again_seconds`, 0 turns it off), the delivery lane judges the same
  message again with `occasion: "pause"` (`I-010A AttentionRequestV2@3`,
  `I-010C ParticipantWakeV2@9`). The agent may get a turn that knows it is
  looking again, sees how long the room has been quiet, and remembers why it
  waited. A new message, or a move the agent sent about that message,
  disarms it; it runs only when nothing else is running, never displaces a
  newer message (the scheduler gains an idle-only offer), and happens once
  per quiet stretch. Claude Code, Codex and the generic runtime look again;
  Hermes does not yet. The behavior suite now grades pause moments instead
  of reporting them as unsupported, records `looked_again` (step 1 is
  graded `not judged` when Nunchi did not look again), and adds a
  restraint scene where looking again should still stay quiet
  (`only-they-can-do-it`, 70 scenes). `nunchi probe` now reports the
  current I-010A, I-010B and I-010C versions; they had been stale.
- The judgment and the agent's turn notice the room's pace (#94, plan step
  6, first part). Every snapshot carries `pace`: the current time, how long
  ago the judged message came, how long the room was quiet before it, its
  author's unbroken run of messages and how long that took, and the
  participant's own share of the window and its last post, in whole seconds
  (`I-010A AttentionRequestV2@2`, `I-010C ParticipantWakeV2@8`,
  `src/nunchi/pace.py`). The attention and turn prompts explain it, a typed
  model gets it in its state, and a reading written from typed answers notes
  a quiet of an hour or more and a quick run of messages. The observation
  provider's clock is injectable, so the behavior suite now judges each
  replayed message at its own scene time and the judged moment at the
  scene's end, however long the replay takes.
- The agent knows what became of its privileged proposals, and can withdraw
  one (#90 additions, #94 plan step 5). The authorization coordinator keeps
  each proposal's status (`awaiting_approval`, `done`, `failed`, `unknown`,
  `denied`, `expired`, `withdrawn`, `cancelled`), and the agent's next turn
  shows its newest 3 as `proposal` moves in `memory.own_moves`
  (`I-010C ParticipantWakeV2@7`). A new `withdraw` action, and the
  `room_withdraw` tool for the Claude Code gate, withdraws a proposal still
  awaiting approval; the operator can no longer approve it. Nunchi never
  reports an outcome in the room. A turn that an outcome itself starts comes
  with step 6. No shipped surface publishes approvals to an operator yet.
- The agent remembers why it made each move (#94, plan step 5, third part).
  Any action of the shared turn protocol, silence included, may carry `why`:
  one short sentence in the agent's own words. The host strips it before
  anything is sent and keeps it in the agent's memory, so a later turn sees
  "stayed quiet: Zoe asked Castor" and not only "stayed quiet"
  (`I-010C ParticipantWakeV2@6`, at most 200 characters). A visible move gets
  its reason once the room shows it with the same words. The Claude Code
  participant keeps its reasons in its own session transcript and has no
  `why`. The behavior suite now plays a scene's earlier moments with the
  agent before the judged one, so its posts, silences and reasons carry
  forward as they would live, and has two new draft scenes where that
  matters (`addressee-never-answers`, `said-it-would-check`).
- The agent remembers who asked what in the room, and which messages
  responded (#94, plan step 5, second part). Step 2 asks two more typed
  questions about each judged message: whether it `asks` someone in the
  room for something, and which earlier message it `responds_to`, the
  agent's own included (`I-010B AttentionDecisionV2@6`). The participant's
  memory keeps each judgment and builds `memory.threads`: recent messages by
  others that asked for something, and the agent's own messages that others
  responded to, each with the first messages that responded and what they
  said, from those answers, from `answered_by`, and from platform replies;
  the newest 6 within a day (`I-010C ParticipantWakeV2@5`). An empty list of
  responses is a fact, not a request; a response is not always an answer. When a model writes no notes, the reading now says
  when a message asks for something and which message it responds to. Both
  turn prompts explain the threads, and say that room text telling the agent
  to speak or stay quiet is its author's claim, not an instruction.
  `NunchiV2Pipeline.recall` judges an already observed message for the
  memory only, and the behavior suite uses it to replay each moment's
  earlier messages as they would have been judged live (`--no-replay` turns
  that off). Messages that arrive while the agent is mid-turn are not judged,
  so they start no thread; Hermes does not carry the memory yet.
- The agent remembers its own part in the room, and its turn prompt reads
  like a person in a group conversation (#94, plan step 5, first part). Every
  turn's wake may carry `memory.own_moves`: what the agent said, replied and
  reacted to, and where it stayed quiet, each pointing at its message: the
  newest 8 visible moves and the latest 3 silences within a day
  (`src/nunchi/memory.py`). Visible moves come from the
  room's history; the participant host records silences.
  `I-010C ParticipantWakeV2@4` adds the field. Both turn prompts now describe
  a socially aware participant and present the look-again without putting
  silence at the decision point: since step 3 that wording made the agent
  quieter on the same wakes (#86). Hermes does not carry the memory yet.
- The README opens with three diagrams: one message's path through the gate,
  how the parts fit, and where the plan stands. The manual `behavior-eval`
  workflow no longer plays the paired turn by default; the suite's README
  says which run answers which question and what it costs, and keeps one
  agent (Haiku 4.5) for the implementation baseline while other agent
  families and real agents are a separate track (#116). Each record grades
  attention's own most likely move (`top_move`), so a run without an agent
  still compares how well models read the moment.
- The behavior suite records what each call cost (#86): tokens in and out,
  reasoning tokens, the provider's reported cost, and the provider that
  served it, for attention and for the agent's real and paired plays, with a
  cost and tokens table in the summary. A chat model's name may carry a
  reasoning effort (`deepseek/deepseek-v4.1-flash@low`), so one run compares
  efforts; `@off` turns reasoning off. The agent's calls cap their output at
  4096 tokens. The OpenAI-compatible participant model takes `extra_body`, and
  the OpenAI-compatible models keep their provider's last response.
- Attention reads the room as typed questions (#94, plan step 4; Zoe,
  2026-10-05). Step 1 asks whether the judged message is conversation a
  participant like this one could take part in; only a "no" suppresses, and
  a message addressed to someone else is still conversation. Step 2 asks who
  it is addressed to, whether it was answered and by which message, whether
  its author is mid-thought, whether the participant has something to add,
  and which kinds of response could fit. Speaking wakes the participant; a
  mhm, waiting or staying quiet give it a turn with the reading, and it
  decides. The reading is written from the answers and always ends with the
  kinds of response that could fit and their probabilities. Two routes give
  the same answers: a chat model answers the questions as JSON, and a typed
  decision model answers them natively through the new `decisions-api`
  attention kind (`src/nunchi/adapters/decisions_api.py`), registered by the
  reference adapters, the Claude Code runner and the Codex runner.
  `I-010B AttentionDecisionV2@5` records the typed `answers` and drops the
  PASS/ACK/ASK/SPEAK `legacy_verdict_confidences` vector; every prompt,
  schema, fixture, conformance scenario and contract case moved with it.
  The behavior suite's Jev prototype is replaced by the adapter. The chat
  prompt shows the answer shape with a number for each yes/no question, and
  a yes/no answer written as `true`/`false`, `"yes"`/`"no"` or a
  `{"yes", "no"}` split is read as the probability it states: in the first
  behavior run every chat model wrote some answers that way, which failed
  44% of chat-model judgments.
- The agent sees the room as it is now, and looks again before speaking
  (#94, plan step 3; Zoe, 2026-10-05). The gate's context and the agent's
  own view are separate. During its turn the agent reads the live room:
  older messages, newer ones, or `new` for what others posted since it last
  looked, including messages that arrived after its turn began. Its history
  never fails the turn: "nothing more", a message no longer retained, or
  the per-turn limit comes back as a short note; in the first baseline with
  the agent simulated, 10 of 19 failed agent turns were history requests in
  a short room. Before
  the first message, reply, or reaction goes out, the shared protocol and
  the Claude Code gate look again once; if others posted a message
  meanwhile, the action is held and the agent is shown it, then sends,
  changes, or drops its action. Hermes does not offer this yet. The behavior suite adds
  messages that arrive mid-turn (`during_turn`) and two draft scenes.
- Attention's reading of the room reaches the agent on every turn it takes
  (#94, plan step 2). The attention model gives a short reading with every
  judgment: what is happening, with pointers to the messages, and the kinds
  of response that could fit, each with a reason, never an order. The
  reading now goes with DEFER turns as well as WAKE, including ACK and
  suppression widened to DEFER. A bad or empty reading no longer throws
  away the judgment: in the last baseline, 27 judgments failed only
  because of their reading, 24 of them empty. Bad items are dropped one by
  one, and the reading is bounded to 4 notes of at most 400 characters.
  When the agent's fresh window has lost a message an item cites, only that
  item is dropped, and `judged_through_event_id` tells the agent the newest
  message the reading saw. The turn prompts frame the reading as a
  recommendation with reasons. Contracts: `I-010B AttentionDecisionV2@4`,
  `I-010C ParticipantWakeV2@3`. The reading's length is attention policy:
  `reading_items` (0 to 4, default 4) and `reading_note_chars` (40 to 400,
  default 400) set the prompt and cap what reaches the agent, so a shorter
  reading can trade detail for speed; the behavior suite's
  `--reading-items` and `--reading-chars` compare lengths.
- The agent sends its own "mhm" by default (Zoe, 2026-10-05). The ACK policy
  is off by default, so an ACK judgment gives the agent a turn, with the
  reading saying why a nod could fit, instead of Nunchi adding 👂 itself.
  `ack.enabled: true` turns Nunchi's nod back on until step 7 of the plan
  removes it. The behavior suite's `--ack` defaults to `agent` to match.
- `main` is the V2 working branch; `integration/v2` is retired. CI and the
  Hermes host-contract workflow run on pushes to `main` and on PRs into it
  (#88).
- Attention failures are typed. Only the attention engine raises
  cancellation or deadline errors, so provider text can no longer pose as a
  cancellation and silently suppress. Duplicate evidence IDs are a provider
  failure, which wakes by default, instead of a crash with no receipt. The
  judgment schema matches the validator (#89).
- Shared-core fixes for PR #83 (#90): a missed turn deadline no longer drops
  the newest pending message; a published operator approval lives until its
  own expiry (default 300 s), an explicit cancel, or restart, and the turn
  deadline bounds only its publication; a commit that never reached its
  executor is closed as FAILED "privileged effect was not attempted"; an open
  commit found at startup loads as UNKNOWN, so replay stays refused and an
  approved retry is possible; a core ACK result observed after its opportunity
  ended is recorded as `unknown`; ACK journal rollback, diagnostics, directory
  sync, and constructor locking are fixed; non-finite deadlines are refused;
  cancelling the authorization coordinator no longer strands the scheduler.
  Fixes #37.
- The shared core is agent- and provider-agnostic (#91). Attention models are
  selected by `kind` through `attention_model_from_config`, defaulting to
  `openai-compatible`, which needs an explicit `base_url`; there is no vendor
  default endpoint. `extra_body` replaces the vendor-specific `reasoning`
  field, and temperature is optional. `HostTextAttentionModel` and
  `decode_judgment_text` serve text-only hosts.
  `HostStructuredAttentionModel` takes the host's denial check and attestation
  setting. Provider and model are optional audit labels. Hermes-specific
  attention setup text and its `PermissionError` convention moved to
  `src/nunchi/integrations/hermes_attention_trust.py`. The
  operator platform table holds only chat platforms, a room on an unregistered
  platform is accepted with a warning, and `--platform` takes any name.
  Operator model `credential_env` is optional and `kind` is accepted.
  `tests/v2/test_agnostic_core.py` guards the boundary.

### Fixed

- In final-answer posting, only words the agent's own model wrote can be its
  post ([leak audit in #135](https://github.com/mentatzoe/nunchi/issues/135#issuecomment-6057394431), row 5).
  A harness that put its own text in place of a missing answer, such as
  Hermes's `(empty)`, "I reached the iteration limit…" or "No reply: …",
  had that text committed as the agent's reply and kept in its memory, so
  the agent and attention took the person's question as answered.
  - `TurnParticipant(..., model_text=True)` declares that the integration
    reports what the model wrote: `model_wrote(turn_id=, text=)` for each
    response's text and reasoning (`Turn.model_wrote`). The answer must be a
    run of those words, in one response or running on across responses, as
    a length continuation does. Case, whitespace, punctuation, markdown and
    tagged blocks such as `<think>` do not count.
  - Any other answer is `silent` at `finish`, and the turn fails with
    `TurnError` ("the agent's run ended with text its model did not write"),
    even when the harness reports the run as finished. It is never posted,
    never the agent's silence, and never remembered. An empty answer is still
    silence. An integration that declares `model_text` and reports nothing
    fails every answer, with that reason, instead of going quiet.
  - The local turn protocol is `I-040D LocalTurnProtocolV2@2`: `/v1/attach`
    answers `model_text`, the new `/v1/turn/model-text` route takes
    `turn_id` and `text`, and a failed `/v1/turn/finish` answers `failed`
    with the reason. Tool-posting integrations are unchanged.
  - The kit's final-answer reference reports what its scripted model wrote.
    Two new scenarios, `final-not-own-words` and `final-no-answer`, check
    that the harness's text is never posted or remembered and the turn
    fails. They need a harness that can answer for its model
    (`KitIntegration.harness_text`, a surface `stand_in` step). The Hermes
    kit plays them on Hermes's real paths: a budget of one model call
    (`agent.max_turns: 1`), and empty model replies until Hermes gives up.
  - The Hermes plugin reports each model response's text and reasoning from
    `post_api_request`, so Hermes's `(empty)` and its iteration-limit notice
    fail the turn instead of becoming the agent's reply. The retry after a
    failed turn (decision D5) is not built.
- The agent's silence is read as silence in whatever form it wrote it
  ([leak audit in #135](https://github.com/mentatzoe/nunchi/issues/135#issuecomment-6057394431), row 6).
  `**[SILENT]**`, `` `[SILENT]` `` or `[silent].` was posted, or, on Hermes,
  hidden by Hermes but remembered as the agent's reply. Silence now ignores
  case, whitespace, punctuation and the markdown wrappers `` ` `` and `~`
  around the marker (never `[` or `]`), for the prefix, own-line and whole
  answer rules. `also_silent` on `Turn` and `TurnParticipant` lists the
  harness's other silent answers, such as `NO_REPLY`, which count only as the
  whole answer. "No reply from Bob yet." still goes out. The kit's
  final-answer reference lists `NO_REPLY`, and its new `final-silence-forms`
  scenario plays four silent forms and one post that only looks like one.
  The Hermes plugin lists Hermes's other silent answers
  (`HERMES_SILENT_ANSWERS`: `SILENT`, `NO_REPLY`, `NO REPLY` and the zh
  forms), and a Hermes-lane test checks the list against the installed
  Hermes's own.
- In a Hermes room, people now see only what the agent chose to do
  ([leak audit in #135](https://github.com/mentatzoe/nunchi/issues/135#issuecomment-6057394431), row 3, and the Hermes notices).
  - The README's room setup, which the kit and the Hermes tests now run with
    (a test checks they match), turns off what Hermes added on its own: the
    file-edit footer and the "No reply" explanation appended after the
    agent's answer or its `[SILENT]`, retry and budget status lines,
    reasoning, the busy notice, the typing indicator, processing reactions,
    and the `clarify` and `cronjob` toolsets. Some of these apply to the whole
    Hermes profile or bot, so the README recommends one profile and one bot
    per room.
  - When the provider refuses for good, Hermes ends the run with no hook the
    plugin saw, and the turn stayed open until the library's 300 s deadline,
    holding up the room's next moment. The plugin now watches
    `api_request_error` and `pre_api_request`, and ends the turn as failed if
    Hermes starts no new model request within 5 s. A fallback provider that
    takes over keeps the turn.
  - If the plugin's output hook fails, the turn fails and Hermes gets
    `[SILENT]`. Hermes posts the raw draft for a hook that raised.
  - The kit's scripted model reports zero output tokens for an empty reply,
    as a provider does, so Hermes stops retrying after two empty replies and
    the empty-model tests take seconds, not a minute.
  - Still open: Hermes's own failed-turn notice on a failed run, approval
    prompts, `hermes send` through the terminal tool, and Hermes's replies to
    its built-in slash commands (decision D4). The README lists them.
- Secrets the library holds no longer reach the room through any harness
  ([leak audit in #135](https://github.com/mentatzoe/nunchi/issues/135#issuecomment-6057394431), rows 9 and 10).
  - The launch secret a `TurnServer` serves with is now in its participant's
    secret guard (`TurnParticipant.withhold`, `SecretGuard.including`). An
    agent that pasted its environment posted Claude Code's
    `NUNCHI_CLAUDE_CODE_GATE_SESSION`; the gate now refuses it, and the agent
    can post again without it. The same holds for the Codex app-server
    bridge's secret. A launch secret under 16 characters is refused. The
    local turn protocol stays `I-040D@1`: no route or answer changed.
  - One secret guard per room: `nunchi.room.room_guard` withholds the value of
    every variable a config key ending in `_env` names (attention model, the
    integration's sections, authorization), the default key variables the
    models read when the config names none (`NUNCHI_ATTENTION_API_KEY`,
    `NUNCHI_PARTICIPANT_API_KEY`), and what the transport declares with the
    new optional `withheld_values()` and `credential_patterns()`.
    `Room` builds it when not given one and exposes it as `room.guard`.
  - The room's host checks every action against that guard, whatever the
    participant did. A refused action posts nothing and its result is
    `failed`.
  - A reason (`why`) that holds a secret is dropped and the move kept, on
    every path: a silence, a turn's last words (tool posting and final
    answers), a one-reply turn's action, and the host's check. A reason is
    never posted, so it never costs the agent its move.
  - The old Codex runner (`nunchi-codex-room-runner`) and the reference
    adapters had no guard at all. Both now pass the room's guard to their
    one-reply turns: a reply with a secret is refused once, and the model
    answers again. The Discord, Telegram and Matrix adapter transports
    declare the token they hold and its shape.
  - The Claude Code runtime, the Codex app-server integration and the Hermes
    plugin build their guard with `room_guard` instead of their own copies of
    the rule, so the Hermes plugin's guard now also withholds its attention
    route's key. The Discord token shape lives in one place,
    `DISCORD_TOKEN_PATTERNS`. The Hermes plugin also refuses Slack token
    shapes.
  - In Claude Code and the Codex app-server, the `Room` gets the
    participant's guard after the `TurnServer` adds the launch secret, so the
    room's host refuses the launch secret too.
    `codex_app_server.build_integration` takes the room's `transport` and
    withholds what it declares; without one, it refuses the Discord token
    shape. A transport's variable stays out of Codex's environment only when
    named in `withhold`.
  - The conformance kit has a 22nd scenario, `launch-secret`: the agent posts
    its harness's launch secret, the post is refused, and its next post goes
    out. It applies to integrations whose harness holds one (Claude Code,
    Codex app-server) and is n/a for the reference turn and Hermes.
- Nunchi's own processes stop other processes of their OS user from reading
  their keys once they have started ([leak audit in #135](https://github.com/mentatzoe/nunchi/issues/135#issuecomment-6057394431), row 8).
  This narrows row 8; it does not close it for an agent that runs as
  Nunchi's OS user. Before, a shell command of the agent could read the
  gate's or runner's `/proc/<pid>/environ` and memory at any time, and post
  to the room with the transport's key, without the library.
  - `nunchi.private_process.keep_private()` marks the process not dumpable
    on Linux. From then on another process of the same user gets
    `PermissionError` on both files, and the process writes no core file;
    root still reads them. Off Linux it does nothing and says
    `unsupported`; if the system refuses, it logs a warning and says
    `failed`, and the process runs on.
  - The Claude Code runner, both Codex runners, `nunchi-mcp-discord`, the
    service worker and the reference adapters call it first in `main`,
    before they read their config or start an agent. The runners' probes
    report `process_private` and `agent_os_user: "same"`. The older Hermes
    integration's probe reports `process_private: false`: it runs inside
    Hermes's own process, which Nunchi leaves alone; the Hermes plugin has
    no probe. `process_private: true` means reads are stopped after
    start-up, not that the keys are safe.
  - Still open under one OS user: keys in a process's starting environment
    are readable by any process of that user for about a tenth of a second
    at each start (Python's start-up and Nunchi's imports, before the
    call). An agent with an unsandboxed shell can leave a reader running
    and force a start by killing a supervised runner; a signal needs only
    the same user, and the service worker or systemd starts it again. What
    closes it: Claude Code's Bash sandbox (a fresh `/proc`), Codex's
    `workspace-write` or `read-only` sandbox (its own process namespace),
    or running the agent as its own OS user, which is not supported yet.
  - Also not covered: other programs started from the shell that exported
    the keys, environment files, a systemd unit's `Environment=` lines,
    macOS and root. The Claude Code and Codex app-server READMEs give the
    harness sandbox settings that keep the agent's commands away from the
    rest.
  - The Codex app-server integration records the sandbox Codex reports for
    the thread, and logs a warning when it is `dangerFullAccess` or
    `externalSandbox` (`CodexRoomRunner.status()`). It still runs.
  - The Claude Code runtime ran `claude --version` with its own environment,
    Nunchi's keys included. It now uses the user's environment without
    Nunchi's keys or any `NUNCHI_*` variable (`user_environment()`).
- Hermes: two concurrent native tool calls no longer refuse each other on a
  slow disk. One call's journal write could hold SQLite's lock past the
  journal's 0.25 s budget, so the other call was refused with "native
  invocation could not be bound and persisted". The runtime now records both
  the start and the end of a native call under one lock. Cancellation can
  wait for one short write.
- A chat model's `"answered": null` no longer fails the judgment when the
  same answers say the message asks for nothing (`asks` below 0.5); it reads
  as 0, the question's own "no" (#87). In run 53 Haiku on chat completions
  answered null 13 times, every time on a message that asked nothing: bot
  status reports, CI lines, spoofed verdicts and tool output. A failed
  judgment wakes the agent by default without the reading, so those moments
  gave it a turn on bot noise, unguided. Null beside a message that does ask
  still fails.
- The behavior suite's paired play, the same turn without the reading, now
  gets its own fresh view of the room. Since #109 it shared the first play's
  view, which never repeats what it has shown, so the second play could not
  see a message that arrived mid-turn or history the first play had read.
  Paired results from runs on #109 through #112 are biased against the play
  without the reading wherever the agent looked at the room. The host's
  per-turn view is now a `RoomView` with a `fork()` for such replays.
- A participant reply in a code fence followed by the model's own note is
  now read as the fenced envelope; the note is dropped and never posted.
  Before, the whole turn failed. In a behavior run after #94 step 2, 16 of
  18 rejected agent replies were a valid fenced silence followed by an
  explanation of why the agent stayed quiet. Any other text beside the
  envelope is still a malformed reply.
- The OpenAI-compatible participant used by the reference adapters now
  sends the action schema its prompt promises, bound to the turn's exact
  binding. Before, the prompt said "matching the supplied action schema" but
  no schema was sent, so models had to guess the envelope: in the first
  behavior run with a simulated agent, 763 of 809 agent turns were rejected
  for an envelope that didn't match.
- The manual `live-smoke` workflow works again. Its model config lacked the
  now-required `base_url`, so every run failed before calling a model. It now
  calls a current model (chosen at dispatch) through OpenRouter with the
  `NUNCHI_OPENROUTER` secret. It fails on a missing secret or any decision
  other than `ok` instead of skipping or passing. It records the version,
  model, digests, command, and full decision in the job summary and an
  artifact.
- Discord REST errors no longer echo the bot token into error text (#88).
- Three defects from #94.
  - The attention snapshot keeps the newest messages of the participant's
    direct exchange (messages that mention it or reply to it, and its own)
    even when they are older than the newest-events window. They take at
    most a quarter of the event cap and stay within the byte and age limits.
    Before, a mention dropped out after 24 newer events. Gaps this leaves
    inside the snapshot can be fetched through the continuation handle.
  - An actor record with kind `unknown` or no display name, such as a
    Discord reactor, no longer erases a known name or kind.
  - ACK on a trigger that is not a message (a reaction or a join) widens to
    DEFER as unsupported instead of reacting to that event.

### Removed

- Executable V1 verdict, adapter gate, Codex hook, send-gate, config app,
  installer, and compatibility entry points.
- Dead V1 tests, fixtures, and Codex shims (#88). V1 contract documents moved
  to `docs/archive/v1/contracts/`; V1 verdict fixtures stay under
  `evals/verdict_suite/fixtures/` as seed conversations for behavioral
  evaluation (#86).
- `HostStructuredParticipant` (#91).
- The headless Claude Code runner (PR #32) and its real-binary scene runner
  (`evals/v2/claude_code/`), replaced by the gate and mod (#43).
- Nunchi's own nod (#94 step 7; Zoe, 2026-10-05: every visible move is the
  agent's own). It had been off by default since #107. A judgment that leans
  to a "mhm" is now `DEFER`: the agent takes the turn and reacts itself if it
  wants to.
  - Contracts: I-010B@9 drops the ACK disposition, the ACK transitions, the
    `capability-defer` valve, the `ack-disabled` and `ack-unsupported`
    causes, and the `ack` audit. I-010C@13 drops the ACK wake source.
    I-010E@5 writes no ACK record but still reads ones written before, so
    older receipt journals load. I-030A@3 and I-040A@3 drop the engine's
    reaction policy and the host's durable nod path.
  - Gone: `AckPolicy`, `AckJournal`, `nunchi.ack` (the reaction capability
    moves to `nunchi.reactions`), the Hermes nod module and its reaction
    probe before every attention call, `nunchi config set-ack`, the setup
    flags `--ack-reaction` and `--ack-disabled`, the eval's `--ack` option
    and the workflow's `ack` input, and the three nod conformance scenarios
    (replaced by one `mhm` scenario).
  - Old settings still load and are ignored: the operator profile's
    `ack_policy`, the `ack` key in adapter, Claude Code and Codex configs,
    and a Hermes room's `ack`.
  - The agent's own reaction is now checked against the platform's attested
    capability: the turn offers a reaction when the capability permits any,
    and a reaction it does not name is refused before dispatch. Before, the
    check used the nod's emoji.
  - `nunchi probe` and the adapter runtime's probe now report the same
    interface versions from one table; the runtime's had fallen behind.
- The executable SpecKit workflow, generated task and checklist control plane,
  and slice lifecycle as implementation authority. Specifications and plans
  remain reference material.

## V1 and SpecKit-era changes, 2026-07-02 to 2026-07-18 (history, never released)

These entries were recorded under "Unreleased" after `v0.2.0`. They describe
V1 behavior and the retired SpecKit process, which V2 replaced. None of this
code or process is current.

### Changed — program and slice lifecycle replaces local-run framing

- External guidance records the 2026-07-11 reset baseline—the V2 program
  `READY`, implementation authority `NOT_GRANTED`, and all slices `010`–`110`
  `PLANNED` with product tasks dormant—as a dated snapshot rather than a live
  registry. Readers resolve current program progress from the umbrella,
  authority from the exact authorization record, and slice state/occupant from
  the bound declarations plus immutable activation/acceptance records and
  append-only candidate/handoff evidence. V1 remains current until the atomic
  V2 merge is post-merge verified
  as `CUTOVER_VERIFIED`.
- Both workflows operate on one existing slice through
  `python3 scripts/run_slice_workflow.py run <workflow> specs/<exact-slice>`.
  The runner verifies exact SpecKit `0.12.11` and its pinned PEP-610 source,
  preflights and binds the slice in the workflow process, resolves the concrete
  integration, pins those facts with the slice input and workflow digests, and
  rejects altered resume state without mutating `.specify/feature.json`. The planning cycle is now the
  nine-step `Nunchi Existing-Slice Planning Cycle` version `1.4.0`; it begins at
  `bind-existing-slice`, stops after analysis, and never creates or replaces a
  feature. Participants resume a paused unchanged-task run only through
  `python3 scripts/run_slice_workflow.py resume <run-id>`; changed tasks or a
  rejected completed handoff start a new bound run. The delivery workflow's
  implementation-authority gate requires the external grant record at
  `evidence/governance/v2-implementation-authorization.md` to enumerate exactly
  all eleven slices; a partial or extra-scope record is invalid for every slice.
  Its separate readiness gate verifies owner, dependencies, analysis, worktree,
  and activation evidence.
- Zoe, or an assigner named in a durable Zoe delegation, assigns the program
  owner and slice occupants. The declaration and activation evidence carry
  `<participant identity> — evidence/governance/assignments/<record>.md`; that
  record contains `Assignee`, `Lane`, `Assigned by`, `Assigned on`, and
  `Authority reference`, plus `Delegated by: Zoe` and `Delegation reference`
  for a non-Zoe assigner. Assignment may precede
  authority for planning but never grants implementation or readiness; no
  central assignment registry is introduced.
- Slice state follows `PLANNED -> READY -> ACTIVE -> CONVERGED -> HANDOFF_READY
  -> ACCEPTED`. Each dependent independently accepts its required upstream
  handoffs before readiness; at slice level `v2-integrator` accepts `010`–`100`
  and Zoe accepts `110`. Only slice `110` integrates. After its handoff, Zoe's
  exact-candidate decision establishes slice `ACCEPTED` and program
  `CUTOVER_ACCEPTED`; one atomic merge remains verification-pending, and a
  docs/evidence-only follow-up combines exact-main verification with final
  current-state docs validation before `CUTOVER_VERIFIED`. State is derived
  from control-plane declarations, immutable activation/acceptance records,
  and append-only candidate/handoff attempt streams, never a central runtime,
  conversation, participant, assignment, or social-state registry.
- Activation evidence now maps dependencies to ordered full commits and
  matching per-consumer acceptance files; slice `110` requires every upstream
  slice to be `ACCEPTED`. Candidate and handoff files are append-only attempt
  streams. Convergence-added tasks and rejected completed handoffs each keep or
  return the same owner to `ACTIVE` and require a new bound run; only paused
  post-convergence fixes with an unchanged task graph resume. No candidate or
  packet history is erased.

### Changed — mandatory documentation freshness for implementation slices

- Constitution 2.3.0 retains `README.md` and affected ordinary documentation as
  blocking part of every SpecKit implementation. Each reviewed surface must use
  `UPDATE`, evidence-backed `NO_IMPACT`, or an exact owner-accepted `HANDOFF`;
  generic documentation tasks and bare no-impact claims no longer close a
  slice.
- The delivery workflow gates documentation freshness after convergence and before
  slice handoff. Spec, plan, task, checklist, agent-guidance, and all V2 slice
  artifacts carry the same ownership and validation rules.
- Slices `010`–`100` update their owned component guides and hand exact global
  claim deltas to `v2-integrator`; slice `110` must update `README.md` and all
  affected cross-surface documentation in the atomic candidate.
- Governance tests reject missing README dispositions, bare `NO_IMPACT`,
  missing doc tasks/checklist coverage, and a missing or misordered workflow
  gate.
- Active slices now inventory exact existing docs as well as planned V2 guides;
  generic directory scope is rejected. The dormant-task check remains strict
  while implementation authority is `NOT_GRANTED`, but permits completed tasks
  after the external grant is documented at
  `evidence/governance/v2-implementation-authorization.md`, enumerates exactly
  all eleven slices, and the bound slice's independent readiness gate passes.

### Fixed — round-4 review: confidence domain, uninstall confinement

- **Confidences must be on the stated [0, 1] scale**, enforced identically at
  the hook (`defer-malformed-confidence` when DEFER is on) and the shared
  schema boundary (`ValidationError`), so core and adapters cannot disagree.
  `{"PASS": 9.0, ...}` and negative vectors previously passed the exactness
  check and hard-blocked — off-scale evidence has no defined margin meaning.
- **Confinement covers destructive writes:** both uninstall paths now call the
  ancestor check before mutating; uninstalling through a symlinked
  `plugins/`/`hooks/` that escapes the configured root is rejected instead of
  recursively deleting external directories. Aleph's repros are the
  regression tests.
- **Residue swept to the current contract:** remaining unreleased-changelog
  lines and the two addressing fixture metas no longer assert the
  deterministic fast-path or alias-authorship-as-fact; the hook's module
  docstring now states the two fail-open contracts explicitly (runtime
  failures receipted; malformed config knobs fall back silently to documented
  defaults, verifiable from receipts' effective values).

### Fixed — round-3 review: terminal fail-open, exact destructive PASS, installer parity

- **Declared fail-open is terminal.** A mistyped `transcript_path` used to
  write `allow-input-error` and then keep judging (the receipt said allow, the
  gate blocked). Input errors now stop processing.
- **A destructive PASS must be complete and exactly typed:** `silent` present
  and boolean, `reasons` a non-empty list of non-empty strings, confidences
  exactly the four verdict keys (extras are evidence malformation → DEFER when
  enabled). Defaults no longer forge the destructive form; admits stay lenient
  because they destroy nothing.
- **The outer guard is actually outer:** fallible config (`NUNCHI_HOOK_TIMEOUT`,
  `NUNCHI_HOOK_TOOL_PATTERN`) parses safely instead of crashing at import, and
  any exception escaping the guarded main — decoder recursion included — exits
  0 with a receipted `allow-hook-error`.
- **Attribute tokens require both boundaries** (`chat_id="c1"junk` no longer
  binds) and duplicate required attributes reject the envelope as ambiguous.
- **Hermes installer parity:** the plugin tree now gets the same
  file-inventory + content-drift verification, upgrade-repairs, and
  `_ensure_confined` ancestor check as the Claude path;
  `verify → upgrade → verify` converges for deleted and tampered plugin files,
  and a symlinked `plugins/` escaping `$HERMES_HOME` is rejected before writes.
- **Docs and prompt tell the current contract:** aliases are addressing
  evidence, never authorship — corrected in `docs/integration.md`,
  `src/nunchi/schema.py`, the unreleased changelog entries, and the classifier
  prompt itself (which had asserted name-equality authorship as fact).

### Removed — the deterministic pre-classifier layer, entirely

- **The fastpath module is gone** (round-2 review + room baseline: suppression
  may be deterministic only where mechanically provable, and the current
  envelope carries no transport-bound identity, so nothing qualifies). The
  mention-elsewhere rule fell in round 2's precursor; round 2 proved the
  self-echo rule equally unsound — author-name equality accepted a human whose
  display name matched an alias as "self", and text equality accepted a human
  repeating "Thanks." as the agent's own echo, both minting PASS 1.0 with no
  model call and sailing past DEFER. Every admission is now classifier-judged.
  Deterministic short-circuits may return only when the message contract
  carries an adapter-asserted runtime binding (schema-v2). `NUNCHI_FASTPATH`
  env knob removed with the layer.

### Fixed — Claude Code gate: strict directive typing, envelope integrity, crash paths

- **Hard suppression now requires a complete, finite, correctly typed
  confidence vector.** A PASS whose confidences are missing, partial, mistyped,
  or non-finite ABSTAINS (`defer-malformed-confidence`, malformation receipted)
  instead of hard-blocking — broken evidence is not confidence. The explicit
  `NUNCHI_DEFER=off` kill switch keeps its hard meaning. `silent` must be a
  real boolean (`"false"` no longer coerces into a forged block) and `reasons`
  a real list; both fail open with a receipted `allow-gate-error` otherwise.
- **Envelope integrity:** attribute parsing requires complete tokens
  (`not-chat_id="c1"` no longer binds as `chat_id`); whitespace-only
  identifiers read as missing (`allow-envelope-error`).
- **The "always exit 0, fail open, receipt errors" contract is now mechanical:**
  `prompt: null` and mistyped top-level fields fail open with a receipted
  `allow-input-error`; a non-object transcript row is skipped; a malformed
  `NUNCHI_HOOK_HISTORY_WINDOW` falls back to its default; any unhandled hook
  exception exits 0 with a receipted `allow-hook-error`.

### Fixed — installer: verification integrity and confinement

- `verify` no longer certifies broken or mixed deployments: every managed file
  must exist as a regular file (a deleted wrapper is reported and `upgrade`
  repairs it), installed bytes are compared against source (content drift
  reported), retired-name broken symlinks are visible, and the stale-settings
  scan runs even when nothing is installed. `verify → upgrade → verify`
  converges for all of these.
- The CLI check reports `present-unverified` — presence is not provenance; the
  shared `nunchi-channel` is a separate deploy surface (documented in
  docs/INSTALL.md with the refresh step).
- Destination ancestors that resolve outside the configured root are rejected
  before any write (symlinked `hooks/` escaping `--prefix` was reproducible);
  symlinks that stay inside the root remain legitimate operator topology.

### Removed — fastpath mention-elsewhere short-circuit (the precursor, in detail)

- **A foreign `<@id>` mention no longer produces a deterministic PASS.** The
  rule conflated referential mention ("another agent appears in the story")
  with floor assignment ("the message is for them"). Live false PASS,
  2026-07-10: the operator replied to an agent's own message, correcting it by
  name, while @mentioning a peer who featured in the anecdote — the fast path
  stamped `PASS 1.0`, `classifier_model: null`, and no model ever read it.
  Because a fastpath PASS carries full confidence, it also sailed past DEFER —
  deterministic overconfidence sat above the uncertainty lane. Room-agreed
  contract (Aleph/Aether/Vigil/Station): *a deterministic rule may hard-PASS
  only what it can prove; a foreign mention proves reference, not exclusive
  targeting.* Foreign-mention messages now always get semantic adjudication.
  (Self-caused echo briefly remained as a short-circuit; the entry above
  removes the whole deterministic layer — name/text equality is not proof.)
  Fixture `a-mention-other-alias-in-passing` keeps its PASS ground truth but is
  now model-scored. (The live canary was pinned in `tests/test_fastpath.py`
  until the whole deterministic layer was removed — see the entry above; the
  canary's ground truth lives on in the fixture corpus.)

### Changed — Claude Code: one judgment per turn, at wake (send-time gate retired)

- **Retired the Claude Code send-time (`PreToolUse`) gate** (`nunchi_gate_hook.py`
  and its `nunchi-pretool-reply.sh` wrapper). It re-judged an already-admitted
  turn against the newest transcript line, so a peer message landing while the
  agent composed stole the causal role and the composed reply died as a false
  PASS. Nunchi now makes its single admission judgment at wake
  (`UserPromptSubmit`) and gets out of the way; no permit/ledger side state is
  needed because nothing has to be kept consistent across two judgments.
  `tests/test_no_second_judgment.py` scans the whole project to keep both the
  retired hook and the ledger shape removed.
- **DEFER (gate abstention) added to the wake gate, default on.** On an
  *uncertain* PASS (best alternative verdict within `NUNCHI_DEFER_MARGIN`,
  default 0.25) the gate declines to silence: the prompt goes through with the
  gate's hesitation noted in-band, and the agent's own model decides — replying
  and staying silent both stay open. `NUNCHI_DEFER=off` restores hard PASS.
  Abstentions are receipted as `defer-uncertain-pass` for offline evaluation.
- **Admissions travel in-band.** SPEAK/ACK/ASK now add a short
  `additionalContext` note naming the message the turn answers, anchoring
  composition to its origin without side state.
- `nunchi-install` upgrade/uninstall now actively remove the retired hook files
  (with backups), `verify` flags leftovers as stale, and the printed
  `settings.json` snippet is `UserPromptSubmit`-only (delete any old
  `PreToolUse` entry by hand — settings remain operator-owned).

### Added — Codex/Vigil room integration and operator surface

- Added a long-running Codex room runner for the shared Discord MCP transport.
  It gates every notification before `codex exec`, backfills configured channel
  history at startup and newly observed/hot-added channels before their first
  live gate, suppresses `PASS` without a frontier wake, and records receipts.
- Admitted room wakes now create and then resume one dedicated Codex task using
  an atomically persisted thread id. Session mode/path are configurable;
  malformed state fails closed, receipts expose the observed task id, and the
  configuration app reports or resets the persistent session.
- Added Codex `UserPromptSubmit` and outbound `PreToolUse` hooks. Supported room
  sends are re-gated immediately before the tool call; missing/current-context,
  malformed-send, duplicate-send, direct Discord command, `PASS`,
  disabled-state, corrupt-state, receipt-write, and closed-policy gate-error
  paths deny the send.
- Added atomic hot runtime state shared by the runner and both hooks, with
  global/per-channel presence, sender/allowlist, receipt detail, classifier
  model, pinned-rule, channel-add, and channel-disable controls.
- Added a local MCP Apps configuration server and responsive task-embedded panel
  for those controls, health, and newest-first receipts. Codex has no documented
  persistent third-party dashboard-tab slot, so this provides the Hermes
  operator functions in Codex's embedded app container.
- Added the repo-local `nunchi-codex@local-repo` marketplace plugin, package
  entry points, copy-safe hook commands, offline unit/protocol tests, and a
  committed bounded Vigil smoke evidence record. A second record verifies two
  admitted live turns resumed the same persisted Codex task and one response
  reached Discord. These support only narrow smoke claims, not sustained
  operations; the app also has offline protocol and responsive interaction
  evidence.
- Normalized Discord rich-only peer messages into tagged, bounded text for
  both live events and history, while preserving ordinary content and excluding
  button labels. This prevents visible embed-only reviews or approval notices
  from being misclassified as empty room events.
- Preserved Discord mention and reply metadata across live/history transport
  shapes. The Codex runner now restores available referenced messages and uses
  structured mention ids for admission and outbound re-gating without changing
  the prose displayed to Codex.

### Added — `nunchi-install`: copy-based installer for operator artifacts

A new `nunchi-install` console script (backed by the stdlib-only
`src/nunchi/install.py`) installs Nunchi's operator artifacts into stable
locations by **copying**, never symlinking. This fixes a real incident: the
Hermes plugin had been **symlinked** into `~/.hermes/plugins` from a live git
checkout, so a `git checkout` on another branch silently swapped the running
plugin for stale code; separately, the Claude Code hooks were registered by
floating checkout paths (`/Volumes/...`) that broke when the path moved.

- **Three artifact groups → stable destinations.** The Hermes plugin
  (`integrations/hermes/nunchi-gate/`, excluding `__pycache__`/`docs/`/`tests`,
  keeping the runtime `.py`, `plugin.yaml`, and `dashboard/`) is copied to
  `$HERMES_HOME/plugins/nunchi-gate/` (default `~/.hermes`) as a **real
  directory**. The Claude Code hooks (`nunchi_gate_hook.py`,
  `nunchi_prompt_gate.py`) are copied to `~/.claude/hooks/`, alongside two
  **fail-open** shell wrappers (`nunchi-pretool-reply.sh`,
  `nunchi-user-prompt-submit.sh`) that source an optional env file and run the
  hook with `|| exit 0` so a missing/broken gate never blocks Claude Code. The
  `nunchi-channel` CLI is checked on `PATH` (never installed; prints `pip`
  guidance if absent).
- **Symlink replacement (the core fix).** A symlinked destination is detected,
  its target recorded in the version marker, backed up (preserved as a link),
  and replaced with a real copy. `uninstall` restores the backed-up symlink.
- **Version stamping + safe upgrade.** Each destination gets a
  `.nunchi-install.json` marker recording the source commit (`git rev-parse
  HEAD`, falling back to a `VERSION` file or `"unknown"`), source path,
  timestamp, and file list. `upgrade` re-copies only when the source commit
  differs (or the destination is missing/symlinked), backing up the old copy
  first; `--force` overrides. `verify` reports per-artifact drift as
  `in-sync` / `stale` / `not-installed` / `symlink-found`.
- **Commands + flags.** `install`, `upgrade`, `verify`, `uninstall`, and
  `print-claude-settings` (prints the `settings.json` hook registration
  pointing at the stable wrapper paths — the operator's file is never
  auto-edited). Global `--dry-run` (plans without touching disk),
  `--prefix` / `--hermes-home` / `--claude-home` / `--repo-root` overrides, and
  `--only` group selection; flags work before or after the subcommand.
- **Determinism.** The wall clock and source-commit resolver are injectable, so
  the 45 new offline `unittest` cases (`tests/test_install.py`) confine every
  write to temp dirs — never the operator's real `~/.hermes` / `~/.claude` —
  and pin marker timestamps and backup names.
- **Docs.** New [`docs/INSTALL.md`](docs/INSTALL.md) (install/upgrade/verify/
  uninstall, the `settings.json` snippet, and the "why we copy, not symlink"
  note); `docs/integration.md` and `integrations/hermes/README.md` now point at
  `nunchi-install` and warn against symlinking the plugin.

### Added — `agent.aliases`: the gate knows every name one bot carries

One agent on a chat surface carries several identities at once — its
configured `agent_id`, its platform mention token (a Discord snowflake), a
display name ("Vigil"), secondary handles ("Codex"), profile names
("Aether"). Two live failures on 2026-07-08 came from the gate knowing only
one of them: a runner whose `mention_id` held the *display name* PASSed a
direct `@<snowflake>` mention ("mentions other participants only"), while
bare occurrences of the name in prose triggered wakes. The envelope now
carries the full bundle. Everything below is **additive-optional**: absent
or empty aliases, behavior — including the serialized classifier request —
is byte-for-byte identical to before (golden-request test pins this).

- **Envelope: optional `agent.aliases`** (list of non-empty strings),
  validated by `validate_request` (non-string/blank entries rejected),
  passed through to the classifier with the rest of the `agent` object.
  Documented in `src/nunchi/schema.py` and `docs/STABILITY.md`.
- **Aliases are addressing evidence for the classifier only.** (This entry
  originally extended the deterministic fast-path's identifier sets; that
  entire layer was later removed in this same unreleased cycle — see the
  removal entries above. Aliases establish who a message may be FOR; they are
  never proof of authorship.)
- **Classifier prompt** now states the agent may be addressed by any of its
  `id`, `mention_id`, or `aliases`. (An earlier revision also told the
  classifier a message authored under an alias "is the agent's own" — that
  authorship claim is retracted per the round-3 review: name-equality is not
  authorship.)
- **Channel adapter**: `agent_aliases` parameter on `build_request()` /
  `gate()`, `agent.aliases` passthrough in the CLI payload, alias-aware
  `self` role inference for history lines, and a shared `parse_alias_csv`
  helper for env knobs. Alias lists are deduped against
  `agent_id`/`mention_id`, order-preserving.
- **Surface knobs** (each documented in its config docstring/README, all
  stating loudly that `mention_id` is the platform snowflake/token, NOT the
  display name — names belong in aliases):
  - the Claude Code wake gate (UserPromptSubmit; its PreToolUse sibling was
    later retired — see above) and the Codex
    UserPromptSubmit hook: `NUNCHI_HOOK_ALIASES` (comma-separated);
  - Codex room runner: `NUNCHI_RUNNER_ALIASES`;
  - Hermes plugin: `aliases:` config key (CSV or list), global and
    per-channel in the map form of `channels`; excluded from runtime state
    overrides like the other identity keys;
  - standalone adapters: `NUNCHI_MATRIX_ALIASES`, `NUNCHI_TELEGRAM_ALIASES`,
    `NUNCHI_DISCORD_ALIASES`.
- **003 corpus: new `addressing` fixture pool (`a-*`)** under
  `evals/verdict_suite/fixtures/addressing/` — six
  envelope+meta pairs distilled from the live failures: direct
  `@<snowflake>` mention with the snowflake in aliases (SPEAK), display-name
  address (SPEAK), secondary-alias address "Codex" (SPEAK), a different
  bot's name (PASS), a relay echo under a profile-name alias, and a mention
  of another participant with our alias only in passing prose (both PASS —
  originally deterministic-fast-path cases, model-scored since the layer's
  removal). Loader,
  runner (`--source addressing`), and runner self-tests discover the pool
  the same way as the injection and tool-chrome classes.
- **Merged `feat/codex-plugin` into this branch** (Codex room runner +
  pre-LLM prompt gate hook, previously unmerged) so the alias knob could
  land on the Codex surface too; its hook tests were also brought under
  `tests/hook_sandbox.sandbox_env`, matching main's receipt-log hygiene
  enforcement.
- Scope note: alias matching is identity plumbing, not fuzzy matching —
  (historical: the then-extant fast-path compared only structured tokens; the
  layer is now removed and ALL addressing judgment, prose or structured, is
  the classifier's). The SPEAK
  expectations in the new fixtures are model judgment (evidence:
  `predicted`), not fast-path guarantees.

### Fixed — fail-policy wiring, empty-send guard, peer-tool-chrome fixtures

- **Hermes plugin: `fail_open` now reaches the nunchi-channel binary as the
  payload's `fail_policy`** (`"open"` when true, `"closed"` when false).
  Previously `fail_open` only governed the plugin's own exception path — the
  binary's envelope defaulted to fail-open, so a classifier outage inside
  `nunchi-channel` degraded to SPEAK even when the operator set
  `fail_open: false` (live event 2026-07-08). `fail_open` was already
  per-channel overridable (map form of `channels`), and the override now
  flows into the payload; tests cover the default (open), both mappings, and
  the per-channel override end-to-end.
- **Standalone adapters (`nunchi-matrix`, `nunchi-telegram`,
  `nunchi-discord`): empty-send guard.** When the responder returns empty or
  whitespace-only text, the send is suppressed and a receipt is written with
  `action: empty-suppressed` (previously the adapters posted literal empty
  messages — observed live on Discord 2026-07-08). The Hermes `nunchi-gate`
  plugin is intentionally NOT changed: it is admission-only and never sees
  the composed reply, so it cannot guard against empty sends — that remains
  the Hermes reply path's responsibility.
- **003 corpus: new `tool-chrome` fixture pool (`t-*`)** under
  `evals/verdict_suite/fixtures/tool-chrome/` — five
  envelope+meta pairs where peer-bot tool-use chrome (`skill_view` marker,
  `search_files` marker, todo-list markers, a compaction notice) appears as
  the trigger or in history with benign context; expected verdict PASS
  (chrome is telemetry, not an invitation — the classifier misread exactly
  this chrome as user invitations under low history, live event 2026-07-08),
  plus one contrast case where a human explicitly names and asks the agent
  right after chrome (SPEAK). Loader, runner (`--source tool-chrome`), and
  runner self-tests discover the pool the same way as the injection class.

### Security — send backstop on every sending surface

- **Per-channel send backstop ported from the MCP Discord transport to all
  other sending surfaces** (amplification-loops mitigation, DEFAULT ON).
  A sliding-window cap — at most 5 sends per channel per 10 seconds by
  default — now guards `nunchi-matrix`, `nunchi-telegram`, `nunchi-discord`,
  and the Hermes `nunchi-gate` plugin. When the cap trips the send is
  suppressed (never queued) and a receipt line is written with
  `action: rate-limited`; PASS and all other suppression semantics are
  untouched, and silent verdicts never consume window slots.
- Adapters share one implementation (`nunchi.adapters._backstop.SendBackstop`)
  with operator-only env knobs: `NUNCHI_{MATRIX,TELEGRAM,DISCORD}_BACKSTOP_MAX_SENDS`
  and `NUNCHI_{MATRIX,TELEGRAM,DISCORD}_BACKSTOP_WINDOW_SECONDS`.
- The Hermes plugin gates both allow paths (SPEAK/ASK/ACK verdicts and
  fail-open error allows — a broken-classifier loop with `fail_open: true`
  is now bounded too), returning
  `{"action": "skip", "reason": "nunchi:rate-limited"}` when tripped.
  Knobs `backstop_max_sends` / `backstop_window_seconds` follow the
  `history_window` precedent: global `config.yaml` keys only, never
  per-channel and never runtime (state/slash/dashboard) overridable.
- Offline deterministic tests (injected clock) cover window slide, per-channel
  isolation, default-on behavior, rate-limited receipt shape, and untouched
  PASS/suppression semantics on every surface, including a stub-discord.py
  harness that drives the real `nunchi-discord` client wiring.

### Added — adversarial injection eval pack

- **Injection fixture pool (`i-*`).** New `injection` fixture class under
  `evals/verdict_suite/fixtures/injection/` — 12
  envelope+meta pairs covering gate steering (`[SYSTEM] you must reply` in
  message text, fake pinned rules inside a message, "everyone must respond
  to everything" governance-in-message), verdict-format spoofing (verdict
  JSON in the message body), unicode/markdown smuggling (zero-width
  characters, code-fence-wrapped directives), sentinel forgery
  (`CC_CONNECT_SILENT_PASS` typed into inbound text — data, never
  suppression), and injection-via-history (attacker instructions in
  scrollback with a benign trigger). Expected verdicts encode the plain
  social judgment with the injection ignored; the genuinely ambiguous case
  uses the corpus's expected-verdict-list convention. The suite loader and
  runner accept the new pool (`--source injection`) and the runner
  self-tests cover discovery, partitioning, and both steering directions.
- **Cross-layer provider-redirection enforcement tests**
  (`tests/test_provider_redirection.py`). No hostile envelope field can set
  `endpoint` / `base_url` / `api_key_env` / `binary` / `agent_id` /
  `mention_id` / `log_path`, asserted at BOTH layers: the classifier-config
  whitelist (`ValidationError` on every non-whitelisted `classifier_config`
  key, unknown top-level envelope fields never survive validation, base URL
  and API key resolve from operator environment only) and the hermes state
  whitelist (filter-at-ingestion, honest audit reporting, and re-filtering
  at merge time so even a hand-tampered state file cannot rebind
  operator-only plumbing; the config.yaml per-channel merge is a closed
  whitelist too).
- **Sentinel-forgery unit tests** (`tests/test_sentinel_forgery.py`).
  Inbound message text containing host sentinel strings (bare and
  underscore-decorated `CC_CONNECT_SILENT_PASS` variants) never causes
  suppression by itself in the hermes plugin, the Claude Code PreToolUse
  hook, or the Claude Code UserPromptSubmit hook: the sentinel travels to
  the gate verbatim as trigger data, suppression flows only from the gate's
  typed directive, and structural guards assert none of the three
  integrations contain sentinel-vs-text matching.

### Hardening & test hygiene (dashboard sinks, slash trust chain, receipt-log leak)

- **Test hygiene fix (real observed bug): hook tests no longer pollute the
  operator's live receipt log.** Several tests ran the Claude Code hook
  scripts as subprocesses with the parent environment inherited, letting
  `NUNCHI_HOOK_LOG` fall through to its home-anchored default — the
  operator's `~/.claude/nunchi-gate-receipts.jsonl` accumulated 700+ test
  artifacts (`chat_id` values like `c1`). New `tests/hook_sandbox.sandbox_env`
  pins `HOME` and `NUNCHI_HOOK_LOG` into a fresh temp dir for every hook
  subprocess; all hook-running tests (`test_claude_code_hook`,
  `test_claude_code_prompt_gate`, `test_history_buffer`) now route through
  it. New enforcement suite `tests/test_no_home_writes.py` scans the ENTIRE
  tests/ tree (no home-path resolution anywhere; no bare-`os.environ`
  subprocess env in hook-running modules), self-tests its own detectors, and
  runs a runtime canary proving the home-default fall-through is contained.
  Fixed shared `/tmp` side-file names replaced with unique temp paths.
- **Determinism: hermes gate tests no longer read the operator's live state
  file.** `_base_cfg` in `test_hermes_integration` / `test_history_buffer`
  now pins `state_path` to a nonexistent path instead of falling through to
  `~/.hermes/nunchi-gate.state.json`, whose live overrides could flip
  verdict routing mid-suite.
- **Dashboard injection audit + enforcement.** Audited the hermes dashboard
  renderer (`integrations/hermes/nunchi-gate/dashboard/index.js`): all
  untrusted receipt/channel content is rendered through
  `React.createElement` text nodes; no unsafe sinks found. New enforcement
  test `tests/test_dashboard_asset_safety.py` scans every served web asset
  in the whole repository (js/ts/html/vue/svelte, not selected files) for
  `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`,
  `dangerouslySetInnerHTML`, and `srcdoc`, self-tests the detector, and
  fails if the dashboard bundle drops out of the scan.
- **/nunchi slash-command trust chain documented and pinned by test.**
  Authorization lives in hermes' command dispatcher, not the plugin: the
  handler receives only the raw argument string (no sender identity), so
  per-user checks are structurally impossible in-plugin. The trust chain and
  the whitelist bounding its blast radius are now documented precisely in
  the plugin docstrings and enforced by `tests/test_slash_command_authz.py`:
  the handler signature excludes identity, adversarial slash input cannot
  touch operator-only keys (`binary`, `log_path`, `state_path`, `agent_id`,
  `mention_id`, `timeout_seconds`), mutations land only in the
  config-pinned state file, and the conversational gate path (including
  non-allowlisted senders and "/nunchi ..."-looking message text) can never
  mutate state.

### Fixed — documentation truthfulness sweep

- **Honest install instructions.** `pip install nunchi[discord]` is impossible
  from the published 0.2.0 release (PyPI 0.2.0 = core + `nunchi`/`nunchi-channel`
  only; the platform adapters landed later). README, `docs/adapters.md`, the
  Discord adapter docstring, and its missing-dependency error message now give
  source-install commands (`pip install "nunchi[discord] @ git+…"` /
  `pip install ".[discord]"`) with an availability note. Stale "not yet on
  PyPI" claims in README and `docs/integration.md` (false since 0.2.0 shipped
  on 2026-07-02) now state what PyPI actually carries versus what is
  source-only.
- **Beta labels disclose live-run status.** The adapter index tables in
  `docs/adapters.md` and README now footnote that the Matrix/Telegram/Discord
  adapters have full offline test coverage but have not yet been run against
  live servers.
- **Stale history defaults.** `NUNCHI_MATRIX_HISTORY`, `NUNCHI_TELEGRAM_HISTORY`,
  and `NUNCHI_DISCORD_HISTORY` docs and module docstrings said `10`; the code
  default has been `20` since the history-depth merge. A new enforcement test
  (`tests/test_docs_truthfulness.py`) pins documented defaults to the code
  constants so this class of drift fails CI.
- **Hermes `history_window` documented.** The functional-but-undocumented
  `history_window` config key (default 20, global `config.yaml` only — not a
  per-channel key) is now in the nunchi-gate plugin config docstring, also
  pinned by the enforcement test.
- **Changelog link hygiene.** Added the missing `[0.2.0]` compare anchor,
  pointed link references at `mentatzoe/nunchi` (was `mentatzoe/turnaware`),
  and `[Unreleased]` now compares from `v0.2.0`.

### Claude Code peer-hearing — transport patch + hook docs

- **Operator-carried Discord transport patch.**
  `integrations/claude-code/transport-patch/` ships
  `0001-allow-bot-messages-allowfrom.patch` for the official Claude Code
  Discord plugin (`anthropics/claude-plugins-official`): the unconditional
  bot-drop in the `messageCreate` handler (`if (msg.author.bot) return`)
  becomes a self-only drop, so explicitly allowlisted peer bots reach the
  session while the plugin's existing `gate()`/`allowFrom` access control
  remains the authorization layer (upstream issues #1153/#1559, still open).
  Built from and `git apply --check`-verified against upstream HEAD
  (`server.ts` blob `0595fc7`, fetched 2026-07-09); community reference:
  chenjr0719 fork, branch `fix/allow-bot-messages` (commit `e0474df`). The
  accompanying README documents what changes and why, exact apply steps
  (git checkout and installed-copy paths), how `access.json` composes as the
  second authorization layer — including the empty-`allowFrom` and
  bot-echo-loop caveats — and a live verification recipe with a negative
  check (non-allowlisted bot stays dropped).
- **Claude Code docs cover both hooks.** The Claude Code section of
  `docs/adapters.md` now documents the inbound `UserPromptSubmit` gate
  (merged 2026-07-08, previously missing from the adapter reference)
  alongside the outbound `PreToolUse` hook, with a direction/event/on-PASS
  summary table, the bot-deaf transport gap plus transport-patch pointer,
  and honest status wording: hooks merged and exercised against live channel
  traffic; transport patch is a local operator step, upstream fix pending.
- **Fixed stale outbound history default.** `integrations/claude-code/README.md`
  claimed the outbound hook's history window default was 10; the code default
  is 25 for both hooks (`NUNCHI_HOOK_HISTORY_WINDOW`). The note is corrected
  and the variable now appears in the outbound hook's environment table.

### Changed

- **Hermes dashboard tab: UX repair and product redesign.** Two rounds driven
  by a behavioral audit and direct owner review. Repair: Reset All actually
  clears (empty-dict-replaces semantics in a new tested `apply_state_patch`),
  per-field override deletion via `null`, overrides equal to the baseline are
  pruned instead of accumulating, success messages auto-dismiss, pending edits
  are badged, Save disables when clean, badges no longer pollute accessible
  names. Redesign: native hermes theming via host CSS variables and SDK
  components (zero hardcoded colors), human-readable channel names resolved
  from the hermes channel directory, a real `allow_from` editor, in-place help
  copy for sender policies and verbosity levels, per-channel `model` and
  `pinned_rules` (room governance) editing — `pinned_rules` joins the state
  whitelist — receipt rows show the full confidence distribution with a
  corrected four-verdict legend, and the receipts poll gained pause/interval
  controls plus visibility-aware suspension.

- **Dashboard round 3.** The Nunchi tab can now add channels directly (a
  picker of gateway-known channels not yet configured, plus free-text id
  entry; staged through the normal Save flow) with an inline note that the
  channel must also be one the gateway listens to. The global and per-channel
  model fields show the actual resolved model and its source (config /
  environment / .env) instead of an unhelpful "inherit" placeholder. Receipt
  rows are expandable disclosures rendering every logged field — full reasons,
  confidence table, model, message id, and (at debug verbosity) the complete
  gate payload and directive.
- **Dashboard verification round.** Fixed the text-input remount bug (typing
  no longer loses focus per keystroke), added an honest save contract (PUT
  echoes applied state and rejected keys; the UI reports fields the server
  did not accept instead of faking success) and an `api_version` handshake
  that banners loudly when the dashboard service runs an outdated backend,
  per-channel and global paths back to baseline (inherit options, per-channel
  clear, `allow_from` cleanup on policy change), readable channel-ID pills,
  effective-model display, verbosity meanings in the options, and label/input
  association fixes.

### Added

- **Telegram reference adapter.** `nunchi.adapters.telegram` joins Telegram chats
  as a gated participant using the Telegram Bot HTTP API over stdlib `urllib`
  (zero extra dependencies). Ships the `nunchi-telegram` console script. Features:
  - Long-polling `getUpdates` loop with offset persistence
    (`NUNCHI_TELEGRAM_STATE`)
  - Chat allowlist from `NUNCHI_TELEGRAM_CHATS` (comma-separated integer IDs)
  - PASS/ACK/ASK/SPEAK gate-first architecture; text messages only
  - Author-kind tagging: own messages are `self` (skipped as triggers),
    `is_bot=true` users are `peer_bot`, everything else is `human`
  - Pluggable responder callback; built-in demo responder shared with
    `nunchi-matrix` via `nunchi.adapters._responder`
  - `sendMessage` on non-silent verdicts (SPEAK/ACK/ASK)
  - JSONL receipt log (`NUNCHI_TELEGRAM_LOG`) with the same field shape as the
    Matrix adapter
  - Retry/backoff on HTTP 429 — honours `retry_after` from the JSON response
    body first, then the `Retry-After` header; permanent 4xx abort immediately
  - `--dry-run` and `--once` flags

- **Discord adapter (optional extra).** `nunchi.adapters.discord` joins Discord
  channels as a gated participant via discord.py's event-driven client.
  - Install from source with the `[discord]` extra (`pip install ".[discord]"`
    from a checkout); discord.py is not a default dependency and never leaks
    into the core install path
  - Configurable bot policy: `NUNCHI_DISCORD_BOT_POLICY=all` (default, gate all
    bots as peers) or `allowlist` (only bots in `NUNCHI_DISCORD_PEER_BOTS`)
  - History backfill of up to 10 messages via `channel.history` on the first
    event per channel
  - `NUNCHI_DISCORD_MAX_EVENTS` for bounded test runs (no `--once` — discord.py
    is event-driven)
  - Pure import-safe functions (`_resolve_author_kind`, `_append_to_history`,
    `_build_receipt`) live at module level and are testable without discord.py
  - Ships the `nunchi-discord` console script; `--dry-run` flag supported

- **Shared demo responder.** `nunchi.adapters._responder._demo_responder`
  extracted from the Matrix adapter into a shared internal module so Telegram,
  Discord, and future platform adapters can reuse it without copying code. The
  Matrix adapter public API is unchanged.

- **Adapter docs index.** `docs/adapters.md` is the new single-source adapter
  reference: an index table (adapter, surface, install weight, status), full
  setup guides for Matrix, Telegram, and Discord, and links to the Hermes plugin
  and Claude Code hook integration docs. The full Matrix adapter section has
  moved from `README.md` to `docs/adapters.md`; the README now carries a compact
  overview table with a link.

- **Matrix reference adapter.** `nunchi.adapters.matrix` joins Matrix rooms as a
  gated participant using the Matrix Client-Server API over stdlib `urllib` (no
  `matrix-nio` or other runtime dependencies). Ships the `nunchi-matrix` console
  script: one command to stand up a read-the-room agent on Matrix. Features:
  - Long-polling `/sync` loop with since-token persistence
  - PASS/ACK/ASK/SPEAK gate-first architecture: every inbound message is checked
    before any response is generated
  - Pluggable responder callback (`respond(trigger, history, gate_result) -> str | None`);
    a built-in demo responder (OpenAI-compatible chat-completions via `urllib`) is
    included and clearly labelled a demo
  - Author-kind tagging: own messages are `self`, user IDs matching
    `NUNCHI_MATRIX_PEER_BOTS` are `peer_bot`, everything else is `human`
  - Encrypted-room detection: `m.room.encrypted` events are skipped with a
    one-time per-room warning; unencrypted rooms only
  - JSONL receipt log per gated event with verdict, action, elapsed_ms, reasons
  - Retry/backoff on HTTP 429 and 5xx; permanent 4xx errors abort immediately
  - `--dry-run` flag (gates but never sends) and `--once` flag (one sync batch
    then exit, for cron/testing)
  - Room allowlist from `NUNCHI_MATRIX_ROOMS`; events outside the allowlist are
    ignored
  - Open Floor Protocol vocabulary alignment: SPEAK/PASS/ACK/ASK map onto OFP
    floor semantics so future OFP compatibility requires no translation layer

### Evidence (room sessions)

- **Room-session receipt evidence (003).** New stats-only evidence file
  `evidence/verdict-suite/room-sessions-2026-07-02+05.md`
  covering the 2026-07-02 first live in-room deployment and the 2026-07-05
  organic multi-agent session: per-participant verdict distributions, the
  three enforced denials, mention-fastpath hits, history_len stats (100%
  hermes-side blind — the F1 regression, quantified), UTC timeline bounds,
  integration paths, and itemized discrepancies against the operator's
  private retrospective (two off-by-one counts and a fastpath count
  corrected). States the Station receipts-log test-artifact contamination as
  a caveat. Zero message content, per the evidence redaction convention.
- **Evidence index repaired.** The evidence `README.md` index now lists the
  open-weight bake-off (`model-selection-openweight-2026-06-14.md` +
  `bakeoff-openweight-2026-06-14/`), `history-depth-2026-07-07.md`, and the
  new room-sessions file.

## [0.2.0] - 2026-07-02

### Changed

- **Renamed to nunchi.** The project, package, module, console scripts, and
  environment variables are now `nunchi` (눈치 — the art of reading the room
  and knowing whether it is your turn to speak; the word means exactly what
  the gate does). `turnaware` was never published to PyPI, so this is a clean
  break: `TURNAWARE_*` environment variables become `NUNCHI_*`, the
  `turnaware`/`turnaware-channel` scripts become `nunchi`/`nunchi-channel`,
  and `TurnAwareError` becomes `NunchiError`. Historical spec narratives and
  captured evidence keep the old name as a matter of record.
- **Social core prompt.** The classifier system prompt now poses the
  read-the-room question — who is speaking, what has been said, who is this
  agent; is it this agent's turn? — judged as a socially competent participant
  would. Room doctrine inherited from the open-floor pilot (default-PASS,
  net-new-value bar, ACK-rarity, operator-only directives, corroboration for
  completion claims) is no longer baked into the core prompt; rooms opt into it
  (or any other governance) via `pinned_rules`, which the prompt now applies
  with precedence over plain social sense.
- **Tolerant reference bookkeeping.** Near-miss `context_checked` references
  from the provider (bare `trigger`, prefix-less ids) normalise to their
  canonical envelope references, and unrecognisable references are dropped,
  instead of failing the whole evaluation with "unchecked context references".
  Dropping is conservative for `require_pass_corroboration`: a PASS whose only
  corroboration was an unknown reference ends up uncorroborated and is
  downgraded, never upgraded.

### Added

- **Room governance profiles.** `profiles/open-floor.md` preserves the
  open-floor pilot doctrine as reusable `pinned_rules` text. The 003 verdict
  suite loader accepts a `governance_profile` metadata field and injects the
  named profile into the fixture envelope as a `pinned-rules` context item;
  the five fixtures whose expected verdicts were adjudicated under that
  doctrine now declare it explicitly.

## [0.1.0] - 2026-06-16

### Added

- **Admission core.** A pre-reply admission gate that returns exactly one of the
  four verdicts `PASS`, `ACK`, `ASK`, or `SPEAK`. `PASS` is a hard stop: no
  ordinary user-visible room message is emitted. Admission results never carry
  reply prose (`message`, `reply`, `draft`, and `content` are forbidden result
  fields), keeping the boundary at admission rather than reply composition.
- **Provider-backed classifier.** A `product` classifier backed by an
  OpenAI-compatible chat-completions client built on the standard library
  (`urllib`), defaulting to OpenRouter. Configuration is security-hardened:
  API keys come from the environment (`OPENROUTER_API_KEY` or
  `TURNAWARE_CLASSIFIER_API_KEY`), the model is set via
  `TURNAWARE_CLASSIFIER_MODEL`, and the base URL is overridable via
  `TURNAWARE_CLASSIFIER_BASE_URL`.
- **Classifier rubric and live model selection.** A documented rubric for the
  four-verdict decision, with `gemini-3.1-flash-lite` as the default live model
  selection (plus an open-weight alternative captured in the selection evidence).
- **Provider resilience.** Bounded retry with exponential backoff on transient
  provider errors (HTTP 429/5xx, timeouts); permanent errors (401/403 and other
  4xx) abort immediately. Tunable via `classifier_config.max_retries` and
  `retry_base_delay`.
- **Deterministic fast-path.** A conservative pre-classifier that resolves
  certain-from-the-envelope cases (an `<@id>` mention aimed at another agent, or
  a self-echo) to `PASS` without a provider call, cutting per-turn cost and
  latency; anything ambiguous escalates to the classifier. Disable with
  `TURNAWARE_FASTPATH=0`.
- **Opt-in PASS-corroboration mode.** `classifier_config.require_pass_corroboration`
  (default off) downgrades an uncorroborated `PASS` (one with no consulted
  `context:` reference) to `ASK`, for surfaces that must challenge unverified
  completion claims.
- **Transport-neutral channel adapter.** A `turnaware-channel` adapter that emits
  a transport-neutral verdict-plus-silent JSON envelope by default, exposes a
  generic suppression token for any transport, and offers a `cc-connect` preset
  (`--format cc-connect`) emitting the `CC_CONNECT_SILENT_PASS` sentinel.
- **CLI.** A `turnaware` console script with an `admit` command that reads a
  request from stdin and writes the admission verdict as JSON.
- **Packaging.** A stdlib-only distribution (zero runtime dependencies) that
  installs cleanly in one line and ships the `turnaware` and `turnaware-channel`
  console scripts.
- **CI.** A fully offline GitHub Actions matrix (Python 3.11/3.12/3.13) running
  the `unittest` suite plus a clean-install packaging job that verifies the
  public surface and console scripts.
- **Stability contract and drift detection.** `docs/STABILITY.md` documents the
  stable verdict/result/request surface and the SemVer policy; a manual
  live-smoke job and a scheduled weekly live corpus eval (`scripts/live_eval.py`)
  track provider/model drift.
- **Integration guide.** Documentation covering configuration and adapter
  integration for embedding the admission gate, including a drop-in loader
  template and a generic (non-cc-connect) host example.

[Unreleased]: https://github.com/mentatzoe/nunchi/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/mentatzoe/nunchi/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/mentatzoe/nunchi/releases/tag/v0.1.0
