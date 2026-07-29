# Slice 060 — Hermes V2 acceptance matrix

This matrix freezes the slice acceptance boundary before implementation. It is subordinate to the normative V2 architecture, contract, platform, completion, and delivery documents and does not redefine them.

## Candidate identity

One exact candidate SHA must be used for all repository tests, wheel construction, clean installation, installed-runtime probes, live Discord/Telegram scenes, independent review, and integration evidence. Any remediation creates a new candidate and invalidates later-stage evidence from the previous one.

## Automated conformance

- **Foundation ancestry** — `014546d2ec685341106b177bcf2f6e52e758e0a9` is an ancestor of the candidate.
- **Shared contracts** — the canonical V2 contract suite passes unchanged.
- **Shared runtime** — observation, attention, participant host, scheduler, authorization, transport uncertainty, cancellation, and restart suites pass.
- **Hermes exact identity** — Discord and Telegram fixtures bind exact native actor IDs; alias collisions never establish self; state paths are partitioned by Hermes profile, participant, platform, room, and continuity scope.
- **Authorized observation only** — unauthorized or unbound routes never enter observation; malformed events cannot create a wake; admitted message facts normalize without inferred roster, relation, obligation, handled state, or floor ownership.
- **Participant-owned attention** — each authorized routable trigger makes zero calls under trusted bypass and exactly one call otherwise; SUPPRESS invokes no participant; WAKE/DEFER/bypass/default error invoke one act-or-silence turn; no send-time classifier exists.
- **Direct contribution or silence** — the participant receives a validated ParticipantWakeV2 packet with advice as separate non-authoritative annotation, can request only host-mediated bounded expansion, and returns one ordinary action, one privileged proposal, or silence.
- **Native transport truth** — Discord and Telegram sends/replies/reactions return sent only from a closed host acknowledgement matching the exact platform, room, routed profile, authenticated native self actor, effect kind, submitted content, reply/target identity, and a new message or deterministic reaction-effect identity. Missing or mismatched fields, timeout, exception, or malformed acknowledgement return failed, unknown, or unavailable and never fabricate success.
- **Privileged effects** — proposals resolve the requester from the retained origin event, match a pinned operator policy and fixed capability executor, persist authorization before dispatch, support authenticated approval, recheck policy/revocation/expiry immediately before the effect, reject replay, preserve unknown-effect semantics, and discard pending authority on restart.
- **Concurrency and restart** — ingress stays ordered, one active plus newest pending opportunity is enforced per binding, queue gaps become explicit continuity gaps, cancelled/stale work cannot dispatch, and restart retains only documented durable observation/receipt/effect facts.
- **No V1 route** — the shipped Hermes plugin has no V1 gate/classifier import, environment switch, compatibility bridge, alternate decision vocabulary, or fallback path; the installed probe reports generation 2 and `v1_fallback: false`.
- **Hermes plugin API** — the wheel exposes one `hermes_agent.plugins` entry point named `nunchi-v2`; registration negotiates `PluginContext.participant_host_api_version` and supports major 2 without pinning an exact Hermes release or source identity. The narrower gateway-message-hook major is evidence, not acceptance authority. Missing, unreadable, malformed, old, or future umbrella majors fail before configuration, hooks, or commands and direct the operator to update Hermes and retry. The installed doctor emits stable JSON, fails incompatible hosts, and optionally requires the machine-readable plugin row to be enabled and active without restarting Hermes. Hermes invokes the plugin through public async message/cancellation/shutdown hooks and route-bound delivery only after native admission, authorization, profile routing, and control-command interception. The plugin owns all Nunchi observation, attention, scheduling, participant, authorization, receipt, and privileged-capability behavior and uses the host-owned plugin LLM facade without reading provider credentials. The installed wheel contains no Hermes-file applicator, wrapper, `pre_gateway_dispatch`, raw `GatewayRunner`, private adapter/session-store access, monkeypatch, or Hermes-core Nunchi import.

Primary command:

```bash
python3 -m unittest tests.v2.test_hermes
```

## Artifact and installed-runtime proof

- Build the reproducible wheel from a clean candidate; sdists are not release evidence.
- Install the wheel into a fresh Python environment and the exact Hermes runtime environment used for the probe.
- Use a fresh isolated `HERMES_HOME`; enable only `nunchi-v2`; install pinned profile/config/policy files with private permissions.
- Verify plugin discovery, closed/pinned configuration, profile and package provenance, state-root isolation, clean restart, V2 probe output, and absence of a repository checkout dependency.
- Run the platform-specific verification commands required by `docs/platform-v2.md` and record exact stdout/stderr, exit status, artifact digest, Hermes version, Python executable, plugin entry point, Nunchi version, configuration digests, and candidate SHA.

## Live surface proof

### Discord

In an explicitly bound authorized room configured so the Hermes gateway forwards every relevant room message to Nunchi:

- one human plus at least two exact Hermes participant bindings;
- ordinary unmentioned conversation is observed;
- exact self output does not wake itself;
- SUPPRESS remains later-hearable within the declared horizon;
- contribution and silence both occur through ordinary participant turns;
- reply/reaction capability is either positively exercised or recorded unavailable without parity inflation;
- a restart invalidates stale work and preserves only attested durable state.

### Telegram

On a Hermes-native Telegram group/topic binding with equivalent available facts:

- authorized ordinary messages enter the same V2 lifecycle;
- equivalent facts normalize equivalently;
- unavailable mention/reaction/history facts are declared in coverage/capability evidence rather than inferred;
- contribution, silence, restart, and delivery acknowledgement are exercised.

Live evidence must identify native message IDs, participant/profile binding, installed artifact digest, and candidate SHA without exposing credentials.

## Exact-candidate review and integration

- Independent reviewers read the exact candidate commit and exact evidence packet.
- Security/provenance review covers identity, auth before observation, prompt/data separation, config pinning, native output attestation, capability mapping, approval authentication, effect replay/unknown handling, persistence, cancellation, restart, queue gaps, packaging, and V1 retirement.
- Every blocker is remediated with a retained regression test on a new candidate; review repeats until blocker-free.
- Push a PR targeting `integration/v2`, use the checks and merge procedure in `docs/v2-delivery.md`, and verify that the integrated successor contains the reviewed candidate and passes the required post-integration commands.
