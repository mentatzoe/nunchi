# Normal Hermes turn on untouched installed hosts

Run records for `tests/v2/test_hermes_normal_turn.py`
(`NUNCHI_REQUIRE_HERMES_NORMAL_TURN=1`). Each lane builds a stock Hermes the
official way, installs Nunchi as a non-editable wheel, copies the `tests/`
tree into a scratch harness and runs it with `python -I` so no source
checkout is importable. Each probe drives the installed `GatewayRunner` and
the shipped `plugins/platforms/discord/adapter.py` with a loopback
OpenAI-compatible model double (SSE) and a fake `discord.py` client. No real
credentials: the Discord token is a placeholder string.

| lane | host | Python | install | Nunchi | result |
|---|---|---|---|---|---|
| minimum | hermes-agent 0.19.0 | 3.11 | `uv pip install "hermes-agent[messaging] @ file://…"` (non-editable wheel) | 2.0.0 wheel from `49d3db5` + this branch | 20 probes: 16 pass, 4 recorded product baselines |
| current | hermes-agent 0.21.5 | 3.13 | installer path: `uv sync --locked` (editable) | same | 6/6 stock probes pass; every Nunchi probe fails at plugin load |

## What passes on both hosts (stock baseline, Nunchi absent)

`StockHermesNormalTurnBaseline`: allowlisted human turn reaches the model
once and is delivered through the native `channel.send`; unauthorised human
and peer bot are dropped before the model (`DISCORD_ALLOWED_USERS`, default
`allow_bots: none`); `read_file` runs through the native dispatcher; a
dangerous `terminal` call parks in native approval until `/approve`
(0.21.5 phrases the prompt "needs your OK"), and `/deny` returns a blocked
result the model can see. The session guard is released after each turn.

## Recorded product baselines (0.19.0, Nunchi loaded)

Each is asserted by a probe whose failure message names the mechanism; the
log line is the evidence.

1. **Default install cannot run the attention model.** Stock `PluginLlm`
   refuses provider/model overrides unless the operator sets
   `plugins.entries.nunchi.llm.allow_provider_override` /
   `allow_model_override`. Nunchi's attention call then fails with
   `provider-failure` and the room degrades to `ERROR_FALLBACK` (wake).
   Probe: `NunchiDefaultInstallTrustGate`. With the flags set (every other
   Nunchi probe), the attention call reaches the model double.
2. **Configured routes blanket-deny every Hermes tool.** On 0.19.0 Nunchi
   answers every tool call with "Nunchi blocks Hermes tools on configured
   routes because Hermes 0.19.0 has no final-effect hook after approval",
   so neither `read_file` nor the native approval round trip is reachable in
   a Nunchi room. Probes: `test_ordinary_tool_on_configured_route`,
   `test_native_approval_control_on_configured_route`.
3. **Stock session guard leaks after a Nunchi-wrapped turn.** The lifecycle
   shim runs stock `_process_message_background` inside a child task;
   stock's cleanup (`gateway/platforms/base.py`, 0.19.0 ~L5570) only
   releases `_active_sessions[key]` when `asyncio.current_task()` is the
   task it registered, so the guard stays held and the next message in that
   room takes the busy branch. Probe:
   `test_stock_session_guard_released_after_configured_turn`. The harness
   therefore settles on `_session_tasks`, not `_active_sessions`.

## Recorded product baseline (0.21.5)

4. **`register()` deadlocks under the stock plugin loader.** 0.21.x runs
   each plugin's `register()` on a deadline worker that holds
   `PluginManager._discovery_lock`; Nunchi's
   `_active_discord_adapter_class()` calls `platform_registry.get("discord")`,
   which runs the deferred Discord platform loader, which re-acquires that
   lock from the same worker. Stock reports `load timed out after 10s
   (import + register() never returned)` and leaves Nunchi disabled. Every
   Nunchi probe on this host fails at that assertion; the traceback captured
   with `faulthandler` is in the task thread for t_44229f49.

Logs: `hermes-0.19.0-2026-10-01.log`, `hermes-0.21.5-2026-10-01.log`
(`$WS` = the task workspace; noise lines removed).
