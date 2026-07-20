# Slice 020 acceptance-owner review — attempt 1

## Decision

**Slice**: `020-v2-observation`

**Candidate commit**: `7b00bcaa4a2b8af12b6eb71bf6d8b098f4cfeba7`

**Handoff-ready commit**: `a29d9625d5ccbdbca4d8d864c3cc79d7d5453a66`

**Reviewed by**: `v2-integrator` (`codex-session-2`), assigned by
`evidence/governance/assignments/codex-session-2-v2-integrator-2026-07-16.md`

**Reviewed on**: 2026-07-19

**Decision**: REJECT attempt 1. The HIGH around-cursor non-progression defect
and the MEDIUM continuation truncation-cause defect below are independently
confirmed against the exact candidate implementation.

The candidate and handoff-ready commits carry the identical
`src/nunchi/observation.py` Git blob:

```text
$ git rev-parse 7b00bcaa4a2b8af12b6eb71bf6d8b098f4cfeba7:src/nunchi/observation.py
78066ae228a254575ec6fb14a2230de2b52f01fe
$ git rev-parse a29d9625d5ccbdbca4d8d864c3cc79d7d5453a66:src/nunchi/observation.py
78066ae228a254575ec6fb14a2230de2b52f01fe
```

## Packet verification

The recorded packet commands were rerun independently before the decision:

| Command | Independent result |
|---|---|
| `PYTHONPATH=src:. python3 -m unittest discover -s tests/v2/observation -p 'test_*.py'` | 100 tests, OK |
| `PYTHONPATH=src:. python3 -m evals.v2.observation.run_scenes` | 5 suites, 32 rows, 0 FAIL |
| `PYTHONPATH=src python3 -m unittest tests.v2.observation.test_attempt6_corpus_conformance` | 5 tests, OK |
| `PYTHONPATH=src python3 -m unittest` | 1349 tests, OK, 4 skipped |
| `python3 -m evals.verdict_suite.runner --list` | 60 fixtures discovered |
| `python3 scripts/check_governance.py --check-cli` | `governance boundary + CLI: OK (SpecKit 0.12.11)` |
| `python3 scripts/check_governance.py --task-manifest specs/020-v2-observation` | T001–T054 initial/completed IDs; SHA256 `b305267271aed22a83c98c3a95e8f967edfbe080115d9ee58d6a99eacaca4536` |
| `git diff --check` | PASS, exit 0 |

These nominal passes do not refute the findings: the committed continuation
tests and eval runner paginate `before`, but do not paginate `around`, and no
continuation-fetch assertion distinguishes byte-cap from event-cap
`coverage.truncated_by`.

## Independent reproduction

Both findings were reproduced in one fresh Python process from the handoff
checkout, whose implementation blob is identical to the candidate as shown
above:

```sh
PYTHONPATH=src:. python3 - <<'PY'
from nunchi.observation import ContinuationProvider, serialized_byte_size
from tests.v2.observation.helpers import make_message, make_provider, seed_room


def room():
    provider = make_provider()
    seed_room(provider, [
        make_message(
            f"e{i}",
            "discord:1001",
            f"message {i}",
            timestamp=f"2026-07-17T01:00:0{i}Z",
        )
        for i in range(1, 6)
    ])
    return provider


provider = room()
continuation = ContinuationProvider(provider)
capability = continuation.issue(
    trigger_event_id="e3",
    max_events_per_fetch=2,
    max_bytes_per_fetch=8192,
)
request = {
    "request_id": "around-page-1",
    "handle_id": capability["handle_id"],
    "direction": "around",
    "anchor_event_id": "e3",
    "max_events": 2,
    "max_bytes": 8192,
}
page1 = continuation.fetch(
    request,
    host_context=capability["bound_to"],
    fetch_time="2026-07-17T01:30:00Z",
)
page2 = continuation.fetch(
    dict(request, request_id="around-page-2", cursor=page1["next_cursor"]),
    host_context=capability["bound_to"],
    fetch_time="2026-07-17T01:30:00Z",
)
print("AROUND_EVENT_CAP")
print("page1.events =", [event["id"] for event in page1["events"]])
print("page1.cursor_tail =", page1["next_cursor"].rsplit(":", 2)[1:])
print("page2.events =", [event["id"] for event in page2["events"]])
print("page2.cursor_tail =", page2["next_cursor"].rsplit(":", 2)[1:])
print("events_repeat =", page1["events"] == page2["events"])
print("cursor_repeats =", page1["next_cursor"] == page2["next_cursor"])

provider = room()
continuation = ContinuationProvider(provider)
one_event_bytes = serialized_byte_size(provider._events[0])
capability = continuation.issue(
    trigger_event_id="e3",
    max_events_per_fetch=6,
    max_bytes_per_fetch=one_event_bytes,
)
request = {
    "request_id": "around-byte-cap",
    "handle_id": capability["handle_id"],
    "direction": "around",
    "anchor_event_id": "e3",
    "max_events": 6,
    "max_bytes": one_event_bytes,
}
page = continuation.fetch(
    request,
    host_context=capability["bound_to"],
    fetch_time="2026-07-17T01:30:00Z",
)
print("AROUND_BYTE_CAP")
print("one_event_bytes =", one_event_bytes)
print("events =", [event["id"] for event in page["events"]])
print("coverage.truncated_by =", page["coverage"]["truncated_by"])
print("cursor_tail =", page["next_cursor"].rsplit(":", 2)[1:])
PY
```

Exact result:

```text
AROUND_EVENT_CAP
page1.events = ['e2', 'e3']
page1.cursor_tail = ['around', '3']
page2.events = ['e2', 'e3']
page2.cursor_tail = ['around', '3']
events_repeat = True
cursor_repeats = True
AROUND_BYTE_CAP
one_event_bytes = 156
events = ['e1']
coverage.truncated_by = ['events']
cursor_tail = ['around', '1']
```

## Findings

### H020-A1-01 — HIGH — `around` pagination ignores its incoming cursor and cannot progress

`ContinuationProvider.fetch()` reads the cursor at
`src/nunchi/observation.py:1166`. The `before` and `after` branches use it to
choose their starting index at lines 1172–1177, but the `around` branch at
lines 1178–1182 always reconstructs the same fixed anchor window and never
uses the cursor. When that window truncates, lines 1217–1226 mint an
`around` cursor from `next_index`; replaying that valid same-handle,
same-direction cursor passes validation and selects the original window again.

The independent event-cap reproduction served `e2,e3`, minted cursor tail
`around:3`, and then replayed the identical `e2,e3` page with the identical
cursor. This is an infinite non-progress loop and repeats exact event IDs
across sequential pages. It violates the slice's truthful bounded
before/after/around continuation requirement and FR-009 exact-event
deduplication across the continuation sequence; it also leaves SC-003's cursor
replay claim unproven for `around`.

Required RED→GREEN remediation:

1. Add a failing unit test that performs two same-handle, same-direction
   `around` fetches over `e1`–`e5`, anchored at `e3`, with an event cap of 2,
   and asserts page 2 does not overlap page 1 and either advances the cursor or
   exhausts it.
2. Add a matching continuation eval case and committed evidence row that
   actually follows the minted `around` cursor and fails on repeated events or
   a repeated non-progress cursor.
3. Make the `around` branch consume a validated cursor as its next scan
   position, while preserving anchor binding, authoritative order, side
   coverage, byte/event caps, and exact event-ID non-overlap across pages.
4. Rerun the complete observation, continuation-eval, repository, verdict,
   governance, task-manifest, and diff-check matrix and record the new result in
   append-only candidate/handoff evidence.

### M020-A1-02 — MEDIUM — continuation fetch misattributes byte truncation as event truncation

The page loop at `src/nunchi/observation.py:1187-1192` collapses two distinct
stop causes—`len(page_events) >= cap_events` and
`total_bytes + size > cap_bytes`—into the single `next_index` sentinel. The
page coverage at line 1246 then reports `['events']` for every non-null
`next_index`, regardless of which cap stopped the scan.

The independent byte-cap reproduction used an event cap of 6 over a five-event
room and a 156-byte cap that admitted only `e1`. Event capacity was not
exhausted, but the returned page reported `coverage.truncated_by = ['events']`
instead of `['bytes']`. This makes returned continuation coverage materially
false and violates FR-007/SC-002 truncation-cause honesty.

Required RED→GREEN remediation:

1. Add failing continuation-fetch tests for an event-only cap and a byte-only
   cap, plus a case where both limits are simultaneously reached if the
   implementation can truthfully report both.
2. Track the actual stop cause or causes independently from `next_index` and
   populate `coverage.truncated_by` with `events`, `bytes`, or both as the
   actual fetch conditions require.
3. Add/update continuation eval cases and committed evidence that assert the
   exact cause list, then rerun and record the complete verification matrix for
   the new candidate.

## Review boundary

This record is rejection evidence only. It does not accept the slice, integrate
the candidate, cut over V2, deploy, release, or promote anything. It changes no
product code, tests, evals, specification, plan, tasks, candidate record, or
slice declaration. The assigned `v2-observation-owner` separately returns the
declarations to `ACTIVE`, appends rework tasks as needed, and starts the new
bound delivery run required for a rejected completed handoff.
