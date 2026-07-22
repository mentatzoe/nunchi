# V2 slice 040/050 composition evidence

This record is integration evidence for the source composition in pull request
[#19](https://github.com/mentatzoe/nunchi/pull/19). It is not a slice lifecycle
acceptance, a DT-07 live result, or a V2-to-main cutover claim.

## Provenance

- Integration base before composition: `adc8b645791e217eea5d4704a5fcb53be1e18e38`
- Approved slice 040 source head: `7ec446a5dd09a3cbd8314fc12aaec49864290842`
- Approved slice 050 source head: `f24d12e471bca77cb02594b46374f78f6955d981`
- Initial combined candidate: `3ec310eb5c460f162e7732287bfb84f2ba8e99f3`
- Aleph exact-head review: `CHANGES_REQUESTED` on 2026-07-22T08:04:15Z
- Composition repair commit: `46fef4f6580efe451e37e8ea39fedb40d8780615`

The initial candidate preserved both approved source projections exactly. The
review then found two cross-surface defects that were not visible in either
slice's isolated checks: the Discord continuation was dropped before the
participant host, and bootstrap/local history omissions were erased from
coverage.

## Repair

The successor:

- retains a transport-issued continuation only when its participant, room,
  continuity scope, and trigger bind the accepted event exactly;
- carries that capability into attention and participant snapshots while
  keeping opaque authority out of classifier projection;
- gives the participant host, not Codex, the authenticated `read_history`
  callback;
- permits Codex to return only a schema-valid, bounded context request, which
  `ParticipantTurn.fetch_context()` validates and the host serves before the
  same Codex thread continues;
- caps expansion at eight rounds inside the original turn deadline and keeps
  Codex without MCP credentials or direct tool authority; and
- validates bootstrap event/byte counts and monotonically preserves remote and
  local truncation in later coverage.

The cross-slice reproduction now begins with a real
`DiscordEventSourceV2.notification_params()` continuation, passes through
`CodexRoomV2` and `ParticipantTurn.fetch_context()`, invokes authenticated
`read_history`, validates the I-010D page, and returns it to the participant.
The test also confirms that the classifier projection does not contain the
opaque handle.

## Verification

Run from the exact repair commit:

```text
python3 -m unittest -v tests.v2.test_codex tests.v2.participant.test_host tests.v2.test_discord_transport
Ran 91 tests — OK

env -u HERMES_HOME -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 python3 -m unittest
Ran 1287 tests — OK (skipped=9)

python3 -m evals.v2.discord_transport.runner
7/7 deterministic scenes — PASS

python3 scripts/check_governance.py --check-cli
governance boundary + CLI: OK (SpecKit 0.12.11)
```

A clean temporary virtual environment installed `.[mcp-discord]`. From an
external copied test tree, the same 91 focused tests passed and the packaged
`nunchi.integrations/codex_participant_action.schema.json` resource was present
under site-packages.

`git diff --check` and JSON parsing of the structured-output schema also
passed. No live Discord ladder, installed participant-runtime acceptance,
slice `HANDOFF_READY`/`ACCEPTED`, main merge, or cutover is asserted here.

## Event-cap truncation successor

Aleph re-reviewed exact head
`2270c714f1d4ad9d1f73071d4cd57e11a964c18b` in review `4752659661` and found
that an event-saturated bootstrap could still claim complete coverage: the
producer asked Discord for exactly its event cap, leaving no evidence that an
older suffix existed. Repair commit
`bb01e85e5a7fa8232a0b2c1da272d8ec53d384f3` closes that producer-to-consumer
boundary.

The bootstrap now requests one extra event below Discord's 100-message edge
and performs one bounded `before=oldest` probe at that edge. Its closed coverage
reports distinct `events` and `bytes` truncation causes. `CodexRoomV2` validates
those causes, unions them with local omissions without duplicates, and carries
them into participant coverage.

The new regression begins with a two-message authoritative REST dataset and a
one-event bootstrap cap, observes the producer request `limit=2`, then passes
the result through `CodexRoomV2.backfill()` and a live participant turn. The
participant receives `has_more_before=true` and `truncated_by=["events"]`. A
separate test proves the bounded second probe at Discord's 100-message edge.

Verification at the repair commit:

```text
Focused composition/participant/Discord suite: 95 tests — OK
Clean installed wheel from an external test tree: 95 tests — OK
Complete deterministic suite: 1291 tests — OK (skipped=9)
Discord replay: 7/7 — PASS
Governance boundary + CLI: OK (SpecKit 0.12.11)
git diff --check: OK
```

This appended result has the same scope limits as the earlier record: it does
not claim DT-07, installed-runtime acceptance, a slice lifecycle transition,
main merge, or cutover.
