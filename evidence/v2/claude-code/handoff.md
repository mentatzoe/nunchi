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

---

## Attempt 3 — 2026-07-20 (rework after two remaining fail-open paths)

**Delivering lane**: `v2-claude-owner` — Station, model `claude-fable-5`.
Attempt 2 (candidate `1990129`, evidence `1c89ea5`) closed the nine named
Attempt-1 findings, but independent probes found two remaining fail-open
paths plus a directory-mode gap and an arming-instruction fix. Attempts 1 and
2 and their evidence are preserved unchanged in git history; this attempt is a
new candidate on the same branch, appended here.

### Exact candidate and commit split

- **Implementation candidate**: `651313531f19ba82683a8234bcc3c0252e67adfd`
  (descends from Attempt-2 evidence tip `1c89ea5` on branch
  `claude/claude-code-v2-integration-3ac219`). Product, patch, test, doc only.
- **Evidence-only binding**: the commit adding this Attempt-3 section (plus the
  regenerated deterministic evidence and refreshed provenance) sits on top; its
  diff from `6513135` touches only `evidence/v2/claude-code/`.

Attempt-3 changed-file inventory (implementation candidate, `1990129` →
`6513135`):

```text
M  integrations/claude-code/nunchi_claude_v2.py                 # B1,B2 fail-closed; B3 consumer dir check
M  integrations/claude-code/transport-patch/0001-allow-bot-messages-allowfrom.patch  # rebuilt
M  integrations/claude-code/transport-patch/0002-native-fact-sidecar.patch           # B3 dir validation
M  integrations/claude-code/transport-patch/README.md           # new digest + dir wording
M  integrations/claude-code/transport-patch/apply-transport-patch.sh  # new pinned PATCHED_SHA256
M  tests/v2/test_claude_code.py                                 # B1/B2/B3 adversarial regression
```

No `src/`, `schemas/`, or other lane's surface was touched; the Attempt-2
fixes that passed are unchanged.

### Corrections (integrator's required list)

| # | Required correction | Resolution | Proof |
|---|---|---|---|
| 1 | invalid policy → bound-room prompt passes un-gated; subsequent Bash allowed | Once a prompt is a recognized Discord channel event AND V2 is configured, `handle_user_prompt_submit` never returns a bare pass-through. Any config/policy/state failure records a durable degraded room-causal marker (`_record_marker_and_block`) so PreToolUse denies mapped privileged tools this session, and blocks the room delivery; if the marker cannot be recorded, it still blocks. The outer handler catches broadly so a crash cannot fail open. | `test_invalid_policy_blocks_prompt_and_denies_privileged`, `test_state_failure_blocks_prompt_fail_closed` |
| 2 | foreign-room channel event passes un-gated; subsequent privileged allowed | A foreign room for the single-room binding is **declined** (blocked) with a durable degraded marker, not passed through as operator work; the marker denies the session's mapped privileged tools, and the room-binding check denies a room-action targeting the foreign room. A healthy same-session bound-room turn is never clobbered. | `test_foreign_room_declined_and_privileged_denied`, `test_foreign_room_does_not_clobber_a_healthy_bound_turn`, `test_operator_prompts_pass_but_foreign_rooms_are_declined`; live installed probe in `installed-runtime.md` |
| 3 | sidecar dir created 0700 only when new; pre-existing 0755 unchanged; writer validates file not dir | Before every write the transport validates the containing directory is a caller-owned, non-symlink directory with mode `0700` (`nunchiSidecarDirIsSafe`), rejecting a pre-existing `0755`/`0777`/symlink/non-directory path fail-closed; the file remains created `0600`, opened `O_NOFOLLOW`, owner/regular-validated. The consumer validates the parent directory the same way (`_validate_owner_only_dir`). Directory/file mode wording corrected in `transport-patch/README.md`. | `test_group_readable_sidecar_directory_is_refused`, `test_symlinked_sidecar_directory_is_refused`; transport dir-validation asserted in `test_transport_patch_provenance_is_pinned_and_fail_closed` |
| 4 | remove unconditional old-sidecar deletion from arming instructions | The `rm -f …/nunchi-native-events.jsonl` step is removed. The hardened path is `…/nunchi-v2/native-events.jsonl` and never reuses the old file; any cleanup is left explicit and recoverable (review and move aside). | `installed-runtime.md` §Remaining operator steps; `transport-patch/README.md` |
| 5 | return Attempt-3 commits, inventory, results; do not arm host or run live scenes until Zoe approves | This section (commits, inventory, results below). No host arming or outbound live scene was run; the staged host copy was refreshed only (no `settings.json`, transport patch, or send). | this file + `verification.md` |

### Deterministic commands and results (Attempt 3)

`python3 -m unittest tests.v2.test_claude_code` → 52 OK; the four-module guard
run → 74 OK; full baseline `python3 -m unittest` → **1173 OK (skipped=7)**;
`python3 scripts/check_governance.py --check-cli` → OK;
`PYTHONPATH=src:. python3 -m evals.v2.claude_code.run_scenes --out-dir <tmp>`
→ 20 rows (19 PASS, 1 declared limitation), byte-identical across runs;
`git diff --check` → clean. Full table in `verification.md`.

### Transport and installed provenance (Attempt 3)

- Pinned base `c3c79c65…`; patched result **`0d1ffaa0c51e60b09646e9e78ff92820f375695c0dbeac59f5393e6367b43b4c`** (base + `0001` + `0002` with directory-safety validation; reproducible, transpiles clean under `bun build`).
- Installed hook `nunchi_claude_v2.py` digest `e2bd2202…`; runtime manifest
  `62746431…` at source commit `651313531f19…`. Full component digests and the
  arming steps are in `installed-runtime.md` (Attempt 3). The host still runs
  the V1 registration; no arming was performed.

### Host-mutation approval still required (do not arm until Zoe approves)

The live ladder remains NOT RUN. Per the integrator, the corrected candidate
must be explicitly approved for host installation before arming. The exact
operator steps are in `installed-runtime.md` (apply the pinned `0001`+`0002`,
register the four hooks replacing the V1 entry, start a fresh session). No
`rm` cleanup is required. This lane performed no repository-external host
mutation beyond refreshing the staged (inert) copy, and ran no outbound
Discord send.

### Known limitations and rejected claims (Attempt 3)

Unchanged from Attempt 2. **Rejected claim**: "live parity is proven" — it is
not; live scenes are pending Zoe's explicit approval to arm the host.

**Handoff target**: `v2-integrator` for adversarial re-review (the exact prior
probes plus the prior rejection suite). This lane does not self-declare
acceptance.

---

## Attempt 4 — 2026-07-21 (rework: wrapper process-boundary fail-open)

**Delivering lane**: `v2-claude-owner` — Station, model `claude-fable-5`.
Attempt 3 (candidate `6513135`, evidence `c3442d7`) closed the four required
corrections and passed independent re-review, but one bounded process-boundary
blocker remained: the shell wrapper converted a configured
`user-prompt-submit` gate failure into a silent `exit 0`. Attempts 1–3 and
their evidence are preserved unchanged in git history; this attempt is a new
candidate on the same branch, appended here. The Attempt-3 corrections
themselves are unchanged and were not revisited.

### Exact candidate and commit split

- **Implementation candidate**: `a6a7a8be8af1bf1e55f84113bc6db7e7a686c3fb`
  (descends from Attempt-3 evidence tip `c3442d7` on branch
  `claude/claude-code-v2-integration-3ac219`).
- **Evidence-only binding**: the commit adding this Attempt-4 section (plus
  refreshed provenance) sits on top; its diff from `a6a7a8b` touches only
  `evidence/v2/claude-code/`.

Attempt-4 changed-file inventory (implementation candidate, `6513135` →
`a6a7a8b`):

```text
M  integrations/claude-code/README.md               # wrapper role description
M  integrations/claude-code/nunchi-claude-v2-hook.sh # fail-closed on gate failure
A  tests/test_claude_code_hook_wrapper.py            # subprocess fault injection
```

No other file changed. `nunchi_claude_v2.py`, both transport patches, the
installer, and the Attempt-1/2/3 test files are byte-identical to Attempt 3.

### Correction (integrator's single required item)

| Required correction | Resolution | Proof |
|---|---|---|
| a configured `user-prompt-submit` wrapper failure (missing python3, missing gate, import/startup failure, signal/nonzero exit) must block, not succeed | The wrapper now captures the gate's stdout and, on any nonzero exit (crash, syntax error, missing file, missing `python3`, killed by signal), emits `{"decision": "block", "reason": "nunchi-v2 gate unavailable; failing closed. Fix the gate or unset NUNCHI_CLAUDE_V2_POLICY to bypass."}` instead of exiting silently. A healthy gate's own decision passes through unmodified. `stop`/`post-tool` keep their deliberate fail-open direction (unchanged per the integrator's instruction); `pre-tool` keeps exit-2 fail-closed; unconfigured installs remain fully inert. | `tests/test_claude_code_hook_wrapper.py` (11 subprocess tests against the real wrapper: syntax error, missing file, killed-by-signal, missing `python3`, nonzero-exit-with-plausible-stdout, healthy passthrough, unconfigured fail-open, and the pre-tool/stop/post-tool direction controls) + a live installed-host fault-injection probe (below) |

### Deterministic commands and results (Attempt 4)

`python3 -m unittest tests.test_claude_code_hook_wrapper` → 11 OK;
`python3 -m unittest tests.v2.test_claude_code` → 52 OK; the five-module guard
run (`test_no_home_writes`, `test_sentinel_forgery`, `test_no_second_judgment`,
`test_claude_code`, `test_claude_code_hook_wrapper`) → 85 OK; full baseline
`python3 -m unittest` → **1184 OK (skipped=7)**;
`python3 scripts/check_governance.py --check-cli` → OK; scene replay → 20 rows
(19 PASS, 1 declared), byte-identical across runs (the wrapper fix does not
touch scene mechanics); patch reproducibility unchanged (`0d1ffaa0…`, this
attempt touches no `.ts` or patch file); `git diff --check` → clean. Full
table in `verification.md`.

### Installed provenance and live fault-injection probe (Attempt 4)

Staged wrapper digest `39988bfe3b8184fa077c95fa054c3bbaef785a62475b5ca3503be5f6baea2cbf`
(the Python gate `nunchi_claude_v2.py`, digest `e2bd2202…`, is unchanged since
Attempt 3). With the installed wrapper live, `nunchi_claude_v2.py` was
temporarily replaced with a syntax-broken file, a bound-room channel prompt
was submitted, and the installed wrapper produced the block decision above
(exit 0, stdout carrying the block JSON, stderr carrying the Python traceback
and the wrapper's own diagnostic) — the prompt was never admitted. The gate
file was restored immediately and its SHA-256 re-verified to match the
pre-probe digest exactly, so the probe left no drift in the staged install.
Full digests and the probe transcript are in `installed-runtime.md`. This
probe exercised only the staged (inert) components; no `settings.json` edit,
no transport patch application, and no outbound Discord send occurred.

### Host-mutation approval still required (do not arm until Zoe approves)

Unchanged from Attempt 3: the live ladder remains NOT RUN pending Zoe's
explicit approval to arm the host. The operator steps are unchanged
(`installed-runtime.md`).

### Known limitations and rejected claims (Attempt 4)

Unchanged from Attempt 3. **Rejected claim**: "live parity is proven" — it is
not; live scenes are pending Zoe's explicit approval to arm the host.

**Handoff target**: `v2-integrator` for adversarial re-review (the wrapper
fault injection, the prior Attempt-3 probes, focused/full tests, scenes,
patch reproduction, and installed-digest comparison). This lane does not
self-declare acceptance.

---

## Attempt 5 — 2026-07-21 (rework: empty/truncated gate file no longer silently admits)

**Delivering lane**: `v2-claude-owner` — Station, model `claude-fable-5`.
Attempt 4 (candidate `a6a7a8b`, evidence `9cbc18d`) fixed the wrapper's
crash/nonzero-exit handling, but Codex/Vigil's independent review found a
distinct, exit-status-invisible failure mode: a configured, existing-but-
empty/truncated gate FILE executes cleanly under `python3` (no syntax error,
exit 0, zero bytes of stdout), which the Attempt-4 wrapper still forwarded as
silent admission. Reproduced by Codex against `9cbc18d`
(`[N2-CLAUDE-A4-REWORK-01]`): `exit=0 stdout_bytes=0`. Attempts 1–4 and their
evidence are preserved unchanged in git history; this attempt is a new
candidate on the same branch, appended here.

### Exact candidate and commit split

- **Implementation candidate**: `f6c34d12af907bad114ebceda6b1f52c0c026665`
  (descends from Attempt-4 evidence tip `9cbc18d` on branch
  `claude/claude-code-v2-integration-3ac219`).
- **Evidence-only binding**: the commit adding this Attempt-5 section (plus
  refreshed provenance) sits on top; its diff from `f6c34d1` touches only
  `evidence/v2/claude-code/`.

Attempt-5 changed-file inventory (implementation candidate, `9cbc18d` →
`f6c34d1`, the immediate parent — not `a6a7a8b`, which would also show the
intervening Attempt-4 evidence commit's changes):

```text
M  integrations/claude-code/nunchi-claude-v2-hook.sh   # non-empty/brace-wrapped stdout required
M  integrations/claude-code/nunchi_claude_v2.py        # _explicit_allow for the operator-prompt path
M  tests/test_claude_code_hook_wrapper.py              # empty/truncated/malformed regressions + oracle fix
M  tests/v2/test_claude_code.py                        # one assertion updated to the new inert-allow shape
```

No `src/`, `schemas/`, transport patches, or other lane's surface changed.

### Correction (integrator's single required item)

| Required correction | Resolution | Proof |
|---|---|---|
| a configured, empty/truncated gate file that exits 0 with zero bytes admits a bound-room prompt; the test oracle's prose was also inverted for this case | Traced every configured `user-prompt-submit` code path: the **only** legitimate exit-0-empty-output case was a plain operator (non-channel-tagged) prompt while configured — every other path already returned a real decision. Added `_explicit_allow()` (Python) so that path now emits a non-empty, semantically inert `hookSpecificOutput` with an empty `additionalContext` instead of nothing. With that gap closed, a real gate can never legitimately produce empty output for a configured `user-prompt-submit`, so the wrapper now requires non-empty, brace-wrapped stdout at exit 0 for that event and treats empty/malformed output exactly like a crash. Corrected `_cannot_be_interpreted_as_admission`'s inverted semantics: empty stdout at exit 0 **is** an implicit allow per Claude Code's actual contract — that was the exact gap the defect exploited, not a safe case. | `tests/test_claude_code_hook_wrapper.py`: `test_empty_gate_file_blocks_not_admits`, `test_truncated_gate_file_blocks_not_admits`, `test_gate_exits_zero_with_malformed_output_blocks`, `test_gate_exits_zero_with_truncated_json_blocks`, `test_healthy_configured_operator_prompt_gets_explicit_non_empty_allow`, `test_healthy_room_wake_through_real_gate_and_wrapper`, `test_healthy_room_block_through_real_gate_and_wrapper`, `UnconfiguredInertAcrossAllHookEventsCase` (all four hook events) + a live installed-host reproduction of the exact reported scenario (below) |

### Deterministic commands and results (Attempt 5)

`python3 -m unittest tests.test_claude_code_hook_wrapper` → **22 OK** (11 new);
`python3 -m unittest tests.v2.test_claude_code` → 52 OK; the five-module guard
run → **96 OK**; full baseline `python3 -m unittest` → **1195 OK (skipped=7)**;
`python3 scripts/check_governance.py --check-cli` → OK; scene replay → 20 rows
(19 PASS, 1 declared), byte-identical across runs (gate/wrapper fix does not
touch attention/scene mechanics); patch reproducibility unchanged (`0d1ffaa0…`
— this attempt touches no `.ts` or patch file); `git diff --check` → clean.
Full table in `verification.md`.

### Installed provenance and live fault-injection probe (Attempt 5)

Staged gate digest `398dff634429bfbd25dd1ae525cb05af1aa95b0e5f7b3e59897f39cace08a9eb`,
wrapper digest `563423ef1e7d16489170ade417ec0b57059924d24eeb6eb0a1d88099db23e89f`.
With the installed wrapper live, `nunchi_claude_v2.py` was temporarily
replaced with a genuinely empty (zero-byte) file — the exact reported
reproduction — a bound-room channel prompt was submitted, and the installed
wrapper produced the block decision with `gate produced empty or malformed
output` on stderr — the prompt was never admitted. The gate file was then
restored and its SHA-256 re-verified to match the pre-probe digest exactly,
so the probe left no drift in the staged install. Full digests and the probe
transcript are in `installed-runtime.md`.

### Host-mutation approval still required (do not arm until Zoe approves)

Unchanged: the live ladder remains NOT RUN pending Zoe's explicit approval to
arm the host. The operator steps are unchanged (`installed-runtime.md`). This
lane performed no repository-external host mutation beyond refreshing the
staged (inert) copy and the one restore-verified fault-injection probe; no
`settings.json` edit, no transport patch application, no outbound Discord
send beyond textual status replies.

### Known limitations and rejected claims (Attempt 5)

Unchanged from Attempt 4. **Rejected claim**: "live parity is proven" — it is
not; live scenes are pending Zoe's explicit approval to arm the host.

**Handoff target**: `v2-integrator` for adversarial re-review (the exact
prior probes plus this new fault-injection scenario). This lane does not
self-declare acceptance.

---

## Attempt 6 — 2026-07-21 (rework: strict JSON validation + arming-ladder correction)

**Delivering lane**: `v2-claude-owner` — Station, model `claude-fable-5`.
Attempt 5 (candidate `f6c34d1`, evidence `3ca8589`) closed the empty/truncated
gate defect, but exact-object adversarial re-review of that exact candidate
found two further HIGH blockers: the brace-check was too loose, and the
documented arming ladder would fail immediately on this specific host.
Attempts 1–5 and their evidence are preserved unchanged in git history; this
attempt is a new candidate on the same branch, appended here.

### Exact candidate and commit split

- **Implementation candidate**: `4ca9d8bbb6fc40c33b9fc54a7dd027922472994e`
  (descends from Attempt-5 evidence tip `3ca8589` on branch
  `claude/claude-code-v2-integration-3ac219`).
- **Evidence-only binding**: the commit adding this Attempt-6 section (plus
  refreshed provenance and the arming-ladder correction) sits on top; its
  diff from `4ca9d8b` touches only `evidence/v2/claude-code/`.

Attempt-6 changed-file inventory (implementation candidate, `3ca8589` →
`4ca9d8b`, the immediate parent):

```text
M  integrations/claude-code/nunchi-claude-v2-hook.sh   # strict JSON validation
M  tests/test_claude_code_hook_wrapper.py              # StrictOutputValidationCases
```

`nunchi_claude_v2.py` (the Python gate) is unchanged since Attempt 5; the
transport patches are unchanged since Attempt 3. No `src/`, `schemas/`, or
other lane's surface changed.

### First correction — HIGH: brace-wrapping is not proof of a valid decision

| Required correction | Resolution | Proof |
|---|---|---|
| the Attempt-5 wrapper only checked `{`…`}` shell pattern-matching; `{not-json}`, `{"decision":"allow"}`, and duplicate-key `{"decision":"block","reason":"","decision":"allow"}` all pass that check and were forwarded unchanged at exit 0 | The wrapper now pipes stdout through a `python3 -c` validator that parses strictly (`object_pairs_hook` rejects duplicate keys; `parse_constant` rejects `NaN`/`Infinity`/`-Infinity`) and accepts **only** an exact match, by key set and type, against the gate's two owned output shapes: `{"decision": "block", "reason": <str>}` or `{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": <str>}}`. Every other configured `user-prompt-submit` path already emits one of those two exact shapes (confirmed by code trace, unchanged since Attempt 5), so anything else — invalid JSON, an unsupported decision value, duplicate keys, an unrecognized shape, missing/extra keys, wrong types, wrong event name, non-finite constants — is treated exactly like a crash. | `tests/test_claude_code_hook_wrapper.py::StrictOutputValidationCases` — the exact three reported reproductions plus `{"unexpected":true}`, missing/extra keys on both shapes, wrong `reason`/`additionalContext` types, wrong `hookEventName`, and a non-finite constant, each independently proven blocked; plus two byte-for-byte pass-through controls for the exact gate-owned shapes. Live installed-host reproduction of `{"decision":"allow"}` below. |

### Second correction — HIGH: arming ladder would fail immediately on this host (REWORK-02)

The prior "Remaining operator steps" ladder applied the transport patch
directly. On this exact host that fails immediately: the installed
`server.ts` (`b025d1c2…`) is neither the pinned base (`c3c79c65…`) nor the
pinned patched result (`0d1ffaa0…`) — it is a historical, functionally
partial hand-patch predating this packet — so `apply-transport-patch.sh`'s
own fail-closed check refuses it (`UNRECOGNIZED`, exit 2) before ever
touching it. **Independently re-confirmed live and read-only this session**
(no host mutation performed): `--verify` against the installed file exits
`2` `UNRECOGNIZED` with digest `b025d1c2…`, exactly matching Codex's
finding; the pristine backup `server.ts.orig-0.0.4` exists, is a
caller-owned regular file, and matches the pinned base digest `c3c79c65…`
exactly, so `--rollback` will succeed. `installed-runtime.md`'s ladder is
corrected to `--rollback` first, `--verify` (expect exit 1, pristine),
apply, `--verify` (expect exit 0, `0d1ffaa0…`), then settings/restart, with
the observed/expected digest transition recorded (`b025d1c2…` →
`c3c79c65…` → `0d1ffaa0…`). **No rollback or apply was performed** — both
confirmation checks are read-only.

### Deterministic commands and results (Attempt 6)

`python3 -m unittest tests.test_claude_code_hook_wrapper` → **36 OK** (14
new); `python3 -m unittest tests.v2.test_claude_code` → 52 OK; the
five-module guard run → **110 OK**; full baseline `python3 -m unittest` →
**1209 OK (skipped=7)**; `python3 scripts/check_governance.py --check-cli` →
OK; scene replay → 20 rows (19 PASS, 1 declared), byte-identical across
runs; patch reproducibility unchanged (`0d1ffaa0…` — this attempt touches
no `.ts` or patch file); `git diff --check` → clean. Full table in
`verification.md`.

### Installed provenance and live fault-injection probes (Attempt 6)

Staged wrapper digest
`5443e928575e9832255d3fb53712a08130b7f2b37e05fc0552b08335d6b98feb` (gate
digest unchanged at `398dff63…`). With the installed wrapper live,
`nunchi_claude_v2.py` was temporarily replaced with a stub emitting the
well-formed but unsupported `{"decision":"allow"}` — a bound-room channel
prompt was submitted, and the installed wrapper produced the fail-closed
block decision; the forged allow was never forwarded. The gate file was
restored and its SHA-256 re-verified to match the pre-probe digest exactly.
Separately, `apply-transport-patch.sh --verify` (read-only) was re-run
against the installed plugin and independently confirmed exit `2`
`UNRECOGNIZED` at `b025d1c2…`, and the pristine backup was confirmed
(read-only) to match `c3c79c65…` exactly. Full digests and transcripts are
in `installed-runtime.md`.

### Host-mutation approval still required (do not arm until Zoe approves)

Unchanged: the live ladder remains NOT RUN pending Zoe's explicit approval
to arm the host. The corrected operator steps are in `installed-runtime.md`.
This lane performed no repository-external host mutation beyond refreshing
the staged (inert) copy and two restore-verified fault-injection probes,
plus two read-only transport-patch confirmation checks; no `settings.json`
edit, no `--rollback`, no patch application, no outbound Discord send
beyond textual status replies.

### Known limitations and rejected claims (Attempt 6)

Unchanged from Attempt 5. **Rejected claim**: "live parity is proven" — it
is not; live scenes are pending Zoe's explicit approval to arm the host.

**Handoff target**: `v2-integrator` for adversarial re-review (the exact
prior probes plus these two new scenarios). This lane does not
self-declare acceptance.
