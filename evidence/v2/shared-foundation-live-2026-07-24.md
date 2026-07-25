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

## Exact-successor native closure

Date: 2026-07-25

The fresh non-author reviewer
`/root/foundation_final_candidate_review` rejected exact candidate
`755091b749876fa0954b42a9d5e86e2424c37b8b` on one proof boundary: the
successful acknowledgement and target-attestation bytes had changed, so the
predecessor native matrix could not be reused. The reviewer found no
implementation blocker and independently reproduced the source, installed,
contract, lifecycle, focused, acknowledgement, retry, exclusion, and artifact
checks described above.

The exact candidate was then installed again from wheel SHA-256
`f2852390c7e4fc8beff03091e6a9478ff22186c7030846f319c5b241d00eb9c1`
into a new Python 3.14 environment with `mcp==1.28.1`. Imports resolved from
that environment's `site-packages`. The same Vigil application, channel,
participant binding, Nous attention model, Codex OAuth participant, and
external credential boundaries from the earlier run were retained.

Pinned configuration hashes for this closure were:

| Purpose | Configuration SHA-256 |
|---|---|
| ordinary WAKE and classifier DEFER | `c3af5eb05f513f5bafcc9bb42c038cebb7493913c87b1cdfae85113469332292` |
| ordinary margin DEFER and SUPPRESS state | `43d9cd370d70c14e4bb2824ba1edeb73dc5248770104960012b1f7c416681dfd` |
| trusted bypass | `01a9434ce7fc0ac18a367a9ab67f65b87aac7d4fd7eadad6e34186548d33baa5` |
| provider failure | `0ce47d1e3dd8dba602958936eb7dac61b91a50d0767f1b8bb460563adbc8150b` |
| participant profile | `5a87469fbba0330b21d7d5024d8d0d16c2b12a597eebfb0e3572750d386bdfcc` |

The ordinary-policy configurations used the same participant profile, Nous
model, active `0.12` uncertainty margin, and policy provenance; they differed
only in private state path to keep the scenario horizon explicit. A proposed
zero-margin configuration received no event and was discarded after the
operator correctly objected that forcing the valve would not demonstrate a
natural model-shaped SUPPRESS. No result from it appears below.

### Exact-successor room matrix

| Scene | Native trigger | Correlated request | Observable result |
|---|---|---|---|
| WAKE and contribution | `1530376861610152066` | `discord:1530259309802295316:9c5cd1ae-9884-42fe-abba-1e0edba316a3` | classifier/effective `WAKE`; participant handoff persisted as `unknown`; transport `sent`; target-attested Vigil message `1530376904006172692` contained exactly `NUNCHI-V2-WAKE-755091B` |
| direct classifier DEFER and silence | `1530377627913949236` | `discord:1530259309802295316:c9c5e32d-5d20-46e8-a5ac-ea3362dd0e23` | classifier/effective `DEFER`, valve `classifier-defer`; participant invoked and chose `silent`; no transport stage or Discord reply |
| margin DEFER and silence | `1530379287683662018` | `discord:1530259309802295316:e481ea36-4726-4886-b4cd-7beba01a8810` | classifier `SUPPRESS`, effective `DEFER`, valve `margin-defer`, active margin `0.12`; participant invoked and chose `silent`; no transport stage or Discord reply |
| natural SUPPRESS | `1530381617506422794` | `discord:1530259309802295316:e8de84ff-afc6-4475-969a-f7cdecab33f0` | classifier/effective `SUPPRESS` under the same ordinary policy and active margin; stream ended at attention with no participant-host or transport stage |
| trusted bypass and silence | `1530384130628386858` | `discord:1530259309802295316:5bdf2c87-9090-46a1-a807-b30c8b7d65d5` | `classifier_not_invoked: true`, cause `preattention-disabled`, wake source `PREATTENTION_BYPASS`; participant invoked and chose `silent`; no transport stage or Discord reply |
| provider error fallback | `1530384526650507376` | `discord:1530259309802295316:f9adfa19-b404-4a59-b41e-7073d081f572` | operational `provider-failure` with no fabricated social disposition; wake source `ERROR_FALLBACK`; participant handoff persisted as `unknown`; transport `sent`; target-attested Vigil message `1530384564755759177` contained exactly `NUNCHI-V2-ERROR-FALLBACK-755091B` |

One additional ordinary-policy attempt was retained rather than concealed:
trigger `1530378829028262029`, request
`discord:1530259309802295316:8e691172-e520-455a-89d1-879ced1e5afb`.
Because the bounded context still contained the earlier unresolved direct
request, the delegated model returned classifier/effective `DEFER`; the
participant chose silence. That truthful result is not used as the SUPPRESS
claim.

Every admitted native trigger above was received live after its pinned runner
registered. Scenario-state changes are not represented as one uninterrupted
participant session. The shared Discord gateway and exact installed artifact
remained fixed across them. The WAKE and error-fallback sends exercised the
repaired successful acknowledgement, shaping, exact-bot, exact-room,
exact-content, authorization, and target-attestation path that the reviewer
identified as lacking native successor proof.

### Exact-successor recovery and cleanup

Fresh transport startup declared source uncertainty. Carrier message
`1530371404242096199` was recorded as `queue-rejected` while gap
`discord:transport-gap:037c9a98-cdfb-4fc2-9efe-49c532fa8433` was signaled and
delivered. The carrier created no observation, attention decision, participant
invocation, or later reply; the later WAKE trigger was newly admitted rather
than replayed.

After the matrix, the exact-successor runner and transport stopped. Vigil's
application flags were restored from temporary `557056` to exact original
`524288`; the saved flag state and temporary output-HMAC key were deleted.
Both pre-existing Vigil launch agents were restored and observed running.
Hermes and Claude Code were not installed, repaired, changed, armed, or
exercised.

### Correction: zero-margin chronology

The statement at lines 210-215 of exact candidate `85553e2` is false. The
proposed zero-margin configuration did receive one event before it was
discarded, and an earlier launch attempt failed its trusted configuration pin.
This append-only correction preserves that history instead of rewriting it.

- The zero-margin configuration SHA-256 was
  `13ef4927832dd51b512766b59dc40be41b33aeab2e0aba5f319299a58e25a628`.
  It retained the same Nous `openai/gpt-5.6-luna` delegated attention model
  and policy provenance, but set the active `effective_margin` to `0.0` with
  margin source
  `operator-live-smoke:suppress-zero-margin@2026-07-25`.
- One launch was rejected before the runner registered because its adapter
  configuration bytes did not match the trusted SHA-256 pin. It admitted no
  event and produced no social result.
- A later correctly pinned launch received native trigger
  `1530380597091111013`, delivery
  `discord:gateway:2ed21f246b0eeb29bf499a7d303bb7ec:8:MESSAGE_CREATE:1530380597091111013`,
  and request
  `discord:1530259309802295316:fc710602-3fbc-4394-9384-446015068169`.
  The transport audit recorded `accepted` and `client-delivered`; the
  observation and attention stages then recorded classifier/effective
  `SUPPRESS` under
  `operator-live-smoke:suppress-policy@2026-07-25`. There was no
  participant-host or output-transport stage.

This zero-margin result is intentionally not a matrix acceptance result:
changing the uncertainty margin to force the deterministic valve does not
demonstrate natural participant-shaped suppression. The operator raised that
objection after the event, the setup was discarded, and the later ordinary
active-`0.12` result at trigger `1530381617506422794` remains the matrix's
natural SUPPRESS evidence. The omitted execution and failed launch were
evidence-recording errors; they do not replace or invalidate the independently
correlated six-scene matrix.

The previously omitted failed launch is retained verbatim and attributed in
`evidence/v2/shared-foundation-zero-margin-abort-2026-07-25.json`. Its local
Codex execution transcript records tool call
`call_st3beJHaY5M4L1mjBQ8Z5Rq7` at `2026-07-25T01:04:25.161Z`, the exact
command, actual configuration hash, incorrectly supplied hash, runner exit
status `3`, unredacted raw output, runtime and launch identity, and source
record hash. The enclosing diagnostic shell command exited `0`; the launched
runner itself rejected the mismatched pin before registration and admitted no
event.

### Fresh non-author disposition

Reviewer `/root/foundation_final_candidate_review` (generated identity Dirac;
OpenAI `gpt-5.6-sol`) approved exact clean evidence candidate
`8296e11d6cb3018e68d2904765a7e1d61f218bd9` with no unresolved blocker. The
review matched the abort record to raw transcript records 7543-7544, reproduced
the configuration and wheel hashes, verified that the rejected launch preceded
registration and admitted no event, and rechecked the accepted six-scene
matrix, excluded zero-margin result, gap handling, cleanup, and platform
boundaries. The reviewer also confirmed that this successor changed no product,
test, schema, integration, Hermes, or Claude Code bytes.
