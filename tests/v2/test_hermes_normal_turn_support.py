"""Offline regression for isolation between installed normal-turn probes."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

from tests.v2.hermes_normal_turn_support import ProbeHost


class ProbeCleanupTests(unittest.TestCase):
    def test_close_drains_cancelled_turn_threads_before_closing_storage(self):
        release = threading.Event()
        started = threading.Event()
        finished = threading.Event()
        pool = ThreadPoolExecutor(max_workers=1)
        self.addCleanup(pool.shutdown)
        self.addCleanup(release.set)

        def worker():
            started.set()
            release.wait(5)
            finished.set()

        pool.submit(worker)
        self.assertTrue(started.wait(1))
        stored_after_worker = []
        host = object.__new__(ProbeHost)
        host.runner = SimpleNamespace(
            _executor=pool, _shutdown_executor=mock.Mock(),
            _async_session_store=SimpleNamespace(close=mock.AsyncMock()),
            session_store=SimpleNamespace(close=lambda: stored_after_worker.append(finished.is_set())),
        )

        async def go():
            closing = asyncio.create_task(host.close())
            await asyncio.sleep(0.05)
            self.assertFalse(closing.done(), "close must wait for the cancelled coroutine's live worker")
            release.set()
            await asyncio.wait_for(closing, 2)

        asyncio.run(go())
        self.assertTrue(finished.is_set())
        self.assertEqual([True], stored_after_worker)
        host.runner._shutdown_executor.assert_called_once_with()
