# Privileged action authorization boundary (A3 implementation complete; acceptance pending)

`I-010F PrivilegedActionAuthorizationV2@1` is a complete contract
implementation, not a running authorization system. It defines the facts a
later host guard must correlate before a privileged effect. Independent
acceptance is pending, so it is not yet an effective upstream dependency.

## What is protected

Privileged actions include mutation, destruction, external side effects,
secret-bearing work, and account or configuration changes. A participant may
propose an action and name an origin event and capability. It never decides
whether that action is allowed.

The request identifies the exact proposal without exposing its body:

- a unique action ID;
- a SHA-256 digest plus canonicalization-profile ID;
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
  -> I-040B rechecks policy, scope, digest, expiry, revocation, persistence
  -> one effect, or no effect
```

`ALLOW`, `DENY`, and `APPROVAL_REQUIRED` are audit facts, not bearer tokens.
An allow is meaningful only for its exact bound request and only at the host's
single effect-commit point.

## Safe defaults and recovery

High-impact work defaults to `APPROVAL_REQUIRED` unless trusted operator policy
explicitly preauthorizes the exact actor, capability, and scope. The challenge
is host-only, expiring, bound to the exact digest, and accepts only an exact
authenticated approver. Approval must cause a fresh recheck before a new allow:
the later authenticated decision must retain that recheck's policy, expiry,
revocation, and persistence facts and be timestamped after it. The completion
must follow the originating approval-required decision, and the recheck must
keep the challenge's policy provenance.

The host executes nothing when any fact is missing, ambiguous, expired,
revoked, mismatched, replayed, or not durably persisted. It drops pending
approvals on restart instead of reconstructing them from room history. A full
implementation must bound pending state and make cancellation race-safe; those
runtime responsibilities belong to slice `040`.

## What this complete implementation proves and does not prove

The A3 tests prove schema closure, digest shape, and deterministic correlation
rules for supplied records, including substitution, wrong-approver, replay,
approval-recheck drift, expiry, revocation, and unknown-persistence cases. They
do not prove that a
platform delivery is authentic, an operator is authenticated, a policy is
trusted, persistence actually succeeded, or an effect ran once. Those claims
require the later guard, transport, integration, and live evidence.

Run the focused deterministic checks with:

```sh
python3 -m unittest tests.v2.contract.test_privileged_action_authorization
uv run --offline --isolated --no-project --with 'jsonschema==4.26.0' python -m unittest discover -s tests/v2/contract -p 'test_*.py'
```
