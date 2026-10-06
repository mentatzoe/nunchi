# V2 stability boundary

No V2 release has been tagged; the last tag is `v0.2.0`. This page names the
boundary a V2 release would hold stable: the closed V2 contract in
`docs/contracts/nunchi-v2.md`, the runtime validators in
`nunchi.v2_contracts`, and the installed commands below.

## Public commands

Shared core and operator surface:

- `nunchi attention|validate|probe` — one attention judgment, contract
  validation, and installed interface provenance.
- `nunchi setup|config|diagnose|dashboard|service|uninstall` — the operator
  surface. `config` has `show|validate|rollback|add-room`; `service`
  has `start|stop|restart|status|logs|reset|install|uninstall`.
- `nunchi-install init|verify|upgrade|rollback|uninstall|probe` — private
  config and state roots.
- `nunchi-conformance` — the deterministic V2 lifecycle scenarios
  (`python3 -m evals.verdict_suite.runner` is the repository wrapper).

Reference adapters and the shared transport:

- `nunchi-channel`
- `nunchi-discord`
- `nunchi-matrix`
- `nunchi-telegram`
- `nunchi-mcp-discord`

Integrations:

- `nunchi-codex-room-runner` — reduced: Discord only, read-only Codex
  sandbox, privileged actions disabled.
- `nunchi-hermes-dashboard install|verify` and
  `nunchi-hermes-lifecycle plan|apply|verify|rollback`.

Installed but not part of the stable boundary:

- `nunchi-claude-code-room-runner` — the Claude Code gate and its mod
  ([#43](https://github.com/mentatzoe/nunchi/issues/43)). Its configuration and
  the mod's room tools may still change: it depends on Claude Code's mods API,
  which is early access, and it has no live proof.
- `nunchi-service-worker` — internal supervisor that `nunchi service` starts.

No V1 request, verdict, hook, responder, configuration, or exit-code contract
is stable or executable.

## Compatibility rules

- Contract documents are closed; unknown fields fail validation.
- Native IDs remain strings and canonical IDs are platform-qualified.
- `self.actor_id` is exact transport/host binding, independent of aliases,
  names, and roles.
- Attention dispositions are `SUPPRESS`, `WAKE`, and `DEFER`. A judgment
  that leans to a "mhm" is `DEFER`, and the participant sends any "mhm"
  itself; Nunchi never reacts for it (#94 step 7 removed `ACK` and
  `config set-ack`). Receipt journals written before then still read, and a
  config that still has an `ack` setting loads with it ignored. Bypass and
  operational error are distinct non-social statuses.
- Attention is answered as fixed typed questions (steps 1 and 2 of reading
  the room); the decision records the answers (`I-010B@6`). A chat model and
  a typed decision model answer the same questions.
- Attention model configuration selects its implementation with `kind`
  (default `openai-compatible`; the adapters and the Claude Code and Codex
  runners add `decisions-api`, `messages-api` and `responses-api`). The `openai-compatible` attention model and
  the OpenAI-compatible participant model require an explicit `base_url`;
  there is no default endpoint, and a configuration without one fails
  validation. Operator profiles accept `kind` and an optional
  `credential_env` per model.
- Receipt ownership and ordering are immutable.
- Continuation authority is host-only, bound, bounded, expiring, and discarded
  on restart.
- Privileged authorization binds the exact requester origin, participant,
  route, capability, resource, operation digest, policy revision, expiry,
  approval, revocation state, and one-use effect commit.
- Platform-native absences are explicit capability facts, never invented.

A change to any of these requires a contract version change, conformance
updates, and downstream review.
