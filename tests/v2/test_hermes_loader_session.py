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
import tempfile
import threading
import time
import types
import unittest
from dataclasses import dataclass
from pathlib import Path
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
        self._background_tasks: set[asyncio.Task[object]] = set()
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


_SHIPPED_ADAPTER_FILE = "/host/plugins/platforms/discord/adapter.py"


def _install_shipped(
    adapter_class: type,
    *,
    file: str = _SHIPPED_ADAPTER_FILE,
) -> dict[str, types.ModuleType]:
    modules = {
        "plugins": types.ModuleType("plugins"),
        "plugins.platforms": types.ModuleType("plugins.platforms"),
        "plugins.platforms.discord": types.ModuleType("plugins.platforms.discord"),
        "plugins.platforms.discord.adapter": types.ModuleType(
            "plugins.platforms.discord.adapter"
        ),
    }
    adapter = modules["plugins.platforms.discord.adapter"]
    adapter.DiscordAdapter = adapter_class
    adapter.__file__ = file
    return modules


def _registry_module(registry: object) -> dict[str, types.ModuleType]:
    gateway = types.ModuleType("gateway")
    registry_module = types.ModuleType("gateway.platform_registry")
    registry_module.platform_registry = registry
    gateway.platform_registry = registry_module
    return {"gateway": gateway, "gateway.platform_registry": registry_module}


class _MinimumRegistry:
    """0.19.0 registry writes: no lock and no two-map CAS."""

    def __init__(self) -> None:
        self._entries: dict[str, object] = {}
        self._deferred: dict[str, object] = {}

    def register(self, entry: object) -> None:
        self._deferred.pop(getattr(entry, "name", "discord"), None)
        self._entries[getattr(entry, "name", "discord")] = entry

    def register_deferred(self, name: str, loader: object) -> None:
        if name in self._entries:
            return
        self._deferred[name] = loader


def _run_at_source_line(function, fragment, action, operation):
    """Run action to completion immediately before function executes fragment."""

    lines, start = inspect.getsourcelines(function)
    try:
        target = next(start + index for index, line in enumerate(lines) if fragment in line)
    except StopIteration as exc:
        raise AssertionError(f"boundary not in {function.__name__}: {fragment}") from exc
    entered = threading.Event()
    done = threading.Event()
    errors: list[BaseException] = []

    def writer() -> None:
        try:
            if not entered.wait(5):
                raise AssertionError("boundary not reached")
            action()
        except BaseException as exc:
            errors.append(exc)
        finally:
            done.set()

    def trace(frame, event, arg):
        del arg
        if (
            event == "line"
            and frame.f_code is function.__code__
            and frame.f_lineno == target
        ):
            entered.set()
            if not done.wait(5):
                raise AssertionError("writer did not finish")
        return trace

    thread = threading.Thread(target=writer)
    thread.start()
    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        return operation()
    finally:
        sys.settrace(previous)
        thread.join(6)
        if thread.is_alive():
            raise AssertionError("writer still running")
        if errors:
            raise errors[0]


def _run_at_lineno(function, lineno: int, action, operation):
    """Run action to completion immediately before function executes lineno."""

    entered = threading.Event()
    done = threading.Event()
    errors: list[BaseException] = []

    def writer() -> None:
        try:
            if not entered.wait(5):
                raise AssertionError(f"line {lineno} not reached")
            action()
        except BaseException as exc:
            errors.append(exc)
        finally:
            done.set()

    def trace(frame, event, arg):
        del arg
        if event == "line" and frame.f_code is function.__code__ and frame.f_lineno == lineno:
            entered.set()
            if not done.wait(5):
                raise AssertionError(f"native reader did not finish at line {lineno}")
        return trace

    thread = threading.Thread(target=writer)
    thread.start()
    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        return operation()
    finally:
        sys.settrace(previous)
        thread.join(6)
        if thread.is_alive():
            raise AssertionError("native reader still running")
        if errors:
            raise errors[0]


def _executed_lines(function, operation) -> list[int]:
    seen: list[int] = []

    def trace(frame, event, arg):
        del arg
        if event == "line" and frame.f_code is function.__code__ and frame.f_lineno not in seen:
            seen.append(frame.f_lineno)
        return trace

    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        operation()
    finally:
        sys.settrace(previous)
    return seen


def _source_line(function, lineno: int) -> str:
    lines, start = inspect.getsourcelines(function)
    return lines[lineno - start].strip()


class _ReadableMinimumRegistry:
    """0.19.0 register/get/unregister, including the documented atomic reads."""

    def __init__(self) -> None:
        self._entries: dict[str, object] = {}
        self._deferred: dict[str, object] = {}
        self.loader_calls = 0

    def register(self, entry: object) -> None:
        name = getattr(entry, "name", "discord")
        self._deferred.pop(name, None)
        self._entries[name] = entry

    def register_deferred(self, name: str, loader: object) -> None:
        if name in self._entries:
            return
        self._deferred[name] = loader

    def unregister(self, name: str) -> bool:
        self._deferred.pop(name, None)
        return self._entries.pop(name, None) is not None

    def get(self, name: str) -> object:
        if name not in self._entries:
            loader = self._deferred.pop(name, None)
            if loader is not None:
                self.loader_calls += 1
                loader()  # type: ignore[operator]
        return self._entries.get(name)


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
        modules["plugins.platforms.discord.adapter"]._build_adapter = build_adapter
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
        live_module.__file__ = _SHIPPED_ADAPTER_FILE
        live_module.DiscordAdapter = live

        def build_adapter(config: object) -> object:
            del config
            return live()

        build_adapter.__module__ = live_module.__name__
        live_module._build_adapter = build_adapter
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
        live_module.__file__ = _SHIPPED_ADAPTER_FILE
        live_module.DiscordAdapter = live

        def build_adapter(config: object) -> object:
            del config
            return live()

        build_adapter.__module__ = live_module.__name__
        live_module._build_adapter = build_adapter
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

        def loader() -> None:
            loaded.append("loaded")

        class Registry:
            def current_scope_key(self) -> str:
                return "home"

            def snapshot_registration(self, name: str, *, scope: str | None = None):
                del name
                if scope == "home" and "entry" not in published:
                    return (None, loader)
                if scope == "home":
                    return (published["entry"], None)
                return (None, None)

            def register(self, entry: object, *, scope: str | None = None) -> None:
                raise AssertionError("publication must use native CAS")

            def restore_registration(self, name, current, previous, *, scope=None):
                if self.snapshot_registration(name, scope=scope) != current:
                    return False
                published["entry"] = previous[0]
                published["scope"] = scope
                return True

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


def _track_like_stock(adapter: _StockAdapter, session_key: str, task: asyncio.Task[object]) -> None:
    """The bookkeeping stock installs on the task it records as session owner."""

    adapter._session_tasks[session_key] = task
    adapter._background_tasks.add(task)
    task.add_done_callback(adapter._background_tasks.discard)
    task.add_done_callback(adapter._expected_cancelled_tasks.discard)


def _alias_module(name: str, *, file: str) -> tuple[types.ModuleType, type]:
    module = types.ModuleType(name)
    module.__file__ = file
    adapter = type("DiscordAdapter", (), {})
    adapter.__module__ = name
    module.DiscordAdapter = adapter
    return module, adapter


class ShippedFileProvenanceTests(unittest.TestCase):
    def test_same_file_nonfactory_is_not_an_adapter(self) -> None:
        shipped = _shipped_discord()
        modules = _install_shipped(shipped)
        module = modules["plugins.platforms.discord.adapter"]

        def register(ctx: object) -> None:
            raise AssertionError("must not invoke a candidate factory")

        register.__module__ = module.__name__
        module.register = register
        entry = types.SimpleNamespace(adapter_factory=register)
        with mock.patch.dict(sys.modules, modules):
            self.assertIsNone(
                hermes_v2._discord_registration_is_shipped(entry, shipped)
            )

    def test_recognised_namespace_with_contradictory_file_is_not_shipped(self) -> None:
        shipped = _shipped_discord()
        name = "hermes_plugins.platforms__discord.adapter"
        foreign_module, foreign = _alias_module(
            name, file="/independent-custom-plugin/adapter.py"
        )
        modules = _install_shipped(shipped)
        modules[name] = foreign_module
        entry = types.SimpleNamespace(adapter_factory=foreign)
        with mock.patch.dict(sys.modules, modules):
            resolved = hermes_v2._discord_registration_is_shipped(entry, shipped)
        self.assertIsNone(
            resolved,
            "a known namespace must not override contradictory file provenance",
        )

    def test_path_suffix_alone_is_not_the_shipped_file(self) -> None:
        shipped = _shipped_discord()
        name = "unrelated.adapter"
        lookalike, foreign = _alias_module(
            name, file="/other/tree/plugins/platforms/discord/adapter.py"
        )
        modules = _install_shipped(shipped)
        modules[name] = lookalike
        entry = types.SimpleNamespace(adapter_factory=foreign)
        with mock.patch.dict(sys.modules, modules):
            resolved = hermes_v2._discord_registration_is_shipped(entry, shipped)
        self.assertIsNone(resolved)

    def test_recognised_name_without_a_file_is_not_shipped(self) -> None:
        shipped = _shipped_discord()
        name = "hermes_plugins.discord_platform.adapter"
        module = types.ModuleType(name)
        foreign = type("DiscordAdapter", (), {"__module__": name})
        module.DiscordAdapter = foreign
        modules = _install_shipped(shipped)
        modules[name] = module
        entry = types.SimpleNamespace(adapter_factory=foreign)
        with mock.patch.dict(sys.modules, modules):
            self.assertIsNone(
                hermes_v2._discord_registration_is_shipped(entry, shipped)
            )

    def test_genuine_minimum_and_current_aliases_match_the_shipped_file(self) -> None:
        shipped = _shipped_discord()
        names = (
            "hermes_plugins.discord_platform.adapter",
            "hermes_plugins.platforms__discord.adapter",
            "hermes_plugins.platforms__discord__home_ab12cd.adapter",
        )
        for name in names:
            with self.subTest(name=name):
                alias, live = _alias_module(name, file=_SHIPPED_ADAPTER_FILE)

                def build_adapter(config: object, cls: type = live) -> object:
                    del config
                    return cls()

                build_adapter.__module__ = name
                alias._build_adapter = build_adapter
                modules = _install_shipped(shipped)
                modules[name] = alias
                entry = types.SimpleNamespace(adapter_factory=build_adapter)
                with mock.patch.dict(sys.modules, modules):
                    resolved = hermes_v2._discord_registration_is_shipped(
                        entry, shipped
                    )
                self.assertIs(live, resolved)

    def test_foreign_factory_reexport_of_shipped_class_is_not_shipped(self) -> None:
        shipped = _shipped_discord()
        foreign_name = "custom_plugin.discord_adapter"
        foreign = types.ModuleType(foreign_name)
        foreign.__file__ = "/independent-custom-plugin/adapter.py"
        foreign.DiscordAdapter = shipped

        def build_adapter(config: object) -> object:
            del config
            return shipped()

        build_adapter.__module__ = foreign_name
        modules = _install_shipped(shipped)
        modules[foreign_name] = foreign
        entry = types.SimpleNamespace(adapter_factory=build_adapter)
        with mock.patch.dict(sys.modules, modules):
            self.assertIsNone(
                hermes_v2._discord_registration_is_shipped(entry, shipped)
            )


class NativeSessionBookkeepingTests(unittest.TestCase):
    def test_repeated_stops_do_not_retain_finished_children(self) -> None:
        adapter = _StockAdapter()

        async def one_stop(session_key: str) -> None:
            started = asyncio.Event()

            async def work() -> None:
                started.set()
                await asyncio.Event().wait()

            async def parent() -> None:
                _track_like_stock(adapter, session_key, asyncio.current_task())
                await hermes_v2._run_stock_process_with_deadline(
                    _Runtime(),
                    _Trace(),
                    work(),
                    adapter=adapter,
                    session_key=session_key,
                )

            wrapper = asyncio.create_task(parent())
            await asyncio.wait_for(started.wait(), timeout=2)
            task = adapter._session_tasks.pop(session_key)
            adapter._expected_cancelled_tasks.add(task)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await wrapper
            await asyncio.sleep(0)

        async def run() -> tuple[int, int]:
            await one_stop("session-a")
            await one_stop("session-b")
            return (
                len(adapter._expected_cancelled_tasks),
                len(adapter._background_tasks),
            )

        retained, background = asyncio.run(run())
        self.assertEqual(0, retained)
        self.assertEqual(0, background)

    def test_shutdown_tracks_and_clears_the_adopted_child(self) -> None:
        adapter = _StockAdapter()
        session_key = "agent:main:discord:group:42"
        started = asyncio.Event()
        observed: dict[str, asyncio.Task[object]] = {}

        async def work() -> None:
            observed["child"] = asyncio.current_task()
            started.set()
            await asyncio.Event().wait()

        async def parent() -> None:
            _track_like_stock(adapter, session_key, asyncio.current_task())
            await hermes_v2._run_stock_process_with_deadline(
                _Runtime(),
                _Trace(),
                work(),
                adapter=adapter,
                session_key=session_key,
            )

        async def run() -> None:
            wrapper = asyncio.create_task(parent())
            await asyncio.wait_for(started.wait(), timeout=2)
            child = observed["child"]
            self.assertIn(child, adapter._background_tasks)
            pending = [task for task in adapter._background_tasks if not task.done()]
            for task in pending:
                adapter._expected_cancelled_tasks.add(task)
                task.cancel()
            await asyncio.sleep(0)
            wrapper.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await wrapper
            await asyncio.sleep(0)
            self.assertTrue(child.done())
            self.assertEqual(0, len(adapter._expected_cancelled_tasks))
            self.assertEqual(0, len(adapter._background_tasks))

        asyncio.run(run())


def _platform_entry_type() -> type:
    @dataclass
    class PlatformEntry:
        name: str
        label: str
        adapter_factory: object
        check_fn: object
        source: str = "plugin"
        plugin_name: str = ""
        emoji: str = ""

    return PlatformEntry


def _publication_modules(
    registry: object, shipped: type
) -> dict[str, types.ModuleType]:
    modules = _install_shipped(shipped)
    modules["plugins.platforms.discord.adapter"].register = (  # type: ignore[attr-defined]
        lambda ctx: ctx.register_platform(  # type: ignore[attr-defined]
            name="discord",
            label="Discord",
            adapter_factory=shipped,
            check_fn=lambda: True,
            emoji="🎮",
        )
    )
    modules.update(_registry_module(registry))
    modules["gateway.platform_registry"].PlatformEntry = _platform_entry_type()  # type: ignore[attr-defined]
    return modules


class DiscordPublicationOwnershipTests(unittest.TestCase):
    def _loader(self) -> object:
        manifest = types.SimpleNamespace(name="discord-platform")

        def loader(_manifest: object = manifest) -> None:
            raise AssertionError("deferred Discord loader must never run")

        return loader

    def test_failed_register_restores_scoped_loader_and_keeps_a_newer_entry(self) -> None:
        from tests.v2.test_hermes_portable import FakeLlm, room_config

        shipped = _shipped_discord()
        shipped.__module__ = "plugins.platforms.discord.adapter"
        loader = self._loader()
        state = {"entry": None, "loader": loader}

        class Registry:
            scope = "home"

            def current_scope_key(self) -> str:
                return "home"

            def snapshot_registration(self, name: str, *, scope: str | None = None):
                del name
                if scope != "home":
                    return (None, None)
                return (state["entry"], state["loader"])

            def register(self, entry: object, *, scope: str | None = None) -> None:
                self.registered_scope = scope
                state["entry"] = entry
                state["loader"] = None

            def restore_registration(
                self,
                name: str,
                current: tuple[object, object],
                previous: tuple[object, object],
                *,
                scope: str | None = None,
            ) -> bool:
                del name, scope
                if (state["entry"], state["loader"]) != current:
                    return False
                state["entry"], state["loader"] = previous
                return True

        registry = Registry()

        def install(plugin: object) -> None:
            del plugin
            hermes_v2._active_discord_adapter_class()

        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(Path(temporary), llm=FakeLlm([]))

            def register_hook(name: str, callback: object) -> None:
                del name, callback
                raise RuntimeError("injected later activation failure")

            ctx.register_hook = register_hook
            modules = _publication_modules(registry, shipped)
            with mock.patch.dict(sys.modules, modules):
                with mock.patch.object(
                    hermes_v2, "_hermes_version", return_value="0.21.5"
                ):
                    with mock.patch.object(
                        hermes_v2, "_install_host_contract_v1", side_effect=install
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError, "injected later activation failure"
                        ):
                            hermes_v2.register(
                                ctx,
                                config_loader=lambda _: config,
                                dashboard_installer=lambda: None,
                            )
        self.assertIsNone(state["entry"])
        self.assertIs(loader, state["loader"])

        state["entry"] = object()
        state["loader"] = None
        # A generation published after ours must survive the same inverse.
        self.assertIsNotNone(state["entry"])

    def test_failed_register_restores_minimum_deferred_loader(self) -> None:
        from tests.v2.test_hermes_portable import FakeLlm, room_config

        shipped = _shipped_discord()
        shipped.__module__ = "plugins.platforms.discord.adapter"
        loader = self._loader()

        class Registry:
            def __init__(self) -> None:
                self._entries: dict[str, object] = {}
                self._deferred = {"discord": loader}

            def register(self, entry: object) -> None:
                self._deferred.pop(getattr(entry, "name", "discord"), None)
                self._entries["discord"] = entry

        registry = Registry()

        def install(plugin: object) -> None:
            del plugin
            hermes_v2._active_discord_adapter_class()

        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(Path(temporary), llm=FakeLlm([]))

            def register_hook(name: str, callback: object) -> None:
                del name, callback
                raise RuntimeError("injected later activation failure")

            ctx.register_hook = register_hook
            modules = _publication_modules(registry, shipped)
            with mock.patch.dict(sys.modules, modules):
                with mock.patch.object(
                    hermes_v2, "_hermes_version", return_value="0.19.0"
                ):
                    with mock.patch.object(
                        hermes_v2, "_install_host_contract_v1", side_effect=install
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError, "injected later activation failure"
                        ):
                            hermes_v2.register(
                                ctx,
                                config_loader=lambda _: config,
                                dashboard_installer=lambda: None,
                            )
        self.assertNotIn("discord", registry._entries)
        self.assertIs(loader, registry._deferred.get("discord"))

    def test_publication_preserves_manifest_name_and_ledger_inverse(self) -> None:
        from tests.v2.test_hermes_portable import FakeLlm, room_config

        shipped = _shipped_discord()
        shipped.__module__ = "plugins.platforms.discord.adapter"
        loader = self._loader()
        state = {"entry": None, "loader": loader}
        recorded: dict[str, object] = {}

        class Registry:
            def current_scope_key(self) -> str:
                return "home"

            def snapshot_registration(self, name: str, *, scope: str | None = None):
                del name
                if scope != "home":
                    return (None, None)
                return (state["entry"], state["loader"])

            def register(self, entry: object, *, scope: str | None = None) -> None:
                self.scope = scope
                state["entry"] = entry
                state["loader"] = None

            def restore_registration(
                self,
                name: str,
                current: tuple[object, object],
                previous: tuple[object, object],
                *,
                scope: str | None = None,
            ) -> bool:
                del name
                if scope != "home" or (state["entry"], state["loader"]) != current:
                    return False
                self.scope = scope
                state["entry"], state["loader"] = previous
                return True

        registry = Registry()

        def track(
            manifest: object,
            kind: str,
            name: str,
            tracked_registry: object,
            current: tuple[object, object],
            previous: tuple[object, object],
            finalize: object = None,
        ) -> None:
            recorded["lease"] = (
                manifest,
                kind,
                name,
                tracked_registry,
                current,
                previous,
                finalize,
            )

        def install(plugin: object) -> None:
            del plugin
            hermes_v2._active_discord_adapter_class()

        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(Path(temporary), llm=FakeLlm([]))
            ctx.manifest = types.SimpleNamespace(name="nunchi")
            ctx._manager = types.SimpleNamespace(
                scope_key="home",
                _plugin_platform_names=set(),
                _track_scoped_registration=track,
                _remove_platform_name_if_unowned=lambda name: None,
            )
            modules = _publication_modules(registry, shipped)
            with mock.patch.dict(sys.modules, modules):
                with mock.patch.object(
                    hermes_v2, "_hermes_version", return_value="0.21.5"
                ):
                    with mock.patch.object(
                        hermes_v2, "_install_host_contract_v1", side_effect=install
                    ):
                        hermes_v2.register(
                            ctx,
                            config_loader=lambda _: config,
                            dashboard_installer=lambda: None,
                        )
        entry = state["entry"]
        self.assertIsNotNone(entry)
        self.assertEqual("discord-platform", entry.plugin_name)  # type: ignore[attr-defined]
        self.assertEqual("home", registry.scope)
        lease = recorded["lease"]
        self.assertEqual("platform", lease[1])  # type: ignore[index]
        self.assertEqual("discord", lease[2])  # type: ignore[index]
        self.assertIs(entry, lease[4][0])  # type: ignore[index]
        self.assertIs(loader, lease[5][1])  # type: ignore[index]
        restored = registry.restore_registration(
            "discord", lease[4], lease[5], scope="home"  # type: ignore[index]
        )
        self.assertTrue(restored)
        self.assertIsNone(state["entry"])
        self.assertIs(loader, state["loader"])
        # Rediscovery can publish a new deferred loader only after the inverse
        # clears the concrete entry our publication left behind.
        state["entry"] = None
        state["loader"] = None
        registry.restore_registration(
            "discord", (None, loader), (None, None), scope="home"
        )
        self.assertEqual((None, None), (state["entry"], state["loader"]))

    def test_publication_does_not_overwrite_a_newer_registration(self) -> None:
        shipped = _shipped_discord()
        shipped.__module__ = "plugins.platforms.discord.adapter"
        loader = self._loader()
        newer = types.SimpleNamespace(adapter_factory=shipped, plugin_name="kept")
        seen_loader = False

        class Registry:
            def current_scope_key(self) -> str:
                return "home"

            def snapshot_registration(self, name: str, *, scope: str | None = None):
                nonlocal seen_loader
                del name
                if scope != "home":
                    return (None, None)
                if seen_loader:
                    return (newer, None)
                seen_loader = True
                return (None, loader)

            def register(self, entry: object, *, scope: str | None = None) -> None:
                del entry, scope
                raise AssertionError("must not overwrite a newer Discord registration")

        modules = _publication_modules(Registry(), shipped)
        with mock.patch.dict(sys.modules, modules):
            resolved = hermes_v2._active_discord_adapter_class()
        self.assertIs(shipped, resolved)

    def test_newer_deferred_loader_is_preserved_and_activation_fails_closed(self) -> None:
        shipped = _shipped_discord()
        shipped.__module__ = "plugins.platforms.discord.adapter"
        loader = self._loader()
        newer = self._loader()
        registry = types.SimpleNamespace(
            _entries={}, _deferred={"discord": loader}, register=lambda entry: None
        )
        build = hermes_v2._host_platform_entry

        def replace_loader(**kwargs):
            registry._deferred["discord"] = newer
            return build(**kwargs)

        with mock.patch.dict(sys.modules, _publication_modules(registry, shipped)):
            with mock.patch.object(hermes_v2, "_host_platform_entry", side_effect=replace_loader):
                with self.assertRaises(ValidationError):
                    hermes_v2._active_discord_adapter_class()
        self.assertEqual({}, registry._entries)
        self.assertIs(newer, registry._deferred["discord"])

    def test_concurrent_publication_keeps_and_validates_winner(self) -> None:
        # Pause at the actual write operation, not at a preceding snapshot.
        for scoped in (False, True):
            for foreign in (False, True):
                with self.subTest(scoped=scoped, foreign=foreign):
                    shipped = _shipped_discord()
                    shipped.__module__ = "plugins.platforms.discord.adapter"
                    loader = self._loader()
                    winner = types.SimpleNamespace(
                        adapter_factory=object if foreign else shipped
                    )
                    entered = threading.Event()
                    completed = threading.Event()
                    errors = []

                    def pause():
                        entered.set()
                        if not completed.wait(2):
                            raise AssertionError("concurrent writer did not finish")

                    class Entries(dict):
                        def setdefault(self, name, value):
                            pause()
                            return super().setdefault(name, value)

                    class Registry:
                        def __init__(self):
                            self._entries = Entries()
                            self._deferred = {"discord": loader}
                            self._lock = threading.RLock()

                        def register(self, entry, *, scope=None):
                            # The old implementation takes this unconditional path.
                            pause()
                            with self._lock:
                                self._deferred.pop("discord", None)
                                self._entries["discord"] = entry

                    registry = Registry()
                    if scoped:
                        registry.current_scope_key = lambda: "home"

                        def snapshot(name, *, scope=None):
                            with registry._lock:
                                if scope != "home":
                                    return None, None
                                return registry._entries.get(name), registry._deferred.get(name)

                        def restore(name, current, previous, *, scope=None):
                            pause()
                            with registry._lock:
                                if snapshot(name, scope=scope) != current:
                                    return False
                                registry._entries[name] = previous[0]
                                registry._deferred.pop(name, None)
                                return True

                        registry.snapshot_registration = snapshot
                        registry.restore_registration = restore

                    def writer():
                        try:
                            if not entered.wait(2):
                                raise AssertionError("publication never reached write")
                            with registry._lock:
                                registry._deferred.pop("discord", None)
                                registry._entries["discord"] = winner
                        except BaseException as exc:
                            errors.append(exc)
                        finally:
                            completed.set()

                    thread = threading.Thread(target=writer)
                    thread.start()
                    try:
                        with mock.patch.dict(sys.modules, _publication_modules(registry, shipped)):
                            if foreign:
                                with self.assertRaises(ValidationError):
                                    hermes_v2._active_discord_adapter_class()
                            else:
                                self.assertIs(shipped, hermes_v2._active_discord_adapter_class())
                    finally:
                        thread.join(3)
                    self.assertFalse(thread.is_alive())
                    self.assertEqual([], errors)
                    self.assertIs(winner, registry._entries["discord"])
                    self.assertNotIn("discord", registry._deferred)

    def test_unload_inverse_does_not_replace_a_newer_entry(self) -> None:
        from tests.v2.test_hermes_portable import FakeLlm, room_config

        shipped = _shipped_discord()
        shipped.__module__ = "plugins.platforms.discord.adapter"
        loader = self._loader()
        state = {"entry": None, "loader": loader}
        recorded: dict[str, object] = {}

        class Registry:
            def current_scope_key(self) -> str:
                return "home"

            def snapshot_registration(self, name: str, *, scope: str | None = None):
                del name
                if scope != "home":
                    return (None, None)
                return (state["entry"], state["loader"])

            def register(self, entry: object, *, scope: str | None = None) -> None:
                del scope
                state["entry"] = entry
                state["loader"] = None

            def restore_registration(
                self,
                name: str,
                current: tuple[object, object],
                previous: tuple[object, object],
                *,
                scope: str | None = None,
            ) -> bool:
                del name, scope
                if (state["entry"], state["loader"]) != current:
                    return False
                state["entry"], state["loader"] = previous
                return True

        def track(*args: object, **kwargs: object) -> None:
            del kwargs
            recorded["current"] = args[4]
            recorded["previous"] = args[5]

        def install(plugin: object) -> None:
            del plugin
            hermes_v2._active_discord_adapter_class()

        registry = Registry()
        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(Path(temporary), llm=FakeLlm([]))
            ctx.manifest = types.SimpleNamespace(name="nunchi")
            ctx._manager = types.SimpleNamespace(
                scope_key="home",
                _plugin_platform_names=set(),
                _track_scoped_registration=track,
                _remove_platform_name_if_unowned=lambda name: None,
            )
            modules = _publication_modules(registry, shipped)
            with mock.patch.dict(sys.modules, modules):
                with mock.patch.object(
                    hermes_v2, "_hermes_version", return_value="0.21.5"
                ):
                    with mock.patch.object(
                        hermes_v2, "_install_host_contract_v1", side_effect=install
                    ):
                        hermes_v2.register(
                            ctx,
                            config_loader=lambda _: config,
                            dashboard_installer=lambda: None,
                        )
        self.assertIn("current", recorded)
        newer = object()
        state["entry"] = newer
        state["loader"] = None
        restored = registry.restore_registration(
            "discord",
            recorded["current"],  # type: ignore[arg-type]
            recorded["previous"],  # type: ignore[arg-type]
            scope="home",
        )
        self.assertFalse(restored)
        self.assertIs(newer, state["entry"])

    def test_minimum_rollback_pop_keeps_a_concurrent_native_entry(self) -> None:
        # Pause before the inverse commit. A native register() that finished
        # there must still be the owner; the commit re-checks under the writer gate.
        published = types.SimpleNamespace(name="discord", adapter_factory=object)
        newer = types.SimpleNamespace(name="discord", adapter_factory=object)
        old_loader = self._loader()
        registry = _MinimumRegistry()
        registry.register(published)

        def writer() -> None:
            registry.register(newer)

        restored = _run_at_source_line(
            hermes_v2._restore_discord_registration,
            "_commit_minimum_discord_inverse(",
            writer,
            lambda: hermes_v2._restore_discord_registration(
                registry, None, (published, None), (None, old_loader)
            ),
        )
        self.assertFalse(restored)
        self.assertIs(newer, registry._entries.get("discord"))
        self.assertNotIn("discord", registry._deferred)

    def test_minimum_rollback_restore_keeps_a_native_entry(self) -> None:
        published = types.SimpleNamespace(name="discord", adapter_factory=object)
        newer = types.SimpleNamespace(name="discord", adapter_factory=object)
        old_loader = self._loader()
        registry = _MinimumRegistry()
        registry.register(published)

        def writer() -> None:
            registry.register(newer)

        restored = _run_at_source_line(
            hermes_v2._restore_discord_registration,
            "_commit_minimum_discord_inverse(",
            writer,
            lambda: hermes_v2._restore_discord_registration(
                registry, None, (published, None), (None, old_loader)
            ),
        )
        self.assertFalse(restored)
        self.assertIs(newer, registry._entries.get("discord"))
        self.assertNotIn("discord", registry._deferred)

    def test_deferred_winner_after_loader_claim_fails_closed(self) -> None:
        shipped = _shipped_discord()
        shipped.__module__ = "plugins.platforms.discord.adapter"
        old_loader = self._loader()
        newer_loader = self._loader()
        registry = _MinimumRegistry()
        registry.register_deferred("discord", old_loader)
        rollbacks: list[object] = []
        token = hermes_v2._REGISTRY_ROLLBACKS.set(rollbacks)
        try:
            with mock.patch.dict(
                sys.modules, _publication_modules(registry, shipped)
            ):

                def writer() -> None:
                    registry.register_deferred("discord", newer_loader)

                with self.assertRaises(ValidationError):
                    _run_at_source_line(
                        hermes_v2._replace_deferred_discord_registration,
                        'entries.setdefault("discord", entry)',
                        writer,
                        hermes_v2._active_discord_adapter_class,
                    )
        finally:
            hermes_v2._REGISTRY_ROLLBACKS.reset(token)
        self.assertEqual([], rollbacks)
        self.assertNotIn("discord", registry._entries)
        self.assertIs(newer_loader, registry._deferred.get("discord"))

    def test_unowned_publication_release_keeps_a_newer_native_entry(self) -> None:
        shipped = _shipped_discord()
        shipped.__module__ = "plugins.platforms.discord.adapter"
        old_loader = self._loader()
        newer_loader = self._loader()
        newer = types.SimpleNamespace(name="discord", adapter_factory=object)
        registry = _MinimumRegistry()

        class GapDeferred(dict):
            def get(self, key, default=None):
                # The claim/insert gap already installed a deferred winner.
                if (
                    key == "discord"
                    and registry._entries.get("discord") is not None
                    and "discord" not in self
                ):
                    self["discord"] = newer_loader
                return super().get(key, default)

        registry._deferred = GapDeferred({"discord": old_loader})
        token = hermes_v2._REGISTRY_ROLLBACKS.set([])
        try:
            with mock.patch.dict(
                sys.modules, _publication_modules(registry, shipped)
            ):

                def writer() -> None:
                    registry.register(newer)

                with self.assertRaises(ValidationError):
                    _run_at_source_line(
                        hermes_v2._release_minimum_discord_entry,
                        "_commit_minimum_entry_release(",
                        writer,
                        hermes_v2._active_discord_adapter_class,
                    )
        finally:
            hermes_v2._REGISTRY_ROLLBACKS.reset(token)
        self.assertIs(newer, registry._entries.get("discord"))
        self.assertNotIn("discord", registry._deferred)

    def _stale_minimum_owner(self):
        published = types.SimpleNamespace(name="discord", adapter_factory=object)
        newer = types.SimpleNamespace(name="discord", adapter_factory=object)
        registry = _ReadableMinimumRegistry()
        registry.register(published)
        registry.register(newer)
        return registry, published, newer

    def _assert_stale_inverse_stays_visible(self, function, operation_for) -> None:
        registry, published, newer = self._stale_minimum_owner()
        lines = _executed_lines(function, lambda: operation_for(registry, published, newer))
        self.assertGreater(len(lines), 0)
        for lineno in lines:
            fresh, fresh_published, fresh_newer = self._stale_minimum_owner()
            observed: list[object] = []
            _run_at_lineno(
                function,
                lineno,
                lambda: observed.append(fresh.get("discord")),
                lambda: operation_for(fresh, fresh_published, fresh_newer),
            )
            self.assertEqual(
                [fresh_newer],
                observed,
                _source_line(function, lineno),
            )
            self.assertIs(fresh_newer, fresh.get("discord"), _source_line(function, lineno))
            self.assertEqual(0, fresh.loader_calls)

    def _assert_stale_inverse_does_not_resurrect(self, function, operation_for) -> None:
        registry, published, newer = self._stale_minimum_owner()
        lines = _executed_lines(function, lambda: operation_for(registry, published, newer))
        self.assertGreater(len(lines), 0)
        for lineno in lines:
            fresh, fresh_published, fresh_newer = self._stale_minimum_owner()
            returned: list[bool] = []
            _run_at_lineno(
                function,
                lineno,
                lambda: returned.append(fresh.unregister("discord")),
                lambda: operation_for(fresh, fresh_published, fresh_newer),
            )
            self.assertEqual([True], returned, _source_line(function, lineno))
            self.assertIsNone(
                fresh.get("discord"),
                _source_line(function, lineno),
            )
            self.assertEqual(0, fresh.loader_calls)

    def test_stale_minimum_rollback_keeps_newer_owner_visible(self) -> None:
        def operation(registry, published, newer):
            del newer
            return hermes_v2._restore_discord_registration(
                registry, None, (published, None), (None, self._loader())
            )

        self._assert_stale_inverse_stays_visible(
            hermes_v2._restore_discord_registration, operation
        )

    def test_stale_minimum_rollback_does_not_resurrect_native_unregister(self) -> None:
        def operation(registry, published, newer):
            del newer
            return hermes_v2._restore_discord_registration(
                registry, None, (published, None), (None, self._loader())
            )

        self._assert_stale_inverse_does_not_resurrect(
            hermes_v2._restore_discord_registration, operation
        )

    def test_stale_minimum_cleanup_keeps_newer_owner_visible(self) -> None:
        def operation(registry, published, newer):
            del newer
            hermes_v2._release_minimum_discord_entry(registry._entries, published)

        self._assert_stale_inverse_stays_visible(
            hermes_v2._release_minimum_discord_entry, operation
        )

    def test_stale_minimum_cleanup_does_not_resurrect_native_unregister(self) -> None:
        def operation(registry, published, newer):
            del newer
            hermes_v2._release_minimum_discord_entry(registry._entries, published)

        self._assert_stale_inverse_does_not_resurrect(
            hermes_v2._release_minimum_discord_entry, operation
        )
