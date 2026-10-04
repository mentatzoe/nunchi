# Shared deadline fixture reconstruction

The prior reviewed fixture commits `9634a4f` / `efb1ee7` were not available
in the surviving owner Git objects after the reviewer scratch clone was
cleaned. The review report remains attached to Kanban task `t_ebd25bd4`.
This is a new reconstruction from that report, NOT a byte-for-byte recovery
and NOT automatically covered by the old review verdict.

Only the two `AttentionAndHostTests.test_host_total_deadline_*` fixtures
change. Product source and policy-race regression tests are untouched.

- Native wait: transport advances a controlled module clock through the
  unchanged 0.05-second budget, parks on an Event, and must still be parked
  when the host returns unknown and closes its scheduler.
- Whole opportunity: attention, participant, transport advance that clock to
  1000.04 / 1000.08 / 1000.12 against the unchanged 0.10-second budget. The
  host must return unknown with the participant cancellation Event set.
- Both require exactly one native call and stable receipts after releasing
  and joining the late native worker. Two-second watchdogs are cleanup
  bounds, not product-latency assertions. Queue/Event clocks remain real.

Commands, from the repository with its development interpreter:

    python -m unittest tests.v2.test_shared_foundation tests.v2.test_shared_deadline_race -q
    python scripts/verify_shared_deadline_fixtures.py
    python -m unittest

Observed: 68 focused tests passed; 300 repeated fixture executions passed;
budget-reset and two native-wait/late-result mutation cases each failed on
`unknown != sent`; no native/participant worker leaks. Canonical suite passed
with its explicit optional integration skips. Raw execution logs are in the
owner workspace evidence/recovered-fixtures-{focused,mutation,canonical}.txt.

The initial reconstruction mistakenly looked up participant `cancel_event`
rather than the defined callable argument `cancel`; the focused test exposed
that as failed delivery. Corrected by inspecting the real invocation signature.
No product behavior was changed to make a test pass.

This artifact needs a new independent exact-delta review before publication.
