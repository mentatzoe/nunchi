# Repeatable stock-Hermes verification

This verifier exercises an installed Nunchi wheel on untouched stock Hermes.
It is deterministic installed-runtime evidence, not authenticated provider or
platform delivery, release readiness, running-profile adoption, or complete V2.
The remaining typing, voice/media, detached-command, native event, other-platform
and live acceptance requirements in `v2-completion-goal.md` remain required.

## What runs

`scripts/verify_stock_hermes.py` is the public entry point. Select `--lane`
multiple times; each lane runs in a separate isolated interpreter and fresh home.

| Lane | Required tests | Boundary exercised |
|---|---:|---|
| `contract` | 4 | Installed discovery, registry rollback, platform host contract; Discord or Telegram |
| `normal-attention` | 32 | Stock Discord admission, normal participant turn, native read-file dispatch, native approval/denial, ACK/silence, attention Save/WAKE/SUPPRESS/revocation |
| `startup-single` | 1 | Real single-profile startup, adapter ownership, native connect budgets and reconnect |
| `startup-multiplex` | 1 | Real two-profile startup and profile-owned reconnect |

Normal/startup lanes are Discord-only. Telegram contract proof does not imply
Telegram normal-turn proof. Zero tests, skips, errors, failures, wrong counts,
external socket attempts, incorrect import origins or changed host/package bytes
fail the verifier. A failing lane does not prevent the other selected lanes
from running. Do not mark the canary optional or skip failing cases to get green.

The model is an OpenAI-compatible loopback SSE fixture. The Discord client
captures native output; it does not authenticate to Discord. Stock dispatch,
participant execution and native approval are not replaced. Optional remote model
metadata and Tirith binary acquisition are explicit doubles, recorded by name;
security scanning/approval are not mocked. Main moved acquisition to PM, so its
optional `_background_install` replaces the older `_download_file` double.
Startup also doubles network connection and unrelated perpetual/warm-up services;
the exact list is visible in `tests/v2/test_hermes_startup_installed.py`.

## Prepare private environments

Use a disposable working directory, not an active Hermes environment. Installation
requires package/Git network access; deterministic probes do not. No real provider
or platform credentials are needed. Use Python 3.11 for the pinned releases and
3.14 for moving main. Preserve full Git history/tags for source-version provenance.

The workflow `.github/workflows/hermes-host-contract.yml` contains the exact
CI installation commands. Equivalent local commands, from a clean Nunchi clone:

```sh
REPO="$PWD"
WORK="$(mktemp -d)"
python3.11 -m venv "$WORK/build"
"$WORK/build/bin/python" -m pip wheel --no-deps "$REPO" -w "$WORK/nunchi-wheels"
git clone https://github.com/NousResearch/hermes-agent.git "$WORK/stock-hermes"
# Pick exactly one target:
REF=3ef6bbd201263d354fd83ec55b3c306ded2eb72a  # RELEASE 0.19.0
# REF=f97608f178d1ffeca59860195ab7da295f7c8e5f # RELEASE 0.21.5
# REF=main                                # moving canary, NOT a release

git -C "$WORK/stock-hermes" checkout --detach "$REF"
git -C "$WORK/stock-hermes" rev-parse HEAD
python3.11 -m venv "$WORK/host"              # python3.14 for main
PYTHON="$WORK/host/bin/python"
"$PYTHON" -m pip install "$WORK"/nunchi-wheels/*.whl jsonschema==4.26.0
```

For minimum 0.19.0, build its real released-source wheel and install it:

```sh
"$PYTHON" -m pip wheel --no-deps "$WORK/stock-hermes" -w "$WORK/host-wheels"
HOST_WHEEL="$(printf '%s\n' "$WORK"/host-wheels/*.whl)"
"$PYTHON" -m pip install "${HOST_WHEEL}[messaging]"
MODE=wheel
```

For 0.21.5 or main, use upstream's supported source-install layout:

```sh
"$PYTHON" -m pip install -e "$WORK/stock-hermes[messaging]"
MODE=source
```

Newer Hermes deliberately rejects generic wheels. Do not use a Nix build bypass,
fabricated metadata, source modifications or an old editable finder pointing at
someone else's checkout. Nunchi itself is always a noneditable wheel. If using a
uv-created environment without pip, install with `uv pip --python "$PYTHON"`
instead; the verification script itself does not require pip.

## Run the same invocation as CI

```sh
"$PYTHON" -m pip check
"$PYTHON" "$REPO/scripts/verify_stock_hermes.py" \
  --hermes-source "$WORK/stock-hermes" --host-mode "$MODE" --host-ref "$REF" \
  --nunchi-wheel "$WORK"/nunchi-wheels/*.whl --platform discord \
  --lane contract --lane normal-attention \
  --lane startup-single --lane startup-multiplex --output "$WORK/discord-receipts"
"$PYTHON" "$REPO/scripts/verify_stock_hermes.py" \
  --hermes-source "$WORK/stock-hermes" --host-mode "$MODE" --host-ref "$REF" \
  --nunchi-wheel "$WORK"/nunchi-wheels/*.whl --platform telegram \
  --lane contract --output "$WORK/telegram-receipts"
```

Output directories must be new, so reruns cannot overwrite earlier receipts.
The parent copies tests and the private child runner, never product source, to a
temporary directory. Children use `-I -B`, a fixed environment allowlist and fresh
HOME/HERMES_HOME; PYTHONPATH and operator credentials are not inherited. Import
origins are asserted before and after dispatch. Python audit hooks reject external
DNS, TCP and UDP operations, even if host code catches the exception; the denied
attempt remains a lane failure. Numeric loopback and local Unix sockets are
allowed. This is an in-process test fence, not a general OS sandbox for arbitrary
untrusted subprocesses; these fixtures do not approve terminal execution.

Receipts include commands, UTC timestamps, interpreter, requested host ref and
resolved commit/tree, installed versions/dependencies, direct-install metadata,
Nunchi wheel SHA-256, source/wheel/installed payload comparisons, host tracked-file
hashes and installed RECORD-verified hashes before/after, test counts, explicit
doubles and raw logs. A timeout or setup failure is a failure, never a pass.
Independent builds may differ in wheel digest; only compare exact bytes when the
digest is actually reproduced.

The six existing host/platform CI jobs remain. Discord jobs additionally execute
normal/startup lanes, and `always()` uploads retain failed diagnostics. Offline CI
also runs on `integration/v2` pushes. No remote CI execution is implied by local
CI-shaped commands; publication and GitHub CI consumption belong to the owner.

## Current canary finding (2 October 2026)

Minimum and release probes pass locally. At main commit
`1af98f58baed50c9e09bca5555596780c91a62e9`, Python 3.14 and actual declared
`ruamel.yaml` replace PyYAML. Fixtures now use the host's real `hermes_yaml` API,
falling back to PyYAML only when that host module does not exist. Placeholder
`0.0.0` metadata is compared against the official host source-version API, not
rewritten or treated as a released host.

This exposes a production blocker: `hermes_attention_trust._read_host_config`
still imports `yaml` for ordinary YAML config. Five normal-attention Save cases
fail with `ModuleNotFoundError` wrapped in `ValidationError`. Do not add PyYAML
only to CI, write JSON instead to evade the failing path, or mock the Save reader.
The canary remains visibly failing pending an owner-routed production repair.
Contract and startup checks are separate evidence, not substitutes for that gap.

## Recovery and rollback

Nothing is installed into a live profile. Preserve receipts and the frozen wheel;
discard only the disposable environments after review. Recreate an environment
from the same host commit and wheel for a clean retry. To withdraw this CI change,
the owner can revert its ordinary source commit; no runtime/data migration or
gateway restart is involved. Package uninstall, V1 migration and live rollback
are separate operator-lifecycle work, not proved by this verifier.
