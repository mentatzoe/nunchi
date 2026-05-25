# Research: Admission Classifier Completion

## Decision: Make the product classifier path provider-backed; remove deterministic as a classifier path

**Rationale**: TUR-11 is meant to complete the actual admission classifier, not promote the offline deterministic harness into the product path. Zoe explicitly rejected a selectable deterministic classifier path on 2026-05-25. The constitution still requires CI-verifiable verdict behavior without live stochastic providers, so deterministic evidence remains mandatory, but it is implemented as provider-fixture test evidence behind the product path rather than as a public/core classifier selection.

**Alternatives considered**:
- Deterministic classifier as the only supported path: rejected because it repeats the fake-done shape Zoe called out; offline evidence is necessary but not the product classifier.
- Provider-backed product classifier with no deterministic evidence: rejected because CI/offline verification would depend on network/credentials and could not be the mandatory done bar.
- Continue the current keyword heuristic: rejected because it causes the known ACK substring and fake-done PASS failures.

## Decision: Make classifier identity visible in successful results/audit output

**Rationale**: Hosts must know which classifier path and provider/model configuration produced a verdict. Machine-readable result fields keep CLI and callable core equivalent and are easier to test than prose-only audit logs.

**Alternatives considered**:
- CLI-only banner or stderr line: rejected because callable-core consumers would lose the audit identity.
- Documentation-only default: rejected because it cannot prove which path was actually selected.

## Decision: Unsupported classifier config fails clearly with no silent fallback

**Rationale**: Silent fallback would make audit output unreliable and could hide missing provider/configuration dependencies. Invalid selection must produce a non-success result path with clear stderr/error semantics through the public CLI and equivalent callable-core error behavior.

**Alternatives considered**:
- Fallback to local/deterministic behavior: rejected because it contradicts FR-007 and makes host configuration non-auditable.
- Treat unknown classifier as ASK: rejected because classifier configuration errors are not admission uncertainty.

## Decision: PASS requires corroborating inspected completion context when resolved-looking text is contradicted or unsupported

**Rationale**: PASS is a hard stop. Resolved-looking text in a trigger is insufficient when supplied context says implementation/evidence is missing, and absence of corroborating context should not become high-confidence PASS.

**Alternatives considered**:
- First-match verdict priority: rejected because it reproduces the current false PASS failure.
- Always downgrade resolved-looking text to ASK: rejected because legitimate PASS must remain reachable with inspected completion evidence.

## Decision: Model confidence as verdict-specific distribution with uncertainty and conflict reflected

**Rationale**: The current fixed `0.85/0.05` distribution masks conflict and makes keyword-shaped matches look equally certain. Provider results and deterministic provider-fixture evidence must lower confidence and surface reasons when context signals conflict or missing evidence.

**Alternatives considered**:
- Preserve the fixed distribution: rejected because FR-013 requires uncertainty/conflict to affect reasons and confidences.
- Return only a scalar confidence: rejected because the existing contract uses per-verdict confidences.

## Decision: Keep adapters and broad benchmarks out of the slice

**Rationale**: TUR-11 is a core admission-classifier slice. Adapter work and marketing/launch claims would blur done criteria and increase fake-done risk.

**Alternatives considered**:
- Include Discord/cc-connect smoke integration: rejected as out of scope by the issue and constitution.
- Add broad benchmark corpus: rejected for this slice; deterministic provider-fixture adversarial cases are the required evidence.
