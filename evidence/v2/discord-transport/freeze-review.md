# Slice 050 Discord-transport source freeze

**Review status**: FROZEN FOR INDEPENDENT SOURCE REVIEW

**Effective source commit**: `adc8b645791e217eea5d4704a5fcb53be1e18e38`

**Pre-surface comparison commit**: `09e204a`

**Audit-only base branch**: `codex/review-base-v2-050`

**Frozen review branch**: `codex/freeze-v2-050`

This packet projects the current effective slice-050-owned source, focused
tests, and owned operator/design documentation into a narrow GitHub diff. It
does not rewrite the integration candidate and is not a merge vehicle. Review
approval or rejection applies only to the exact frozen bytes listed in
`frozen-files.sha256`.

## Included surface

- `src/nunchi/mcp_discord/`
- `tests/v2/test_discord_transport.py`
- `integrations/mcp-discord/README.md`
- `integrations/mcp-discord/DESIGN.md`

These are the effective implementation, focused-test, and existing owned-doc
paths assigned to slice 050 by
`specs/050-v2-discord-transport/plan.md`. The manifest also pins the unchanged
`ws.py` member of the owned package even though it does not appear in the PR
diff.

## Known packet gaps exposed for review

The effective integration commit contains no `tests/fixtures/v2/discord/`, no
`evals/v2/discord_transport/`, no product guide at
`docs/integrations/discord-mcp-v2.md`, and no pre-existing transport scene,
installed-runtime, mixed-room, or manifest evidence under
`evidence/v2/discord-transport/`. This freeze records those absences rather
than manufacturing completion evidence. Reviewers should report any missing
claim support or ordinary-path requirement as a finding.

## Review requirements

1. Verify every listed SHA-256 and Git blob against effective source commit
   `adc8b645791e217eea5d4704a5fcb53be1e18e38` and confirm the PR does not move.
2. Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v
   tests.v2.test_discord_transport`.
3. Adversarially inspect exact actor/self/room binding, canonical
   authorization before observation, raw event identity and relation
   preservation, ordering/deduplication, resume and gap recovery, bounded
   history/continuation, malformed or coercible native facts, and capability
   honesty.
4. Exercise send/reply/react/history authorization, privileged-action
   provenance, rate limits, request correlation, exact receipt persistence,
   cancellation/timeout/unknown outcomes, and zero send-time social
   reclassification.
5. Check cross-parameter policy, participant, room, session, connection,
   cursor, and restart binding. Green focused tests are not sufficient.
6. Return evidence-backed Critical/High/Medium findings with exact file:line
   references and reproduction results. Do not edit or merge this audit PR.

## Dependency and downstream note

Hermes and Claude Code already contain these source bytes in their ancestry.
Their work remains paused for new integration claims until this exact surface
is reviewed. A review result does not itself establish slice lifecycle
acceptance, installed-runtime parity, or mixed-room proof.
