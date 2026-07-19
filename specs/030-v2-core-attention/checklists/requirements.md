# Specification Quality Checklist: V2 Core Attention

**Purpose**: Validate that the attention-engine requirements are complete,
human-shaped, measurable, lifecycle-safe, and integration-ready

**Created**: 2026-07-11

**Slice specification**: [spec.md](../spec.md)

## Scope and Ownership

- [x] CHK001 Is the `PLANNED` slice and its separately documented `GRANTED` program authority distinguished explicitly from current V1 implementation truth, with tasks `DORMANT` until immutable activation establishes `READY`? [Clarity, Spec §Control-Plane Boundary]
- [x] CHK002 Are all product, test, eval, evidence, and documentation targets ordinary paths? [Consistency, Spec §Control-Plane Boundary, FR-016]
- [x] CHK003 Is `v2-core-owner` the sole I-030A owner with complete upstream and downstream handoffs? [Completeness, Spec §Interface Summary]
- [x] CHK004 Are observation, participant hosting, surface integration, final cutover, release, and margin retirement excluded? [Coverage, Spec §Explicit Exclusions]

## Judgment and Transition Requirements

- [x] CHK005 Is the single attention question narrow, participant-shaped, and free of speaker-algorithm or reply-composition requirements? [Clarity, Spec §FR-002–FR-003]
- [x] CHK006 Are classifier dispositions, trusted no-classifier preattention bypass, and operational ERROR unambiguously separate? [Consistency, Spec §FR-004, FR-017]
- [x] CHK007 Are advice authority, grounding, allowed disposition, and reply-prose prohibitions complete? [Completeness, Spec §FR-005]
- [x] CHK008 Are all suppression-legitimacy conditions and trusted operator-policy boundaries specified? [Completeness, Spec §FR-006–FR-007]
- [x] CHK009 Are direct DEFER, margin DEFER, the inclusive `PASS - max(ACK, ASK, SPEAK) <= transition_defer_margin` boundary, malformed confidence evidence, allowed widening, and margin-retirement boundaries clear? [Clarity, Spec §FR-008–FR-010]
- [x] CHK010 Are all validation/provider/timeout/config/runtime failures, the wake-default trust boundary, and the explicit NO_WAKE override defined without social relabeling and representable through accepted I-010E `@2`'s exact paired override fields? [Coverage, Spec §Resolved post-acceptance contract blocker, FR-011]

## Scenario, Security, and Evidence Coverage

- [x] CHK011 Do scenarios cover confident suppress, grounded wake advice, direct DEFER, margin DEFER, disabled delegation, trusted preattention bypass, unproven recovery, ERROR, and core/CLI parity? [Coverage, Spec §User Scenarios & Testing]
- [x] CHK012 Are forged output/advice, request-controlled configuration, provider retries, invalid transitions, trusted actual/declared attention-budget boundaries, host-secret projection leaks, same-class address, and apparent-resolution scars addressed? [Edge Case, Spec §Edge Cases]
- [x] CHK013 Is the immutable attention stage limited to accepted I-010E `@2`'s closed classifier/bypass, effective-route, valve, policy/model-source, and error shapes when a valid request ID exists, while representing every selected effective-policy and NO_WAKE provenance obligation and forbidding fabricated IDs/receipts for unassignable pre-validation failures and downstream host/transport facts? [Completeness, Spec §Resolved post-acceptance contract blocker, FR-012]
- [x] CHK014 Are deterministic mechanics, replay, multi-model evidence, downstream canary protocol, and margin evidence distinguished so unit tests cannot overclaim social quality or create a dependency cycle? [Evidence, Spec §FR-014, SC-004–SC-006]
- [x] CHK015 Can every success criterion and handoff obligation be measured against a named ordinary artifact or result? [Measurability, Spec §SC-001–SC-008, FR-015]
- [x] CHK016 Is the exact CLI stdout/stderr/exit 0/1/2/3 process contract complete for valid, bypass, schema-invalid, operational, and unreadable inputs? [Completeness, Spec §FR-019]
- [x] CHK017 Are host-only continuation secrets excluded from classifier input while the bound capability remains available to the participant host? [Security, Spec §FR-018–FR-020]
- [x] CHK018 Does documentation freshness inventory every exact known affected path, require V2 and retained-V1 evaluation `UPDATE` rows, route shared/downstream `HANDOFF` deltas including `README.md` to accepting owners, and require validation/reviewer evidence? [Documentation, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]
- [x] CHK019 Does readiness require the slice-specific bound delivery command `python3 scripts/run_slice_workflow.py run speckit specs/030-v2-core-attention`, which performs preflight atomically; a paused run with an unchanged task graph resumes only by run ID, an assigned participant plus durable external assignment source declared before readiness, the valid complete program authorization record enumerating exactly `010` through `110`, accepted `010-v2-contract`, active `v2-core-owner`, zero CRITICAL/HIGH findings, and an isolated worktree, with `evidence/v2/attention/slice-activation.md` written afterward to copy/attest those facts and establish `READY` before `ACTIVE` or any implementation checkbox? [Lifecycle, tasks.md §Slice activation]

- [x] CHK020 Does activation evidence preserve declared dependency order, use ordered `Dependency commits` as `slice=full-sha` with matching ordered `Dependency acceptance references` as `slice=repo-relative-evidence-file`, and keep candidate/handoff attempts append-only across `REJECTED` return-to-`ACTIVE` rework, which starts a new bound run rather than resuming the completed run, and do convergence-added tasks likewise require a new run while paused unchanged-task fixes may resume? [Lifecycle, Spec/Plan/Tasks metadata]

## Notes

- CHK010 and CHK013 now pass through independently accepted I-010E `@2`.
  The earlier incompatibility remains immutable history at
  `evidence/v2/attention/dependency-010-post-acceptance-blocker.md`, alongside
  the original acceptance; the updated consumer decision is recorded at
  `evidence/v2/attention/dependency-010-amendment-A1-acceptance.md`. These
  checks do not claim that I-030A, V2 CLI behavior, or social evidence exists.

## Formal Reviewer Run — 2026-07-18

**Purpose**: Apply a formal reviewer gate to requirement quality, governance
boundaries, and documentation-freshness dispositions before delivery analysis
or implementation readiness.

**Depth**: Formal blocking review

**Actor / timing**: Peer reviewer after spec, plan, and task-graph review and
before the zero-CRITICAL/HIGH analysis and slice-readiness gates

### Requirement Completeness

- [x] CHK021 Are the required request, decision, receipt, callable-core, and CLI semantics complete for `SUPPRESS`, `WAKE`, classifier `DEFER`, margin `DEFER`, trusted `bypass`, and operational `error`, including the allowed fields and process outcomes for every branch? [Completeness, Spec §FR-001, FR-004, FR-008, FR-017, FR-019; Plan §CLI Process Contract]
- [x] CHK022 Are all prerequisites for effective social suppression documented, including exact participant authorization, trusted recoverability, operator delegation and revocation, transition evidence, and the provenance of each prerequisite? [Completeness, Spec §FR-001, FR-006–FR-009; Plan §Trusted recoverability capability]
- [x] CHK023 Are the complete trusted-configuration inputs, single-source/conflict rules, participant/scope bindings, room-input exclusions, secret-handling constraints, sink protocol, and audit obligations specified and representable for provider, model, actual and declared event/projection-byte budgets (including canonicalization, equality, overage, call, receipt, and no-truncation behavior), the exact point at which `NO_WAKE` gains authority, error action, suppression, and margin policy through accepted I-010E `@2` where receipt facts are owned? [Completeness, Security, Spec §FR-001, FR-007, FR-011, FR-012, FR-018; Plan §I-030A callable and CLI equivalence seam, Trusted attention-budget boundary, Bypass operational error and CLI parity, Accepted contract amendment resolution]
- [x] CHK024 Does the handoff requirement enumerate every recipient and every required packet fact—exact commit, consumed and produced interface versions, commands/results, model and policy provenance, evidence, canary protocol, margin state, documentation dispositions, rejected claims, limitations, and dependency acceptance expectations? [Completeness, Spec §FR-015, SC-007; Plan §Owner Handoff; Tasks §T026]

### Requirement Clarity

- [x] CHK025 Are qualitative terms such as “participant-shaped,” “sparse,” “short,” “brief,” “cheap uncertainty,” “inspectable,” “revocable,” and “recoverability eligibility” defined tightly enough for two reviewers to reach the same requirement interpretation? [Ambiguity, Spec §FR-002, FR-005, FR-006; Plan §One judgment and the dual-valve transition]
- [x] CHK026 Is “one logical model judgment” distinguished unambiguously from transport retries through specified retry boundaries, idempotency expectations, maximum attempts or budgets, and terminal-failure semantics? [Ambiguity, Spec §FR-003; Plan §Technical Context]
- [x] CHK027 Are classifier disposition, effective disposition, response status, routing valve, override cause, bypass provenance, and downstream wake source defined as distinct concepts with no branch that can be interpreted in two ways? [Clarity, Spec §FR-004, FR-008, FR-011, FR-012, FR-017; Plan §Bypass, operational error, and CLI parity]
- [x] CHK028 Is the required legacy confidence vector identified by an exact accepted contract location and are “valid margin,” active-margin precedence, and the evidence/authority needed for later retirement stated without leaving local interpretation to slice 030? [Clarity, Dependency, Spec §FR-008, FR-009, SC-006; Plan §Contract authority and runtime validation]
- [x] CHK029 Is selected V2 target language consistently distinguishable from current V1 behavior, an accepted-but-verification-pending cutover, and `CUTOVER_VERIFIED`, so no planning or component claim can imply that V2 is current? [Clarity, Spec §Control-Plane Boundary, Explicit Exclusions; Constitution §Selected V2 Product Boundary, Documentation Freshness Gate]

### Requirement Consistency and Conflicts

- [x] CHK030 Do the spec, plan, and tasks agree on `PLANNED` state, `GRANTED` program authority, dormant execution, the assigned participant/source, accountable lane, dependency, activation path, and exact workflow binding? [Consistency, Spec metadata; Plan metadata; Tasks metadata]
- [x] CHK031 Are I-010A/B/E and I-030A identifiers, versions, schema/source paths, read-only ownership, and downstream recipients identical across the interface summary, slice-interface plan, ordinary targets, task graph, and handoff requirements? [Consistency, Spec §Interface Summary, FR-001, FR-015; Plan §Slice Interfaces, Ordinary Repository Targets; Tasks §Dependencies & Execution Order]
- [x] CHK032 Do the lifecycle requirements consistently separate external program authority, assignment, dependency acceptance, activation evidence, `READY`, owner-declared `ACTIVE`, task execution, convergence, documentation freshness, handoff, and recipient acceptance? [Consistency, Spec metadata; Plan metadata; Tasks §Slice activation; Constitution §Program and Slice Lifecycle Gates]
- [x] CHK033 Are the matching `NO_IMPACT` dispositions for `integrations/mcp-discord/README.md` and `integrations/mcp-discord/DESIGN.md` in the spec and plan backed by the same gate-neutral transport rationale and ordinary handoff-evidence obligation? [Consistency, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]
- [x] CHK034 Are the complete documentation path inventory, per-path owner, disposition, validation/rationale/delta, and T025/T026 responsibility consistent across the spec, plan, and tasks, including paths present in only one artifact? [Consistency, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness; Tasks §T025–T026]

### Governance Boundaries

- [x] CHK035 Does the requirements set state the authority order and the required resolution path when the selected Vault design, constitution, runtime guidance, slice artifacts, or current ordinary-path truth conflict? [Completeness, Governance, Spec §Authority source; Constitution §Authority and Repository Boundaries]
- [x] CHK036 Are planning-only content and ordinary-path product artifacts separated exhaustively, including explicit homes for schemas, source, tests, corpora, evidence, runtime assets, and product documentation and a prohibition on ordinary commands depending on managed paths? [Boundary, Spec §Control-Plane Boundary, FR-016, SC-008; Constitution §SpecKit Is Control-Plane Only]
- [x] CHK037 Are the single-owner boundaries complete for slice-030 source, 010-owned schemas, 020 observation, 040 participant hosting, surface integrations, shared documentation, and slice-110 integration, with an explicit escalation or handoff rule for every out-of-scope change? [Ownership, Spec §Interface Summary, Explicit Exclusions; Plan §Integration Strategy; Tasks §Notes]
- [x] CHK038 Are slice-readiness requirements written as a conjunction of one complete eleven-slice authority record, durable owner assignment, exact accepted 010 commit, consumer-owned dependency acceptance reference, zero CRITICAL/HIGH findings, isolated worktree, and immutable activation evidence—without allowing any one fact to imply the others? [Completeness, Governance, Spec metadata; Tasks §Activation prerequisites; Constitution §Program and Slice Lifecycle Gates]
- [x] CHK039 Are the durable assignment requirements complete for assignee, exact lane, assigner, ISO date, authority reference, and non-Zoe delegation fields, while making clear that assignment neither grants implementation authority nor activates the slice? [Completeness, Governance, Spec metadata; Constitution §Program and Slice Lifecycle Gates]
- [x] CHK040 Are activation, candidate, handoff, rejection, rework, and acceptance record requirements explicit about immutability versus append-only history, exact commits/task hashes, decision ownership, and when a new bound run is mandatory versus when resume is allowed? [Completeness, Governance, Spec metadata; Plan metadata; Tasks metadata; Constitution §Program and Slice Lifecycle Gates]
- [x] CHK041 Is delivery-owner handoff kept separate from `v2-integrator` acceptance or rejection, with no requirement permitting slice 030, the program owner, or workflow completion to fabricate the recipient’s decision? [Ownership, Spec §Interface Summary; Plan §Owner Handoff; Constitution §Program and Slice Lifecycle Gates]
- [x] CHK042 Do the requirements prohibit lifecycle status, assignment, dependency acceptance, or authorization from becoming a central mutable registry, runtime state, conversation/classifier input, receipt data, roster, social ledger, or memory service? [Boundary, Gap, Constitution §Program and Slice Lifecycle Gates; Spec §FR-012, Explicit Exclusions]
- [x] CHK043 Are atomic integration, cutover acceptance, exact-main verification, final current-state documentation, release, and promotion assigned only to their authorized owners and kept outside the slice-030 completion claim? [Ownership, Spec §Control-Plane Boundary, Explicit Exclusions; Plan §Integration Strategy, Owner Handoff; Constitution §Program and Slice Lifecycle Gates]

### Acceptance Criteria and Evidence Quality

- [x] CHK044 Is “contract-equivalent” defined by an objective comparison rule for core and CLI outputs, including which audit/provenance fields must match exactly and which values, if any, may legitimately differ? [Measurability, Ambiguity, Spec §FR-001, SC-001; Plan §CLI Process Contract]
- [x] CHK045 Is the complete transition-matrix domain enumerated so “zero invalid success pairs” and “zero unsafe suppression” have a finite, reproducible denominator across dispositions, policy states, recoverability, margin evidence, and error overrides? [Measurability, Spec §SC-002; Tasks §T003, T014–T017]
- [x] CHK046 Are social-quality acceptance thresholds or explicit non-gating evidence rules defined for mistaken suppressions, missed suppressions, wake volume, three-family disagreement, and false-suppression scars, rather than requiring reports whose pass/fail meaning is unspecified? [Gap, Measurability, Spec §FR-014, SC-004, SC-005; Plan §Acceptance Scenes and Evidence]
- [x] CHK047 Are model/evaluation records required to include enough immutable provenance to reproduce and compare attempts—canonical scene IDs, exact provider model ID, provider and endpoint class, date, prompt/config identity, policy source, commands, results, and override authority? [Traceability, Spec §FR-014; Plan §Acceptance Scenes and Evidence; Tasks §T023]
- [x] CHK048 Do the success criteria distinguish what deterministic tests, replay, multi-model runs, preregistered downstream canaries, installed-runtime evidence, and final live parity can each establish, including explicit claims that remain unavailable at slice-030 handoff? [Evidence, Consistency, Spec §FR-014, SC-004–SC-007, Explicit Exclusions; Plan §Owner Handoff]

### Scenario, Edge-Case, and Non-Functional Coverage

- [x] CHK049 Are primary, alternate, exception, and recovery requirements complete for confident suppression, grounded wake, both DEFER valves, disabled preattention bypass, suppression-policy widening, validation/provider/runtime failure, untrusted raw/partial versus fully trusted `NO_WAKE`, and retry exhaustion, with the override represented by accepted I-010E `@2`? [Coverage, Spec §User Scenarios & Testing, Resolved post-acceptance contract blocker, Edge Cases]
- [x] CHK050 Are policy-change scenarios specified for revocation, recoverability becoming unavailable, configuration-source conflict (including a parseable `NO_WAKE` that never gains authority), margin evidence becoming malformed, and a later margin-retirement decision, including the validation-first/first-match safe route for each case? [Coverage, Spec §FR-001, FR-006–FR-011, SC-006; Plan §One judgment and the dual-valve transition, Finite transition and social-evidence gates]
- [x] CHK051 Are hostile and malformed-input requirements complete for forged structured output, unknown evidence IDs, reply-bearing advice, non-finite confidence values, request-controlled secrets/policy, illegal disposition pairings, and classifier projection of host-only continuation material? [Coverage, Security, Spec §Edge Cases, FR-005, FR-007, FR-009, FR-018, FR-020]
- [x] CHK052 Are non-functional requirements explicit that latency/byte/token metrics are descriptive/non-gating, enumerate their required fields and environment, mechanically bound provider retries, prove no secret exposure, preserve immutable/request-correlated audit and offline determinism, and prohibit extending the closed I-010E body with performance fields? [Non-Functional, Spec §FR-003, FR-012, SC-008; Plan §Technical Context, Receipt and performance evidence boundary]

### Documentation Freshness Dispositions

- [x] CHK053 Does the documentation review enumerate `README.md` and every exact affected ordinary path across behavior, contracts, configuration/defaults, install/upgrade, entry points, supported surfaces, security, evidence grade, limitations, version/current state, diagrams, examples, and commands, with exactly one disposition per path? [Completeness, Documentation, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness; Constitution §Documentation Freshness Gate]
- [x] CHK054 Does every `UPDATE` requirement name the exact document, claim delta, accountable task/lane, candidate-relative validation for links/diagrams/examples/commands/machine-checkable claims, and the evidence that determines pass or fail? [Completeness, Measurability, Plan §Documentation Impact and Freshness; Constitution §Documentation Freshness Gate]
- [x] CHK055 Does every `NO_IMPACT` requirement name one exact path, give a concrete candidate-specific rationale, require ordinary-path handoff evidence plus reviewer identity, and remain rejectable when the candidate diff or resulting claim invalidates that rationale? [Completeness, Measurability, Plan §Documentation Impact and Freshness; Constitution §Documentation Freshness Gate]
- [x] CHK056 Does every `HANDOFF` requirement identify a shared or downstream-owned exact file, state the exact required claim delta, name the accepting owner, prohibit use for slice-owned documents, and avoid treating handoff as no impact? [Completeness, Ownership, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness; Constitution §Documentation Freshness Gate]
- [x] CHK057 Is the `README.md` handoff precise about the accepted I-030A disposition, bypass, ERROR, CLI, dual-DEFER, active-margin, and verification-pending deltas while prohibiting any slice-030 or atomic-candidate wording that presents V2 as verified current behavior? [Clarity, Documentation, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness; Constitution §Documentation Freshness Gate]
- [x] CHK058 Are the slice-owned `docs/attention/v2.md` update and the retained-V1 contract/evaluation updates required to distinguish component evidence, historical scar evidence, current V1 truth, planned V2 integration, and unavailable downstream live results without premature parity or cutover claims? [Consistency, Documentation, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]
- [x] CHK059 Do T025 and T026 require documentation work and its exact evidence before convergence/handoff while preserving the later workflow-owned documentation-freshness decision, and is the pass/fail packet contract defined for exact candidate commit, reviewed paths, dispositions, validation results, reviewer, rationales/deltas, and accepting owners? [Traceability, Governance, Tasks §T025–T026; Plan §Documentation Impact and Freshness, Owner Handoff]

## Formal Reviewer Notes

- Mark an item complete only when the requirement text itself is complete,
  clear, consistent, measurable, and traceable. Passing implementation tests is
  not evidence that these requirement-quality items pass.
- Record blocking findings inline with the affected CHK ID and reject analysis
  readiness while any unresolved requirement ambiguity, governance conflict, or
  documentation-disposition conflict remains.

## Formal Reviewer Refresh — 2026-07-19

**Purpose**: Re-review the current requirement text after the authority,
participant-shaped judgment, evidence-provenance, handoff, and exact
documentation-inventory clarifications.

**Depth**: Formal blocking review

**Actor / timing**: Peer reviewer after the current spec, plan, and task-graph
review and before zero-CRITICAL/HIGH analysis, slice activation, or
implementation

### Requirement Quality

- [x] CHK060 Are I-030A callable, CLI, decision, and receipt requirements complete for classifier `SUPPRESS`, `WAKE`, and `DEFER`, effective routing, trusted `bypass`, operational `error`, and every stdout/stderr/exit branch without conflating social and non-social outcomes? [Completeness, Spec §FR-001, FR-004, FR-008, FR-012, FR-017, FR-019; Plan §CLI Process Contract]
- [x] CHK061 Is “participant-shaped and sparse” defined by the exact classifier perspective, attention question, disposition guidance, grounding rule, and prohibited speaker/address/topology/obligation/reply rules, so two reviewers need not supply their own social rubric? [Clarity, Spec §FR-002; Vault technical design §Governed model pre-attention]
- [x] CHK062 Are “cheap uncertainty,” “inspectable,” “revocable,” and “recoverability eligibility” defined through explicit facts, provenance, and safe widening behavior rather than remaining qualitative suppression-legitimacy labels? [Clarity, Spec §FR-006–FR-010; Plan §Trusted recoverability capability, One judgment and the dual-valve transition]
- [x] CHK063 Are model and evaluation provenance requirements complete and objective for canonical scene/corpus identity, exact provider model, endpoint class, date, prompt/config identity, effective-policy source, command, result, and any Zoe-authorized substitution? [Completeness, Traceability, Spec §FR-014, SC-005; Plan §Acceptance Scenes and Evidence; Tasks §T023]
- [x] CHK064 Does the owner-handoff requirement enumerate every recipient and every packet fact, including exact commit roles, consumed/produced versions, commands/results, evidence classes, canary protocol, margin state, documentation dispositions, rejected claims, limitations, publication/deletion delta, and each dependent’s separate acceptance duty? [Completeness, Spec §FR-015, SC-007; Plan §Owner Handoff; Tasks §T026]
- [x] CHK065 Are the primary, alternate, exception, recovery, and hostile-input requirements complete for both DEFER valves, trusted bypass, suppression revocation, raw/partial versus fully trusted `NO_WAKE`, malformed transition evidence, retry exhaustion, receipt persistence uncertainty, and host-secret projection attempts? [Coverage, Spec §User Scenarios & Testing, Edge Cases, FR-003, FR-006–FR-012, FR-017–FR-020]
- [x] CHK066 Are “contract-equivalent,” “zero unsafe suppression,” and documentation-freshness PASS defined with finite comparison domains, exact allowed differences, evidence grades, and explicit blocking/non-gating rules rather than implementation-success language? [Measurability, Spec §SC-001–SC-008, Documentation Freshness; Plan §Finite transition and social-evidence gates]

### Governance Boundaries

- [x] CHK067 Does the requirements set state the selected-target authority order and an explicit escalation path while separately recognizing ordinary-path artifacts as authority for current implementation and evidence truth? [Governance, Clarity, Spec §Authority source, Control-Plane Boundary; Constitution §Authority and Repository Boundaries]
- [x] CHK068 Is current V1 behavior distinguished consistently from selected V2 design, staged non-current slice-030 symbols, an accepted-but-verification-pending atomic candidate, and final `CUTOVER_VERIFIED` current-state claims? [Consistency, Spec §Control-Plane Boundary, FR-013, Explicit Exclusions; Plan §Green pre-cutover staging, Integration Strategy]
- [x] CHK069 Are the control-plane boundary requirements exhaustive about allowed SpecKit content, ordinary homes for product artifacts, and the prohibition on build/test/eval/docs/package/release/runtime commands depending on managed paths? [Boundary, Spec §Control-Plane Boundary, FR-016, SC-008; Constitution §SpecKit Is Control-Plane Only]
- [x] CHK070 Do the requirements prohibit authority, assignment, dependency acceptance, lifecycle, handoff, or acceptance facts from becoming runtime/configuration/conversation/classifier/receipt state, a roster, social ledger, obligation queue, or memory service? [Boundary, Spec §Control-Plane Boundary, Explicit Exclusions; Constitution §Program and Slice Lifecycle Gates]
- [x] CHK071 Are durable assignment requirements complete for a non-symlink record, assignee, exact lane, assigner, ISO date, authority reference, conditional Zoe-delegation fields, and the statement that assignment grants neither program authority nor readiness/activation? [Completeness, Governance, Spec metadata; Constitution §Program and Slice Lifecycle Gates]
- [x] CHK072 Is slice readiness written as a conjunction of the exact eleven-slice authorization record, durable assignment, exact accepted 010 dependency and consumer acceptance, zero CRITICAL/HIGH findings, isolated worktree, frozen starting baseline/task manifest, and immutable activation evidence before `ACTIVE` or any checkbox? [Completeness, Governance, Spec metadata; Tasks §Activation Gate; Constitution §Program and Slice Lifecycle Gates]
- [x] CHK073 Do spec, plan, and tasks consistently consume accepted I-010E `AttentionReceiptV2@2` and its paired `NO_WAKE`/`policy_provenance` representation while preserving prior acceptance/blocker history and forbidding a 030-owned schema or free-text substitute? [Consistency, Dependency, Spec §Resolved post-acceptance contract blocker, FR-012; Plan §Accepted contract amendment resolution; Tasks §Resolved upstream finding]
- [x] CHK074 Are activation/acceptance immutability, candidate/handoff append-only history, exact commit/task-hash binding, rejection return to `ACTIVE`, and new-run versus resume rules complete and mutually consistent across all three control-plane artifacts? [Consistency, Governance, Spec metadata; Plan metadata; Tasks metadata; Constitution §Program and Slice Lifecycle Gates]
- [x] CHK075 Are 030 ownership, out-of-scope escalation, delivery handoff, `v2-integrator` acceptance/rejection, dependent-owner acceptance, slice-110 atomic integration, exact-main verification, release, and promotion requirements assigned without overlap or silent ownership transfer? [Ownership, Spec §Interface Summary, FR-015, Explicit Exclusions; Plan §Integration Strategy, Owner Handoff; Tasks §Post-Task Lifecycle Gates]

### Documentation Freshness Dispositions

- [x] CHK076 Is the exact-path inventory requirement measurable as the same 32 unique paths across spec, plan, and T025 with exactly 6 `UPDATE`, 14 `NO_IMPACT`, and 12 `HANDOFF` dispositions? [Measurability, Consistency, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness; Tasks §T025]
- [x] CHK077 Does the documentation review require one disposition for every exact affected ordinary path across behavior, contracts, configuration/defaults, install/upgrade, entry points, supported surfaces, security, evidence grade, limitations, version/current/release state, diagrams, examples, and commands, with no grouped path or wildcard substitution? [Completeness, Documentation, Spec §Documentation Freshness; Constitution §Documentation Freshness Gate]
- [x] CHK078 Does every `UPDATE` requirement name the exact document, concrete claim delta, accountable task/lane, candidate-relative validation for applicable links/diagrams/examples/commands/machine-checkable claims, and ordinary evidence needed for PASS? [Completeness, Measurability, Plan §Documentation Impact and Freshness; Constitution §Documentation Freshness Gate]
- [x] CHK079 Does every `NO_IMPACT` requirement name one exact path, give a concrete candidate-specific rationale, require reviewer identity and ordinary handoff evidence, and remain rejectable when the exact candidate diff or resulting claim invalidates the rationale? [Completeness, Measurability, Plan §Documentation Impact and Freshness; Constitution §Documentation Freshness Gate]
- [x] CHK080 Does every `HANDOFF` requirement identify an exact shared or downstream-owned file, state the exact required claim delta, name the accepting owner, prohibit use for slice-owned documents, and avoid representing downstream work as completed or no-impact? [Completeness, Ownership, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness; Constitution §Documentation Freshness Gate]
- [x] CHK081 Is the `README.md` handoff requirement precise about I-030A dispositions, trusted bypass, operational ERROR, CLI 0/1/2/3 behavior, dual-DEFER and active-margin state, while preserving verification-pending wording until exact-main proof and final documentation validation? [Clarity, Documentation, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness; Constitution §Documentation Freshness Gate]
- [x] CHK082 Are documentation path, disposition, owner, validation/rationale/delta, evidence location, and task responsibility consistent across the spec inventory, plan matrix, T025, T026, candidate requirements, and handoff packet requirements? [Consistency, Documentation, Spec §FR-015, Documentation Freshness; Plan §Documentation Impact and Freshness, Owner Handoff; Tasks §T025–T026]
- [x] CHK083 Is documentation-freshness PASS tied to the exact lifecycle candidate and ordinary evidence, with explicit rejection of stale inventories, bare assertions, premature current-state claims, missing validation/reviewer facts, or any disposition that no longer matches the candidate diff? [Acceptance Criteria, Documentation, Spec §Documentation Freshness; Tasks §Post-Task Lifecycle Gates; Constitution §Documentation Freshness Gate]

### Amendment and owner-handoff refresh

- [x] CHK084 Do spec, plan, and tasks consistently consume accepted I-010B
  `AttentionDecisionV2@2`, bind exact A2-R1 candidate
  `26a6b531fa146ba1f1f5fcd1c4d191041b141301`, preserve the earlier
  acceptance/blocker history, and require the inclusive `[0,1]`
  applied-margin domain without changing another decision rule? [Consistency,
  Dependency, Spec §Resolved post-acceptance contract amendments; Plan
  §Accepted contract amendment resolution; Tasks §Resolved upstream findings]
- [x] CHK085 Is the stale program interface registry kept as an exact
  `v2-program-owner` handoff—neither silently edited nor claimed complete by
  slice 030—while remaining outside this bound slice's dependency and
  CRITICAL/HIGH task-graph findings? [Ownership, Scope, Spec §Resolved
  post-acceptance contract amendments; Plan §Planning Decisions; Tasks §Open
  program-owner handoff]
- [x] CHK086 Do spec, plan, tasks, and acceptance scenes consistently require
  every receipt-sink invocation failure—both `not-persisted` and `unknown`—to
  use the shared `WAKE` default, forbidding a previously trusted `NO_WAKE`
  override when its required receipt did not persist? [Consistency, Safety,
  Spec §Clarifications, FR-001, FR-012; Plan §I-030A callable and CLI
  equivalence seam, Bypass operational error and CLI parity; Tasks §T004,
  T018, T021]

## Formal Reviewer Refresh Notes

- Mark an item complete only when the requirement text itself is complete,
  clear, consistent, measurable, and traceable. Passing implementation tests is
  not evidence that these requirement-quality items pass.
- Record blocking findings inline with CHK060–CHK086 and reject analysis
  readiness while any unresolved requirement ambiguity, governance conflict,
  ownership leak, or documentation-disposition mismatch remains.
- This refresh does not establish `READY`, create activation evidence, or
  authorize implementation.

**2026-07-19 refresh result**: 86/86 requirement-quality items pass after the
slice-owned clarifications and accepted dependency amendments. Accepted I-010B
`@2` clears the zero-margin dependency conflict; the stale program registry is
an explicit non-blocking `v2-program-owner` handoff rather than a bound-slice
finding. Slice 030 remains `PLANNED` pending fresh bound analysis and the
remaining activation prerequisites.
