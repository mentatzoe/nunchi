# ACK contention and Hermes operator diagnostics — 2 October 2026

The PR83 successor repairs scheduler-sensitive ACK tests and a real reservation
cleanup race. Ordinary stock Hermes tools and native approval still work; the
probe and current operator documentation now say so. This is source and
isolated installed-stock verification, not live-platform or complete V2 acceptance.

## Candidate and artifacts

- Baseline: `9682792ad8dd5202387c843b1a329a2c1b8251ec`.
- Source: the successor containing this record. Task `t_1bab30c0`'s frozen
  handoff and `successor-verification.json` name its exact commit and tree.
- Wheel: `nunchi-2.0.0-py3-none-any.whl`, SHA-256
  `6e7bd39ac698565549291d92a5e6ff4dc9136a0a85c0a2f73531d2cde9b4d2c4`.
- Author runtime: `openai-codex/gpt-6-astra`, from session startup, not the
  developer-b profile's default. Independent review is a separate fresh-context
  task; no cross-family review is claimed here.

The task artifacts include the wheel, an incremental Git bundle, raw logs,
control scripts and the machine-readable digest manifest. Evidence filenames
below refer to that archive's `evidence/` directory.

## Diagnosis and controls

The original reservation test timed synchronous receipt seeding and other-room
fixture construction as though they were the event loop's journal wait.
Slowing only the first seed by 110 ms reproduced the timer failure while real
journal operations and dispatch remained unchanged (`ack-slow-setup-red.txt`).
Moving setup before the measured deadline passes the same control
(`ack-slow-setup-green.txt`).

Reservation and settlement tests now observe entry into the real journal call,
yield a loop turn, and require the call still to be pending while its real lock
is held. Reservation additionally requires another room's successful dispatch
within 200 ms, deadline refusal within 350 ms, zero native calls and durable
replay suppression. Settlement acquires its lock after durable reservation at
native callback entry; it no longer races a sleeping lock-holder thread.
Deliberately running either real persistence attempt inline fails the progress
witness (`negative-reserve.txt`, `negative-settle.txt`); these are expected
negative-control failures, not unexplained test failures.

The fixture-only full-suite run then exposed a production race
(`3.11-fixture-only-red.txt`). `threading.Event.wait(timeout)` can return `False`
before the asyncio observer times out. Ignoring that return allowed the caller
to exit without owning the still-running reservation worker or its cleanup.
The repair treats this as abandonment, publishes worker error/readiness
atomically with the ownership decision, and schedules owned cleanup when an
error was already published before observer timeout or cancellation. Native
and persistence deadlines are unchanged.

Two deterministic regressions select those orderings while retaining real
journal locks, deadlines and writes. Replacing only the reservation function
with the exact predecessor yields three assertion failures: the normal False
return and the published-error timeout/cancellation subcases
(`ack-ownership-predecessor-red.txt`). Both tests pass on the successor
(`ack-ownership-green.txt`). The False-return control delays only the observer's
fallback timer, not the journal or dispatch deadline; otherwise local scheduler
overshoot can accidentally select only the asyncio timeout branch.

An adjacent RLock test assumed executor completion notification always preceded
a timer snapshot. The replacement waits for owned completion until the same
absolute writer cleanup deadline plus a bounded 500 ms observation allowance,
with the lock still held. Durable state must stay unchanged after release.
Delaying only executor notification fails the previous snapshot assertion and
passes the repaired test (`rlock-notification-red.txt`,
`rlock-notification-green.txt`). This does not extend the writer deadline.

## Verification

The final source matrix uses Python 3.11.15, 3.12.12 and 3.13.7 with the JSON
schema oracle installed. Each interpreter runs:

- `python -m unittest`: 768 tests, 30 explicit installed-host/opt-in skips;
- `python -m evals.verdict_suite.runner --list`;
- `python -m evals.verdict_suite.runner`: 11/11 deterministic scenarios;
- ten fixed repetitions of five ACK tests: reservation contention, settlement
  contention, False-return ownership, published-error timeout/cancellation,
  and bounded RLock ownership. No retry-until-green loop is used.

Logs are `{3.11,3.12,3.13}-{canonical,eval-list,eval-run,repeat}.txt`.
`compileall` and `git diff --check` also pass. The canonical skips do not stand
in for installed proof: the separate installed lanes below have no skips.

The same wheel was installed into private copies of two clean stock hosts:

| Host | Exact Hermes source | Normal/attention | Discord + Telegram contracts | Startup modes 0 + 1 |
|---|---|---|---|---|
| minimum 0.19.0 | `3ef6bbd201263d354fd83ec55b3c306ded2eb72a` | 32/32 | 4/4 each | 1/1 each |
| release 0.21.5 | `f97608f178d1ffeca59860195ab7da295f7c8e5f` | 32/32 | 4/4 each | 1/1 each |

Every installed lane records `EXTERNAL_ATTEMPTS []`, no skips, scrubbed
environments and isolated homes. The reviewed runner removes checkout package
imports, discovers the installed plugin normally, uses stock participant/tool/
approval code with a loopback model server, and captures platform output.
Ordinary-tool and native-approval tests assert the probe's corrected
`stock-hermes-with-nunchi-invocation-guards` value after observing actual native
behavior, while retaining false lifecycle completion and disabled-surface flags.
The earlier minimum-host probe red is `probe-red-minimum.txt`.

`integrity-before.json` and `integrity-after.json` verify unchanged stock source
against the pinned archives and unchanged installed Hermes RECORD files and
hashed members. The minimum comparison covers 6,737 source files and 942
RECORD-hashed files; release covers 15,075 source files and 15 RECORD-hashed
files (editable host, separately covered by the source comparison). All 58
wheel package members equal both source and each installed Nunchi package.
The full hashes are in the machine-readable task artifact.

## Operator audit and remaining work

The operator guide now separates package installation from profile activation,
restart, retained state and rollback. Code inspection confirms:

- plugin disable needs process restart to remove existing process-local guards;
- the dashboard installer migrates only its safely attributed legacy bridge,
  not V1 config or state;
- no automatic V1 state converter or complete Hermes user-data uninstaller
  exists; package uninstall does not remove bridges, journals, configs or
  private backups, and the shared uninstall command is not a Hermes uninstaller;
- attention setup's private-backup procedure remains the trust rollback path.

These missing mechanisms are reported to the delivery owner, not implemented
as an unrelated refactor. The exact predecessor wheel and matching config/state
must be retained; do not clear journals to force replay or assume arbitrary old
wheels understand new state. Disable and return to stock when compatibility is
not verified. Package rollback cannot undo native effects already issued.

The probe still reports `complete_v2_lifecycle: false`. Native Hermes authority
is retained: invocation claims are not atomic universal external-effect
authority, and a journal `finish` is a callback result, not external-effect
confirmation. Typing, voice, media, detached commands and other-platform gaps
remain required work. Moving-main CI on the predecessor proves contracts only.
This successor still needs independent exact-artifact review, owner-published
CI and incremental PR83 landing. Live first-save/restart, native platforms,
current-main normal turns, release/adoption and whole-V2 acceptance remain open.
