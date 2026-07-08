# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed — documentation truthfulness sweep

- **Honest install instructions.** `pip install nunchi[discord]` is impossible
  from the published 0.2.0 release (PyPI 0.2.0 = core + `nunchi`/`nunchi-channel`
  only; the platform adapters landed later). README, `docs/adapters.md`, the
  Discord adapter docstring, and its missing-dependency error message now give
  source-install commands (`pip install "nunchi[discord] @ git+…"` /
  `pip install ".[discord]"`) with an availability note. Stale "not yet on
  PyPI" claims in README and `docs/integration.md` (false since 0.2.0 shipped
  on 2026-07-02) now state what PyPI actually carries versus what is
  source-only.
- **Beta labels disclose live-run status.** The adapter index tables in
  `docs/adapters.md` and README now footnote that the Matrix/Telegram/Discord
  adapters have full offline test coverage but have not yet been run against
  live servers.
- **Stale history defaults.** `NUNCHI_MATRIX_HISTORY`, `NUNCHI_TELEGRAM_HISTORY`,
  and `NUNCHI_DISCORD_HISTORY` docs and module docstrings said `10`; the code
  default has been `20` since the history-depth merge. A new enforcement test
  (`tests/test_docs_truthfulness.py`) pins documented defaults to the code
  constants so this class of drift fails CI.
- **Hermes `history_window` documented.** The functional-but-undocumented
  `history_window` config key (default 20, global `config.yaml` only — not a
  per-channel key) is now in the nunchi-gate plugin config docstring, also
  pinned by the enforcement test.
- **Changelog link hygiene.** Added the missing `[0.2.0]` compare anchor,
  pointed link references at `mentatzoe/nunchi` (was `mentatzoe/turnaware`),
  and `[Unreleased]` now compares from `v0.2.0`.

### Changed

- **Hermes dashboard tab: UX repair and product redesign.** Two rounds driven
  by a behavioral audit and direct owner review. Repair: Reset All actually
  clears (empty-dict-replaces semantics in a new tested `apply_state_patch`),
  per-field override deletion via `null`, overrides equal to the baseline are
  pruned instead of accumulating, success messages auto-dismiss, pending edits
  are badged, Save disables when clean, badges no longer pollute accessible
  names. Redesign: native hermes theming via host CSS variables and SDK
  components (zero hardcoded colors), human-readable channel names resolved
  from the hermes channel directory, a real `allow_from` editor, in-place help
  copy for sender policies and verbosity levels, per-channel `model` and
  `pinned_rules` (room governance) editing — `pinned_rules` joins the state
  whitelist — receipt rows show the full confidence distribution with a
  corrected four-verdict legend, and the receipts poll gained pause/interval
  controls plus visibility-aware suspension.

- **Dashboard round 3.** The Nunchi tab can now add channels directly (a
  picker of gateway-known channels not yet configured, plus free-text id
  entry; staged through the normal Save flow) with an inline note that the
  channel must also be one the gateway listens to. The global and per-channel
  model fields show the actual resolved model and its source (config /
  environment / .env) instead of an unhelpful "inherit" placeholder. Receipt
  rows are expandable disclosures rendering every logged field — full reasons,
  confidence table, model, message id, and (at debug verbosity) the complete
  gate payload and directive.
- **Dashboard verification round.** Fixed the text-input remount bug (typing
  no longer loses focus per keystroke), added an honest save contract (PUT
  echoes applied state and rejected keys; the UI reports fields the server
  did not accept instead of faking success) and an `api_version` handshake
  that banners loudly when the dashboard service runs an outdated backend,
  per-channel and global paths back to baseline (inherit options, per-channel
  clear, `allow_from` cleanup on policy change), readable channel-ID pills,
  effective-model display, verbosity meanings in the options, and label/input
  association fixes.

### Added

- **Telegram reference adapter.** `nunchi.adapters.telegram` joins Telegram chats
  as a gated participant using the Telegram Bot HTTP API over stdlib `urllib`
  (zero extra dependencies). Ships the `nunchi-telegram` console script. Features:
  - Long-polling `getUpdates` loop with offset persistence
    (`NUNCHI_TELEGRAM_STATE`)
  - Chat allowlist from `NUNCHI_TELEGRAM_CHATS` (comma-separated integer IDs)
  - PASS/ACK/ASK/SPEAK gate-first architecture; text messages only
  - Author-kind tagging: own messages are `self` (skipped as triggers),
    `is_bot=true` users are `peer_bot`, everything else is `human`
  - Pluggable responder callback; built-in demo responder shared with
    `nunchi-matrix` via `nunchi.adapters._responder`
  - `sendMessage` on non-silent verdicts (SPEAK/ACK/ASK)
  - JSONL receipt log (`NUNCHI_TELEGRAM_LOG`) with the same field shape as the
    Matrix adapter
  - Retry/backoff on HTTP 429 — honours `retry_after` from the JSON response
    body first, then the `Retry-After` header; permanent 4xx abort immediately
  - `--dry-run` and `--once` flags

- **Discord adapter (optional extra).** `nunchi.adapters.discord` joins Discord
  channels as a gated participant via discord.py's event-driven client.
  - Install from source with the `[discord]` extra (`pip install ".[discord]"`
    from a checkout); discord.py is not a default dependency and never leaks
    into the core install path
  - Configurable bot policy: `NUNCHI_DISCORD_BOT_POLICY=all` (default, gate all
    bots as peers) or `allowlist` (only bots in `NUNCHI_DISCORD_PEER_BOTS`)
  - History backfill of up to 10 messages via `channel.history` on the first
    event per channel
  - `NUNCHI_DISCORD_MAX_EVENTS` for bounded test runs (no `--once` — discord.py
    is event-driven)
  - Pure import-safe functions (`_resolve_author_kind`, `_append_to_history`,
    `_build_receipt`) live at module level and are testable without discord.py
  - Ships the `nunchi-discord` console script; `--dry-run` flag supported

- **Shared demo responder.** `nunchi.adapters._responder._demo_responder`
  extracted from the Matrix adapter into a shared internal module so Telegram,
  Discord, and future platform adapters can reuse it without copying code. The
  Matrix adapter public API is unchanged.

- **Adapter docs index.** `docs/adapters.md` is the new single-source adapter
  reference: an index table (adapter, surface, install weight, status), full
  setup guides for Matrix, Telegram, and Discord, and links to the Hermes plugin
  and Claude Code hook integration docs. The full Matrix adapter section has
  moved from `README.md` to `docs/adapters.md`; the README now carries a compact
  overview table with a link.

- **Matrix reference adapter.** `nunchi.adapters.matrix` joins Matrix rooms as a
  gated participant using the Matrix Client-Server API over stdlib `urllib` (no
  `matrix-nio` or other runtime dependencies). Ships the `nunchi-matrix` console
  script: one command to stand up a read-the-room agent on Matrix. Features:
  - Long-polling `/sync` loop with since-token persistence
  - PASS/ACK/ASK/SPEAK gate-first architecture: every inbound message is checked
    before any response is generated
  - Pluggable responder callback (`respond(trigger, history, gate_result) -> str | None`);
    a built-in demo responder (OpenAI-compatible chat-completions via `urllib`) is
    included and clearly labelled a demo
  - Author-kind tagging: own messages are `self`, user IDs matching
    `NUNCHI_MATRIX_PEER_BOTS` are `peer_bot`, everything else is `human`
  - Encrypted-room detection: `m.room.encrypted` events are skipped with a
    one-time per-room warning; unencrypted rooms only
  - JSONL receipt log per gated event with verdict, action, elapsed_ms, reasons
  - Retry/backoff on HTTP 429 and 5xx; permanent 4xx errors abort immediately
  - `--dry-run` flag (gates but never sends) and `--once` flag (one sync batch
    then exit, for cron/testing)
  - Room allowlist from `NUNCHI_MATRIX_ROOMS`; events outside the allowlist are
    ignored
  - Open Floor Protocol vocabulary alignment: SPEAK/PASS/ACK/ASK map onto OFP
    floor semantics so future OFP compatibility requires no translation layer

## [0.2.0] - 2026-07-02

### Changed

- **Renamed to nunchi.** The project, package, module, console scripts, and
  environment variables are now `nunchi` (눈치 — the art of reading the room
  and knowing whether it is your turn to speak; the word means exactly what
  the gate does). `turnaware` was never published to PyPI, so this is a clean
  break: `TURNAWARE_*` environment variables become `NUNCHI_*`, the
  `turnaware`/`turnaware-channel` scripts become `nunchi`/`nunchi-channel`,
  and `TurnAwareError` becomes `NunchiError`. Historical spec narratives and
  captured evidence keep the old name as a matter of record.
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

[Unreleased]: https://github.com/mentatzoe/nunchi/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/mentatzoe/nunchi/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/mentatzoe/nunchi/releases/tag/v0.1.0
