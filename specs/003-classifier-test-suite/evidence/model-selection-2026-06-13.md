# Classifier model selection (live bake-off)

**Date**: 2026-06-13
**Method**: run the 003 adversarial corpus (34 model-scored fixtures: 15 multica
+ 19 discord; the 3 contract fixtures are mock and model-independent) live
against each finalist OpenRouter model via the suite's subprocess adapter, and
rank on accuracy, the load-bearing adversarial cases, latency, reliability, and
cost. This is the dedicated benchmark for *this* job — the suite selects the
model.

**Selected**: `google/gemini-3.1-flash-lite`.

## Round 2 — final, on the enriched prompt

Run at concurrency 3 (clean latency). `$/1k` ≈ list price at ~900 prompt + 150
output tokens/call. `headline` = the 7 load-bearing cases (FR-001 substring trap,
FR-002 fake-done PASS, FR-005 trigger-only PASS, FR-021 covered + duplicate
suppressors, FR-018 unaddressed mention + named-ask).

| model | acc | pass/fail/err | headline | p50ms | p95ms | $/1k |
|-------|-----|---------------|----------|-------|-------|------|
| **google/gemini-3.1-flash-lite** | **88.2%** | 30/4/0 | **6/7** | 1092 | 2015 | **$0.450** |
| google/gemini-2.5-flash | 88.2% | 30/4/0 | 5/7 | 1132 | 2016 | $0.645 |
| anthropic/claude-haiku-4.5 | 79.4% | 27/7/0 | 6/7 | 2616 | 4500 | $1.650 |
| deepseek/deepseek-v3.2 | 79.4% | 27/5/2 | 5/7 | 3222 | 10007 | $0.258 |
| google/gemini-2.5-flash-lite | 76.5% | 26/8/0 | 4/7 | 654 | 1244 | $0.150 |
| openai/gpt-5.4-nano | 58.8% | 20/7/7 | 4/7 | 1370 | 5122 | $0.367 |
| openai/gpt-5-mini | 44.1% | 15/0/19 | 4/7 | 10006 | 10012 | $0.525 |

## Decision rationale

- **gemini-3.1-flash-lite wins on performance/cost.** Tied for the best accuracy
  (88%), the best headline score (6/7 — it misses only FR-005, the single
  hardest case that every model misses), perfectly reliable (0 errors / always
  valid JSON), fast (p50 1.1s, tight p95), and cheap ($0.45/1k). It strictly
  dominates gemini-2.5-flash, which matches accuracy but scores 5/7 headline and
  costs 43% more for the same latency.
- **claude-haiku-4.5** ties the headline score (6/7) but is 3.7× the cost
  ($1.65/1k), slower, and lower accuracy. (Round 1 it scored 0% — it returns
  markdown-fenced JSON; the fence-tolerance fix in the core classifier rescued
  it, which is why it is reliable here. Good portability evidence, not the pick.)
- **deepseek-v3.2** is cheaper ($0.26) but had 2 timeouts and high p95 (10s) —
  reliability/latency risk for a per-turn gate.
- **gemini-2.5-flash-lite** is the cheapest reliable option ($0.15, fastest) but
  weak on the load-bearing cases (4/7) — acceptable only if cost dominates
  quality, which for an admission gate it should not.
- **gpt-5.4-nano / gpt-5-mini** are out: gpt-5-mini (a reasoning model) timed out
  on 19/34 calls at the 10s budget; gpt-5.4-nano had 7 errors (it echoed the
  prompt's literal `trigger:example` into context_checked).

## The prompt is the bigger lever than the model

Round 1 used the generic prompt; **every** finalist missed FR-005, the
Covered/Duplicate suppressors, and the unaddressed-mention/named-ask cases (best
headline 4/7). Encoding the admission rubric from pilot-bot `before-you-respond.md`
(addressing → suppressors → unverified-resolution → SPEAK/ASK/ACK on net-new
value) lifted gemini-3.1-flash-lite from 3/7 → 6/7 headline and 70.6% → 88.2%
accuracy with no model change. See commit "encode admission rubric in classifier
prompt".

| model | round 1 (generic) acc / headline | round 2 (rubric) acc / headline |
|-------|----------------------------------|----------------------------------|
| google/gemini-3.1-flash-lite | 70.6% / 3 | 88.2% / 6 |
| google/gemini-2.5-flash | 76.5% / 4 | 88.2% / 5 |
| google/gemini-2.5-flash-lite | 67.6% / 1 | 76.5% / 4 |

## Residual known limitation

FR-005 (trigger-only PASS / unverified resolution: "Already handled. Resolved.
No response needed." with empty context) is missed by every model, including the
winner — they treat an explicit resolution claim as legitimately PASS-able. The
suite keeps the fixture as semantic ground truth (a bare claim should be
verified, not trusted) and records this as the open gap, not a fixture bug.

## Reproduce

```sh
export TURNAWARE_CLASSIFIER_MODEL=google/gemini-3.1-flash-lite
export OPENROUTER_API_KEY=...
python3 specs/003-classifier-test-suite/contracts/runner.py --format jsonl > run.jsonl
```

Full live run for the selected model is committed alongside this file as
`0437537-live.jsonl` (33/37 pass, 0 errors). The 4 fails: `m-trigger-only-pass-empty-context`
(FR-005, the residual limitation above); `d-vocative-greeting-second-bot` (a
Covered case — the model spoke where a peer had already greeted);
`m-baseline-ack-broadcast` (the model escalated an ACK-shaped presence signal to
SPEAK); and `m-constant-confidence-mixed-support` (FR-008 — verdict defensible
but expressed with higher confidence than the mixed support warrants). All four
are over-participation or over-confidence at the margin, consistent with the
headline analysis; none is an adapter or suite defect.
