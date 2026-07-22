# Discord V2 source successor handoff

**Candidate implementation:** `b46bc8a0fbba18a3af0fb401aefa431f1e953302`

**Status claimed:** exact source/clean-installed-runtime re-review ready. This
record does not claim slice `HANDOFF_READY` or `ACCEPTED`; DT-07 live mixed-room
evidence is explicitly `NOT_RUN`.

The successor closes the original source findings: one exact process binding;
READY-attested self identity; subscribe-before-backfill barrier and bounded SSE
replay; exact gateway lineage and gap boundaries; durable pre-effect request
claims; enforced message nonce; bound I-010D continuation; actual worker-future
drain; nested fact cross-binding; shared Discord rate buckets; and closed social-
control-free action objects; supervised global replay-store exhaustion; known-
gap history coverage; and honest one-extra event truncation.

Verification results:

- focused ordinary environment: `139` passed, `5` SDK-absent skips;
- complete offline suite: `1273` passed, `9` skipped;
- clean-installed `mcp==1.28.1` packet suite: `139` passed, `1` mutually
  exclusive missing-SDK skip;
- deterministic replay: `7/7` scenes passed.

Documentation disposition:

- `UPDATE`: `integrations/mcp-discord/README.md`
- `UPDATE`: `integrations/mcp-discord/DESIGN.md`
- `UPDATE`: `docs/transport/discord-v2.md`
- `HANDOFF`: global current-state wording remains with `v2-integrator`; no
  partial V2 current-state claim was added to `README.md`.
