# Rehearsals: a live model in each real harness (step 9f)

**Status: the probe ran live once and passed in all three harnesses.** On
2026-10-09 the first dispatch of the `rehearsal` workflow
([run 37912807549](https://github.com/mentatzoe/nunchi/actions/runs/37912807549))
ran a live model through Claude Code, Codex and Hermes, each on its pinned
install, with Nunchi and live attention, and every job passed (findings
below). PR 2 adds Claude Code's scripted lane and the settled spend reading:
**implemented, unverified** in CI. The scripted Claude Code probe has run
here, offline, against the pinned Claude Code 2.1.289, with its sandbox on
and off; CI's `claude-code-mod` job runs it with the sandbox on and has not
run yet. The settled spend reading has not met
OpenRouter yet. PR 3b's Discord room, where Nunchi's own Discord processes
run on the Discord stand-in (below), is **implemented, unverified** in CI.
PR 3c adds Hermes's own gateway process to it (The Hermes column, below):
**implemented, unverified** in CI too. PR 4a adds a director that plays four
of the behavior suite's multi-person scenes on the reference column and grades
them from each scene's own draft expectations (Directed scenes, below):
**implemented, unverified** in CI too. PR 4b plays the same four scenes
through Claude Code and Codex, with the reference as the control:
**implemented, unverified** in CI too. PR 4c plays seven more, the ones where
timing and the agent's own history matter: a message that lands while the
agent is composing, a question asked while it is busy, a promise it made, a
nod it gave: **implemented, unverified** in CI too. PR 4d lets the manual
`rehearsal` dispatch play the directed scenes with a live model behind each
column on the stand-in, so we can see how a live agent reads a multi-person
room through the reference, Claude Code and Codex (Live scenes, below):
**implemented, unverified**. No live run has been made yet; the unit tests use
a fake provider on loopback, and nothing in this PR's checks spends anything.

## The first live run (2026-10-09)

Every job passed: each harness reached its model through OpenRouter and
took part in the room through Nunchi, with attention judging. What it
showed besides:

- **Claude Code loads three plugins built into its binary** besides the mod:
  `cc-plugin-agents-md`, `cc-plugin-telemetry` and
  `cc-plugin-plugin-authoring` (its `init` names them with `path: builtin`).
  They come with the stock install; the probe records them
  (`mod_loaded.init_plugins`) and does not fail on them.
- **Codex has no model metadata for the slug** (`anthropic/claude-haiku-4.5`)
  and falls back to its defaults for an unknown model. The turn still ran.
- **Hermes's terminal is unsandboxed by default**: its `local` backend runs
  the agent's commands as the user. The run records it (`sandbox: off`), as
  designed.
- **R3: OpenRouter passed Codex's namespace tools through.** The Codex run
  on `anthropic/claude-haiku-4.5` passed, so R3 did not block it (below).
- **The spend watchdog read $0 in every job.** OpenRouter's usage figure for
  the key lags behind the calls, so no reading between moments, or right
  after the last, had moved. The reading after the last moment now reads it
  up to a bound and keeps each read (Cost, below).

## What the probe proves, and what it does not

For each harness, on a clean, pinned install (Claude Code 2.1.289, Codex
0.160.1, Hermes `a50406d9`), one dispatch shows:

- whether the harness reaches a live model through OpenRouter on its own
  route, with attention live too: Claude Code's `claude -p`, `codex
  app-server`, and Hermes's `GatewayRunner` in the probe's process;
- whether the agent takes part in a room through Nunchi: a wake becomes a
  turn bound to it, the turn ends with the harness's own result, it makes at
  most one room action, that action is delivered, and the room shows only
  what the library committed;
- that a harness failure fails the run with its name, never reads as silence;
- that no committed post names Nunchi's machinery;
- that neither the key nor a planted canary appears in any output.

It plays two moments, message by message, as live deliveries:

1. a bot's status report (`bot-status-report` from the behavior scenes):
   expected, no harness turn;
2. a person asks the agent a direct question
   (`evals/rehearsal/scenes/direct-question.json`): expected, one post.

The status report goes first so that the room's clock only moves forward.
In a live run, whether each moment went as expected is **reported, never pass
or fail**: the model decides. A moment whose graded message never reached
Nunchi reads `not delivered`, and a graded turn that attention's error
fallback woke is marked as not attention's judgment. With `--scripted` the
model and attention are scripted, so each moment's outcome is known and is a
hard check, and for Codex and Claude Code so is the room tool call.

Hermes drops other bots' messages before any plugin hook by default
(`discord.allow_bots: none`). The probe gives Hermes the README's peer-agent
settings, `discord.allow_bots: all` and `discord.bots_require_inline_mention:
false`, so the bot's status report reaches attention there as in the other
harnesses. As the README says, they apply to the whole profile, and Hermes's
bot loop guard still drops bot messages once bots post 20 in 5 minutes in one
chat.

It does not prove:

- **That it works in a real room.** The room is an in-process stand-in.
  Claude Code and Codex run through their production runtimes
  (`ClaudeCodeRoomRuntime`, `CodexRoomRunner`) with a stand-in for the
  shared Discord transport. Hermes runs its real `GatewayRunner` in the
  probe's process, on the conformance kit's Discord world, with the shipped
  plugin directory loaded from a Nunchi config written as its README says.
  With `--room discord` (PR 3b and 3c, below), the harnesses' own Discord
  processes run on a Discord stand-in at Discord's real names, scripted only:
  Nunchi's for Claude Code, Codex and the reference, and Hermes's own
  gateway, `hermes gateway run`, with the plugin. The live probe's two moments
  keep the in-process room; only a directed scene is played live on the
  stand-in (PR 4d, Live scenes).
- **How well the agent reads the room.** Two moments, once each. Beside
  them, `--scene` plays one behavior scene on the reference, Claude Code or
  Codex column and grades it from the scene's own draft expectations, with the
  agent and attention scripted (Directed scenes, below): that checks the
  director, the grader and each harness's wiring to the room, not a model. A
  live run of a scene is PR 4d (Live scenes, below); its grades are drafts
  compared with a live agent, reported and never failed.
- **Hermes's own model as attention** (`hermes-host`). Attention is the same
  OpenRouter chat route in every harness here.
- **That Claude Code sends nothing past its proxy settings in CI.** Its
  scripted lane sees only what Claude Code sends through `HTTPS_PROXY` (below);
  a connection that ignored the proxy settings would not be seen there.

## Claude Code offline (`--scripted`)

The scripted lane runs the real `claude -p` and the Nunchi mod, through the
same `ClaudeCodeRoomRuntime` as a live run, with no provider and no key, at
$0 (a Claude Code cloud container's own credential is the exception, below):

- **The model** is a scripted Anthropic Messages endpoint on localhost
  (`standin.ScriptedClaudeAgent`), set as `ANTHROPIC_BASE_URL`. It answers
  only a streamed `POST /v1/messages`, in the event shape Claude Code
  2.1.289 reads (`message_start`, each content block's start, delta and
  stop, `message_delta`, `message_stop`). A call that offers the mod's
  `mcp__nunchi__room_send` gets a `tool_use` of it with the scripted answer;
  the call that carries its result gets a short text, which ends the turn;
  a streamed call without the room tools gets a short text. Anything else,
  a call without `stream` included, gets a 404: when Claude Code cannot read
  a stream it retries the call without one, and that fallback must fail the
  turn, never pass it. Its requests are recorded
  (`transcript/scripted-model-requests.json`, and the counts in the report's
  `scripted_model`), without the key's value.
- **Everything else** Claude Code sends through its proxy settings goes to a
  local proxy that refuses it (HTTP 403) and names it
  (`standin.RefusingProxy`): the probe sets `HTTPS_PROXY`, `HTTP_PROXY` and
  their lowercase forms to it, with `NO_PROXY=127.0.0.1,localhost`, in
  Claude Code's session and the version read for the record, never the
  probe's own process (Python's `urlopen` keeps the
  proxy settings it first saw for the whole process). The
  report's `network` lists each `host:port` and how often, read after
  Claude Code has exited, since it still tries to reach Anthropic as it
  shuts down; its detail is among the first lines of `summary.md`.
- **Attention** is the scripted chat endpoint the other lanes use: it wakes
  for the direct question and lets the bot's report pass.

So the scripted model calls the mod's room tool to post the scripted answer
on the direct question, and the bot's report gets no turn; both are hard
checks (`scripted-outcomes`), with the room tool call read from Claude
Code's own stream-json. A Claude Code result that is an error fails the run
too, even after the post (What a pass means, below).

**With Anthropic's servers out of reach, the mod loads.** Run here on
2026-10-09 with the pinned 2.1.289, inside a network namespace with only
loopback and with every `connect` of Claude Code's process tree traced
(`strace -f`), Claude Code made no connection outside loopback and no DNS
lookup: its connections were the scripted endpoint, the proxy, the mod's own
MCP server inside the process, and the gate's socket. Everything it tried
past them was a `CONNECT api.anthropic.com:443` through the proxy, refused.
A review that put a TLS-terminating stand-in in the proxy's place, logging
paths, header names and lengths but no value, saw what they were:

- `GET /mcp-registry/v0/servers` (the MCP registry) and `POST
  /api/event_logging/v2/batch` (a telemetry batch of about 300 KB, sent as
  Claude Code exits), both without a credential;
- `GET /api/claude_cli/bootstrap` and `GET /api/claude_code_penguin_mode`,
  each with `Authorization: Bearer` and a credential Claude Code read from
  a file, not the route's `ANTHROPIC_AUTH_TOKEN`.

That file is a Claude Code cloud container's own credential. The pinned
2.1.289 reads `/home/claude/.claude/remote/.oauth_token` (and its siblings
`.api_key` and `.session_ingress_token`) from that fixed path, whatever
`HOME`, `CLAUDE_CONFIG_DIR` or a clean environment say. This container has
it, so here Claude Code tried all four requests (`CONNECT x4` in the
record); with that directory hidden in a private mount namespace it tried
only the registry and the telemetry batch (`CONNECT x2`), and the run still
passed. "No key" therefore holds only where that directory is absent, as on
a CI runner. The proxy refused the bootstrap calls, so the credential did
not leave the machine; the report records which of those files Claude Code
could read (`fixed_credentials`, paths only, never their contents), and
`summary.md` says so among its first lines when one is readable. A live run
from such a container would send them as the container's account, so run
live probes from CI. The mod loaded (its `init` lists `nunchi` beside the
three built-in plugins), attached, bound the turn, and posted through the
room tool in every one of these runs, with Claude Code's sandbox on and
with it off (`--no-sandbox`); CI runs it on.

CI runs this lane in the `claude-code-mod` job of `ci.yml`, after the mod's
validation and tests, on the same pinned version: the pinned Claude Code
from npm, bubblewrap and socat installed and checked as the rehearsal
workflow does, the probe's tests, then the scripted probe with the README's
sandbox on. `--no-sandbox` runs Claude Code without its Bash sandbox
(`sandbox.enabled: false` in the clean user's settings) for a machine where
bubblewrap cannot run; the run records the sandbox as off. It is for Claude
Code only, and CI never passes it.

## The Discord stand-in (PR 3a)

**Status: implemented, unverified in CI; Nunchi's own Discord processes
run on it in the Discord room (PR 3b, below).**
`evals/rehearsal/fake_discord/` answers as Discord's REST API and gateway,
so that the production Discord processes (`hermes gateway run`,
`nunchi-mcp-discord` with both runners, `nunchi-discord`) run on it
unmodified: PR 3b brought Nunchi's own processes and the launcher that
maps Discord's names to it, PR 3c `hermes gateway run`. Here, offline, it has
run against Nunchi's transport clients and against real discord.py 2.7.1 on
Python 3.12 and 3.14.

It is a library, `FakeDiscord`, on its own thread in the caller's process.
It behaves like Discord wherever a column reads the room from:

- **time**: each channel has a clock that only moves forward, and a thread
  keeps its parent's. A message the director posts, as a person or a
  scripted bot, takes its scene time, raised (and recorded) when that would
  put its id before the clock's last; a bot's own post through REST is
  stamped when it arrives, which brings the clock to the wall. Ids come
  from the clock and only increase;
- **who is addressed**: user and role mentions, `@everyone` and `@here`
  only with MENTION_EVERYONE, a bot's `allowed_mentions`, and reply pings
  (a world setting: Discord's default is unverified);
- **what replies to what**: type 19, `message_reference` and
  `referenced_message`, `fail_if_not_exists`, and the reference echoed in
  the create response, which the transport's acknowledgement check needs;
- **who wrote it**: people without `bot`; bots with `bot: true`, their
  `nonce` echoed and `enforce_nonce` honored;
- **who may see, post or react**: one permission function, Discord's
  algorithm, behind fan-out, the 403s and the GETs the transport's reaction
  capability reads;
- **the agent's own limits**: 2000 characters, no empty message, 20
  distinct reactions, and an approximate emoji check that refuses a word or
  two emoji sent as one reaction.

It serves only the routes something has been shown to call: login, posts,
reactions, and the channel, member and roles reads, and, since PR 3c, the
ones Hermes calls (The Hermes column, below). Any other route or host
gets 599, as does a request field or body it does not model (a file's
multipart, say) and a request it fails on. discord.py does not retry a 599;
Nunchi's transport retries a GET three times (about 14 s), and each attempt
is recorded. Each of those, an unknown gateway op (closed with 4001), a
gateway URL other than v10 JSON, a TLS name not Discord's, and a payload it
sends without a key discord.py 2.7.1 requires (the shape pin,
`discord_types.json`, read from `discord.types` by AST) is recorded as
`unknown`, which fails the stand-in's verdict: Hermes swallows many REST
errors, so the stand-in's own record decides. The director (PR 4) posts
as a person or as a scripted bot that belongs to no harness, never as a
harness's bot (every bot is a harness's, with a token, unless the world
says `"harness": false`); creates threads; reconnects, invalidates, closes
or drops a bot's gateway session; injects faults (a 429 with `Via` and a
JSON body, as discord.py needs); moves a channel's clock; and waits on the
wire.

With an output directory it writes `world.json` (ids, roles, permissions and
intents: what configs read, and the checklist for a real guild; never a
token), `discord-wire.jsonl` (every TLS hello and completed handshake,
exchange, frame and control call, each token replaced by `<bot:name>`) and
`discord-standin.json` (what each bot did, every unknown and raised time,
and the `fidelity` list of what is not modelled). Its tests are `tests/v2/test_fake_discord.py`
(standard library, in the `test` job) and
`tests/v2/test_fake_discord_discordpy.py` (in the `discord-standin` job on
Python 3.12 and the `hermes-plugin` job on 3.14, each after `python -m
evals.rehearsal.fake_discord.shapes --check`).

## The launcher (PR 3b)

**Status: implemented, unverified in CI; run here offline. The probe's
Discord room (below) runs inside it, in three CI jobs.**
`evals/rehearsal/discord_net.py` makes Discord's names lead to the stand-in
for one run, so that Nunchi's own Discord processes can run against it
unmodified, at Discord's real names and over TLS:

```sh
sudo -E "$PY" -m evals.rehearsal.discord_net --offline -- "$PY" -m evals.rehearsal.probe ...
```

Run it from the repository's root. `sudo -E` keeps the environment but
resets `PATH` and drops `PYTHONPATH`, so name each Python by its full path,
with Nunchi installed in it. In order, the launcher:

1. makes a per-run CA, limited by name constraints to `discord.com`,
   `discord.gg`, `discordapp.com` and `discordapp.net`, and one leaf for the
   five names the stand-in answers; the CA's key is deleted at once;
2. enters a private mount namespace (`unshare --mount --propagation
   private`, plus `--net` with `--offline`, which leaves only loopback) and
   mounts there a copy of `/etc/hosts` that maps the names to 127.0.0.1 and
   `::1` alone (a line for each, so that a lookup for an IPv6 address cannot
   reach the real service either: nothing listens on `::1`, a client falls
   back to 127.0.0.1, and an IPv6-only one is refused), and a copy of
   `/etc/ssl/certs` with the CA in the bundle and the hashed directory, so
   each Python trusts it with its default context;
3. sets `net.ipv4.ip_unprivileged_port_start=443`, so the stand-in binds
   443 as you. The setting belongs to the network namespace. Without
   `--offline` it would change this machine's, so the launcher refuses that
   unless it is on a GitHub Actions runner (`CI=true` and `GITHUB_ACTIONS=true`,
   both: `CI` alone is a variable anyone sets), and restores it afterwards; that mode exists for live
   lanes, which need their model provider's network, and no scripted lane
   uses it. The first user is PR 4d's live scenes, in the manual `rehearsal`
   workflow only (Live scenes, below);
4. checks that no proxy variable is set (`HTTP_PROXY`, `HTTPS_PROXY`,
   `ALL_PROXY`, `WS_PROXY`, `WSS_PROXY` or `DISCORD_PROXY`, in any case: the
   transport's REST calls and Hermes's discord.py follow one past the
   mapping), that each name resolves to 127.0.0.1 alone, and, with
   `--require-bwrap`, that `bwrap --ro-bind / / true` runs as you, so a
   sandbox that uses bubblewrap fails before any harness starts. Only a lane
   whose harness sandbox uses bubblewrap passes the flag (Claude Code and
   Codex); without it the check does not run, and the record says `checked:
   false, skipped: not required`;
5. runs the command as you (`SUDO_UID`, `SUDO_GID` and your groups), with
   `NUNCHI_DISCORD_NET` naming `net.json`: the names, the stand-in's
   certificate and key, and what the launcher did. When the command ends,
   the run's files, the key included, are removed. The exit status is the
   command's, which can be any number, or 2 for a refusal and 3 for a failed
   setup or check, including a namespace that could not be made.

The launcher maps Discord's names and cuts TCP and UDP with `--offline`; it
is not a filesystem or privilege sandbox, and it runs this checkout and the
chosen Python's packages as root before it drops to you, so run it only on a
checkout you have read. Root writes and changes an owner only in directories
only root can write: the run directory and `tls/` stay root's (0711), you own
the leaf key alone, and the chain and `net.json` are root's and readable
(0644), so nothing running as you can redirect what root writes. SIGTERM and
SIGHUP end the launcher after the run's files are removed and the port
setting restored, whenever they come, and are passed on to the command; the
probe turns them into an interrupt, as Ctrl-C does, so it stops the Discord
processes it started.

The stand-in has one route of its own for this, `GET
/api/v10/_preflight/{nonce}`: it needs no token and answers the run's nonce
(`FakeDiscord.preflight_nonce`); any other nonce gets 404 and an unknown.
`python -m evals.rehearsal.preflight --nonce N`, run in a Discord process's
own environment once the stand-in is up, repeats the proxy and name checks,
GETs that route on the default SSL context, and opens TLS to each other name,
which must show the same certificate. A proxy, a name that leads elsewhere,
an untrusted certificate or another run's stand-in fails it.

Proxy variables alone could not do this: the transport's gateway client and
`nunchi-discord` ignore them and would reach the real Discord. Every Discord
client here resolves names through glibc and trusts OpenSSL's default paths,
which is what the launcher changes. Run here offline (2026-10-09), with the
stand-in at port 443: the preflight, the transport's REST client and its
gateway client reached it by name on Python 3.11, 3.12 and 3.14, as root and
as an unprivileged user, and this machine's `/etc/hosts`, trust store and
port setting stayed unchanged. Not run yet: without `--offline` (that needs
a runner), and the bubblewrap check itself, since bubblewrap is not
installed here. CI passes `--offline` too, so the port setting stays in the
run's namespace on a runner as well, and passes `--require-bwrap` only for
Claude Code and Codex (Hermes's terminal backends use no bubblewrap, and its
default, `local`, runs the agent's commands unsandboxed).
Its tests are `tests/v2/test_discord_net.py`; the one that runs the
launcher needs root, so it skips in the `test` job.

## The Discord room (PR 3b)

**Status: implemented, unverified in CI. Run here offline, inside the
launcher, for Claude Code (2.1.289, with `--no-sandbox`), Codex (0.160.1)
and the reference: every hard check held in each (2026-10-09, and again on
2026-10-10 with the transport's three gaps closed, below).** `--room discord` plays
the probe's moments on the Discord stand-in at Discord's real names, with
Nunchi's own Discord processes unmodified (`evals/rehearsal/discord_room.py`):

```sh
sudo -E "$PY" -m evals.rehearsal.discord_net --offline -- \
  /usr/bin/env PATH="$PATH" "$PY" -m evals.rehearsal.probe --harness codex --scripted --room discord --out rehearsal-out
```

`--room standin` stays the default. The Discord room's moments are scripted
only (a live run of them keeps the in-process room; only a directed scene is
played live there, PR 4d) and the room runs only inside the launcher: without
its `NUNCHI_DISCORD_NET` the probe could not run (exit 3) and starts nothing. `sudo` resets `PATH`, hence `env PATH="$PATH"` for the
harnesses that need Node.

- **Claude Code and Codex** each get a `nunchi-mcp-discord` process of their
  own, with its own bot, port, routes, output key and state directory. The
  runner (`ClaudeCodeRoomRuntime`, `CodexRoomRunner`) stays in the probe's
  process, built with the same calls as its CLI's `main`
  (`load_pinned_config`, `transport_client`), and serves the room over real
  MCP (`DiscordRoomConnection.serve`, given a stop the probe sets at the
  end). The probe watches it as it watches the in-process room.
- **The reference**, `--harness reference`, is `nunchi-discord` on
  discord.py in its own process, with a scripted plain-call participant: an
  OpenAI-compatible endpoint that answers each turn in the participant-turn
  protocol (`standin.ScriptedParticipant`). `--discord-python` names a
  Python with discord.py. Its evidence comes from outside it: its receipts
  and delivery audits, what the scripted endpoints were asked and answered,
  and the wire.

Each Discord process starts as its console script does (`main` from the
same module), with the path, locale and certificate settings, a fresh
`HOME` and `TMPDIR`, and its own keys alone: no proxy variable, no key of
the harness's, no canary. Before it starts, `python -m
evals.rehearsal.preflight --nonce` runs in exactly that environment and
Python, and must reach this run's stand-in with the launcher's certificate;
otherwise the process is never started (exit 3). Attention is the scripted
endpoint. The moments play in one channel, named after the column:

| Moment | What happens | Checked |
|---|---|---|
| first-message | a person greets the room | reported; pinned `reached` on every column: a fresh transport declares its gap, and the message arrives behind it (below) |
| bot-status-report | a scripted bot posts a build report | no turn |
| direct-question | a person asks the agent | one post: the scripted answer |
| reply | the person replies to the agent's post | one reply, to that message |
| reaction | op 7 goes to every bot, then at once the person asks for a thumbs up, so the message crosses the reconnect | one 👍 on that message |
| thread | the person opens a thread under the room and posts in it | reported; pinned `reached` on every column: a thread under the room is part of it |
| thread-question | the person asks the agent a question in that thread | one reply to that message, and it must land in the thread, not in the channel (read from the wire) |

Beside the probe's hard checks, a run in the Discord room holds seven more:

- `discord-preflight`: each process's preflight passed and showed the
  launcher's certificate;
- `discord-processes`: each process got only its own keys, ran through the
  moments, and stopped on SIGINT or SIGTERM;
- `discord-standin-clean`: the stand-in's verdict has no unknown record;
- `discord-clients-complete`: each bot identified, got READY (and a member
  chunk where its client asks for one), and made its column's calls;
- `discord-writes-reconciled`: each committed action that reads `sent` is
  exactly one write the bot made, with the same content and target, and
  every write the bot made is a committed action;
- `discord-continuity`: the gap a fresh process declares reached the
  participant (Hermes's plugin declares it when its room starts, which is
  when the first message arrives, ahead of that message); after op 7 each bot
  resumed, did not identify again, and the message posted meanwhile reached
  Nunchi; on the shared transport and in Hermes no gap was marked. The
  reference marks a stream gap on any disconnect (`on_disconnect`): recorded,
  not failed;
- `discord-addressing`: a graded message reached the agent as it was sent.
  The scene's pings, the message a reply answers and the thread a message was
  said in are recorded when the stand-in sends it, and compared with the
  trigger in the turn the scripted agent or participant was handed
  (`mentioned_actor_ids`, `reply_to_event_id`, `thread_root_event_id`): the
  direct question, the thumbs-up request and the question in the thread must
  ping the agent and every ping must arrive, the reply's own ping included
  (Discord pings the author of the message a reply answers, and the stand-in
  records that ping as sent), the reply must be sent to the agent's own last
  post on the wire and arrive as a reply to it, and the question must arrive as
  a message in the thread it was sent in. A transport or reference that drops
  a mention, a reply reference or a thread fails here. Scripted attention
  wakes on a phrase and the scripted agent answers it, so no other check would
  notice. Two things the room log must give the agent are checked here too:
  the next turn after the agent's reaction must hold it in `memory.own_moves`
  (every column does, Hermes's too since the library records the reaction it
  sent), and the reply's target must be the agent's own post in the
  participant's log (`reply_resolves`). Every column holds the second but
  Hermes, whose gap is pinned the other way (below): a fix fails the lane
  until the pin and these docs are updated.

With `--scripted`, each graded moment is checked against the script, and
each pin holds: `TRANSPORT_PINS` for the shared transport, `REFERENCE_PINS`
for the reference. A pin fails when its moment reads otherwise, a fix or a
regression included ("update the pin and its docs"). The thread question is
graded, not pinned: the scripted agent replies to it, and the reply must have
landed in the thread (`checks.discord_moment_outcome`, read from the wire).
What the runs showed:

- **A reconnect loses nothing** (2026-10-09). The message posted right after
  op 7 went out on the old connection behind the op 7 frame, so no client
  read it there. The transport and discord.py both resumed, and the stand-in
  replayed it. The transport marked no gap.
- **Three gaps of the shared transport were found here and closed**
  (2026-10-10; pins flipped to `reached`;
  `integrations/mcp-discord/README.md`, "What reaches the participant").
  First, the first routed event after a start was replaced by the continuity
  gap the transport declares then, so a person's first message never reached
  the agent: now it arrives behind the gap. Second, a message in a thread
  under a routed channel was dropped: now it is part of the room, and the
  agent's reply goes into the thread (`binding.threads_in_room`, default
  `true`). Third, a notification sent before the runner's stream was open was
  lost while the journal said it was delivered: the runner now opens its
  stream before it registers, and the transport records a delivery only while
  the session's stream is open. The lanes no longer wait after registration:
  the first moment starts at once, and the run record
  (`discord.runner.order`) shows `connect`, `open_stream`, `register`.
- **The reference refused thread messages too** (`route-rejected`: a
  thread's id is not the bound channel); it now maps a thread to its parent
  channel and answers in the thread. Its first message was always `reached`.

It writes `world.json`, `discord-wire.jsonl` and `discord-standin.json` (the
stand-in's), `discord/<process>.log`, and a `discord` section in `run.json`:
the launcher's record, each process with its command, variable names,
preflight and exit, the stand-in's verdict, the start gap, each reconnect,
and the bot's writes. Each process also records what it ran on
(`installed`: Python, Nunchi, and mcp, or discord.py and aiohttp), read in
its own Python and environment. The scan covers them all, and looks for
each bot's per-run token too. Its tests are
`tests/v2/test_rehearsal_discord_room.py` (no root).

**In CI**, one lane per column runs as a step of its own: the launcher with
`--offline` around `--room discord --scripted`, with a fresh `HOME` and
`TMPDIR`, and the step's `PATH` passed on to the probe, since `sudo` resets
it. (Hermes's lane, the fourth, is described in the next section.)

| Job | Column | Python | The Discord process runs on |
|---|---|---|---|
| `claude-code-mod` | Claude Code 2.1.289, with the README's sandbox on | 3.12 | Nunchi's wheel and the `mcp-discord` extra as `mcp==1.28.1` (`MCP_VERSION`) |
| `codex-app-server` | Codex 0.160.1 | 3.12 | the same |
| `discord-standin` | the reference | 3.12 | Nunchi's wheel, `discord.py==2.7.1` and `aiohttp==3.14.3`, in a clean virtualenv |
| `hermes-plugin` | Hermes `a50406d9`, `hermes gateway run` | 3.14 | Nunchi's wheel and Hermes with `[messaging]`, in the job's virtualenv; no `mcp` |

The two transport lanes come after their job's in-process probe, and the
`mcp` install comes just before the lane, so the in-process steps run as
before. The same step runs `tests.v2.test_mcp_discord_gaps` first, since
its tests on the real MCP SDK (the connect race, a stream that dies, the SDK's
drop of a notification) need the extra and skip without it. Each step prints `pip freeze`. The Claude Code and Codex lanes pass
`--require-bwrap`, since both harnesses' sandboxes use bubblewrap (Codex's
uses the one on `PATH` and falls back to a copy it bundles), so those jobs
install it and lift Ubuntu's AppArmor limit on user namespaces; the
reference has no sandbox, so its job installs nothing and passes no flag;
Hermes's job does the same (the next section).
When a lane fails, the job scans the lane's output for the canary it made
(and for `NUNCHI_ATTENTION_API_KEY`, which these jobs do not have) with the
scan the rehearsal workflow uses, and only if the scan passes uploads it as
`rehearsal-discord-<column>-<run id>-<attempt>`. These steps have not run in
CI yet. Here (2026-10-09), each job's steps ran from `ci.yml`'s own text on
Python 3.12, with these local changes: no bubblewrap here, so the launcher
ran without `--require-bwrap` and Claude Code with `--no-sandbox`; no
`apt-get` or `sysctl`;
the pinned harnesses already on disk instead of `npm install`; and `pip`
reaching PyPI through this machine's settings, which the `sudo` line
unsets. All three lanes passed with every hard check, as root and dropping
to an unprivileged user.

Expected on `ubuntu-latest`, not checked: passwordless `sudo -E`, no proxy
variables, bubblewrap running in the launcher's namespace after the drop to
the runner user, Claude Code's sandbox inside that namespace, and
setup-python's Python trusting `/etc/ssl/certs`. The launcher refuses a
proxy variable, `--require-bwrap` fails before any harness starts where
bubblewrap cannot run, and the preflight fails on an untrusted certificate, so none of these can pass
quietly.

## The Hermes column (PR 3c)

**Status: implemented, unverified in CI; the plugin is parked (2026-10-10), and this lane stays in the `hermes-plugin` CI job.** Run here offline, inside the launcher, against Hermes `a50406d9` on Python 3.14: every hard check held in the last run (2026-10-10, once, after the plugin was parked: the thread question pinned to the main channel, the start gap and the reaction record required), from a virtualenv built as the `hermes-plugin` job builds it (the wheel, Hermes editable with `[messaging]`), as root.
The plugin is parked because it injects a turn of its own instead of riding Hermes's native flow (`integrations/hermes-plugin/README.md`, Parked): the lane records what it does, and no new Hermes work is planned until it is unparked.
`--harness hermes --room discord` runs Hermes's own gateway process,
`hermes gateway run`, unmodified, with the Nunchi plugin loaded the way Hermes
loads any plugin, on the stand-in at Discord's real names
(`HermesGatewayLeg` in `evals/rehearsal/discord_room.py`):

```sh
sudo -E "$PY" -m evals.rehearsal.discord_net --offline -- /usr/bin/env PATH="$PATH" \
  "$PY" -m evals.rehearsal.probe --harness hermes --scripted --room discord --out rehearsal-out
```

`$PY` is a Python with Nunchi and Hermes's `[messaging]` extra, as in the
`hermes-plugin` job; `--discord-python` names another for Hermes. A bare
`hermes gateway` only prints its help: `run` is the foreground gateway. The
in-process room (`--room standin`) still runs the kit's `GatewayRunner` in the
probe's process, as before. The moments, the launcher, the preflight and the
seven `discord-*` checks are the Discord room's (above). A run takes about 40 s.
Each pin and each piece of evidence is shown to fail the lane when it changes,
in a copy of the tree with one change made (the end of this section).

**What runs**

- **Hermes** starts in a session of its own, as the console script beside the
  Python does, with the path and locale, a fresh `HOME` and `TMPDIR`, a fresh
  `HERMES_HOME` under the run's directory, no proxy variable, and three keys:
  its bot's per-run token (`DISCORD_BOT_TOKEN`, in the environment only, so no
  file the run records holds it), the run's placeholder `OPENROUTER_API_KEY`
  (the variable the plugin's attention route names, and one Hermes strips from
  its agent's terminal) and the canary. The preflight runs first, in that
  environment. The probe waits for READY on the wire and for Hermes's own
  `gateway_state.json` to say the gateway is running with Discord connected, and
  stops it with SIGINT at the end. Hermes writes that state before its inbound
  gate opens: the first message is queued and handled about a second later, which
  the 8 s reach budget covers (the wait does not).
- **Its profile** is the plugin README's ("Hermes setup the room needs", "On
  Discord"), written from the kit's own room settings so that one test keeps
  README and kit equal. `config.yaml` has the display keys under
  `display.platforms.discord`, `thread_sessions_per_user`, the
  `discord:` block (`typing_indicator: false`, `reactions: false`,
  `free_response_channels: [<the column's channel>]`,
  `free_response_auto_thread: false`) with the probe's peer-agent settings
  (`allow_bots: all`, `bots_require_inline_mention: false`), the disabled
  toolsets, the plugin's entry (`allow_gateway_injection`, and
  `allow_platform_actions` for reactions) and `tools.tool_search.enabled: off`;
  `.env` has `DISCORD_ALLOWED_ROLES=<the room's role id>`, an empty
  `DISCORD_ALLOWED_USERS`, `GATEWAY_ALLOWED_USERS=nunchi-turns` and
  `HERMES_DISCORD_TEXT_BATCH_DELAY_SECONDS=0`. Each name was found in Hermes
  `a50406d9`'s code (`plugins/platforms/discord/adapter.py`: the role gate at
  `_allowed_role_ids`, `_get_allow_bots`, `_discord_bots_require_inline_mention`,
  `_discord_free_response_channels`, the batch delay; `gateway/authz_mixin.py`:
  `GATEWAY_ALLOWED_USERS`). The scripted people hold the room's role, and the
  scripted bot (`CI`) is heard through `allow_bots: all`. Changing either
  shows it: with a role id nobody has, no person's message reached Nunchi (every
  moment that starts with one read `not delivered`; the bot's report was still
  heard); without the peer-agent settings, the bot's status report did not
  reach Nunchi. The probe also stamps `_config_version`, as `hermes setup` does:
  without it Hermes takes the file for a two-year-old config at boot and logs
  that it skipped the migration.
- **The plugin** is the shipped directory, copied to
  `$HERMES_HOME/plugins/nunchi-room` (where `hermes plugins install` leaves
  it, which needs GitHub) and enabled in that `config.yaml`; its Nunchi config
  is the harness guide's with `binding.platform: discord`, the channel's id and
  a `hermes` section (`turn_user_id: nunchi-turns`, `withheld_env` the token
  and the key). It builds its room on the first message it admits.
- **The model** is the scripted endpoint through `model.provider: custom` and
  `base_url`, for the agent and every auxiliary task (what the in-process
  room writes too), and it follows the same script as the other columns
  (`RoomScript`): a final answer for a question, a reply or a thread question,
  one `room_react` call and then the silence marker (`[SILENT]`) for the
  thumbs-up request. **Attention** is `ScriptedAttention`.

**How Hermes differs from the other columns**

- **Hermes posts the agent's final answer itself**, as a plain message: it
  makes no Discord reply. The `reply` moment therefore fits one plain message
  from the turn that was about the graded message, not a reply to it
  (`checks.discord_moment_outcome`, `posts_itself`). The committed action reads
  `unknown` ("the harness delivers it") by design, and counts as delivered when
  the wire shows exactly that text from the bot, once. That it is a plain
  message is pinned from the wire: an answer whose request carries a
  `message_reference` (`replied_to`) fails with "Hermes now replies: update the
  plain-message pin and the docs", beside `discord-writes-reconciled`.
- **A thread question is answered in the main channel.** Hermes posts where
  its run started, and the plugin starts every run in the channel
  (`integrations/hermes-plugin/README.md`, Known gaps). The `thread-question`
  moment pins that: it fits only when the answer lands in the main channel,
  read from the wire, so a fix makes the lane fail with a note to update the pin
  and its docs (the note is shown only when that moment misses). Not fixed, and
  no change to Hermes.
- **The plugin declares a gap when its room starts.** The transport and the
  reference put a continuity gap ahead of their first message, and so does the
  plugin now: its room is built on the first message it admits, and the gap
  (`hermes:startup-gap:<ns>`) is declared before that message reaches it. The
  first snapshot reports continuity `unknown` with a restart gap, so after a
  Hermes restart the participant knows it may have missed messages although
  Hermes gives the plugin no history to read. `discord-continuity` requires it
  and records what the plugin said (`discord.start_gap`). The lane never
  restarts Hermes, so what a real restart does is not exercised.
- **A person's reply to the agent's answer has a target the library does not
  hold.** Hermes reports no id for its post and drops the bot's own messages
  before any hook, so the library files the answer as
  `nunchi:delivered:<request id>`. The reply arrives with the real Discord id
  as `reply_to_event_id`, ping and all, but that id is in no event of the
  participant's log: the library cannot link the reply to the agent's own
  message. No public Hermes extension point gives a plugin that id (README,
  Known gaps, No delivered message id, with what was checked and what would
  fix it). `discord-addressing` pins `reply_resolves` false for Hermes and
  true for every other column, where the same reply resolves to the agent's
  post.
- **The agent's own reaction is remembered.** Hermes gives plugins no reaction
  events and `platform_actions.add_reaction` returns only `ok`, so the
  plugin tells the library its room never shows the agent's own reactions
  (`HarnessDelivery(room_shows_own_reactions=False)`), and the host records each
  reaction the transport reports sent in the room log
  (`nunchi:reaction:<request id>`, the participant's own reaction on the message
  the turn was about). The next turn's `memory.own_moves` holds it, as it does
  for the transport and the reference. `discord-addressing` requires it; the
  lane reads the committed reaction's emoji and target from that record, and
  `discord-writes-reconciled` compares them with the wire.
- **Op 7**: Hermes (discord.py) resumed with no new IDENTIFY, the message posted
  meanwhile reached Nunchi, and no gap was marked anywhere. The plugin marks
  none after a reconnect either, so a gap marked after one fails the lane
  (`gaps_fail`), where the reference's own stream gap is recorded, not failed.

**Evidence from outside the process**

The plugin and the library run inside Hermes's process, so the probe sees none
of their objects. It reads:

| From | What it gives |
|---|---|
| the participant's receipts (`hermes-plugin-receipts.jsonl`) | each request: the message it was about (`observation`), attention's judgment, the host's end of the turn (`invoked`, the wake's source, `silent` or an action handed over) and the transport's delivery |
| the library's record of the message Hermes delivered (`nunchi:delivered:<request id>` in the observation log, which also holds the events the reply and memory checks look for) | the text the turn committed, and the message it was about. When the transport receipt says Hermes delivered and the library holds no such record, that is a hard problem (`turns-bound-and-ended`), and the scripted model's words are never put in its place |
| the scripted model | what it was asked, and how often (`moves`, counted as the turn's calls; nothing committed is taken from it), and what Hermes showed the agent (`discord-addressing`) |
| Hermes's `state.db` and logs, copied after it stops (`hermes-state.json`) | its sessions: each injected turn with the wake marker, the `room_react` call and its result, `[SILENT]`. Recorded for reading: no check reads it, and "the harness reached its model" rests on the scripted endpoint's own request log |
| the library's record of the reaction Hermes added (`nunchi:reaction:<request id>` in the observation log) | the emoji and the message the turn reacted to, which no receipt names. When the transport receipt says Hermes added the reaction and the library holds no such record, that is a hard problem (`turns-bound-and-ended`), as for a delivered message |
| the stand-in's wire (`discord-wire.jsonl`) | every call Hermes made and every message and reaction that landed, and where; `discord-writes-reconciled` compares the committed reaction (the library's record) with the reaction on the wire, so a different emoji or message there fails |

**What the Hermes column can prove, and what it cannot**

It can prove that Hermes, as installed, with the plugin and the README's
settings, hears each moment (a bot's report it should stay out of, a direct
question, a reply, a reaction request, a reconnect, a thread remark and a
thread question: each reached the library and attention judged it); that a
wake became a turn that ended in a delivery, a reaction or a silence through the
plugin's hooks; that what landed in the room is exactly what the library
committed, once, and nothing else (no extra post or notice, and no typing: the
stand-in serves no typing route, so Hermes's indicator on a fresh run would fail
`discord-standin-clean`); that the pings, reply reference and thread of a
person's message reached the agent as sent; and where an answer lands. With a scripted answer, the text is known, so
the content checks hold.

It cannot show whether a turn was bound to its wake. The probe sees no hook; a
turn counts as bound when the receipts show it ended in a delivery or a silence,
which only a bound run can reach (`bound_evidence` says so in `turns.json`).
It cannot read the library's decisions inside the process, only what the
participant shows the scripted model of its memory; and with a live model it
could read a committed message and a committed reaction only from the library's
record of them. It does not show how well the
agent reads the room (the model and attention are scripted), anything about a
live Discord (the stand-in is our model of it, `fidelity` in
`discord-standin.json`), a restart of Hermes (the lane never stops and starts
it), or the slash-command sync to its end: the lane stops before it finishes.
Invoking a registered command is never exercised either: the stand-in sends no
`INTERACTION_CREATE`, so none of the 70 commands is run.

**What Hermes calls on the stand-in**

Besides the login (`GET /users/@me`, `GET /oauth2/applications/@me`), the
gateway, the member chunk, the agent's post and its reaction, which every
column makes, Hermes calls these routes; each was added to the stand-in on
that evidence, with a test (`tests/v2/test_fake_discord.py`, `HermesRoutesTest`,
and one through discord.py in `test_fake_discord_discordpy.py`), and
`HERMES_CALLS` must all be made:

| Route | Who calls it, and when |
|---|---|
| `GET /applications/@me` | Hermes's own Discord tool reads the application's `flags` for the privileged intents (`tools/discord_tool.py`), once, at start |
| `GET /applications/{id}/commands`, `POST /applications/{id}/commands` | the slash-command sync (`DISCORD_COMMAND_SYNC_POLICY` `safe`, Hermes's default): a `GET`, then one `POST` per command, 4.5 s apart, in the background from about two seconds after READY. A fresh `HERMES_HOME` syncs all 70; the lane stops Hermes after the first six or seven, and nothing checks the number. Measured once, with the run held open for about 5.5 minutes (a copy of the lane with a sleep; the lane has no option for it): all 70 got a 201 from the stand-in, 310 s from first to last, with no unknown record. The stand-in does not model Discord's rules for options and choices, so that is its acceptance, not Discord's; the 70 bodies were also checked by hand against Discord's published limits (names, descriptions, at most 25 options and 25 choices, required options first) and met them |
| `GET /channels/{id}/messages?limit&before` | the history Hermes backfills for a reply (`limit=50`, and `limit=10` around the message replied to) and for every message in a thread |
| `GET /channels/{id}/messages/{id}` | `platform_actions.add_reaction` fetches the message before it reacts |

The stand-in keeps the commands in memory for the run (create or overwrite by
name: 201 or 200; at most 100: error 30032), answers history newest first with
`before` and `limit` (an empty list without READ_MESSAGE_HISTORY), and returns the
reactions a message holds when it is read over REST. `fidelity` lists what is
approximated: Discord's rules and error codes for a command's name and
description, its default `contexts` and `integration_types`, that option and
choice rules are not modelled (options are stored as sent), the `after` and
`around` of history, and that `PUT` (bulk sync), `PATCH` and `DELETE` of commands
are not served (Hermes's `bulk` policy, or a second sync with changed commands,
would be unknown and fail the run). The application's `flags` now say which
privileged intents are enabled for the bot (READY and both application
routes), as an unverified bot in fewer than 100 servers has them: the "limited"
bits (`1<<15`, `1<<19`), not the full ones (`1<<14`, `1<<18`) of a verified bot;
a world option `verified` sets the full ones. A command's
`default_member_permissions` comes back as a string, as Discord sends it. A
route Hermes calls that the stand-in does not serve is answered 599
and recorded as unknown, which fails the run: Hermes swallows many REST errors,
so the stand-in's own record decides. Typing is one: on a fresh run (others
posted while the agent composed, or its answer was refused once; README, Known
gaps) Hermes sends `POST /channels/{id}/typing`, which the stand-in does not
serve. No scripted moment starts a fresh run, so the lane never makes the call;
a scene that does fails `discord-standin-clean` naming that path, and
`hermes.typing` in the summary counts the request from the wire. Serving the
route (204, needing VIEW_CHANNEL and SEND_MESSAGES) would let a typing bubble
pass silently, so it comes with a pin that allows it in a fresh-run turn only.

**What the lane showed**

- A Hermes answer carries `allowed_mentions: {parse: [users], replied_user:
  true}` and no `message_reference`, in the channel, with a `nonce`.
- Hermes registers 70 slash commands in the bot's name, one every 4.5 s from
  its start. In a real room they appear in everyone's slash menu; the README
  keeps Hermes's default (Known gaps, Registered slash commands, decision D4).
- The agent's own message comes back to the library as a message of its own,
  in reply to the one the turn was about, and its reaction as a reaction of its
  own on the message it was about; later turns' packets list both
  (`delivered_event_ids`, `memory.own_moves`), so its memory and the room's
  pace see them. A person's reply to the message does not resolve to it,
  though (above).
- `hermes.typing` is 0 in every run: no scripted moment starts a fresh run.

**What turns the lane red** (each shown offline on 2026-10-10, before the
plugin was parked, inside the launcher, in a copy of the tree with one change
made; the copy was thrown away, so nothing was left changed): the plugin
dropping the mentions of a reply (`discord-addressing`: the reply pings the
agent, and Nunchi saw none); the plugin not declaring its gap when its room
starts (`discord-continuity`); the plugin telling the library that the room
shows the agent's reactions, or the library not recording the reaction it sent
(`turns-bound-and-ended`: the transport receipt says Hermes added it and the
library holds no record, then `no-leaks`, `discord-writes-reconciled`,
`discord-addressing` and `scripted-outcomes`); the library unable to record its
own delivered post (`turns-bound-and-ended`, `discord-writes-reconciled` and
others: the scripted model's words are not put in its place); a simulated fix
of the reply's target (`discord-addressing`, the pin); the stand-in making
Hermes's answers Discord replies (`scripted-outcomes`: "Hermes now replies", and
`discord-writes-reconciled`); and one answer that the plugin must refuse, which
starts a fresh run and so Hermes's typing (`discord-standin-clean` names the
path, and `hermes.typing` reads 1).
- Hermes's agent is offered 26 tools, `terminal`, `execute_code` and `browser_exec`
  among them, with the `local` backend: unsandboxed, as the first live run
  recorded (`sandbox: off`). Hermes's own builders, run in exactly its
  environment, give the agent's terminal neither the bot's token nor the key,
  only the canary, a name Hermes does not know (`pins-and-isolation`).
- Run as root, as the local lane is, Hermes logs a security warning about it; a
  CI runner is not root.

**In CI** it is the last step of `hermes-plugin` (Python 3.14, Hermes `a50406d9`
from a clean virtualenv with Nunchi's wheel): the launcher with `--offline`
around the scripted probe with `--harness hermes --room discord`, then, as in
the other three jobs, a canary made before it, a scan of the lane's record for
the canary after a failure, and an upload as `rehearsal-discord-hermes-<run
id>-<attempt>` only after a clean scan. The job's `tests.v2.test_rehearsal`
step now also runs `tests.v2.test_rehearsal_discord_hermes`. No
`--require-bwrap`, and no bubblewrap: Hermes's sandboxes (Docker, Singularity,
Modal, Daytona, SSH, Vercel) use none, and its default is unsandboxed. Not run
in CI yet, and expected rather than checked on `ubuntu-latest`: passwordless
`sudo -E`, no proxy variables, setup-python's Python trusting `/etc/ssl/certs`,
and Hermes starting as the runner user inside the launcher's namespace in about
the time it took here.

## Directed scenes (PR 4a, 4b, 4c)

**Status: implemented, unverified in CI. Run here offline, inside the
launcher, on Python 3.12 with discord.py 2.7.1 (2026-10-11): each of the four
scenes PR 4a plays exited 0 with every hard check holding and a matrix reading
`fits`/`ok`; the reference, Codex and Claude Code lanes ran once more with the
same results. The new tests (`tests/v2/test_rehearsal_directed.py`) pass.** A
first review found that the grader could pass a column that did the wrong thing
in the room; the repairs are described under "How it is graded" and "What
changes in the checks", and five mutations of the reference and the director
(a turn on a suppressed message that speaks, a reaction on the wrong message,
a reply to chatter, a dropped message, a dropped ping) each now fail the scene.
The scenes are drafts (`evals/behavior/README.md`), so every result says
"draft expectations".

**PR 4b: implemented, unverified in CI. Run here offline, inside the launcher
(2026-10-11), on Python 3.12 with the pins CI installs (discord.py 2.7.1,
aiohttp 3.14.3, mcp 1.28.1), against the pinned Claude Code 2.1.289 (with
`--no-sandbox`, since bubblewrap cannot run here) and Codex 0.160.1: each of
the four scenes exited 0 through Claude Code, through Codex and through the
reference, in two passes (24 runs), every hard check holding and every graded
moment `fits`/`ok`. No
harness column missed a scene the reference passes, so 4b has no finding about
an integration to report yet. Three mutations each fail a harness column's
lane and name the cause: a script that plays a listed miss (the status report
answered), an agent that answers the chatter where the script is silent, and a
leg that forgets what an action was about. The plain Discord lanes of the
three columns are unchanged in substance.**

**PR 4c: implemented, unverified in CI. Run here offline, inside the launcher
(2026-10-11), on Python 3.12 with the pins CI installs, against the pinned
Claude Code 2.1.289 (with `--no-sandbox`) and Codex 0.160.1: each of the seven
scenes it adds (`asked-while-busy`, `answered-while-composing`,
`never-mind-while-composing`, `build-finishes-after-promise`,
`build-finishes-long-after-promise`, `did-you-see`, `addressee-never-answers`)
exited 0 through the reference, through Claude Code and through Codex, in four
passes (84 runs; the last on the code as committed, with the other four scenes
and the plain lanes), every hard check
holding, every graded moment `fits`/`ok` and every hold `held` (none raced). No
harness column missed a scene the reference passes, so 4c has no finding about
an integration to report. The 4a and 4b scenes and the plain Discord lanes of
the three columns ran twice and are unchanged in substance (compared with the
base commit's plain lanes). Mutations each fail the intended check on all three
columns and name the cause: an agent that answers after it has been shown the
page, a line of the agent's that is not said, a release before the held message
reached Nunchi, a release that never comes, and a hold that lands only the
earlier message of an unattended moment; and, with the core's look before
posting switched off in a scratch copy, every column posts the answer it had
ready and the hold reads `unseen`, the column's miss.**

The behavior suite judges one moment at a time, with the room handed to
attention as a snapshot. A rehearsal with one person cannot show what a room
of several does to an agent: a bot's status report, a question for someone
else, a story told across messages. `--scene ID` plays one scene as a
conversation instead: a **director** (`evals/rehearsal/directed.py`) posts
the scene's people and bots to the Discord stand-in through its control API,
as messages (pings, replies and all), and a column takes part in it: the
reference, `nunchi-discord` in its own process (PR 4a), or Claude Code or
Codex through their own `nunchi-mcp-discord` (PR 4b). What the room saw of the
agent is graded
with the suite's own `score.grade` from each moment's `fitting`, `misses` and
`step1`, and read like a cell of the suite's matrix. The reference is the
control: a harness column's miss that the reference does not share is the
integration's.

```sh
sudo -E "$PY" -m evals.rehearsal.discord_net --offline -- /usr/bin/env PATH="$PATH" \
  "$PY" -m evals.rehearsal.probe --harness reference --scripted --room discord --scene story-across-messages \
  --discord-python /path/to/python-with-discord.py --out rehearsal-out
```

One scene per run, so that each starts from a fresh room and a fresh agent;
scripted, offline, with no model and no key. The reference plays it as shown;
Claude Code and Codex take `--harness claude-code` or `--harness codex` in its
place (below). **The
director never posts as the agent**: every visible move is the agent's own,
and the stand-in refuses a post as a harness's bot. A scene that holds an
earlier line of the agent's, a promise it made or a nod it gave, is played by
having the agent say the line itself, as its scripted move on the message it
answers (PR 4c, below). `directed.plan` sorts each scene and gives the reasons
it cannot be played; `tests/v2/test_rehearsal_directed.py` pins this table, so a
new scene fails until it is classified here:

| Scene | Played | What it needs, or what stops it (`directed.REASONS`) |
|---|---|---|
| `bot-status-report` | yes | nothing |
| `story-across-messages` | yes | nothing |
| `said-it-would-check` | yes | nothing; the agent's reply to the first request is its own live move |
| `mention-in-busy-room` | yes | nothing; 21 messages of history, 11 live |
| `asked-while-busy` | yes (4c) | a line (`v1`, the agent's reply to `z1`) and a hold: Sam's question and Zoe's thanks land while the agent is still answering Zoe; time compressed (50 seconds) |
| `answered-while-composing` | yes (4c) | a cue for `v1` (what the agent said three hours before) and a hold: Castor's answer lands while the agent composes its own; time compressed (3 hours) |
| `never-mind-while-composing` | yes (4c) | a cue for `v1` and a hold: Zoe's "never mind" lands while the agent composes; time compressed (3 hours) |
| `build-finishes-after-promise` | yes (4c) | a line (`v1`, the promise); time compressed (50 minutes) |
| `build-finishes-long-after-promise` | yes (4c) | four lines (the promise and three answers, `v1`, `r1` to `r3`); time compressed (3 hours); 25 messages, each with a turn |
| `did-you-see` | yes (4c) | a line (`r1`, the nod, a reaction); time compressed (12 minutes) |
| `addressee-never-answers` | yes (4c) | a cue for `v1` (what the agent wrote two hours before); time compressed (2 hours) |
| `addressee-first` | no | `pause`: the look-again timer counts 300 real seconds |
| `only-they-can-do-it` | no | `pause` |
| `quiet-for-hours` | no | `time`: the room's seven quiet hours are the point, and they would be seconds (below) |
| `approval-comes-through` | no | `outcome`, `pause`: the Discord lanes have no approval path |
| `answered-by-someone-else` | no | `seen-through`: a snapshot the live pipeline cannot be asked for (`answered-while-composing` covers the live case) |
| `two-agents-one-question` | no | `several-participants`: two harness bots in one room (PR 5) |

The pause (`addressee-first`, `only-they-can-do-it`) is a real wait of 300
seconds, which neither PR 4c nor PR 4d plays; it gets its own small PR.
`addressee-never-answers` was refused until PR 4c, because without `v1` the
second moment's "Vigil knows the answer" would be untrue and its grade
meaningless. One person could type `story-across-messages`,
`never-mind-while-composing` and `did-you-see`; the rest need other voices,
which the director gives as stand-in people and scripted bots.

**How a scene is played.** Events older than ten minutes
(`HISTORY_SECONDS`) before the first graded message are history: posted
backdated (`post(at=)`), oldest first, so the room's clock only moves
forward, and the room goes quiet once. The clock is then moved to the wall
(`advance`) and the rest is posted live, in order, each after the room went
quiet again (the first graded message is always among them). Their gaps are
`pace` times the scene's own: 0 here, no wait. Two limits are real: the
stand-in stamps the agent's own post at the wall, so a gap after the agent
has posted cannot be kept (a scene with a line of the agent's therefore has
its time compressed, below); and `advance` does not move the agent's look-again
timer, which counts 300 real seconds, so a scene that needs a pause is a real
wait and is not played here. A message that mentions someone pings them in
place of their name, and a `reply_to` becomes a Discord reply to the message
the stand-in made for it.

**The agent's own earlier lines, cues and compressed time (PR 4c).** A scene's
event of the agent's, the promise Vigil made or the nod it gave, is not posted:
the director never posts as the agent. The agent says it itself, as its
scripted move on the message the scene has it answer or react to (`standin.Line`:
`v1` of `build-finishes-after-promise` is a reply to `z1`, `r1` of
`did-you-see` a 👂 on `z1`). Attention wakes the agent for that message (leans to
a mhm for a nod) and the agent says exactly the scene's words or reaction. It
is not graded; it is a precondition, checked to have happened exactly
(`directed.judge_scene`, `directed-outcomes`): the turn on that message must
have delivered one action, of the scene's kind, with its words or reaction,
about that message, and for a harness column a completed room tool call must
back it. A line that did not land fails the run, since the moments after it
would be judged against a history the agent never had. And the turn after
it must hold it in `memory.own_moves` (`discord-addressing`): the next turn,
and each graded turn, however many messages came between. That is what a
promise outliving the window of recent messages
(`build-finishes-long-after-promise`) and a nod that is asked about
(`did-you-see`) need to show.

Two things in how that is played are named in every result, because they
differ from the scene as written:

- **Played with a cue.** A line that answers nothing in the scene (`v1` of
  `answered-while-composing`, `never-mind-while-composing` and
  `addressee-never-answers`) has no message to be the agent's move on, so the
  director adds one: a person's message, posted just before the line, whose
  scripted answer is the line. It is the first human who posts in the scene
  (Zoe) saying "Vigil, anything to report?", and the agent's reply is the
  scene's words as a plain post. The cue is not in the scene, it is in the
  plan (`Plan.cues`) and the result (`cues`, and the summary), and a live model
  will see it in the room's history, which is why it is named.
- **Time compressed.** The stand-in stamps the agent's post at the wall, so
  nothing posted after it can be backdated before it, and a scene with a line
  of the agent's is played live from the message that triggers its first line
  (`Plan.compressed` says how much of the scene's own time that is: 50 seconds
  for `asked-while-busy`, 50 minutes, 3 hours, 12 minutes, 2 hours and 3 hours
  for the others). The room's timestamps show seconds where the scene has
  hours. A scene whose point is a long quiet, with more than four hours before
  its graded message (`QUIET_SECONDS`), cannot be played that way:
  `quiet-for-hours` is refused as `time`. No change was made to the stand-in's
  clock rule.

**Holds (PR 4c).** Three scenes put a message into a turn that is under way,
which a one-person test cannot show: Castor answers while Vigil is composing
its own answer, Zoe says "never mind" while Vigil composes, Sam asks a question
while Vigil is answering Zoe and Zoe thanks Vigil before it is done. The
director cannot hold the agent's process, so the hold is a gate on the scripted
model endpoint (`standin.Gate`), the same for all three columns: the endpoint
holds the first model call of the turn on the trigger. The director waits until
the endpoint has that call, posts the scene's `during_turn` messages, waits for
each to reach Nunchi (its audit), and releases the call. The agent's first
attempt is the answer it has ready (`SCENE_DRAFT`, a post that names its moment,
which would show as an action where the script is quiet); the core's look before
posting holds it back and shows the agent the new message (a plain-call
participant gets a page, `Not posted yet: ...`, in its next request; Claude Code
and Codex get it in the result of the room tool they called, `Turn.call`); and
the script then does what the scene fits, here a silence. A `during_turn` moment
is graded on what the agent finally does after the core shows it the page, as
every moment is. Each hold is judged (`directed.hold_outcome`) and the result
says which:

- `held`: the model was asked about the turn, every held message had reached
  Nunchi before the release, and the page the core showed the turn holds them.
- `raced`: the turn went on before a held message reached Nunchi (the release
  came first, or the model's wait of `HOLD_SECONDS` (25 s, under the reference's
  30 s model timeout) ran out). It is not a miss, since the moment was not played
  as scripted; it is reported as `raced`, the moment's own grade is left aside,
  and a scripted run fails.
- `unseen`: the messages reached Nunchi in time and the core did not show them
  to the turn before it posted. That is the column's miss, and the first attempt
  is then in the room, graded as the speak it is.
- `unmerged` (an `unattended` hold): the moment's unattended messages were
  judged on their own and not read with it, or were also read on their own.
- `never-asked`: the model was never asked about the turn.

`asked-while-busy` is the other kind, the `unattended` moment: Sam's question
arrives while Vigil answers Zoe, and Zoe's thanks comes next, "and Nunchi reads
both". Nunchi keeps one pending message and replaces it with a newer one, so
the question is read with the thanks only if the thanks also arrives while the
agent is busy. The hold therefore holds the turn on Zoe's question (the one that
plays Vigil's reply) and lands both Sam's question and Zoe's thanks in it
(`Hold.events`).

**This plays `asked-while-busy` in another order than the scene's, and says so
in every result** (`record._reordered`, "played in another order than the
scene's"). The scene is written z1, s1, `v1` (Vigil's reply to Zoe), z2 (the
thanks). Played, it is z1, s1, z2, and then Vigil's reply `v1`, which is said
after the thanks has landed, since both land in the turn that plays it. The
unattended premise needs that order; the written one cannot be played, because
the thanks would then follow the turn and Sam's question would be judged on its
own. What it means for the moment's facts: "Vigil answered Zoe but not Sam"
holds only after z2 (in the scene it held before it), and the moment is judged
at z2 with Vigil's reply already in the room, as in the scene. What it means
for a live model: it would compose its reply to Zoe with her thanks already in
the room, and may drop the reply after the look page shows it the thanks, so
`v1` cannot be assumed in a live run and the scripted run shows only that the
core hands it the page. The scripted agent says the reply (a line, a reply to
Zoe's first message) both at the first attempt and after the page, because the
script is the scene's.

Landing only Sam's message, and the thanks after the turn, was run here too:
Sam's message then gets a turn of its own before the thanks, the thanks lists
nothing as unattended, and the run fails as `unmerged`. A turn of its own for
Sam's message beside the thanks' turn reading it as unattended (it was read
twice) fails as `unmerged` too.

**The script.** `standin.SceneScript` is what attention and the agent both
follow, so a scene needs no phrase list. At a graded moment it does the first
of the moment's `fitting` moves, as the room would see it (waiting shows
nothing, so it is silence): attention suppresses a moment whose step 1 is
`suppress`, wakes for `speak`, leans to a mhm for `mhm` and defers otherwise;
the agent then posts one scripted line that names its moment (a write is
matched to an action by its content, so no two lines may be alike), reacts
with 👂 on the message, or says nothing. Every other message is the scene's
chatter: attention passes it (`DEFER`, as "when unsure, pay attention" asks)
and the agent stays silent, so each scene shows a turn that ends in silence.
The director tells the script each graded message's text just before it posts
it, since the script only sees the room's text (a ping reads `<@id>` there); in
PR 4c it also tells it the text of each message that triggers a line of the
agent's (a cue included), at which attention wakes the agent and the agent says
the line, and a held turn pauses at the endpoint (above).

**How it is graded** (`directed.judge_scene`), for each graded moment, in the
keys the suite's results use:

1. the turns the message started, or that listed it as `unattended` (a turn
   that took it with a later message as one moment). Where the script acts, a
   turn must have **begun** on the message: one that only listed it as
   unattended read it with another, and one action cannot stand for two
   moments, so that moment fails `off_script`, saying it was only folded into
   another turn;
2. their delivered committed actions, already reconciled with the bot's own
   2xx writes (`discord-writes-reconciled`);
3. the move the room saw: `score.agent_move` (a message or reply is `speak`, a
   reaction `mhm`, nothing `stay_quiet`) whenever a turn began on the message,
   **whatever attention said of it**: a turn that ran on a message attention
   suppressed is the agent's, and a reply there is graded as the reply it is.
   Only when no turn ran is it attention's quiet (`by`: `attention` or
   `agent`);
4. step 1 from attention's receipt for that message, as the suite reads it
   (`score.visible_result`): `ok`, `over-suppress` or `over-wake`; `not
   judged` where a turn ran on a message attention left no judgment for;
5. `off_script`, how the delivered actions differ from the one the script
   makes, worked out from the scene's first `fitting` move and not from what
   the script did (`directed.scripted_action`): none where the script is quiet;
   otherwise exactly one, with its kind and words (or reaction), about the
   graded message (a reaction's `target_event_id`; a message's
   `origin_event_id`, which the director keeps in the committed record), as
   `checks.discord_moment_outcome` reads the plain lanes' moments;

and `visible` is `fits`, `miss` or `unlisted`, from the scene alone. A message
that never reached Nunchi, or that attention never judged and no turn began
on, reads `unsupported`; one that woke the agent whose turn did not deliver
reads `woken`, which fits nothing. The record also lists `other_actions`, every
committed action outside the graded turns (the script is silent on the
chatter), and the moment reads `misses` for any of them; the turns that play the
agent's own earlier lines (PR 4c) are the scene's setup and not among them. It
also lists each line with whether it landed (`lines`, with `problems`) and each
hold with how it went (`holds`, with `outcome` and `detail`); a graded moment a
hold is for carries its outcome (`hold`), and a run whose hold raced reads
`raced` in place of `misses`. `cited` says for each of the moment's facts
whether attention's evidence points at one of its messages (scripted
attention cites the trigger only). `summary.md` shows a **grade matrix**
(`## Grade matrix (draft expectations)`): one row per graded moment, and the
column's cell as the suite's matrix shows it (`S`, `m`, `q`, `Q`, with `!` for
a clear miss), then the visible grade and step 1, such as `` `S` fits/ok``, and
`hold raced` (or `unseen`, `unmerged`, `never-asked`) where a hold did not hold.
`summary.md` also has a section, **How the scenes were played**, that names a
scene played with a cue and the quoted cue, a scene whose time was compressed
and by how much, each earlier line of the agent's and whether it landed as the
scene has it, and each hold and how it went.

**What changes in the checks.** The seven `discord-*` checks and the probe's
own all run. `directed-outcomes` (`checks.directed_outcomes`) replaces
`scripted-outcomes`: every graded moment must have reached Nunchi, read `fits`
with step 1 `ok`, be the move the script makes and be exactly the action it
makes (`off_script`); a script that plays a listed miss fails it, naming the
scene, the moment and the scene's reason. It also fails when the agent did
anything outside the graded turns (`other_actions`), when **any** message the
director posted never reached Nunchi (not only the graded ones: a lost
message changes the room the graded one is read in), and when a wait for the
room to go quiet timed out (below). Since PR 4c it fails too when one of the
agent's earlier lines did not land exactly as the scene has it (the kind, the
words or the reaction, about the message that triggers it, one action); when a
hold did not hold (`raced`, `unseen`, `unmerged` or `never-asked`, above); and,
for a hold that raced, it names the race and not a miss.
A scene plays no reconnect, so `discord-continuity` checks the start gap alone
there (`reconnects_required`); `discord-clients-complete` expects the calls the
script makes (its login, a post where it speaks or says a line, a reaction where
it nods);
`discord-addressing` checks, for every message the director posted, that the
pings the **scene meant** (`meant_actor_ids`, worked out from the scene and
not from the text sent) were sent, and that they and the reply target arrived
as the stand-in sent them in Nunchi's own room log and, where a turn was
handed the message, in the turn; that every turn that ran was shown its
trigger (a request the agent's model was asked holds that turn: a quiet answer
to a message the model never saw proves nothing); and that the next turn after
the agent's reaction holds it in `memory.own_moves`, about the message it
reacted to; since PR 4c the same for each of its earlier lines (a reaction, a
reply to the message it answered, a post by its words), at the next turn and at
every graded turn after it. A live scene is graded the same way, from what the
live agent did, reported and never failed (Live scenes, below).

**A wait that timed out.** Every message is posted and then waited on until the
room goes quiet (`Leg.settle`), and the wait is recorded in the delivery
(`settled`). One that ran out leaves the room moving, so a late turn or post
would be missing from the record and a grade made now would pass over it. A
scripted run fails on it, in the scene and in the plain moments alike
(`directed-outcomes` and `scripted-outcomes`, naming the messages:
`checks.unsettled`); a live run flags it, with `unsettled` on the
moment and a line in `summary.md`, and reports the rest. A run whose waits all
ended quiet records as before.

**Through Claude Code and Codex (PR 4b, 4c).** The scenes also run through
`DiscordClaudeCodeLeg` and `DiscordCodexLeg`, so that each harness's real
process (`claude -p` with the mod, `codex app-server` with the integration)
reads the room the director makes, through its own `nunchi-mcp-discord`, with
the harness's runner in the probe's process as in the moments' lane. A leg
takes the directed spec as the reference does (`OnTheTransport.play` and
`judge`); the world holds the scene's people and bots and the director posts
them. What changes for a harness:

- **The scripted model follows the scene.** The scripted Messages endpoint
  (Claude Code) and the scripted Responses endpoint (Codex) follow the same
  `SceneScript` as attention: `SceneScript.move` says its move as a room tool
  call, `send` (`SCENE_SAY`, naming the moment) or `react` (`SCENE_NOD` on the
  trigger), or `silence`. A silent turn makes no room tool call and ends on a
  short message that goes nowhere: Claude Code and Codex post only through the
  room's tools, so that is how they stay quiet. The scene's chatter gets
  silence, as for the reference, and attention is the same `ScriptedAttention`.
  A line of the agent's is a `send` (with the `reply_to_event_id` of the message
  it answers, for a reply) or a `react`, and a held turn is held at the same
  gate: on the first model call of the turn, before the tool call, so that the
  call the core answers with the page is the endpoint's own `send` of the draft.
  The page comes back as that tool's result, and the next model call makes no
  room tool call (`news_shown` reads it from the newest message or input item of
  the request). A quiet scene (`bot-status-report`) calls no room tool and no check asks for
  one. What its summary's verdict line says depends on the column: Codex's
  reads "no room tool was called: the turn ended without one", Claude Code's
  does not count calls and reads as always ("the mod attached and bound the
  turn, and the model answered as ..."); neither fails anything.
- **What the leg records.** The judge reads the same record as for the
  reference. The harness runs in the probe's process, so the leg records it as
  it goes (`Leg.instrument`): each turn with the messages it took while the
  agent was busy (`unattended`), each committed action with the message it was
  about (`origin_event_id`, in a scene only, so the plain lanes' records are as
  they were), and attention's decision for each message, read from the
  participant's own receipts, the receipts the reference's state directory
  holds (`discord_room.attention_entries`), with the evidence it cited.
- **The checks.** The hard checks of 4a hold for each column: `directed-outcomes`,
  the seven `discord-*` checks, `one-room-action-per-turn`, `no-leaks`, and
  nothing outside the graded turns. Three differ for a harness.
  `discord-clients-complete` expects the transport's own lookups (the channel,
  the member, the roles) and a post or a reaction where the script makes one.
  `directed-outcomes` holds each action that reached the room to the harness's
  own record of its room tool calls, per action and not per run
  (`checks.room_call_for`): a post needs a completed `room_send` with the same
  words and a nod a completed `room_react` on the same message with the same
  reaction, one call for one action, so a move that reached the room some
  other way, or through a call that did not complete, fails and is named. The
  calls are read from Claude Code's stream-json (a `tool_use` of a room tool and
  the `tool_result` that came back) and from Codex's completed `mcpToolCall`
  items, and kept in `run.json` (`discord.room_tool_calls`). And a scene run
  fails the hard check `room-errors` if the room's own lane (`lane_errors`) or
  the runner's serve loop (`serve_errors`) met an error: both are recorded for
  every run, and were empty in every run that passed here, the plain lanes
  included; only a scene fails on them. The start gap the transport declares is
  read after the scene; no reconnect is played.
- **Turn counts differ by column, and nothing depends on them.** A message that
  arrives while a turn runs is read with the next one as a single moment
  (`unattended`, #94 step 6), and a harness's turn is slower than the
  reference's, so the chatter of `mention-in-busy-room` took 32 turns on the
  reference, 24 and 25 on Codex and 20 and 23 on Claude Code in two passes
  (2026-10-11), and each graded message, posted after the room went quiet,
  started a turn of its own in all three. The other three scenes took the same
  turns in every column, and so did the seven of PR 4c in all three passes: for
  example `build-finishes-long-after-promise` took 25 turns (4 playing the
  promise and its three answers, 1 graded, 20 on the chatter), and the three
  scenes with a hold took 2 or 3, the held turn among them.

The reference is the control. A scene that a harness column fails and the
reference passes is that integration's miss, and is the finding this part is
for: the script, the grader and the checks are not bent to pass it. It is
pinned as a named failure or an expected-failure test that states what the room
would show, and reported. None has appeared yet. What the tests hold instead
(`tests/v2/test_rehearsal_directed_harness.py`): the scripted endpoints follow a
scene's script for every graded moment of the eleven scenes; a script that plays
a listed miss through a harness column fails `directed-outcomes` and names the
moment and the scene's reason; so does an action the script is silent on, an
action no room tool call backs, a graded message the script acts on that only a
later turn listed as unattended, a turn that ran on a message the model was
never shown, and a room whose lane met an error. PR 4c adds
`tests/v2/test_rehearsal_directed_holds.py`: the plan of each of the seven
scenes (its lines, cues, holds and compressed time), the gate, the script's
draft and its decision after the page, the three endpoints' reading of that
page, the director's order of posting, how a hold and a line are judged, and
the agent's own history in the next turn's memory, each with the mutation that
must fail it: the agent answering after it has been shown the page, a line
missing or in other words, a release before the held message reached Nunchi, a
model wait that ran out, an unattended message read on its own.

**In CI** it is a step of the `discord-standin` job, after the reference's
lane, and of the `claude-code-mod` and `codex-app-server` jobs, after their
Discord lane: a loop over the eleven scene ids (the four of PR 4a and 4b, then
the seven of PR 4c), each inside the launcher with
`--offline` (and `--require-bwrap` in the two harness jobs, with Claude Code's
sandbox on as in its lane: CI never passes `--no-sandbox`), in the lane's
virtualenv and with a fresh `HOME` and `TMPDIR`; the step fails after the last
if any scene failed. The launcher steps of the three jobs have a timeout of their
own (`timeout-minutes`: 15 for the room lane, 20 for the eleven scenes; run here
a lane took 15 to 20 seconds and the eleven scenes 2 to 3 minutes), so a hung
scene fails the job and is not left to the runner's six hours. A failure runs the same scan for the key and the canary
over every scene's record and uploads it as
`rehearsal-discord-scenes-<run id>-<attempt>` (reference),
`rehearsal-discord-claude-code-scenes-<run id>-<attempt>` or
`rehearsal-discord-codex-scenes-<run id>-<attempt>` only after a clean scan.
Run here, a scene took 5 to 60 seconds (the longest,
`build-finishes-long-after-promise`, 25 messages each with a turn). None has run
in CI.

**What it does not prove.** The agent and attention are scripted, so this
shows that the director posts a scene as a room would see it, that the
reference and each harness hear it as sent and act on the script (through
their own tools, for Claude Code and Codex), and that the grader reads
the result both ways (`tests/v2/test_rehearsal_directed.py` grades a synthetic
move for every fitting move, every miss and every unlisted move of every
scene). The scenes of PR 4c are played with three stand-ins that a live
run would not have: a cue the model will see in history, a room whose hours were
seconds, and a turn held at the model endpoint (a live model is not held, and
its composing takes the time it takes, so which message lands while it composes
is a matter of timing there). One scene is also played in another order than
it is written: in `asked-while-busy` the agent's reply comes after Zoe's thanks,
not before it. A live model would compose that reply with the thanks already
in the room and may drop it after the look page, so the reply cannot be
assumed live, and "Vigil answered Zoe but not Sam" holds only after the
thanks. What a hold shows is that the core's look before
posting and the page it hands the agent work through each harness's own tools,
and that the grade reads the room after it. It says nothing about how well any
model reads the room: that needs a live run (Live scenes, below), and Zoe's
review of the scenes first (`evals/behavior/README.md`). Six scenes are still
not played (the table above). Hermes is parked (`AGENTS.md`): its lane keeps
its moments and plays no scene.

## Live scenes (PR 4d)

**Status: implemented, unverified. No live run has been made.** What has run:
the unit tests (`tests/v2/test_rehearsal_live_scene.py`), with a fake provider on
loopback in place of OpenRouter and a thread for the live agent; and the eleven
scripted scenes and the three plain Discord lanes on all three columns, which
are unchanged (below). After this merges, one pass of the four scenes of PR 4a on
all three columns is the first live run; this section's claims about it
(what it reads, what it costs, how long it takes) are then to be checked.

The manual `rehearsal` workflow takes `room: discord` and plays the behavior
suite's directed scenes with a live model behind each column, on the Discord
stand-in at Discord's real names, so that we see how a live agent reads a room
of several people through each harness. The reference (`nunchi-discord`, on the
same model through OpenRouter's chat completions) is the control, as in the
scripted lanes: a miss only a harness column has is the integration's, a miss
all three share is the model's or Nunchi's. Hermes plays no scene (parked).

```
Actions → rehearsal → Run workflow
  room        discord            (in-process, the default, is the two-moment probe as before)
  harness     all | claude-code | codex   (the reference always runs; hermes is refused)
  scenes      bot-status-report story-across-messages said-it-would-check mention-in-busy-room   (the default: the four of PR 4a)
  passes      1 | 2 | 3          (each scene once per column and pass; 23% of woken moments change move between runs)
  agent_model, attention_model, budget_usd  as before
```

One job, `scenes`, installs the pinned Claude Code and Codex, the reference's
virtualenv (discord.py) and the transports' (mcp), and plays each (pass, scene,
column) as a probe run of its own, inside the launcher **without `--offline`**
(the models are on the internet; the launcher allows that on a GitHub Actions
runner alone), with `--require-bwrap` for Claude Code and Codex and their
sandboxes on. A run that fails does not stop the others; each has a timeout of
40 minutes (or what is left of the step's 290 minutes of planning, wind-up
included; none starts with less than ten minutes left), and the step has another.
GNU `timeout`, run without `--foreground`, sends TERM to its whole process group,
not only to the launcher: the launcher, the probe and the harness's processes.
The launcher passes its TERM on to the probe, which turns the first into an
interrupt and winds the run up (stops the Discord processes, reads the key's
usage one last time for up to 75 s, writes the record) and ignores a second, so
the duplicate is harmless. The Discord processes run in sessions of their own
(`setsid`), so the group's TERM does not reach them: the probe's wind-up stops
them. `--kill-after` is how long that has before SIGKILL: 300 s, so a run that
timed out still leaves a partial record when it can.

Between runs the step reads the recorded spend of **the whole dispatch** (all
passes together) and stops starting runs once it has passed `budget_usd` (a soft
limit: the figure lags). A spend it cannot read stops them too, rather than
counting as nothing. Every run not started is written to `status.tsv` as
`skipped`, `halted.tsv` says why (budget, time, or an unreadable spend), and the
summary's first line says the dispatch halted. The inputs are checked before
anything is installed: `scenes` as a whole string (ids joined by single spaces,
each a scene the director can play, de-duplicated, never more than there are),
`budget_usd` as a plain positive number (`nan`, `inf` and exponents are refused),
`passes` as 1, 2 or 3, and Hermes is refused.

After the last run, a step TERMs and then KILLs whatever the play step left
running (a timeout or a cancel can leave root's launcher, the Discord processes
and the harnesses writing into the outputs the scan reads) and fails if
anything remains; the key and canary scan covers every output only after that,
and only after a clean scan does the job summary show the matrix (below) and
the records upload as `rehearsal-scenes-<run id>`.

**The live run's egress is open.** The launcher runs online because the models
are on the internet, so the harnesses, their tools and the reference can reach
any host (the in-process live probe before it was no different). What bounds it:
Codex's workspace-write sandbox has `network_access = false`; Claude Code's Bash
tool runs in its sandbox (bubblewrap, which the launcher checks first); the
Discord names lead to the stand-in at 127.0.0.1 and `::1`, whose certificate
covers those names only; Claude Code is asked to keep off telemetry and
nonessential traffic (`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`,
`DISABLE_TELEMETRY`); and there is no real Discord credential on the runner. A
network-sealed live run (a private network namespace with a relay to
openrouter.ai) is planned, not built. Not done either: hash-pinned constraints
for the installs (pip's and npm's pins are by version, and generating the hashes
needs the network); the GitHub environment that would gate the secret, and a
credit-limited key, which are Zoe's to set up.

**It refuses to run in the wrong place.** `probe.live_scene_refusal`, in `main`
and in `run_probe`, stops a live scene before anything is written or started:
off a CI runner (`CI` is not exactly `true`) it exits 2 (the launcher also wants
`GITHUB_ACTIONS=true`, above); without a key its column
reads, under that key's own name, it exits 3. The keys are
`NUNCHI_ATTENTION_API_KEY` for attention and, by column, `NUNCHI_PARTICIPANT_API_KEY`
(the reference's participant model), `ANTHROPIC_AUTH_TOKEN` (Claude Code) or
`OPENROUTER_API_KEY` (Codex); the in-process live probe falls back to the attention
key for a harness's own, a scene does not. The workflow gives all four the one
secret in the step's environment, never on a command line, and `env -u` drops from
each column the two it does not read. The Discord room also checks the launcher's
own record: a live scene started in an `--offline` launcher, or one that never saw
a runner (`CI=true` and `GITHUB_ACTIONS=true`), stops before any process starts.

### What is reported, and what fails

| | Reported in the job summary, never failed | Fails the run |
|---|---|---|
| The agent | each graded moment's grade (`fits`, `miss`, `unlisted`; step 1 `ok`, `over-wake`, `over-suppress`), what the agent did, whether attention's evidence cites each fact; what it did on the chatter (`other_actions`) | |
| Setup | `precondition not met`; a hold's outcome (`held`, `raced`, `unseen`, `never-asked`, `unmerged`); a wait that ran out; a message that did not reach Nunchi | |
| Plumbing and safety | | the checks of any run: `pins-and-isolation`, `record-complete`, `turns-bound-and-ended`, `turns-on-others-messages`, `attention-judged`, `one-room-action-per-turn`, `no-leaks`, `live-scene-plumbing` (a message the director posted never reached Nunchi; for Claude Code and Codex, an action delivered to the room without a completed room tool call of the harness's own record behind it), `room-errors` (Claude Code and Codex), the `discord-*` checks (preflight, processes, stand-in clean, clients complete, writes reconciled with the wire, continuity, addressing: what the stand-in sent arrived as sent); the probe raising an error; the key or canary in an output (the scan deletes every output) |
| Spend | the cost, recorded and estimated | `spend-recorded`: no reading of the key's usage gave a figure (the first is tried up to three times, and the detail names the error of each that failed), the model calls were not counted, or none was counted for an agent whose turns ran |

The scenes' expectations are drafts nobody has reviewed (`evals/behavior/README.md`),
so a live result is not called a miss until Zoe has reviewed the scene: every page
says "draft expectations", and the matrix is titled "draft expectations, not
reviewed". There is no `directed-outcomes` or `scripted-outcomes` check live; the
script that held an agent to its scene has nothing to hold.

### The agent's words are its own

The director never posts as the agent (as before), and now it cannot force
the agent's words either, so a scene is played as the live agent makes it:

- **An earlier line of the agent's** (a promise, a nod; PR 4c) is the live agent's
  own move on the message it answers, or on the cue the director adds. It is
  checked only to be of the scene's kind (`directed.line_landing`): a reply
  or a post answers, a reaction nods, and it must have been delivered.
  If the agent made no such move (no turn began, it stayed silent, it nodded
  where the scene has a reply), every graded moment of the scene reads
  `precondition not met` with what the agent did, is not graded, and **the scene
  stops** there (nothing after it is posted: it would be judged against a history
  the agent did not have, and each message costs a turn). The summary shows
  the scene's words and the agent's side by side.
- **A hold is timing, not a gate.** There is no proxy in front of OpenRouter. The
  director posts the held messages as soon as the column's turn has begun
  (`Leg.begun`: Claude Code's and Codex's turn is recorded when the host hands it
  to the harness; the reference's is attention's receipt reading as a wake, the
  earliest signal it has, which can come a moment before the turn's packet is
  built), waits for each to reach Nunchi, and lets the room settle. The hold
  reads `held` if every held message reached Nunchi before the
  agent's move reached the room (or before its turn ended, if it moved not at all),
  `raced` if the agent moved first (not a miss: the moment was not played as the
  scene has it, and it is reported as `raced`), a held message never reached
  Nunchi, or a held message was already in the first packet handed to the agent
  for the turn (the reference's host receipt lists the packet's events, and the
  wake Claude Code and Codex are handed does too: a message that reached Nunchi
  before the turn began did not arrive in it), `unseen` if they reached Nunchi in
  time, the agent moved, and the column's own record shows the turn was never
  shown them (shown means in the transcript from the turn's start to the moment it
  moved, or ended: the same transcript holds the next turn's wake, which is another
  turn's), `never-asked` if no
  turn began on the trigger within 60 s (the scene goes on, the moment reads
  `precondition not met`), and `unmerged` for an `unattended` hold as before. The
  times are compared to the millisecond; a tie is `held`.
- **The scenes that need the agent to know something it does not** are not
  meaningful live: `answered-while-composing`, `never-mind-while-composing` and
  `addressee-never-answers` have the agent say, three hours earlier, a fact the
  scene's later moments turn on. A live agent given the cue says whatever it
  says, and the page shows both. They are not in the default list.
  `asked-while-busy` is played in the order PR 4c names, and a live agent may
  drop its reply after the page shows it Zoe's thanks, which reads
  `precondition not met`.

### What each column shows

| | Claude Code, Codex | Reference |
|---|---|---|
| Its model | the harness's own process, through OpenRouter | `nunchi-discord`'s participant model, the agent model through OpenRouter's chat completions |
| Turns, actions, attention | recorded in the probe's process as in the scripted lanes | read from outside its process (`discord_room.LiveTurns`): its receipts, stamped when first read (about every 0.1 s), and the stand-in's wire; a delivered action's kind, words and target are the wire's, paired in order with the transport's receipts |
| Whether a held message was shown to the turn | yes: its id in the harness's own transcript from the turn's start to the moment it moved or ended (`shown_to_turn`) | **no**: the page goes to a model the probe does not see, so a hold is `held` or `raced`, `unseen` cannot be reported, and a `held` is marked **unproven** (timing alone) in the matrix cell (`hold held (unproven: timing alone)`) and in the summary (`held, unproven`) |
| Which messages a turn read as unattended | yes (the wake's `unattended_event_ids`) | **no**: a message that began a turn of its own is taken as judged on its own (`unmerged`) |
| What a turn was handed | the wake the host built, in process | the host's receipt that the trigger was in its packet, and the room log's record of the message; its memory is not shown |
| Model calls counted | Claude Code: the distinct assistant messages in its stream-json; Codex: the `token_count` events in its session files; attention: the calls made | **a lower bound**: the turns that ran (a page the look before posting showed, or a refused answer, asks the model again and the process does not show it), and the attention receipts that name a model |

Both limits of the reference are the cost of not putting a recording hop in front
of the model, which would also have shown its calls and the pages it was shown; it
is the repair if the reference's holds need to be told apart from a race.
A live reference is settled when no request is open (a message observed whose
attention is not back, a woken turn without its host receipt, a hand-off without
its transport receipt) and nothing moved for 4 s, since a live model leaves
nothing outside its process while it thinks. A message that arrived while the
agent was busy is judged for the memory alone before the newest one
(`NunchiV2Pipeline._recall_midturn`): it gets an observation and an attention
receipt, a wake among them, and no turn, so no host receipt ever. It is told
from a turn about to begin by what follows: once a later request has its
attention back (the lane runs one opportunity at a time, so a real turn's host
receipt comes first), or when it is older than the participant's timeout and its
grace, no turn is coming, it is not open, and it did not begin.

Before it starts, the live reference makes one call to its participant model
with the body its participant will send (`response_format` `json_object`, through
the same code), and the run could not run, with the provider's answer, if what
comes back is not a JSON object: whether the agent model's providers honor that
is the first thing a live run learns, and it must not be learnt by every turn
failing. It is one model call and is counted.

### The job summary

A matrix per pass, the columns side by side (`evals/rehearsal/matrix.py`), titled
"Directed scenes, live: grade matrix (draft expectations, not reviewed)": a row
for each graded moment, a cell for each column in the form of the scripted
matrix (the suite's letter for the move, the visible grade and step 1, or
`precondition not met`), a table of the facts each moment turns on and whether
attention's evidence cites them, how each scene was played (what the live agent did
instead of the scene's earlier lines, each hold and how it went, a scene that
stopped), each run's exit status with the hard checks that failed and, for a run
that failed, the tail of its stderr (the cause when the launcher refused or a
setup failed before the probe wrote a record), and the cost. A dispatch that
halted says so first, with why, and its runs not started read `skipped`. A moment
whose attention call failed reads step 1 `not judged` with the error named (the
error fallback woke the agent; that is not attention's reading), and a moment
that is not graded for a reason other than a setup the agent did not make reads
`not judged`, not `precondition not met`.
Each run's own `summary.md` is in the uploaded records. The grades are the draft's
reading of a live conversation, and a live agent varies from run to run: read
three passes before reading a column.

### Cost

Per pass of the default four scenes, on the three columns: **about $1.40
(roughly $1 to $3), an estimate, not measured.** A pass is 12 runs, about 43
messages per column (2 + 5 + 4 + 32), so at most 43 attention calls, and I
assume 8 to 12 agent turns per column (a guess from the scenes' size; a
harness turn is 2 or 3 model requests). Costs per call, assumed (`spend.ESTIMATED_USD_PER_CALL`):

| Call | Assumed | How |
|---|---|---|
| attention | $0.002 | the behavior eval reported $1.92 for eight attention routes over all scenes, three runs each (about $0.001 a call); doubled for the default model's reasoning tokens and a scene's longer room |
| the reference's agent turn | $0.01 | a snapshot of the room (about 5,000 tokens in, 200 out) at $1 and $5 per million tokens, the default agent model's list price, about $0.006; rounded up |
| a Claude Code or Codex model request | $0.02 | the harness's system prompt and tools beside the room (about 18,000 tokens in, 300 out), same prices, no cache credit |

So a pass is about 43 × $0.002 × 3 = $0.26 of attention, 10 × $0.01 = $0.10 for the
reference and 10 × 2.5 × $0.02 = $0.50 for each harness, about $1.4. The
summary shows it two ways per pass and column: **recorded** (the key's usage over
each run, read before the first message and for about 75 s after the last, which
lags the calls and counts other runs on the key, so only the sum over a pass is
worth reading) and **estimated** (the counted calls times the assumed costs). The
first live run replaces the assumed costs; until then neither figure has been
seen. The 75 s wait after each run is 15 minutes of waiting per pass; a pass is
expected to take about an hour, three passes about three (unmeasured), within the
job's 350 minutes (the play step plans inside 290 of its 300). `budget_usd`
(default 2) stops starting runs once the dispatch, all its passes together, has
recorded that much (the runs not started are listed as skipped); raise it for a
full pass if the estimate holds.

### Run here, offline

The eleven scripted scenes and the three plain Discord lanes on all three columns,
offline inside the launcher (2026-10-11, the pins CI installs, Claude Code
with `--no-sandbox` since bubblewrap cannot run here): see the status line in the
CHANGELOG. The live path itself has not met a provider, OpenRouter's usage endpoint
or a CI runner: `sudo -E` carrying the keys through the launcher, `timeout` signalling
the launcher, the runner check and the online launcher on `ubuntu-latest`, the
reference's `participant_model` on OpenRouter's chat completions with the
agent model (whether that route honors the participant protocol's JSON response
format), and the hold timing of a live model are all unverified.

## What a pass means

A run passes only when the harness reached its model and took part in the
room through Nunchi, with attention judging. Anything else fails the run,
and `summary.md` opens with every reason (`evals/rehearsal/checks.py`):

- no wake reached the harness, so nothing showed it reaching its model;
- a turn ended as a named failure: the mod never attached, the harness could
  not take the turn, or the model call failed (Claude Code's error result,
  Codex's failed turn, Hermes's provider failure). Claude Code's error
  result and Codex's failed turn fail the run even when the turn had
  already posted: the post settles the turn's outcome for the library, so a
  later call that fails shows only in the harness's own result;
- the participant-host receipt, which wins over what the probe recorded,
  says a turn's outcome is `unknown` with nothing handed to the room: the
  turn was cancelled, outlived the host's deadline, or failed;
- attention never returned a judgment. Failed attention calls, and the wakes
  their error fallback caused, are counted and listed even when it did;
- a turn made more than one room action, or an action was not delivered: on
  Claude Code and Codex it must read `sent`, and the stand-in applies the
  shared transport's own checks (`ToolExecutor`), so a post over 2000
  characters is refused as on Discord; Hermes posts its final answer itself,
  so there the room must have received exactly that answer;
- something reached the room that the library did not commit, a declared
  Hermes gap included, or a committed post names Nunchi's machinery;
- a turn started on a message no one else posted, such as the agent's own
  post coming back from the room;
- with `--scripted`, a moment did not go as scripted, or, for Codex and
  Claude Code, the post did not go through a room tool; with `--scene`, a
  graded moment did not read `fits` with step 1 `ok` and exactly the action the
  script makes, the agent did something outside the graded turns, or a message
  the director posted never reached Nunchi (`directed-outcomes`, naming the
  moment); in either, a wait for the room to go quiet timed out; and, in a
  scene with the agent's own earlier lines or a held turn, a line did not land
  exactly as the scene has it, or a hold did not hold (`raced`, `unseen`,
  `unmerged`, `never-asked`);
- the pins, the isolation or the record did not hold: among them, a
  recorded process got a key other than its harness's own (Nunchi's keys
  stay in Nunchi's process), or, where Hermes's own builders show it, the
  agent's terminal gets any key; or the harness showed it ran otherwise
  than configured: Claude Code did not recognize the model, or started in
  another permission mode than the pinned version does for that model;
- the probe itself raised an error (`run.json`'s `errors`);
- the key or the canary is in an output, or an output could not be read;
- with a live `--scene`, only the above and `spend-recorded` (no reading of the
  key's usage gave a figure, or the model calls were not counted). Its grades,
  holds and setups are reported, never failed (Live scenes).

A pass with no post delivered says so in its first line: the harness reached
its model, but the room tools were not exercised in that run. A run that
could not start (exit 3) or stopped at the budget (exit 4) is not a pass
either. The probe does not retry a provider error; only the
harness's own retries apply (the live Codex config keeps Codex's defaults).
An error that outlasts them fails the run, with the harness's own words for
it as the reason.

## Run it

Dispatch **Actions → rehearsal → Run workflow** (the workflow must be on
`main` first). Inputs: `harness` (`all`, `claude-code`, `codex`, `hermes`),
`agent_model` (default `anthropic/claude-haiku-4.5`), `attention_model`
(default `openai/gpt-6-luna@low`), `budget_usd` (default 2, per probe run),
and `codex_openai_model` (default `openai/gpt-6-luna`; empty skips it), the
agent's model for the Codex job's labelled OpenAI-model arm (R3, below). Three
inputs choose what is played (PR 4d): `room` (`in-process`, the default: all of
the above as before; or `discord`: the directed scenes, live, Live scenes below),
`scenes` (behavior scene ids, separated by spaces; the four of PR 4a by default)
and `passes` (1, 2 or 3). With `room: discord` the `harness` input picks the
columns beside the reference (which always runs, as the control), `hermes` is
refused, the Codex arm is not run, and `budget_usd` stops starting scene runs
once the whole dispatch, all its passes together, has recorded that much. The
jobs run one at a time. In each job the scan of every output is a step of
its own after the probe, and it runs whether the probe step passed, failed,
timed out or was cancelled. Only after a clean scan does the job show the
run's `summary.md` and upload `rehearsal-out/` as an artifact. After a hit
every output but the leak notice (files and variables, never a value) and
`scan.json` is deleted, the job fails, and its summary shows the notice.

Locally, from a checkout, with the pinned harness installed:

```sh
# offline, no key
NUNCHI_CODEX_BIN=/path/to/codex python -m evals.rehearsal.probe --harness codex --scripted --out rehearsal-out
NUNCHI_CLAUDE_BIN=/path/to/claude python -m evals.rehearsal.probe --harness claude-code --scripted --out rehearsal-out
# live: costs money
NUNCHI_ATTENTION_API_KEY=... python -m evals.rehearsal.probe --harness hermes --out rehearsal-out --budget-usd 2
# the Discord room, offline, as root (The Discord room, above)
sudo -E "$PY" -m evals.rehearsal.discord_net --offline -- /usr/bin/env PATH="$PATH" \
  "$PY" -m evals.rehearsal.probe --harness reference --scripted --room discord --discord-python /path/to/python-with-discord.py --out rehearsal-out
# the same for Hermes: a Python with Nunchi and Hermes's [messaging] extra (The Hermes column)
sudo -E "$PY" -m evals.rehearsal.discord_net --offline -- /usr/bin/env PATH="$PATH" \
  "$PY" -m evals.rehearsal.probe --harness hermes --scripted --room discord --out rehearsal-out
# one behavior scene, directed and graded, on the reference (Directed scenes, below)
sudo -E "$PY" -m evals.rehearsal.discord_net --offline -- /usr/bin/env PATH="$PATH" \
  "$PY" -m evals.rehearsal.probe --harness reference --scripted --room discord --scene story-across-messages \
  --discord-python /path/to/python-with-discord.py --out rehearsal-out
# the same scene through Claude Code or Codex: --harness claude-code (add --no-sandbox where bubblewrap cannot run) or --harness codex
```

The live probe needs the key in `NUNCHI_ATTENTION_API_KEY`. It hands the
harness its own key variable's value when that is set, and otherwise the
same key, under the name the harness reads (below). Run it with a Python
that can import Nunchi (CI installs the wheel). Exit status: 0 every hard
check held; 1 a hard check failed, the probe raised an error, or the scan
found a secret; 2 bad arguments, a Claude Code `--agent-model` the probe has
no row for or `--no-sandbox` for another harness among them (below); 3 it
could not run (a harness or the key is missing, for example); 4 it stopped
at the budget with every hard check holding. With two
moments, a stop can only come before the direct question, and a run that
stops there usually has no wake, so it reads as a failure (exit 1); the
first lines of `summary.md` name the stop either way.
`--room discord` needs the launcher, and its moments are scripted only: it
exits 2 for a live run of the moments or the reference outside the Discord
room, and 3 (could not run) without the launcher, or, for Hermes, where Hermes
with discord.py cannot be read in the Python that runs it; `--harness
reference` runs in it alone. `--scene ID` is played in the Discord room by the
reference, Claude Code or Codex: Hermes (parked), an unknown scene or one the
director cannot play exits 2 (the last two list the scenes that can be played).
Scripted it is offline; without `--scripted` it is live (PR 4d): exit 2 off a CI
runner, 3 without a key its column reads, and 0 or 1 as for any run, whatever the
grades.
`--attention-model` takes the behavior eval's label (`id` or `id@effort`);
a label for another route (`messages:`, `responses:`) is refused, since the
probe builds the chat route only. `--arm LABEL` names a run that is one arm
of a comparison, in `run.json` and in the title of `summary.md`.

A live scene is dispatched, never run by hand: the probe refuses it off a CI
runner (exit 2) and without its column's keys (exit 3), and the launcher runs
without `--offline` only there (Live scenes):

```sh
# in the rehearsal workflow only (a GitHub Actions runner, the keys in the environment):
sudo -E timeout --signal=TERM --kill-after=300s 2400s env HOME="$LANE_HOME" TMPDIR="$LANE_TMP" "$PY" -m evals.rehearsal.discord_net [--require-bwrap] -- \
  /usr/bin/env PATH="$PATH" "$PY" -m evals.rehearsal.probe --harness {reference,claude-code,codex} --room discord --scene SCENE --out OUT
```

CI runs `--scripted`, and this probe's tests (`tests/v2/test_rehearsal.py`,
the scripted probe's own test included), in the Claude Code (`claude-code-mod`),
Codex and Hermes lanes of `ci.yml`, with no secret. It runs `--room discord
--scripted` inside the launcher for Claude Code, Codex, the reference and
Hermes (The Discord room and The Hermes column), and, in the jobs of the
reference, Claude Code and Codex, the eleven directed scenes (Directed scenes).

## Model routes and keys

One secret, `NUNCHI_OPENROUTER`, goes in under the name each process reads,
and only the probe steps and the scan step see it
(`evals/rehearsal/routes.py`):

| Who | Route | Key variable |
|---|---|---|
| Attention beside Claude Code and Codex | OpenRouter chat completions, `openai/gpt-6-luna` at `low` | `NUNCHI_ATTENTION_API_KEY`, in Nunchi's process only |
| Attention beside Hermes | the same | `OPENROUTER_API_KEY`, Hermes's own, in Hermes's process |
| Claude Code | `ANTHROPIC_BASE_URL=https://openrouter.ai/api`, `ANTHROPIC_API_KEY=""`, `--model <slug>`, the background-model variables on the same slug, and `modelOverrides` {Claude Code's id for the model: slug} in the user settings | `ANTHROPIC_AUTH_TOKEN` |
| Codex | a throwaway `$CODEX_HOME/config.toml`: `[model_providers.openrouter]` at `https://openrouter.ai/api/v1`, `wire_api = "responses"`, `env_key = "OPENROUTER_API_KEY"` | `OPENROUTER_API_KEY` |
| Hermes | `model.provider: openrouter` with the slug, every auxiliary task on the same slug | `OPENROUTER_API_KEY`, named in the plugin's `withheld_env` |
| The reference, in a live scene (PR 4d) | `nunchi-discord`'s `participant_model` at `https://openrouter.ai/api/v1` (chat completions) on the agent model; attention beside it as for Claude Code and Codex | `NUNCHI_PARTICIPANT_API_KEY` and `NUNCHI_ATTENTION_API_KEY`, in its process only |

Every harness runs as a clean user: fresh `HOME` (and XDG directories under
it), `CODEX_HOME`, `HERMES_HOME`, `CLAUDE_CONFIG_DIR` and `TMPDIR`, its
route's settings, and nothing else from the job's environment but the path,
the locale and network settings, its own key and the canary. Each agent
starts in a fresh `work` directory under the run; for Hermes, which runs in
the probe's process, that is its terminal's `cwd`, since it would otherwise
start in the Nunchi checkout and read its `AGENTS.md`. Where each of
Nunchi's keys lives:

- **Claude Code and Codex.** The probe's process holds Nunchi's own keys,
  `NUNCHI_ATTENTION_API_KEY` and the stand-in transport's
  `NUNCHI_REHEARSAL_OUTPUT_KEY`. Their integrations strip every `NUNCHI_*`
  variable from the harness's environment, then add back only what the room
  tools need: the gate's socket path and per-launch secret for the Claude
  Code session (`NUNCHI_CLAUDE_CODE_GATE_*`), and the same pair for the
  room's MCP server that Codex starts (`NUNCHI_CODEX_TURN_*`). Neither is a
  key: each opens only a socket that closes with the run.
- **Hermes.** Hermes runs the plugin in the probe's process, so whatever
  attention reads is in Hermes's process too. Attention therefore reads
  Hermes's own `OPENROUTER_API_KEY`, which Hermes strips from the
  environment of the agent's terminal and code tools. The probe removes
  every `NUNCHI_*` key from its environment before it loads Hermes, since
  Hermes would pass a `NUNCHI_*` name to the agent's shell. The run records what Hermes's own builders
  (`tools.environments.local._make_run_env` and `_sanitize_subprocess_env`)
  give the agent's commands, and fails if they would pass a key.

Each harness keeps its own model key where it needs it, and the agent's
shell can reach it: Claude Code's Bash gets `ANTHROPIC_AUTH_TOKEN` (inside
its sandbox), and Codex's agent shell is not checked. Only for Hermes do the
harness's own builders let the probe check what the agent's shell gets.

Behind a gateway Claude Code knows a model only by its Anthropic id. Given
the bare slug, Claude Code 2.1.289 logs `[claude-code:unrecognized_model]`,
starts `claude -p` in `auto` permission mode and sends what its newest
models take. So the probe maps each slug it runs Claude Code on to that id
(`routes.CLAUDE_CODE_MODELS`, for example `anthropic/claude-haiku-4.5` →
`claude-haiku-4-5`) and writes the override into the clean user's settings,
as Claude Code's model configuration docs say for a gateway alias. A slug
with no row is refused (exit 2). Each row also says which permission mode
the pinned Claude Code starts `claude -p` in on that model through a
gateway: `default` on Haiku 4.5 and Sonnet 4.5, which do not support auto
mode, and `auto` on the newer models. Only `anthropic/claude-haiku-4.5` has
been used against OpenRouter; the other slugs follow its naming. Checked
offline, the pinned 2.1.289 against a local Messages endpoint, on the slug
`anthropic/claude-haiku-4.5`:

| | First request | Permission mode |
|---|---|---|
| without the override | `thinking: {type: adaptive, display: updates}`, `output_config: {effort: high}`, a `safeguards` block, the `effort`, `afk-mode` and `dangerous-tool-use` betas; `unrecognized_model` logged | `auto` |
| with it | `thinking: {type: enabled, budget_tokens: 31999, display: updates}`, no `output_config`, no `safeguards`, none of those betas; no diagnostic | `default` |

Both send the slug upstream. Haiku 4.5 takes only `budget_tokens` thinking,
and effort errors on it, so without the override every turn would likely
fail. The run fails pins-and-isolation, with Claude Code's own line, if
Claude Code still logs `unrecognized_model` or starts in another permission
mode than its row says.

`run.json` lists the variable names each recorded process got. The run
checks that the real user's `~/.codex` and `~/.hermes` were not created or
changed. `REHEARSAL_CANARY` holds a random value in the harness's
environment that no `*_env` key names, so the room's guard does not know it;
only the scan can catch it. The room tools' per-run launch secrets (Codex's,
and Claude Code's gate session) are not scanned for and may stay in the
transcripts: they open only a socket that closes with the run.

The user settings follow each integration's README: Claude Code's Bash
sandbox, and Codex's `workspace-write` sandbox without network. Both run the
agent's commands in bubblewrap, so the workflow installs it (and socat, for
Claude Code) in both jobs, and in CI's scripted Claude Code lane, lifts
Ubuntu's AppArmor limit on unprivileged user namespaces, and checks that
`bwrap` runs. Hermes runs the agent's
commands with its default `local` terminal backend, unsandboxed. Each run
records whether the harness's sandbox was on, in its report and in the
first lines of `summary.md`: for Claude Code from its settings (with
`failIfUnavailable`, a session that starts has its sandbox); for Codex from
the sandbox policy it reports and its bubblewrap warnings; for Hermes from
its terminal backend. A sandbox that is off is recorded, not failed.
`--no-sandbox` turns Claude Code's off, for a machine where bubblewrap
cannot run (Claude Code offline, above).

## What a run records

Under `rehearsal-out/<harness>/` (`evals/rehearsal/record.py`):

- `run.json`: the commit, the Nunchi wheel's sha256, the harness version
  (and the mod or plugin version, and package lists), the binding, the
  requested models and the providers that served them wherever a
  transcript shows it, every config written with its sha256 and text (no
  config holds a key; each names the key's variable), every command the
  probe and the integrations ran for the harness (version checks, `npm ls`,
  the working directory's `git init`, and each harness process launched:
  Claude Code's sessions, Codex's app-servers and the room's MCP server
  Codex starts), each with the names of the variables it got and which of
  them hold a key or the canary (never values); the same for the processes
  no command starts (Hermes's own, and what its builders give the agent's
  commands); each harness's report, with its verdict and sandbox; the spend
  readings and the budget, each moment and each check;
- `checks.json` and `summary.md`, written even when the run fails;
- `scan.json`: the key and canary scan over everything here. After a hit,
  every other output is deleted and `summary.md` is the leak notice. The
  scan reads each file as written and as a normalized copy (JSON escapes
  undone, whitespace and backslashes removed), for each value as written,
  base64-encoded and hex-encoded, so line-wrapped base64, a hex dump in
  lines or bytes, a value split by spaces or newlines, and a value inside a
  JSON string are all found. A hex dump with addresses between its lines
  (`xxd`'s default) is not. A symlink or an unreadable file counts as a hit;
- the participant's receipts, the turns and committed actions with their
  delivery (`turns.json`), the attention calls (`attention.json`), what
  reached the room (`room.json`), and for Claude Code and Codex the
  stand-in's wire log (`wire.jsonl`);
- the harness's own transcript: Claude Code's stream-json; Codex's
  app-server JSON-RPC and its session files; Hermes's sessions, messages,
  system prompts and model usage from its `state.db` (`hermes-state.json`),
  with its session index and logs. A scripted run adds the requests the
  scripted model received, and for Claude Code where else it tried to reach
  (the report's `network`).

`summary.md` opens with the outcome and every reason for it (each failed
check, any error the probe raised, a stop at the budget), then attention's
count, each harness's verdict in full, and whether its sandbox was on.
The moments, the checks, the reports' plain values, the models, the spend
and the record's identity follow; everything else is in `run.json`.
For Codex the verdict says whether a room tool was actually called:
OpenRouter may not pass Codex's namespace tools through. Codex 0.160.1
offers them for this provider block (its `modelProvider/capabilities/read`
answers `namespaceTools: true` from the config alone), and the scripted lane
records that the room tools reach the model as a `namespace` tool
(`room_tools_offered_as_namespace`). The verdict names R3 only on evidence:
a turn error that names the namespace, or, scripted, the room tools missing
from the model's requests. Any other turn error is given in Codex's own
words. For Claude Code the verdict says whether the mod attached and bound
the turn and which model the response names, or Claude Code's own words for
the first error (a result's `errors`), and then anything that shows it ran
otherwise than configured; its report also lists the tools the model called
(`tool_calls`, `room_tool_called`), every error result (`failures`), and
which credential files Claude Code reads from a fixed path whatever `HOME`
says were readable (`fixed_credentials`). For Hermes it says whether the plugin
loaded and how many model calls its session records.

## Cost

A live scene dispatch has its own estimate, per pass, in Live scenes above (about
$1.40 for the default four scenes on the three columns, unmeasured). The rest of
this section is the in-process probe.

Estimated under $1 for a dispatch of all three harnesses: per harness, two
moments, about one agent turn (a few cents on Haiku 4.5) and three attention
calls; the Codex job's OpenAI-model arm is one more such run. Not measured
yet: in the first live run the key's usage figure had not moved by any
reading (below). The scripted lanes cost nothing.

Claude Code and Hermes give client-side cost estimates (`total_cost_usd`,
and `estimated_cost_usd` in Hermes's `state.db`; both are recorded), and
Codex's session files give token counts only. None of them is what the key
was charged, so the spend watchdog reads the key's usage
(`GET https://openrouter.ai/api/v1/key`) before the first moment and between
moments, and stops before the next moment once the probe run has spent
`budget_usd` (the Codex job has two runs, each with its own).

OpenRouter's usage figure lags behind the calls: in the first live run every
reading, between moments and right after the last, read $0 spent, in every
job. So the last reading, after the last moment (or after a run that
failed partway), reads the figure at once
and then every 5 s, up to 75 s after the last moment: no read starts past
the bound, and each read's timeout is cut to the time left. Since the
reading is a record, not a limit, it never stops early, so a live probe run
takes about 75 s longer. It keeps each read and takes the last figure read
as the settled one: `spend.spent_usd`, and the last entry of
`spend.readings`, whose `series` lists each read as [seconds after the last
moment, usage] (null for a failed read). Charges posted after the bound are
missed, and the series shows the lag: when the figure moved, and whether it
was still moving at the bound. The Spend section of `summary.md` says the
same. Whether 75 s covers OpenRouter's lag has not been measured: no live
run has used this wait yet. A scripted run reads nothing and waits for
nothing.

The spend reading is **a record, and a soft limit between moments, never a
limit inside one**, and `run.json` and `summary.md` say so: a moment under
way runs to its end, the figure it stops on can lag, and other runs on the
same key count in the same figure. Job and step timeouts are a second limit.
Only a key with a credit limit is a hard one.

## Zoe's open choices, and the defaults the probe takes

- **R1, the key.** Default: the existing `NUNCHI_OPENROUTER` with the soft
  watchdog, and no behavior eval dispatched while a rehearsal runs. The
  alternative is a rehearsal key with a credit limit, the only hard limit. A
  live scene dispatch (PR 4d) uses the same secret and the same soft watchdog,
  and three passes cost several times the two-moment probe (Live scenes,
  Cost), so the credit limit matters more there.
- **R2, the room.** Default: the Discord stand-in, which answers at
  Discord's hostnames so `nunchi-mcp-discord`, discord.py and
  `hermes gateway run` run unmodified. Nunchi's own processes run on it in
  the scripted Discord room (PR 3b), `hermes gateway run` in PR 3c. The live
  probe's two moments still use the in-process stand-ins above; a live directed
  scene (PR 4d) runs on the Discord stand-in.
- **R3, Codex's namespace tools.** Outcome of the first live run
  (2026-10-09): OpenRouter passed Codex's namespace tools through, and the
  Codex run on `anthropic/claude-haiku-4.5` passed. What follows is how the
  probe tells the cases apart, kept for later runs and other models. If
  OpenRouter rejects the room tools
  Codex sends as a `namespace` tool, Codex's turn fails, and so does its
  run, with the provider's error as the reason; the verdict reads "blocked
  on a model route (R3)" when that error names the namespace. The other two
  jobs go on. If OpenRouter drops the tools, the model answers without a
  room tool and the turn ends in silence. That run can still pass, since in
  a live run silence is the model's call; its verdict says that no room
  tool was called, and the direct question reads `misses`. The Codex job
  then runs the labelled arm with an OpenAI model (design choice 5),
  whatever the main run's outcome: the same probe with `codex_openai_model`
  as the agent's model, recorded under `rehearsal-out/openai-arm/codex/`
  and shown in the job summary on its own, with its own pass or fail; a
  failed arm fails the job. A failure on Haiku beside a pass on the OpenAI
  model points at the namespace tools with a non-OpenAI model on
  OpenRouter's Responses route; both failing points at the route itself.
  The two requests differ in more than the model: on a GPT-6 model Codex
  0.160.1 runs in its code mode, sending its tools in an `additional_tools`
  input item (still as `namespace` tools) with the room tools nested in its
  `exec` tool, not listed. Checked offline with a scripted endpoint: a room
  call made from `exec` reaches the room and reads as a room tool call in
  the verdict. The arm has no scripted CI lane: the kit's scripted Codex
  endpoint does not speak code mode. The alternatives are an OpenAI key for
  Codex, or a translating hop between Codex and OpenRouter, which is not
  built without Zoe's say.
