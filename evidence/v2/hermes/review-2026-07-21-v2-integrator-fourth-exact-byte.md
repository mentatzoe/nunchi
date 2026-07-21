# Fourth exact-byte review — Hermes V2 candidate

**Slice**: `060-v2-hermes`

**Reviewed candidate base HEAD**: `a03eeb95c7d569895e1171993c7a5748fc250bd8`

**Frozen candidate manifest**: `evidence/v2/hermes/candidate-files.sha256`

**Manifest SHA-256**: `97e500259aaaac805913dcac8f9f91c1019686f4915ad6a29088b5fbc2a098f0`

**Manifest entries**: 23

**Reviewed by**: independent fourth exact-byte Codex review

**Recorded by**: `v2-integrator` (`codex-session-2`)

**Reviewed on**: 2026-07-21

**Verdict**: `REWORK`

## Decision boundary

This is the blocking verdict from the required fourth read-only review of the
exact frozen working-tree bytes. It is not acceptance, self-acceptance,
remediation, integration, deployment, release, promotion, or cutover authority.
Slice 060 remains `PLANNED`/`DORMANT`: no canonical activation, candidate,
handoff, rejection, or acceptance lifecycle record is created or changed by
this review. Because no canonical `HANDOFF_READY` attempt exists, `REWORK` here
is an advisory exact-byte review outcome rather than a lifecycle `REJECTED`
handoff decision.

The review made no edits to the candidate worktree or installed Hermes source.

## Findings

### H1 — Active-session slash/control dispatch escapes Nunchi's output and receipt boundary

Candidate `integrations/hermes/nunchi-gate/v2_plugin.py:1621-1627`
explicitly returns `None` for slash events, while its output collection exists
only around `_process_message_background` at
`integrations/hermes/nunchi-gate/v2_plugin.py:1471-1513`.

Installed Hermes routes every resolvable command around the active-session
owner at `/Users/zmll/.hermes/hermes-agent/hermes_cli/commands.py:389-409` and
performs inline handler plus `_send_with_retry` output at
`/Users/zmll/.hermes/hermes-agent/gateway/platforms/base.py:4684-4741`.
Native Discord also emits direct interaction responses at
`/Users/zmll/.hermes/hermes-agent/plugins/platforms/discord/adapter.py:4038-4063`.

The reproduction held a genuine Nunchi ticket open, delivered `/status` in the
same installed `BasePlatformAdapter` session, and observed:

```text
ticketed_before=True
ticketed_after=True
platform_output=['STATUS-LEAK']
```

Platform output therefore occurs without participant-host or transport receipt
while the admitted turn remains active. This contradicts
`evidence/v2/hermes/handoff.md:48-49` and
`docs/integrations/hermes-v2.md:35-36` in the frozen candidate.

### H2 — Raw Discord context uses weaker adapter authorization than the canonical gateway decision

Candidate `integrations/hermes/nunchi-gate/v2_plugin.py:930-955` calls
`DiscordAdapter._is_allowed_user`, and
`integrations/hermes/nunchi-gate/v2_plugin.py:1187-1216` retains the event
without calling `gateway._is_user_authorized`.
`integrations/hermes/nunchi-gate/v2_runtime.py:208-213` then stamps it
authorized.

Installed adapter channel-only authorization returns true at
`/Users/zmll/.hermes/hermes-agent/plugins/platforms/discord/adapter.py:3292-3305`,
while canonical gateway authorization default-denies the same
no-user-allowlist source at
`/Users/zmll/.hermes/hermes-agent/gateway/authz_mixin.py:467-514`.

The reproduction with only `DISCORD_ALLOWED_CHANNELS=42` observed:

```text
adapter_auth=True
candidate_raw_retention=True
gateway_authorization=False
```

Unauthorized text can therefore enter later classifier context. This
contradicts `evidence/v2/hermes/handoff.md:42` and
`docs/integrations/hermes-v2.md:24-31` in the frozen candidate.

### H3 — Pre-participant cancellation leaves the staged admission and scheduler state alive

Candidate cleanup begins only after entry into `wrapped_turn` at
`integrations/hermes/nunchi-gate/v2_plugin.py:1321-1359`. The outer process
wrapper's `finally` at
`integrations/hermes/nunchi-gate/v2_plugin.py:1483-1511` only finishes output
collection.

Installed Hermes awaits typing/processing and then its handler at
`/Users/zmll/.hermes/hermes-agent/gateway/platforms/base.py:4874-4926`, while
shutdown cancels these tasks at
`/Users/zmll/.hermes/hermes-agent/gateway/platforms/base.py:5437-5482`.
Cancellation can therefore occur before `wrapped_turn` is entered.

The reproduction cancelled the installed background process while its
pre-participant handler was suspended and observed:

```text
ticketed_after_preparticipant_cancel=True
dispatch_ticket_after_cancel=True
```

The staged turn, ticket, scheduler opportunity, and host delivery remain live;
a later duplicate or redispatch can consume stale admission, and the active
scheduler lane remains wedged. This contradicts the remediation claim at
`evidence/v2/hermes/verification.md:103-112` in the frozen candidate.

## Verification context

- Focused Hermes suite: 53 of 53 passed.
- HM-01 through HM-06: all reported `PASS`.
- Governance: passed.
- Full repository suite: 1,251 tests passed, 7 skipped.

Those green gates do not exercise the three cross-parameter paths above.

## Frozen-byte and source provenance

- Start manifest SHA-256:
  `97e500259aaaac805913dcac8f9f91c1019686f4915ad6a29088b5fbc2a098f0`.
- Final manifest SHA-256: identical.
- All 23 entries verified at both boundaries.
- Candidate HEAD remained
  `a03eeb95c7d569895e1171993c7a5748fc250bd8`.
- Manifest movement: none.
- The installed Hermes checkout disappeared externally only after the
  installed-source reproductions and exact line capture. This review made no
  edits to either tree.

## Owner handback

The Hermes owner lane must treat this exact candidate as blocked, address all
three HIGH findings within its own authority, regenerate the frozen candidate
and evidence truthfully, and present the successor bytes for a new independent
review. This record does not perform or authorize that remediation.
