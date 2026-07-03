# Nunchi

**nunchi** (눈치, *NOON-chee*): the art of reading the room and knowing
whether it is your turn to speak. This library gives your agent that.

Nunchi is a portable CLI/library for deciding whether an agent should visibly
participate on an unstructured shared surface before ordinary reply generation.
It returns an auditable admission verdict:

- `PASS` — hard stop; no ordinary visible reply
- `ACK` — brief acknowledgement is warranted
- `ASK` — clarification is warranted
- `SPEAK` — substantive contribution is warranted

## Status

The current classifier slice exposes a product/default admission classifier path
backed by a configured provider/model. Successful results include the selected
classifier identity, provider/model audit fields, verdict, confidence
distribution, checked context, and reasons. There is no public `deterministic`
classifier path; offline/CI evidence uses a test fixture provider behind the
product path.

The first **adapter** ships alongside the core: `nunchi.adapters.channel`
maps a channel-local message shape to an admission request and routes the
verdict for a participant agent (see "Consuming the gate" below). Live
Discord/cc-connect process integration, central orchestration, broad benchmarks,
launch claims, and reply composition remain out of scope — the adapter produces
the sentinel an existing cc-connect deployment already understands; wiring it
into a running bot is the consumer's step.

## Install

Stdlib-only (Python 3.11+, no runtime dependencies). Not yet on PyPI; install
from source:

```sh
pip install "git+https://github.com/mentatzoe/nunchi.git"   # or: pip install .
# zero-install one-shot:
uvx --from "git+https://github.com/mentatzoe/nunchi.git" nunchi --help
```

This provides the `nunchi`, `nunchi-channel`, and `nunchi-matrix` console scripts. See
[`CHANGELOG.md`](CHANGELOG.md) for releases and [`docs/STABILITY.md`](docs/STABILITY.md)
for the versioning / verdict-surface stability contract.

## Quickstart

Evaluate a request from stdin through the product/default classifier:

```sh
export NUNCHI_CLASSIFIER_MODEL="your/provider-model"
export OPENROUTER_API_KEY="..."
PYTHONPATH=src python3 -m nunchi admit < tests/fixtures/speak.json
```

Evaluate a request from a file through the product classifier:

```sh
PYTHONPATH=src python3 -m nunchi admit --input tests/fixtures/pass.json
```

Evaluate with classifier selection in the envelope, or override it from the CLI:

```sh
PYTHONPATH=src python3 -m nunchi admit --input tests/fixtures/speak_with_classifier.json
PYTHONPATH=src python3 -m nunchi admit --classifier product --input tests/fixtures/speak_cli_precedence.json
```

Run the verification suite:

```sh
python3 -m unittest
```

## Product contract

The core output contract is:

- `classifier`
- `classifier_provider`
- `classifier_model`
- `verdict`
- `confidences`
- `context_checked`
- `reasons`

Successful CLI evaluations write one JSON object to stdout and exit `0`.
Failures write diagnostics to stderr and do not emit a success verdict on
stdout.

Exit codes:

- `0` — successful evaluation
- `1` — unexpected runtime failure
- `2` — input source or JSON parse failure
- `3` — admission request validation failure

Nunchi owns admission, not composition. It does not draft the final reply and
it does not prescribe speech shape beyond the admission verdict.

## Classifier selection

The documented default classifier path is `product`. It is the only supported
classifier path in this slice and is backed by a configured OpenAI-compatible
provider/model. It is not a relabelled local keyword or deterministic verifier.
If provider/model configuration is unavailable, Nunchi fails clearly instead
of silently falling back to local logic.

Classifier selection can be supplied by:

- envelope field: `"classifier": "product"`
- CLI flag: `--classifier product`

If both are present, the CLI flag takes precedence. Optional
`classifier_config` / `--classifier-config` must be a JSON object. Supported
product configuration keys are `provider`, `model`, and `timeout`. Unsupported
classifier names or config keys fail clearly without emitting a success result.

The provider endpoint and API key are operator-only and are never read from
`classifier_config`: because a request envelope carries `classifier_config`, an
untrusted request must not be able to redirect the provider call (which carries
the operator's API key) or choose which environment variable the key is read
from. These are resolved exclusively from operator environment variables:

- `NUNCHI_CLASSIFIER_MODEL` for the model name (or `classifier_config.model`).
- `NUNCHI_CLASSIFIER_API_KEY` or `OPENROUTER_API_KEY` for the API key.
- `NUNCHI_CLASSIFIER_BASE_URL` or `OPENAI_BASE_URL` for the compatible API
  base URL; default is `https://openrouter.ai/api/v1`.

The test suite sets a fixture provider response for deterministic offline
verification. That fixture provider is not a selectable classifier path.

## Python API

The in-process core is available without shelling out:

```python
import os
import sys
sys.path.insert(0, os.path.abspath("src"))

from nunchi import evaluate

os.environ["NUNCHI_CLASSIFIER_MODEL"] = "your/provider-model"
os.environ["OPENROUTER_API_KEY"] = "..."

result = evaluate({
    "trigger": {"content": "nunchi-vigil, please implement the CLI MVP."},
    "context": [],
})
```

`result["classifier"]` identifies the selected path, `result["classifier_model"]`
identifies the provider model, and `result["verdict"]` is one of `PASS`, `ACK`,
`ASK`, or `SPEAK`.

## Consuming the gate: the channel adapter

A participant agent on a shared, turn-aware surface does not call the core
directly — it uses the **channel adapter** (`nunchi.adapters.channel`), which
maps its channel-local inputs (the triggering message, the recent transcript,
its own identity) to an admission request, runs the gate, and returns a
transport-neutral decision: `verdict` plus `silent`. If `silent`, the host posts
nothing; otherwise it composes one turn in the returned *run-shape*. The adapter
never writes replies, and nothing in it is tied to a specific chat platform.

In-process (Python host):

```python
from nunchi.adapters.channel import gate

result = gate(
    {"content": "dalgos, summarize the cache tradeoffs", "author": "zoe",
     "author_kind": "human", "message_id": "m-42"},
    history=[                      # last ~10 channel messages, oldest first
        {"content": "I'd go in-process LRU.", "author": "vigil",
         "author_kind": "peer_bot", "message_id": "m-41"},
    ],
    agent_id="dalgos",            # plus optional agent_role / agent_mention_id
    pinned_rules=None,            # optional channel governance text
    fail_policy="open",           # open->SPEAK | closed->PASS | raise
)

if result.silent:
    ...                           # post nothing this turn
else:
    ...                           # compose a turn per result.verdict / result.run_shape
```

Subprocess (non-Python host) — JSON in, a transport-neutral JSON directive out:

```sh
echo '{"trigger":{"content":"vigil, rebase the branch","message_id":"m-1"},
       "history":[],"agent":{"id":"dalgos"},"fail_policy":"open"}' \
  | PYTHONPATH=src python3 -m nunchi.adapters
# -> {"verdict":"PASS","silent":true,...}    (host posts nothing)
# -> {"verdict":"SPEAK","silent":false,...}  (host composes a turn)
```

If your transport suppresses a send via a magic final-output string, pass your
own with `--silent-token "<token>"` (or `result.silent_token("<token>")`) to
print it on PASS. cc-connect is just a named preset of this — `--format
cc-connect` ≡ `--silent-token CC_CONNECT_SILENT_PASS` — with no special status;
no transport is a dependency.

### Room governance profiles

The classifier core judges by plain social sense: who is speaking, what has
been said, who this agent is — is it this agent's turn? It carries no room
doctrine of its own. A room that wants a specific bar for taking a turn
supplies its norms as `pinned_rules`; the classifier applies the room's bar
with precedence over plain social sense.

[`profiles/open-floor.md`](profiles/open-floor.md) ships as the first reusable
profile: the strict operator-led working-channel doctrine of the original
open-floor pilot (default PASS, net-new-value bar for SPEAK, rare ACK,
operator-only directives, corroboration for completion claims). Pass its text
as `pinned_rules` to opt a channel into that regime:

```python
from pathlib import Path
from nunchi.adapters.channel import gate

result = gate(trigger, history=history, agent_id="dalgos",
              pinned_rules=Path("profiles/open-floor.md").read_text())
```

Verdict-suite fixtures whose expected verdicts were adjudicated under that
doctrine declare `"governance_profile": "open-floor"` in their metadata; the
suite loader injects the profile into their envelopes so the corpus stays
honest about which expectations are social sense and which are room policy.

**[`docs/integration.md`](docs/integration.md) is the full integration guide** —
scope, the three install/integration paths (loader instruction, in-process
import, subprocess CLI), how to wire it into a channel adapter, and how to
generalize to other surfaces. A runnable multi-turn demo is in
[`examples/read_the_room_demo.py`](examples/read_the_room_demo.py); the adapter
contract is in [`specs/004-read-the-room-adapter/spec.md`](specs/004-read-the-room-adapter/spec.md).
This is the adapter tier (Constitution VI): it depends on the core and is not a
live Discord integration — it produces the sentinel an existing cc-connect
deployment already understands.

## Matrix adapter (reference)

`nunchi.adapters.matrix` is a reference integration that joins Matrix rooms as a
gated participant. One command, zero extra dependencies.

### One-command quickstart

```sh
pip install "git+https://github.com/mentatzoe/nunchi.git"

export NUNCHI_MATRIX_HOMESERVER="https://matrix.example.com"
export NUNCHI_MATRIX_TOKEN="<your-access-token>"
export NUNCHI_MATRIX_ROOMS="!room1:example.com,!room2:example.com"
export NUNCHI_CLASSIFIER_MODEL="openai/gpt-4o-mini"
export OPENROUTER_API_KEY="<your-key>"

nunchi-matrix
```

Use `--dry-run` to gate without sending, or `--once` to process one sync batch
and exit (useful for cron or testing).

#### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `NUNCHI_MATRIX_TOKEN` | yes | — | Matrix access token |
| `NUNCHI_MATRIX_HOMESERVER` | yes | — | Base URL of your homeserver |
| `NUNCHI_MATRIX_ROOMS` | yes | — | Comma-separated room IDs to watch |
| `NUNCHI_CLASSIFIER_MODEL` | yes | — | Model for the admission gate |
| `OPENROUTER_API_KEY` | yes | — | API key (gate + demo responder) |
| `NUNCHI_MATRIX_STATE` | no | `~/.nunchi/matrix-sync.json` | Since-token persistence |
| `NUNCHI_MATRIX_LOG` | no | `~/.nunchi/matrix-gate.jsonl` | JSONL receipt log |
| `NUNCHI_MATRIX_AGENT_ID` | no | `bot_<localpart>` | Agent identity label |
| `NUNCHI_MATRIX_PEER_BOTS` | no | `` | Comma-separated user IDs (or `@prefix*` globs) treated as `peer_bot` |
| `NUNCHI_MATRIX_HISTORY` | no | `10` | Recent messages fed to the gate as context |
| `NUNCHI_RESPONDER_MODEL` | no | `NUNCHI_CLASSIFIER_MODEL` | LLM for the built-in demo responder |
| `NUNCHI_CLASSIFIER_BASE_URL` | no | OpenRouter | OpenAI-compatible API base URL |

#### Obtaining a Matrix access token

```sh
curl -XPOST 'https://YOUR_HOMESERVER/_matrix/client/v3/login' \
     -H 'Content-Type: application/json' \
     -d '{"type":"m.login.password",
          "identifier":{"type":"m.id.user","user":"@BOTUSER:HOMESERVER"},
          "password":"SECRET"}'
# Response includes "access_token"; export it as NUNCHI_MATRIX_TOKEN.
```

Or from Python:

```python
from nunchi.adapters.matrix import login
token = login("https://matrix.example.com", "@bot:example.com", "secret")
```

### Bridge note

One adapter covers Discord, Slack, Microsoft Teams, Telegram, and IRC via the
[Matrix bridge ecosystem](https://matrix.org/ecosystem/bridges/). Deploy
nunchi-matrix on your homeserver; the bridges handle protocol translation.

### Limitation: unencrypted rooms only

`nunchi-matrix` uses the Matrix Client-Server API directly without an E2EE
library. Rooms that use `m.room.encrypted` are detected and skipped with a
one-time warning per room. Use an unencrypted Matrix room or a bridge endpoint
that decrypts before delivering.

### Responder callback contract

The built-in demo responder is clearly labelled a demo — the adapter's product
is the gating loop. To wire a real agent, pass a callable:

```python
from nunchi.adapters.matrix import MatrixSyncLoop

def my_responder(trigger: dict, history: list[dict], gate_result) -> str | None:
    """
    trigger  — dict with content/author/author_kind/message_id/timestamp
    history  — list of the same shape, oldest first
    gate_result — ChannelGateResult (verdict/silent/run_shape/reasons/confidences)

    Return a string to post, or None to post nothing (receipt: responder-declined).
    """
    return f"[{gate_result.verdict}] I would respond here."

loop = MatrixSyncLoop(
    homeserver="https://matrix.example.com",
    token="tok_...",
    room_ids=["!room:example.com"],
    agent_id="my-agent",
    own_user_id="@my-agent:example.com",
    peer_bot_specs=["@other-bot:example.com"],
    history_len=10,
    state_path=...,
    log_path=...,
    responder=my_responder,
)
loop.run()
```

### Open Floor Protocol alignment

Nunchi verdicts map onto Open Floor Protocol floor semantics:

- `SPEAK` — taking the floor (producing a substantive participant turn)
- `PASS` — yielding the floor (posting nothing for this turn)
- `ACK` — brief acknowledgement without claiming the floor
- `ASK` — requesting clarification before proceeding

The adapter uses these names explicitly so future OFP compatibility is
vocabulary-aligned: a transport that implements OFP can map `gate_result.verdict`
to OFP floor-request/yield primitives without a translation layer.

## Verdict test suite

The classifier verdict test suite is the merge contract for classifier
changes: a fixture corpus of observed and predicted failure modes
(Multica-shaped agent traffic, Discord-shaped human conversation, and
verdict-surface contract cases) run through a pluggable adapter against any
classifier candidate. The single entry command is
`python3 specs/003-classifier-test-suite/contracts/runner.py`; see
[specs/003-classifier-test-suite/quickstart.md](specs/003-classifier-test-suite/quickstart.md)
for the offline deterministic path, live evidence runs, and how to add a
fixture.

## Development method

This repository uses Spec Kit. The constitution at
`.specify/memory/constitution.md` is the source of governance for all specs,
plans, tasks, implementation, documentation, and release claims.

For production work, use:

```text
constitution -> specify -> clarify -> plan -> checklist -> tasks -> analyze -> implement
```

A product spec should prove an end-to-end runnable path from supplied
conversation context to a verdict a harness can obey.

## License

Nunchi is dual-licensed under MIT OR Apache-2.0, at your option. See
`LICENSE-MIT` and `LICENSE-APACHE`.
