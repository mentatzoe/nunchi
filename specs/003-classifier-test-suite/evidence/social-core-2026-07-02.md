# Social core vs rulebook prompt — live evidence, 2026-07-02

Model under test: `google/gemini-3.1-flash-lite` (temperature 0), in-process
adapter, full 37-fixture corpus. Captured while replacing the rulebook system
prompt with the social core (`58e6871`) and relocating open-floor doctrine to
`profiles/open-floor.md`.

## Runs

| Run | Prompt | Profile tags | Result | Artifact |
|-----|--------|--------------|--------|----------|
| Baseline | rulebook (`53d9262`, main) | none | 33/37 | `53d9262-rulebook-baseline.jsonl` |
| Bare social v1 | social core | none | 29/37 | not committed (exploration) |
| Social v2 + tags ×3 | social + 2 extra anchors | 5 tagged | 30/37, identical across 3 runs | not committed (rejected revision) |
| **Final** | social core v1 (`58e6871`) | 4 tagged | **32/37** | `58e6871-social-core-live.jsonl` |

The v2 anchor experiment ("re-asked question needs no new answer", "room as a
whole includes this agent") was rejected on evidence: it cost
`d-suppressor-duplicate` and fixed none of its targets. The shipped prompt is
the simpler v1.

## Run-to-run flicker

Temperature 0 does not eliminate provider variance. Observed flicker set
across the five live runs: `d-operator-topic-pivot-human-pet`,
`m-baseline-ask-ambiguous`, `d-vocative-greeting-second-bot`,
`d-suppressor-duplicate`. A single-run score for this model is honest only as
a range: social core lands 30–33/37; the 33/37 rulebook baseline is a single
run subject to the same flicker.

## Stable failures in the final configuration

| Fixture | Observed | Why it fails | Class |
|---------|----------|--------------|-------|
| `m-baseline-pass-adapter-resolved` | SPEAK | tagged open-floor; flash-lite does not reliably apply pinned-rules doctrine over an explicit summon | in-context governance limit |
| `d-self-iteration-late-turn-duplicate` | SPEAK | agent repeats its own sign-off when the operator re-asks | social-judgment limit |
| `m-constant-confidence-mixed-support` | PASS @ 0.95 | constant winner confidence (FR-008); fails under both prompts | pre-existing invariant limit |
| `m-trigger-only-pass-empty-context` | PASS | trusts an unverified completion claim; fails under both prompts; shipped mitigation is opt-in `require_pass_corroboration` | pre-existing, structural guard covers it |

## What the profile mechanism proved

`d-suppressor-covered` and `c-verdict-surface-typed` fail bare and pass
stably with `profiles/open-floor.md` injected as pinned rules — the model
applies room governance supplied in-context for these shapes.
`m-baseline-pass-adapter-resolved` shows the ceiling: rules-in-context are
weaker than rules-in-prompt for this model. Gains from de-doctrination are
also real: `m-baseline-ack-broadcast` ("please acknowledge" → ACK) fails
under the rulebook's ACK-is-rare doctrine and passes stably under the social
core.

## Implication

Model selection (2026-06-13) chose flash-lite under the rulebook prompt. The
social core shifts what the model must be good at — social judgment plus
applying in-context governance — so the bake-off should be rerun under this
prompt before the next model decision.
