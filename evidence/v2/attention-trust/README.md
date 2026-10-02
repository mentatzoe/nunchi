# Attention trust setup repair — candidate, not V2 completion

Task: nunchi-v2:t_ecc91269; owner: t_7041b201. Base: `333fe8b` (includes reviewed `9158f0c`). Author runtime reported by this session: gpt-6-astra / openai-codex. Independent review remains required.

## Result

Explicit dashboard Save now configures stock Hermes's provider/model trust gate for the configured room attention routes. It does not drop the explicit participant-bound route, borrow the participant model, bypass host policy, or grant permissions from runtime attention. Missing permissions produce a safe `host-permission-denied` receipt with actionable setting names, not generic `provider-failure`. Dashboard readiness is explicitly saved-configuration readiness, not credential/quota or running-gateway health.

Final installed wheel: `5c9890b9f93e94166c3bcf2ec935ce9b42c5c8c505f1a07ff8415a38a170bbb5` (Nunchi 2.0.0). Wheel package files were compared against `src/nunchi`; no mismatches. No `hermes_v2.py` edit or proposed callsite hunk is needed for this repair.

## Changes and rollback

- `hermes_attention_trust.py`: explicit Save-owned transaction, exact configured provider/model allowlists, unrelated mapping preservation (including YAML alias separation), private content-addressed original-byte backup, staged publication/read-back and caught-exception rollback. Unsupported non-JSON YAML values fail closed. JSON output is valid YAML; original comments/format remain only in backup.
- Dashboard store enters that transaction after validating the pinned room config. A supplied `environ` without nonblank `HERMES_HOME` now fails before profile resolution or writes.
- Dashboard API and JS show trust prerequisite status and disclose the permission write in the Save action; unchanged room config can still repair missing trust.
- `attention.py` classifies host `PermissionError` without exposing raw exception text; configured provider/model and participant profile remain authoritative.
- Documentation explains permissions, readiness limits, backup/rollback and per-call effect. Runtime never changes trust; revoked permission stays revoked.

A caught Save error restores previous host bytes/absence unless another writer changed the file. Process termination is not a multi-file atomic transaction: a crash may leave the narrow grant, and repeating Save reconciles it. Manual rollback must preserve intervening edits and restore the matching host backup and pinned room config/digest. Backups may contain credentials and must never be uploaded. No gateway restart is included. Host trust is checked per call and can take effect before restart.

## Final execution evidence

All final tests used an allowlisted subprocess environment with disposable HOME and HERMES_HOME. Installed probes used `python -I`, no PYTHONPATH, a noneditable Nunchi wheel, real stock PluginLlm, and the existing t_44229f49 normal-turn fixtures with loopback model/fake Discord network boundaries. These are not live-provider or live-room acceptance.

| Check | Actual result |
|---|---|
| `python3 -m unittest -v tests.v2.test_hermes_attention_trust tests.v2.test_hermes_dashboard` | 54 tests, OK |
| `python3 -m unittest` | 654 tests, OK, 8 expected opt-in skips |
| `python3 -m evals.verdict_suite.runner --list` | exit 0, 11 V2 lifecycle scenarios |
| `node --check src/nunchi/integrations/hermes_dashboard_assets/index.js` | exit 0 |
| `git diff --check` | exit 0 |
| `uv pip check --python <minimum/current-env>/bin/python` | both compatible (82/83 installed packages) |
| Minimum stock Hermes 0.19.0 / Python3.11.15, native setup path | 3/3 pass, zero skips: exact attention WAKE + participant delivery, SUPPRESS without participant, revoked trust denied without runtime regrant |
| Minimum stock direct service sequence | 1/1 pass: default deny -> explicit Save -> exact attention model -> revoke -> deny |
| Current release stock Hermes 0.21.5 / Python3.13.7, direct service sequence | 1/1 pass, same sequence |
| Current release native entrypoint | 3/3 FAIL at existing PluginManager 10-second load timeout; no native attention success claimed |

The minimum host is installed in site-packages; current is the stock source-installed runtime in `stock/current`, not a fabricated host wheel. Their before/after integrity checks covered 943 and 7302 files respectively with zero changes. Exact aggregate hashes, timestamps, origins, commands, fixture hashes and exit statuses are in each `*-final/{receipt,invocation}.json`. The current archive has no local .git: a `git -C stock/current` lookup climbs into the unrelated Home repository and must not be used as host SHA evidence. These receipts identify the executing distribution and content manifest, not an independently recovered upstream commit identity.

The current loader failure is the already-reported sibling-owned `hermes_v2.py` loader issue, not a reason to weaken the gate or substitute a direct service test for a native pass. Owner must combine the reviewed loader repair and rerun this native lane. Full V2 remains incomplete.

Earlier runs and failures are retained: `canonical-serial.log` has 3 deadline-boundary failures, `canonical-final.log`/`canonical-unittest.log` retain previous attempts, and `deadline-diagnostic.log` records two targeted passes. No deadline assertions were changed here. Final canonical run passed without weakening them. UI and YAML-alias RED logs are retained, along with the isolation RED/GREEN sequence. Earlier wheel `3c135c771bd9272d0134035ed62d3cb12f8303f5ec66ac9ba571b2080b7b867a` is superseded by the final wheel above; earlier receipts are not final-candidate evidence.

## Safety incident discovered on retry

Do not describe the whole task as having left live configuration untouched. The first run timed out; on recovery, metadata-only inspection found three `~/.hermes/config.yaml.nunchi-backup-*` files created during that run. The original dashboard test fixture `_write_config` supplied Nunchi paths but omitted HERMES_HOME. The new Save transaction called `_hermes_home(environment)`, which selected `Path.home()/.hermes`. This indicates unintended live host-config writes by the tests.

Metadata-only mtimes (BST): suffixes `269e3cb5fe039c5aa82f9436aa50879833855b61840005915332a44b36c4e3a1` and `5cd1e2d0758372602d7a5ef124b0c074b625483f739cd3cc7ca99745e0d534e4` at 2026-10-02 14:52:37 +0100; suffix `76071c3a7df7a8b9be866346d0840d6efa9e270d96b6365fc5be3959917ce6b8` at 14:52:38. No backup/live config contents were inspected or uploaded during recovery. No restoration or restart was attempted. Exact value-level impact remains uninspected, not asserted harmless. Owner routed authorized recovery separately as t_8df36093.

Repair: both affected fixtures explicitly name HERMES_HOME; Save rejects missing home in an injected environment. Regression `test_injected_environment_without_home_cannot_select_real_profile` traps Path.home before host IO. RED proves the original ambient fallback; GREEN proves rejection before it. All subsequent checks use isolated HOME as a second boundary. The incidental live change is not accepted as deployment and still requires the separate operator incident disposition.

## Reproduce the installed checks

From this checkout with disposable stock minimum/current environments and the built wheel:

```
python3 scripts/verify_hermes_attention_setup.py \
  --python /absolute/disposable-env/bin/python \
  --harness-source evidence/v2/attention-trust/normal-turn-fixtures \
  --output /absolute/new-probe-directory \
  --wheel /absolute/nunchi-2.0.0-py3-none-any.whl
```

Add `--service-only` for the separate trust/service sequence. Runner does not install the wheel; install it first with `uv pip install --python ... --no-deps /absolute/wheel`. Do not run probes against a live environment. Never copy retained test homes or any host backups into evidence. `manifest.json` hashes the included allowlisted logs and fixture files; report and manifest itself are excluded from that manifest.

Review requested from developer-b on the exact candidate. Source is preserved as a git-format patch and bundle alongside this report so scratch cleanup cannot lose the repair. No GitHub writes, live gateway starts or restarts were performed.
