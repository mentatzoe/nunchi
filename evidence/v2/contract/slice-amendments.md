# Slice 010 accepted-amendment ledger

Canonical, append-only record of every accepted post-acceptance amendment to
slice `010-v2-contract`. This file exists so downstream slices have a single
machine-checkable source for "which exact candidate commit is currently
effective for interface X," without a validator needing to parse the
narrative `amendment-A*.md` records (which also contain rejected drafts,
freshness corrections, and prose not meant for mechanical consumption).

This ledger never revises `slice-candidate.md`, `slice-handoff.md`, or
`slice-acceptance.md`. Those remain pinned to the terminal attempt-6 accepted
candidate `bff6b463a44c1b9066fc654691042f9550da6c64` forever. An amendment
changes only the *effective* commit a new dependent must bind to for the
amended interface; it never reopens or reauthors slice 010's own acceptance.

Each record below documents one accepted amendment, in acceptance order.
`Prior effective commit` must equal the terminal accepted candidate for the
first record, and the immediately preceding record's `Amendment candidate
commit` for every record after that — this is what lets a validator confirm
the chain is unbroken without trusting any single record in isolation.

## Amendment A1 — ACCEPTED

**Slice**: `010-v2-contract`

**Amendment ID**: A1

**Status**: ACCEPTED

**Amended interface**: I-010E

**Prior interface version**: @1

**New interface version**: @2

**Prior effective commit**: `bff6b463a44c1b9066fc654691042f9550da6c64`

**Amendment candidate commit**: `817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`

**Amendment decision commit**: `30aba09f13a6752b4c24811da0d8ec772a9d9682`

**Accepted by**: v2-integrator

**Accepted on**: 2026-07-19

**Decision reference**: `evidence/v2/contract/review-2026-07-19-v2-integrator-amendment-A1-revised.md`

**Amendment record**: `evidence/v2/contract/amendment-A1-receipt-policy-provenance.md`

## Amendment A2 — ACCEPTED

**Slice**: `010-v2-contract`

**Amendment ID**: A2

**Status**: ACCEPTED

**Amended interface**: I-010B

**Prior interface version**: @1

**New interface version**: @2

**Prior effective commit**: `817394d6cd4aa17fc47d7a89ebb8c8d974c595eb`

**Amendment candidate commit**: `26a6b531fa146ba1f1f5fcd1c4d191041b141301`

**Amendment decision commit**: `d504310c61a93afbe57d4fe4ed05e93055c75555`

**Accepted by**: v2-integrator

**Accepted on**: 2026-07-19

**Decision reference**: `evidence/v2/contract/review-2026-07-19-v2-integrator-amendment-A2-revised.md`

**Amendment record**: `evidence/v2/contract/amendment-A2-decision-margin-boundary.md`

## Current effective dependency commit

`26a6b531fa146ba1f1f5fcd1c4d191041b141301` — carries I-010A @1, I-010B @2,
I-010C @1, I-010D @1, I-010E @2. Any slice depending on 010 must record
exactly this commit (not the terminal `bff6b463...`) in its own activation
evidence, and cite this ledger's A1/A2 records — not the terminal
acceptance alone — as the authority for that binding.
