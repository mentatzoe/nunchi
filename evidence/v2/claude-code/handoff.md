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

---

## Attempt 7 — 2026-07-21 (integrator live-source remediation)

The integrator armed exact Attempt-6 evidence tip `b12726b9e01739c2faf9027b6ef5038d3cd0c969`
using its documented recoverable ladder. The first real Discord delivery
then proved that Claude Code 2.1.215 emits
`source="plugin:discord:discord"`, while the packet fixture and parser used
the synthetic shorthand `source="discord"`. The native transport sidecar
was correct, but the hook returned the configured operator-prompt allow shape
before joining it. This was a live fail-open mismatch and Attempt 6 was not
accepted.

**Implementation successor**:
`7ea499be33c6260f79e10f07fe77110b147929e2` on
`claude/claude-code-v2-integration-3ac219`. It binds the exact installed host
source, treats any other visible channel envelope as a degraded blocked room
event rather than operator input, changes the deterministic fixtures to the
observed host envelope, adds both positive and fail-closed regressions, and
updates the owned docs. No shared contract or other adapter source changed.

Verification at the implementation successor:

- focused Claude/guard tests: 72 tests, OK;
- full repository suite: 1,211 tests, OK (7 skipped);
- governance boundary and exact SpecKit CLI: OK;
- live message `1528950867355635755` produced exact native event
  `discord:message:1528950867355635755`, an immutable observation receipt,
  and an attention receipt with `classifier_not_invoked=true`, cause
  `preattention-disabled`, and policy provenance; the active turn records
  `PREATTENTION_BYPASS`;
- installed gate bytes are identical to the successor source at SHA-256
`c4c55671fa41caaeaa268d98ef7d74536df44b898b5d0f8ea30cf8389a53522e`.

The installed Claude CLI received the gated context but returned the host
error `Login expired - Please run /login`. Consequently no model reply,
silence outcome, participant-host receipt, or transport receipt is claimed.
The exact installed transition and remaining live boundary are recorded in
`integrator-live-arming.md`. Attempt 7 remains **REWORK / live-pending**, not
accepted, until a freshly authenticated Claude session completes the bounded
reply, silence, privileged-denial, error-recovery, and restart scenes.

---

## Attempt 8 — 2026-07-21 (rework: strict validation, PostToolUseFailure,
atomic room-action reservation, strict receipt acks, strict tools config)

**Delivering lane**: `v2-claude-owner`, fresh Claude Code session (model
`claude-sonnet-5`), commissioned directly by Codex as the human-authorized V2
DRI to close five evidence-backed blockers identified after Attempt 7's
live-source fix (Zoe's standing instruction to finish V2 without acting as a
clipboard; this session had direct scoped implementation authority for the
Claude packet). Attempt 7 (product `7ea499b`, evidence `7e3d970`) was
REWORK, not acceptance — the host is armed with the transport and hooks, but
`integrator-live-arming.md` records only reactive transport, native identity,
observation, and trusted-bypass attention as live-proven; participant
completion remained blocked on the installed Claude CLI's expired login and
was never re-attempted this session (no host mutation was performed or
requested).

### Exact candidate

- **Implementation candidate**: `d594b29c1bca487da38f025b1a46de21c183b8f6`
  (descends from Attempt-7 evidence tip `7e3d970` on branch
  `claude/claude-code-v2-integration-3ac219`). Product, test, and owned-docs
  changes only.
- **Evidence-only binding**: this commit (adding this Attempt-8 section) sits
  on top; its diff from `d594b29` touches only `evidence/v2/claude-code/`.

Attempt-8 changed-file inventory (implementation candidate, `7e3d970` →
`d594b29`):

```text
M  docs/integrations/claude-code-v2.md
M  evals/v2/claude_code/run_scenes.py
M  integrations/claude-code/README.md
M  integrations/claude-code/nunchi-claude-v2-hook.sh
M  integrations/claude-code/nunchi_claude_v2.py
M  tests/test_claude_code_hook_wrapper.py
M  tests/v2/test_claude_code.py
```

No `src/`, `schemas/`, or other lane's surface changed; the transport patches
(`0001`/`0002`) and `nunchi_claude_v2.py`'s exact-source binding from Attempt
7 are otherwise unchanged.

### Finding-by-finding disposition

| # | Blocker (commissioned) | Resolution | Proof |
|---|---|---|---|
| 1 | Strict UTF-8/JSON parsing with duplicate-key/non-finite rejection, exact native sidecar types | `_strict_json_loads` (strict UTF-8 decode, `object_pairs_hook` rejects duplicate keys, `parse_constant` rejects `NaN`/`Infinity`/`-Infinity`) now backs every JSON source the gate reads: hook stdin, the tools-config file, sidecar lines, and this integration's own state files (`RoomStateStore.read_event_rows`/`read_room`/`read_turn_actions`). `validate_sidecar_record` requires each field's EXACT JSON type — no `str()`/`bool()` coercion — so a JSON string `"false"` for `author.bot` or `mention_everyone` can no longer coerce to `True`, and a numeric `author.id`/`message_id`/`guild_id` or non-string mention ID is refused rather than silently stringified. | `StrictJsonParsingCases`, `SidecarExactTypeCases` (`tests/v2/test_claude_code.py`) |
| 2 | Real `PostToolUseFailure` hook registration and handler with exact `tool_use_id` correlation | `handle_post_tool_failure` added, registered in `_SETTINGS_TEMPLATE` and the CLI (`post-tool-failure` subcommand); correlates strictly by `tool_use_id` via the same `_resolve_reservation` exact-match path `PostToolUse` uses. | `ReservationAndPostToolFailureCases.test_post_tool_failure_records_a_failed_delivery`, `..._mismatched_tool_use_id_does_not_resolve`; wrapper: `MalformedStdinFailsClosedCases`, `PreToolAndStopDirectionCases.test_post_tool_failure_configured_broken_gate_still_fails_open`, `UnconfiguredInertAcrossAllHookEventsCase.test_post_tool_failure_inert_when_unconfigured` |
| 3 | One atomic reply-or-reaction reservation per woken turn, bound to exact tool identity/input, truthfully closed by `PostToolUse`/`PostToolUseFailure`/`Stop` so unresolved outcomes are never silence | `_reserve_room_action` (at `PreToolUse`) creates exactly one reservation per turn — a second reply/react attempt in the same turn is denied regardless of whether the first resolved — bound to the exact `tool_use_id`, tool name, and a SHA-256 digest of the exact `tool_input`. `_resolve_reservation` (at `PostToolUse`/`PostToolUseFailure`) closes it only on an exact match; a mismatched `tool_use_id` or `tool_input` neither closes the reservation nor gets attested as the turn's action. `complete_turn`'s `replay_observed_native_turn` now raises (routing the outcome to `unknown`, never `None`/silent) whenever a reservation was made but is still unresolved at `Stop`, or resolved with no attestable action. | `ReservationAndPostToolFailureCases` (`test_second_room_action_in_the_same_turn_is_denied`, `test_reservation_without_tool_use_id_is_denied`, `test_unresolved_reservation_reports_unknown_not_silence`, `test_mismatched_tool_use_id_post_tool_does_not_attest`, `test_mismatched_tool_input_post_tool_does_not_attest`) |
| 4 | Receipt sinks accept only exact `None` as persistence acknowledgement | `run_attention`'s observation-receipt persistence and `_ObservedDeliveryRecorder.__call__` now require the sink's return value to be exactly `None` before treating it as a persisted receipt — matching the strict contract `src/nunchi/participant.py` already enforces for every other receipt call in this turn. A non-raising sink that returns a falsy-but-not-`None` value (`0`, `""`) is now treated exactly like a raised persistence failure. | `ReceiptSinkStrictAckCases` (`test_observation_receipt_sink_returning_non_none_is_treated_as_failure`, `test_observed_delivery_recorder_forwards_non_none_ack`, `test_observed_delivery_recorder_forwards_none_ack`) |
| 5 | Tools configuration rejects coercion, ambiguity, unknown keys, and malformed patterns | `_load_tools_config` rewritten: rejects any unknown key at the top level, inside `room_action_tools`, or inside a `privileged[]` entry; requires `tool_pattern`/`capability`/`impact`/`resource_kind`/`resource_id_input_key`/`resource_id_const` to be real JSON strings (`_require_config_str`) instead of coercing via `str()`; rejects an entry that sets both `resource_id_input_key` and `resource_id_const` (ambiguous resource-identity source); and `_compile_config_pattern` catches `re.error` — which is **not** a `ValueError` subclass and previously escaped every handler's `except (..., ValueError)` clause uncaught — converting it into `ClaudeGateConfigError`. | `ToolsConfigStrictCases` (11 tests: unknown top-level/room_action_tools/privileged keys, non-string pattern, malformed room-action and privileged patterns, missing required key, coerced capability, ambiguous resource-identity source, `test_pre_tool_denies_fail_closed_on_malformed_tools_config`, `test_well_formed_example_config_still_loads`) |

### Self-found sixth defect (adversarial self-review before handoff)

Before returning this candidate, an independent adversarial review
(`silent-failure-hunter`) of this exact diff was run against the working tree.
It found that wiring `_strict_json_loads` into `main()`'s stdin parsing had
introduced a **new** regression: `main()` began catching both the stdin-read
exception and the JSON-parse `ValueError` into a silently-synthesized
`payload = {}`. An empty payload reads to every handler as "no room event, no
session" — exactly the shape of a legitimate operator prompt (for
`user-prompt-submit`) or a session-mismatched turn (for `pre-tool`) — so a
merely truncated or malformed hook stdin would have been silently admitted or
allowed a privileged tool through, undetectable by the wrapper (exit 0, no
crash). The pre-existing (Attempt 1–7) code had the same JSON-parse fallback,
but the stdin-read catch was new to this attempt and is the more severe half
of the regression, since the read failure previously crashed uncaught and was
already caught by the wrapper's fail-closed/fail-open-per-event contract.

**Fixed**: `main()` no longer catches either failure. A stdin read failure, a
strict-parse failure, or a well-formed-but-non-object payload now crashes the
process uncaught — exactly like any other gate failure — so the already
fully-tested wrapper (`nunchi-claude-v2-hook.sh`) remains the single
fail-closed/fail-open boundary for a gate that cannot produce a real decision:
block for `user-prompt-submit`, deny (exit 2) for `pre-tool`, open for
`stop`/`post-tool`/`post-tool-failure`. No new bespoke logic was added to the
Python gate. Six new regression tests exercise this end-to-end through the
real wrapper and real gate. | `tests/test_claude_code_hook_wrapper.py::MalformedStdinFailsClosedCases` (malformed JSON and duplicate-key stdin block `user-prompt-submit`; a non-object payload blocks `user-prompt-submit`; malformed stdin denies `pre-tool` exit 2; unconfigured stays inert even with malformed stdin)

### Deterministic commands and results (Attempt 8)

`python3 -m unittest tests.v2.test_claude_code` → **90 OK** (38 new);
`python3 -m unittest tests.test_claude_code_hook_wrapper` → **43 OK** (7 new);
the five-module guard run (`test_no_home_writes`, `test_sentinel_forgery`,
`test_no_second_judgment`, `test_claude_code`,
`test_claude_code_hook_wrapper`) → **155 OK**; full baseline
`python3 -m unittest` → **1254 OK (skipped=7)**;
`python3 scripts/check_governance.py --check-cli` → OK; scene replay
(`PYTHONPATH=src:. python3 -m evals.v2.claude_code.run_scenes --out-dir <tmp>`)
→ 20 rows (19 PASS, 1 declared limitation), byte-identical to the Attempt-7
evidence rows already committed at `evidence/v2/claude-code/scene-results.jsonl`
/ `reactive-bot-hearing.jsonl` (confirmed by direct diff — this attempt
touches no attention/scene mechanics, so those files are not regenerated);
`git diff --check` → clean. Full table in `verification.md`.

### Installed provenance (Attempt 8)

Repository gate SHA-256 at the implementation candidate:
`ba3948f23ec2e6e4b37d4132256285af3d0690472a8f67fd5af78967c9822d9d`; wrapper
SHA-256: `eb510f86c91e15ec029d942034d54c8cd057df768bf3d4d7bbeb6798a41aecd0`.
**No host mutation was performed or requested this session** — no
`settings.json` edit, no transport-patch application, no outbound Discord
send, no staged-install refresh. The installed host state, the Attempt-7
`integrator-live-arming.md` record, and the remaining operator boundary
(participant completion blocked on the installed Claude CLI's expired login)
are unchanged; re-arming the staged gate/wrapper with these exact bytes and
re-running the live ladder from a freshly authenticated session is unchanged
process, not repeated here.

### Known limitations and rejected claims (Attempt 8)

Unchanged from Attempt 7, plus the reservation-coverage limitation now
documented in `integrations/claude-code/README.md` (`PreToolUse` disabled
while `PostToolUse` stays registered cannot bind a reservation, so an
unreserved send is reported unattested rather than "sent" — the same
disabled-hooks unenforced-path category as guard coverage, not a new gap).
**Rejected claim**: "live parity is proven" — it is not; this session
performed no live scenes and no host mutation. **Rejected claim**: "the
self-found sixth defect exhausts adversarial review" — one independent
review pass found one defect; it does not prove no others remain, and this
lane does not self-declare acceptance.

**Handoff target**: Codex, for independent adversarial re-review of this
exact candidate (`d594b29c1bca487da38f025b1a46de21c183b8f6`). This lane does
not self-accept and did not integrate.

---

## Attempt 9 — 2026-07-21 (rework: close pc-vigil's five findings on PR #15)

**Delivering lane**: `v2-claude-owner`, same session as Attempt 8 (model
`claude-sonnet-5`), continuing under Codex's direct scoped implementation
authority for the Claude packet. Attempt 8 (candidate `d594b29`, evidence
`2bec439`) was reviewed on the newly-opened GitHub PR
([mentatzoe/nunchi#15](https://github.com/mentatzoe/nunchi/pull/15), base
`codex/v2-integration`) by `pc-vigil` (Codex's review identity) and returned
**CHANGES_REQUESTED** with five HIGH and one MEDIUM finding, plus a CI note
attributing the PR's red checks to an unrelated, already-owned base-branch
issue (Codex PR #16: shallow checkout vs. `check_governance.py`'s historical
commit requirement) — not to this packet's content.

### Exact candidate

- **Implementation candidate**: `2389a9b48b471273e6856ca0430b8a58891091d6`
  (descends from Attempt-8 evidence tip `2bec439` on branch
  `claude/claude-code-v2-integration-3ac219`). Product, test, and owned-docs
  changes only.
- **Evidence-only binding**: this commit (adding this Attempt-9 section)
  sits on top; its diff from `2389a9b` touches only
  `evidence/v2/claude-code/`.

Attempt-9 changed-file inventory (implementation candidate, `2bec439` →
`2389a9b`):

```text
M  docs/integrations/claude-code-v2.md
M  integrations/claude-code/README.md
M  integrations/claude-code/nunchi_claude_v2.py
A  integrations/claude-code/transport-patch/0003-nunchi-bound-room-safety.patch
M  integrations/claude-code/transport-patch/README.md
M  integrations/claude-code/transport-patch/apply-transport-patch.sh
M  tests/test_claude_code_hook_wrapper.py
M  tests/v2/test_claude_code.py
```

No `src/`, `schemas/`, or other lane's surface changed.

### Finding-by-finding disposition

| # | pc-vigil finding | Resolution | Proof |
|---|---|---|---|
| 1 | HIGH — empty/whitespace-only configured hook stdin still fails open | `main()`'s `raw_stdin.strip() else {}` special case is removed entirely. `json.loads` already rejects empty/whitespace as invalid JSON, so it now crashes uncaught exactly like any other malformed stdin, and the already-tested wrapper crash-handling (block for `user-prompt-submit`, deny for `pre-tool`) is the single fail-closed boundary — no new bespoke logic. | `tests/test_claude_code_hook_wrapper.py::MalformedStdinFailsClosedCases` (`test_empty_stdin_blocks_user_prompt_submit`, `test_whitespace_only_stdin_blocks_user_prompt_submit`, `test_empty_stdin_denies_pre_tool_fail_closed`) |
| 2 | HIGH — native Discord effect/output tools (`edit_message`, `download_attachment`, `fetch_messages`) escape send safety, the reservation, and receipts | A Discord-namespace catch-all (`_DEFAULT_DISCORD_NAMESPACE_RE`) default-denies any tool the plugin exposes beyond reply/react/`fetch_messages`. `fetch_messages` (read-only) is allowed once room-scoped (its own `channel` input key, not `chat_id`). `edit_message`/`download_attachment` are denied unconditionally for a room-caused turn — they have no reservation/receipt shape the canonical participant-action schema understands. Defense in depth: if one executes anyway (disabled/bypassed guard), `PostToolUse`/`PostToolUseFailure` record an `unattested_effect` marker so `Stop` reports `unknown`, never `silent`. | `tests/v2/test_claude_code.py::NativeToolCoverageCases` (7 tests) |
| 3 | HIGH — `SUPPRESS` leaks room-visible activity (typing indicator, ack reaction) before attention runs | New transport patch `0003-nunchi-bound-room-safety.patch`: reads an optional `NUNCHI_CLAUDE_V2_CHANNEL_ID`; for the exact bound room, skips the pre-attention typing indicator and configured ack reaction entirely. Every other room is byte-for-byte unaffected (both behaviors run exactly as before when the env var is unset or the message is in a different room). | `ReactiveHearingCases.test_transport_patch_provenance_is_pinned_and_fail_closed` (patch-content assertions); manual reproducible-apply verification below |
| 4 | HIGH — the plugin's native permission-reply/button channel bypasses I-040B | Patch `0003` also skips the "yes/no `<code>`" room-TEXT permission-reply intercept for the bound room (ordinary room text can no longer satisfy a privileged approval there). The DM/button leg (`interactionCreate`) is a separate, cross-session surface reached only via direct message, keyed by a short code with no room/turn provenance in the plugin's own notification payload — not room-scoped by construction, and not addressed by a transport-layer patch. Honestly reported, not claimed safe, in `README.md` and `transport-patch/README.md`. | Same patch-content assertions as finding 3; residual limitation documented, not silently omitted |
| 5 | HIGH — transport backlog can become FIFO wake work (one attention cycle per already-delivered message instead of coalescing) | New `read_channel_backlog` + `_coalesce_backlog_anchor`: before committing to an anchor, the handler scans the sidecar for other not-yet-ingested authorized messages in the bound room, ingests them as context, and anchors the opportunity on the newest one found. Each older message's own later hook invocation then finds itself already known (`duplicate-retained`) and is coalesced away rather than spending its own attention cycle — the exact reported reproduction (two already-delivered rows before the host processes the first queued prompt) now produces exactly one classifier call, anchored on the newer message. | `CoalescingAndRestartCases.test_already_delivered_backlog_coalesces_to_one_wake` |
| 6 | MEDIUM — `schema_version` equality (`!=`) accepts `True`/`1.0`, not exact `int` | `_is_exact_schema_version` requires `isinstance(value, int) and not isinstance(value, bool)`, applied to both the tools-config loader and the state-file (`room.json`) reader. | `ToolsConfigStrictCases.test_boolean_schema_version_is_not_accepted_as_one` / `test_float_schema_version_is_not_accepted_as_one`; `StateSchemaStrictCases` (3 tests) |

One pre-existing test, `test_native_reply_and_mentions_are_preserved`, wrote
both its sidecar rows before either prompt was processed — a burst shape
that fix 5 now correctly coalesces, which is not what that test was
checking. Its sidecar-append timing was split to match the real temporal
order (the `relation` message is recorded only after `upstream`'s own turn
completes), preserving its actual intent (reply/mention preservation across
two genuinely sequential turns) without weakening fix 5.

### Deterministic commands and results (Attempt 9)

`python3 -m unittest tests.v2.test_claude_code` → **104 OK** (14 new since
Attempt 8's 90); `python3 -m unittest tests.test_claude_code_hook_wrapper`
→ **46 OK** (3 new since Attempt 8's 43); the five-module guard run
(`test_no_home_writes`, `test_sentinel_forgery`, `test_no_second_judgment`,
`test_claude_code`, `test_claude_code_hook_wrapper`) → **172 OK**; full
baseline `python3 -m unittest` → **1271 OK (skipped=7)**;
`python3 scripts/check_governance.py --check-cli` → OK; scene replay
(`PYTHONPATH=src:. python3 -m evals.v2.claude_code.run_scenes --out-dir <tmp>`,
run twice) → 20 rows (19 PASS, 1 declared limitation) each time,
byte-identical to each other and to the already-committed
`scene-results.jsonl`/`reactive-bot-hearing.jsonl` (this attempt touches no
attention/scene mechanics); `git diff --check` → clean.

Transport patch reproducibility (manual, since the real pristine plugin
source is third-party and not vendored into this repo — the same
verification class every prior attempt records here rather than as an
automated test): rebuilt from the pinned pristine base
(`c3c79c65…`) with `0001` → `0002` → `0003` applied in sequence via
`git apply`, each `--check` and apply clean; final digest
`46420d46dcff14bf486a7291e6790e91c4bb09a887c1fe29ada9f3e5f9106775` matches
the pinned `PATCHED_SHA256` in `apply-transport-patch.sh` exactly; the
result transpiles clean under `bun build`. A full `apply-transport-patch.sh`
apply/`--verify`/`--rollback`/`--verify` cycle was also run end-to-end
against a scratch copy of the pristine base (not the installed host) and
produced the expected digest transitions and messages at every step.

### Installed provenance (Attempt 9)

Repository gate SHA-256 at the implementation candidate:
`11267794f63c075f2ffe0aa3f92b46bb6a643eee92f814cd82f6613ca0d0d2ef`; new
transport patch SHA-256:
`b1231a8778944c10dff165a622eeb07365128cd3549b13e6f1df599130cf940b`.
**No host mutation was performed or requested this session** — no
`settings.json` edit, no transport-patch application, no outbound Discord
send, no staged-install refresh. The installed host remains at Attempt-7's
armed two-patch state (`0d1ffaa0…`); re-arming to this candidate requires
the corrected ladder in `integrations/claude-code/README.md` (now including
the `NUNCHI_CLAUDE_V2_CHANNEL_ID` line in the Discord plugin's own `.env`)
plus a fresh `--rollback` → `--verify` → apply → `--verify` cycle expecting
the new three-patch result digest. Full detail in `installed-runtime.md`'s
Attempt-9 correction note.

### Known limitations and rejected claims (Attempt 9)

Unchanged from Attempt 8, plus the new, honestly-reported residual from
finding 4: the plugin's DM/button native permission-approval path
(`interactionCreate`) remains unaddressed — it is a cross-session surface
keyed by a short code with no room/turn provenance in the notification
payload, not room-scoped by construction, and closing it fully would
require the plugin itself to thread Nunchi turn context through that
payload (outside what a transport-layer patch can do). **Rejected claim**:
"live parity is proven" — it is not; this session performed no live scenes
and no host mutation. **Rejected claim**: "this candidate closes every
finding an adversarial reviewer could find" — six were found and closed
this round; that does not prove none remain, and this lane does not
self-declare acceptance.

**Handoff target**: Codex, for independent adversarial re-review of this
exact candidate (`2389a9b48b471273e6856ca0430b8a58891091d6`) on
[mentatzoe/nunchi#15](https://github.com/mentatzoe/nunchi/pull/15). This
lane does not self-accept and did not integrate.

## Attempt 10 — 2026-07-22 (merge codex/v2-integration@8e647469, close the analogous receipt-sink-failure gap)

**Delivering lane**: `v2-claude-owner`, same session (model `claude-sonnet-5`).
Between Attempt 9 and this attempt, this same session independently reviewed
and approved slice 040 (participant-wake, PR #17), slice 050 (Discord-transport,
PR #18), and their composition onto `codex/v2-integration` (PR #19) — all now
merged. Zoe relayed Codex's instruction to merge that integration line into
this branch, apply whatever fixes from that work are relevant to this
integration, and push a successor.

### Exact candidate

- **Merge commit**: `6ab3bd42…` — `git merge origin/codex/v2-integration`
  (tip `8e64746970f9910d03b372291c5aa173883e869f`, PR #19's merge commit) into
  `claude/claude-code-v2-integration-3ac219` at Attempt-9 evidence tip
  `a4e0d9d`. Clean three-way merge via the `ort` strategy — zero conflicts,
  confirmed by grep for conflict markers across the tree. `integrations/claude-code/`
  itself has zero path overlap with anything `codex/v2-integration` touched.
- **Implementation candidate**: `1b54cfbe6801fe0196f50d042861ad5fb4293677`
  (two fix commits — `b735c14` then a self-correction `1b54cfb` — on top of
  the merge commit).
- **Evidence-only binding**: this commit (adding this Attempt-10 section)
  sits on top; its diff from `1b54cfb` touches only `evidence/v2/claude-code/`.
- Repository gate SHA-256 of `nunchi_claude_v2.py` at the implementation
  candidate: `267dbe193805548b7a07cbb7ef5dd54fb72ff18ba8ee34e700344f087565b34f`.

Attempt-10 changed-file inventory (post-merge, own commits only):

```text
M  evals/v2/claude_code/run_scenes.py
M  evidence/v2/claude-code/verification.md
M  integrations/claude-code/nunchi_claude_v2.py
M  tests/v2/test_claude_code.py
```

No `src/` file was touched by this lane; those changes arrived entirely
through the merge and are owned by their respective reviewed/merged slices.

### What the merge changed for this integration, and what was applied

`nunchi.participant` changed by 497 lines across the reviewed 040 rework
(PR #17, three rounds — my own approval, then two corrections after Aleph
caught real gaps I'd missed, detailed in this session's PR review history).
The externally-visible contract change relevant to this lane: the immutable
`participant-host` receipt stage now *always* attests `outcome="unknown"`
before any transport effect and is never rewritten — delivery truth lives
exclusively in the separate `transport` stage, closing the "immutable host
receipt can claim `sent` before the action seam has an outcome" class of bug
Aleph found in the reviewed source. This lane's own `complete_turn()` already
calls `run_participant_turn` for exactly this purpose, so no code change was
needed there — only four stale test assertions (`test_claude_code.py`) and
two stale scene-runner assertions (`run_scenes.py`, missed by the first pass
and caught by re-running the deterministic scene replay itself) that expected
the old `"sent"`-on-the-host-receipt behavior, including one
(`test_post_tool_failure_records_a_failed_delivery`) that had been asserting
the *buggy* behavior as correct — a failed transport delivery with a host
receipt still claiming `"sent"`.

Auditing the rest of the merge for the same categories of bug the PR #17/#18/#19
reviews surfaced (trust-boundary confused-deputy gaps, hardcoded literals
standing in for computed coverage state, incomplete trigger coverage for a
gap/taint signal, bounded-resource exhaustion) found one real, analogous gap
in this lane's own code, unrelated to any merge conflict:

`run_attention()` reimplements (rather than reuses) the attention→participant
orchestration `LiveRoomRuntime._process_one()` performs upstream, since this
lane doesn't use `nunchi.runtime` directly. It did not have the upstream
fix's explicit check for `decision["error"]["code"] == "receipt-sink-failure"`
before branching on decision status. With this lane's default
`error_action="WAKE"`, a receipt-sink failure inside `evaluate_v2()` (the
attention-stage receipt failing to persist) was indistinguishable from an
ordinary classifier/operational error and fell through to the same
`ERROR_FALLBACK` wake path as a real WAKE/DEFER decision — returning a real
`snapshot` for eventual real participant/privileged-tool invocation, exactly
the bug Aleph found and Codex fixed in `LiveRoomRuntime._process_one()`.
Fixed: `run_attention()` now checks for `receipt-sink-failure` first, before
any other status branch, and routes it to `operational-error` (denying
privileged effects via the existing degraded-turn machinery), matching the
fixed upstream contract.

RED-to-GREEN verified: `git stash` of just the product file reproduced the
bug with the new test (`route="wake"`, `KeyError: 'degraded'` — no snapshot
gate at all) before the fix was restored and the same test passed.

`read_channel_backlog`/`_coalesce_backlog_anchor` were checked against the
Codex composition's "bootstrap truncation erased from participant coverage"
finding (PR #19) and found not applicable: that function only coalesces
toward the newest already-locally-known anchor within an append-only sidecar
scan window bounded from the *end* of the file — it never makes a
completeness/coverage claim that a truncated *earlier* window could falsify,
unlike `bootstrap_history()`'s remote-history-restoration role.

### Self-found, out-of-scope finding (flagged, not fixed this attempt)

While tracing `handle_pre_tool`'s reply/react branch to confirm degraded
turns can't produce a real send, found that they can: `_reserve_room_action`
(and its caller) never checks `turn.get("degraded")` or
`turn.get("snapshot")`, so an ordinary reply/react tool call is not denied at
`PreToolUse` during a degraded turn — only "privileged" (I-040B) actions are
unconditionally denied there. Worse, `complete_turn()` unconditionally
short-circuits for any degraded turn *before* calling `run_participant_turn`,
so if a reply/react does execute during one, no participant-host and no
transport receipt are ever written for it — the send happens with zero
attestation, which the canonical singly-attested receipt-chain invariant this
whole system is built around does not allow for. Confirmed via `git log`/`git
show` that this exact code shape predates this attempt (present at Attempt-9
tip `a4e0d9d`) — it is not a regression from today's merge or fix, and fixing
it requires a real design decision (deny reply/react outright during degraded
turns, or receipt whatever happens honestly) that is out of scope for "apply
the fixes relevant to this merge." Flagged as a standalone follow-up rather
than silently left for a future reviewer to rediscover.

### Deterministic commands and results (Attempt 10)

`python3 -m unittest tests.v2.test_claude_code tests.test_claude_code_hook_wrapper`
→ **151 OK** (1 new since Attempt 9's 150 combined); full baseline
`python3 -m unittest` (isolated `HOME`, `HERMES_HOME`/`PYTHONPATH` unset) →
**1372 OK (skipped=9)**; `python3 scripts/check_governance.py --check-cli` →
OK; scene replay (`PYTHONPATH=src:. python3 -m evals.v2.claude_code.run_scenes
--out-dir <tmp>`, run twice after the scene-runner fix) → 20 rows (19 PASS, 1
declared limitation) each time, byte-identical to each other and to the
already-committed `scene-results.jsonl`/`reactive-bot-hearing.jsonl` (this
attempt touches receipt-outcome semantics only, not attention/scene
mechanics — the recorded data rows were never affected, only the assertion
text that checks them); `python3 -m py_compile` and `ast.parse` on the
product file → clean; `git diff --check` → clean.

### Installed provenance (Attempt 10)

**No host mutation was performed or requested this session** — no
`settings.json` edit, no transport-patch application, no outbound Discord
send, no staged-install refresh. The installed host remains at Attempt-7's
armed two-patch state (`0d1ffaa0…`), unchanged by this attempt; re-arming
still requires the ladder documented in `installed-runtime.md`.

### Known limitations and rejected claims (Attempt 10)

Unchanged from Attempt 9, plus: the self-found degraded-turn receipt gap
above is now a known, tracked limitation rather than an undiscovered one —
**rejected claim**: "the merge was a mechanical no-op for this lane" — it
surfaced one real, confirmed, previously-live bug in this lane's own
receipt-sink-failure handling (fixed this attempt) and one real, confirmed,
pre-existing gap in degraded-turn room-action denial (flagged, not fixed).
**Rejected claim**: "the receipt-sink-failure fix is upstream's problem, not
this lane's" — `run_attention()` is this lane's own reimplementation of the
orchestration `LiveRoomRuntime` provides upstream, so the same class of bug
had to be independently checked for and independently fixed here; it does
not inherit fixes made only inside `nunchi.runtime`.

**Handoff target**: Codex, for independent adversarial re-review of this
exact candidate (`1b54cfbe6801fe0196f50d042861ad5fb4293677`) on
[mentatzoe/nunchi#15](https://github.com/mentatzoe/nunchi/pull/15). This
lane does not self-accept and did not integrate.

---

## Attempt 11 — 2026-07-22 (rework: deny reply/react during degraded turns, closing Attempt-10's self-found gap)

**Delivering lane**: `v2-claude-owner`, same session (model `claude-sonnet-5`).
Attempt 10 found and flagged, but did not fix, a gap in its own review scope:
`handle_pre_tool`'s reply/react branch did not check `turn.get("degraded")`,
so an ordinary reply/react could execute during a degraded (operational-error)
turn with zero participant-host or transport receipt ever attested for it —
the send happens, the receipt chain does not. Zoe reviewed the flagged
finding directly and directed the fix.

### Exact candidate

- **Implementation candidate**: `bb79cca17cccaa2965ead3aa8182cb3c2602b991`
  (cherry-picked, zero conflicts, from an identical commit authored in a
  sibling worktree on the same base — Attempt-10 evidence tip `33c50b4` —
  branch `claude/youthful-cori-976b2d` commit `fe909e4`).
- Repository gate SHA-256 of `nunchi_claude_v2.py` at the implementation
  candidate: `b42bee5e3dd4bfa1ef98c41d2a11c756375b5a1ec397395af14d0f1cf0baddfd`.
- **Evidence-only binding**: this commit (adding this Attempt-11 section)
  sits on top; its diff from `bb79cca` touches only `evidence/v2/claude-code/`.

Attempt-11 changed-file inventory:

```text
M  integrations/claude-code/nunchi_claude_v2.py
M  tests/v2/test_claude_code.py
```

No `src/`, `schemas/`, or other lane's surface changed.

### Direction decided, and why the alternative was rejected

Attempt 10 named two possible directions: deny reply/react outright during a
degraded turn (matching how privileged actions are already denied there), or
write an honest "unknown-provenance" receipt for whatever the reply/react
call did. The second was evaluated and rejected: `nunchi.observation`'s
`check_receipt_sequence` enforces a canonical `observation -> attention ->
participant-host -> transport` prefix per `request_id`, which a degraded turn
cannot reliably supply — the `snapshot-unavailable` operational-error route
has no `request_id` at all, and at least one other route
(`observation-receipt-persistence-unknown`) leaves the `observation`-stage
persistence itself uncertain. Writing a bare `participant-host`/`transport`
receipt in either case would itself violate that canonical-order invariant
this whole system is built around, and fixing it correctly would mean
extending the core receipt schema in `src/nunchi/observation.py` — an
upstream contract change outside this integration's lane, not something to
reach into unilaterally from a Claude Code fix.

Chosen instead: `handle_pre_tool`'s reply/react branch now denies fail-closed
when `turn.get("degraded")` or `turn["snapshot"]` is not a `dict`, exactly
mirroring the privileged-action seam two branches down in the same function.
Nothing sends, so nothing needs an unattested receipt — `complete_turn()`'s
existing degraded short-circuit (clear the turn, no fabricated stage) is now
fully honest rather than a discard-after-the-fact. Updated the
`handle_pre_tool`/`start_degraded_turn` docstrings and the
`_drive_opportunity` operational-error context message rendered to the model,
so they accurately state reply/react is denied too, not just privileged
tools — the prior text told the model it could "take one normal room turn,"
which is no longer true.

### Test coverage

Added `test_operational_error_wake_denies_reply_and_react_too`
(`AdversarialRegressionCases`), reusing the exact receipt-sink-failure
degraded-turn setup from the two sibling tests immediately above it, then
confirming both `mcp__discord__reply` and `mcp__discord__react` are denied
at `PreToolUse` and that neither attempt ever created a reservation.

### Deterministic commands and results (Attempt 11)

`python3 -m unittest tests.v2.test_claude_code tests.test_claude_code_hook_wrapper`
→ **152 OK** (1 new, since Attempt 10's 151); the five-module guard run
(`test_no_home_writes`, `test_sentinel_forgery`, `test_no_second_judgment`,
`test_claude_code`, `test_claude_code_hook_wrapper`) → **174 OK**; full
baseline `python3 -m unittest` → **1373 OK (skipped=9)**;
`python3 scripts/check_governance.py --check-cli` → OK; scene replay
(`python3 evals/v2/claude_code/run_scenes.py`, run twice) → 20 rows (19 PASS,
1 declared limitation) each time, identical to Attempt 10 (this attempt
changes `PreToolUse` denial semantics only, not attention/scene mechanics —
no scene ever executes a reply/react during a degraded turn, so no recorded
row is affected); `git diff --check` against the implementation candidate →
clean.

### Installed provenance (Attempt 11)

**No host mutation was performed or requested this session** — no
`settings.json` edit, no transport-patch application, no outbound Discord
send, no staged-install refresh. The installed host remains at Attempt-7's
armed two-patch state (`0d1ffaa0…`), unchanged by this attempt.

### Known limitations and rejected claims (Attempt 11)

Unchanged from Attempt 10, minus the degraded-turn receipt gap, which is now
closed rather than a tracked limitation. **Rejected claim**: "denying
reply/react during a degraded turn changes ordinary (non-degraded) turn
behavior" — it does not; the new check only fires when `turn.get("degraded")`
is true or `turn["snapshot"]` is not a `dict`, both exclusive to the
operational-error path `start_degraded_turn` creates.

**Handoff target**: Codex, for independent adversarial re-review of this
exact candidate (`bb79cca17cccaa2965ead3aa8182cb3c2602b991`) on
[mentatzoe/nunchi#15](https://github.com/mentatzoe/nunchi/pull/15). This
lane does not self-accept and did not integrate.

## Attempt 12 — 2026-07-22 (self-review vs merged upstream: unattestable-reference denial)

**Delivering lane**: `v2-claude-owner`, same session (model `claude-fable-5`
for this attempt). Zoe asked for a review of whether this slice is done
against the latest upstream "and honestly so". Answer: Attempt 11 was
verified genuinely closed (all claimed numbers reproduced independently;
RED-to-GREEN re-proven by file swap against the pre-fix candidate; both
degraded-turn producers — `start_degraded_turn` and `_degraded_turn_marker`
— confirmed covered by the deny condition), but the review found one more
real post-merge gap that Attempt 10's "apply the relevant fixes" audit
missed, so the honest answer was "not yet" and this attempt closes it.

### Exact candidate

- **Implementation candidate**: `abb823ed55a6e20addf8c54913f9976641457122`
  (one product commit on top of Attempt-11 evidence tip `1bf4c24`).
- **Evidence-only binding**: this commit (adding this Attempt-12 section and
  the manifest/verification amendments) sits on top; its diff from `abb823e`
  touches only `evidence/v2/claude-code/`.
- Repository gate SHA-256 of `nunchi_claude_v2.py` at the implementation
  candidate:
  `57d0c9e7155a231db038bd945544799d4cefcdfdcda927aab2ad788d068b1574`.

Changed-file inventory (implementation candidate):

```text
M  integrations/claude-code/nunchi_claude_v2.py
M  tests/v2/test_claude_code.py
```

### The gap, its reproduction, and the fix

The merged `nunchi.participant` (slice-040 successor, PR #17) binds
`reply_to_event_id`/`target_event_id` to facts delivered in the participant
packet (`_validate_action` → `turn.binds_event`) and rejects anything else.
Claude Code natively can reply/react to ANY message in the channel,
including ones outside the packet's event budget — the packet typically
carries a bounded window, and `fetch_messages` (allowed, read-only) can
surface older messages the model may then want to reference.

Reproduced concretely before fixing (scratch scenario, kept out of the
suite; the committed regression tests supersede it): a native reply to an
out-of-packet target **executes**, then at `Stop` the host raises
"participant reply target is unavailable" before the action sink runs. The
recorded chain: `participant-host` `outcome="unknown"`, **no transport
stage at all** — for a delivery this integration directly observed succeed.
Pre-merge, the identical flow produced `participant-host` + `transport(sent)`.
It never fabricates silence, but it records unknown-for-a-known-fact,
silently drops an observed delivery attestation, and never warns the model.

Since the `Stop`-time rejection is inevitable under the upstream contract,
the fix moves it before the irreversible native send — the same
attestability-not-social-gate pattern as the cross-room denial and
Attempt 11's degraded-turn denial. New `_unattestable_reference` helper in
`handle_pre_tool`'s reply/react branch, after room binding, before the
reservation:

- reply with no `reply_to` (plain message): always allowed — nothing to bind;
- reply with a digit-string `reply_to`: allowed iff
  `discord:message:<id>` is one of this turn's packet event ids, else
  denied with a message telling the model to target a packet message or
  send without the reference;
- reply with a non-digit/non-string `reply_to`: denied for attestation
  fidelity — `_observed_action` would omit the reference from the replayed
  action while the native call might still send with one, so the attested
  action would under-report what happened;
- react: `message_id` (mirroring `_observed_action`'s `str()` coercion
  exactly) must be digits and one of the packet event ids.

The helper's rules mirror `_observed_action`'s replay construction exactly,
so PreToolUse's judgment of "what will be attested" always matches what
PostToolUse will actually record. A denied attempt creates no reservation,
so a corrected in-packet retry works end-to-end (covered by test). The
common cases — replying/reacting to the trigger or any packet message, or
sending a plain message — are unaffected.

One existing test (`test_second_room_action_in_the_same_turn_is_denied`)
reacted to out-of-packet `message_id="1"` merely as a placeholder; its
second call now targets the in-packet trigger so the reservation denial —
that test's actual subject — is what fires, not the new earlier denial.

### RED-to-GREEN and verification (Attempt 12)

All three new tests
(`test_out_of_packet_reply_target_is_denied_before_execution`,
`test_out_of_packet_reaction_target_is_denied_before_execution`,
`test_non_numeric_reply_reference_is_denied_before_execution`) fail against
the pre-fix product file — the gate returned allow and the send went
through — and pass with the fix, verified by file swap. Attempt 11's
`test_operational_error_wake_denies_reply_and_react_too` was likewise
re-proven RED against the Attempt-10 product file during this review, not
taken on faith.

`python3 -m unittest tests.v2.test_claude_code
tests.test_claude_code_hook_wrapper` → **155 OK** (3 new); five-module guard
run → **177 OK**; full baseline (isolated env) → **1376 OK (skipped=9)**;
`python3 scripts/check_governance.py --check-cli` → OK; scene replay ×2 →
20 rows (19 PASS, 1 declared limitation), byte-identical to each other and
to the committed evidence rows (PreToolUse denial semantics only; no scene
references an out-of-packet target); `git diff --check` → clean.

### Upstream-contract audit summary (what "done against latest upstream" was checked to mean)

Every upstream seam this lane consumes was re-checked against the merged
tree: `evaluate_v2` (receipt-sink-failure routing — closed in Attempt 10),
`run_participant_turn` (receipt ordering — Attempt 10; action fact-binding
— this attempt; strict `None`-only receipt acks — already conformant since
Attempt 8), `build_participant_wake` (decisions come from the real
`evaluate_v2`, conformant by construction), `DiscordEventSourceV2.native_input`
(sidecar records already validated to exact native types since Attempt 8;
new `MessageEvent` fields carry defaults), `ConversationOpportunityScheduler`
(interface unchanged), `ReloadingPolicyReceiptSink` (new
`claim_transport_action` is additive and unused here: the exclusive-create
receipt files already deduplicate the replayed transport stage per
request_id, and a turn is completed exactly once before `room["turn"]` is
cleared), privileged-guard seams (derive-only + unconditional deny,
unchanged). `record_upstream_coverage` (new upstream) is not applicable:
this lane declares `message: live-only` visibility and performs no remote
history restoration, so there is no upstream coverage claim to record —
stated here so its absence reads as a decision, not an omission.

### Known limitations and rejected claims (Attempt 12)

Unchanged from Attempt 11 otherwise. **Rejected claim**: "the slice was
already done against the latest upstream before this attempt" — it was not;
this review found the unattestable-reference gap that Attempt 10 missed,
and closed it. **Rejected claim**: "denying out-of-packet references is a
send-time social judgment" — it is not; the content of the send is never
examined, only whether its reference can bind to a delivered fact, exactly
the check the canonical host performs unconditionally at `Stop`; this
attempt only moves that mechanical rejection before the irreversible
effect. **Residual fidelity note**: replayed message actions do not carry
`mention_actor_ids` (native mention metadata is not reconstructed from
`tool_input`); the attested action's content still contains the literal
text. Pre-existing, unchanged by the merge, recorded here for completeness.

**Handoff target**: Codex, for independent adversarial re-review of this
exact candidate (`abb823ed55a6e20addf8c54913f9976641457122`) on
[mentatzoe/nunchi#15](https://github.com/mentatzoe/nunchi/pull/15). This
lane does not self-accept and did not integrate.

## Attempt 13 — 2026-07-22 (rework: close pc-vigil's two Attempt-12 findings)

**Delivering lane**: `v2-claude-owner`, same session (model `claude-fable-5`).
pc-vigil's Attempt-12 exact-head review (PR #15, CHANGES_REQUESTED at
`31adbfd`) returned two HIGH findings. Both were verified against the pinned
plugin source (`~/.claude/plugins/cache/claude-plugins-official/discord/0.0.4/server.ts`)
before fixing — the reply tool's `files` schema/upload path and the chunked
send loop's partial-failure throw were confirmed exactly as cited.

### Exact candidate

- **Implementation candidate**: `5b661134d9f0b68cdb98ab248361a89723629d41`
  (one product commit on top of Attempt-12 evidence tip `31adbfd`).
- **Evidence-only binding**: this commit (adding this Attempt-13 section and
  the manifest/verification amendments) sits on top; its diff from `5b66113`
  touches only `evidence/v2/claude-code/`.
- Repository gate SHA-256 of `nunchi_claude_v2.py` at the implementation
  candidate:
  `055766c3829ccd7c78f1d9f17149c35a43176eeebaede7fdb34622495fff2dc9`.

Changed-file inventory (implementation candidate):

```text
M  docs/integrations/claude-code-v2.md
M  integrations/claude-code/nunchi_claude_v2.py
M  tests/v2/test_claude_code.py
```

### Finding-by-finding disposition

| # | pc-vigil finding | Resolution | Proof |
|---|---|---|---|
| 1 | HIGH — the supported `reply` path permits `files` uploads absent from the canonical action and receipts | `handle_pre_tool` denies a reply carrying `files` unless absent or exactly `[]`, fail-closed on any other shape (non-empty list, string, dict, number), before the reservation — the reviewer's "deny until a canonical, authorized, receipted media action exists" option. A denied attempt burns no reservation. | `test_reply_with_files_is_denied_before_execution` (non-empty list denied, malformed string denied, no reservation burned, empty list allowed) |
| 2 | HIGH — partial multi-message delivery misattested as clean failure | `_ObservedDeliveryRecorder` never writes `failed` anymore: an error/failure report cannot transport-prove zero effects at this seam (the pinned plugin throws after earlier chunks landed; even a first-send error may have landed server-side — the same non-idempotent-POST reasoning as slice 050's nonce finding). Any undelivered row → delivery `unknown`, with bounded error text and parsed `chunks_sent`/`chunks_total` in the transport detail when the pinned format matches. `handle_post_tool` now captures response-embedded errors so both report paths carry the facts. Stale `outcome=sent` docstring and blanket failed-delivery docs wording corrected. | `test_post_tool_failure_records_an_unknown_delivery`, `test_partial_chunk_failure_preserves_the_partial_send_fact`, `test_error_response_delivery_is_recorded_unknown_not_failed` |

### Self-found in the same seam (fixed this attempt, same class as finding 2)

Tracing the post-tool observation seam for finding 2 exposed two adjacent
executed-effects-understated holes, both fixed here rather than deferred:

- **An unreserved executed in-room send was attested as silence.** The
  unmatched-reservation path appended no row at all, so `Stop`'s replay
  found no reservation and no marker and returned `None` — an executed send
  recorded as a genuinely silent turn. Reachable when PreToolUse is
  unregistered or bypassed while PostToolUse still reports — exactly the
  guard-bypass scenario for which `unattested_effect` markers already
  existed on the unsupported-tool path. Both post handlers now append an
  `unattested_effect` row for unmatched reports, so `Stop` reports
  `unknown`, never silence. Only an exact duplicate re-description of the
  already-resolved reservation (same `tool_use_id`, tool name, input digest
  — new `_is_duplicate_report`) is ignored as benign, so a cleanly attested
  turn cannot be flipped to `unknown` by a duplicate report.
- **A cross-room execution report was silently allowed with no marker.**
  Same reasoning: the model DID act (just not in the bound room), so the
  turn's outcome cannot be silence. Both post handlers now record the
  marker.

### RED-to-GREEN and verification (Attempt 13)

Six new/updated tests fail against the Attempt-12 product file — the files
reply was allowed through and reserved; error/failure reports produced
`transport(failed)`; unreserved and cross-room executed sends were attested
as silence — and pass with the fix, verified by file swap. The
duplicate-report test passes on both files (it guards the new unmatched
behavior against over-tainting) and is recorded as a regression guard, not
a RED-to-GREEN proof.

`python3 -m unittest tests.v2.test_claude_code
tests.test_claude_code_hook_wrapper` → **160 OK** (5 new, 2 renamed/
reworked); five-module guard run → **182 OK**; full baseline (isolated env)
→ **1381 OK (skipped=9)**; governance → OK; scene replay ×2 → 20 rows
(19 PASS, 1 declared limitation), byte-identical to each other and to the
committed evidence rows (no scene exercises the failure/bypass paths this
attempt changed); `git diff --check` → clean.

### Known limitations and rejected claims (Attempt 13)

Unchanged from Attempt 12, plus: **transport-stage `failed` is no longer
producible at this hook seam at all** — zero-effect proof would require the
patched plugin itself to attest structured sent-IDs/counts across the hook
boundary (the reviewer's alternative direction), which is a possible future
transport-patch extension, honestly deferred rather than half-claimed.
**Rejected claim**: "denying `files` is a capability regression" — there
was never a receipted media capability; what existed was an unattested
upload path. **Rejected claim**: "the unreserved/cross-room markers were in
the reviewer's findings" — they were not; they are self-found members of
the same class, reported and fixed here rather than left for a future
round to rediscover.

**Handoff target**: Codex, for independent adversarial re-review of this
exact candidate (`5b661134d9f0b68cdb98ab248361a89723629d41`) on
[mentatzoe/nunchi#15](https://github.com/mentatzoe/nunchi/pull/15). This
lane does not self-accept and did not integrate.
