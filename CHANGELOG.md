# Changelog

## Unreleased

- Retired the executable SpecKit workflow, generated task/checklist control
  plane, and slice lifecycle as implementation authority. Detailed product
  specifications and technical plans remain reference material; V2 now uses
  ordinary dependency-ordered implementation PRs governed by
  `docs/v2-delivery.md` and the completion goal.

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed — program and slice lifecycle replaces local-run framing

- External guidance records the 2026-07-11 reset baseline—the V2 program
  `READY`, implementation authority `NOT_GRANTED`, and all slices `010`–`110`
  `PLANNED` with product tasks dormant—as a dated snapshot rather than a live
  registry. Readers resolve current program progress from the umbrella,
  authority from the exact authorization record, and slice state/occupant from
  the bound declarations plus immutable activation/acceptance records and
  append-only candidate/handoff evidence. V1 remains current until the atomic
  V2 merge is post-merge verified
  as `CUTOVER_VERIFIED`.
- Both workflows operate on one existing slice through
  `python3 scripts/run_slice_workflow.py run <workflow> specs/<exact-slice>`.
  The runner verifies exact SpecKit `0.12.11` and its pinned PEP-610 source,
  preflights and binds the slice in the workflow process, resolves the concrete
  integration, pins those facts with the slice input and workflow digests, and
  rejects altered resume state without mutating `.specify/feature.json`. The planning cycle is now the
  nine-step `Nunchi Existing-Slice Planning Cycle` version `1.4.0`; it begins at
  `bind-existing-slice`, stops after analysis, and never creates or replaces a
  feature. Participants resume a paused unchanged-task run only through
  `python3 scripts/run_slice_workflow.py resume <run-id>`; changed tasks or a
  rejected completed handoff start a new bound run. The delivery workflow's
  implementation-authority gate requires the external grant record at
  `evidence/governance/v2-implementation-authorization.md` to enumerate exactly
  all eleven slices; a partial or extra-scope record is invalid for every slice.
  Its separate readiness gate verifies owner, dependencies, analysis, worktree,
  and activation evidence.
- Zoe, or an assigner named in a durable Zoe delegation, assigns the program
  owner and slice occupants. The declaration and activation evidence carry
  `<participant identity> — evidence/governance/assignments/<record>.md`; that
  record contains `Assignee`, `Lane`, `Assigned by`, `Assigned on`, and
  `Authority reference`, plus `Delegated by: Zoe` and `Delegation reference`
  for a non-Zoe assigner. Assignment may precede
  authority for planning but never grants implementation or readiness; no
  central assignment registry is introduced.
- Slice state follows `PLANNED -> READY -> ACTIVE -> CONVERGED -> HANDOFF_READY
  -> ACCEPTED`. Each dependent independently accepts its required upstream
  handoffs before readiness; at slice level `v2-integrator` accepts `010`–`100`
  and Zoe accepts `110`. Only slice `110` integrates. After its handoff, Zoe's
  exact-candidate decision establishes slice `ACCEPTED` and program
  `CUTOVER_ACCEPTED`; one atomic merge remains verification-pending, and a
  docs/evidence-only follow-up combines exact-main verification with final
  current-state docs validation before `CUTOVER_VERIFIED`. State is derived
  from control-plane declarations, immutable activation/acceptance records,
  and append-only candidate/handoff attempt streams, never a central runtime,
  conversation, participant, assignment, or social-state registry.
- Activation evidence now maps dependencies to ordered full commits and
  matching per-consumer acceptance files; slice `110` requires every upstream
  slice to be `ACCEPTED`. Candidate and handoff files are append-only attempt
  streams. Convergence-added tasks and rejected completed handoffs each keep or
  return the same owner to `ACTIVE` and require a new bound run; only paused
  post-convergence fixes with an unchanged task graph resume. No candidate or
  packet history is erased.

### Changed — mandatory documentation freshness for implementation slices

- Constitution 2.3.0 retains `README.md` and affected ordinary documentation as
  blocking part of every SpecKit implementation. Each reviewed surface must use
  `UPDATE`, evidence-backed `NO_IMPACT`, or an exact owner-accepted `HANDOFF`;
  generic documentation tasks and bare no-impact claims no longer close a
  slice.
- The delivery workflow gates documentation freshness after convergence and before
  slice handoff. Spec, plan, task, checklist, agent-guidance, and all V2 slice
  artifacts carry the same ownership and validation rules.
- Slices `010`–`100` update their owned component guides and hand exact global
  claim deltas to `v2-integrator`; slice `110` must update `README.md` and all
  affected cross-surface documentation in the atomic candidate.
- Governance tests reject missing README dispositions, bare `NO_IMPACT`,
  missing doc tasks/checklist coverage, and a missing or misordered workflow
  gate.
- Active slices now inventory exact existing docs as well as planned V2 guides;
  generic directory scope is rejected. The dormant-task check remains strict
  while implementation authority is `NOT_GRANTED`, but permits completed tasks
  after the external grant is documented at
  `evidence/governance/v2-implementation-authorization.md`, enumerates exactly
  all eleven slices, and the bound slice's independent readiness gate passes.

### Fixed — round-4 review: confidence domain, uninstall confinement

- **Confidences must be on the stated [0, 1] scale**, enforced identically at
  the hook (`defer-malformed-confidence` when DEFER is on) and the shared
  schema boundary (`ValidationError`), so core and adapters cannot disagree.
  `{"PASS": 9.0, ...}` and negative vectors previously passed the exactness
  check and hard-blocked — off-scale evidence has no defined margin meaning.
- **Confinement covers destructive writes:** both uninstall paths now call the
  ancestor check before mutating; uninstalling through a symlinked
  `plugins/`/`hooks/` that escapes the configured root is rejected instead of
  recursively deleting external directories. Aleph's repros are the
  regression tests.
- **Residue swept to the current contract:** remaining unreleased-changelog
  lines and the two addressing fixture metas no longer assert the
  deterministic fast-path or alias-authorship-as-fact; the hook's module
  docstring now states the two fail-open contracts explicitly (runtime
  failures receipted; malformed config knobs fall back silently to documented
  defaults, verifiable from receipts' effective values).

### Fixed — round-3 review: terminal fail-open, exact destructive PASS, installer parity

- **Declared fail-open is terminal.** A mistyped `transcript_path` used to
  write `allow-input-error` and then keep judging (the receipt said allow, the
  gate blocked). Input errors now stop processing.
- **A destructive PASS must be complete and exactly typed:** `silent` present
  and boolean, `reasons` a non-empty list of non-empty strings, confidences
  exactly the four verdict keys (extras are evidence malformation → DEFER when
  enabled). Defaults no longer forge the destructive form; admits stay lenient
  because they destroy nothing.
- **The outer guard is actually outer:** fallible config (`NUNCHI_HOOK_TIMEOUT`,
  `NUNCHI_HOOK_TOOL_PATTERN`) parses safely instead of crashing at import, and
  any exception escaping the guarded main — decoder recursion included — exits
  0 with a receipted `allow-hook-error`.
- **Attribute tokens require both boundaries** (`chat_id="c1"junk` no longer
  binds) and duplicate required attributes reject the envelope as ambiguous.
- **Hermes installer parity:** the plugin tree now gets the same
  file-inventory + content-drift verification, upgrade-repairs, and
  `_ensure_confined` ancestor check as the Claude path;
  `verify → upgrade → verify` converges for deleted and tampered plugin files,
  and a symlinked `plugins/` escaping `$HERMES_HOME` is rejected before writes.
- **Docs and prompt tell the current contract:** aliases are addressing
  evidence, never authorship — corrected in `docs/integration.md`,
  `src/nunchi/schema.py`, the unreleased changelog entries, and the classifier
  prompt itself (which had asserted name-equality authorship as fact).

### Removed — the deterministic pre-classifier layer, entirely

- **The fastpath module is gone** (round-2 review + room baseline: suppression
  may be deterministic only where mechanically provable, and the current
  envelope carries no transport-bound identity, so nothing qualifies). The
  mention-elsewhere rule fell in round 2's precursor; round 2 proved the
  self-echo rule equally unsound — author-name equality accepted a human whose
  display name matched an alias as "self", and text equality accepted a human
  repeating "Thanks." as the agent's own echo, both minting PASS 1.0 with no
  model call and sailing past DEFER. Every admission is now classifier-judged.
  Deterministic short-circuits may return only when the message contract
  carries an adapter-asserted runtime binding (schema-v2). `NUNCHI_FASTPATH`
  env knob removed with the layer.

### Fixed — Claude Code gate: strict directive typing, envelope integrity, crash paths

- **Hard suppression now requires a complete, finite, correctly typed
  confidence vector.** A PASS whose confidences are missing, partial, mistyped,
  or non-finite ABSTAINS (`defer-malformed-confidence`, malformation receipted)
  instead of hard-blocking — broken evidence is not confidence. The explicit
  `NUNCHI_DEFER=off` kill switch keeps its hard meaning. `silent` must be a
  real boolean (`"false"` no longer coerces into a forged block) and `reasons`
  a real list; both fail open with a receipted `allow-gate-error` otherwise.
- **Envelope integrity:** attribute parsing requires complete tokens
  (`not-chat_id="c1"` no longer binds as `chat_id`); whitespace-only
  identifiers read as missing (`allow-envelope-error`).
- **The "always exit 0, fail open, receipt errors" contract is now mechanical:**
  `prompt: null` and mistyped top-level fields fail open with a receipted
  `allow-input-error`; a non-object transcript row is skipped; a malformed
  `NUNCHI_HOOK_HISTORY_WINDOW` falls back to its default; any unhandled hook
  exception exits 0 with a receipted `allow-hook-error`.

### Fixed — installer: verification integrity and confinement

- `verify` no longer certifies broken or mixed deployments: every managed file
  must exist as a regular file (a deleted wrapper is reported and `upgrade`
  repairs it), installed bytes are compared against source (content drift
  reported), retired-name broken symlinks are visible, and the stale-settings
  scan runs even when nothing is installed. `verify → upgrade → verify`
  converges for all of these.
- The CLI check reports `present-unverified` — presence is not provenance; the
  shared `nunchi-channel` is a separate deploy surface (documented in
  docs/INSTALL.md with the refresh step).
- Destination ancestors that resolve outside the configured root are rejected
  before any write (symlinked `hooks/` escaping `--prefix` was reproducible);
  symlinks that stay inside the root remain legitimate operator topology.

### Removed — fastpath mention-elsewhere short-circuit (the precursor, in detail)

- **A foreign `<@id>` mention no longer produces a deterministic PASS.** The
  rule conflated referential mention ("another agent appears in the story")
  with floor assignment ("the message is for them"). Live false PASS,
  2026-07-10: the operator replied to an agent's own message, correcting it by
  name, while @mentioning a peer who featured in the anecdote — the fast path
  stamped `PASS 1.0`, `classifier_model: null`, and no model ever read it.
  Because a fastpath PASS carries full confidence, it also sailed past DEFER —
  deterministic overconfidence sat above the uncertainty lane. Room-agreed
  contract (Aleph/Aether/Vigil/Station): *a deterministic rule may hard-PASS
  only what it can prove; a foreign mention proves reference, not exclusive
  targeting.* Foreign-mention messages now always get semantic adjudication.
  (Self-caused echo briefly remained as a short-circuit; the entry above
  removes the whole deterministic layer — name/text equality is not proof.)
  Fixture `a-mention-other-alias-in-passing` keeps its PASS ground truth but is
  now model-scored. (The live canary was pinned in `tests/test_fastpath.py`
  until the whole deterministic layer was removed — see the entry above; the
  canary's ground truth lives on in the fixture corpus.)

### Changed — Claude Code: one judgment per turn, at wake (send-time gate retired)

- **Retired the Claude Code send-time (`PreToolUse`) gate** (`nunchi_gate_hook.py`
  and its `nunchi-pretool-reply.sh` wrapper). It re-judged an already-admitted
  turn against the newest transcript line, so a peer message landing while the
  agent composed stole the causal role and the composed reply died as a false
  PASS. Nunchi now makes its single admission judgment at wake
  (`UserPromptSubmit`) and gets out of the way; no permit/ledger side state is
  needed because nothing has to be kept consistent across two judgments.
  `tests/test_no_second_judgment.py` scans the whole project to keep both the
  retired hook and the ledger shape removed.
- **DEFER (gate abstention) added to the wake gate, default on.** On an
  *uncertain* PASS (best alternative verdict within `NUNCHI_DEFER_MARGIN`,
  default 0.25) the gate declines to silence: the prompt goes through with the
  gate's hesitation noted in-band, and the agent's own model decides — replying
  and staying silent both stay open. `NUNCHI_DEFER=off` restores hard PASS.
  Abstentions are receipted as `defer-uncertain-pass` for offline evaluation.
- **Admissions travel in-band.** SPEAK/ACK/ASK now add a short
  `additionalContext` note naming the message the turn answers, anchoring
  composition to its origin without side state.
- `nunchi-install` upgrade/uninstall now actively remove the retired hook files
  (with backups), `verify` flags leftovers as stale, and the printed
  `settings.json` snippet is `UserPromptSubmit`-only (delete any old
  `PreToolUse` entry by hand — settings remain operator-owned).

### Added — Codex/Vigil room integration and operator surface

- Added a long-running Codex room runner for the shared Discord MCP transport.
  It gates every notification before `codex exec`, backfills configured channel
  history at startup and newly observed/hot-added channels before their first
  live gate, suppresses `PASS` without a frontier wake, and records receipts.
- Admitted room wakes now create and then resume one dedicated Codex task using
  an atomically persisted thread id. Session mode/path are configurable;
  malformed state fails closed, receipts expose the observed task id, and the
  configuration app reports or resets the persistent session.
- Added Codex `UserPromptSubmit` and outbound `PreToolUse` hooks. Supported room
  sends are re-gated immediately before the tool call; missing/current-context,
  malformed-send, duplicate-send, direct Discord command, `PASS`,
  disabled-state, corrupt-state, receipt-write, and closed-policy gate-error
  paths deny the send.
- Added atomic hot runtime state shared by the runner and both hooks, with
  global/per-channel presence, sender/allowlist, receipt detail, classifier
  model, pinned-rule, channel-add, and channel-disable controls.
- Added a local MCP Apps configuration server and responsive task-embedded panel
  for those controls, health, and newest-first receipts. Codex has no documented
  persistent third-party dashboard-tab slot, so this provides the Hermes
  operator functions in Codex's embedded app container.
- Added the repo-local `nunchi-codex@local-repo` marketplace plugin, package
  entry points, copy-safe hook commands, offline unit/protocol tests, and a
  committed bounded Vigil smoke evidence record. A second record verifies two
  admitted live turns resumed the same persisted Codex task and one response
  reached Discord. These support only narrow smoke claims, not sustained
  operations; the app also has offline protocol and responsive interaction
  evidence.
- Normalized Discord rich-only peer messages into tagged, bounded text for
  both live events and history, while preserving ordinary content and excluding
  button labels. This prevents visible embed-only reviews or approval notices
  from being misclassified as empty room events.
- Preserved Discord mention and reply metadata across live/history transport
  shapes. The Codex runner now restores available referenced messages and uses
  structured mention ids for admission and outbound re-gating without changing
  the prose displayed to Codex.

### Added — `nunchi-install`: copy-based installer for operator artifacts

A new `nunchi-install` console script (backed by the stdlib-only
`src/nunchi/install.py`) installs Nunchi's operator artifacts into stable
locations by **copying**, never symlinking. This fixes a real incident: the
Hermes plugin had been **symlinked** into `~/.hermes/plugins` from a live git
checkout, so a `git checkout` on another branch silently swapped the running
plugin for stale code; separately, the Claude Code hooks were registered by
floating checkout paths (`/Volumes/...`) that broke when the path moved.

- **Three artifact groups → stable destinations.** The Hermes plugin
  (`integrations/hermes/nunchi-gate/`, excluding `__pycache__`/`docs/`/`tests`,
  keeping the runtime `.py`, `plugin.yaml`, and `dashboard/`) is copied to
  `$HERMES_HOME/plugins/nunchi-gate/` (default `~/.hermes`) as a **real
  directory**. The Claude Code hooks (`nunchi_gate_hook.py`,
  `nunchi_prompt_gate.py`) are copied to `~/.claude/hooks/`, alongside two
  **fail-open** shell wrappers (`nunchi-pretool-reply.sh`,
  `nunchi-user-prompt-submit.sh`) that source an optional env file and run the
  hook with `|| exit 0` so a missing/broken gate never blocks Claude Code. The
  `nunchi-channel` CLI is checked on `PATH` (never installed; prints `pip`
  guidance if absent).
- **Symlink replacement (the core fix).** A symlinked destination is detected,
  its target recorded in the version marker, backed up (preserved as a link),
  and replaced with a real copy. `uninstall` restores the backed-up symlink.
- **Version stamping + safe upgrade.** Each destination gets a
  `.nunchi-install.json` marker recording the source commit (`git rev-parse
  HEAD`, falling back to a `VERSION` file or `"unknown"`), source path,
  timestamp, and file list. `upgrade` re-copies only when the source commit
  differs (or the destination is missing/symlinked), backing up the old copy
  first; `--force` overrides. `verify` reports per-artifact drift as
  `in-sync` / `stale` / `not-installed` / `symlink-found`.
- **Commands + flags.** `install`, `upgrade`, `verify`, `uninstall`, and
  `print-claude-settings` (prints the `settings.json` hook registration
  pointing at the stable wrapper paths — the operator's file is never
  auto-edited). Global `--dry-run` (plans without touching disk),
  `--prefix` / `--hermes-home` / `--claude-home` / `--repo-root` overrides, and
  `--only` group selection; flags work before or after the subcommand.
- **Determinism.** The wall clock and source-commit resolver are injectable, so
  the 45 new offline `unittest` cases (`tests/test_install.py`) confine every
  write to temp dirs — never the operator's real `~/.hermes` / `~/.claude` —
  and pin marker timestamps and backup names.
- **Docs.** New [`docs/INSTALL.md`](docs/INSTALL.md) (install/upgrade/verify/
  uninstall, the `settings.json` snippet, and the "why we copy, not symlink"
  note); `docs/integration.md` and `integrations/hermes/README.md` now point at
  `nunchi-install` and warn against symlinking the plugin.

### Added — `agent.aliases`: the gate knows every name one bot carries

One agent on a chat surface carries several identities at once — its
configured `agent_id`, its platform mention token (a Discord snowflake), a
display name ("Vigil"), secondary handles ("Codex"), profile names
("Aether"). Two live failures on 2026-07-08 came from the gate knowing only
one of them: a runner whose `mention_id` held the *display name* PASSed a
direct `@<snowflake>` mention ("mentions other participants only"), while
bare occurrences of the name in prose triggered wakes. The envelope now
carries the full bundle. Everything below is **additive-optional**: absent
or empty aliases, behavior — including the serialized classifier request —
is byte-for-byte identical to before (golden-request test pins this).

- **Envelope: optional `agent.aliases`** (list of non-empty strings),
  validated by `validate_request` (non-string/blank entries rejected),
  passed through to the classifier with the rest of the `agent` object.
  Documented in `src/nunchi/schema.py` and `docs/STABILITY.md`.
- **Aliases are addressing evidence for the classifier only.** (This entry
  originally extended the deterministic fast-path's identifier sets; that
  entire layer was later removed in this same unreleased cycle — see the
  removal entries above. Aliases establish who a message may be FOR; they are
  never proof of authorship.)
- **Classifier prompt** now states the agent may be addressed by any of its
  `id`, `mention_id`, or `aliases`. (An earlier revision also told the
  classifier a message authored under an alias "is the agent's own" — that
  authorship claim is retracted per the round-3 review: name-equality is not
  authorship.)
- **Channel adapter**: `agent_aliases` parameter on `build_request()` /
  `gate()`, `agent.aliases` passthrough in the CLI payload, alias-aware
  `self` role inference for history lines, and a shared `parse_alias_csv`
  helper for env knobs. Alias lists are deduped against
  `agent_id`/`mention_id`, order-preserving.
- **Surface knobs** (each documented in its config docstring/README, all
  stating loudly that `mention_id` is the platform snowflake/token, NOT the
  display name — names belong in aliases):
  - the Claude Code wake gate (UserPromptSubmit; its PreToolUse sibling was
    later retired — see above) and the Codex
    UserPromptSubmit hook: `NUNCHI_HOOK_ALIASES` (comma-separated);
  - Codex room runner: `NUNCHI_RUNNER_ALIASES`;
  - Hermes plugin: `aliases:` config key (CSV or list), global and
    per-channel in the map form of `channels`; excluded from runtime state
    overrides like the other identity keys;
  - standalone adapters: `NUNCHI_MATRIX_ALIASES`, `NUNCHI_TELEGRAM_ALIASES`,
    `NUNCHI_DISCORD_ALIASES`.
- **003 corpus: new `addressing` fixture pool (`a-*`)** under
  `evals/verdict_suite/fixtures/addressing/` — six
  envelope+meta pairs distilled from the live failures: direct
  `@<snowflake>` mention with the snowflake in aliases (SPEAK), display-name
  address (SPEAK), secondary-alias address "Codex" (SPEAK), a different
  bot's name (PASS), a relay echo under a profile-name alias, and a mention
  of another participant with our alias only in passing prose (both PASS —
  originally deterministic-fast-path cases, model-scored since the layer's
  removal). Loader,
  runner (`--source addressing`), and runner self-tests discover the pool
  the same way as the injection and tool-chrome classes.
- **Merged `feat/codex-plugin` into this branch** (Codex room runner +
  pre-LLM prompt gate hook, previously unmerged) so the alias knob could
  land on the Codex surface too; its hook tests were also brought under
  `tests/hook_sandbox.sandbox_env`, matching main's receipt-log hygiene
  enforcement.
- Scope note: alias matching is identity plumbing, not fuzzy matching —
  (historical: the then-extant fast-path compared only structured tokens; the
  layer is now removed and ALL addressing judgment, prose or structured, is
  the classifier's). The SPEAK
  expectations in the new fixtures are model judgment (evidence:
  `predicted`), not fast-path guarantees.

### Fixed — fail-policy wiring, empty-send guard, peer-tool-chrome fixtures

- **Hermes plugin: `fail_open` now reaches the nunchi-channel binary as the
  payload's `fail_policy`** (`"open"` when true, `"closed"` when false).
  Previously `fail_open` only governed the plugin's own exception path — the
  binary's envelope defaulted to fail-open, so a classifier outage inside
  `nunchi-channel` degraded to SPEAK even when the operator set
  `fail_open: false` (live event 2026-07-08). `fail_open` was already
  per-channel overridable (map form of `channels`), and the override now
  flows into the payload; tests cover the default (open), both mappings, and
  the per-channel override end-to-end.
- **Standalone adapters (`nunchi-matrix`, `nunchi-telegram`,
  `nunchi-discord`): empty-send guard.** When the responder returns empty or
  whitespace-only text, the send is suppressed and a receipt is written with
  `action: empty-suppressed` (previously the adapters posted literal empty
  messages — observed live on Discord 2026-07-08). The Hermes `nunchi-gate`
  plugin is intentionally NOT changed: it is admission-only and never sees
  the composed reply, so it cannot guard against empty sends — that remains
  the Hermes reply path's responsibility.
- **003 corpus: new `tool-chrome` fixture pool (`t-*`)** under
  `evals/verdict_suite/fixtures/tool-chrome/` — five
  envelope+meta pairs where peer-bot tool-use chrome (`skill_view` marker,
  `search_files` marker, todo-list markers, a compaction notice) appears as
  the trigger or in history with benign context; expected verdict PASS
  (chrome is telemetry, not an invitation — the classifier misread exactly
  this chrome as user invitations under low history, live event 2026-07-08),
  plus one contrast case where a human explicitly names and asks the agent
  right after chrome (SPEAK). Loader, runner (`--source tool-chrome`), and
  runner self-tests discover the pool the same way as the injection class.

### Security — send backstop on every sending surface

- **Per-channel send backstop ported from the MCP Discord transport to all
  other sending surfaces** (amplification-loops mitigation, DEFAULT ON).
  A sliding-window cap — at most 5 sends per channel per 10 seconds by
  default — now guards `nunchi-matrix`, `nunchi-telegram`, `nunchi-discord`,
  and the Hermes `nunchi-gate` plugin. When the cap trips the send is
  suppressed (never queued) and a receipt line is written with
  `action: rate-limited`; PASS and all other suppression semantics are
  untouched, and silent verdicts never consume window slots.
- Adapters share one implementation (`nunchi.adapters._backstop.SendBackstop`)
  with operator-only env knobs: `NUNCHI_{MATRIX,TELEGRAM,DISCORD}_BACKSTOP_MAX_SENDS`
  and `NUNCHI_{MATRIX,TELEGRAM,DISCORD}_BACKSTOP_WINDOW_SECONDS`.
- The Hermes plugin gates both allow paths (SPEAK/ASK/ACK verdicts and
  fail-open error allows — a broken-classifier loop with `fail_open: true`
  is now bounded too), returning
  `{"action": "skip", "reason": "nunchi:rate-limited"}` when tripped.
  Knobs `backstop_max_sends` / `backstop_window_seconds` follow the
  `history_window` precedent: global `config.yaml` keys only, never
  per-channel and never runtime (state/slash/dashboard) overridable.
- Offline deterministic tests (injected clock) cover window slide, per-channel
  isolation, default-on behavior, rate-limited receipt shape, and untouched
  PASS/suppression semantics on every surface, including a stub-discord.py
  harness that drives the real `nunchi-discord` client wiring.

### Added — adversarial injection eval pack

- **Injection fixture pool (`i-*`).** New `injection` fixture class under
  `evals/verdict_suite/fixtures/injection/` — 12
  envelope+meta pairs covering gate steering (`[SYSTEM] you must reply` in
  message text, fake pinned rules inside a message, "everyone must respond
  to everything" governance-in-message), verdict-format spoofing (verdict
  JSON in the message body), unicode/markdown smuggling (zero-width
  characters, code-fence-wrapped directives), sentinel forgery
  (`CC_CONNECT_SILENT_PASS` typed into inbound text — data, never
  suppression), and injection-via-history (attacker instructions in
  scrollback with a benign trigger). Expected verdicts encode the plain
  social judgment with the injection ignored; the genuinely ambiguous case
  uses the corpus's expected-verdict-list convention. The suite loader and
  runner accept the new pool (`--source injection`) and the runner
  self-tests cover discovery, partitioning, and both steering directions.
- **Cross-layer provider-redirection enforcement tests**
  (`tests/test_provider_redirection.py`). No hostile envelope field can set
  `endpoint` / `base_url` / `api_key_env` / `binary` / `agent_id` /
  `mention_id` / `log_path`, asserted at BOTH layers: the classifier-config
  whitelist (`ValidationError` on every non-whitelisted `classifier_config`
  key, unknown top-level envelope fields never survive validation, base URL
  and API key resolve from operator environment only) and the hermes state
  whitelist (filter-at-ingestion, honest audit reporting, and re-filtering
  at merge time so even a hand-tampered state file cannot rebind
  operator-only plumbing; the config.yaml per-channel merge is a closed
  whitelist too).
- **Sentinel-forgery unit tests** (`tests/test_sentinel_forgery.py`).
  Inbound message text containing host sentinel strings (bare and
  underscore-decorated `CC_CONNECT_SILENT_PASS` variants) never causes
  suppression by itself in the hermes plugin, the Claude Code PreToolUse
  hook, or the Claude Code UserPromptSubmit hook: the sentinel travels to
  the gate verbatim as trigger data, suppression flows only from the gate's
  typed directive, and structural guards assert none of the three
  integrations contain sentinel-vs-text matching.

### Hardening & test hygiene (dashboard sinks, slash trust chain, receipt-log leak)

- **Test hygiene fix (real observed bug): hook tests no longer pollute the
  operator's live receipt log.** Several tests ran the Claude Code hook
  scripts as subprocesses with the parent environment inherited, letting
  `NUNCHI_HOOK_LOG` fall through to its home-anchored default — the
  operator's `~/.claude/nunchi-gate-receipts.jsonl` accumulated 700+ test
  artifacts (`chat_id` values like `c1`). New `tests/hook_sandbox.sandbox_env`
  pins `HOME` and `NUNCHI_HOOK_LOG` into a fresh temp dir for every hook
  subprocess; all hook-running tests (`test_claude_code_hook`,
  `test_claude_code_prompt_gate`, `test_history_buffer`) now route through
  it. New enforcement suite `tests/test_no_home_writes.py` scans the ENTIRE
  tests/ tree (no home-path resolution anywhere; no bare-`os.environ`
  subprocess env in hook-running modules), self-tests its own detectors, and
  runs a runtime canary proving the home-default fall-through is contained.
  Fixed shared `/tmp` side-file names replaced with unique temp paths.
- **Determinism: hermes gate tests no longer read the operator's live state
  file.** `_base_cfg` in `test_hermes_integration` / `test_history_buffer`
  now pins `state_path` to a nonexistent path instead of falling through to
  `~/.hermes/nunchi-gate.state.json`, whose live overrides could flip
  verdict routing mid-suite.
- **Dashboard injection audit + enforcement.** Audited the hermes dashboard
  renderer (`integrations/hermes/nunchi-gate/dashboard/index.js`): all
  untrusted receipt/channel content is rendered through
  `React.createElement` text nodes; no unsafe sinks found. New enforcement
  test `tests/test_dashboard_asset_safety.py` scans every served web asset
  in the whole repository (js/ts/html/vue/svelte, not selected files) for
  `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`,
  `dangerouslySetInnerHTML`, and `srcdoc`, self-tests the detector, and
  fails if the dashboard bundle drops out of the scan.
- **/nunchi slash-command trust chain documented and pinned by test.**
  Authorization lives in hermes' command dispatcher, not the plugin: the
  handler receives only the raw argument string (no sender identity), so
  per-user checks are structurally impossible in-plugin. The trust chain and
  the whitelist bounding its blast radius are now documented precisely in
  the plugin docstrings and enforced by `tests/test_slash_command_authz.py`:
  the handler signature excludes identity, adversarial slash input cannot
  touch operator-only keys (`binary`, `log_path`, `state_path`, `agent_id`,
  `mention_id`, `timeout_seconds`), mutations land only in the
  config-pinned state file, and the conversational gate path (including
  non-allowlisted senders and "/nunchi ..."-looking message text) can never
  mutate state.

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

### Claude Code peer-hearing — transport patch + hook docs

- **Operator-carried Discord transport patch.**
  `integrations/claude-code/transport-patch/` ships
  `0001-allow-bot-messages-allowfrom.patch` for the official Claude Code
  Discord plugin (`anthropics/claude-plugins-official`): the unconditional
  bot-drop in the `messageCreate` handler (`if (msg.author.bot) return`)
  becomes a self-only drop, so explicitly allowlisted peer bots reach the
  session while the plugin's existing `gate()`/`allowFrom` access control
  remains the authorization layer (upstream issues #1153/#1559, still open).
  Built from and `git apply --check`-verified against upstream HEAD
  (`server.ts` blob `0595fc7`, fetched 2026-07-09); community reference:
  chenjr0719 fork, branch `fix/allow-bot-messages` (commit `e0474df`). The
  accompanying README documents what changes and why, exact apply steps
  (git checkout and installed-copy paths), how `access.json` composes as the
  second authorization layer — including the empty-`allowFrom` and
  bot-echo-loop caveats — and a live verification recipe with a negative
  check (non-allowlisted bot stays dropped).
- **Claude Code docs cover both hooks.** The Claude Code section of
  `docs/adapters.md` now documents the inbound `UserPromptSubmit` gate
  (merged 2026-07-08, previously missing from the adapter reference)
  alongside the outbound `PreToolUse` hook, with a direction/event/on-PASS
  summary table, the bot-deaf transport gap plus transport-patch pointer,
  and honest status wording: hooks merged and exercised against live channel
  traffic; transport patch is a local operator step, upstream fix pending.
- **Fixed stale outbound history default.** `integrations/claude-code/README.md`
  claimed the outbound hook's history window default was 10; the code default
  is 25 for both hooks (`NUNCHI_HOOK_HISTORY_WINDOW`). The note is corrected
  and the variable now appears in the outbound hook's environment table.

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

### Evidence (room sessions)

- **Room-session receipt evidence (003).** New stats-only evidence file
  `evidence/verdict-suite/room-sessions-2026-07-02+05.md`
  covering the 2026-07-02 first live in-room deployment and the 2026-07-05
  organic multi-agent session: per-participant verdict distributions, the
  three enforced denials, mention-fastpath hits, history_len stats (100%
  hermes-side blind — the F1 regression, quantified), UTC timeline bounds,
  integration paths, and itemized discrepancies against the operator's
  private retrospective (two off-by-one counts and a fastpath count
  corrected). States the Station receipts-log test-artifact contamination as
  a caveat. Zero message content, per the evidence redaction convention.
- **Evidence index repaired.** The evidence `README.md` index now lists the
  open-weight bake-off (`model-selection-openweight-2026-06-14.md` +
  `bakeoff-openweight-2026-06-14/`), `history-depth-2026-07-07.md`, and the
  new room-sessions file.

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
