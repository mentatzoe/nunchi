# Nunchi V2 completion goal

**Revision:** 2

**Completion authority:** Zoe

## Goal

Deliver Nunchi V2 as one coherent, secure, installable product that lets
multiple agents participate naturally in live shared conversations.

Nunchi uses each participant's own delegated stochastic model—shaped by that
participant's identity, instructions, and truthful bounded room facts—to decide
whether to spend attention. Deterministic code validates transport facts,
lifecycle, and authority; it does not decide conversational relevance,
resolution, or obligation. Messages are current observations, not queued work.
Privileged or external effects occur only after trusted host controls verify
the exact current authority for the exact proposed action.

The product is complete only when repository truth, built artifacts, installed
runtimes, documentation, and reproducible evidence all describe the same exact
candidate.

The binding decision chain is the **Authority order** in repository-root
`AGENTS.md`, including the Zoe-selected Nunchi decisions and technical design
recorded by Aleph Vault PR 67 (`bdd1ebb`), the contract clarification in PR 68
(`c834e8c`), and the repository-owned selected design and contract. Zoe may
durably supersede a
selected decision only through an explicit product decision that names the old
decision, its replacement, and every affected requirement and surface, and
amends that chain. The Vault commits are provenance; the binding decisions
themselves must be present in this repository before the self-contained
condition can pass. Existing source, branches, packets, approvals, and evidence
are inherited material: they may be reused when they satisfy this goal, but
none establishes acceptance merely by existing. An unsound implementation may
be replaced; a selected product outcome may not be silently discarded.

## Required product surface

Completion covers this baseline, plus every public or in-tree executable entry
point, hook, launcher, configuration path, native ingress, and outbound path
present when this revision is adopted or added later and reachable from a
clean install or supported upgrade:

| Surface | Required outcome |
|---|---|
| Portable contract and core | One versioned V2 interface and behavior governs identity, observation, attention, continuation, scheduling, authorization, receipts, and errors. |
| CLI, packaging, and operator paths | Installation, supported V1 upgrade, configuration, diagnostics, restart, and rollback work from committed documentation. |
| Shared transport and Discord | Native facts, identity, authority, ordering, and delivery closure are preserved through the common transport and Discord path. |
| Codex | The installed Codex integration implements the complete V2 lifecycle. |
| Hermes | The installed Hermes integration implements the complete V2 lifecycle. |
| Claude Code | The installed Claude Code integration implements the complete V2 lifecycle. |
| Reference adapters | Generic channel, Matrix, Telegram, and standalone Discord implement the applicable V2 contract and represent unavailable platform facts honestly. |

A surface may be removed only through Zoe's explicit product-scope decision
showing how every affected requirement and user capability is resolved.
Difficulty, missing evidence, an unfinished implementation, or a narrower
support label is not an exclusion. A surface advertised as live-supported must
pass real native live evidence; a deliberately reference-only tier requires
Zoe's approval, must be labelled, and cannot support a live-parity claim. Each
surface's required capabilities, native facts, and acceptance scenes are
frozen before inherited work is admitted or reused and before any delivery
resumes under this revision. Historical attempts remain non-candidates until
they pass that frozen matrix. A claimed platform absence requires native-
platform evidence or Zoe's product-scope decision.

## Accountability

One named integrator owns the end-to-end product, dependency order, shared
seams, assembly, proof closure, and final handoff. Platform owners may deliver
bounded packets only after their dependencies are terminal; packet ownership
or acceptance never transfers integration accountability. Reviewers challenge
the candidate independently and do not become silent co-implementers.

## End conditions

Nunchi V2 is complete only when all of the following are true:

1. **One contract, with no hidden old path.** Every required surface implements
   the same applicable V2 semantics. Equivalent available native facts produce
   equivalent observations, routing, participant context, authority decisions,
   and receipt meaning. Genuine platform absences remain explicit. No V1
   verdict, consumer, compatibility bridge, hook, shim, configuration, or
   fallback remains executable.

2. **Participant-shaped social judgment.** Only the exact participant's
   delegated model may make a social suppression decision. Its request is
   bound to integrity-protected, provenance-recorded identity and instructions
   without profile, room, or session leakage; private profile values need not
   be committed. A shared generic relevance classifier cannot stand in for
   the participant. Binding tests reject missing or swapped profiles, and
   profile-sensitive trials hold room facts constant while materially
   different valid instructions produce their intended different attention
   behavior. Exact self-binding remains separate from names, aliases, and
   roles. Governed suppression is inspectable, revocable, and recoverable
   through restart and backfill only as factual later context; recovery never
   recreates a wake obligation or missed moment. Uncertainty widens attention
   through separately observable classifier and margin `DEFER` paths, and the
   margin retires only on evidence.

3. **Live conversation, not queued work.** For each participant and room there
   is at most one active attention-or-participant opportunity and one
   replaceable newest event waiting to trigger the next opportunity. Every
   valid native event class has a positive construct-and-route test. Only exact
   duplicate delivery, an exact self event, or a payload from which no
   configured route can construct a native event may deterministically avoid
   attention, and each remains auditable. Exact self-binding prevents waking
   only that author: the canonical event remains available to other
   participants and as later factual context for its author. Every other
   accepted native event appears in the next bounded current snapshot or the
   snapshot truthfully records what is missing and how authorized host code may
   fetch it. Newer events may replace the trigger but may not silently erase
   accepted context. Later resolution is shown as actual room context to the
   participant, never declared by deterministic code. There is no inferred
   roster, social handled/open ledger, or obligation queue. Each possible send
   has one recorded output-commit point: dispatch to the native transport. Work
   invalidated before that point cannot emit or revive stale conversation after
   delay, backpressure, restart, or backfill.

4. **The complete attention lifecycle works on the ordinary path.**
   `SUPPRESS`, `WAKE`, both `DEFER` paths, trusted pre-attention bypass,
   operational `ERROR`, direct participant contribution, and valid participant
   silence remain distinct. Bypass fabricates no model result. Operational
   failure wakes by default only from a valid current snapshot; without one it
   remains an explicit error with no fabricated social result or effect. A
   woken participant uses its normal room-action path or sends nothing, never
   an admission or intermediate meta-answer. No second social judgment,
   handled/open registry, or conversational permission gate runs at send time.
   The host deadline includes provider and network waiting time: expiry or
   cancellation closes a late result even when external delay caused it.

5. **Deterministic authority boundaries allow the right action and prevent the
   wrong one.** Before candidate freeze, every mutating, external,
   secret-bearing, account, and configuration effect and required capability
   is inventoried. Each is guarded or, if not required, explicitly disabled;
   disabling a required capability needs the same Zoe product-scope decision
   as removing a surface. The release-proof profile freezes impact
   classifications, with ambiguity treated as high impact. Ordinary room
   content may be conversational input but is never proof of authority.
   Immediately before dispatch, the host re-verifies the current actor, origin
   event, room, session, self-binding, capability, scope, policy, runtime,
   expiry, revocation, approval, and action digest, and consumes any grant
   atomically at one recorded effect-commit point. Cancellation or invalidation
   ordered before that point prevents dispatch; one ordered after it cannot
   retroactively erase a committed effect. High-impact actions require an
   inspectable, expiring, authenticated, digest-bound approval unless a narrow
   pre-authorization explicitly covers them. Every required effect class
   proves a successful authorized native path in a release-proof-profile-
   approved test target. Each grant permits at most one logical effect and is
   marked consumed at its first dispatch; it cannot authorize a different
   effect. Every transport attempt rechecks the current bindings, policy,
   expiry, and revocation. A target-attested success is recorded as confirmed,
   while a lost acknowledgement is `UNKNOWN`. The same logical effect may be
   retried only when the original grant and policy explicitly allow retry under
   the same target-enforced idempotency or deduplication key. Otherwise, a new
   authenticated approval must acknowledge the unknown prior outcome and
   duplicate-effect risk and authorize one distinct retry. Ordinary fresh
   authority or broad pre-authorization is not enough. Absent, unverifiable,
   forged, stale, copied, replayed, revoked, expired, mutated, mismatched, or
   time-of-check/time-of-use-changed authority causes zero initial dispatch.
   Deny-all is not a passing implementation.

6. **Silence and isolation are complete.** Every native outbound API is in the
   frozen surface inventory. `SUPPRESS`, participant silence, authorization
   denial, and work cancelled or invalidated before its output-commit point
   make zero calls to conversational or native outbound APIs across messages,
   typing, reactions, threads, drafts, errors, clarification or approval
   notices, private notices, media, voice, and platform equivalents. The
   universal exception is immutable off-surface receipts. A separately
   authenticated operator approval surface may emit a prompt only for an
   otherwise valid, authenticated, still-live proposal whose sole missing
   execution authority is the required approval. That prompt is itself an
   inventoried authorized effect, closes on cancellation, and is never an
   exception for `SUPPRESS`, participant silence, denial, or invalidated work.
   It may not appear as room output or a participant response. Observation,
   attention, participant-host, and transport receipts are request-correlated
   audit records written only by their owning stage. No user-visible output may
   bypass the host that invokes the participant and the transport's correlated
   send closure. Continuation fetch authority is host-only: the attention model
   sees no opaque handle, binding, cursor, expiry, or fetch secret. Rooms,
   profiles, identities, sessions, continuation authority, secrets, and
   receipts do not cross-contaminate under concurrency, failure, or restart.

7. **The real installed product works.** Release artifacts install in clean
   environments without editable links, repository imports, or `PYTHONPATH`
   assistance. Installed Codex, Hermes, and Claude Code runtimes with distinct
   identities complete the required scenes together in an authorized real
   room through native ingress and egress. Every other live-supported adapter
   proves its native path. Upgrade starts from the declared supported V1
   release with representative operator state; hard-kill restart preserves
   declared continuity; rollback restores the declared predecessor outcome
   without hand-editing source, configuration, or state. Nunchi-controlled
   latency, memory, retention, capacity, recovery, and starvation bounds are
   fixed before testing and met throughout the declared operating envelope.
   Explicit tests beyond each limit prove bounded, fail-safe overload behavior
   without cross-room starvation. External provider and network time are
   reported separately but remain subject to the host's total deadline.

8. **The repository stands alone.** A non-author records a cold-clone exercise
   with Aleph Vault, conversation history, ignored and untracked files, prior
   installations, private session state, and contributor-local configuration
   absent, then understands, builds, tests, installs, configures, operates,
   reviews, and continues the product using committed documentation alone.
   Documented host runtimes, platform accounts, room identifiers, endpoints,
   operator policy and participant-profile data, and credentials may be
   external and must be enumerated with their schemas, integrity, and
   provenance requirements. They may not provide missing product logic.
   Undisclosed product logic, patches, preexisting mutable state, or manual
   intervention may not be required.

9. **Dependencies are terminal before downstream work starts.** No inherited or
   new downstream implementation or platform packet is admitted, resumed, or
   reused toward completion until every declared upstream dependency is
   accepted at its exact effective commit and packet and contains every
   interface and control that consumer needs. Historical attempts remain
   non-candidates until revalidated against those exact terminal dependencies.
   A known missing requirement or required successor means the dependency is
   not terminal. Any change to an accepted effective commit or packet blocks
   all named direct and transitive consumers by default. A no-impact exception
   requires a machine comparison proving every consumed contract, schema,
   runtime, and behavior-shaping configuration byte unchanged, plus independent
   review. Otherwise, a consumer is released only after its applicable
   contract, security, install/runtime, and live proof passes against the exact
   successor; prose compatibility claims cannot unblock it. Incompatible work
   is replaced without regard to sunk cost.

10. **One frozen candidate closes review. Cutover is atomic and truth remains exact.**
    An input manifest freezes the exact source, dependencies, build and
    install instructions, integration inputs, behavior-shaping configuration,
    and proof profile before final build, install, or evidence. Build and
    installation attestations name that input manifest and record content-
    addressed artifact, installed-file, effective configuration, credential-
    identity/scope, and non-ephemeral process identity. Those attestations are
    then sealed into one immutable closure manifest. Only after closure do
    final deterministic, stochastic, installed-runtime, and live evidence runs
    begin against that sealed subject. At least two isolated reviewers from
    distinct model families—neither an author nor remediator of that
    candidate—keep candidate bytes read-only while using separate environments
    to verify the manifests and execute the complete review matrix. Any blocker
    creates an exact successor, a fresh held-back challenge set, and a complete
    new review. Zoe alone accepts or rejects the final repository commit, input
    manifest, and closure manifest through a durable decision.

    Atomic cutover means one `main` product tree, version, and artifact manifest
    in which no installed instance mixes retained V1 and V2 paths. Operator
    rollout may be staged only between isolated environments or rooms; a room
    or session never mixes V1 and V2 participants. The accepted subject is the
    manifest-covered product tree and inputs. A topology-only merge commit may
    have a different commit ID, but those covered bytes must be identical and
    the exact-main rebuild must reproduce the accepted artifact digests.
    Accepted sealed artifacts may be reused only when their manifest mapping
    and bytes remain exact; any mismatch is a blocker requiring a new closure
    and affected review. Every blocking proof is rerun against that exact
    `main` commit and current-state documentation is validated against
    installed behavior before V2 is complete. A post-merge
    blocker forbids any verified-current claim and requires an immediate revert
    or a newly frozen, fully reviewed, Zoe-accepted successor. Release and
    promotion remain separate decisions.

## Proof standard

Before final evidence begins, a committed release-proof profile freezes:

- the complete dependency graph, surface, per-surface capability and
  applicability, native-event, ingress, outbound-effect, privileged-effect,
  and supported-upgrade inventories;
- every canonical `S01`–`S18` scene selected in
  `specs/001-nunchi-v2-program/plan.md`, copied unchanged into an ordinary-path
  release profile and executable/evidence manifest, plus stricter public cases
  and reviewer-held challenge cases precommitted by digest and count under
  independent custody; reference definitions are provenance, never a build,
  test, evaluation, install, or runtime dependency;
- participant profiles, model families and versions, materially different
  parameterizations, sampling settings or seeds where available,
  configurations, trial counts, complete-run inclusion rules, and
  social-quality thresholds;
- the complete deterministic test and evaluation identifiers, expected
  coverage, and skip/exception counts present at final profile freeze, with the
  adoption-time inventory as a non-regression floor and a Zoe-approved V2
  replacement mapping for any retired V1 coverage;
- a threat model covering assets, trust boundaries, attacker capabilities,
  credentials, supply chain and installation, transport and identity,
  cancellation and races, capacity, and output escape paths, with explicit
  disposition of every risk, no unresolved Critical or High risk, and every
  residual risk included in Zoe's profile decision;
- operating and overload limits, recovery deadlines, upgrade/rollback state
  outcomes, severity rules, and blocking criteria; and
- the input- and closure-manifest boundaries and an exact review matrix naming
  reviewer families and reasoning settings and mapping every end condition,
  hard-zero invariant, `S01`–`S18` scene, and proof claim to independent review
  and reproduction.

Independent non-author reviewers and Zoe durably accept the initial profile
before any held-back or final candidate evidence runs. Thresholds and loads
must be justified against the selected product decisions, baselines, and
false-suppression risk and must reject near-degenerate behavior, not only exact
always-one-outcome implementations. The profile may grow stricter. Weakening
it or shrinking scope after results requires Zoe's explicit supersession and a
fresh candidate evidence run.

Evidence counts only under all of these rules:

- **One subject and one provenance chain.** The frozen input manifest covers
  every behavior-shaping non-secret byte and input: source, dependency locks,
  build scripts, integration patches, wrappers, hooks, configuration
  templates, and installation inputs. Pre-closure build and installation
  attestations name the input manifest; the sealed closure incorporates them
  and binds package, installed-file, effective non-secret configuration, and
  non-ephemeral process digests. Secret values remain secret, but their
  provider, account or bot identity, permission scope, reference, and policy
  provenance are attested. Every final test, evaluation, installed-runtime, and
  live record names the input and sealed closure manifests. A covered-byte,
  credential identity or scope, or behavior-shaping configuration change
  invalidates affected evidence.
- **Passing outcomes, not artifacts.** A document, task, test, demo, review, or
  evidence file does not count merely because it exists. The predeclared
  expected result must pass. Missing or unverifiable evidence is a failure, not
  a limitation. Documentation and governance alone cannot close a missing
  behavior, control, or live outcome.
- **Complete, attributable results.** Every execution after the proof profile
  or candidate input freezes—including aborted runs, failures, and reruns—is
  retained with the committed input, exact command and exit status, time,
  native event or run identity, model/runtime metadata, manifest identity, and
  raw result needed to reproduce the claim. Pre-freeze tuning evidence that
  influenced the product or profile is disclosed but cannot count as final
  evidence. Any necessary secret or personal-data redaction is declared and
  may not change the tested meaning. Selective reruns, hidden failures, deleted
  hard cases, new skips, and hand-authored summaries without underlying proof
  do not pass. Reviewer-held cases are revealed and committed with complete
  results after input freeze; each successor receives a fresh held-back set or
  a previously committed reserve that remained undisclosed.
- **The right evidence tier.** Deterministic tests prove deterministic
  semantics. Mocks and in-process substitutes never prove installed or live
  behavior. “Live” means the real supported runtime, identity, provider, native
  transport, and outbound API running the installed candidate.
- **No degenerate pass.** The proof profile must distinguish the intended
  product from always-`WAKE`, always-`SUPPRESS`, always-`DEFER`, deny-all,
  near-always-one-outcome, all-talk, and all-mute implementations. False
  suppression is the highest-risk stochastic error. Unauthorized dispatch,
  output from work invalidated before its commit point, cross-room/profile
  leakage, hidden V1 execution, unmanifested runtime bytes, and product-
  invariant breaches have a hard-zero tolerance.
- **Independent falsification.** Each reviewer independently evaluates every
  end condition and hard-zero invariant. The review matrix gives every
  applicable `S01`–`S18` outcome and proof claim at least two independent
  reviewer dispositions and at least one independent reproduction. Candidate
  bytes remain read-only; isolated installations and separately recorded
  reviewer evidence are allowed.
- **No evidence rewrite.** Reviewed evidence is immutable. A successor or
  changed proof profile receives fresh affected evidence and review. The
  post-merge follow-up may append exact-main verification and truthful
  current-state documentation; it may not replace or rewrite evidence used to
  accept the candidate or change any manifest-covered input. Independent
  review verifies that narrow diff and the prior evidence hashes. If either
  changes, the candidate must be frozen and reviewed again.

## Completion decision

Completion is a product claim about one exact candidate, not the sum of checked
tasks, accepted packets, green checks, or approvals. A technical reading of a
check cannot override a failed product outcome, security boundary, or
invariant. If any required surface, end condition, or proof rule is false,
unknown, or unproven, Nunchi V2 remains incomplete.
