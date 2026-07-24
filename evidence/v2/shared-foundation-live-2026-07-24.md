# Shared-foundation V2 installed and live evidence

Date: 2026-07-24

Result: passed for the shared foundation, shared Discord transport, CLI,
Codex, and reference-adapter candidate. This record does not implement,
exercise, approve, or arm Hermes or Claude Code, and it does not claim
integration, release, or Zoe's final product acceptance.

## Subject and identity

- Implementation commit:
  `ca4404b7fb3c04b96ae80319eeb22723a5d7f8b2`.
- Clean-built wheel:
  `nunchi-2.0.0-py3-none-any.whl`, SHA-256
  `36975d5f1e863e41db0b9a70d3057ae0b05c87276eec38c0ed52ce15da1b0d82`.
- Clean install: Python 3.14 `site-packages`, with `mcp==1.28.1`; no editable
  install, checkout import, or `PYTHONPATH`.
- Discord channel: `1530259309802295316`.
- Discord application and exact transport self: Vigil,
  `1494822530643398827`.
- Participant route: `vigil` in the exact channel above.
- Human stimulus actor: Discord actor `362335298983559169`.
- Attention provider/model: Nous,
  `openai/gpt-5.6-luna`, using an operator-supplied `NOUS_API_KEY`.
- Participant model: Codex `gpt-5.6-luna`, using the existing authenticated
  Codex OAuth session. The participant subprocess received no Discord,
  attention-provider, or transport credential.

Credentials were read only from operator-owned external configuration and
environment names. No credential value, authorization MAC, or participant
private profile is captured here.

## Pinned runtime configurations

| Purpose | Configuration SHA-256 |
|---|---|
| ordinary attention | `0c60514cd46c160b993de92832004e6a3b5b42d981fddeb9ef540db63e4c4520` |
| forced margin | `4c35e5e174cb398529ae5ef22debaf261e1b8b4b2a6db6441608a9ff019ff6f3` |
| trusted bypass | `19d965d46c97bb6f56ddf4a091649add084d8ea19fdcc3fe1cfb6b2081387e72` |
| provider failure | `7435a36bb6e2df1ede5e990d0fc62e1e52d382f12db1b2feaf995a904ff24306` |
| participant profile | `5a87469fbba0330b21d7d5024d8d0d16c2b12a597eebfb0e3572750d386bdfcc` |

Each configured probe reported generation 2 with `v1_fallback: false`. The
ordinary and forced-margin attention calls used the participant-bound Nous
model. Bypass invoked no attention model. The failure configuration targeted
a deliberately unavailable local endpoint and retained the explicit default
`WAKE` operational policy.

## Real-room matrix

Receipts were immutable JSONL records in canonical stage order. Discord
message IDs below are native ingress or target-attested output identities.

| Scene | Native trigger | Correlated request | Observable result |
|---|---|---|---|
| SUPPRESS | `1530330973433106442` | `discord:1530259309802295316:56a6373a-dcea-471e-94ab-8d8409ee148b` | classifier `SUPPRESS`, effective `SUPPRESS`; stream ends at attention with no participant-host or transport stage |
| WAKE and contribution | `1530326334004396072` | `discord:1530259309802295316:3322fc7c-abca-4ed4-a66f-2c2dfcc459e2` | classifier/effective `WAKE`; participant handoff `unknown` before effect; transport `sent`; Vigil message `1530326376924581958` contained exactly `NUNCHI-V2-WAKE-20260724` |
| direct classifier DEFER | `1530327601711808674` | `discord:1530259309802295316:3347f00e-5b9e-4330-955d-26300362aaae` | classifier/effective `DEFER`, valve `classifier-defer`; participant contributed a bounded clarification; transport `sent` as Vigil message `1530327727687860274` |
| margin DEFER and silence | `1530328188029239306` | `discord:1530259309802295316:b9f88f0e-5c39-4b9f-b202-b06b46a925b3` | classifier `SUPPRESS`, effective `DEFER`, valve `margin-defer`, explicit margin provenance; participant `silent`; no transport stage or Discord reply |
| trusted bypass and silence | `1530328472411574403` | `discord:1530259309802295316:5420e49a-06c5-4700-a939-344cdd4c2538` | `classifier_not_invoked: true`, cause `preattention-disabled`, wake source `PREATTENTION_BYPASS`; participant `silent`; no transport stage or Discord reply |
| provider error fallback | `1530328756491915296` | `discord:1530259309802295316:8513cc8a-9504-4e1c-94be-fac919f90ce9` | operational `provider-failure` with no fabricated classifier disposition; wake source `ERROR_FALLBACK`; fresh authorized send; transport `sent`; Vigil message `1530328776020328608` contained exactly `NUNCHI-V2-ERROR-FALLBACK-20260724` |

Every native send above was preceded by the participant-host's persisted
`unknown` handoff and a fresh one-use exact-operation authorization. The
transport stage alone attested `sent` after checking the returned native
message ID, room, exact authenticated bot, submitted content, and reply
binding. Accepted authorization nonces were persisted without exposing them
in this record.

## Recovery and non-revival

A fresh Discord process truthfully declared a source gap because gateway
resume authority is process-local. Message `1530325906982174770` arrived while
that gap was pending. The transport recorded it as `queue-rejected`, delivered
gap `discord:transport-gap:4f74bfb2-c2a7-4163-80da-f3cf97ceae96`, and never
created an observation, attention decision, participant invocation, or later
reply for the rejected message. The explicit resubmission
`1530326334004396072` was then accepted as new work.

The final exact-candidate SUPPRESS closure repeated that boundary: carrier
`1530330768495218979` was rejected while gap
`discord:transport-gap:278ddd36-8e0b-493e-a918-0cb3bb2b96d8` was delivered;
the later message `1530330973433106442` was accepted. Neither rejected event
was replayed. This is the intended fail-safe restart behavior, not a reply
queue.

## Installed and deterministic checks

The same implementation commit passed:

- `python3 -m unittest`: 314 tests, 4 optional JSON-Schema-oracle skips;
- pinned `jsonschema==4.26.0` dual-validator suite: 218 tests, zero skips;
- lifecycle conformance: 8/8 scenarios;
- focused shared-foundation, surface, hardening, transport, cancellation,
  authorization, replay, isolation, bounded-context, coalescing, and recovery
  suite: 96 tests against source and again against the installed wheel;
- installed `nunchi`, installer, conformance, generic channel, Discord,
  Matrix, Telegram, Codex, and MCP entry-point probes;
- installer `init` and `verify` in new private roots;
- explicit rejection of removed V1 command `nunchi admit`;
- installed imports from the clean environment's `site-packages`.

The live run itself exposed two installed-path blockers before this subject
was frozen: the documented bare `/mcp` endpoint caused a POST redirect that
`urllib` correctly refused to replay, and Codex's provider rejected a
top-level `oneOf` output schema. Commits `887747e` and `ca4404b` fixed those
issues with regression tests. The matrix above was then closed on `ca4404b`;
the earlier predecessor SUPPRESS result is not used as the final SUPPRESS
claim.

## Cleanup

The Discord application flags were temporarily changed from `524288` to
`557056` solely to enable the required Server Members gateway intent. They
were restored to exactly `524288` after each bounded run. The temporary
output-HMAC file and saved flag-state file were deleted. The temporary V2
processes shut down cleanly, and both pre-existing Vigil launch agents were
restored and observed running. No Hermes or Claude Code process was installed,
armed, changed, or exercised.

## Repaired successor after fresh review

A fresh non-author review later rejected exact evidence candidate
`4dc13f72c153699424fadc3ecf46717549d77969` for one blocker. After an
authorized Discord effect was attempted, a lost, malformed, or 5xx
acknowledgement could be surfaced as a definitive failure even though the
effect might exist. A malformed nested author value could also escape as an
unhandled exception. These findings do not change the successful native
message attestations above, but they prevented `4dc13f7` from being the final
candidate.

Implementation successor
`c5f5e6c0c7e2fd6af1bf888ca9a86a7a8f4d7e63` closes that boundary:

- lost, malformed, exceptional, and 5xx post-effect acknowledgements produce
  an explicit `delivery.status: unknown`;
- explicit Discord 4xx rejections remain definitive failures;
- mutating 5xx requests are not retried, avoiding duplicate effects without
  target idempotency;
- malformed nested message fields are shaped safely and cannot fabricate a
  target-attested send; and
- Codex preserves the transport's `unknown` result instead of reclassifying it
  as `failed`.

The exact successor was built twice from clean archives with fixed source
time. Both builds produced byte-identical
`nunchi-2.0.0-py3-none-any.whl` artifacts with SHA-256
`f2852390c7e4fc8beff03091e6a9478ff22186c7030846f319c5b241d00eb9c1`.
A new Python 3.14 environment installed that wheel with `mcp==1.28.1` and
`jsonschema==4.26.0`; imports resolved from its `site-packages`.

The repaired source and installed wheel each passed:

- 319 full tests, with only the four optional source-interpreter JSON-Schema
  oracle skips and zero installed skips;
- all 218 pinned dual-validator contract tests with zero skips;
- all eight lifecycle scenarios;
- 101 focused shared-foundation, transport, cancellation, authorization,
  replay, isolation, bounded-context, coalescing, and recovery tests; and
- five direct regressions covering lost or malformed message
  acknowledgement, lost reaction acknowledgement, single-attempt mutating
  5xx, retained GET retry, and Codex propagation of `unknown`.

The installed CLI, installer, conformance, generic channel, Discord, Matrix,
Telegram, Codex, and MCP entry points were probed. Installer `init` and
`verify` created and checked private V2-only state, and removed V1 command
`nunchi admit` was rejected.

The real-room matrix remains attributable to exact installed implementation
predecessor `ca4404b` and wheel
`36975d5f1e863e41db0b9a70d3057ae0b05c87276eec38c0ed52ce15da1b0d82`.
The successor changes only failure closure after an effect attempt; successful
room behavior above was not rerun. Instead, the changed path was exercised
from the exact successor's clean installed wheel using controlled
lost/malformed/5xx acknowledgements. This differential boundary is explicit
for the final reviewer to accept or reject; it is not represented as an exact
successor live-room run.
