"""Minimum-host Discord ownership against the real 0.19.0 registry.

These tests skip unless the interpreter is the supported minimum host. They
schedule completed and in-flight native operations around class preparation,
not around the removed map-swap hooks. A synthetic loader is not accepted.
"""

from __future__ import annotations

import importlib._bootstrap as bootstrap
import inspect
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

from nunchi.errors import ValidationError
from nunchi.integrations import hermes_v2


def _minimum_available() -> bool:
    try:
        from gateway.platform_registry import PlatformRegistry
        from hermes_cli.plugins import PluginManager
    except ImportError:
        return False
    del PluginManager
    registry = PlatformRegistry()
    return (
        not callable(getattr(registry, "restore_registration", None))
        and type(registry._entries) is dict
        and type(registry._deferred) is dict
    )


def _line_of(function, fragment: str) -> int:
    lines, start = inspect.getsourcelines(function)
    try:
        return next(start + index for index, line in enumerate(lines) if fragment in line)
    except StopIteration as exc:
        raise AssertionError(f"{fragment!r} not in {function.__name__}") from exc


def _at_line(function, fragment: str, action, body):
    at = _line_of(function, fragment)
    fired: list[bool] = []

    def trace(frame, event, arg):
        del arg
        if (
            event == "line"
            and frame.f_code is function.__code__
            and frame.f_lineno == at
            and not fired
        ):
            fired.append(True)
            action()
        return trace

    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        return body()
    finally:
        sys.settrace(previous)
        assert fired, "scheduling hook was not reached"


@unittest.skipUnless(
    _minimum_available(),
    "real minimum Hermes registry is not installed in this interpreter",
)
class MinimumNamespaceTests(unittest.TestCase):
    def setUp(self) -> None:
        from gateway.platform_registry import PlatformRegistry, PlatformEntry
        import gateway.platform_registry as registry_module
        from hermes_cli.plugins import PluginManager

        self.registry = PlatformRegistry()
        self.PlatformEntry = PlatformEntry
        self.global_patch = patch.object(
            registry_module, "platform_registry", self.registry
        )
        self.global_patch.start()
        self.addCleanup(self.global_patch.stop)
        self.manager = PluginManager()
        shipped = hermes_v2._shipped_discord_adapter_class()
        directory = Path(inspect.getfile(shipped)).resolve().parent
        self.manifest = self.manager._parse_manifest(
            directory / "plugin.yaml", directory, "bundled", ""
        )
        self.assertIsNotNone(self.manifest)
        self.manager._register_deferred_platform(self.manifest)
        self.loader = self.registry._deferred["discord"]
        self.maps = (self.registry._entries, self.registry._deferred)
        self.newer = PlatformEntry(
            "discord", "Native winner", object, lambda: True
        )
        self.rollbacks: list[object] = []
        token = hermes_v2._REGISTRY_ROLLBACKS.set(self.rollbacks)  # type: ignore[arg-type]
        self.addCleanup(hermes_v2._REGISTRY_ROLLBACKS.reset, token)
        holder: list[object] = []
        prep = hermes_v2._MINIMUM_PREPARATION.set(holder)
        self.addCleanup(hermes_v2._MINIMUM_PREPARATION.reset, prep)

    def assert_maps_unchanged(self) -> None:
        self.assertIs(self.maps[0], self.registry._entries)
        self.assertIs(self.maps[1], self.registry._deferred)
        self.assertIs(type(self.registry._entries), dict)
        self.assertNotIn("register", self.registry.__dict__)
        self.assertNotIn("unregister", self.registry.__dict__)
        self.assertNotIn("register_deferred", self.registry.__dict__)
        self.assertEqual([], self.rollbacks)

    def prepare(self):
        prepared = hermes_v2._prepare_minimum_discord_adapter_class(
            self.registry, hermes_v2._shipped_discord_adapter_class()
        )
        return prepared

    def test_prepare_does_not_call_loader_or_publish(self) -> None:
        with patch.object(
            self.manager, "_load_plugin", side_effect=AssertionError("loader invoked")
        ):
            prepared = self.prepare()
            self.assertIsNone(self.registry._entries.get("discord"))
            self.assertIs(self.loader, self.registry._deferred["discord"])
            hermes_v2._rollback_shim_attributes([])
        self.assertIs(self.loader, self.registry._deferred["discord"])
        self.assertTrue(prepared.__module__.endswith(".adapter"))
        self.assert_maps_unchanged()

    def test_native_publication_uses_the_prepared_class(self) -> None:
        from gateway.config import PlatformConfig

        prepared = self.prepare()
        entry = self.registry.get("discord")
        self.assertIsNotNone(entry)
        self.assertEqual("discord-platform", entry.plugin_name)
        selected = hermes_v2._discord_registration_is_shipped(
            entry, hermes_v2._shipped_discord_adapter_class()
        )
        self.assertIs(selected, prepared)
        instance = self.registry.create_adapter(
            "discord", PlatformConfig(enabled=True)
        )
        self.assertIs(type(instance), prepared)
        hermes_v2._rollback_shim_attributes([])
        self.assertIs(entry, self.registry.get("discord"))
        self.assert_maps_unchanged()

    def test_gateway_factory_uses_the_prepared_class(self) -> None:
        from gateway.config import GatewayConfig, Platform, PlatformConfig
        from gateway.run import GatewayRunner

        prepared = self.prepare()
        runner = object.__new__(GatewayRunner)
        runner.config = GatewayConfig()
        instance = runner._create_adapter(
            Platform.DISCORD, PlatformConfig(enabled=True)
        )
        self.assertIs(type(instance), prepared)
        self.assertIs(instance.gateway_runner, runner)
        self.assert_maps_unchanged()

    def test_concrete_owner_and_foreign_rejection(self) -> None:
        entry = self.registry.get("discord")
        prepared = self.prepare()
        self.assertIs(
            hermes_v2._discord_registration_is_shipped(
                entry, hermes_v2._shipped_discord_adapter_class()
            ),
            prepared,
        )
        self.registry.register(self.newer)
        holder = hermes_v2._MINIMUM_PREPARATION.get()
        if isinstance(holder, list):
            holder.clear()
        with self.assertRaises(ValidationError) as raised:
            self.prepare()
        self.assertIn("foreign concrete owner", str(raised.exception))
        self.assertIs(self.newer, self.registry.get("discord"))
        self.assert_maps_unchanged()

    def test_completed_register_survives_patch_rollback(self) -> None:
        self.prepare()
        self.registry.register(self.newer)
        hermes_v2._rollback_shim_attributes([])
        self.assertIs(self.newer, self.registry.get("discord"))
        self.assertIsNone(self.registry._deferred.get("discord"))
        self.assert_maps_unchanged()

    def test_completed_unregister_is_not_resurrected(self) -> None:
        self.prepare()
        entry = self.registry.get("discord")
        self.assertIsNotNone(entry)
        self.assertTrue(self.registry.unregister("discord"))
        hermes_v2._rollback_shim_attributes([])
        self.assertEqual(
            (None, None),
            (
                self.registry._entries.get("discord"),
                self.registry._deferred.get("discord"),
            ),
        )
        self.assert_maps_unchanged()

    def _interleave(self, removing: bool, phase: str) -> None:
        from gateway.platform_registry import PlatformRegistry

        self.prepare()
        self.registry.get("discord")
        native = (
            PlatformRegistry.unregister if removing else PlatformRegistry.register
        )
        fragment = (
            "return self._entries.pop" if removing else "if entry.name in self._entries:"
        )
        entered, resume, done = threading.Event(), threading.Event(), threading.Event()
        results: list[bool] = []
        errors: list[BaseException] = []

        def native_thread() -> None:
            def paused() -> None:
                entered.set()
                if not resume.wait(8):
                    raise AssertionError("native writer not resumed")

            try:
                _at_line(
                    native,
                    fragment,
                    paused,
                    lambda: results.append(self.registry.unregister("discord"))
                    if removing
                    else self.registry.register(self.newer),
                )
            except BaseException as exc:
                errors.append(exc)
            finally:
                done.set()

        thread = threading.Thread(target=native_thread)
        thread.start()
        self.assertTrue(entered.wait(8))

        def complete() -> None:
            resume.set()
            self.assertTrue(done.wait(8), "already-running native writer did not finish")

        try:
            if phase == "rollback":
                _at_line(
                    hermes_v2._rollback_shim_attributes,
                    "for target, name, original, replacement in reversed(patches):",
                    complete,
                    lambda: hermes_v2._rollback_shim_attributes(
                        [(object(), "marker", None, object())]
                    ),
                )
            else:
                holder = hermes_v2._MINIMUM_PREPARATION.get()
                if isinstance(holder, list):
                    holder.clear()

                def body() -> None:
                    try:
                        hermes_v2._prepare_minimum_discord_adapter_class(
                            self.registry,
                            hermes_v2._shipped_discord_adapter_class(),
                        )
                    except ValidationError:
                        pass

                _at_line(
                    hermes_v2._prepare_minimum_discord_adapter_class,
                    "if before[0] is not None:",
                    complete,
                    body,
                )
        finally:
            resume.set()
            thread.join(9)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], errors)
        if removing:
            self.assertEqual([True], results)
            self.assertIsNone(self.registry._entries.get("discord"))
            self.assertIsNone(self.registry._deferred.get("discord"))
        else:
            self.assertIs(self.newer, self.registry.get("discord"))
            self.assertIsNone(self.registry._deferred.get("discord"))
        self.assert_maps_unchanged()

    def test_inflight_register_survives_rollback(self) -> None:
        self._interleave(False, "rollback")

    def test_inflight_unregister_survives_rollback(self) -> None:
        self._interleave(True, "rollback")

    def test_inflight_register_survives_preparation(self) -> None:
        self._interleave(False, "prepare")

    def test_inflight_unregister_survives_preparation(self) -> None:
        self._interleave(True, "prepare")

    def test_foreign_loader_is_not_invoked(self) -> None:
        calls: list[str] = []
        self.registry.unregister("discord")
        loader = lambda: calls.append("foreign")
        self.registry.register_deferred("discord", loader)
        with self.assertRaises(ValidationError) as raised:
            self.prepare()
        self.assertIn("unknown loader", str(raised.exception))
        self.assertEqual([], calls)
        self.assertIs(loader, self.registry._deferred["discord"])
        self.assert_maps_unchanged()

    def test_removed_loader_fails_closed_and_native_reader_finishes(self) -> None:
        from gateway.platform_registry import PlatformRegistry

        errors: list[str] = []

        def resolve_during_gap() -> None:
            try:
                self.prepare()
            except ValidationError as exc:
                errors.append(str(exc))

        entry = _at_line(
            PlatformRegistry._resolve,
            "if loader is None:",
            resolve_during_gap,
            lambda: self.registry.get("discord"),
        )
        self.assertIsNotNone(entry)
        self.assertEqual(1, len(errors))
        self.assertIn("absent or in-progress owner", errors[0])
        self.assertIsNone(self.registry._deferred.get("discord"))
        self.assert_maps_unchanged()

    def test_deferred_replacement_during_import_stays_visible(self) -> None:
        observed: list[object] = []
        errors: list[BaseException] = []

        def newer_loader() -> None:
            self.registry.register(self.newer)

        def reader() -> None:
            try:
                observed.append(self.registry.get("discord"))
            except BaseException as exc:
                errors.append(exc)

        def replace_and_read() -> None:
            self.registry.register_deferred("discord", newer_loader)
            thread = threading.Thread(target=reader)
            thread.start()
            thread.join(8)
            self.assertFalse(thread.is_alive())

        with self.assertRaises(ValidationError) as raised:
            _at_line(
                hermes_v2._prepare_minimum_deferred_class,
                "module = manager._load_directory_module(manifest)",
                replace_and_read,
                self.prepare,
            )
        self.assertIn("changed owner", str(raised.exception))
        self.assertEqual([], errors)
        self.assertEqual([self.newer], observed)
        self.assertIs(self.newer, self.registry.get("discord"))
        self.assertEqual([], self.rollbacks)
        self.assert_maps_unchanged()

    def test_removal_during_import_is_not_resurrected(self) -> None:
        with self.assertRaises(ValidationError):
            _at_line(
                hermes_v2._prepare_minimum_deferred_class,
                "module = manager._load_directory_module(manifest)",
                lambda: self.registry.unregister("discord"),
                self.prepare,
            )
        self.assertIsNone(self.registry._entries.get("discord"))
        self.assertIsNone(self.registry._deferred.get("discord"))
        self.assert_maps_unchanged()

    def test_native_materialization_during_preparation_is_the_same_class(self) -> None:
        seen: list[object] = []
        prepared = _at_line(
            hermes_v2._prepare_minimum_deferred_class,
            "module = manager._load_directory_module(manifest)",
            lambda: seen.append(self.registry.get("discord")),
            self.prepare,
        )
        self.assertIsNotNone(seen[0])
        self.assertIs(
            hermes_v2._discord_registration_is_shipped(
                seen[0], hermes_v2._shipped_discord_adapter_class()
            ),
            prepared,
        )
        hermes_v2._rollback_shim_attributes([])
        self.assertIs(seen[0], self.registry.get("discord"))
        self.assert_maps_unchanged()

    def test_cached_class_survives_native_reregistration(self) -> None:
        prepared = self.prepare()
        self.registry.get("discord")
        self.registry.unregister("discord")
        self.manager._register_deferred_platform(self.manifest)
        entry = self.registry.get("discord")
        self.assertIs(
            hermes_v2._discord_registration_is_shipped(
                entry, hermes_v2._shipped_discord_adapter_class()
            ),
            prepared,
        )
        self.assert_maps_unchanged()

    def test_00_cold_concurrent_import_shares_one_class(self) -> None:
        alias = "hermes_plugins.discord_platform.adapter"
        if alias in sys.modules:
            self.skipTest("cold import requires a process that has not loaded the alias")
        prep_ready, prep_resume = threading.Event(), threading.Event()
        native_ready, native_resume = threading.Event(), threading.Event()
        import_lock_entered = threading.Event()
        prepared: list[type] = []
        entries: list[object] = []
        errors: list[BaseException] = []
        adapter_file = str(
            Path(inspect.getfile(hermes_v2._shipped_discord_adapter_class())).resolve()
        )
        prepare_fn = hermes_v2._prepare_minimum_discord_adapter_class

        def prep_thread() -> None:
            at = _line_of(
                hermes_v2._prepare_minimum_deferred_class,
                "module = manager._load_directory_module(manifest)",
            )

            def trace(frame, event, arg):
                del arg
                if (
                    event == "line"
                    and frame.f_code is hermes_v2._prepare_minimum_deferred_class.__code__
                    and frame.f_lineno == at
                ):
                    prep_ready.set()
                    if not prep_resume.wait(8):
                        raise AssertionError("preparation not resumed")
                if (
                    event == "call"
                    and frame.f_code is bootstrap._ModuleLock.acquire.__code__
                    and frame.f_locals.get("self") is not None
                    and getattr(frame.f_locals["self"], "name", None) == alias
                ):
                    import_lock_entered.set()
                return trace

            sys.settrace(trace)
            try:
                prepared.append(
                    prepare_fn(
                        self.registry, hermes_v2._shipped_discord_adapter_class()
                    )
                )
            except BaseException as exc:
                errors.append(exc)
            finally:
                sys.settrace(None)

        def native_thread() -> None:
            def trace(frame, event, arg):
                del arg
                if (
                    event == "line"
                    and frame.f_code.co_filename == adapter_file
                    and frame.f_globals.get("__name__") == alias
                    and not native_ready.is_set()
                ):
                    native_ready.set()
                    if not native_resume.wait(8):
                        raise AssertionError("native import not resumed")
                return trace

            sys.settrace(trace)
            try:
                entries.append(self.registry.get("discord"))
            except BaseException as exc:
                errors.append(exc)
            finally:
                sys.settrace(None)

        first = threading.Thread(target=prep_thread)
        second = threading.Thread(target=native_thread)
        first.start()
        try:
            self.assertTrue(prep_ready.wait(8))
            second.start()
            self.assertTrue(native_ready.wait(8))
            prep_resume.set()
            self.assertTrue(
                import_lock_entered.wait(8),
                "preparation did not use the native import lock",
            )
        finally:
            prep_resume.set()
            native_resume.set()
            first.join(9)
            if second.ident is not None:
                second.join(9)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual([], errors)
        self.assertEqual(1, len(prepared))
        self.assertEqual(1, len(entries))
        self.assertIs(
            hermes_v2._discord_registration_is_shipped(
                entries[0], hermes_v2._shipped_discord_adapter_class()
            ),
            prepared[0],
        )
        self.assert_maps_unchanged()


if __name__ == "__main__":
    unittest.main(verbosity=2)
