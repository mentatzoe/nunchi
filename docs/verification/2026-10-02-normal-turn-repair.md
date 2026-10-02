# Installed Hermes normal-turn repair

Implemented and verified the named admission, attention-diagnostic and final-delivery repairs on stock Hermes 0.19.0 and release 0.21.5. This is not whole-V2 readiness or live adoption: canonical verification has an inherited failure, and separate startup coverage needs repair. Independent exact-artifact review remains required.

## Changes

- Recognise MessageEvent destinations only for `_send_final_text` and `send_final_ledgered`. Require the adapter platform and event platform to agree, and event thread and delivery metadata to agree. Existing room/opportunity/cancellation checks remain authoritative.
- Recognise the two stock final-wrapper delegation edges so the chain counts one actual delivery rather than multiple wrapper effects.
- Resolve the explicitly single-profile normal-turn fixture's `multiplex_profiles` setting. Real `GatewayRunner.start()` resolves this tri-state setting; bypassing start had left it `None`, falsely failing peer/unmentioned admission. No production admission relaxation.
- Preserve `host-permission-denied`, actionable Save/restart guidance and fail-open WAKE assertions. Add actual dashboard-store Save, plugin/runner restart, selected-model attention and final-sent receipt coverage without manually rewriting trust after Save.
- Match real Save's private fixture directory permissions. Publish native deferred platform ownership via discovery before the installed-contract test injects its exact command-registry failure; rollback checks are not relaxed.
- Add narrow Discord/Telegram target tests: wrong room/platform/thread, missing topic metadata, malformed event, absent opportunity and cancelled authority all block; the valid wrapper chain sends once. Add installed self-bot denial and strengthen SUPPRESS checks.

## Exact environment and evidence

Implementation base: `53cae9c59814936df79aaba04e33dd1bcd65aab6`.
Author runtime: `openai-codex / gpt-6-astra` (not the profile's xAI label).
Workspace: `/Users/zmll/.hermes/kanban/boards/nunchi-v2/workspaces/t_4a3fab4d`.

Hosts are independent of the owner's environments. Minimum is a noneditable host wheel built from the authorised minimum source archive, CPython 3.11.15. Release is the public `v2026.9.24` archive, Hermes 0.21.5, installed using `uv sync --locked --python 3.13 --extra messaging`. Local Git archive-baseline commits establish integrity, not upstream Git identity.

Release archive SHA256: `15b15ce4e6ec8ea424a081823709d1e17f0943e7b42b59597d24ebb94cbd1742`.
Wheel: `artifacts/final/nunchi-2.0.0-py3-none-any.whl`.
Wheel SHA256: `01636ce06260a4ce0dfe7e50d0c762d39f8dcb356d696c4b5fcb7c96b76bc02a`.

`run_probe.py` stages tests only outside the checkout, runs the installed host interpreter with `-I`, uses an environment allowlist and disposable HOME/HERMES_HOME, and rejects skipped tests. Platform SDK and model-server doubles are explicit; real host plugin discovery, native agent/tools/approvals, admission, lifecycle, delivery and receipts execute. No authenticated platform or external model run is claimed. `verify_artifact.py` checks noneditable origins, exact installed wheel member bytes and host RECORD hashes. The contract verifier checks host source/distribution integrity before and after.

## Results

All log paths below are relative to workspace `evidence/`.

- RED: `red-minimum.txt` and `red-release.txt` reproduce the original diagnostic, admission and final-delivery failures; `red-contract-minimum.txt` reproduces the early owner-publication failure.
- Target regression: `red-event-target.txt` is the initial environment/import failure, not behavioural RED. The release normal-turn RED above establishes the real delivery defect. `green-event-target.txt` verifies focused boundaries; `final-focused.txt` records portable plus new boundary coverage.
- Final installed minimum: `final-minimum.txt`, 32/32 pass, zero skips.
- Final installed release: `final-release-repeat.txt`, 32/32 pass, zero skips. The first final run (`final-release.txt`) had one native-tool model-call-count failure (expected 2, observed 3); the repeat passed. Retained as a reliability finding, not hidden.
- Final contracts: `final-contract-{minimum,release}-{discord,telegram}/receipt.json`, four runs of 4/4, zero skips, unchanged host integrity. These are discovery/contract probes, not Telegram full normal-turn proof.
- Full canonical: `final-canonical.txt`, 761 tests, 29 opt-in skips, one failure in `test_persistent_contention_fails_closed_and_keeps_existing_claim` (elapsed time exceeds two seconds). The exact unmodified base also fails: `baseline-canonical.txt`, 760 tests, 29 skips, same assertion at 2.577s. Standalone baseline journal tests pass (`baseline-journal.txt`). No journal code or timing assertion was changed; this remains unresolved.
- `eval-list.txt`: all 11 V2 lifecycle scenarios listed. No live model evaluation was run.
- `git diff --check` passes.

Public main was recorded separately at `4e3fcd5cd7e40c37cb6f9a21a76fc57a7361957a`, archive SHA256 `16bdaa96c94e73c7a6c6bec198fe3d200c86a7ddb738e7ae398ca086a39be554`. It reports version 0.0.0 and uses Python 3.14.3. Its clean locked install no longer provides PyYAML: the existing normal-turn fixture fails importing `yaml` before any host turn (`main-normal.txt`). Main is unverified, not substituted for the supported release.

## Follow-up boundaries

Code inspection also found the existing plugin `connect_adapter_with_timeout` shim lacks stock release's `initial` keyword (`gateway/run_adapters.py:164`); the normal-turn fixture constructs a runner without full startup. That startup path needs its own reproducer/repair, not a claim that these turn probes cover startup.

Owner retains integration, CI, publication, merge and live adoption. No stock source, owner environment, live profile/configuration, credentials or gateway was changed. Archive integrity baselines remain clean. Separate follow-up work must address the canonical timing failure and startup gap before whole-product readiness.
