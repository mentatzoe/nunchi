# Discord V2 source successor handoff

**Candidate implementation:** `c95ea79e952bcf7803b54d24ba84485ba9ff0804`

**Status claimed:** exact source/clean-installed-runtime re-review ready. This
record does not claim slice `HANDOFF_READY` or `ACCEPTED`; DT-07 live mixed-room
evidence is explicitly `NOT_RUN`.

The successor closes the original source findings: one exact process binding;
READY-attested self identity; subscribe-before-backfill barrier and bounded SSE
replay; exact gateway lineage and gap boundaries; durable pre-effect request
claims; enforced message nonce; bound I-010D continuation; actual worker-future
drain; nested fact cross-binding; shared Discord rate buckets; and closed social-
control-free action objects; supervised global replay-store exhaustion; known-
gap history coverage; honest one-extra event truncation; conservative process-
epoch taint; and explicit fresh-IDENTIFY boundaries.

Verification results:

- focused ordinary environment: `141` passed, `5` SDK-absent skips;
- complete offline suite: `1275` passed, `9` skipped;
- clean-installed `mcp==1.28.1` packet suite: `141` passed, `1` mutually
  exclusive missing-SDK skip;
- deterministic replay: `7/7` scenes passed.

Documentation disposition:

- `UPDATE`: `integrations/mcp-discord/README.md`
- `UPDATE`: `integrations/mcp-discord/DESIGN.md`
- `UPDATE`: `docs/transport/discord-v2.md`
- `HANDOFF`: global current-state wording remains with `v2-integrator`; no
  partial V2 current-state claim was added to `README.md`.
