# Install and operate Nunchi V2

## Artifact installation

Build and install the exact candidate into a new environment. The wheel digest
is an exact-byte contract, not a decompressed-content equivalence claim. The
normative build inputs are: a clean checkout of one exact commit, that commit's
timestamp as `SOURCE_DATE_EPOCH`, `PYTHONHASHSEED=0`, UTC/C locale, umask
`022`, uv `0.11.2`, an explicitly selected supported Python (`3.11`–`3.13`),
and the isolated PEP 517 backend `setuptools==83.0.0` pinned in
`pyproject.toml`. Build the wheel directly into a fresh output directory; do
not reuse `build/`, `dist/`, `*.egg-info`, a source tree, or an output directory
from another build.

```sh
test -z "$(git status --porcelain=v1 -uall)"
test "$(uv --version | cut -d' ' -f2)" = "0.11.2"
PYTHON=/absolute/path/to/python3.11  # or an exact supported 3.12/3.13 interpreter
OUT=/absolute/path/to/fresh-wheel-output
test ! -e "$OUT"
mkdir -p "$OUT"
umask 022
export SOURCE_DATE_EPOCH="$(git show -s --format=%ct HEAD)"
export PYTHONHASHSEED=0 TZ=UTC LC_ALL=C
uv build --offline --no-config --no-sources --force-pep517 --wheel \
  --clear --no-create-gitignore --python "$PYTHON" --out-dir "$OUT" .
WHEEL="$OUT/nunchi-2.0.0-py3-none-any.whl"
shasum -a 256 "$WHEEL"

python3 -m venv /tmp/nunchi-v2-clean
/tmp/nunchi-v2-clean/bin/python -m pip install --no-deps \
  "$WHEEL"
/tmp/nunchi-v2-clean/bin/nunchi probe
/tmp/nunchi-v2-clean/bin/nunchi-install probe
```

For reproducibility evidence, repeat that block from a second independent clean
checkout of the same commit, with a distinct supported Python and fresh output
directory. Require `cmp` success and identical outer wheel SHA-256, then compare
`RECORD`, ZIP member order, timestamps, modes, compression metadata, and every
decompressed member hash. Matching member contents with different wheel bytes
does not pass.

The wheel is the review subject. A source checkout on `PYTHONPATH` is not
installed-artifact evidence.

Initialize stable operator-owned directories:

```sh
nunchi-install init \
  --config-root "$NUNCHI_CONFIG_ROOT" \
  --state-root "$NUNCHI_STATE_ROOT"
nunchi-install verify --config-root "$NUNCHI_CONFIG_ROOT"
```

Both roots must be private to the operator (`0700`). Runtime journals and
markers are created `0600`. The generic installer has no repository discovery
or platform-artifact copy operations. Hermes V2 is shipped as a wheel entry
point and has a separate pinned-bundle generator described below.

## Trusted configuration

Every configured adapter uses a JSON file whose exact bytes are pinned by
`--config-sha256` or `NUNCHI_ADAPTER_CONFIG_SHA256`. The Codex runner uses
`NUNCHI_CODEX_CONFIG_SHA256`. Hermes uses profile-scoped
`NUNCHI_HERMES_V2_CONFIG_<PROFILE>` and
`NUNCHI_HERMES_V2_CONFIG_SHA256_<PROFILE>`. The profile entry contains its own
exact `path`/`sha256` pin.

Trusted configuration owns:

- exact participant, native self actor, platform, room, and continuity scope;
- participant profile and delegated attention model;
- attention suppression/recovery/margin/error policy;
- bounded retention, snapshot, age, continuation-page, continuation-handle,
  and expiry limits; every byte bound includes the referenced actor IDs and
  metadata as well as events;
- participant model or fixed Codex model/session settings;
- stable state directory and optional pinned privileged-action policy;
- native transport endpoint and credential environment-variable names.

Room text cannot supply or override any of these values.

## Shared Discord transport

Install `nunchi[mcp-discord]`, then set:

```text
NUNCHI_DISCORD_TOKEN
NUNCHI_DISCORD_PARTICIPANT_ROUTES
NUNCHI_DISCORD_OUTPUT_HMAC_KEY
NUNCHI_DISCORD_STATE_DIRECTORY
```

`NUNCHI_DISCORD_PARTICIPANT_ROUTES` is a closed JSON object such as
`{"codex":["123456789"]}`. It defines exact participant/room pairs, never a
participant-by-room cross product.

`NUNCHI_DISCORD_OUTPUT_HMAC_KEY` must be at least 32 bytes and shared only
between the host-owned participant runner and transport. Output/history tool
calls require a short-lived, exact-operation HMAC. Accepted nonces are fsynced
before native dispatch and remain replay-blocked across restart.

The transport requests message, reaction, membership, and message-content
gateway intents. Each MCP session must authenticate one exact route before it
can receive notifications or invoke tools. Notifications carry the
gateway-attested bot actor and exact target participant. The bounded queue
never replaces an accepted event. If an event or one participant delivery is
lost, a durable per-route audit is written; after restart, that route receives
an explicit continuity gap before any later event. Because gateway resume
credentials are intentionally process-local, every fresh shared or standalone
Discord process declares a source gap before it accepts post-start facts;
within-process resumable reconnects preserve their narrower attested
continuity.

Output success is target-attested. Message results must include a non-empty
native message identity for the exact room and authenticated bot and must echo
the exact submitted content plus the exact reply target or absence of one.
Reaction results must echo the exact room, target, operation, and reaction.
The Codex consumer independently rechecks those facts, JSON-RPC request
correlation, and the single MCP text result. Empty, stale, cross-bot,
wrong-content, wrong-reply, mismatched, or malformed acknowledgements are
recorded as unknown rather than sent.

`participant_timeout_seconds` is the host's total opportunity deadline despite
the compatibility name: observation packet construction, delegated attention,
the participant turn, expansion, privileged authorization, and native
transport acknowledgement all consume the same budget. A stage timeout may be
narrower, but no provider or network wait may extend the total deadline; a
late native result is recorded as `unknown` and cannot revive the opportunity.
Before any native effect, the shared host persists a participant-host
`unknown` handoff receipt. The separately owned transport stage alone may
later attest `sent`; if receipt persistence consumes the remaining deadline,
the host makes zero native calls and records a failed transport stage.

## Hermes native plugin

The same wheel exposes `nunchi-v2` in the `hermes_agent.plugins` entry-point
group and `nunchi-hermes-v2-config` as the pinned configuration generator.
Install the exact wheel into the Python environment used by Hermes, enable
`nunchi-v2`, generate one private bundle per Hermes profile/participant/room
binding, set the printed profile-scoped environment keys, and restart Hermes.

The plugin claims only configured routes after Hermes host authorization. The
bound Discord channel/thread or Telegram group/topic must be configured so
ordinary unmentioned messages reach the gateway callback; otherwise Hermes has
withheld observation before participant attention can run. Telegram topic room
IDs use `CHAT_ID:topic:TOPIC_ID`.

Keep the room mention/command-gated until the exact Hermes core artifact and
Nunchi wheel are installed, configuration is pinned, the plugin is enabled and
Hermes has restarted, and `/nunchi-v2 probe` reports `operational: true` with
the expected public artifact, host-seam, patch, interface, and aggregate config
digests. Separately inspect the private `0600` config/profile files locally and
verify their exact profile, participant, actor, room/topic, state root, and
enabled capabilities. Only then admit unmentioned room traffic. A
verified configuration failure registers a profile-wide fail-closed hook and
reports `operational: false`; admission gating also protects against an entry
point that could not be imported at all.

The plugin invokes delegated attention and the ordinary participant turn
through Hermes' host-owned structured LLM facade. Ordinary actions return
through the public route-bound delivery capability. Privileged proposals use
the shared authorization coordinator and a fixed capability-to-tool map.
Approval inspection/completion is accepted only in an authorized DM from an
exact approver actor:

```text
nunchi-v2 approvals
nunchi-v2 approve APPROVAL_CHALLENGE_ID
```

`/nunchi-v2 probe` is deliberately redacted: it reports generation,
loaded-profile count, full Nunchi package identity and version, consumed V2
interface versions, verified Hermes/patch identity, and aggregate configuration
provenance. It does not report route bindings, profile names, state paths, or
capability names. A valid installation reports generation 2 and
`v1_fallback: false`. Full commands and admission settings are in
`integrations/hermes/README.md`.

## Restart and recovery

Restart:

1. cancels active and pending conversation opportunities;
2. discards continuation handles and pending approvals;
3. retains bounded canonical observations as context only;
4. retains content-free replay reservations plus observation, receipt,
   authorization, output-nonce, and transport audits;
5. never promotes retained events into new wake work.

Corrupt or uncertain observation, receipt, authorization, nonce, session, or
continuity state fails closed. Operator recovery uses a new state directory or
an evidence-backed repair; the runtime never silently rewrites untrusted state.
Canonical delivery and event identities are fsynced to a content-free replay
reservation before mutable observation content. If the content or final audit
commit is uncertain, the event cannot wake again and coverage becomes unknown.

## Rollback

First restore mention/command-only admission for every bound room and verify
ordinary unmentioned traffic no longer reaches the participant seam. Then stop
Hermes and V2 processes before disabling the plugin or changing artifacts.
Rollback is an atomic Hermes-core/Nunchi deployment choice: do not run V1 and
V2 participants in one room/session. Retain the V2 state directory for audit,
but do not feed V2 journals to a V1 runtime. Never leave an observation-open
room with the V2 entry point absent, disabled, or non-operational.
