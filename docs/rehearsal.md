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
OpenRouter yet.

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
  `nunchi-mcp-discord`, discord.py's wire and the `hermes gateway` process
  come with the Discord stand-in (PR 3).
- **How well the agent reads the room.** Two moments, once each. The scenes,
  grading and a reference column come in PR 4.
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
  Claude Code, the post did not go through a room tool;
- the pins, the isolation or the record did not hold: among them, a
  recorded process got a key other than its harness's own (Nunchi's keys
  stay in Nunchi's process), or, where Hermes's own builders show it, the
  agent's terminal gets any key; or the harness showed it ran otherwise
  than configured: Claude Code did not recognize the model, or started in
  another permission mode than the pinned version does for that model;
- the probe itself raised an error (`run.json`'s `errors`);
- the key or the canary is in an output, or an output could not be read.

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
agent's model for the Codex job's labelled OpenAI-model arm (R3, below). The
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
`--attention-model` takes the behavior eval's label (`id` or `id@effort`);
a label for another route (`messages:`, `responses:`) is refused, since the
probe builds the chat route only. `--arm LABEL` names a run that is one arm
of a comparison, in `run.json` and in the title of `summary.md`.

CI runs `--scripted`, and this probe's tests (`tests/v2/test_rehearsal.py`,
the scripted probe's own test included), in the Claude Code (`claude-code-mod`),
Codex and Hermes lanes of `ci.yml`, with no secret.

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
  alternative is a rehearsal key with a credit limit, the only hard limit.
- **R2, the room.** Default: the Discord stand-in, which answers at
  Discord's hostnames so `nunchi-mcp-discord`, discord.py and
  `hermes gateway` run unmodified, comes in PR 3. Until then the probe uses
  the in-process stand-ins above.
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
