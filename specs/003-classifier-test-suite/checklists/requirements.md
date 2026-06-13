# Specification Quality Checklist: Classifier Verdict Test Suite

**Purpose**: Validate specification completeness and quality before proceeding to planning

**Created**: 2026-05-25

**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`.

### Validation walkthrough (iteration 1, all items pass)

- **Implementation-details cleanliness**: the spec references the existing classifier path (`turnaware/core.py::_classify_text`) and the public release tag (`turnaware-0.1.0` at commit `a132ccc`) only as context for *what is being tested*, never as prescriptions for *how the suite is built*. It does not pin a programming language, test framework, file format beyond an abstract "envelope file", or runner architecture. The suite is described by its observable contract (single command, deterministic, machine-readable + human-readable output) and its required fixture classes — not by any tech stack.
- **Stakeholder readability**: each user story is opened in plain-language terms (the implementer, the reviewer, the future contributor) before any technical detail; the *why* lines tie back to merge-gating, reviewer independence, and corpus rot. Technical terms (substring trap, fallthrough, audit field) are introduced through worked examples in Edge Cases rather than relied on as jargon.
- **Testability of FRs**: every FR-NNN names either a concrete fixture class or a concrete observable property of the runner. FR-001 / FR-002 carry source pointers (TUR-9 samples + commit hash) so reviewers can verify the fixtures were reconstructed faithfully. FR-009 / FR-015 / FR-017 are determinism + offline constraints expressed as MUST/MUST-NOT, not soft preferences.
- **Success-criteria measurability**: SC-001 is a discrete pass/fail count against a named commit. SC-002 is reproducibility across two reviewers. SC-004 is a five-minute extension budget. SC-005 is a five-second runtime budget with no network. SC-006 / SC-007 / SC-008 are output-format assertions checkable by reading a single report.
- **Acceptance scenarios**: each user story carries Given/When/Then scenarios that map directly to FRs (US1.1 → SC-001 / FR-001 / FR-002 / FR-003; US1.3 → FR-003 baseline regression protection; US2.1 → SC-002; US3.1 → FR-014 / SC-004).
- **Edge-case coverage**: the Edge Cases section enumerates substring traps, trigger-only PASS, trigger-vs-context contradiction (and its symmetric form), context-checked truncation, ASK-fallthrough vs positive ASK, constant-confidence collapse, legitimate per-verdict baselines, and the no-keyword negative control — each tied to either a runtime-observed failure or an explicit code-reading prediction in the TUR-12 corpus.
- **Scope bounding**: the Assumptions section explicitly excludes (a) classifier implementation (owned by TUR-11), (b) provider/model choice (the suite is mechanism-level), and (c) re-investigation of the TUR-12 cases (the corpus comment is the authoritative source). The "this spec is for the test suite only" clause makes the boundary load-bearing.
- **Dependencies/assumptions**: documented in the Assumptions section, including the verdict surface contract, the envelope shape inherited from the smoke runs, the authoritative source for fixture content, the commit pin (`a132ccc`), and the spec-numbering rationale relative to `001-core-cli-mvp` and `002-admission-classifier`.

No re-iteration was required; all 16 checklist items pass on the first validation pass.

### Caveats called out explicitly so they are not silently swept under "passes"

- The spec assumes the TUR-12 corpus comment is correct; the suite implementer must reconstruct fixture envelopes from the trigger/context summaries there. If the corpus comment is later revised, the FR-001 / FR-002 source pointers must be re-verified before `/speckit-implement`.
- The five-second / five-minute / "standard developer laptop" thresholds in SC-004 and SC-005 are derived from common test-suite expectations, not from a measured baseline on this codebase. If a future planning step uncovers a justification to relax either threshold, the spec should be revisited rather than the SC silently softened.
- The "regex-based classifier" example in US2.2 is illustrative of implementation-agnosticism; it is not a hint that a regex classifier is the intended fix.

### Validation walkthrough (iteration 2, after human-conversation expansion on 2026-05-25)

Re-walked the 16-item checklist against the expanded spec (US3 added at P1, FR-018 through FR-021 added, SC-009 through SC-011 added, new Discord-pilot-shape edge-case subsection, new Key Entities for envelope shape and Discord suppressor, expanded Sources of evidence and Assumptions). All 16 items remain passing:

- **Implementation-details cleanliness**: the new content references `~/github/pilot-bot/before-you-respond.md` and the pilot-bot session log path as *evidence sources*, not as runtime dependencies. The suite is still language- and framework-agnostic; the `source_shape` field is a metadata convention, not a stack choice. FR-020's "typed verdict, not a transport-layer string" is expressed as a contract assertion, not as a Python enum, Rust type, or anything stack-specific.
- **Stakeholder readability**: US3's opening paragraph defines each Discord-shape failure mode in plain language ("vocative greetings", "bracketed persona framings", "casual pivots with emotional padding") with concrete quoted examples from the pilot. No jargon precedes its explanation.
- **Testability of FRs**: FR-018 enumerates the required fixture set discretely; FR-019 names a single metadata field and a single CLI-style filter; FR-020 names the exact malformed-sentinel variants observed in the pilot; FR-021 enumerates the four named suppressors. Every new FR is countable.
- **Success-criteria measurability**: SC-009 / SC-010 / SC-011 each name a concrete artifact (a count, a filter behaviour, a specific malformed-string set) that a reviewer can verify by running the suite against a known-broken and a known-good classifier.
- **Acceptance scenarios**: US3 carries three Given/When/Then scenarios mapping directly to the new FRs and SCs (US3.1 → SC-010 / FR-018; US3.2 → FR-019; US3.3 → FR-018 + SC-006).
- **Edge-case coverage**: the new "Discord-pilot-shape edge cases" subsection enumerates 11 named cases, each tied to either a runtime quote from the pilot session or to a published rule in `before-you-respond.md`.
- **Scope bounding**: the new Sources of evidence subsection makes explicit that the suite is one corpus drawn from two evidence pools. The new Assumption (pilot-bot session is the authoritative Discord-shape source; the suite tracks `before-you-respond.md` policy) makes the pool ownership explicit.
- **Dependencies/assumptions**: the new Discord-shape Assumption acknowledges that if TurnAware's default-PASS policy changes, the Discord-shape fixtures and their expected verdicts must move alongside; this is a known maintenance dependency, not a hidden one.

No re-iteration required; all 16 items remain passing after the expansion. Caveats specific to the expansion are noted in the "Caveats" subsection above.
