# Open-weight / non-big3 candidate bake-off — 2026-06-14

Live run of the 34-fixture adversarial corpus (rubric prompt on main) against
open-weight and non-big3-proprietary models on OpenRouter, in response to the
owner's Q1. Method matches model-selection-2026-06-13.md.

```
model                             acc     p/f/e  head  p50ms    $/1k
----------------------------------------------------------------------
x-ai/grok-4.3                     91%  31/3/0   6/7   3847   1.500
qwen/qwen3-235b-a22b-2507         88%  30/4/0   6/7   2837   0.096
meta-llama/llama-4-maverick       82%  28/6/0   5/7   2306   0.225
deepseek/deepseek-v3.2            82%  28/5/1   4/7   4266   0.258
mistralai/mistral-small-2603      79%  27/7/0   4/7    991   0.225
deepseek/deepseek-v4-flash        68%  23/4/7   5/7   5545   0.108
z-ai/glm-4.7-flash                18%   6/0/28   2/7   8470   0.114
minimax/minimax-m2.5              12%   4/0/30   0/7  10008   0.270
z-ai/glm-4.7                       3%   1/0/33   1/7  10007   0.623
moonshotai/kimi-k2.5               0%   0/0/34   0/7  10009   0.641
```

head = the 7 load-bearing adversarial cases. $/1k = list price at ~900in/150out.
Current default for comparison: google/gemini-3.1-flash-lite — 88% / 6-7 / $0.45.

## Findings

- **qwen/qwen3-235b-a22b-2507** (Alibaba, open-weight) matches the current pick's
  accuracy (88%) and headline score (6/7) at ~1/5 the cost ($0.096/1k). Strongest
  open-weight alternative.
- **x-ai/grok-4.3** leads quality (91%, 6/7) but at $1.50/1k (non-big3 proprietary).
- The reasoning-tuned models (z-ai/glm-4.7, minimax/minimax-m2.5, moonshotai/kimi-k2.5)
  timed out on most calls at the suite's 10s subprocess budget — not viable for a
  per-turn gate without a much higher latency tolerance.

## Latency / reliability caveat (provider-load-dependent)

These are hosted-provider measurements and vary with OpenRouter load at run time.
The concurrent bake-off above recorded 0 errors for qwen3-235b; a later isolated
re-measure caught a rough patch (p50 ~4.5s, 12 of 34 calls hit the 10s timeout),
while gemini-3.1-flash-lite held p50 ~1.3s. Treat accuracy and cost as the stable
differentiators; gemini-flash-lite is the more consistently low-latency option,
qwen3-235b the cheapest-at-equal-quality option with more latency variance.

## Decision status

Resolved 2026-06-16 (owner): **keep `google/gemini-3.1-flash-lite` as the
default** — its quality/latency/cost is good enough, and its latency is the most
consistent. `qwen/qwen3-235b-a22b-2507` is documented as the recommended
**open-weight** alternative (equal accuracy/headline at ~1/5 the cost, with more
latency variance through OpenRouter); switching is a one-line
`TURNAWARE_CLASSIFIER_MODEL` change. See the integration guide's Configuration
section.
