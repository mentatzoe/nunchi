# Slice 050 Discord-transport source freeze

**Review status**: SUCCESSOR FROZEN FOR INDEPENDENT SOURCE RE-REVIEW

**Effective successor implementation commit**: `b46bc8a0fbba18a3af0fb401aefa431f1e953302`

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

## Successor closure and remaining lifecycle boundary

The successor closes every source defect reported on the prior heads and now
includes native fixtures, deterministic replay material, the product guide, DT
scene results, a clean-installed `mcp==1.28.1` record, and an evidence manifest.
Replay-store exhaustion is supervised as global continuity failure, known
gateway restart gaps remain in signed history coverage, and event-limit
truncation is established by a one-extra bounded probe. The exact 31-file
source/test/doc/eval surface is pinned below.

Live DT-07 mixed-room evidence is truthfully `NOT_RUN` because no authenticated
Discord credential was available to this review process. Source approval and
installed-runtime verification are deliberately decoupled from that remaining
lifecycle gate: this PR does not claim `HANDOFF_READY` or `ACCEPTED`.

## Review requirements

1. Verify every listed SHA-256 and Git blob against successor implementation
   commit `b46bc8a0fbba18a3af0fb401aefa431f1e953302` and confirm the PR does not move.
2. Run the focused ordinary and clean-installed SDK commands recorded in
   `evidence/v2/discord-transport/installed-runtime.md` and the deterministic
   replay runner `python3 -m evals.v2.discord_transport.runner`.
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
