# Hermes Integration: Nunchi V2

> **Pre-activation draft technical-review object, not current behavior.** This
> directory contains a Slice 060 implementation draft for Codex review. It is not
> a canonical candidate or handoff, is not installed by `nunchi-install`, and has
> no integration authority while Slice 060 remains `PLANNED`.

`nunchi-gate` binds one Nunchi participant to an exact Hermes profile,
transport-authenticated self actor, and native room scope. It retains bounded
structured observation, schedules one attention opportunity, and either
suppresses the wake or redispatches the exact event into one ordinary Hermes
act-or-silence turn.

The draft plugin path is V2-only. It was verified against the pinned
installed Hermes source below but was not installed or armed. Retired V1
verdict, command, and quiet-room machinery is absent from the executable
packet; migration history is preserved only in
[`../../docs/archive/v1/hermes-nunchi-gate.md`](../../docs/archive/v1/hermes-nunchi-gate.md).

## Pinned host

The private host wrappers in this packet were inspected and evaluated against:

- Installed Hermes version: `0.19.0`
- Installed Hermes commit: `279be8211d8347cc3500b9a78c6a0f8cb4d92a6a`
- Candidate base: `8e64746970f9910d03b372291c5aa173883e869f`

The wrappers target:

- `BasePlatformAdapter.set_busy_session_handler` for admission before Hermes
  queue/interrupt behavior;
- `GatewayRunner._handle_message_with_agent` for whole participant-turn outcome;
- `BasePlatformAdapter._process_message_background` plus terminal text/media and
  interactive methods, including Telegram drafts and clarification/approval
  prompts, for whole-process transport outcome;
- `discord.ext.commands.Bot.dispatch` and `DiscordAdapter._handle_message` for
  ordered eligible self/peer-directed context, pre-mutation literal mentions,
  and parent-channel continuation before response filters/auto-thread output;
- `TelegramAdapter._enqueue_text_event` to preserve each scoped native text
  update rather than consume Hermes' lossy concatenation batch;
- Hermes `pre_gateway_dispatch` and `pre_llm_call` hooks;
- Hermes `tool_execution` middleware.

A different Hermes revision requires a new source inspection and compatibility
run. Do not assume private wrapper compatibility from the semantic version
alone.

## Configuration

The Nunchi package from the exact candidate checkout must be importable by the
Hermes process. The operator policy must be an owner-only absolute JSON file
accepted by `nunchi.policy.OperatorPolicySource`.

```yaml
plugins:
  enabled:
    - nunchi-gate

nunchi:
  enabled: true
  api_version: 2
  participant_id: resident
  policy_path: /absolute/owner-only/path/nunchi-v2-policy.json
  platforms: [discord, telegram]
  channels: ["1518384310321811456", "-1001234567890"]

  # Required by this candidate. Streaming bypasses the whole-turn/final-send
  # receipt boundary and therefore fails the supported-host precondition.
  streaming: false
```

`channels` entries are native Discord channel/thread IDs or Telegram chat IDs.
A Telegram topic can be selected explicitly with the parent-qualified canonical
form `telegram:chat:<chat-id>:topic:<topic-id>`. A raw Telegram topic ID is never
matched independently because topic IDs are only unique within their parent chat.

Hermes' effective profile/platform streaming setting must also be disabled. The
plugin resolves that host setting independently; the Nunchi field is not treated
as proof. If either setting enables streaming, the room is outside V2 scope.
Terminal sends attempted before participant-host completion are blocked before
platform I/O as a separate fail-closed rail.
Gateway proxy mode and every effective per-session
`model.openai_runtime: codex_app_server` selection are unsupported because they
bypass ordinary Hermes tool middleware. Immediately before a ticketed turn, the
plugin re-attests those host facts plus participant, semantic policy,
authenticated binding, and normalized session. Explicit scoped Discord
self-mentions continue in their parent channel without entering Hermes'
auto-thread attempt/error branch. Processing typing/reactions/voice
acknowledgements are suppressed rather than emitted outside receipt accounting.

The policy's `attention.participant_id` and
`recoverability.participant_id` must equal `nunchi.participant_id`. Its
`recoverability.continuity_scope_id` must equal the exact binding generated for
the current profile, platform, authenticated self actor, and room. A mismatch
fails closed.

For Discord, the pinned raw-dispatch wrapper retains exact self echoes and
already-authorized peer-directed context that Hermes' response filters would
otherwise drop. It mirrors host bot/user/channel authorization and creates no
attention opportunity for context-only events. Nunchi does not infer a
participant roster from names or message prose.

## Exact state partition

Each process-local binding key is:

```text
(profile_name, platform, authenticated_self_actor_id, native_room_scope_id)
```

Display names, aliases, role labels, and model names never establish self.
Discord self identity comes from the authenticated adapter client user. Telegram
self identity comes from the authenticated bot. Room scope includes native
thread/topic identifiers when present.

Observation is bounded and structured. This candidate truthfully reports
`continuity: session-only` and `has_restart_gap: true`; retained context may be
restored by an explicitly trusted host path, but scheduler obligations and wake
tickets are never restored. Social suppression therefore remains subject to the
canonical recovery valve: an unproven suppression widens to `DEFER`.

## Turn lifecycle

1. Human input passes Hermes authorization before entering Nunchi state.
   Internal/control events are rejected; exact profile/adapter identity and room
   scope are resolved from native transport facts.
2. Busy-room input is admitted through Hermes' busy-session handler before its
   queue/interrupt path. A ticket redispatch waits for the current owner to
   release the adapter session guard.
3. Eligible raw Discord self/peer-directed filtered events are captured before
   host content mutation, retained in transport order as context only, and create
   no attention opportunity. Scoped Telegram text bypasses host concatenation so
   each native update retains its own ID and entity set.
4. Policy loading and the participant-shaped classifier run off the gateway
   event loop.
5. Effective `SUPPRESS` writes observation and attention stages and does not
   invoke Hermes.
6. `WAKE`, either `DEFER`, disabled-preattention bypass, or default error fallback
   creates one one-use ticket correlated to the exact native trigger.
7. The ticket redispatches the native event. `pre_llm_call` injects structured
   `I-010C` facts plus separately labelled untrusted attention annotation. It
   asks for no admission verdict or meta-answer.
8. The whole-turn wrapper records `participant-host` before returning a final
   message to the adapter. Silence completes without transport.
9. Terminal platform output is blocked until participant-host completion. One
   conservative `transport` receipt is recorded only after the complete adapter
   output process and every observed terminal text/media method finish.
10. Completion promotes only the newest pending anchor off the event loop. No send-time social
   classifier runs.

## Supported and unsupported action surfaces

| Surface | Candidate behavior |
|---|---|
| Normal non-streaming final message | Supported; participant-host precedes platform I/O and one transport receipt follows whole-process output closure |
| Normal participant silence | Supported; participant-host records `silent`, no transport is fabricated |
| Explicit non-privileged model tool during a ticketed turn | Supported only after participant-host receipt persistence and exact transport-session binding |
| Privileged file/terminal/host-command effect | Supported only through the shared `I-040B` guard/coordinator, exact operation digest, canonical room scope, matching active grant, audit persistence, and re-attestation |
| Model-requested reaction | Supported only for exact native target aliases in the canonical room and after `I-040B` authorization |
| Concurrent registry tool, nested `execute_code`, detached/background effect | Unsupported and fail-closed/not claimable |
| Hermes processing typing/reactions/voice acknowledgement | Suppressed for scoped V2 processing; never counted as participant output |
| Direct platform send/edit/delete, model-issued slash command, auto-TTS | Outside the verified effect boundary; unsupported |
| Gateway proxy or `codex_app_server` runtime | Outside V2 scope; rejected at admission and participant-time re-attestation |
| Streaming final reply | Unsupported; Nunchi and effective Hermes profile/platform streaming must both be disabled |
| Cron/script-only, plugin direct dispatch, MCP bridge send | Unsupported because exact origin-event provenance is absent |

Non-Nunchi turns pass through tool middleware unchanged. Middleware denial is a
terminal return value rather than an exception because Hermes middleware is
fail-open when a callback raises before `next_call`.

## Verification

From the exact candidate checkout:

```sh
.venv/bin/python -m unittest \
  tests.v2.test_hermes tests.v2.test_hermes_eval -v

.venv/bin/python -m evals.v2.hermes.runner \
  --hermes-source /absolute/path/to/hermes-agent \
  --output evidence/v2/hermes/hermes-scenes.jsonl \
  --require-complete
```

HM-01 through HM-03 are deterministic sandbox evidence. HM-04 and HM-05 are
explicitly synthetic, not live Discord/Telegram proof. HM-06 is exact installed
source inspection plus registration against the installed classes, not proof
that this candidate plugin was deployed or that a live provider/model turn succeeded.

See [`../../docs/integrations/hermes-v2.md`](../../docs/integrations/hermes-v2.md)
and [`../../evidence/v2/hermes/verification.md`](../../evidence/v2/hermes/verification.md)
for the packet manifest and evidence grades.
