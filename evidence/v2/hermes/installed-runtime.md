# Installed Hermes provenance — pre-activation draft review 2026-07-22

## Inspected source

- Installed Hermes path: `/Users/zmll/.hermes/hermes-agent`
- Installed Hermes version: `0.19.0`
- Installed Hermes commit: `279be8211d8347cc3500b9a78c6a0f8cb4d92a6a`
- Candidate base: `8e64746970f9910d03b372291c5aa173883e869f`
- Tracked source status before and after verification: clean
- Full untracked status: only the acknowledged `.install_method` installer
  marker; every other untracked path is verifier-fatal

No draft file was copied into the installed checkout. No package was
installed into the production venv. No gateway/profile/runtime configuration
was changed, and no service was restarted.

## Disposable verification method

Installed tests ran with the production checkout's interpreter and an isolated
temporary `PYTHONPATH` containing only `pytest` and `pytest-asyncio` installed
by `uv`. The temporary directory was deleted after the run. The command used
`PYTHONDONTWRITEBYTECODE=1`, disabled pytest's cache provider, and cleared
Discord/Telegram credential and allowlist environment variables.

## Fresh results

The current related private-seam suite contains 83 cases across:

- `tests/gateway/test_session_race_guard.py`
- `tests/gateway/test_pending_drain_race.py`
- `tests/gateway/test_pending_drain_no_recursion.py`
- `tests/gateway/test_discord_roles_dm_scope.py`
- `tests/gateway/test_discord_slash_auth.py`

The exact isolated run completed `83 passed in 10.81s`.

HM-06 separately loaded the draft with the installed production interpreter. A
direct installed-class registration probe forced a late Telegram-wrapper failure
and proved every host class patch was restored. Separate probes instantiated the
installed `PluginManager`, `PluginContext`, and `PluginManifest`; through the
installed `_load_plugin` catch path they forced after-append second-hook and
middleware failures and proved each registry dictionary, every pre-existing
target-name callback-list object, and its exact ordered sentinel contents were
restored with zero Nunchi callbacks. Successful loading then registered exactly
two hooks and one tool middleware before HM-06 exercised the installed
`_run_execution_chain` contract in both directions: a forced Nunchi
authorization-sink failure remained terminal without invoking the privileged
executor, while a native downstream executor failure propagated with its
original `RuntimeError` semantics after exactly one call.

This pre-activation draft does not claim a canonical candidate, handoff, or
installed runtime cutover.
