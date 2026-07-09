# Codex Integration Adversarial Review — 2026-07-09

Scope: Codex room runner, inbound `UserPromptSubmit` hook, outbound
`PreToolUse` send gate, repo Codex plugin bundle, and operator docs.

Baseline compared: Hermes `nunchi-gate` plugin philosophy:

- channel-scoped rollout and configurable identity
- explicit agent id, mention id, and aliases
- true PASS suppression
- inspected history in the gate payload
- receipts outside the conversation surface
- configurable fail policy by surface
- outbound amplification guard

Codex parity state after review:

- Room wakes are gated before `codex exec`; `PASS` writes a receipt and does
  not wake Codex.
- The runner is configurable through TOML and env, including channel ids,
  bot/self id, agent id, mention id, aliases, history size, binaries, timeouts,
  fail policy, and Codex args.
- Configured channels are backfilled through `read_history` before streaming.
- The inbound hook blocks channel-tagged `PASS` prompts and fail-opens for
  operator safety.
- The outbound hook gates supported `send_message` / `reply_message` MCP
  sends, denies missing or stale Nunchi room context, denies a second send for
  the same admitted context, and fail-closes by default on gate errors.
- The plugin bundle packages the hooks and a streamable-HTTP MCP config for
  the local `nunchi-discord` transport; the repo marketplace exposes it as
  `nunchi-codex@local-repo`.

Findings fixed in this review:

1. Stale room context reuse: the outbound hook accepted any prior
   `<nunchi_context>` in the transcript. It now accepts context only from the
   latest user turn.
2. Repeated send for one admitted context: the outbound hook would allow a
   second `send_message` for the same wake. It now denies subsequent sends
   after a prior room send for that context.
3. Direct Discord webhook bypass: Bash webhook sends were not in the default
   direct-send detector. The default pattern now denies Discord webhook API
   sends as well as channel-message API sends and `nunchi-discord` shell paths.
4. Context-tag injection: room text containing `<nunchi_context>` could create
   extra literal tags in the wake prompt. The runner now escapes untrusted
   display fields and encodes angle brackets inside the hidden context JSON.
5. Hook env crash: invalid numeric hook env values crashed at import time. The
   hooks now fall back to safe defaults and continue through their documented
   decision paths.

Offline verification run during review:

```sh
PYTHONPATH=src python3 -m unittest \
  tests.test_codex_prompt_gate \
  tests.test_codex_send_gate \
  tests.test_codex_room_runner \
  tests.test_codex_plugin_bundle \
  tests.test_docs_truthfulness \
  tests.test_integration_entrypoints \
  tests.test_no_home_writes

python3 /Users/zmll/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py \
  integrations/codex/nunchi-codex
```

Result at review time: both commands passed locally.

Live evidence subsequently committed:
[`2026-07-09-vigil-live-smoke.md`](./2026-07-09-vigil-live-smoke.md) records one
successful Vigil room wake and outbound hook allow in channel
`1522258711047831653`, using the installed Codex plugin, the shared
`nunchi-mcp-discord` transport, and the long-running room runner.

Residual scope note: that evidence supports a single live-smoke claim, not a
sustained operations claim.
