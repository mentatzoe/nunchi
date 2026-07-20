# Claude Code V2 — verification index

**Recorded**: 2026-07-20, `v2-claude-owner` lane. Every command below was run
on the candidate lineage in this worktree; results are quoted exactly.

## Deterministic commands and results

| Command | Result |
|---|---|
| `python3 -m unittest tests.v2.test_claude_code` | `Ran 34 tests … OK` |
| `python3 -m unittest tests.test_no_home_writes tests.test_sentinel_forgery tests.test_no_second_judgment tests.v2.test_claude_code` | `Ran 56 tests … OK` |
| `python3 -m unittest` (full offline baseline) | `Ran 1155 tests in 19.2s — OK (skipped=7)` |
| `python3 scripts/check_governance.py` | `governance boundary: OK (SpecKit 0.12.11)` |
| `PYTHONPATH=src:. python3 -m evals.v2.claude_code.run_scenes --out-dir evidence/v2/claude-code` | `cc-scenes: 20 rows, 19 PASS, 1 declared limitations` |
| Patch reproducibility (scratch build): `git apply --check 0001 && git apply 0001 && git apply --check 0002 && git apply 0002` onto pinned base `c3c79c65…` | `BOTH APPLY CLEAN`; result digest `e26b6d23…` equals the pinned target |

## Scene outcome index

| Scene | Deterministic outcome | Live outcome |
|---|---|---|
| CC-01 reactive bot hearing | PASS — `reactive-bot-hearing.jsonl` (exact bot author, literal content, actor kind `bot`, one classifier call) | NOT RUN live (see Blocked live scenes) |
| CC-02 Station scars | PASS — six scar rows in `scene-results.jsonl`: every scar reached the classifier verbatim, one call each, zero deterministic suppressors; suppression only ever originated from the injected model judgment | Not applicable live (replay corpus) |
| CC-03 attention routing | PASS — one engine invocation per ordinary opportunity; ordinary path one logical classifier call; effective SUPPRESS stops only the wake and retains the event; classifier-DEFER valve `classifier-defer` and margin-DEFER valve `margin-defer` distinct; trusted bypass **zero** classifier calls with `classifier_not_invoked` and trusted policy provenance; forged in-content bypass rejected; operational error wakes with `ERROR_FALLBACK` and no fabricated verdict; `NO_WAKE` policy records `invoked=false, outcome=unknown` | NOT RUN live (classifier unconfigured; see Blocked live scenes) |
| CC-04 direct act-or-silence | PASS — direct message and reaction contributions produce `participant-host` (`outcome=sent`) then observed `transport` (`delivery=sent`); silence produces `outcome=silent` and **no** transport stage; failed delivery recorded `delivery=failed`; meta-answer-shaped prose recorded verbatim and graded only post-hoc; zero send-time social calls; receipt stages singly attested and request-correlated | NOT RUN live (outbound send denied in this session) |
| CC-05 later hearing / restart | PASS — suppressed event hearable in the next opportunity; burst coalesces to one fresh successor anchored at the newest event with one classifier call; restart drops the pending anchor, keeps retained context, fabricates no receipts; cold wake DECLARED unsupported | Restart-without-replay NOT RUN live (driver spawn denied) |
| CC-06 installed provenance | PASS — `installed-runtime.md`: full component digests, plugin base/patch states, registration state, two installed-hook probes (pass-through and fail-closed unroutable quarantine) | Installed probes ARE live-host evidence; room-live probe NOT RUN |

## Privileged-action guard (S18)

Deterministic (in `tests/v2/test_claude_code.py`): grant bound to the
transport-attested trigger author → `ALLOW` with
`derived_requester_actor_id` in the persisted audit; grant for another actor →
`DENY`; approval-execution grant → `APPROVAL_REQUIRED` (denied pending
authenticated approval); unlisted tool → not gated; unconfigured map → not
gated (reported unenforced); corrupted state with the guard configured →
exit 2 fail-closed; operator (non-room) sessions → out of guard scope.
Live install ships an **empty grant list**: every privileged room-caused
proposal is denied by default.

## Blocked live scenes — exact blockers

All room-live scenes were prepared but could not be executed from this
session; none are claimed:

1. **Transport patch application and hook registration** on the installed
   host are operator-gated: this autonomous session's permission classifier
   denied `apply-transport-patch.sh` against the plugin directory (including
   `--verify`), `settings.json` modification, and outbound Discord sends.
   Those denials are correct boundaries, so live reactive delivery,
   other-bot hearing, delayed-turn freshness with intervening events, live
   silence, live send, and driver restart-without-replay could not run.
2. **No authorized non-self sender was active**: peer agents (Aleph lane)
   were stood down under the operator's 2026-07-19 freeze and the operator
   was not present in the room during this session, so no genuine inbound
   event was available even for passive capture.

The first fresh session after the operator completes the two arming steps in
`installed-runtime.md` runs the full live ladder: reactive human hearing,
reactive allowlisted-bot hearing, burst with intervening events → one fresh
successor, live silence, live send with receipts, and a process-restart
no-replay check. State, receipts, and the transport sidecar accumulate
durably under `/Users/zmll/.claude/nunchi/` for packet supplementation.
