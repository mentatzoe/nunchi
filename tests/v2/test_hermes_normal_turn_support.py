"""Offline regression for isolation between installed normal-turn probes."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

from tests.v2 import hermes_normal_turn_support as support
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


class _InterruptTable(SimpleNamespace):
    """Stand-in for stock ``tools.interrupt``: one bit per thread ident."""

    def __init__(self):
        super().__init__(_lock=threading.Lock(), _interrupted_threads=set(),
                         _interrupt_reasons={}, _yield_threads=set())

    def set_interrupt(self, active, thread_id=None):
        with self._lock:
            assert not active
            self._interrupted_threads.discard(thread_id)
            self._interrupt_reasons.pop(thread_id, None)
            self._yield_threads.discard(thread_id)


class DeadThreadInterruptTests(unittest.TestCase):
    def test_clears_only_bits_whose_thread_exited(self):
        exited = threading.Thread(target=lambda: None)
        exited.start()
        exited.join()
        live = threading.get_ident()
        table = _InterruptTable()
        table._interrupted_threads.update({exited.ident, live})
        table._interrupt_reasons.update({exited.ident: "user interrupt", live: "explicit stop requested"})
        table._yield_threads.add(exited.ident)

        with mock.patch.object(support.importlib, "import_module", return_value=table) as load:
            self.assertEqual([exited.ident], support.clear_dead_thread_interrupts())
        load.assert_called_once_with("tools.interrupt")
        self.assertEqual({live}, table._interrupted_threads)
        self.assertEqual({live: "explicit stop requested"}, table._interrupt_reasons)
        self.assertEqual(set(), table._yield_threads)

    def test_minimum_host_without_yields_is_supported(self):
        exited = threading.Thread(target=lambda: None)
        exited.start()
        exited.join()
        table = _InterruptTable()
        del table._yield_threads, table._interrupt_reasons
        table.set_interrupt = lambda active, thread_id=None: table._interrupted_threads.discard(thread_id)
        table._interrupted_threads.add(exited.ident)

        with mock.patch.object(support.importlib, "import_module", return_value=table):
            self.assertEqual([exited.ident], support.clear_dead_thread_interrupts())
        self.assertEqual(set(), table._interrupted_threads)

    def test_changed_stock_table_fails_loudly(self):
        table = SimpleNamespace(_lock=threading.Lock(), set_interrupt=mock.Mock())
        with mock.patch.object(support.importlib, "import_module", return_value=table):
            with self.assertRaises(AttributeError):
                support.clear_dead_thread_interrupts()
        table.set_interrupt.assert_not_called()
