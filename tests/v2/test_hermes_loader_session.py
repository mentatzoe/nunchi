"""Focused repairs for the installed-host loader deadlock and session-owner leak.

Stock 0.21.5 runs ``register()`` on a worker that already holds
``PluginManager._discovery_lock``. Resolving Discord through
``platform_registry.get`` runs the deferred platform loader, which takes that
lock again. Stock 0.19.0 releases ``_active_sessions`` only when
``asyncio.current_task()`` is the task recorded in ``_session_tasks``. The
deadline wrapper used to run stock processing in a child the owner map did
not name, so the guard stayed held.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
import threading
import time
import types
import unittest
from dataclasses import dataclass
from unittest import mock

from nunchi.errors import ValidationError
from nunchi.integrations import hermes_v2


class _CancelToken:
    def __init__(self) -> None:
        self.cancel_event = asyncio.Event()


class _Scheduler:
    def __init__(self, current: bool = True) -> None:
        self._current = current

    def is_current(self, token: object) -> bool:
        del token
        return self._current


class _Runtime:
    def __init__(self) -> None:
        self.scheduler = _Scheduler()
        self.expired: list[object] = []
        self.detached: list[asyncio.Task[object]] = []

    def expire_stock_turn(self, trace: object) -> None:
        self.expired.append(trace)

    def track_detached_stock_task(self, task: asyncio.Task[object]) -> None:
        self.detached.append(task)


class _Trace:
    def __init__(self, *, deadline: float | None = None) -> None:
        self.token = _CancelToken()
        self.deadline = time.monotonic() + 30 if deadline is None else deadline


class _StockAdapter:
    """The ownership check stock uses, without importing Hermes."""

    def __init__(self) -> None:
        self._active_sessions: dict[str, asyncio.Event] = {}
        self._session_tasks: dict[str, asyncio.Task[object]] = {}
        self._expected_cancelled_tasks: set[asyncio.Task[object]] = set()
        self.released: list[str] = []

    def release_if_owner(self, session_key: str, guard: asyncio.Event) -> bool:
        current = asyncio.current_task()
        if current is None or self._session_tasks.get(session_key) is not current:
            return False
        if self._active_sessions.get(session_key) is not guard:
            return False
        del self._active_sessions[session_key]
        self._session_tasks.pop(session_key, None)
        self.released.append(session_key)
        return True


def _shipped_discord(name: str = "DiscordAdapter") -> type:
    return type(name, (), {})


def _install_shipped(adapter_class: type) -> dict[str, types.ModuleType]:
    modules = {
        "plugins": types.ModuleType("plugins"),
        "plugins.platforms": types.ModuleType("plugins.platforms"),
        "plugins.platforms.discord": types.ModuleType("plugins.platforms.discord"),
        "plugins.platforms.discord.adapter": types.ModuleType(
            "plugins.platforms.discord.adapter"
        ),
    }
    modules["plugins.platforms.discord.adapter"].DiscordAdapter = adapter_class
    return modules


def _registry_module(registry: object) -> dict[str, types.ModuleType]:
    gateway = types.ModuleType("gateway")
    registry_module = types.ModuleType("gateway.platform_registry")
    registry_module.platform_registry = registry
    gateway.platform_registry = registry_module
    return {"gateway": gateway, "gateway.platform_registry": registry_module}


class DiscordAdapterResolutionTests(unittest.TestCase):
    def test_deferred_loader_is_not_invoked_under_discovery(self) -> None:
        shipped = _shipped_discord()
        loaded = threading.Event()
        lock = threading.RLock()

        def loader() -> None:
            # The stock deferred loader re-enters the discovery lock. If this
            # resolver calls it, the same thread deadlocks or records a load.
            if not lock.acquire(blocking=False):
                raise AssertionError("deferred loader re-entered the discovery lock")
            lock.release()
            loaded.set()

        class Registry:
            def __init__(self) -> None:
                self.get_calls = 0

            def current_scope_key(self) -> str:
                return "home"

            def snapshot_registration(self, name: str, *, scope: str | None = None):
                self.last = (name, scope)
                if scope == "home":
                    return (None, loader)
                return (None, None)

            def get(self, name: str):
                self.get_calls += 1
                loader()
                return types.SimpleNamespace(adapter_factory=shipped)

        registry = Registry()
        modules = {**_install_shipped(shipped), **_registry_module(registry)}
        with lock, mock.patch.dict(sys.modules, modules):
            resolved = hermes_v2._active_discord_adapter_class()

        self.assertIs(shipped, resolved)
        self.assertFalse(loaded.is_set(), "deferred Discord loader must stay pending")
        self.assertEqual(0, registry.get_calls)

    def test_minimum_registry_without_snapshot_does_not_resolve_deferred(self) -> None:
        shipped = _shipped_discord()
        loaded = []

        class Registry:
            def __init__(self) -> None:
                self._entries: dict[str, object] = {}
                self._deferred = {"discord": lambda: loaded.append("loaded")}
                self.get_calls = 0

            def get(self, name: str):
                self.get_calls += 1
                self._deferred.pop(name)()
                return types.SimpleNamespace(adapter_factory=shipped)

        registry = Registry()
        modules = {**_install_shipped(shipped), **_registry_module(registry)}
        with mock.patch.dict(sys.modules, modules):
            resolved = hermes_v2._active_discord_adapter_class()

        self.assertIs(shipped, resolved)
        self.assertEqual([], loaded)
        self.assertEqual(0, registry.get_calls)

    def test_concrete_shipped_registration_is_the_resolved_class(self) -> None:
        shipped = _shipped_discord()

        class Registry:
            def current_scope_key(self) -> str:
                return "home"

            def snapshot_registration(self, name: str, *, scope: str | None = None):
                del name
                if scope == "home":
                    return (types.SimpleNamespace(adapter_factory=shipped), None)
                return (None, None)

            def get(self, name: str):
                raise AssertionError(name)

        modules = {**_install_shipped(shipped), **_registry_module(Registry())}
        with mock.patch.dict(sys.modules, modules):
            self.assertIs(shipped, hermes_v2._active_discord_adapter_class())

    def test_foreign_concrete_override_fails_closed_without_loading(self) -> None:
        shipped = _shipped_discord()
        foreign = _shipped_discord("ForeignDiscord")
        loaded = []

        class Registry:
            def current_scope_key(self) -> str:
                return "home"

            def snapshot_registration(self, name: str, *, scope: str | None = None):
                del name, scope
                return (types.SimpleNamespace(adapter_factory=foreign), lambda: loaded.append(1))

            def get(self, name: str):
                raise AssertionError(name)

        modules = {**_install_shipped(shipped), **_registry_module(Registry())}
        with mock.patch.dict(sys.modules, modules):
            with self.assertRaises(ValidationError) as raised:
                hermes_v2._active_discord_adapter_class()

        self.assertIn("Discord adapter", str(raised.exception))
        self.assertEqual([], loaded)

    def test_shipped_factory_function_is_not_a_foreign_override(self) -> None:
        shipped = _shipped_discord()

        def build_adapter(config: object) -> object:
            return shipped(config)

        modules = _install_shipped(shipped)
        modules["plugins.platforms.discord.adapter"].build_adapter = build_adapter
        build_adapter.__module__ = "plugins.platforms.discord.adapter"

        class Registry:
            def current_scope_key(self) -> str:
                return "home"

            def snapshot_registration(self, name: str, *, scope: str | None = None):
                del name, scope
                return (types.SimpleNamespace(adapter_factory=build_adapter), None)

            def get(self, name: str):
                raise AssertionError(name)

        modules.update(_registry_module(Registry()))
        with mock.patch.dict(sys.modules, modules):
            self.assertIs(shipped, hermes_v2._active_discord_adapter_class())

    def test_live_host_class_is_not_a_foreign_override(self) -> None:
        shipped = _shipped_discord()
        live = type("DiscordAdapter", (), {})
        live.__module__ = "hermes_plugins.discord_platform.adapter"
        live_module = types.ModuleType("hermes_plugins.discord_platform.adapter")
        live_module.DiscordAdapter = live

        def build_adapter(config: object) -> object:
            del config
            return live()

        build_adapter.__module__ = live_module.__name__
        modules = _install_shipped(shipped)
        modules[live_module.__name__] = live_module

        class Registry:
            def snapshot_registration(self, name: str, *, scope: str | None = None):
                del name, scope
                return (types.SimpleNamespace(adapter_factory=build_adapter), None)

            def get(self, name: str):
                raise AssertionError(name)

        modules.update(_registry_module(Registry()))
        with mock.patch.dict(sys.modules, modules):
            self.assertIs(live, hermes_v2._active_discord_adapter_class())

    def test_current_host_module_name_is_not_a_foreign_override(self) -> None:
        shipped = _shipped_discord()
        live = type("DiscordAdapter", (), {})
        live.__module__ = "hermes_plugins.platforms__discord.adapter"
        live_module = types.ModuleType(live.__module__)
        live_module.DiscordAdapter = live

        def build_adapter(config: object) -> object:
            del config
            return live()

        build_adapter.__module__ = live_module.__name__
        modules = _install_shipped(shipped)
        modules[live_module.__name__] = live_module

        class Registry:
            def snapshot_registration(self, name: str, *, scope: str | None = None):
                del name, scope
                return (types.SimpleNamespace(adapter_factory=build_adapter), None)

            def get(self, name: str):
                raise AssertionError(name)

        modules.update(_registry_module(Registry()))
        with mock.patch.dict(sys.modules, modules):
            self.assertIs(live, hermes_v2._active_discord_adapter_class())

    def test_lookalike_host_module_fails_closed(self) -> None:
        shipped = _shipped_discord()
        foreign = type("DiscordAdapter", (), {})
        foreign.__module__ = "hermes_plugins.evil_discord.adapter"
        foreign_module = types.ModuleType(foreign.__module__)
        foreign_module.DiscordAdapter = foreign

        def build_adapter(config: object) -> object:
            del config
            return foreign()

        build_adapter.__module__ = foreign_module.__name__
        modules = _install_shipped(shipped)
        modules[foreign_module.__name__] = foreign_module

        class Registry:
            def snapshot_registration(self, name: str, *, scope: str | None = None):
                del name, scope
                return (types.SimpleNamespace(adapter_factory=build_adapter), None)

            def get(self, name: str):
                raise AssertionError(name)

        modules.update(_registry_module(Registry()))
        with mock.patch.dict(sys.modules, modules):
            with self.assertRaises(ValidationError) as raised:
                hermes_v2._active_discord_adapter_class()
        self.assertIn("Discord adapter", str(raised.exception))

    def test_deferred_loader_is_replaced_by_the_shipped_registration(self) -> None:
        shipped = _shipped_discord()
        shipped.__module__ = "plugins.platforms.discord.adapter"
        loaded: list[str] = []
        published: dict[str, object] = {}

        class Registry:
            def current_scope_key(self) -> str:
                return "home"

            def snapshot_registration(self, name: str, *, scope: str | None = None):
                del name
                if scope == "home" and "entry" not in published:
                    return (None, lambda: loaded.append("loaded"))
                if scope == "home":
                    return (published["entry"], None)
                return (None, None)

            def register(self, entry: object, *, scope: str | None = None) -> None:
                published["entry"] = entry
                published["scope"] = scope

            def get(self, name: str):
                raise AssertionError(name)

        def stock_register(ctx: object) -> None:
            ctx.register_platform(  # type: ignore[attr-defined]
                name="discord",
                label="Discord",
                adapter_factory=shipped,
                check_fn=lambda: True,
                emoji="🎮",
            )

        modules = _install_shipped(shipped)
        adapter_module = modules["plugins.platforms.discord.adapter"]
        adapter_module.register = stock_register  # type: ignore[attr-defined]

        @dataclass
        class PlatformEntry:
            name: str
            label: str
            adapter_factory: object
            check_fn: object
            source: str = "plugin"
            emoji: str = ""

        modules.update(_registry_module(Registry()))
        modules["gateway.platform_registry"].PlatformEntry = PlatformEntry  # type: ignore[attr-defined]
        with mock.patch.dict(sys.modules, modules):
            resolved = hermes_v2._active_discord_adapter_class()

        self.assertIs(shipped, resolved)
        self.assertEqual([], loaded)
        self.assertIs(published["entry"].adapter_factory, shipped)  # type: ignore[attr-defined]
        self.assertEqual("home", published["scope"])
        self.assertEqual("plugin", published["entry"].source)  # type: ignore[attr-defined]

    def test_absent_registry_still_uses_the_shipped_class(self) -> None:
        shipped = _shipped_discord()
        modules = _install_shipped(shipped)
        modules["gateway"] = None  # type: ignore[assignment]
        modules["gateway.platform_registry"] = None  # type: ignore[assignment]
        with mock.patch.dict(sys.modules, modules):
            self.assertIs(shipped, hermes_v2._active_discord_adapter_class())


class NativeSessionOwnershipTests(unittest.TestCase):
    def test_child_proves_native_ownership_so_stock_releases_its_guard(self) -> None:
        adapter = _StockAdapter()
        guard = asyncio.Event()
        session_key = "agent:main:discord:group:42"
        adapter._active_sessions[session_key] = guard
        observed: dict[str, object] = {}

        async def stock_process() -> str:
            observed["child"] = asyncio.current_task()
            observed["owner"] = adapter._session_tasks.get(session_key)
            try:
                return "settled"
            finally:
                adapter.release_if_owner(session_key, guard)

        async def parent() -> str:
            adapter._session_tasks[session_key] = asyncio.current_task()
            return await hermes_v2._run_stock_process_with_deadline(
                _Runtime(),
                _Trace(),
                stock_process(),
                adapter=adapter,
                session_key=session_key,
            )

        self.assertEqual("settled", asyncio.run(parent()))
        self.assertIs(observed["child"], observed["owner"])
        self.assertEqual([session_key], adapter.released)
        self.assertNotIn(session_key, adapter._active_sessions)
        self.assertNotIn(session_key, adapter._session_tasks)

    def test_stop_cancels_the_child_stock_recorded_as_the_session_owner(self) -> None:
        adapter = _StockAdapter()
        guard = asyncio.Event()
        session_key = "agent:main:discord:group:42"
        adapter._active_sessions[session_key] = guard
        started = asyncio.Event()
        observed: dict[str, object] = {}

        async def stock_process() -> None:
            observed["child"] = asyncio.current_task()
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                observed["stop_saw_child"] = (
                    asyncio.current_task() in adapter._expected_cancelled_tasks
                )
                raise

        async def parent() -> None:
            adapter._session_tasks[session_key] = asyncio.current_task()
            await hermes_v2._run_stock_process_with_deadline(
                _Runtime(),
                _Trace(),
                stock_process(),
                adapter=adapter,
                session_key=session_key,
            )

        async def run() -> None:
            task = asyncio.create_task(parent())
            await asyncio.wait_for(started.wait(), timeout=2)
            owner = adapter._session_tasks.pop(session_key)
            observed["stopped"] = owner
            adapter._expected_cancelled_tasks.add(owner)
            owner.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        asyncio.run(run())
        self.assertIs(observed["stopped"], observed["child"])
        self.assertTrue(observed["stop_saw_child"])
        self.assertIn(session_key, adapter._active_sessions)
        self.assertIs(guard, adapter._active_sessions[session_key])

    def test_finished_child_does_not_release_a_newer_task_guard(self) -> None:
        adapter = _StockAdapter()
        old_guard = asyncio.Event()
        new_guard = asyncio.Event()
        session_key = "agent:main:discord:group:42"
        adapter._active_sessions[session_key] = old_guard
        newer: asyncio.Task[object] | None = None
        entered = asyncio.Event()

        async def newer_task() -> None:
            await asyncio.Event().wait()

        async def stock_process() -> str:
            nonlocal newer
            entered.set()
            await asyncio.sleep(0)
            newer = asyncio.create_task(newer_task())
            adapter._session_tasks[session_key] = newer
            adapter._active_sessions[session_key] = new_guard
            try:
                return "old-turn"
            finally:
                adapter.release_if_owner(session_key, old_guard)

        async def parent() -> str:
            adapter._session_tasks[session_key] = asyncio.current_task()
            result = await hermes_v2._run_stock_process_with_deadline(
                _Runtime(),
                _Trace(),
                stock_process(),
                adapter=adapter,
                session_key=session_key,
            )
            self.assertIs(newer, adapter._session_tasks[session_key])
            self.assertIs(new_guard, adapter._active_sessions[session_key])
            self.assertIsNotNone(newer)
            assert newer is not None
            self.assertFalse(newer.done())
            newer.cancel()
            return result

        self.assertEqual("old-turn", asyncio.run(parent()))
        self.assertEqual([], adapter.released)

    def test_wrapper_does_not_steal_a_session_it_does_not_own(self) -> None:
        adapter = _StockAdapter()
        guard = asyncio.Event()
        session_key = "agent:main:discord:group:42"
        adapter._active_sessions[session_key] = guard

        async def occupant() -> None:
            await asyncio.Event().wait()

        async def stock_process() -> str:
            try:
                return "unrelated"
            finally:
                adapter.release_if_owner(session_key, guard)

        async def parent() -> str:
            other = asyncio.create_task(occupant())
            adapter._session_tasks[session_key] = other
            try:
                return await hermes_v2._run_stock_process_with_deadline(
                    _Runtime(),
                    _Trace(),
                    stock_process(),
                    adapter=adapter,
                    session_key=session_key,
                )
            finally:
                self.assertIs(other, adapter._session_tasks[session_key])
                self.assertIs(guard, adapter._active_sessions[session_key])
                other.cancel()

        self.assertEqual("unrelated", asyncio.run(parent()))
        self.assertEqual([], adapter.released)

    def test_direct_deadline_call_without_a_session_map_is_unchanged(self) -> None:
        async def work() -> str:
            return "plain"

        async def run() -> str:
            return await hermes_v2._run_stock_process_with_deadline(
                _Runtime(),
                _Trace(),
                work(),
            )

        self.assertEqual("plain", asyncio.run(run()))


class ResolverSourceTests(unittest.TestCase):
    def test_resolver_does_not_call_platform_registry_get(self) -> None:
        source = inspect.getsource(hermes_v2._active_discord_adapter_class)
        self.assertNotIn("platform_registry.get", source)
        self.assertNotIn(".get(\"discord\")", source)
        self.assertNotIn(".get('discord')", source)
