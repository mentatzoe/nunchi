# Claude Code V2 — verification index

**Attempt 2**, recorded 2026-07-20, `v2-claude-owner` lane. Attempt 1's index
is preserved in git at candidate `6476b58`. Every command below was run on the
Attempt-2 candidate `199012901278777750671f4fc0731b779e91c2b8`; results are
quoted exactly.

## Deterministic commands and results

| Command | Result |
|---|---|
| `python3 -m unittest tests.v2.test_claude_code` | `Ran 46 tests … OK` |
| `python3 -m unittest tests.test_no_home_writes tests.test_sentinel_forgery tests.test_no_second_judgment tests.v2.test_claude_code` | `OK` |
| `python3 -m unittest` (full offline baseline) | `Ran 1167 tests in 23.5s — OK (skipped=7)` |
| `python3 scripts/check_governance.py --check-cli` | `governance boundary + CLI: OK (SpecKit 0.12.11)` |
| `PYTHONPATH=src:. python3 -m evals.v2.claude_code.run_scenes --out-dir <tmp>` | `cc-scenes: 20 rows, 19 PASS, 1 declared limitations` (two independent runs to separate temp dirs produced byte-identical JSONL) |
| `git diff --check` (staged Attempt-2 tree) | clean (a scoped `transport-patch/.gitattributes` exempts generated patch files, whose blank-context lines are single spaces by unified-diff format) |
| Patch reproducibility (scratch build): `git apply --check 0001 && git apply 0001 && git apply --check 0002 && git apply 0002` onto pinned base `c3c79c65…` | `BOTH APPLY CLEAN`; result digest `67900f7e…` equals the pinned target; `bun build` of the patched file exits 0 |
| Installer safety: apply against a symlinked target / rollback against a symlinked backup | exit 2 each, `symlink; refusing to follow`, referent bytes unchanged |

## Adversarial regression coverage (Attempt-2 rejection findings)

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
