"""Installed stock startup, with network and background-service doubles only.

Unlike the normal-turn fixture this executes GatewayRunner.start() and native
adapter creation, wiring, owner assignment and connection timeout selection.
No live platform, provider, bootstrap identity or watcher is started.
"""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
import importlib.util
import inspect
import os
import socket
from types import MethodType
import unittest
from unittest import mock

from tests.v2 import hermes_normal_turn_support as sup


@unittest.skipUnless(os.environ.get("NUNCHI_REQUIRE_HERMES_NORMAL_TURN") == "1",
                     "requires installed stock Hermes startup probe")
class InstalledStartupTests(unittest.TestCase):
    def test_native_start_and_reconnect_preserve_owner_and_budgets(self):
        sup.scrub_ambient_environment()
        tmp, home = sup.new_home()
        self.addCleanup(tmp.cleanup)
        os.environ.update(HERMES_HOME=str(home), DISCORD_BOT_TOKEN="probe-token-not-a-secret",
                          DISCORD_ALLOWED_USERS="100", DISCORD_AUTO_THREAD="false")
        server = sup.FakeOpenAIServer()
        self.addCleanup(server.close)
        multiplex = os.environ.get("NUNCHI_PROBE_MULTIPLEX") == "1"
        sup.write_hermes_home(home, model_base_url=server.base_url, enable_nunchi=True,
                              extra_config={"gateway": {"multiplex_profiles": True if multiplex else None}})
        if multiplex:
            secondary_home = home / "profiles" / "secondary"
            sup.write_hermes_home(secondary_home, model_base_url=server.base_url, enable_nunchi=False)
            (secondary_home / ".env").write_text(
                "DISCORD_BOT_TOKEN=secondary-probe-token\nDISCORD_ALLOWED_USERS=100\n")
        sup.write_nunchi_config(home)
        # Stock releases start this optional binary downloader during tool
        # bootstrap; Hermes main dropped it (config v50). Stub installation
        # only; no tool/approval execution is replaced.
        if importlib.util.find_spec("tools.tirith_security") is not None:
            installer = mock.patch("tools.tirith_security.ensure_installed", return_value=None)
            installer.start()
            self.addCleanup(installer.stop)
        loaded = sup.load_nunchi_via_plugin_manager()
        self.addCleanup(sup.unload_nunchi, loaded)
        self.assertIsNone(loaded["state"]["error"])
        import gateway.run as gateway_run
        from gateway.config import Platform
        from gateway.run import GatewayRunner
        from nunchi.integrations import hermes_v2
        gateway_run._hermes_home = home
        runner = GatewayRunner()
        original_create = runner._create_adapter
        connections = []
        budgets = []
        external_attempts = []
        original_budget = runner._platform_connect_timeout_secs

        def budget(*args, **kwargs):
            budgets.append((args[0].value if args else None, kwargs))
            return original_budget(*args, **kwargs)

        async def connect(adapter, *, is_reconnect=False):
            self.assertTrue(callable(adapter._message_handler))
            self.assertTrue(callable(adapter._authorization_check))
            self.assertIs(adapter._session_store, runner.session_store)
            connections.append((adapter, is_reconnect,
                                getattr(adapter, hermes_v2._ADAPTER_PROFILE_ATTRIBUTE, None)))
            adapter._client = sup.FakeDiscordClient(bot_user_id=999)
            adapter._ready_event.set()
            adapter._running = True
            return True

        async def go():
            with ExitStack() as stack:
                def create(*args, **kwargs):
                    # Stock may load a fresh class for each profile. Wrap the
                    # native factory, replacing only the network connection on
                    # every returned instance, never its ownership/wiring.
                    adapter = original_create(*args, **kwargs)
                    if adapter is not None:
                        adapter.connect = MethodType(connect, adapter)
                    return adapter

                native_connect = socket.socket.connect

                def loopback_only(sock, address):
                    if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1"}:
                        external_attempts.append(address)
                        raise AssertionError(f"startup attempted external connection: {address}")
                    return native_connect(sock, address)

                stack.enter_context(mock.patch.object(socket.socket, "connect", loopback_only))
                stack.enter_context(mock.patch.object(runner, "_create_adapter", create))
                stack.enter_context(mock.patch.object(runner, "_platform_connect_timeout_secs", budget))
                # These services are independent of adapter ownership/connection.
                # Do not run remote warm-up, identity bootstrap or perpetual jobs.
                for name in ("_spawn_supervised", "_start_startup_warmup", "_start_free_tier_bootstrap",
                             "_start_loop_heartbeat_task", "_start_heartbeat_poller"):
                    if hasattr(runner, name):
                        stack.enter_context(mock.patch.object(runner, name, return_value=None))
                if hasattr(runner, "_ensure_hosted_room_worker"):
                    stack.enter_context(mock.patch.object(runner, "_ensure_hosted_room_worker", new=mock.AsyncMock()))
                try:
                    self.assertTrue(await runner.start())
                    self.assertEqual(2 if multiplex else 1, len(connections), runner._failed_platforms)
                    adapter = runner.adapters[Platform.DISCORD]
                    self.assertIs(connections[0][0], adapter)
                    self.assertEqual((False, "default"), connections[0][1:])
                    if multiplex:
                        secondary = runner._profile_adapters["secondary"][Platform.DISCORD]
                        self.assertIs(connections[1][0], secondary)
                        self.assertEqual((False, "secondary"), connections[1][1:])
                    self.assertTrue(await runner._connect_adapter_with_timeout(
                        adapter, Platform.DISCORD, is_reconnect=True))
                    self.assertEqual((True, "default"), connections[-1][1:])
                    if "initial" in inspect.signature(original_budget).parameters:
                        self.assertEqual([("discord", {"initial": True})] * (2 if multiplex else 1)
                                         + [("discord", {"initial": False})], budgets)
                    # Real native secondary-profile wiring must not be overwritten
                    # with the launch owner by the connection shim.
                    secondary = runner._create_adapter(Platform.DISCORD, runner.config.platforms[Platform.DISCORD])
                    runner._configure_profile_adapter(secondary, "secondary", Platform.DISCORD)
                    self.assertTrue(await runner._connect_adapter_with_timeout(
                        secondary, Platform.DISCORD, is_reconnect=True))
                    self.assertEqual((True, "secondary"), connections[-1][1:])
                    self.assertEqual([], external_attempts)
                finally:
                    for task in list(getattr(runner, "_background_tasks", ())):
                        task.cancel()
                    tasks = list(getattr(runner, "_background_tasks", ()))
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
                    store = runner.session_store
                    close = getattr(store, "close_all_db_handles", None)
                    if close:
                        close()
                    elif getattr(store, "_db", None) is not None:
                        store._db.close()
        sup.run(go(), timeout=60)
