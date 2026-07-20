# Claude Code V2 integration — proposed packet input

Append-only. This file is the packet input defined by the intake contract in
`docs/INSTALL.md` (§Packet intake contract) and by the commissioned goal of
2026-07-20. It proposes; it does not accept. Acceptance is the
`v2-integrator`'s separate adversarial act, and no lifecycle state is claimed
here.

---

## Attempt 1 — 2026-07-20

**Delivering lane**: `v2-claude-owner` — Station
(evidence/governance/assignments/station-v2-claude-owner-2026-07-16.md),
standing Claude Code agent, model `claude-fable-5`.

**Commissioned by**: Zoe's 2026-07-20 direct goal (implement and hand off the
complete Claude Code V2 integration packet against integration base
`a03eeb95c7d569895e1171993c7a5748fc250bd8`), following Zoe's 2026-07-19
freeze-and-third-party decision recorded live in the coordination room
(message `1528454164726681751`). Program implementation authority:
`evidence/governance/v2-implementation-authorization.md` (AUTHORIZED,
all eleven slices, Zoe, 2026-07-16).

**Lifecycle honesty**: the bound slice-070 activation prerequisites
(accepted `010`–`050` handoffs) are not satisfiable at this base — slices
`040`/`050` have no handoff evidence; their behavior was implemented directly
on the integration branch. This packet therefore follows the external packet
intake contract, not the slice activation path, and asserts no slice state
transition. The integrator may fold it into whichever lifecycle
reconciliation the program adopts.

### 1. Exact candidate commit and changed-file inventory

- **Base**: `a03eeb95c7d569895e1171993c7a5748fc250bd8`
  (`codex/v2-integration`)
- **Branch**: `claude/claude-code-v2-integration-3ac219`
- **Candidate commit**: recorded in the addendum at the end of this file
  (the candidate cannot contain its own hash); the addendum commit on top is
  docs/evidence-only.

Complete inventory, base → candidate:

```text
A  docs/integrations/claude-code-v2.md
A  evals/v2/claude_code/__init__.py
A  evals/v2/claude_code/recovery.jsonl
A  evals/v2/claude_code/run_scenes.py
A  evals/v2/claude_code/scenes.jsonl
A  evidence/v2/claude-code/handoff.md
A  evidence/v2/claude-code/installed-runtime.md
A  evidence/v2/claude-code/manifest.json
A  evidence/v2/claude-code/reactive-bot-hearing.jsonl
A  evidence/v2/claude-code/scene-results.jsonl
A  evidence/v2/claude-code/verification.md
M  integrations/claude-code/DEFER_EVAL.md
M  integrations/claude-code/README.md
A  integrations/claude-code/nunchi-claude-v2-hook.sh
A  integrations/claude-code/nunchi-claude-v2-tools.example.json
A  integrations/claude-code/nunchi-claude-v2.env.example
D  integrations/claude-code/nunchi-gate.env.example
A  integrations/claude-code/nunchi_claude_v2.py
D  integrations/claude-code/nunchi_prompt_gate.py
M  integrations/claude-code/transport-patch/0001-allow-bot-messages-allowfrom.patch
A  integrations/claude-code/transport-patch/0002-native-fact-sidecar.patch
M  integrations/claude-code/transport-patch/README.md
A  integrations/claude-code/transport-patch/apply-transport-patch.sh
A  tests/fixtures/v2/claude_code/native_events.json
D  tests/test_claude_code_prompt_gate.py
D  tests/test_defer.py
M  tests/test_no_home_writes.py
M  tests/test_sentinel_forgery.py
A  tests/v2/claude_code_helpers.py
A  tests/v2/test_claude_code.py
```

No file outside these paths changed. No `src/`, `schemas/`, or other lane's
surface was modified; the V1-test removals (`test_defer.py`,
`test_claude_code_prompt_gate.py`) and the guard-test rewires
(`test_no_home_writes.py`, `test_sentinel_forgery.py`) are Claude-lane test
surfaces for the removed V1 gate.

### 2. Exact consumed interface versions

| Interface | Version | Consumed through |
|---|---|---|
| `I-010A AttentionRequestV2` | `@1` | `nunchi.observation.ObservationProvider.snapshot` / `participant_snapshot` |
| `I-010B AttentionDecisionV2` | `@2` | `nunchi.core.evaluate_v2` |
| `I-010C ParticipantWakeV2` | `@1` | `nunchi.participant.build_participant_wake` |
| `I-010D ContextContinuationV2` | `@1` | not offered by this surface (declared honestly; native `fetch_messages` history remains the participant's in-turn tool) |
| `I-010E AttentionReceiptV2` | `@2` | canonical stage writers + `nunchi.receipts` sinks |
| `I-010F PrivilegedActionAuthorizationV2` | `@2` (schema_version 2 request/decision) | `nunchi.authorization.PrivilegedActionGuard` |
| `I-020A ObservationProviderV2` | `@1` | `nunchi.observation.ObservationProvider` |
| `I-030A AttentionEngineV2` | `@1` | `nunchi.core.evaluate_v2` — exactly one call per ordinary opportunity; zero classifier calls on trusted bypass |
| `I-040A ParticipantTurnHostV2` | `@1` | `nunchi.participant.run_participant_turn` |
| `I-040B PrivilegedActionGuardV2` | `@1` | `nunchi.authorization.PrivilegedActionGuard` / `ReloadingPolicyAuthorizationSink` |
| `I-040C ConversationOpportunitySchedulerV2` | `@1` | `nunchi.scheduling.ConversationOpportunityScheduler` (semantic state persisted per Claude session generation; restart drops pending work per contract) |
| `I-050A DiscordEventSourceV2` | `@1` | `nunchi.mcp_discord.events.DiscordEventSourceV2.native_input` — the sole native→canonical mapping |

No schema is copied or redefined; no new public interface is produced.

### 3. Native mapping, self binding, restart coverage, unavailable facts

- **Native→canonical**: patched-plugin delivery (channel tag + transport
  native-fact sidecar) → `MessageEvent` → `DiscordEventSourceV2.native_input`
  → `ObservationProvider.ingest`. One consumer-side honesty adjustment is
  documented in `nunchi_claude_v2.py`: when the transport cannot attest the
  author's bot flag (sidecar record absent) the event is **unroutable**, and
  identity is never inferred from display names.
- **Exact self**: configured native user ID `1484970897893752902`
  (`NUNCHI_CLAUDE_V2_SELF_USER_ID`); `Station`/`Fable` and the V1 alias list
  are loose evidence only. Context handles/rooms bind exactly
  (`discord:channel:1522258711047831653` scope).
- **Restart/history**: retained event log is restart-safe for previously
  delivered events; pending coalesced anchors drop on session restart
  (I-040C contract); `has_restart_gap=true`; event visibility
  `message=live-only`, `reaction=unavailable`, `membership=unavailable`.
- **Honestly unavailable native facts**: reply-referenced author/content
  (only the referenced message ID is transport-known); reactions; membership
  events; guild member roster; events arriving while no session is live
  (cold wake); thread roots (not exposed by this delivery path).

### 4. Configuration, process boundary, install/upgrade, privileged seams

- **Configuration boundary**: trusted operator policy JSON (canonical shape;
  budgets, margin+provenance, bypass, error action, grants, receipt sink) +
  `NUNCHI_CLAUDE_V2_*` env file + deterministic tools map. Nothing is
  configurable from room content or model output; no credential is required
  for the shipped trusted-bypass posture, and the classifier credential
  (when the operator provisions it) lives only in the owner-only policy file.
- **Executable/process boundary**: plugin transport runs under `bun` as the
  session's MCP server; the gate runs as short-lived `python3` hook processes
  over an owner-only locked state dir; receipts/audits are exclusive-create
  owner-only files.
- **Installation/upgrade/rollback**: `installed-runtime.md` records the
  staged install, digests, and the exact remaining operator arming steps;
  patch application is digest-pinned fail-closed with pristine-base backup
  and `--rollback`.
- **Privileged seams Nunchi can enforce**: any tool named in the operator
  tools map, during room-caused turns, via PreToolUse → `I-040B` with the
  requester derived from the transport-attested origin event. Shipped live
  posture: `Bash`/`Write`/`Edit`/`NotebookEdit` privileged with an empty
  grant list → deny-by-default.
- **Unenforced paths (reported, not claimed safe)**: tools not named in the
  map; sessions with hooks disabled or the settings entry removed; harness
  features that execute without PreToolUse; background processes spawned by
  a previously allowed action; operator-typed (non-room) turns are
  deliberately out of guard scope; and a TOCTOU window between the hook
  decision and host execution (the guard's execute-time recheck cannot wrap
  the host's own tool runner).

### 5. Deterministic reproduction commands and results

See `verification.md` for the exact command/result table:
full baseline `python3 -m unittest` → 1155 OK; slice suite 34 OK; guard
suites 56 OK; governance OK; scene replay 20 rows (19 PASS, 1 declared
limitation). Covered: `SUPPRESS`, `WAKE`, classifier-`DEFER`,
margin-`DEFER`, trusted bypass (zero classifier calls), operational-error
recovery (WAKE fallback and `NO_WAKE`), direct act-or-silence, replies,
mentions, burst coalescing, later hearing, restart without wake replay, and
unauthorized/approval-bound privileged proposals.

### 6. Live evidence

Provided: installed-host provenance and two installed-hook probes
(`installed-runtime.md`), including the live fail-closed unroutable
quarantine for the patch-drift condition. **Not run**: all room-live scenes
(reactive delivery, other-bot hearing, delayed-turn freshness with
intervening events, live silence, live send, restart-without-replay), each
with its exact blocker recorded in `verification.md` §Blocked live scenes —
this session's permission boundary correctly refused transport
self-modification, settings modification, and outbound sends, and no
authorized non-self sender was active during the frozen workstream. The
first operator-armed session runs the full live ladder and appends rows
without rewriting this attempt.

### 7. Known limitations and rejected claims

- Cold wake unsupported; session restart drops pending wake work; an
  interrupted turn's participant-host stage stays absent (no fabrication).
- One room binding per installation; other channels pass through un-gated
  (documented; multi-room is future work).
- Concurrent Claude sessions sharing the state dir serialize through the
  state lock, but multiple live gateway sessions of the same bot account
  can each receive deliveries; only hook-registered sessions gate them.
- `transition_defer_margin=0.12` is provenance-recorded but uncalibrated
  (`DEFER_EVAL.md` plan).
- I-010D continuation handles are not offered by this surface.
- The transport-stage record for Claude sends attests only what PostToolUse
  observed of this integration's own turn; sends made outside a room-caused
  turn are not receipted.
- **Rejected claim**: "the packet's live parity is proven" — it is not; live
  scenes are pending operator arming as itemized above. **Rejected claim**:
  "the host is running V2" — the host still runs the V1 registration until
  the operator completes the arming steps.

### Documentation dispositions (freshness inputs)

| Path | Disposition | Validation / exact delta |
|---|---|---|
| `docs/integrations/claude-code-v2.md` | `UPDATE` (new) | Links resolve; lifecycle/mermaid matches implementation; reviewed against `nunchi_claude_v2.py` behavior |
| `integrations/claude-code/README.md` | `UPDATE` | Install/verify commands executed this session (staged install + probes); limitations verified against code |
| `integrations/claude-code/DEFER_EVAL.md` | `UPDATE` | Dual-DEFER semantics verified by `test_classifier_defer_and_margin_defer_route_distinctly` |
| `integrations/claude-code/transport-patch/README.md` | `UPDATE` | Digests verified by scratch rebuild (`BOTH APPLY CLEAN`, result `e26b6d23…`) |
| `README.md` | `HANDOFF` → `v2-integrator` | Replace the V1 Claude claims: Claude Code arrives as this V2 packet (reactive single-judgment lifecycle, trusted-bypass live posture, staged install, deterministic-complete/live-pending evidence grade, cold-wake and single-room limits) |
| `CHANGELOG.md` | `HANDOFF` → `v2-integrator` | Add the breaking Claude V1→V2 replacement entry (V1 gate and tests removed; V2 hooks; patches 0001/0002) at cutover |
| `docs/INSTALL.md` | `HANDOFF` → `v2-integrator` | On acceptance, unblock `nunchi-install` for this packet's file inventory and registration snippet |
| `docs/adapters.md` | `HANDOFF` → `v2-integrator` | Claude row: "Awaiting accepted Claude V2 packet" → this packet's exact state at acceptance |
| `docs/integration.md` | `HANDOFF` → `v2-integrator` | Claude arrives as accepted V2 packet (this one) at acceptance |
| `docs/architecture/v2-selected-design.md` | `HANDOFF` → `v2-integrator` | Wave-3 070 status delta at acceptance |

Reviewer for the `UPDATE` rows: the delivering lane (behavior-vs-doc check
recorded above); shared `HANDOFF` rows name `v2-integrator` as accepting
owner with the exact deltas listed.

**Handoff target**: `v2-integrator` (and `v2-security-owner` for slice-100
consumption) for adversarial review per `docs/INSTALL.md`: inspect the diff,
rerun the packet commands, run the shared deterministic suite, build/install
the wheel, compare installed inventory, and exercise the mixed-room ladder.
This lane does not self-declare acceptance.

---

## Addendum — exact candidate binding (2026-07-20)

**Candidate commit**: `6476b58ca015e259fa576fd8f9ed569adc0c6913`
(descends from base `a03eeb95c7d569895e1171993c7a5748fc250bd8` on branch
`claude/claude-code-v2-integration-3ac219`; intermediate lineage
`ef7c2cc` implementation → `4e46b39` documentation → `6476b58` evidence).

This addendum commit is docs/evidence-only: its diff from the candidate
touches only `evidence/v2/claude-code/`. Verify with:

```sh
git diff --name-only 6476b58ca015e259fa576fd8f9ed569adc0c6913..HEAD
python3 -m unittest            # 1155 tests OK (skipped=7) at the candidate
python3 scripts/check_governance.py --check-cli
```

---

## Attempt 2 — 2026-07-20 (rework after adversarial rejection)

**Delivering lane**: `v2-claude-owner` — Station, model `claude-fable-5`.
Attempt 1 (candidate `6476b58`) was reviewed and **rejected** by the
`v2-integrator` with nine blocking findings and a required adversarial
regression suite. Attempt 1 and its evidence are preserved unchanged in git
history at `6476b58`; this attempt is a new candidate on the same branch.

### Exact candidate and commit split

- **Implementation candidate**: `199012901278777750671f4fc0731b779e91c2b8`
  (descends from Attempt-1 tip `69e255b` on branch
  `claude/claude-code-v2-integration-3ac219`). It contains only product,
  test, patch, and doc changes.
- **Evidence-only binding**: the commit that adds this Attempt-2 section (plus
  the regenerated deterministic evidence and updated provenance) sits on top
  of the implementation candidate; its diff from `1990129` touches only
  `evidence/v2/claude-code/`.

Attempt-2 changed-file inventory (implementation candidate, `6476b58` →
`1990129`; the Attempt-1 base inventory in Attempt 1 above is otherwise
unchanged):

```text
M  evals/v2/claude_code/run_scenes.py                         # reproducible rows
M  integrations/claude-code/nunchi-claude-v2.env.example      # owner-only sidecar path
M  integrations/claude-code/nunchi_claude_v2.py               # F1–F5 fixes
A  integrations/claude-code/transport-patch/.gitattributes    # F9 git diff --check
M  integrations/claude-code/transport-patch/0001-allow-bot-messages-allowfrom.patch
M  integrations/claude-code/transport-patch/0002-native-fact-sidecar.patch   # F4,F5
M  integrations/claude-code/transport-patch/README.md         # new digest + safety
M  integrations/claude-code/transport-patch/apply-transport-patch.sh  # F6
M  tests/v2/claude_code_helpers.py                            # 0600 sidecar fixtures
M  tests/v2/test_claude_code.py                               # adversarial regression
```

### Finding-by-finding disposition

| # | Finding | Resolution | Proof |
|---|---|---|---|
| 1 | operational-error wakes without a room-causal record → PreToolUse treats tools as operator | `start_degraded_turn` records a confined, transport-attested (`anchor_event_id`) room-causal turn with no snapshot; `PreToolUse` denies privileged effects on any room-caused turn | `test_operational_error_wake_denies_privileged_effects` |
| 2 | `PreToolUse` only `authorize()`s; replay executes twice; audit-fail allows | Room-caused privileged execution **declared unsupported** through the advisory pre-tool seam (it cannot perform the `I-040B` execute-time policy/digest recheck or one-use consumption around the host's own tool runner) and denied fail-closed. Denial is unconditional, so replay and audit-persistence failure have zero effect. The transport-attested requester is still derived (`derive_room_requester`) for the record. | `test_room_caused_privileged_execution_is_denied_unsupported`, `test_identical_privileged_action_replay_never_executes_twice`, `test_authorization_audit_persistence_failure_has_zero_effects`, `test_requester_derivation_resolves_the_transport_attested_origin` |
| 3 | reply/react allowed before `chat_id` check → cross-room | `PreToolUse` enforces the bound room on reply/react before execution; a mismatched `chat_id` is denied | `test_cross_room_reply_is_denied_before_execution`, `test_cross_room_reaction_is_denied_before_execution`, `test_in_room_reply_is_allowed` |
| 4 | patch `0001` drops self before recording/observation | Transport records self native facts *before* the waking-path drop; the consumer syncs self records from the sidecar into observation as `SELF_RETAINED_NO_WAKE` context — retained, never a recursive wake | `test_self_event_is_retained_as_context_but_never_wakes` |
| 5 | sidecar `0644` in `0755` dir; only `msg.content`; unvalidated | Sidecar moved to an owner-only `0700` dir, created `0600`, opened `O_NOFOLLOW`, owner/regular-validated on every write; records the exact delivered content (attachment placeholders + voice transcripts); unserializable records dropped. Consumer opens no-follow/owner-validated and treats malformed/unsafe matching records as unroutable (fail-closed) | `test_malformed_sidecar_record_fails_closed`, `test_group_readable_sidecar_is_refused`, `test_symlinked_sidecar_is_refused`, `test_sidecar_default_path_is_owner_only_directory` |
| 6 | `apply-transport-patch.sh` follows symlinks | Rejects symlinked target/backup, validates owner + regular-file identity, verifies target/backup resolve inside the plugin dir, replaces atomically (sibling temp + rename); never modifies a symlink referent | `test_apply_script_rejects_symlinked_target` + scratch-build symlink probes (referent bytes unchanged) |
| 7 | live evidence absent; host on V1 | Deterministic rework complete and adversarially proven. Live scenes remain NOT RUN — see the explicit operator-arming request below. No acceptance is claimed. | `verification.md` §Blocked live scenes |
| 8 | handoff label `I-010F@2` | **Corrected**: the canonical interface is `I-010F PrivilegedActionAuthorizationV2@1`; its request/decision documents carry `schema_version: 2`. (Attempt 1's table above is preserved as written; this is the correction of record.) | registry `specs/001-nunchi-v2-program/plan.md:167` |
| 9 | evidence not reproducible; `git diff --check` | Scene evidence is byte-reproducible (run-variable request IDs and provenance digests stripped; two runs to separate temp dirs are identical). A scoped `transport-patch/.gitattributes` exempts generated patch files (whose blank-context lines are single spaces by unified-diff format), so `git diff --check` is clean. | `verification.md` command table |

### Deterministic commands and results (Attempt 2)

`python3 -m unittest tests.v2.test_claude_code` → 46 OK; the four-module guard
run → OK; full baseline `python3 -m unittest` → **1167 OK (skipped=7)**;
`python3 scripts/check_governance.py --check-cli` → OK;
`PYTHONPATH=src:. python3 -m evals.v2.claude_code.run_scenes --out-dir <tmp>`
→ 20 rows (19 PASS, 1 declared limitation), byte-identical across runs;
`git diff --check` → clean. Full table in `verification.md`.

### Interface versions (correction of record)

Unchanged from Attempt 1 except the `I-010F` label:
`I-010F PrivilegedActionAuthorizationV2@1` (documents `schema_version: 2`).
All other consumed interfaces are as listed in Attempt 1 §2.

### Transport and installed provenance (Attempt 2)

- Pinned base `c3c79c65…`; patched result **`67900f7e0275debcfd9deabb0345c92e879b25047ce00777e3fbd9552b19bd8a`** (base + `0001` + `0002`, reproducible, transpiles clean under `bun build`).
- Staged host component digests and the exact remaining operator arming steps
  are in `installed-runtime.md` (Attempt 2). The host still runs the V1
  registration until the operator arms V2.

### Explicit operator-arming request (finding 7)

The deterministic rework passes. To produce the required live evidence, the
operator (Zoe) must approve the following exact host mutations — this
autonomous session's permission boundary correctly refuses them:

1. `rm -f ~/.claude/channels/discord/nunchi-native-events.jsonl` (remove any
   world-readable Attempt-1 sidecar so the hardened writer will record).
2. `integrations/claude-code/transport-patch/apply-transport-patch.sh ~/.claude/plugins/cache/claude-plugins-official/discord/0.0.4` (apply the pinned `0001`+`0002`; fail-closed).
3. Merge `python3 integrations/claude-code/nunchi_claude_v2.py print-settings`
   into `~/.claude/settings.json`, replacing the V1 `UserPromptSubmit` entry.
4. Start a fresh Claude Code session.

Then the live ladder runs: reactive human hearing, reactive allowlisted-bot
hearing, delayed burst with intervening events → one fresh successor, live
silence, live send with receipts, cross-room rejection, privileged-action
denial, and a process-restart no-replay check. Those rows append to this
packet without rewriting any attempt.

### Known limitations and rejected claims (Attempt 2)

Unchanged from Attempt 1, plus: **room-caused privileged execution is
unsupported** through the PreToolUse advisory seam and is denied fail-closed
(the hook cannot wrap `I-040B` execute-time one-use semantics around the
host's own tool runner) — the requester derivation is correct and evidenced,
but execution enforcement is honestly declared unsupported, not claimed.
**Rejected claim**: "live parity is proven" — it is not; live scenes are
pending the operator arming above.

**Handoff target**: `v2-integrator` for adversarial re-review. This lane does
not self-declare acceptance.
