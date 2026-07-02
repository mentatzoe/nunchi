# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Social core prompt.** The classifier system prompt now poses the
  read-the-room question — who is speaking, what has been said, who is this
  agent; is it this agent's turn? — judged as a socially competent participant
  would. Room doctrine inherited from the open-floor pilot (default-PASS,
  net-new-value bar, ACK-rarity, operator-only directives, corroboration for
  completion claims) is no longer baked into the core prompt; rooms opt into it
  (or any other governance) via `pinned_rules`, which the prompt now applies
  with precedence over plain social sense.
- **Tolerant reference bookkeeping.** Near-miss `context_checked` references
  from the provider (bare `trigger`, prefix-less ids) normalise to their
  canonical envelope references, and unrecognisable references are dropped,
  instead of failing the whole evaluation with "unchecked context references".
  Dropping is conservative for `require_pass_corroboration`: a PASS whose only
  corroboration was an unknown reference ends up uncorroborated and is
  downgraded, never upgraded.

### Added

- **Room governance profiles.** `profiles/open-floor.md` preserves the
  open-floor pilot doctrine as reusable `pinned_rules` text. The 003 verdict
  suite loader accepts a `governance_profile` metadata field and injects the
  named profile into the fixture envelope as a `pinned-rules` context item;
  the five fixtures whose expected verdicts were adjudicated under that
  doctrine now declare it explicitly.

## [0.1.0] - 2026-06-16

### Added

- **Admission core.** A pre-reply admission gate that returns exactly one of the
  four verdicts `PASS`, `ACK`, `ASK`, or `SPEAK`. `PASS` is a hard stop: no
  ordinary user-visible room message is emitted. Admission results never carry
  reply prose (`message`, `reply`, `draft`, and `content` are forbidden result
  fields), keeping the boundary at admission rather than reply composition.
- **Provider-backed classifier.** A `product` classifier backed by an
  OpenAI-compatible chat-completions client built on the standard library
  (`urllib`), defaulting to OpenRouter. Configuration is security-hardened:
  API keys come from the environment (`OPENROUTER_API_KEY` or
  `TURNAWARE_CLASSIFIER_API_KEY`), the model is set via
  `TURNAWARE_CLASSIFIER_MODEL`, and the base URL is overridable via
  `TURNAWARE_CLASSIFIER_BASE_URL`.
- **Classifier rubric and live model selection.** A documented rubric for the
  four-verdict decision, with `gemini-3.1-flash-lite` as the default live model
  selection (plus an open-weight alternative captured in the selection evidence).
- **Provider resilience.** Bounded retry with exponential backoff on transient
  provider errors (HTTP 429/5xx, timeouts); permanent errors (401/403 and other
  4xx) abort immediately. Tunable via `classifier_config.max_retries` and
  `retry_base_delay`.
- **Deterministic fast-path.** A conservative pre-classifier that resolves
  certain-from-the-envelope cases (an `<@id>` mention aimed at another agent, or
  a self-echo) to `PASS` without a provider call, cutting per-turn cost and
  latency; anything ambiguous escalates to the classifier. Disable with
  `TURNAWARE_FASTPATH=0`.
- **Opt-in PASS-corroboration mode.** `classifier_config.require_pass_corroboration`
  (default off) downgrades an uncorroborated `PASS` (one with no consulted
  `context:` reference) to `ASK`, for surfaces that must challenge unverified
  completion claims.
- **Transport-neutral channel adapter.** A `turnaware-channel` adapter that emits
  a transport-neutral verdict-plus-silent JSON envelope by default, exposes a
  generic suppression token for any transport, and offers a `cc-connect` preset
  (`--format cc-connect`) emitting the `CC_CONNECT_SILENT_PASS` sentinel.
- **CLI.** A `turnaware` console script with an `admit` command that reads a
  request from stdin and writes the admission verdict as JSON.
- **Packaging.** A stdlib-only distribution (zero runtime dependencies) that
  installs cleanly in one line and ships the `turnaware` and `turnaware-channel`
  console scripts.
- **CI.** A fully offline GitHub Actions matrix (Python 3.11/3.12/3.13) running
  the `unittest` suite plus a clean-install packaging job that verifies the
  public surface and console scripts.
- **Stability contract and drift detection.** `docs/STABILITY.md` documents the
  stable verdict/result/request surface and the SemVer policy; a manual
  live-smoke job and a scheduled weekly live corpus eval (`scripts/live_eval.py`)
  track provider/model drift.
- **Integration guide.** Documentation covering configuration and adapter
  integration for embedding the admission gate, including a drop-in loader
  template and a generic (non-cc-connect) host example.

[Unreleased]: https://github.com/mentatzoe/turnaware/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/mentatzoe/turnaware/releases/tag/v0.1.0
