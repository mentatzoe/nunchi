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
- [x] CHK013 Is the immutable attention stage limited to accepted I-010E `@2`'s closed classifier/bypass, effective-route, valve, policy/model-source, and error shapes when a valid request ID and eligible host-owned sink exist, while distinguishing a single offered record from established persistence, representing every selected effective-policy and NO_WAKE provenance obligation, and forbidding fabricated IDs/receipts for unassignable or no-sink paths and downstream host/transport facts? [Completeness, Spec §Resolved post-acceptance contract blocker, FR-012]
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
- [x] CHK047 Are model/evaluation requirements deterministic before execution through a committed closed family-to-exact-model selection manifest, and do results include enough immutable provenance to reproduce and compare attempts—canonical scene IDs, manifest identity, exact provider model ID, provider and endpoint class, date, prompt/config identity, policy source, commands, results, and override authority? [Traceability, Spec §FR-014; Plan §Acceptance Scenes and Evidence; Tasks §T009, T023]
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

- [x] CHK076 Is the exact-path inventory requirement measurable as the same 47 unique paths across spec, plan, and T025 with exactly 8 `UPDATE`, 17 `NO_IMPACT`, and 22 `HANDOFF` dispositions? [Measurability, Consistency, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness; Tasks §T025]
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

## Formal Reviewer Delta Gate — 2026-07-19

**Purpose**: Apply a fresh formal requirements review after the plan expanded
the documentation-freshness matrix and sharpened the program-registry and
slice-110 handoff boundaries.

**Depth**: Formal blocking review

**Actor / timing**: Peer reviewer after spec, plan, and task-graph
reconciliation and before zero-CRITICAL/HIGH analysis, slice activation, or
implementation

**Review status**: Complete. These items were reviewed independently against
the reconciled spec, plan, and dormant task graph; they do not merely inherit
the earlier 86/86 result.

### Requirement Quality

- [x] CHK087 Are the callable, CLI, decision, receipt, bypass, operational-error, and sink-failure requirements still complete and mutually traceable after the current planning revision, without allowing a documentation-only delta to obscure any I-030A branch? [Completeness, Traceability, Spec §FR-001, FR-004, FR-008, FR-012, FR-017, FR-019; Plan §I-030A callable and CLI equivalence seam]
- [x] CHK088 Are “slice-local clarification,” “accepted-dependency contract blocker,” “non-blocking handoff,” and “zero scoped CRITICAL/HIGH findings” defined with objective inclusion, exclusion, ownership, and closure criteria so reviewers cannot classify the same mismatch differently? [Ambiguity, Plan §Planning Decisions; Spec §Resolved post-acceptance contract amendments and program handoff; Tasks §Open program-owner handoff]
- [x] CHK089 Is the exact slice-110 deletion/publication requirement consistent across the planning decision, owner-handoff obligation, specification, and task graph, including the six named source files, removed V1/staging surfaces, and atomically published I-030A names? [Consistency, Plan §Green pre-cutover staging, Owner Handoff; Spec §FR-013, FR-015; Tasks §T020, T026]
- [x] CHK090 Are every success-criterion denominator, blocking rule, evidence grade, and allowed surface difference objectively defined, including contract equivalence, the 36-row transition domain, pre-run exact model selection, social-evidence non-gates, activation-to-candidate commit-range verification, and documentation-freshness PASS? [Measurability, Spec §SC-001–SC-008; Plan §Acceptance Scenes and Evidence, Candidate Verification Commands]
- [x] CHK091 Are primary, alternate, exception, recovery, and hostile-input requirements complete for both DEFER valves, trusted bypass, raw or partially trusted `NO_WAKE`, receipt-sink persistence failure, retry exhaustion, malformed evidence, and host-only continuation material? [Coverage, Spec §User Scenarios & Testing, Edge Cases, FR-001, FR-003, FR-006–FR-012, FR-017–FR-020]
- [x] CHK092 Can every requirement and success criterion be traced to an accountable task, exact ordinary-path artifact, evidence record, and lifecycle gate without treating passing implementation checks as proof of requirement quality? [Traceability, Spec §FR-001–FR-020, SC-001–SC-008; Plan §Ordinary Repository Targets; Tasks §T001–T027, Post-Task Lifecycle Gates]
- [x] CHK093 Are current V1 behavior, non-current slice-030 staging, an accepted but verification-pending atomic candidate, and `CUTOVER_VERIFIED` current behavior distinguished consistently in all requirement, handoff, and documentation claims? [Consistency, Spec §Control-Plane Boundary, FR-013, Documentation Freshness, Explicit Exclusions; Plan §Green pre-cutover staging, Integration Strategy]

### Governance Boundaries

- [x] CHK094 Does the requirements set state the selected-target authority order, the authority for current implementation/evidence truth, and the escalation route for a conflict that slice 030 cannot resolve? [Governance, Completeness, Spec §Authority source, Control-Plane Boundary; Constitution §Authority and Repository Boundaries]
- [x] CHK095 Are program authorization, durable assignment, dependency acceptance, zero-finding analysis, isolated-worktree proof, activation evidence, `READY`, and owner-declared `ACTIVE` specified as separate conjunctive gates, none of which can imply another? [Governance, Clarity, Spec metadata; Tasks §Activation Gate; Constitution §Program and Slice Lifecycle Gates]
- [x] CHK096 Are accepted I-010B/I-010E `@2` consumer truth and the stale `@1` program registry described consistently, with exact amendment provenance, immutable prior history, `v2-program-owner` repair ownership, and no claim that slice 030 completed the repair? [Consistency, Ownership, Spec §Resolved post-acceptance contract amendments and program handoff; Plan §Planning Decisions, Accepted contract amendment resolution; Tasks §Resolved upstream findings, Open program-owner handoff]
- [x] CHK097 Is the `NON_BLOCKING_HANDOFF` classification supported by explicit requirements explaining why the stale program registry is outside slice 030's dependency/task graph while still requiring correction before any downstream claim relies on the canonical registry? [Clarity, Assumption, Plan §Planning Decisions; Spec §Resolved post-acceptance contract amendments and program handoff; Tasks §Activation Gate]
- [x] CHK098 Are ownership and handoff boundaries complete for 010-owned schemas, 020 observation, 030 core/CLI, 040 participant hosting, surface integrations, shared guidance, slice-110 atomic publication, integrator acceptance, exact-main verification, release, and promotion? [Completeness, Ownership, Spec §Interface Summary, FR-015, Explicit Exclusions; Plan §Integration Strategy, Documentation ownership, Owner Handoff]
- [x] CHK099 Are SpecKit-managed content and ordinary product/evidence/documentation content separated exhaustively, including a prohibition on ordinary build, test, evaluation, documentation, packaging, release, or runtime paths depending on the control plane? [Boundary, Spec §Control-Plane Boundary, FR-016, SC-008; Constitution §SpecKit Is Control-Plane Only]
- [x] CHK100 Do the requirements prohibit authority, assignment, dependency acceptance, lifecycle, handoff, or acceptance facts from entering runtime configuration, classifier input, I-010A/B/E, receipts, participant rosters, social ledgers, obligation queues, or memory services? [Boundary, Spec §Control-Plane Boundary, Explicit Exclusions; Constitution §Program and Slice Lifecycle Gates]
- [x] CHK101 Are activation and acceptance records immutable, candidate and handoff attempts append-only, rejections returned to `ACTIVE`, new-run versus resume rules unambiguous, and recipient acceptance kept separate from workflow completion and owner handoff? [Consistency, Governance, Spec metadata; Plan metadata; Tasks metadata, Post-Task Lifecycle Gates; Constitution §Program and Slice Lifecycle Gates]

### Documentation Freshness Dispositions

- [x] CHK102 Are the documentation inventories reconciled before analysis so the spec, plan, T025, T026, and checklist name the same 47 exact paths with `8 UPDATE / 17 NO_IMPACT / 22 HANDOFF`, without a superseded inventory coexisting in current requirements? [Consistency, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness; Tasks §T025–T026]
- [x] CHK103 Is the post-reconciliation inventory count objectively reproducible from unique exact paths, with no duplicates, grouped substitutes, wildcards, or future files silently omitted from its stated denominator? [Measurability, Plan §Documentation Impact and Freshness; Spec §Documentation Freshness]
- [x] CHK104 Are the fifteen finally inventoried surfaces—`AGENTS.md`, `CLAUDE.md`, `evidence/verdict-suite/README.md`, `evidence/v2/contract/README.md`, `evidence/v2/attention/README.md`, `examples/loader-snippet.md`, `examples/generic_host_demo.py`, `examples/read_the_room_demo.py`, `profiles/open-floor.md`, `integrations/claude-code/nunchi-gate.env.example`, `integrations/codex/nunchi-codex/.mcp.json`, `integrations/codex/nunchi-codex/.codex-plugin/plugin.json`, `integrations/codex/nunchi-codex/hooks/hooks.json`, `integrations/hermes/nunchi-gate/dashboard/manifest.json`, and `integrations/hermes/nunchi-gate/plugin.yaml`—each represented with one consistent disposition, owner, rationale or exact delta, validation obligation, and task trace across all three artifacts? [Completeness, Consistency, Gap, Plan §Documentation Impact and Freshness; Spec §Documentation Freshness; Tasks §T025]
- [x] CHK105 Does every `UPDATE` requirement name one exact path, the candidate-specific claim delta, accountable owner/task, applicable link/diagram/example/command validation, evidence-grade boundary, and objective PASS evidence? [Completeness, Measurability, Plan §Documentation Impact and Freshness; Constitution §Documentation Freshness Gate]
- [x] CHK106 Does every `NO_IMPACT` requirement name one exact path, provide a candidate-specific rationale, require reviewer identity and ordinary handoff evidence, and remain rejectable if the exact candidate diff or resulting claim invalidates that rationale? [Completeness, Measurability, Plan §Documentation Impact and Freshness; Tasks §Documentation freshness; Constitution §Documentation Freshness Gate]
- [x] CHK107 Does every `HANDOFF` requirement name one exact shared or downstream-owned path, state the exact claim delta, identify the accepting owner, prohibit use for slice-owned documentation, and avoid representing deferred work as complete or no-impact? [Completeness, Ownership, Plan §Documentation Impact and Freshness; Spec §Documentation Freshness; Constitution §Documentation Freshness Gate]
- [x] CHK108 Are the `README.md`, `AGENTS.md`, and `CLAUDE.md` handoff requirements mutually consistent about V1-current truth, staged I-030A, trusted bypass, separate ERROR, CLI behavior, active dual-DEFER policy, atomic publication, verification-pending wording, and the later exact-main gate? [Consistency, Documentation, Plan §Documentation Impact and Freshness; Spec §Control-Plane Boundary, Documentation Freshness]
- [x] CHK109 Are evidence-index and historical-document requirements clear about which records are updated, which remain unchanged, how V1 scar evidence relates to V2 component evidence, and which social-quality, participant, parity, cutover, release, or promotion claims remain unavailable? [Clarity, Evidence, Plan §Documentation Impact and Freshness; Spec §SC-004–SC-008, Explicit Exclusions]
- [x] CHK110 Do T025, T026, candidate convergence, the documentation-freshness review, and owner handoff require the reconciled matrix, exact candidate/packet identity, per-path result, reviewer, validation or rationale, routed delta, accepting owner, and ordinary evidence before `HANDOFF_READY`, without relying on the earlier 86/86 checklist result? [Traceability, Governance, Conflict, Tasks §T025–T026, Post-Task Lifecycle Gates; Plan §Documentation Impact and Freshness, Owner Handoff]

## Formal Reviewer Delta Notes

- Mark CHK087–CHK110 complete only from the reconciled requirement text. Code,
  test, or evaluation success cannot close a requirement-quality item.
- Record findings inline with the affected CHK ID. Any unresolved conflict,
  ownership leak, ambiguous gate, or documentation-disposition mismatch blocks
  zero-CRITICAL/HIGH analysis and slice activation.
- This checklist does not establish `READY`, create activation evidence,
  authorize implementation, or record an acceptance decision.

**2026-07-19 prior delta result (superseded inventory count)**: 110/110
requirement-quality items passed against the then-current 43-path
documentation/configuration inventory, exact six-file slice-110
publication delta, accepted I-010B/I-010E `@2` inputs, receipt offer/persistence
semantics, pre-run exact model selection, commit-range verification,
receipt-sink wake fallback, and non-blocking program-owner registry handoff were
reconciled across spec, plan, and tasks. Its documentation-completeness result
is superseded by the fresh 47-path review below.

## Formal Reviewer Gate — 2026-07-19

**Purpose**: Provide a fresh formal blocking review of requirement quality,
governance boundaries, and documentation-freshness dispositions for the
current reconciled spec, plan, and dormant task graph.

**Depth**: Formal blocking review

**Reviewer**: codex-session-1 (`v2-core-owner`)

**Actor / timing**: Assigned owner conducting the fresh formal review after
artifact reconciliation and before zero scoped CRITICAL/HIGH analysis, slice
activation, or implementation

**Review status**: Complete. All 24 items were reviewed independently against
the reconciled requirement text; they do not inherit completion from
CHK001–CHK110 or from any implementation result.

### Requirement Quality

- [x] CHK111 Are the requirements complete and ordered for the entire I-030A trust boundary: operator configuration security, duplicate-free parsing, closed input shapes, secure sink construction, request validation, participant/scope binding, budget validation, bypass/provider use, and error-policy eligibility? [Completeness, Spec §FR-001, §FR-007, §FR-011, §FR-019; Plan §I-030A callable and CLI equivalence seam, §Bypass, operational error, and CLI parity]
- [x] CHK112 Are every callable/CLI result class, stable cause pair, stdout/stderr rule, exit code, receipt-eligibility rule, and persistence suffix specified consistently enough to decide combined-failure precedence without implementation knowledge? [Consistency, Clarity, Spec §FR-001, §FR-011–§FR-012, §FR-019; Plan §CLI Process Contract; Tasks §T002, §T018–§T022]
- [x] CHK113 Is “one logical model judgment” objectively bounded by the required `max_retries` domain, closed retryable-failure set, identical payload/request identity, and prohibition on defaults, malformed-output retries, or treating attempts as independent social votes? [Clarity, Measurability, Spec §FR-003; Plan §Retry and sparse-advice boundaries; Tasks §T004, §T006]
- [x] CHK114 Are event-count, canonical-projection-byte, declared-coverage, equality-boundary, continuation-redaction, and no-truncation requirements complete and mutually consistent with slice-020 observation ownership? [Completeness, Consistency, Spec §FR-001, §FR-018, §FR-020; Plan §Trusted attention-budget boundary]
- [x] CHK115 Are WAKE-only advice requirements clear about prompt limits, deterministic citation resolution, owner-adjudicated semantic fields, 100% evidence adherence, and the prohibition on locally narrowing otherwise I-010B-valid advice at runtime? [Clarity, Consistency, Spec §FR-005, §FR-014; Plan §Retry and sparse-advice boundaries, §Advice evidence rubric; Tasks §T004, §T023]
- [x] CHK116 Is the three-family evidence requirement protected against post-result selection by a committed pre-run exact-ID manifest, one-to-one family mapping, catalog/source provenance, owner review, result-to-manifest identity, new-commit rule for ID changes, and durable Zoe authority for family substitution? [Completeness, Assumption, Spec §FR-014, §Assumptions; Plan §Acceptance Scenes and Evidence; Tasks §T009, §T023]
- [x] CHK117 Can the exact 36-row transition denominator and every row oracle be reconstructed from the requirements, including inclusive equality, validation-before-policy, first-match widening precedence, distinct classifier/margin DEFER, and the status/pair/margin/valve/cause fields? [Measurability, Spec §FR-008–§FR-010, §SC-002; Plan §Finite transition and social-evidence gates; Tasks §T003, §T014–§T017]
- [x] CHK118 Are mechanical pass gates, descriptive social-quality rates, downstream live-canary ownership, performance measurements without local thresholds, active-margin non-retirement, rejected claims, and known limitations distinguished so none can be misread as proof of social correctness? [Clarity, Consistency, Spec §FR-014–§FR-015, §SC-004–§SC-008; Plan §Acceptance Scenes and Evidence, §Receipt and performance evidence boundary]

### Governance Boundaries

- [x] CHK119 Does the requirements set distinguish higher-authority selected-target truth from ordinary-path current implementation/evidence truth, preserve V1 as current through `CUTOVER_VERIFIED`, and define escalation when slice 030 cannot resolve an authority conflict? [Governance, Clarity, Spec §Authority source, §Control-Plane Boundary; Constitution §Authority and Repository Boundaries]
- [x] CHK120 Are program authorization, durable assignment, accepted dependency handoff, zero scoped CRITICAL/HIGH analysis, isolated-worktree proof, immutable activation evidence, `READY`, and owner-declared `ACTIVE` separate conjunctive requirements that cannot establish one another? [Governance, Completeness, Spec metadata; Tasks §Activation Gate; Constitution §Program and Slice Lifecycle Gates]
- [x] CHK121 Are terminal slice-010 acceptance, slice-030's separate consumer acceptances, ordered dependency commit/reference mappings, accepted I-010B/I-010E `@2` provenance, immutable earlier blocker history, and the stale program-registry handoff represented without contradiction or weakened readiness? [Consistency, Traceability, Spec §Resolved post-acceptance contract amendments and program handoff; Plan §Accepted contract amendment resolution; Tasks §Resolved upstream findings, §Open program-owner handoff]
- [x] CHK122 Are SpecKit-managed paths limited to planning/control-plane content, with product code, schemas, tests, corpora, evidence, runtime assets, and product documentation assigned exact ordinary homes and ordinary commands prohibited from depending on the control plane? [Boundary, Completeness, Spec §Control-Plane Boundary, §FR-016; Plan §Project Structure; Constitution §SpecKit Is Control-Plane Only]
- [x] CHK123 Do the written boundaries prohibit authorization, assignment, dependency acceptance, lifecycle, candidate, handoff, and acceptance facts from entering runtime configuration, classifier input, I-010A/B/E or I-030A, receipts, participant rosters, handled/open ledgers, obligation queues, or memory services? [Boundary, Spec §Control-Plane Boundary, §Explicit Exclusions; Constitution §Program and Slice Lifecycle Gates]
- [x] CHK124 Are ownership boundaries complete for 010 contracts, 020 observation, 030 core/CLI, 040 participant hosting, every downstream surface, security/provenance, shared documentation, the exact six-file slice-110 atomic publication delta, integrator acceptance, exact-main verification, release, and promotion? [Ownership, Completeness, Spec §Interface Summary, §FR-013, §FR-015, §Explicit Exclusions; Plan §Integration Strategy, §Documentation ownership, §Owner Handoff]
- [x] CHK125 Are immutable activation/acceptance records, append-only candidate/handoff streams, rejection back to `ACTIVE`, convergence-added-task re-entry, new-run versus unchanged-graph resume rules, and protection of historical attempts specified without lifecycle ambiguity? [Governance, Consistency, Spec metadata; Plan metadata; Tasks metadata; Constitution §Program and Slice Lifecycle Gates]
- [x] CHK126 Does delivery stop at `HANDOFF_READY` without fabricating recipient acceptance, while naming `v2-integrator` as the slice-level decision owner and preserving each downstream owner's separate exact-commit/packet acceptance obligation? [Governance, Ownership, Spec §FR-015; Plan §Owner Handoff; Tasks §Post-Task Lifecycle Gates]

### Documentation Freshness Dispositions

- [x] CHK127 Do the spec, plan matrix, T025, T026, and this current checklist agree on one reproducible inventory of 47 unique exact paths with exactly 8 `UPDATE`, 17 `NO_IMPACT`, and 22 `HANDOFF` dispositions? [Consistency, Traceability, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness; Tasks §Documentation freshness, §T025–§T026]
- [x] CHK128 Does every inventoried surface receive exactly one disposition, with no duplicate path, grouped substitute, generic directory, wildcard, or silent omission of a known documentation, evidence, example, profile, configuration, or installed-metadata claim surface? [Completeness, Measurability, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]
- [x] CHK129 Does every `UPDATE` requirement name one exact path, candidate-specific claim delta, accountable task/lane, applicable link/diagram/example/command/configuration validation, evidence-grade boundary, and objective PASS record? [Completeness, Measurability, Plan §Documentation Impact and Freshness; Tasks §T025; Constitution §Documentation Freshness Gate]
- [x] CHK130 Does every `NO_IMPACT` requirement name one exact path, concrete candidate-specific rationale, reviewer identity, and ordinary handoff evidence, while remaining rejectable when the exact candidate diff or resulting claim invalidates that rationale? [Completeness, Measurability, Plan §Documentation Impact and Freshness; Tasks §T025; Constitution §Documentation Freshness Gate]
- [x] CHK131 Does every `HANDOFF` requirement name one exact shared or downstream-owned path, state the exact required claim delta, identify the accepting owner, forbid use for slice-owned documentation, and avoid representing deferred work as complete or no-impact? [Completeness, Ownership, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness; Constitution §Documentation Freshness Gate]
- [x] CHK132 Are `README.md`, `AGENTS.md`, `CLAUDE.md`, stability/install/integration guidance, examples, profiles, and diagrams dispositioned consistently around V1-current truth, non-current I-030A staging, verification-pending cutover, exact-main validation, and eventual V2-current wording? [Consistency, Documentation, Spec §Control-Plane Boundary, §Documentation Freshness; Plan §Documentation Impact and Freshness]
- [x] CHK133 Are evidence indexes, frozen V1 archives, verdict-suite references, operator configuration examples, plugin/hook manifests, and transport-only documents given claim-appropriate validation requirements rather than one generic prose-only rule? [Coverage, Documentation, Plan §Documentation Impact and Freshness; Tasks §T025]
- [x] CHK134 Do T025, T026, convergence, exact-candidate documentation review, packet-commit rerun, and owner handoff require per-path results, reviewer, validation or rationale, routed delta, accepting owner, candidate/packet identity, and ordinary evidence before `HANDOFF_READY`? [Traceability, Governance, Tasks §T025–§T027, §Post-Task Lifecycle Gates; Plan §Candidate Verification Commands, §Owner Handoff]

## Formal Reviewer Gate Notes

- Mark CHK111–CHK134 complete only from the reconciled requirement text and
  cited authority. Code, test, evaluation, or runtime success cannot substitute
  for requirement quality.
- Record findings inline with the affected CHK ID. Any unresolved ambiguity,
  conflict, ownership leak, governance-boundary violation, or documentation-
  disposition mismatch blocks zero scoped CRITICAL/HIGH analysis and activation.
- This gate does not establish `READY`, create activation evidence, authorize
  implementation, complete candidate documentation review, or record an
  acceptance decision.

**2026-07-19 formal result**: 24/24 fresh items pass; the full checklist is now
134/134. The separately owned stale program interface registry remains an open
`v2-program-owner` handoff and is not counted as a scoped slice-030 finding.

## Formal Reviewer Receipt-Sink Delta Gate — 2026-07-19

**Purpose**: Review the requirement quality, governance boundaries, and
documentation-freshness consequences of the clarified callable receipt-sink
exception contract without reusing the completed CHK111–CHK134 result.

**Depth**: Formal blocking review

**Reviewer**: codex-session-1 (`v2-core-owner`), acting as the formal owner
reviewer under Zoe's explicit identity-separation waiver

**Actor / timing**: Assigned owner conducting a fresh review after the receipt-
sink clarification is reconciled across spec, plan, and tasks and before fresh
zero scoped CRITICAL/HIGH analysis, slice activation, or implementation

**Review status**: Complete. All 30 items were reviewed independently against
the post-clarification requirement text; no result is inherited from
CHK111–CHK134 or from implementation behavior.

### Requirement Completeness and Clarity

- [x] CHK135 Is the receipt-sink outcome domain closed and exhaustive: normal `None` return means `persisted`, a recognized engine-owned typed failure carries only `not-persisted` or `unknown`, every unrecognized exception maps to `unknown`, and no raised path may claim `persisted`? [Completeness, Spec §FR-001, User Story 3 Acceptance Scenario 8; Plan §I-030A callable and CLI equivalence seam]
- [x] CHK136 Is the “engine-owned typed sink-failure exception” specified precisely enough to identify its owning interface, construction authority, validated persistence member, and recognition boundary without relying on implementation knowledge? [Clarity, Ambiguity, Spec §FR-001; Plan §I-030A callable and CLI equivalence seam]
- [x] CHK137 Does “every other exception” define whether host-control, cancellation, and process-termination exception classes belong to the mapping domain or remain intentionally outside it? [Gap, Ambiguity, Spec §FR-001, User Story 3 Acceptance Scenario 8]
- [x] CHK138 Are exact-type, subclass, wrapped-error, and cause-chained recognition semantics defined so two conforming hosts cannot disagree about which failure is “recognized,” while attribute-lookalike exceptions are explicitly untrusted? [Clarity, Coverage, Spec §FR-001; Plan §I-030A callable and CLI equivalence seam]
- [x] CHK139 Are CLI adapter requirements complete for mapping collision, pre-create failure, post-create write/flush/fsync/close failure, cleanup success, cleanup uncertainty, and final-directory-fsync uncertainty into the only two permitted typed failure outcomes? [Completeness, Spec §FR-001; Plan §I-030A callable and CLI equivalence seam]
- [x] CHK140 Are the callable-core and CLI-adapter responsibilities separated unambiguously: the adapter classifies its owned persistence facts, the core recognizes only its owned typed failure, and neither trusts arbitrary exception attributes or retries the sink? [Clarity, Ownership, Spec §FR-001, §FR-012; Plan §I-030A callable and CLI equivalence seam]
- [x] CHK141 Are the required response status, stable code/cause-detail pair, `receipt_persistence` suffix, offered-record facts, and one-call/no-second-offer rule defined for every sink outcome? [Completeness, Spec §FR-001, §FR-011–§FR-012, §FR-019; Plan §CLI Process Contract]
- [x] CHK142 Is the safety relationship between sink persistence and `NO_WAKE` authority explicit for recognized `not-persisted`, recognized `unknown`, unrecognized, and lookalike exception paths, with shared `WAKE` required in every failure case? [Clarity, Safety, Spec §FR-001, §FR-011–§FR-012, User Story 3 Acceptance Scenarios 7–8]
- [x] CHK143 Are primary, alternate, exception, recovery, and hostile-input requirements present for normal return, both recognized outcomes, malformed recognized outcome, forbidden `persisted`, unrecognized exception, attribute lookalike, and cleanup uncertainty? [Coverage, Gap, Spec §User Story 3, Edge Cases; Plan §I-030A callable and CLI equivalence seam]
- [x] CHK144 Can every new exception-contract clause be traced to an accountable task, exact ordinary-path target, deterministic case/evidence target, and handoff obligation without treating a passing implementation test as proof of requirement quality? [Traceability, Spec §FR-001, §FR-012; Plan §Ordinary Repository Targets; Tasks §T004, §T007, §T018–§T022, §T026]

### Requirement Consistency and Acceptance Criteria

- [x] CHK145 Do User Story 3 Acceptance Scenario 8, FR-001, FR-012, the callable/CLI plan, and T004/T007/T018/T019/T021 use one non-conflicting exception taxonomy and persistence vocabulary? [Consistency, Spec §User Story 3 Acceptance Scenario 8, §FR-001, §FR-012; Plan §I-030A callable and CLI equivalence seam; Tasks §T004, §T007, §T018–§T021]
- [x] CHK146 Is callable/CLI field equivalence measurable when a host-injected sink raises each recognized or unrecognized failure and the CLI adapter reaches the corresponding persistence outcome, with only framing, diagnostics, and exit status allowed to differ? [Measurability, Spec §SC-001, §FR-019; Plan §CLI Process Contract]
- [x] CHK147 Are “offered,” “persisted,” `not-persisted`, and `unknown` consistent with accepted I-010E ownership, including the prohibition on a response or offered receipt attesting its own persistence? [Consistency, Dependency, Spec §FR-012; Plan §Accepted contract amendment resolution]
- [x] CHK148 Is sink-failure precedence specified relative to configuration, request-schema, binding, budget, bypass, provider/runtime, and malformed-model failures so every combined-failure case has one objectively determined result? [Clarity, Coverage, Spec §FR-001, §FR-011–§FR-012, §FR-019; Plan §CLI Process Contract]
- [x] CHK149 Is there a finite, reproducible acceptance matrix for normal return, each recognized typed outcome, invalid typed member, unrecognized exception, attribute lookalike, and adapter cleanup outcome, including expected wake policy and persistence reporting? [Measurability, Gap, Spec §FR-001, §SC-001, §SC-003; Tasks §T004, §T021]
- [x] CHK150 Are the evidence requirements specific about the exact exception cases, expected facts, denominator/count, zero-skip rule, and candidate binding needed to support the sink-contract completion claim? [Acceptance Criteria, Gap, Spec §SC-003, §SC-008; Plan §Candidate Verification Commands; Tasks §T021, §T027]
- [x] CHK151 Are secrecy requirements consistent about preventing exception messages, sink paths, credentials, and lookalike attributes from entering classifier projection, stdout/stderr, decisions, receipts, logs, or handoff claims beyond the closed persistence fact? [Security, Consistency, Spec §FR-001, §FR-018–§FR-019; Plan §I-030A callable and CLI equivalence seam]

### Governance Boundaries

- [x] CHK152 Is the typed sink failure explicitly scoped to slice-030-owned I-030A runtime seams without changing accepted 010-owned schemas, weakening I-010E receipt ownership, or creating a free-text contract extension? [Boundary, Ownership, Spec §Interface Summary, §FR-012, §FR-016; Plan §Slice Interfaces]
- [x] CHK153 Does the requirements set make an explicit, traceable determination about whether the newly specified host-visible exception changes I-030A `@1` interface exposure or versioning obligations for downstream consumers? [Gap, Dependency, Spec §FR-015; Plan §Slice Interfaces, §Owner Handoff]
- [x] CHK154 Are ownership and handoff requirements complete for the core-defined failure type, CLI adapter classification, downstream host acceptance, security review, integrator acceptance, and slice-110 publication without silent cross-slice ownership transfer? [Completeness, Ownership, Spec §FR-013, §FR-015; Plan §Documentation ownership, §Owner Handoff]
- [x] CHK155 Are current V1 behavior, non-current `evaluate_v2`/`attention-v2` staging, atomic slice-110 publication, verification-pending cutover, and `CUTOVER_VERIFIED` wording still distinguished after the exception-contract clarification? [Consistency, Governance, Spec §Control-Plane Boundary, §FR-013, Explicit Exclusions; Plan §Green pre-cutover staging, §Integration Strategy]
- [x] CHK156 Do activation prerequisites and planning-reconciliation declarations identify this latest formal reviewer gate, rather than treating completed CHK111–CHK134 as review of later requirement changes? [Conflict, Traceability, Tasks metadata §Activation prerequisites, §Planning reconciliation result]
- [x] CHK157 Do the clarified requirements keep authority, assignment, dependency acceptance, lifecycle, candidate, handoff, and acceptance facts out of the exception, runtime configuration, decisions, receipts, and classifier input while keeping this checklist in control-plane-only scope? [Boundary, Spec §Control-Plane Boundary, §FR-016, Explicit Exclusions; Constitution §SpecKit Is Control-Plane Only, §Program and Slice Lifecycle Gates]

### Documentation Freshness Dispositions

- [x] CHK158 Has the 47-path documentation matrix been re-evaluated against the clarified host-visible exception contract, with an explicit requirement that the `8 UPDATE / 17 NO_IMPACT / 22 HANDOFF` denominator remains valid only if no newly affected surface is omitted? [Completeness, Measurability, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]
- [x] CHK159 Do the `UPDATE` requirements for `docs/attention/v2.md` and `evidence/v2/attention/README.md` state the exact typed/unrecognized exception taxonomy, shared-`WAKE` rule, evidence cases, candidate binding, and applicable validation delta? [Completeness, Gap, Plan §Documentation Impact and Freshness; Tasks §T025–§T026]
- [x] CHK160 Are the other evidence and evaluation `UPDATE` rows required either to incorporate the new sink-failure evidence boundary or to retain a concrete candidate-specific rationale for why their existing claim delta is sufficient? [Clarity, Documentation, Plan §Documentation Impact and Freshness; Tasks §T025]
- [x] CHK161 Are `NO_IMPACT` requirements for `docs/contracts/nunchi-v2.md` and `evidence/v2/contract/README.md` re-justified against the host-visible runtime exception seam, accepted 010 contract ownership, and exact candidate diff rather than inherited from the pre-clarification review? [Consistency, Assumption, Plan §Documentation Impact and Freshness; Constitution §Documentation Freshness Gate]
- [x] CHK162 Does every affected `HANDOFF` row name the exact exception-related claim delta and accepting owner for shared or downstream host guidance, while unchanged rows retain an explicit candidate-specific rationale and are not silently treated as complete? [Completeness, Ownership, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness]
- [x] CHK163 Are per-path validation requirements defined for callable examples, CLI exits, configuration syntax, installed metadata, error/persistence claims, links, and evidence-grade/current-state wording instead of one generic documentation-success assertion? [Coverage, Acceptance Criteria, Plan §Documentation Impact and Freshness; Tasks §T025]
- [x] CHK164 Is documentation-freshness PASS tied to the exact post-clarification lifecycle candidate and ordinary handoff evidence, with stale dispositions, inherited reviewer results, missing deltas, or premature V2-current claims explicitly blocking `HANDOFF_READY`? [Governance, Traceability, Spec §FR-015, Documentation Freshness; Tasks §T025–§T027, Post-Task Lifecycle Gates; Constitution §Documentation Freshness Gate]

## Formal Reviewer Receipt-Sink Delta Notes

- Mark CHK135–CHK164 complete only from the reconciled requirement text and
  cited authority. Implementation, test, evaluation, or runtime success cannot
  substitute for requirement quality.
- Record findings inline with the affected CHK ID. Any unresolved ambiguity,
  conflict, ownership leak, governance-boundary violation, traceability gap, or
  documentation-disposition mismatch blocks analysis and activation.
- This generated gate does not establish `READY`, create activation evidence,
  authorize implementation, prove documentation freshness, or record an
  acceptance decision.

**2026-07-19 receipt-sink delta result**: 30/30 fresh items pass; the complete
requirements checklist is now 164/164. The I-030A runtime exception remains
inside slice-030 ownership and changes no accepted 010 contract. The separately
owned program-interface registry remains a non-blocking `v2-program-owner`
handoff, not a scoped slice-030 finding.

**2026-07-19 final inventory revalidation**: codex-session-1 re-ran CHK076,
CHK102–CHK110, CHK127–CHK134, and CHK158–CHK164 after the final ordinary-path
sweep added `examples/generic_host_demo.py`, `examples/read_the_room_demo.py`,
and `integrations/codex/nunchi-codex/.mcp.json`. All remain PASS against the
47-path `8 UPDATE / 17 NO_IMPACT / 22 HANDOFF` denominator; no earlier 44-path
count remains current.

## Formal Reviewer Final Scoped-Finding Gate — 2026-07-19

**Purpose**: Independently review the requirement delta that closes the final
scoped analysis findings: participant-host ownership, continuation retention,
the concrete stdlib retry taxonomy, and conservative sink persistence.

**Depth**: Formal blocking review

**Reviewer**: codex-session-1 (`v2-core-owner`), acting as the formal owner
reviewer under Zoe's explicit identity-separation waiver

**Actor / timing**: Assigned owner after reconciling the advisory sink rule and
the aborted run's final scoped findings across spec, plan, and tasks, before a
new bound planning run, activation, or implementation

**Review status**: Complete. All 12 items were reviewed against the selected
design, accepted I-010A/B/E versions, current stdlib transport seam, and slice
ownership. No result is inherited from the earlier 164 items.

### Ownership, Safety, and Measurability

- [x] CHK165 Does slice 030 prove only the exact I-010B bypass branch/cause and zero classifier calls, without claiming ParticipantWakeV2 emission, host invocation, or downstream wake-source ownership? [Ownership, Boundary, Spec §User Story 3, §FR-017; Plan §Integration Strategy, §S06]
- [x] CHK166 Is the downstream obligation explicit and independently testable: `v2-wake-owner` must accept the exact 030 handoff, map bypass to ParticipantWakeV2 source `PREATTENTION_BYPASS`, and pass a slice-040 acceptance test? [Dependency, Acceptance Criteria, Spec §FR-015, §FR-017; Plan §Owner Handoff; Tasks §T022, §T026]
- [x] CHK167 Do callable requirements prove the accepted request and original continuation are caller-owned immutable input through deep/canonical pre/post equality and continued availability, while the provider receives no secret? [Security, Measurability, Spec §FR-018–§FR-020; Plan §Trusted attention-budget boundary; Tasks §T004, §T007]
- [x] CHK168 Do CLI requirements retain a caller-side byte/deep copy and prove post-evaluation equality and capability availability without claiming that slice 030 invokes the participant host? [Security, Ownership, Measurability, Spec §FR-020; Plan §CLI Process Contract; Tasks §T021]
- [x] CHK169 Is the retryable transport set closed over the concrete V2 stdlib seam: `HTTPError` first with only `429` and `500..599`, outer `URLError` without reason inspection, direct timeout, and request-execution `OSError` including `ConnectionError`? [Clarity, Completeness, Spec §FR-003; Plan §Retry and sparse-advice boundaries; Tasks §T006]
- [x] CHK170 Are non-retryable boundaries and deterministic oracles complete for HTTP `499`/`600`, post-response JSON/model failures, exact attempts/sleeps at all allowed retry counts, payload/request identity, stop-on-success, and exhaustion policy? [Measurability, Coverage, Spec §FR-003; Plan §Retry and sparse-advice boundaries; Tasks §T004, §T021]
- [x] CHK171 Is `not-persisted` restricted to a closed-contract pre-write rejection whose semantics guarantee no durable side effect, with generic, unrecognized typed, ordinary timeout/cancellation, and every post-dispatch failure mapped to `unknown`? [Safety, Clarity, Spec §FR-001; Plan §Receipt-sink exception recognition matrix; Tasks §T004, §T007]
- [x] CHK172 Does every `unknown` sink result prohibit non-idempotent retry and retain the one-offer/no-second-offer/shared-`WAKE` rules? [Safety, Consistency, Spec §FR-001, §FR-012; Plan §I-030A callable and CLI equivalence seam; Tasks §T019, §T021]
- [x] CHK173 Do adapter rows 15–18 report `unknown` even after successful best-effort cleanup, while row 14 alone may report `not-persisted` only when failed exclusive create guarantees no file was created? [Consistency, Measurability, Spec §FR-001; Plan §Receipt-sink exception recognition matrix; Tasks §T019, §T021]
- [x] CHK174 Are host-control `BaseException` propagation and ordinary timeout/cancellation-as-`Exception` classification non-conflicting and explicitly separate? [Clarity, Coverage, Spec §FR-001; Plan §I-030A callable and CLI equivalence seam]
- [x] CHK175 Can each final delta be traced to exact implementation, deterministic corpus/evidence, and handoff tasks without changing accepted 010 schemas or taking slice-040 ownership? [Traceability, Governance, Spec §FR-015–§FR-020; Plan §Ordinary Repository Targets; Tasks §T004, §T006–§T007, §T019, §T021–§T022, §T026]
- [x] CHK176 Does the 47-path `8 UPDATE / 17 NO_IMPACT / 22 HANDOFF` documentation denominator remain complete after these clarifications, with component exception evidence in the existing UPDATE paths and participant-host mapping in the already named downstream/shared HANDOFF paths? [Documentation, Consistency, Spec §Documentation Freshness; Plan §Documentation Impact and Freshness; Tasks §T025–§T026]

## Formal Reviewer Final Scoped-Finding Notes

- Mark CHK165–CHK176 complete only from the reconciled requirement text and
  cited authority; implementation success is not a substitute.
- Any reintroduction of host-owned ParticipantWakeV2 behavior, request
  mutation, open-ended retry classification, or post-dispatch
  `not-persisted` blocks analysis and activation.
- The program-interface registry remains the separately recorded non-blocking
  `v2-program-owner` handoff and is not reclassified by this gate.

**2026-07-19 final scoped-finding result**: 12/12 fresh items pass; the complete
requirements checklist is now 176/176. The task graph remains T001–T027 and
dormant until a separate READY activation record exists.
