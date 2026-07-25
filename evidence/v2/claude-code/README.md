# Claude Code V2 evidence

**Surface**: Claude Code (`070`) · **Owner lane**: `v2-claude-owner`
(`evidence/governance/assignments/claude-v2-claude-owner-2026-07-24.md`)

**Status under `docs/v2-delivery.md`**: **Implemented, unverified.**

Source, deterministic, real-participant, and clean-installed-artifact checks
passed. Live real-room evidence and exact-head non-author review have **not**
been performed. This surface must not be described as Verified, live,
parity-ready, or done until both land.

## Dependency ancestry

The shared foundation this work consumes is integrated:

```sh
git merge-base --is-ancestor \
  014546d2ec685341106b177bcf2f6e52e758e0a9 \
  origin/integration/v2      # exit 0
```

## What passed

| Claim | Command | Result |
|---|---|---|
| repository suite | `python3 -m unittest` | 377 tests, OK, 4 skips (the documented `baseline-oracle-absence` skips) |
| platform conformance | `python3 -m unittest tests.v2.test_claude_code` | 52 tests, OK |
| shared owners still pass | `python3 -m unittest tests.v2.test_shared_foundation tests.v2.test_surfaces tests.v2.test_runtime_hardening` | 102 tests, OK |
| dual-validator contract corpus | `uv run --offline --isolated --no-project --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'` | 218 tests, OK, zero skips (unchanged count — the corpus did not shrink) |
| lifecycle evaluation list | `python3 -m evals.verdict_suite.runner --list` | 8 scenes listed |
| reproducible build | `uv build --wheel` twice | byte-identical wheel, SHA-256 `012f8769368025cc9706211c483811892395cae844cf51a8153f8fef9d45a2b4` |
| clean install | `uv venv` + `uv pip install ./nunchi-2.0.0-py3-none-any.whl` | installed with no editable link, no repository import, no `PYTHONPATH` |
| platform suite against the installed artifact | installed interpreter running `tests.v2.test_claude_code` | 52 tests, OK, `nunchi` resolved from `site-packages` |
| installed probes | `nunchi-claude-code-room-runner --probe` (unconfigured and configured) | see below |
| real-participant scenes | `python3 -m evals.v2.claude_code.participant_scenes` | 3/3 matched expectation (`participant-scenes-2026-07-25.json`) |

### Installed probes

```json
{"configured":false,"generation":2,"product":"nunchi","product_version":"2.0.0",
 "surface":"claude-code","v1_fallback":false}
```

```json
{"actor_id":"discord:actor:149","configured":true,"generation":2,
 "participant_id":"vigil","participant_tools_enabled":false,
 "persistent_session":true,"privileged_actions_enabled":true,"product":"nunchi",
 "product_version":"2.0.0","room_id":"152","send_time_social_judgment":false,
 "shared_discord_transport":true,"surface":"claude-code","v1_fallback":false}
```

The installed runner refused, with exit `3`, each of: a tampered config digest
(`adapter config bytes do not match trusted sha256 pin`), a swapped participant
profile (`participant profile digest does not match trusted configuration`),
and an output key the participant turn could read (`Claude Code transport
output key must not be readable by the participant turn`).

### Real-participant scenes

`evals/v2/claude_code/participant_scenes.py` runs the **real** `claude` binary
(2.1.220) as the participant through the real `ClaudeCodeRoomRuntime`. The
Discord transport is a recording double, so this is **not** live-room evidence.
It establishes what a stub cannot:

- a real headless turn, with exactly the shipped flags and prompts, returned
  exactly one valid V2 action envelope — never a relevance verdict, an
  admission meta-answer, or prose;
- **profile sensitivity with room facts held constant**: the identical open
  room moment produced silence under quiet instructions and a warm
  contribution under sociable instructions;
- silence made zero outbound calls and ended its receipt stream at
  `participant-host` with outcome `silent`, distinct from model suppression
  (which ends at `attention`) and from a contribution (`participant-host`
  `unknown`, then `transport` `sent`).

### Tool-lockdown differential (real CLI)

The "the participant has no tools" claim was checked against the real binary
with a canary file, holding the prompt and the file constant and varying only
the tool flag:

| Invocation | Outcome |
|---|---|
| shipped isolation (`--tools ""`, `--strict-mcp-config`, empty MCP map, `--setting-sources ""`, `--permission-mode manual`) | no tool call, no `permission_denials`, canary **not** present in the result |
| control (`--tools "Read" --permission-mode acceptEdits --add-dir /tmp`) | canary **present** in the result |

The control matters: without it, "the canary did not appear" would be
consistent with a model that simply chose not to answer. The differential shows
the shipped flag set is what removes the capability.

An earlier iteration of the profile-sensitivity pair used a room moment
addressed to a named third party. Both profiles correctly stayed silent, so
that pair could not distinguish a profile-sensitive participant from an
all-mute one. It was replaced with an open, unaddressed moment. The discarded
design and its result are recorded here rather than deleted.

Participant behaviour is stochastic: 3/3 is an observed outcome, not a
deterministic guarantee, and the trial counts are far below what a release
proof profile requires.

## What is NOT proven

1. **No live real-room evidence.** No native Discord ingress or egress was
   exercised: no real gateway, no real bot identity, no attributable native
   message or receipt IDs. Every transport result above came from a recording
   double. The shared Discord consumer contract is exercised only at the
   acknowledgement-shape level.
2. **No mixed-agent proof.** Installed Codex, Hermes, and Claude Code runtimes
   with distinct identities have not completed scenes together in an authorized
   real room.
3. **No independent review.** No non-author reviewer from a distinct model
   family has reviewed this exact head, and no reviewer-held challenge set
   exists for it.
4. **No attention-classifier live evidence.** The real-participant scenes run
   with pre-attention bypass. The classifier path is proven deterministically
   (fixture model) but not against a live provider on this surface.
5. **No upgrade or rollback exercise.** No supported V1 release upgrade with
   representative operator state, no hard-kill restart continuity run, and no
   rollback run were performed for this surface.
6. **No capacity, latency, or overload envelope.** Nunchi-controlled bounds
   were not fixed or measured for this surface.
7. **No release-proof profile.** No frozen input manifest, closure manifest,
   threat model, or reviewer-held challenge set exists for this candidate.
8. **Hermes remains missing**, so the program-level surface inventory is
   incomplete regardless of this surface's state.

Item 1 is blocked in this environment: no Discord remote client is reachable.
It is a real gap, not a limitation to be reinterpreted — under
`docs/v2-completion-goal.md`, missing evidence is a failure, not an exemption.

## Security properties this implementation relies on

Recorded so a reviewer can attack them directly:

- The participant subprocess runs with `--tools ""`, `--strict-mcp-config
  --mcp-config '{"mcpServers":{}}'`, `--setting-sources ""`,
  `--disable-slash-commands`, and `--permission-mode manual`. It has no path to
  Discord; the host owns the one output commit point.
- The participant environment is an explicit allowlist. The shared Discord
  output-authorization key and the classifier credential are withheld, and the
  runtime refuses to start if `output_key_env` names an allowlisted variable.
- Identity comes from the pinned, digest-verified profile via
  `--system-prompt`; room content never enters it.
- Session continuity is pinned to participant, actor, room, continuity scope,
  profile digest, and an invocation-behaviour digest. Any mismatch, and any
  answer reporting a different session, is an operational failure.
- A malformed, truncated, errored, or non-envelope turn is an operational
  failure with an `unknown` participant-host outcome — never fabricated
  silence. A turn that overruns its own budget without host cancellation is
  likewise an error, not silence.
- The single inventoried privileged effect is `workspace.file.write`, confined
  to a configured absolute root, refusing absolute paths, `..` segments,
  resolved escapes, and symlink traversal, and confirming the written bytes.
  Without a configured root the capability has no executor at all. Ordinary
  room contribution is deliberately not a privileged capability.

## Reproducing

```sh
python3 -m unittest tests.v2.test_claude_code
uv run --offline --isolated --no-project --with 'jsonschema==4.26.0' \
  python -m unittest discover -s tests/v2/contract -p 'test_*.py'

# real participant; requires an authenticated `claude` on PATH
python3 -m evals.v2.claude_code.participant_scenes
```
