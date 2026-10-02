# Loader deadlock and session ownership — 2 October 2026

This repairs two installed-host bugs on owner checkpoint `333fe8b`. It is not
completed V2. No stock Hermes file, shared probe environment, or live gateway
was changed.

## What changed

- Discord resolution no longer calls `platform_registry.get()` during
  `register()`. That call ran the deferred loader, which re-enters
  `PluginManager._discovery_lock` on Hermes 0.21.5.
- A pending Discord loader is replaced by the shipped registration from the
  already-imported `plugins/platforms/discord/adapter.py`. Later `get()`
  instantiates that class, so the shims and the live adapter are the same
  object. The loader itself is not called.
- Hermes 0.19.0's `_build_adapter` and the installed
  `hermes_plugins.discord_platform` / `hermes_plugins.platforms__discord`
  loads of that same file are shipped. A class from any other module still
  fails closed.
- The deadline child is named in `_session_tasks` before stock processing
  runs, so stock releases `_active_sessions` for that child and does not
  release a newer task's guard.

## Installed proof

Disposable copies only. Shared `t_44229f49` environments were not written.
Wheel: `nunchi-2.0.0-py3-none-any.whl`.
SHA256: `70f37e82e992c9bbc3a7e4397b7281c4fd4945cc203efecad38dc6d10555357a`.
Both installs are non-editable (`archive_info.hash`, no `dir_info.editable`).

| Lane | Host | Result |
| --- | --- | --- |
| minimum | Hermes 0.19.0, Python 3.11 | 17 pass, 3 fail |
| current | Hermes 0.21.5, Python 3.13 | 13 pass, 7 fail |

Minimum session-guard, plugin load, admitted turn, peer admission, and
unconfigured fall-through pass. Register no longer deadlocks on either lane
(`test_plugin_loaded_and_shims_installed` passes, and the suite finishes).

Remaining failures are outside this repair:

- Default-install attention still returns `provider-failure` instead of `{}`
  on both lanes. That is the recorded trust-gate baseline.
- Configured-route tools still hit the 0.19.0 blanket denial. Native
  invocation and approval are the owner's separate checkpoint, not this diff.
- Current delivery raises `_StockEffectBlocked: Hermes _send_final_text
  target does not match the active Nunchi room`. Stock 0.21.5
  `_send_final_text` takes `(event, session_key, text_content, metadata, ...)`.
  The existing effect resolver treats `args[0]` as a chat id, so the
  MessageEvent does not match the room. That check is not the adapter
  resolver or the deadline wrapper. It blocks the current session-guard
  assertion before ownership can be observed. Minimum, which has no
  `_send_final_text`, releases the guard.

## Local verification

- `python3 -m unittest tests.v2.test_hermes_loader_session -v` — 16 tests, OK.
- `python3 -m unittest` — 657 tests, OK, 4 skipped.
- `python3 -m evals.verdict_suite.runner --list` — exit 0.
