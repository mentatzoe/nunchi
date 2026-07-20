# Installing the Nunchi V2 integration candidate

`nunchi-install` is retained as a required product surface, but this candidate
does not yet contain accepted V2 Hermes and Claude Code integration packets.
It therefore **fails closed and never modifies the filesystem**.

The inherited integration directories contain V1 implementation material. Do
not copy, symlink, register, or run those artifacts as V2. They remain inputs
to the packet owners and are not an installable product.

## Current command behavior

The stable command names are:

```text
nunchi-install install
nunchi-install upgrade
nunchi-install verify
nunchi-install uninstall
nunchi-install print-claude-settings
```

Until both external packets are accepted and integrated, each command exits
with status `2`, reports
`accepted-v2-integration-packets-unavailable`, and makes no change. Add
`--json` for a machine-readable result:

```json
{"changed":false,"command":"verify","detail":"Accepted Hermes and Claude Code V2 integration packets are not present in this candidate; no changes were made.","reason":"accepted-v2-integration-packets-unavailable","status":"blocked"}
```

This includes `uninstall`: a candidate that cannot identify accepted V2 packet
files must not guess which operator-owned files it may delete.

## What will unblock installation

The integration owner must provide each packet as an exact tested commit
against the stable shared V2 contract. The integrator must then verify and
accept that exact packet before wiring it into this installer. The completed
installer must:

- copy accepted artifacts into stable operator locations rather than symlink
  a live checkout;
- identify and verify the exact source commit and installed file inventory;
- confine every write and deletion to explicit operator-selected roots;
- preserve operator-owned configuration and secrets;
- install no V1 judgment, hook, ledger, or send-time reclassification path;
- verify the installed runtime, not merely the source tree;
- document upgrade, rollback, and any deliberate cleanup of old installations.

No settings snippet will be generated before the accepted Claude Code packet
defines the correct V2 registration. No Hermes plugin will be copied before
the accepted Hermes packet defines the correct V2 runtime surface.

### Packet intake contract

This is an acceptance contract, not a request for a new packet framework. A
Hermes or Claude Code owner may use its existing branch and test layout. The
handoff must identify enough immutable input for the integrator to reproduce
the result without Aleph Vault or conversation history:

1. exact candidate commit and a complete changed-file inventory;
2. exact shared interfaces consumed (`AttentionRequestV2`,
   `AttentionDecisionV2`, `ParticipantWakeV2`, continuation and receipt
   contracts, the observation provider, opportunity scheduler, participant
   host, and action guard where the surface exposes privileged actions);
3. native-event-to-canonical-event mapping, exact self binding, restart and
   history coverage, and every genuinely unavailable native fact;
4. configuration, credentials, executable/process boundary, installation
   paths, upgrade/rollback behavior, and the exact privileged seams Nunchi can
   enforce—plus any tool path that bypasses them;
5. deterministic reproduction commands and results for `SUPPRESS`, `WAKE`,
   classifier- and margin-`DEFER`, trusted bypass, operational-error recovery,
   direct act-or-silence, replies, mentions, burst coalescing, later
   resolution, restart without wake replay, and unauthorized/approval-bound
   privileged proposals;
6. live evidence appropriate to that platform, including delayed turns and
   intervening room events, with secrets removed but exact source/runtime
   provenance retained; and
7. known limitations and rejected claims, including any scene that could not
   be run and why.

The integrator will inspect the diff, rerun the packet commands, run the full
shared deterministic suite, build a clean wheel, install into an isolated
environment, compare the installed file and entry-point inventory with the
candidate, and exercise the packet in the mixed-room ladder. A packet is
rejected if it introduces a local V2 dialect, a hidden V1 entry point, a
per-message response queue, deterministic conversational suppression,
send-time social reclassification, alias-derived self/requester identity,
room- or model-controlled policy, or an unguarded privileged seam advertised
as safe. Passing owner-local tests is necessary but not sufficient.
