# Privileged action authorization boundary

**Status: implemented; deterministic checks only.** `AuthorizationCoordinator`
in `src/nunchi/authorization.py` checks `I-010F PrivilegedActionAuthorizationV2@1`
before dispatching an effect. The reference adapters supply no executors, there
is no shipped authenticated approval surface, and no live run has verified a
privileged effect. The shared host and its ownership of turns remain under
[architecture review](../../AGENTS.md#architecture-goal-and-current-gap).

## What is protected

Privileged actions include mutation, destruction, external side effects,
secret-bearing work, and account or configuration changes. A participant may
propose an action and name an origin event and capability. It never decides
whether that action is allowed.

The request identifies the exact proposal without exposing its body:

- a unique action ID;
- a SHA-256 digest using the exact `nunchi.operation-json.v1`
  canonicalization profile;
- participant, capability, exact origin event, and bounded scope;
- a requester derived from the transport-attested actor of that origin event.

Names, aliases, roles, mentions, quoted text, reactions, model output, policy-
looking room text, and copied decisions are not authority.

## Trust boundary

The host retains the operation, canonical origin event, policy, pending
proposal, authenticated-operator session, and executor. They are never public
contract fields. The schema contains no credential, policy file, raw operation,
approval token, or reusable grant.

```text
participant proposal
  -> host resolves retained origin and action bytes
  -> I-010F request / decision facts
  -> optional host-only authenticated approval
  -> coordinator rechecks policy, scope, digest, expiry, revocation, persistence
  -> one effect, or no effect
```

`ALLOW`, `DENY`, and `APPROVAL_REQUIRED` are audit facts, not bearer tokens.
An allow is meaningful only for its exact bound request and only at the host's
single effect-commit point.

High-impact work defaults to `APPROVAL_REQUIRED` unless trusted operator policy
explicitly preauthorizes the exact actor, capability, and scope. The challenge
is host-only, expiring, bound to the exact digest, and accepts only an exact
authenticated approver. Approval causes a fresh recheck before a new allow,
and the allow cannot outlive the expiry that recheck set.

## What the coordinator does

- **Final recheck before dispatch.** Immediately before the effect it reloads
  the pinned policy and rechecks the matching rule, policy revision, grant
  expiry, revocation, retained origin event, operation digest, and
  cancellation. It repeats that recheck after the commit write, because the
  write itself can consume the deadline or overlap a revocation.
- **One use.** The grant is consumed when the `effect_commit` record is
  durably written. If that write is uncertain, no executor runs. A replay of
  the same action is denied.
- **Commits that never ran are closed.** A commit that does not reach its
  executor (refused by the final recheck, cancelled, or a recheck that fails)
  is closed with `effect_result` `FAILED`, detail
  `privileged effect was not attempted: <reason>`. The grant stays consumed.
  If that record cannot be written, the commit stays open, which is the
  conservative reading.
- **Open commits after restart are UNKNOWN.** A commit still open at startup
  does not establish whether the executor ran: a crash can happen before,
  during or after the native call. It loads as `UNKNOWN`: ordinary replay is refused. If the target supports
  idempotency, a fresh policy check may retry with the original idempotency
  key; otherwise a new authenticated approval that shows the exact operation,
  origin, and duplicate-effect risk is required for one retry. A confirmed
  retry closes the unknown state.
- **Approval lifetime.** The turn deadline bounds only publication of an
  approval challenge. Once published, the challenge lives until its own
  `expires_at` (approval TTL, default 300 s), an explicit cancel, or restart.
  Restart drops pending approvals; they are never rebuilt from room history.
- **The agent knows what became of its proposal** (agreed, 2026-10-04, on
  #94). The coordinator keeps the participant's 16 newest proposals with a
  status: `awaiting_approval`, `done`, `failed`, `unknown`, `denied`,
  `expired`, `withdrawn`, or `cancelled`. Each later turn shows the newest 3
  in `memory.own_moves` as `proposal` moves, pointing at the message that
  prompted them, so nothing happens in the agent's name without it knowing.
  Nunchi never reports an outcome in the room; the agent does, in its own
  turn.
- **The agent reports completion itself** (#90, decision 2 on #94).
  When an operator's approval settles the action (`done`, `failed`,
  `unknown`, or `denied` at the recheck), the coordinator tells its outcome
  listeners. The delivery lane then gives the agent a turn about the message
  the action was proposed for, with `occasion: "outcome"`, once nothing
  else is running. Attention reads the room for that turn as advice but
  cannot keep it from the agent (`outcome-turn`). The turn carries no
  authority: it is an ordinary turn, and any further privileged action is a
  new proposal. Withdrawn, expired and cancelled proposals never ran, so
  they start no turn; the next turn's memory shows them.
- **The agent can withdraw.** A `withdraw` action names a proposal still
  awaiting approval. The
  coordinator drops its challenge, so no operator can approve it, and marks
  it `withdrawn`. It counts as the turn's one action. Withdrawing anything
  else, or another participant's proposal, fails and changes nothing.
- **Deadlines must be finite.** A NaN, infinite, or non-numeric deadline is
  refused before any audit or effect.

The host executes nothing when any fact is missing, ambiguous, expired,
revoked, mismatched, replayed, or not durably persisted.

## What is still missing

- **Executors.** Reference adapters can wire the coordinator with an
  `authorization` policy, but supply no executors. They deny privileged
  proposals. The retired Claude Code gate was the only supplied harness
  executor; it is no longer available.
- **Authenticated operator approval surface.** `pending_for_operator()` and
  `complete_authenticated_approval()` are library methods. No shipped command,
  dashboard, or transport calls them, so an `APPROVAL_REQUIRED` proposal
  returns `unavailable` and expires.
- **Live evidence.** No real-platform run has exercised a privileged effect.

## Tests

The contract tests prove schema closure, digest shape, and deterministic
correlation rules for supplied records, including substitution, contradictory
reasons, multiple initial decisions, invalid approval prompts, wrong
approvers, replay, approval-recheck drift, expiry, revocation, and unknown
persistence. The coordinator tests exercise the runtime behavior above with
in-process doubles. Neither proves that a platform delivery is authentic, an
operator is authenticated, or an effect ran once on a real platform.

```sh
python3 -m unittest tests.v2.contract.test_privileged_action_authorization
uv run --offline --isolated --no-project --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'
python3 -m unittest tests.v2.test_shared_foundation tests.v2.test_shared_deadline_race tests.v2.test_shared_deadline_continuity tests.v2.test_core_persistence_closure
```
