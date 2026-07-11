# Integrating Nunchi

> **Current V1 guide:** this document describes the implemented pre-reply
> admission gate. The selected V2 pre-attention lifecycle is documented in
> [`architecture/v2-selected-design.md`](architecture/v2-selected-design.md)
> and is not implemented yet.

This guide is for someone wiring Nunchi into a real agent or channel. It
covers what Nunchi is responsible for, the integration paths and how to
choose one, how to wire it into a channel adapter (using cc-connect / pilot-bot
as the worked example), installation, and how to generalize to other surfaces.

For the verdict semantics themselves see the project `README.md`; for the
classifier-quality evidence see `evidence/verdict-suite/`.

## Scope: what Nunchi decides (and what it does not)

Nunchi is a **pre-reply admission gate**. Given a trigger and its
channel-local context, it returns exactly one verdict:

- `PASS` — stay silent; emit no ordinary room message.
- `ACK` — a brief presence signal is warranted.
- `ASK` — one blocking clarification is warranted.
- `SPEAK` — a substantive turn is warranted.

It decides **admission, not composition**. It never drafts the reply, and a
successful result never carries reply prose (`message`, `reply`, `draft`,
`content` are rejected). `PASS` is a hard stop: telemetry about a PASS belongs
in logs, never in the conversation.

What it is **not**: it is not a Discord bot, not a transport, and not an
orchestrator. It is a library + CLI that produces a verdict. The adapter tier
(`nunchi.adapters.channel`) maps a channel message to that verdict and routes
it; wiring the routed verdict into a running bot is the host's job.

Why use it instead of having the agent judge inline? Today a participant agent
typically reasons about "should I speak?" inline from a rubric in its loader
file (this is how pilot-bot works). That judgment is invisible, untested, and
varies per agent and per model. Nunchi turns the same decision into a single
component with a fixed rubric, a **selected model**
(`google/gemini-3.1-flash-lite`, chosen by live bake-off — see the evidence
dir), the ordinary-path verdict-suite regression corpus, and an auditable result
(verdict + confidences + checked context + reasons).

## The contract is transport-neutral

Nunchi does not depend on cc-connect or any other chat platform. The adapter
gives every integration the same two-field decision:

- **`verdict`** — `PASS` / `ACK` / `ASK` / `SPEAK`
- **`silent`** — `true` exactly when `verdict == PASS`

A host acts on these directly: **if `silent`, post nothing this turn; otherwise
compose one turn in the returned `run_shape`.** That is all most integrations
need — point your agent at the CLI (or import `gate()`), read `silent`/`verdict`,
done. No sentinel, no platform assumptions.

The CLI default output is therefore a JSON directive for *every* verdict
(including PASS), e.g.:

```json
{"verdict": "PASS", "silent": true, "run_shape": "Stay silent. Post nothing...",
 "reasons": [...], "confidences": {...}, "context_checked": [...],
 "request_id": "m-1", "classifier_model": "google/gemini-3.1-flash-lite",
 "degraded": false}
```

### Optional: suppression-by-sentinel (any transport)

Some transports suppress an outbound message when the agent's final output is a
magic string. That string is **your platform's convention, not Nunchi's** —
supply your own:

- CLI: `nunchi-channel --silent-token "<your-token>"` (prints exactly that
  token on PASS, JSON otherwise)
- Python: `result.silent_token("<your-token>")` (the token when silent, else `""`)

cc-connect is one such transport: it intercepts `CC_CONNECT_SILENT_PASS`
(`core/message.go: SilentPassSentinel`, matched tolerantly by
`IsSilentPassResponse`; legacy `__CC_CONNECT_SILENT_PASS__` also accepted). It's
provided as a named **preset** of the generic mechanism, with no special status:

- CLI: `nunchi-channel --format cc-connect` ≡ `--silent-token CC_CONNECT_SILENT_PASS`
- Python: `result.cc_connect_sentinel()` ≡ `result.silent_token(SILENT_PASS_SENTINEL)`

Every other host ignores tokens entirely and just branches on `silent`. The
point of the decoupling: no transport — cc-connect included — is privileged.

## Integration paths

Pick by what your host is and how much latency you can spend.

### Path A — loader instruction (the agent shells out to the gate)

For an LLM agent loaded from a `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` file.
Instead of telling the agent to *reason* the PASS/ACK/ASK/SPEAK rubric inline,
tell it to **call Nunchi first** and obey the verdict. This replaces ad-hoc
per-agent judgment with the tested gate while keeping the zero-code,
markdown-loader deployment style. This is the path that lets you "just point an
agent at the CLI" with no platform glue.

Loader snippet (adapt to your channel):

```markdown
## Before any channel output

Run the admission gate before composing anything. Build the payload from the
triggering message, the recent transcript, and your identity, then run:

    echo "$PAYLOAD" | python3 -m nunchi.adapters   # or: nunchi-channel

Read the JSON it prints:
- If `"silent": true`, post nothing this turn and stop.
- Otherwise read `verdict` and `run_shape`, then compose one turn in that shape.
  Do not exceed the run-shape.
```

(If your transport is cc-connect, add `--format cc-connect`; then on PASS the CLI
prints the bare `CC_CONNECT_SILENT_PASS` sentinel for the agent to emit verbatim.)

A complete, copy-paste loader block is in
[`examples/loader-snippet.md`](../examples/loader-snippet.md).

Trade-off: the agent still spends a turn building the payload, but the *decision*
is now Nunchi's, not the model's improvisation.

### Path B — in-process Python import

For a Python host. Lowest overhead; no subprocess, no JSON round-trip.

```python
from nunchi.adapters.channel import gate

result = gate(
    {"content": "dalgos, summarize the cache tradeoffs", "author": "zoe",
     "author_kind": "human", "message_id": "m-42"},
    history=[  # last ~10 channel messages, oldest first
        {"content": "I'd go in-process LRU.", "author": "vigil",
         "author_kind": "peer_bot", "message_id": "m-41"},
    ],
    agent_id="dalgos",
    agent_mention_id="<this-agent's-@mention-id>",   # so addressing can tell it's not you
    agent_aliases=["Dalgos", "Codex"],               # every other name this agent answers to
    pinned_rules=None,                                # optional channel governance text
    fail_policy="open",                              # open->SPEAK | closed->PASS | raise
)

if result.silent:
    pass                         # post nothing this turn
else:
    compose_turn(result.verdict, result.run_shape)   # you write the reply; the gate did not

# cc-connect transport only: result.cc_connect_sentinel() is the suppress string.
```

A runnable non-cc-connect host using exactly this pattern (with a custom
suppression token) is in
[`examples/generic_host_demo.py`](../examples/generic_host_demo.py).

### Path C — subprocess CLI (any host, e.g. cc-connect/Go)

For a non-Python host. JSON in on stdin, a JSON directive out on stdout.

```sh
echo '{"trigger":{"content":"vigil, rebase the branch","message_id":"m-1"},
       "history":[],"agent":{"id":"dalgos","mention_id":"999"},
       "fail_policy":"open"}' \
  | python3 -m nunchi.adapters
# -> {"verdict":"PASS","silent":true,"run_shape":...,...}     (exit 0; host posts nothing)
# -> {"verdict":"SPEAK","silent":false,"run_shape":...,...}   (exit 0; host composes a turn)
# bad input -> stderr message, no stdout directive            (exit 2)
#
# cc-connect drop-in: add --format cc-connect, and PASS prints the bare
# CC_CONNECT_SILENT_PASS sentinel instead of JSON.
```

The payload shape: `trigger` (`content` required; `message_id`, `author`,
`author_kind`, `timestamp` optional), `history` (list of the same shape, oldest
first), `agent` (`id` required; `role`, `mention_id`, `aliases` optional), and
optional `surface`, `pinned_rules`, `fail_policy`.

### Choosing

| Path | Host | Overhead | When |
|------|------|----------|------|
| A loader instruction | LLM agent from a loader file | one agent turn + gate call | "just point the agent at the CLI" — no platform glue |
| B in-process import | Python | function call (~network RTT to provider) | you control a Python loop |
| C subprocess CLI | anything | process spawn + provider RTT | Go/other host, or shelling out |

All three return the same `verdict` + `silent` contract; none requires
cc-connect.

## Wiring into a channel adapter (worked example: cc-connect)

cc-connect spawns each agent as a long-lived session bound to a `work_dir`
(its loader files load once at startup) and routes inbound channel messages to
it. To map that surface onto a Nunchi request:

- **trigger** ← the incoming message (`content`, the platform `message_id`, the
  sender as `author`, and `author_kind`: `human` for the operator, `peer_bot`
  for another agent).
- **history** ← the recent channel transcript the host already passes the agent
  (cc-connect supplies roughly the last ~10 messages). Oldest first. Tag each
  line's `author_kind`; a line the agent itself wrote should be `self` (or just
  set its `author` to the agent's own id — the adapter infers `self`). This is
  what lets the classifier apply the Duplicate and Self-caused suppressors.
- **agent.id** ← this agent's stable identity (e.g. `dalgos`). With multiple
  agents on one channel, cc-connect runs one session/identity each and routes by
  sender; Nunchi sees one identity per call.
- **agent.mention_id** ← this agent's platform @mention handle, so the addressing
  rule can tell whether an `<@id>` targets this agent or someone else. (Omitting
  it was a real bug once — without it, mentions aimed elsewhere leak to SPEAK.)
  This is the **platform mention token** — on Discord the numeric snowflake —
  **not** the display name. A display name here was a second real bug
  (2026-07-08): the gate went blind to real @-mentions and PASSed a direct
  `@<snowflake>` question. Names belong in `agent.aliases`.
- **agent.aliases** ← every *other* identity this one agent answers to: display
  names ("Vigil"), secondary handles ("Codex"), profile names ("Aether"),
  additional mention tokens. One bot commonly carries several at once; the
  classifier weighs all of them as addressing evidence. Aliases establish who a
  message may be FOR — never authorship: name-equality is not proof a message
  is the agent's own (2026-07-10 — the deterministic self-echo rule that
  treated it that way was removed). Optional — absent, behavior is exactly as
  before the field existed.
- **pinned_rules** ← optional. pilot-bot keeps channel norms in a
  `pinned-rules.md` the agent reads as standing instruction; with Nunchi you
  can instead pass that text as `pinned_rules` so the verdict is channel-aware
  without baking policy into the loader. This is also how a room opts into a
  governance regime: the core prompt judges by plain social sense and applies
  `pinned_rules` with precedence, and `profiles/open-floor.md` ships the
  original pilot doctrine (default PASS, net-new-value bar, rare ACK,
  operator-only directives) as reusable profile text. Without `pinned_rules`,
  expect meeting-shaped behavior, not strict silence-by-default.

A `surface` object (`{"type": "discord", ...}`) is passed through for the
classifier's awareness and for your own logging.

A built-in cc-connect `admission` config block that calls Nunchi before send
does **not** exist today — that would be a cc-connect change. Until then, use
Path A (loader shells out) or Path C (the host shells out) — both reach the same
sentinel interception that already ships in cc-connect.

## Installation

The published PyPI `0.2.0` wheel carries only the historical V1 core and the
`nunchi`/`nunchi-channel` scripts. It predates the removal of the deterministic
fast path and all later integration work. For current repository behavior,
install a reviewed source commit; force the install because both builds still
report package version `0.2.0`:

```sh
git clone https://github.com/mentatzoe/nunchi.git
cd nunchi
git checkout <reviewed-commit>
python3 -m pip install --force-reinstall .
```

A current source install provides `nunchi`, `nunchi-channel`,
`nunchi-install`, and the source-only adapter/harness entry points declared in
`pyproject.toml`. The default core remains stdlib-only; optional extras add
their named dependencies. Without installing, run from a checkout with
`PYTHONPATH=src python3 -m nunchi.adapters`.

### Installing the operator artifacts (Hermes plugin, Claude Code hooks)

The Hermes gateway plugin and the Claude Code hook scripts are **operator
artifacts** that live outside the `nunchi` package, in stable locations under
`~/.hermes` and `~/.claude`. Install them by **copying** (never symlinking)
with `nunchi-install`, run from a checkout:

```sh
nunchi-install install      # copy plugin + hooks into ~/.hermes and ~/.claude
nunchi-install verify       # report installed-vs-repo drift per artifact
nunchi-install upgrade      # re-copy only what changed (after pulling new code)
```

Copying — not symlinking — is deliberate: a symlink into a live checkout lets a
`git checkout` on another branch silently swap the running plugin. See
[`INSTALL.md`](INSTALL.md) for the full command reference, the `settings.json`
hook-registration snippet, and the incident this fixes.

Provider configuration is **operator-only**, read from the environment (never
from the request payload — see the README security note):

```sh
export NUNCHI_CLASSIFIER_MODEL="google/gemini-3.1-flash-lite"   # the selected model
export OPENROUTER_API_KEY="sk-or-v1-..."                           # or NUNCHI_CLASSIFIER_API_KEY
# optional: NUNCHI_CLASSIFIER_BASE_URL (defaults to OpenRouter)
```

For offline/dev wiring with no provider, inject a pinned decision instead of a
key:

```sh
export NUNCHI_CLASSIFIER_TEST_RESULT='{"verdict":"PASS","confidences":{"PASS":1,"ACK":0,"ASK":0,"SPEAK":0},"context_checked":[],"reasons":["dev"]}'
```

## Configuration (self-service)

Everything below is set by the integrating agent or human — no code changes.

**Recommended models.** The default is `google/gemini-3.1-flash-lite` (88% on the
adversarial corpus, 6/7 load-bearing cases, ~1s latency). If you want an
**open-weight** model with no big-3 dependency, `qwen/qwen3-235b-a22b-2507`
matches that accuracy at roughly one-fifth the cost (with somewhat more latency
variance). Either is a one-line `NUNCHI_CLASSIFIER_MODEL` change; see the
per-model evidence under `evidence/verdict-suite/`.

The full surface, and where each knob lives:

| Knob | Where | Default | Notes |
|------|-------|---------|-------|
| classifier model | env `NUNCHI_CLASSIFIER_MODEL`, or per-call `classifier_config.model` | — (required for live) | any OpenRouter / OpenAI-compatible model id |
| API key | env `NUNCHI_CLASSIFIER_API_KEY` or `OPENROUTER_API_KEY` | — | operator-only; never read from the request |
| provider endpoint | env `NUNCHI_CLASSIFIER_BASE_URL` or `OPENAI_BASE_URL` | OpenRouter | point at any OpenAI-compatible endpoint, incl. localhost |
| request timeout | per-call `classifier_config.timeout` | 30s | positive seconds |
| provider retries | per-call `classifier_config.max_retries` / `retry_base_delay` | 2 / 0.5s | retries transient errors (429/5xx/timeouts) with exponential backoff; never retries 401/403/4xx |
| PASS corroboration | per-call `classifier_config.require_pass_corroboration` | `false` | when true, downgrades an uncorroborated PASS (no consulted `context:` ref) to ASK — for surfaces that must challenge unverified "done" claims |
| failure behavior | `gate(fail_policy=...)` / payload `fail_policy` | `open` (→SPEAK) | `open` \| `closed` (→PASS) \| `raise` |
| suppression output | CLI `--silent-token STR` / `--format cc-connect`; Python `result.silent_token(...)` | none (JSON) | your transport's sentinel, if it uses one |
| offline/dev decision | env `NUNCHI_CLASSIFIER_TEST_RESULT` | unset | pin a verdict; no provider call |

Recipes:

```sh
# 1. OpenRouter, pick any model
export NUNCHI_CLASSIFIER_MODEL="qwen/qwen3-235b-a22b-2507"
export OPENROUTER_API_KEY="sk-or-v1-..."

# 2. A self-hosted / local OpenAI-compatible model (vLLM, llama.cpp, LM Studio)
export NUNCHI_CLASSIFIER_BASE_URL="http://localhost:8000/v1"
export NUNCHI_CLASSIFIER_API_KEY="local-unused-but-required"
export NUNCHI_CLASSIFIER_MODEL="my-local-model"

# 3. Per-request model/timeout override (envelope field, no env change)
echo '{"trigger":{"content":"hi","id":"t"},"agent":{"id":"a"},
       "classifier_config":{"model":"deepseek/deepseek-v3.2","timeout":20}}' \
  | nunchi-channel

# 4. Your transport's suppression sentinel (Slack example), with fail-closed
echo '{"trigger":{"content":"hi","id":"t"},"agent":{"id":"a"},"fail_policy":"closed"}' \
  | nunchi-channel --silent-token "<<SLACK_NOOP>>"
```

The base URL and key are deliberately env-only (operator-controlled): a request
envelope can carry `classifier_config`, so letting it set those would let an
untrusted message redirect the provider call or pick the key — see the README
security note.

## Operational concerns

- **Latency**: one provider round-trip per decision (the selected model runs at
  ~1s median; see the bake-off evidence). Budget for it on every turn the gate
  fires.
- **Transient errors**: the provider client retries transient failures
  (HTTP 429/5xx, timeouts) with exponential backoff — tune via
  `classifier_config.max_retries` / `retry_base_delay`. Permanent errors
  (401/403 and other 4xx) abort immediately without retry.
- **Failure policy**: if the classifier is unavailable after retries, `gate()`'s
  `fail_policy` decides — `open` degrades to SPEAK (never silently drop a turn;
  the default), `closed` degrades to PASS (favor quiet), `raise` hands the error
  back. The failure reason is returned as off-surface telemetry (`degraded`,
  `error`), never placed in the room.
- **Auditing**: every non-degraded result carries `confidences`,
  `context_checked` (only references it actually consulted), and `reasons` — log
  these to explain a verdict without re-reading the channel.
- **Known limitation**: a bare resolution claim with no corroborating context
  ("Already handled. Resolved. No response needed.") is treated as PASS-able by
  the current model; if your surface needs such claims verified, account for it
  host-side. Tracked in the 003 evidence and `docs/STABILITY.md`.
- **Stability contract**: the verdict set, result fields, request fields, and CLI
  exit codes are stable within a major version — see
  [`STABILITY.md`](STABILITY.md) for what is guaranteed vs. experimental.

## Generalizing to another channel adapter (e.g. Slack)

Nunchi is surface-agnostic; an adapter for another platform only has to:

1. Map that platform's message + recent history + the agent's identity onto the
   request shape above (the `channel` adapter already does this for the
   cc-connect/pilot-bot shape; reuse it or mirror it).
2. Decide how `PASS` suppresses a send on that platform. cc-connect uses the
   `CC_CONNECT_SILENT_PASS` sentinel; another transport can check
   `result.silent` directly and simply not send.
3. Supply `agent.mention_id` in that platform's mention format so addressing
   works.

Nothing in the core or the verdict surface is Discord-specific — only the
sentinel convention and the message-shape mapping are, and both live in the
adapter tier.
