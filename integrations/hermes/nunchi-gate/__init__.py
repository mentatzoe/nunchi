"""Hermes 0.19.0 entrypoint for the Nunchi V2 integration.

This module intentionally contains only the V2 loader and host configuration
adapter. Retired admission-verdict, command, and quiet-room implementations are
not part of the installed product surface.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any


_PLUGIN_DIR = Path(__file__).resolve().parent


def _load_v2_plugin():
    name = "nunchi_hermes_v2_plugin"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = _PLUGIN_DIR / "v2_plugin.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("Hermes V2 plugin module is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_v2_plugin = _load_v2_plugin()


def _load_config() -> dict[str, Any]:
    try:
        module = importlib.import_module("hermes_cli.config")
        loaded = module.load_config()
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _nunchi_config() -> dict[str, Any]:
    config = _load_config().get("nunchi")
    return dict(config) if isinstance(config, dict) else {}


def _platform_name(source: Any) -> str:
    platform = getattr(source, "platform", None)
    value = getattr(platform, "value", platform)
    return value.strip().lower() if isinstance(value, str) else ""


def _streaming_enabled(full_config: dict[str, Any], platform: str) -> bool:
    try:
        display_module = importlib.import_module("gateway.display_config")
        resolved = display_module.resolve_display_setting(
            full_config, platform, "streaming"
        )
    except Exception:
        resolved = None
    if resolved is not None:
        return resolved if type(resolved) is bool else True
    raw = full_config.get("streaming", {})
    if type(raw) is bool:
        return raw
    if not isinstance(raw, dict):
        return True
    enabled = raw.get("enabled", False)
    transport = raw.get("transport", "auto")
    if type(enabled) is not bool or not isinstance(transport, str):
        return True
    return enabled and transport.strip().lower() != "off"


def register(ctx: Any) -> None:
    initial_config = _nunchi_config()
    configured_participant = initial_config.get("participant_id")
    env_participant = os.environ.get("NUNCHI_HERMES_PARTICIPANT_ID")
    participant_id = (
        configured_participant.strip()
        if isinstance(configured_participant, str) and configured_participant.strip()
        else env_participant.strip()
        if isinstance(env_participant, str) and env_participant.strip()
        else "hermes"
    )

    def resolved_profile_config(source: Any, gateway: Any) -> dict[str, Any]:
        config = _nunchi_config()
        full_config = _load_config()
        config["_host_streaming_disabled"] = not _streaming_enabled(
            full_config, _platform_name(source)
        )
        model_config = full_config.get("model")
        openai_runtime = (
            model_config.get("openai_runtime", "").strip().lower()
            if isinstance(model_config, dict)
            and isinstance(model_config.get("openai_runtime", ""), str)
            else ""
        )
        proxy_resolver = getattr(gateway, "_get_proxy_url", None)
        try:
            proxy_url = proxy_resolver() if callable(proxy_resolver) else None
        except Exception:
            proxy_url = "unknown"
        config["_host_effect_runtime_supported"] = (
            openai_runtime != "codex_app_server" and not proxy_url
        )
        return config

    def profile_config(event: Any, gateway: Any) -> dict[str, Any]:
        source = getattr(event, "source", None)
        resolve_home = getattr(gateway, "_resolve_profile_home_for_source", None)
        profile_home = resolve_home(source) if callable(resolve_home) else None
        if profile_home:
            try:
                run_module = importlib.import_module("gateway.run")
                profile_scope = getattr(run_module, "_profile_runtime_scope")
                with profile_scope(profile_home):
                    return resolved_profile_config(source, gateway)
            except Exception:
                return {}
        return resolved_profile_config(source, gateway)

    def schedule_redispatch(event: Any, gateway: Any) -> None:
        source = getattr(event, "source", None)
        adapter_for_source = getattr(gateway, "_adapter_for_source", None)
        adapter = adapter_for_source(source) if callable(adapter_for_source) else None
        handle_message = getattr(adapter, "handle_message", None)
        if not callable(handle_message):
            raise RuntimeError("Hermes adapter redispatch seam is unavailable")
        session_resolver = getattr(gateway, "_session_key_for_source", None)
        resolved_session = session_resolver(source) if callable(session_resolver) else None
        if not isinstance(resolved_session, str) or not resolved_session:
            raise RuntimeError("Hermes redispatch session is unavailable")
        loop = asyncio.get_running_loop()

        async def owned_redispatch() -> None:
            try:
                accepted = await handle_message(event)
                if accepted is False:
                    await asyncio.to_thread(
                        _v2_plugin._CONTROLLER.abort_participant_turn,
                        resolved_session,
                    )
            except BaseException:
                await asyncio.to_thread(
                    _v2_plugin._CONTROLLER.abort_participant_turn,
                    resolved_session,
                )
                raise

        task = loop.create_task(owned_redispatch())
        background = getattr(adapter, "_background_tasks", None)
        if isinstance(background, set):
            background.add(task)
            task.add_done_callback(background.discard)

    _v2_plugin.configure(
        config_loader=profile_config,
        participant_id=participant_id,
        schedule_redispatch=schedule_redispatch,
    )
    _v2_plugin.register(ctx)


__all__ = ["register"]
