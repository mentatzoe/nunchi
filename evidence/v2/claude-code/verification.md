# Claude Code V2 — verification index

**Attempt 8**, recorded 2026-07-21, `v2-claude-owner` lane, on top of the
integrator's Attempt-7 live-source remediation (`7ea499b` / evidence
`7e3d970`). The Attempt 1–6 indexes below are preserved as originally
recorded at their own candidates; the table immediately following this note
is the current (Attempt-8) index.

## Attempt-8 deterministic commands and results

Every command below was run on the Attempt-8 implementation candidate
`d594b29c1bca487da38f025b1a46de21c183b8f6`.

| Command | Result |
|---|---|
| `python3 -m unittest tests.v2.test_claude_code` | `Ran 90 tests … OK` (38 new: `StrictJsonParsingCases`, `SidecarExactTypeCases`, `ReservationAndPostToolFailureCases`, `ReceiptSinkStrictAckCases`, `ToolsConfigStrictCases`) |
| `python3 -m unittest tests.test_claude_code_hook_wrapper` | `Ran 43 tests … OK` (7 new: `MalformedStdinFailsClosedCases` ×6, `post-tool-failure` fail-open/inert coverage) |
| `python3 -m unittest tests.test_no_home_writes tests.test_sentinel_forgery tests.test_no_second_judgment tests.v2.test_claude_code tests.test_claude_code_hook_wrapper` | `Ran 155 tests … OK` |
| `python3 -m unittest` (full offline baseline) | `Ran 1254 tests … OK (skipped=7)` |
| `python3 scripts/check_governance.py --check-cli` | `governance boundary + CLI: OK (SpecKit 0.12.11)` |
| `PYTHONPATH=src:. python3 -m evals.v2.claude_code.run_scenes --out-dir <tmp>` (×2, diffed) | `cc-scenes: 20 rows, 19 PASS, 1 declared limitations`; byte-identical across two independent runs, and byte-identical to the committed `scene-results.jsonl`/`reactive-bot-hearing.jsonl` (this attempt touches no attention/scene mechanics, so those evidence files are unchanged) |
| `git diff --check` | clean |

## Attempt-8 defect coverage

| Blocker | Proven by |
|---|---|
| Strict UTF-8/JSON parsing (duplicate-key, non-finite-constant rejection) wired into stdin, tools config, sidecar, and state-file reads | `StrictJsonParsingCases` |
| Exact native sidecar types (no `str()`/`bool()` coercion) | `SidecarExactTypeCases` |
| Real `PostToolUseFailure` hook + exact `tool_use_id` correlation | `ReservationAndPostToolFailureCases`, wrapper `PreToolAndStopDirectionCases`/`UnconfiguredInertAcrossAllHookEventsCase` post-tool-failure cases |
| One atomic reply-or-reaction reservation per turn; unresolved outcome is `unknown`, never silence | `ReservationAndPostToolFailureCases` |
| Receipt sinks accept only exact `None` as persistence acknowledgement | `ReceiptSinkStrictAckCases` |
| Tools configuration rejects coercion/ambiguity/unknown keys/malformed patterns | `ToolsConfigStrictCases` |
| Self-found: `main()`'s stdin read/parse failure must crash uncaught (wrapper is the fail-closed/open boundary), not synthesize an empty payload | `tests/test_claude_code_hook_wrapper.py::MalformedStdinFailsClosedCases` |

Full finding-by-finding narrative is in `handoff.md` (Attempt 8).

---

**Attempt 6**, recorded 2026-07-21, `v2-claude-owner` lane. The Attempt
1/2/3/4/5 indexes are preserved in git at candidates `6476b58` / `1990129` /
`6513135` / `a6a7a8b` / `f6c34d1`. Every command below was run on the
Attempt-6 candidate `4ca9d8bbb6fc40c33b9fc54a7dd027922472994e`; results are
quoted exactly.

## Deterministic commands and results

| Command | Result |
|---|---|
| `python3 -m unittest tests.test_claude_code_hook_wrapper` | `Ran 36 tests … OK` |
| `python3 -m unittest tests.v2.test_claude_code` | `Ran 52 tests … OK` |
| `python3 -m unittest tests.test_no_home_writes tests.test_sentinel_forgery tests.test_no_second_judgment tests.v2.test_claude_code tests.test_claude_code_hook_wrapper` | `Ran 110 tests … OK` |
| `python3 -m unittest` (full offline baseline) | `Ran 1209 tests in 23.5s — OK (skipped=7)` |
| `python3 scripts/check_governance.py --check-cli` | `governance boundary + CLI: OK (SpecKit 0.12.11)` |
| `PYTHONPATH=src:. python3 -m evals.v2.claude_code.run_scenes --out-dir <tmp>` | `cc-scenes: 20 rows, 19 PASS, 1 declared limitations` (byte-identical across runs; the JSON-validation fix does not touch attention/scene mechanics) |
| `git diff --check` (staged Attempt-6 tree) | clean |
| Patch reproducibility (scratch build) onto pinned base `c3c79c65…` | `BOTH APPLY CLEAN`; result digest `0d1ffaa0…` equals the pinned target (unchanged since Attempt 3 — this attempt touches only the shell wrapper, not the transport patches) |
| Installer safety: apply against a symlinked target / rollback against a symlinked backup | exit 2 each, `symlink; refusing to follow`, referent bytes unchanged |
| Transport-patch state, re-confirmed read-only | `--verify` against the installed plugin → exit `2` `UNRECOGNIZED`, digest `b025d1c2…` (matches Codex's independent finding exactly); pristine backup confirmed to match pinned base `c3c79c65…` exactly — no write performed |
| Installed-host probes (Attempt 6, no arming) | foreign-room prompt → `block`; bound-room prompt with no sidecar → `block` fail-closed; non-channel prompt → exit 0 no output; wrapper fault injection (syntax-broken gate) → `block`; wrapper fault injection (empty gate file) → `block`; **wrapper fault injection (well-formed but unsupported `{"decision":"allow"}`) → `block`, gate restored and digest re-verified afterward** |

## Strict JSON output validation (Attempt-6 correction)

`tests/test_claude_code_hook_wrapper.py::StrictOutputValidationCases` proves
brace-wrapping alone is not proof of a real decision — every case below is
brace-shaped and would have passed Attempt 5's shell pattern check, but must
still be blocked under strict, independent validation:

| Case | Result |
|---|---|
| `{not-json}` (brace-wrapped, invalid JSON) | blocked |
| `{"decision":"allow"}` (valid JSON, unsupported decision value) | blocked |
| `{"decision":"block","reason":"","decision":"allow"}` (duplicate key — a naive parser resolves this to "allow") | blocked |
| `{"unexpected":true}` (valid JSON, unrecognized shape) | blocked |
| Block shape missing `reason`, or with an extra key, or wrong `reason` type | blocked (each independently) |
| Context shape missing `additionalContext`, with an extra key, wrong `hookEventName`, or wrong `additionalContext` type | blocked (each independently) |
| `{"decision":"block","reason":NaN}` (non-finite constant, a non-standard JSON extension some parsers accept) | blocked |
| Exact gate-owned block shape, byte-for-byte | passes unmodified (control) |
| Exact gate-owned context shape, byte-for-byte | passes unmodified (control) |

## Empty/truncated-gate process-boundary fault injection (Attempt-5 correction)

`tests/test_claude_code_hook_wrapper.py` adds coverage for the class of
failure that exit-status checking alone cannot see — a gate that runs
cleanly (exit 0) but never produces a real decision:

| Case | Result |
|---|---|
| Empty (zero-byte) gate file | wrapper prints `{"decision": "block", ...}`; stderr names "empty or malformed output" |
| Gate file with only a comment (truncated-write shape) | same block decision |
| Gate exits 0 with non-JSON garbage stdout | wrapper's own block decision is emitted; the garbage is **not** forwarded |
| Gate exits 0 with truncated JSON (`{"decision": "bl`) | wrapper's own complete block decision is emitted; the fragment is **not** forwarded verbatim |
| Healthy configured operator prompt (real gate) | now emits an explicit, non-empty, semantically inert decision (`hookSpecificOutput.additionalContext: ""`) instead of empty stdout — closing the one legitimate empty-output path the defect exploited |
| Healthy room WAKE (real gate + wrapper, trusted bypass) | `hookSpecificOutput.additionalContext` containing `source=PREATTENTION_BYPASS`, end to end through the actual wrapper |
| Healthy room BLOCK (real gate + wrapper, self-retention) | `{"decision": "block"}`, end to end through the actual wrapper |
| Unconfigured + broken gate, all four hook events | every event fully inert (empty stdout, exit 0) — explicitly tested per event, not just `user-prompt-submit` |

The test oracle `_cannot_be_interpreted_as_admission` was also corrected: it
previously treated empty stdout as safe/blocked, which is backwards — Claude
Code's actual UserPromptSubmit contract treats empty stdout at exit 0 as an
implicit allow. That inversion is exactly why the original defect was
possible; the corrected oracle now matches the real contract.

## Wrapper process-boundary fault injection (Attempt-4 correction)

`tests/test_claude_code_hook_wrapper.py` invokes the real
`nunchi-claude-v2-hook.sh` as a subprocess (never the Python gate directly)
with a *configured* policy and a deliberately broken/missing gate, and asserts
the wrapper's stdout can never be read as admission:

| Case | Result |
|---|---|
| Syntax error in gate | wrapper prints `{"decision": "block", ...}`; the crash traceback stays on stderr |
| Missing gate file | same block decision |
| Gate killed by signal (SIGKILL) | same block decision |
| Missing `python3` on `PATH` | same block decision, stderr names `python3 missing` |
| Gate exits nonzero but prints plausible-looking stdout | wrapper's own block decision is emitted; the gate's untrustworthy (nonzero-exit) stdout is **not** forwarded |
| Healthy gate, exit 0 | gate's exact decision passes through byte-for-byte |
| Unconfigured install, broken gate | fails open (empty stdout, exit 0) — inert installs are unaffected |
| `pre-tool`, configured, broken gate | exit `2` (unchanged fail-closed direction) |
| `stop` / `post-tool`, configured, broken gate | exit `0`, no output (unchanged fail-open direction, deliberate) |
| Real gate (not a stub), unresolvable policy path | wrapper forwards the real gate's own config-error block decision end-to-end |

## Adversarial regression coverage (Attempt-2 and Attempt-3 findings)

`tests/v2/test_claude_code.py::AdversarialRegressionCases` plus the reworked
`ActionGuardCases` prove, per finding:

| Finding | Proven by |
|---|---|
| F1 operational-error cannot create an unguarded privileged turn | `test_operational_error_wake_denies_privileged_effects` (forces a receipt-sink failure → degraded room-causal turn → privileged denied) |
| F2 identical privileged action replay cannot execute twice | `test_identical_privileged_action_replay_never_executes_twice` (both proposals denied) |
| F2 unknown authorization-audit persistence has zero effects | `test_authorization_audit_persistence_failure_has_zero_effects` (deny stands with the audit sink broken; no ALLOW written) |
| F2 room-caused privileged execution honestly unsupported+denied | `test_room_caused_privileged_execution_is_denied_unsupported`, `test_approval_bound_execution_is_unsupported_and_denied` |
| requester derivation binds the transport-attested origin | `test_requester_derivation_resolves_the_transport_attested_origin` |
| F3 cross-room replies/reactions denied before execution | `test_cross_room_reply_is_denied_before_execution`, `test_cross_room_reaction_is_denied_before_execution`, `test_in_room_reply_is_allowed` |
| F4 self events retained but never wake recursively | `test_self_event_is_retained_as_context_but_never_wakes` |
| F5 malformed/unsafe sidecar records fail closed; sidecar confidential | `test_malformed_sidecar_record_fails_closed`, `test_group_readable_sidecar_is_refused`, `test_symlinked_sidecar_is_refused`, `test_sidecar_default_path_is_owner_only_directory` |
| F6 patch target/backup symlinks rejected without touching referents | `test_apply_script_rejects_symlinked_target` (subprocess; referent bytes unchanged) plus the scratch-build symlink probes above |
| B1 configured channel event never passes un-gated on config/policy/state failure | `test_invalid_policy_blocks_prompt_and_denies_privileged` (prompt blocked + degraded marker + mapped Bash denied), `test_state_failure_blocks_prompt_fail_closed` |
| B2 foreign-room events declined, not an entry point | `test_foreign_room_declined_and_privileged_denied` (prompt blocked + room-action denied + privileged denied), `test_foreign_room_does_not_clobber_a_healthy_bound_turn`, `test_operator_prompts_pass_but_foreign_rooms_are_declined` |
| B3 sidecar containing directory must be owner-only 0700 non-symlink | `test_group_readable_sidecar_directory_is_refused`, `test_symlinked_sidecar_directory_is_refused`; transport-side dir validation asserted in `test_transport_patch_provenance_is_pinned_and_fail_closed` |

## Scene outcome index

| Scene | Deterministic outcome | Live outcome |
|---|---|---|
| CC-01 reactive bot hearing | PASS — `reactive-bot-hearing.jsonl` (exact bot author, literal content, actor kind `bot`, one classifier call) | NOT RUN live (see Blocked live scenes) |
| CC-02 Station scars | PASS — six scar rows in `scene-results.jsonl`: every scar reached the classifier verbatim, one call each, zero deterministic suppressors | Not applicable live (replay corpus) |
| CC-03 attention routing | PASS — one engine invocation per ordinary opportunity; effective SUPPRESS stops only the wake and retains the event; classifier-DEFER and margin-DEFER valves distinct; trusted bypass zero classifier calls with `classifier_not_invoked` and trusted provenance present; forged in-content bypass rejected; operational error wakes `ERROR_FALLBACK` with no fabricated verdict | NOT RUN live (classifier unconfigured) |
| CC-04 direct act-or-silence | PASS — message/reaction contributions produce `participant-host`(sent) then observed `transport`(sent); silence produces `outcome=silent` and no transport stage; failed delivery recorded `failed`; meta-answer prose recorded verbatim and graded only post-hoc; zero send-time social calls; stages singly attested | NOT RUN live (outbound send denied) |
| CC-05 later hearing / restart | PASS — suppressed event hearable next opportunity; burst coalesces to one fresh successor; restart drops the pending anchor, keeps retained context, fabricates no receipts; cold wake DECLARED unsupported | Live restart NOT RUN |
| CC-06 installed provenance | PASS — `installed-runtime.md`: full component digests, plugin base/patch states, registration state, two installed-hook probes | Installed probes ARE live-host evidence; room-live probe NOT RUN |

## Blocked live scenes — exact blockers

All room-live scenes were prepared but could not be executed from this session;
none are claimed:

1. **Transport patch application and hook registration** on the installed host
   are operator-gated: this autonomous session's permission classifier denied
   `apply-transport-patch.sh` against the plugin directory (including
   `--verify`), `settings.json` modification, and outbound Discord sends.
   Those denials are correct boundaries, so live reactive delivery, other-bot
   hearing, delayed-turn freshness with intervening events, live silence, live
   send, cross-room rejection, privileged-action denial, and driver
   restart-without-replay could not run against a live gateway.
2. **No authorized non-self sender was active**: peer agents (Aleph lane) were
   stood down under the operator's 2026-07-19 freeze and the operator was not
   present in the room during this session, so no genuine inbound event was
   available even for passive capture.

The Attempt-2 fixes are fully proven deterministically (including adversarial
reproduction of every rejection finding); the live ladder awaits the operator
arming steps in `installed-runtime.md`. State, receipts, and the transport
sidecar accumulate durably under `/Users/zmll/.claude/nunchi/` for packet
supplementation once armed.
