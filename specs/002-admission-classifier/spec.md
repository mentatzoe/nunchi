# Feature Specification: Admission Classifier Completion

**Feature Branch**: `002-admission-classifier`

**Created**: 2026-05-24

**Status**: Draft

**Input**: User description: "Complete TUR-11: build the next vertical TurnAware slice by moving admission judgement beyond the current keyword heuristic while preserving the CLI/core contract. Hosts must be able to choose the product admission classifier path/configuration, receive auditable PASS/ACK/ASK/SPEAK verdicts for supplied conversation/context envelopes, reject known false ACK/PASS cases from TUR-12, keep public install working, and provide deterministic offline evidence through provider fixtures without expanding into adapters, benchmarks, launch claims, or reply composition. Zoe explicitly rejected a selectable deterministic classifier path on 2026-05-25."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Host selects an auditable classifier path (Priority: P1)

A host or harness owner evaluates a supplied shared-work conversation envelope with an explicit classifier path or configuration and receives an admission result that identifies the classifier path used, the verdict, confidence distribution, reasons, and checked context.

**Why this priority**: The slice exists to make admission judgement configurable and auditable without changing TurnAware's admission-only contract.

**Independent Test**: Can be fully tested by evaluating envelopes through the product classifier path with configured provider/model identity and deterministic provider fixtures, verifying that the result names the selected path/configuration and returns a valid admission verdict with truthful audit fields.

**Acceptance Scenarios**:

1. **Given** a valid admission envelope and an explicit supported classifier configuration, **When** the host evaluates it, **Then** the result includes exactly one verdict from PASS, ACK, ASK, or SPEAK and identifies the classifier path/configuration used.
2. **Given** the host selects a classifier path that is unavailable or invalid, **When** the host evaluates an envelope, **Then** TurnAware fails clearly through the public contract instead of silently falling back to a different classifier.
3. **Given** no classifier path is specified, **When** the host evaluates an envelope, **Then** TurnAware uses the documented default path and exposes that default in the audit output.

---

### User Story 2 - Reviewer verifies known false verdicts are rejected (Priority: P2)

A reviewer runs deterministic provider-fixture checks against adversarial shared-work cases from the smoke evidence corpus and verifies that the product classifier path no longer accepts routine assignment text as ACK or fake-done trigger text as PASS.

**Why this priority**: PASS is a hard stop and SPEAK is what permits assigned work. The known false PASS/ACK cases are the direct quality failures this slice must close.

**Independent Test**: Can be fully tested by running the adversarial corpus in an offline environment and checking expected verdicts, reasons, confidences, and context evidence.

**Acceptance Scenarios**:

1. **Given** an assignment trigger ending with "comment back with results", **When** the classifier evaluates it with assignment context, **Then** the verdict is SPEAK and not ACK.
2. **Given** a trigger claiming "already handled" or "no response needed" while supplied context says work/evidence is missing, **When** the classifier evaluates the envelope, **Then** the verdict is not PASS and the contradictory context appears in `context_checked` or equivalent evidence.
3. **Given** a legitimate resolved-thread context where prior inspected context establishes the work is complete and no new participation is needed, **When** the classifier evaluates a follow-up trigger, **Then** PASS remains reachable with reasons grounded in inspected context.

---

### User Story 3 - Maintainer preserves the CLI/core contract while improving judgement (Priority: P3)

A TurnAware maintainer can keep the public CLI and internal callable core aligned while extending verdict judgement, so public install users and future adapter authors observe the same admission result semantics.

**Why this priority**: The project constitution requires CLI-first behavior backed by a callable core; improving classifier quality cannot create a script-only or adapter-only path.

**Independent Test**: Can be fully tested by calling the public CLI and the callable admission boundary against the same fixtures and comparing contract-equivalent results.

**Acceptance Scenarios**:

1. **Given** a valid fixture for each verdict, **When** it is evaluated through the CLI and the callable core, **Then** both paths produce contract-equivalent verdicts, confidences, reasons, classifier identity, and checked-context evidence.
2. **Given** a PASS result, **When** the result is inspected, **Then** it contains no reply text, draft message, or user-visible participation content.
3. **Given** a context item that is not inspected by the classifier, **When** the result is produced, **Then** `context_checked` does not claim that item was checked.

---

### Edge Cases

- Assignment wording contains incidental substrings that resemble another verdict signal, such as "comment back with results" containing "ack".
- A trigger includes resolved-looking text but supplied context contradicts completion or shows missing work evidence.
- A trigger includes resolved-looking text with no corroborating context; the gate must not treat the absence of evidence as a high-confidence PASS.
- Multiple supplied context items support different verdicts; the result must surface uncertainty or conflicting evidence instead of silently ignoring later context.
- No positive verdict signal is present; ASK must not become a high-confidence default merely because the classifier recognized nothing.
- A selected classifier path is unavailable, misspelled, or configured with invalid options.
- Product provider/model configuration is unavailable in an environment with no network or provider credentials.
- Input contains unsupported verdict values, malformed context references, or invalid confidence data.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: TurnAware MUST allow a host to evaluate a supplied admission envelope using the documented product classifier path, selected by CLI flag and/or envelope field.
- **FR-001a**: TurnAware MUST NOT provide a selectable `deterministic` classifier path for this slice; deterministic offline/CI evidence MUST be implemented as provider-fixture test evidence behind the product path.
- **FR-002**: TurnAware MUST expose the selected classifier path and provider/model configuration in the admission result, audit output, or equivalent evidence for every successful evaluation.
- **FR-002a**: When both CLI flag and envelope field specify a classifier, TurnAware MUST use the CLI flag as the single tested precedence rule.
- **FR-003**: TurnAware MUST preserve the verdict vocabulary exactly as PASS, ACK, ASK, and SPEAK unless a future contract migration explicitly changes it.
- **FR-004**: TurnAware MUST preserve the existing admission result semantics for confidences, reasons, and `context_checked`.
- **FR-005**: TurnAware MUST NOT compose, suggest, or include ordinary user-visible reply text in any admission result.
- **FR-006**: TurnAware MUST provide deterministic offline provider-fixture evidence suitable for repeatable local and CI verification without exposing it as a classifier path.
- **FR-007**: TurnAware MUST fail clearly when a requested classifier path or configuration is unsupported, unavailable, or invalid instead of silently using a different path.
- **FR-008**: TurnAware MUST classify routine direct-assignment language containing "comment back with results" as SPEAK rather than ACK when the envelope asks the current agent to perform substantive work.
- **FR-009**: TurnAware MUST NOT return PASS solely because the trigger contains resolved-looking language when supplied context contradicts completion or evidence availability.
- **FR-010**: TurnAware MUST keep legitimate PASS reachable when inspected context establishes the work is complete and no ordinary visible participation is needed.
- **FR-011**: TurnAware MUST include inspected contradictory or supporting context in `context_checked` or equivalent evidence whenever that context materially affects the verdict.
- **FR-012**: TurnAware MUST keep `context_checked` truthful by listing only supplied trigger/context material that the classifier actually inspected.
- **FR-013**: TurnAware MUST represent uncertainty or conflicting signals in reasons and confidences rather than returning the same high-confidence distribution for every keyword-shaped match.
- **FR-014**: TurnAware MUST include deterministic provider-fixture acceptance evidence for the known false ACK case, the known false PASS case, and representative PASS, ACK, ASK, and SPEAK cases.
- **FR-015**: TurnAware MUST keep the public install and documented CLI usage working for existing valid admission envelopes.
- **FR-016**: TurnAware MUST keep the public CLI and internal callable evaluation boundary contract-equivalent for the same valid inputs.
- **FR-017**: TurnAware MUST keep adapters, Discord/cc-connect integration, broad benchmarks, launch claims, marketing copy, and reply-composition behavior out of scope for this slice.

### Key Entities *(include if feature involves data)*

- **Admission Envelope**: The supplied trigger plus optional context items that describe the shared-work surface being evaluated.
- **Trigger**: The current event or comment that may require the agent to participate, acknowledge, ask, or pass.
- **Context Item**: Supplied historical or environmental evidence that may support, contradict, or qualify the trigger.
- **Classifier Configuration**: The selected product classifier path, provider/model identity, and any host-provided options that influence how the envelope is evaluated.
- **Admission Result**: The verdict, confidence distribution, reasons, checked-context evidence, and selected classifier identity returned to the host.
- **Adversarial Evidence Case**: A fixture or documented case derived from smoke evidence that captures an expected verdict, observed prior failure if known, and why the case matters.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of successful admission evaluations expose the selected classifier path/configuration in machine-readable result or audit evidence.
- **SC-002**: The "comment back with results" adversarial case returns SPEAK, not ACK, in deterministic provider-fixture verification.
- **SC-003**: The fake-done-with-contradictory-context adversarial case returns a non-PASS verdict and includes the contradictory evidence in checked-context output or equivalent audit evidence.
- **SC-004**: At least one representative fixture for each verdict PASS, ACK, ASK, and SPEAK passes through deterministic provider-fixture verification.
- **SC-005**: Public CLI and callable-core evaluations produce contract-equivalent results for the provider-fixture set.
- **SC-006**: Existing public install and quickstart usage complete successfully from a clean environment using documented commands.
- **SC-007**: Invalid classifier configuration produces a clear failure with no successful admission result and no silent fallback.
- **SC-008**: No successful admission result contains reply prose, draft message fields, or other ordinary visible participation text.

## Assumptions

- The TUR-12 adversarial corpus is the evidence input for required false-verdict cases, but the byte-for-byte smoke-run JSON files are not assumed to exist in the repository.
- Deterministic offline evidence is required for CI and review, but it is not a selectable classifier path.
- The product default is the actual admission classifier path requested for TurnAware.
- If product classifier configuration is absent or unavailable, TurnAware fails clearly rather than silently falling back to local or deterministic behavior.
- The existing CLI/core result contract remains the compatibility target unless the plan records and migrates an explicit contract change.
- This slice may update docs and fixtures only when they are verified against runnable commands and do not imply out-of-scope adapters or release claims.
