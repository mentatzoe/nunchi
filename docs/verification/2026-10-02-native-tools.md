# Native tool invocation checkpoint — 2 October 2026

Implemented and locally verified; not a complete V2 release or live adoption.

The configured-route blanket tool denial is replaced by an invocation boundary
inside the existing stock tool-execution middleware. The callback receives the
exact final arguments after upstream middleware. Before calling it, Nunchi
checks the opportunity and persists an unknown-effect claim bound to participant,
actor, room, origin event, request, generation, configuration revision, tool name,
argument digest, and native session/turn/tool-call identifiers. A duplicate native
identity is refused, including after reopening the ledger. Arguments themselves
are not stored. A second lifetime check follows persistence.

Native `next_call` still runs Hermes's own policy, approval and tool handler.
Returned values and raised exceptions update invocation status only: neither
proves whether an effect happened. No automatic retry of an ambiguous invocation
is permitted. The private SQLite ledger is stored beside the room journals.

## Private host dependencies

- Native `hermes_cli.middleware.run_tool_execution_middleware` and its identity
  keywords; unknown/missing identity fails closed on a configured route.
- `tools.interrupt.set_interrupt(active, thread_id)` and native polling. Only
  registered in-flight threads are interrupted under their deregistration lock.
  Nunchi never clears the shared bit: native turn/worker teardown owns reset, so
  the plugin cannot erase a concurrent `/stop`.
- Hermes 0.19.0: `tools.approval._await_gateway_decision`, checked signature and
  interrupt polling, wrapped before/after its native wait.
- Hermes 0.21.5: `tools.approval_gateway_wait._poll_event`, reached through the
  exact helper bound in `tools.approval`. Both leader and coalesced follower
  waits use this global. An expired result becomes native `interrupted`, not an
  invented approval or a user refusal.

Registration uses the existing attribute transaction, so rollback/unload restores
the native function. Unknown private shapes refuse activation. An unrelated
stock route falls through unchanged.

Cancellation is cooperative. An already-committed handler that neither waits for
approval nor polls the native interrupt may continue after expiry. Its effect
remains unknown. This does not claim a sandbox or zero syscalls after deadline.

## Executed checks

- Eleven focused native invocation/approval tests pass, including both private
  wait shapes, replay after reopening, native denial, exceptional return,
  persistence failure/expiry, argument snapshotting and orphan-route rejection.
- Canonical `python -m unittest`: 663 tests, OK, seven expected installed-host
  skips (four contract tests and three normal-turn classes). Eval inventory and
  `git diff --check` pass. This run does not resolve the separately tracked
  intermittent shared-foundation timing fixtures.
- Built wheel SHA256:
  `c934ef8478a35145f920836a9a18dc026d2f556d5933248ee9a6d1cb52dab3a1`.
  Noneditable Nunchi installs on stock 0.19.0 (Python 3.11) and stock 0.21.5
  (Python 3.13, supported source-installed host). Plugin source is not on
  `PYTHONPATH`; native guard probes use `python -I`.
- `scripts/probe_native_approval.py` reaches each real host's
  `check_all_command_guards`, queues and wait through the installed plugin
  wrapper. Five cases on each host pass: approve, deny, approve after expiry,
  interrupt, and unconfigured fall-through. Queues empty afterward and exact
  attribute rollback passes. No command is executed. The opportunity state and
  human answer are controlled; native approval internals are not mocked.
- Installed minimum-host normal-turn suite: 20 tests, 18 pass and two fail.
  Native read_file, parked terminal approval followed by `/approve`, final send
  receipt, peer routing, auth rejection, SUPPRESS, `/stop`, deadlines, delivery
  failure and unconfigured fall-through pass. The two failures are default
  attention trust and leaked native session ownership; separate repairs are in
  progress. Network boundaries use a loopback model and fake Discord client,
  not live provider/platform credentials.

The current-host loader repair must land before complete current normal-turn
acceptance. Shared attention ACK reaction capability is still missing; a final
message's send acknowledgement is not that feature. Other lifecycle exclusions,
exact combined-artifact independent review, CI and canonical landing remain
required before V2 completion. No live gateway/profile was changed.

Raw logs are retained on delivery task `t_7041b201` under `evidence/native-*`.
The earlier `native-installed-minimum-r1.txt` is a harness failure (resolving a
venv Python symlink selected the base interpreter); r2 is the corrected real
installed-host run, not a retry that changed product assertions.
