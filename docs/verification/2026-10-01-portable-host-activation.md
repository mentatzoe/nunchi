# Portable Hermes activation checkpoint — 1 October 2026

This is an integration checkpoint for #46, #42 and #50, not completed V2.
No live Hermes checkout, gateway or room was changed.

## What changed

- Native `/approve` and `/deny` pass through the authenticated, event/task-bound
  control route without attention scheduling and without cancelling the turn
  whose approval they control. `/stop`, `/new` and `/reset` still cancel it.
- Native outbound media guards also wrap inherited mixin methods at their
  defining class. This covers the current Discord media split, including
  `super()` dispatch; rollback restores the original attribute owners.
- Version resolution uses installed release metadata or verified official
  source-install provenance. An unverified `0.0.0` placeholder is not a version.
- Streaming silence compatibility recognises the current `_should_edit`
  helper only with its checked call edge, signature and module bindings.
- Streaming TTS compatibility recognises the current
  `_run_agent_start_streaming_tts` helper. Configured turns retain the existing
  whole-response TTS fallback; unconfigured native streaming remains intact.
- CI installs the plugin wheel and checks six host/platform combinations,
  retaining failure logs, package hashes and host integrity receipts.

These remain private, checked in-process adapters, not source edits. Unknown
shapes reject activation transactionally rather than dropping a platform or
silently skipping its checks.

## Exact installed artifact and evidence boundary

Product source: `49d3db5` on the isolated `wt/portable-v2-t_7041b201` branch.
Wheel: `nunchi-2.0.0-py3-none-any.whl`.
SHA256: `4510d1efcaf1b24c4e0ca83c4b41cb5302dd450c2aac5dcf557469320145d0db`.

| Stock host | Revision | Installation | Platforms |
| --- | --- | --- | --- |
| 0.19.0 / v2026.7.20 | `3ef6bbd201263d354fd83ec55b3c306ded2eb72a` | host wheel | Discord, Telegram |
| 0.21.5 / v2026.9.24 | `f97608f178d1ffeca59860195ab7da295f7c8e5f` | official source-installed layout | Discord, Telegram |
| Current main | `bd394e2a4bdf55fa2f14b0f6963d343049787f90` | official source-installed layout | Discord, Telegram |

DevOps card `t_becfea50` records four passing installed-contract tests without
skips in each lane, using this exact wheel. Its receipts identify module
origins, isolated homes and unchanged host source/distribution hashes.
Current-main official identity is `0.21.5+5346.gbd394e2`; no synthetic version
stamp was installed. These checks prove discovery, configured activation,
setup and transactional rollback. They do **not** prove authenticated normal
turns, ordinary native tools or ACK delivery.

New Hermes releases intentionally reject generic wheel builds. Their supported
source-installed runtime is distinguished from a plugin development checkout:
Nunchi itself must be a noneditable wheel, with no `PYTHONPATH` or our local
Hermes patches. Do not bypass upstream packaging with a fabricated Nix build
flag. `scripts/verify_stock_hermes.py` records `--host-mode source` versus
`--host-mode wheel` explicitly.

A disposable minimum-host uninstall/reinstall drill also passed: Nunchi's
package and entry point disappeared, stock Hermes remained importable, and
reinstallation restored the contract. That does not demonstrate unpatching an
already-running gateway; runtime adoption and process control remain separate.

## Verification commands

Run the unit suite with `python -m unittest`, not an unrestricted historical
V1 test discovery. `tests/__init__.py` defines the atomic V2 suite.

After installing the artifact into an isolated stock runtime, run its Python:

    python /path/to/nunchi/scripts/verify_stock_hermes.py \
      --hermes-source /path/to/untouched/stock-runtime \
      --host-mode source --platform discord --output /new/receipt-directory

Use `--host-mode wheel` for the minimum wheel installation, and repeat with
`--platform telegram`. The verifier creates a fresh environment/home, copies
only the test harness, removes inherited credentials and refuses editable
Nunchi imports. Its receipt explicitly marks normal authenticated turns as
not exercised.

The owner ran 102 focused portability/version tests successfully. A pre-existing
portable deadline probe was made deterministic after reproducing its failure
on baseline `ac8a5f7`: fsync latency could expire its tiny budget before the
intended cancellation-ignoring participant even started. Controlled clocks now
exercise the intended late-effect rejection. Separate shared-host deadline
fixture failures are being investigated in `t_ebd25bd4`; this checkpoint does
not claim the whole local suite is green.

## Still required before V2 delivery

- Replace blanket configured-route tool denial with durable exact invocation
  handoff and native authority/approval semantics. The native approval-wait
  cancellation race is under a separate exact-host probe, `t_a02587b7`.
- Complete the real native-turn harness in `t_44229f49`: authentication,
  human/peer routing, tool dispatch, cancellation, replay and final delivery.
- Wire authenticated native reaction capability and ACK delivery rather than
  calling conservative capability fallback complete acknowledgement support.
- Obtain fresh exact-artifact review, green integrated CI and land the agreed
  changes to `integration/v2`. Only then prepare the Maintenance-owned live
  adoption edge under its existing idle-room conditions.

Do not treat this checkpoint, an open PR, or a green host-shape matrix as the
requested usable V2 outcome.
