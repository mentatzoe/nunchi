# Hermes V2 deterministic replay inventory

This directory contains the complete offline scenario inventory for slice 060.
It validates fixture completeness, deterministic oracle behavior, exact manifest
digests, and explicit expected outcomes for ingress, identity, attention,
scheduling, lifecycle, receipts, capability decisions, and Discord/Telegram
route normalization.

Run it with:

```bash
python3 -m evals.v2.hermes.runner \
  --mode replay \
  --manifest evals/v2/hermes/manifest.json \
  --require-complete
python3 -m unittest tests.v2.test_hermes_replay_runner_060
```

The runner emits one machine-readable JSON document. `--require-complete` fails
when any required scenario is absent, duplicated, malformed, or does not match
its declared expected result.

## Evidence boundary

This is a deterministic **fixture replay oracle**, not executable-source,
installed-artifact, Discord, Telegram, or live-runtime evidence. The manifest
and emitted report hard-code that boundary:

```json
{
  "source_behavior": false,
  "installed": false,
  "live": false
}
```

Source tests, clean wheel installation, native platform scenes, and
exact-candidate review remain separate mandatory gates in
`specs/060-v2-hermes/acceptance.md`.
