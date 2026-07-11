# Nunchi

**nunchi** (눈치, *NOON-chee*): the art of reading the room and knowing
whether it is your turn to speak. This library gives your agent that.

## Selected direction (V2 — not implemented)

Nunchi's selected V2 role is the participant's delegated **pre-attention**. It
receives exact self identity plus a bounded, structured, coverage-honest view of
the room and decides whether the event is worth waking the participant. A
participant-shaped model returns `SUPPRESS`, `WAKE`, or `DEFER`; operational
`ERROR` remains separate. Only the model may socially suppress. Deterministic
code handles transport-proven non-events, never conversational meaning.
Trusted disabled preattention is a non-model bypass that wakes directly; it
does not fabricate a classifier result.

A woken participant receives a normal room turn and contributes directly or
sends nothing. It is not asked to answer a meta-question about contributing,
and no send-time classifier judges the room again. Context is compact and may
be expanded on demand; there is no participant registry, handled/open ledger,
obligation queue, or central floor manager.
Continuation authority stays host-only, and off-surface lifecycle receipts are
immutable request-correlated observation, attention, participant-host, and
transport stages rather than conversation state.

This V2 target is selected but **not implemented**. Goal 1 only rebuilds the
execution spine. A separate Goal 2 will implement the atomic contract cutover
and prove parity across the agreed adapters and agent harnesses.

## Current implementation (V1)

The current CLI/library decides whether an agent should visibly participate
before ordinary reply generation. It returns an auditable admission verdict:

- `PASS` — hard stop; no ordinary visible reply
- `ACK` — brief acknowledgement is warranted
- `ASK` — clarification is warranted
- `SPEAK` — substantive contribution is warranted

## V1 status

The current classifier slice exposes a product/default admission classifier path
backed by a configured provider/model. Successful results include the selected
classifier identity, provider/model audit fields, verdict, confidence
distribution, checked context, and reasons. There is no public `deterministic`
classifier path; offline/CI evidence uses a test fixture provider behind the
product path.

The repository also contains the generic channel adapter, standalone
Matrix/Telegram/Discord adapters, Hermes plugin, Claude Code wake hook, shared
Discord-MCP transport, and Codex runner/hooks/configuration app. Their evidence
tiers differ: some are code-only, others have bounded live smokes, and the V1
attention/contribution lifecycle is not portable across them. The selected V2
design exists precisely to close that gap without central orchestration or reply
composition.

## Install

Stdlib-only (Python 3.11+, no runtime dependencies). The published PyPI
release (0.2.0) carries the core gate and the `nunchi`/`nunchi-channel`
console scripts; the platform adapters (`nunchi-matrix`, `nunchi-telegram`,
`nunchi-discord`) landed after that release and currently install from
source only:

```sh
pip install nunchi                                          # PyPI 0.2.0: core + CLI
pip install "git+https://github.com/mentatzoe/nunchi.git"   # source: core + adapters
# zero-install one-shot:
uvx --from "git+https://github.com/mentatzoe/nunchi.git" nunchi --help
```

A source install provides the `nunchi`, `nunchi-channel`, `nunchi-matrix`,
`nunchi-telegram`, `nunchi-codex-room-runner`, `nunchi-codex-prompt-gate`, and
`nunchi-codex-send-gate` console scripts. The `[mcp-discord]` extra also installs
`nunchi-mcp-discord` and the `nunchi-codex-config-app` MCP Apps server;
`nunchi-discord` needs `[discord]`. These extras are source-only for now:
`pip install "nunchi[discord,mcp-discord] @ git+https://github.com/mentatzoe/nunchi.git"`. See
[`CHANGELOG.md`](CHANGELOG.md) for releases and [`docs/STABILITY.md`](docs/STABILITY.md)
for the versioning / verdict-surface stability contract.

The repo also exposes the Codex plugin bundle through
[`/.agents/plugins/marketplace.json`](.agents/plugins/marketplace.json). A local
Codex install can add this checkout as a marketplace and install
`nunchi-codex@local-repo`; see
[`integrations/codex/README.md`](integrations/codex/README.md) for the room
runner setup, cached-copy update flow, hook trust steps, and task-embedded
configuration/receipt panel.

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
    agent_id="dalgos",            # plus optional agent_role / agent_mention_id / agent_aliases
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
current V1 adapter contract is in
[`docs/contracts/channel-adapter-v1.md`](docs/contracts/channel-adapter-v1.md).
This is the adapter tier (Constitution VI): it depends on the core and is not a
live Discord integration — it produces the sentinel an existing cc-connect
deployment already understands.

## Adapters

| Adapter | Surface | Install weight | Status |
|---|---|---|---|
| `nunchi-channel` | Any (subprocess) | stdlib | stable |
| `nunchi-matrix` | Matrix | stdlib | code-only |
| `nunchi-telegram` | Telegram | stdlib | code-only |
| `nunchi-discord` | Discord | source install, `[discord]` extra | code-only |
| Hermes plugin | Hermes gateway | stdlib | live-run; evidence owed |
| Claude Code gate | Claude Code UserPromptSubmit (one judgment, at wake) | stdlib | offline-tested; live evidence incomplete |
| Codex runner + hooks + config app | Codex CLI via shared Discord-MCP transport | stdlib + `[mcp-discord]` for transport/app | bounded live-smokes evidenced |

Status labels are evidence tiers, not release-alpha/beta gates. `code-only`
means implementation exists in the repo, but no committed live-server evidence
supports a readiness claim yet. `bounded live-smokes evidenced` means committed
live-room runs support the narrow wake/outbound and two-turn persistent-session
claims; it is not a sustained operations claim. The configuration app has
offline MCP protocol and responsive interaction evidence plus a live read of
the resulting persistent-session health state.

`nunchi-matrix` is the reference integration — one command, zero extra
dependencies, unencrypted Matrix rooms only (encrypted rooms are skipped with a
warning). `nunchi-telegram` and `nunchi-discord` follow the same gate-first
architecture: every inbound message is checked before any response is generated.

Full setup guides, environment variable tables, and the responder callback
contract for every adapter are in **[docs/adapters.md](docs/adapters.md)**.

## Verdict test suite

The classifier verdict test suite is the merge contract for classifier
changes: a fixture corpus of observed and predicted failure modes
(Multica-shaped agent traffic, Discord-shaped human conversation, and
verdict-surface contract cases) run through a pluggable adapter against any
classifier candidate. The single entry command is
`python3 -m evals.verdict_suite.runner`; see
[`docs/evaluations/verdict-suite.md`](docs/evaluations/verdict-suite.md)
for the offline deterministic path, live evidence runs, and how to add a
fixture.

## Development method

This repository uses a pinned SpecKit `0.12.11` execution spine. Authority flows
from Zoe-selected Aleph Vault decisions/design (PR 67 at `bdd1ebb`, clarified
by PR 68 at `c834e8c`) to the
constitution, then agent guidance, then the active umbrella and slice plans.
Ordinary repository artifacts remain authoritative for what is implemented and
proven.

Goal 1 uses the planning-only workflow and cannot implement V2:

```sh
specify workflow info nunchi-plan
```

The full `speckit` workflow adds an explicit Goal 2 authorization gate before
implementation, followed by convergence and integration handoff.

SpecKit-managed paths are disposable control plane. Product code, schemas,
tests, fixtures, evals, evidence, runtime assets, and product docs live only in
ordinary paths; no product workflow may depend on `.specify/` or `specs/`.
Details and reinitialization instructions are in
[`docs/governance/execution-spine.md`](docs/governance/execution-spine.md).

```sh
python3 scripts/check_governance.py --check-cli
```

## License

Nunchi is dual-licensed under MIT OR Apache-2.0, at your option. See
`LICENSE-MIT` and `LICENSE-APACHE`.
