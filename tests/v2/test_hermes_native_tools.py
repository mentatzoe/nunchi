"""Native invocation commitment; host authority remains inside next_call."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

from nunchi.integrations import hermes_v2
from nunchi.integrations import hermes_tools
from tests.v2.test_hermes_portable import FakeAdapter, FakeEvent, FakeLlm, judgment, room_config


class NativeToolTests(unittest.TestCase):
    @contextmanager
    def active_turn(self):
        with tempfile.TemporaryDirectory() as temporary:
            config, ctx = room_config(Path(temporary), llm=FakeLlm([judgment("WAKE", "discord:message:500")]))
            plugin = hermes_v2.NunchiHermesV2Plugin(config=config, ctx=ctx, hermes_version="0.19.0", mode="process-local-gate")
            event = FakeEvent()
            asyncio.run(plugin.gate_ingress(adapter=FakeAdapter(), event=event, stock_handle=mock.AsyncMock()))
            runtime = plugin._rooms[("discord", "42")]
            trace = runtime.stock_trace(event)
            self.assertIsNotNone(trace)
            middleware = types.ModuleType("hermes_cli.middleware")
            middleware.run_llm_execution_middleware = lambda request, next_call, **context: next_call(request)
            middleware.run_tool_execution_middleware = lambda tool_name, args, next_call, **context: next_call(args)
            host = types.ModuleType("hermes_cli")
            host.middleware = middleware
            patches = []
            owner = hermes_v2._SHIM_OWNER
            hermes_v2._SHIM_OWNER = None
            token = hermes_v2._ACTIVE_STOCK_TURN.set(trace)
            patch_token = hermes_v2._PATCH_TRANSACTION.set(patches)
            try:
                with mock.patch.dict(sys.modules, {"hermes_cli": host, "hermes_cli.middleware": middleware}):
                    hermes_v2._install_execution_boundary_shim(plugin)
                yield plugin, runtime, trace, middleware
            finally:
                hermes_v2._PATCH_TRANSACTION.reset(patch_token)
                hermes_v2._ACTIVE_STOCK_TURN.reset(token)
                hermes_v2._rollback_shim_attributes(patches)
                hermes_v2._SHIM_OWNER = owner

    def invoke(self, middleware, native, **overrides):
        context = dict(session_id="native-session", turn_id="native-turn", tool_call_id="call-1")
        context.update(overrides)
        return middleware.run_tool_execution_middleware("read_file", {"path": "safe.txt"}, native, **context)

    def test_valid_tool_runs_native_once_and_reserves_unknown_before_handoff(self):
        with self.active_turn() as (plugin, runtime, trace, middleware):
            self.assertIsNone(plugin.pre_tool_call(tool_name="read_file"))
            calls = []
            def native(args):
                calls.append(args)
                records = runtime.native_invocations.records()
                self.assertEqual(1, len(records))
                self.assertEqual("committed", records[0]["invocation"])
                self.assertEqual("unknown", records[0]["effect"])
                return "native tool output"
            self.assertEqual("native tool output", self.invoke(middleware, native))
            self.assertIn("error", json.loads(self.invoke(middleware, native)))
            self.assertEqual([{"path": "safe.txt"}], calls)
            record = runtime.native_invocations.records()[0]
            self.assertEqual("returned", record["invocation"])
            self.assertEqual("unknown", record["effect"])
            self.assertEqual("read_file", record["binding"]["tool_name"])
            self.assertEqual("native-turn", record["binding"]["turn_id"])

    def test_concurrent_distinct_native_calls_reserve_and_finish_without_loss(self):
        with self.active_turn() as (_, runtime, trace, middleware), ThreadPoolExecutor(2) as pool:
            # Repeat the actual middleware lock order: reserve under _lock,
            # run the host outside it, finish under it again.
            assert trace is not None
            trace.deadline += 30
            calls = []
            for batch in range(20):
                start = threading.Barrier(2)
                def invoke(call_id):
                    start.wait(timeout=2)
                    return self.invoke(middleware, lambda args: calls.append(call_id) or call_id,
                                       tool_call_id=call_id)
                ids = [f"batch-{batch}-{slot}" for slot in range(2)]
                futures = [pool.submit(copy_context().run, invoke, identity) for identity in ids]
                self.assertEqual(ids, [future.result(timeout=3) for future in futures])
            records = runtime.native_invocations.records()
            self.assertEqual(40, len(records))
            self.assertEqual(40, len(set(calls)))
            self.assertTrue(all(record["invocation"] == "returned" for record in records))
            self.assertTrue(all(record["effect"] == "unknown" for record in records))
            self.assertEqual({}, runtime._native_threads)

    def test_a_slow_finish_does_not_refuse_another_call(self):
        with self.active_turn() as (_, runtime, trace, middleware), ThreadPoolExecutor(2) as pool:
            assert trace is not None
            trace.deadline += 30
            journal = runtime.native_invocations
            original_finish = journal.finish
            finishing = threading.Event()
            slow = [True]
            def finish(identity, invocation):
                if slow and slow.pop():
                    # A slow disk: hold SQLite's write lock past the journal's
                    # 0.25 s budget while another call reserves.
                    with journal._connect(write=True):
                        finishing.set()
                        time.sleep(0.6)
                original_finish(identity, invocation)
            with mock.patch.object(journal, "finish", finish):
                first = pool.submit(copy_context().run, self.invoke, middleware,
                                    lambda args: "first", tool_call_id="first")
                self.assertTrue(finishing.wait(timeout=3))
                second = pool.submit(copy_context().run, self.invoke, middleware,
                                     lambda args: "second", tool_call_id="second")
                self.assertEqual(["first", "second"], [first.result(timeout=5), second.result(timeout=5)])
            records = runtime.native_invocations.records()
            self.assertEqual(["returned", "returned"], [record["invocation"] for record in records])

    def test_cancellation_interrupts_only_registered_native_threads_without_clearing(self):
        with self.active_turn() as (_, runtime, trace, middleware):
            calls = []
            runtime._native_interrupt = lambda active, tid: calls.append((active, tid))
            def native(args):
                runtime.cancel()
                return "native result"
            self.invoke(middleware, native)
            self.assertEqual([(True, threading.get_ident())], calls)
            runtime.cancel()
            self.assertEqual(1, len(calls))
            self.assertEqual({}, runtime._native_threads)

    def test_post_approval_check_rejects_expired_native_once_choice(self):
        with self.active_turn() as (_, runtime, trace, middleware):
            approval = types.ModuleType("tools.approval")
            interrupt = types.ModuleType("tools.interrupt")
            def set_interrupt(active, thread_id=None):
                pass
            def is_interrupted():
                return False
            def _await_gateway_decision(session_key, notify_cb, approval_data, *, surface="gateway"):
                is_interrupted()
                trace.deadline = 0
                return {"resolved": True, "choice": "once", "reason": None}
            _await_gateway_decision.__module__ = approval.__name__
            approval._await_gateway_decision = _await_gateway_decision
            interrupt.set_interrupt = set_interrupt
            interrupt.is_interrupted = is_interrupted
            tools = types.ModuleType("tools")
            tools.approval, tools.interrupt = approval, interrupt
            with mock.patch.dict(sys.modules, {"tools": tools, "tools.approval": approval, "tools.interrupt": interrupt}):
                install = getattr(hermes_tools, "install_approval_boundary", None)
                self.assertTrue(callable(install), "native post-wait deadline boundary is missing")
                install(hermes_v2._ACTIVE_STOCK_TURN.get, hermes_v2._CONFIGURED_ROUTE_CONTEXT.get,
                        hermes_v2._set_shim_attribute, [runtime])
                result = approval._await_gateway_decision("session", None, {})
            self.assertEqual("deny", result["choice"])
            self.assertTrue(trace.token.cancel_event.is_set())

    def test_stale_and_missing_identity_never_call_native(self):
        for condition in ("cancelled", "deadline", "missing_id"):
            with self.subTest(condition=condition), self.active_turn() as (_, runtime, trace, middleware):
                native = mock.Mock()
                context = {}
                if condition == "cancelled":
                    runtime.cancel()
                elif condition == "deadline":
                    trace.deadline = 0
                else:
                    context["tool_call_id"] = ""
                self.assertIn("error", json.loads(self.invoke(middleware, native, **context)))
                native.assert_not_called()

    def test_persistence_failure_or_expiry_during_commit_prevents_handoff(self):
        for condition in ("failure", "expired"):
            with self.subTest(condition=condition), self.active_turn() as (_, runtime, trace, middleware):
                reserve = runtime.native_invocations.reserve
                def delayed(identity, binding):
                    if condition == "failure":
                        raise hermes_tools.PersistenceError("unavailable")
                    result = reserve(identity, binding)
                    trace.deadline = 0
                    return result
                native = mock.Mock()
                with mock.patch.object(runtime.native_invocations, "reserve", side_effect=delayed):
                    self.assertIn("error", json.loads(self.invoke(middleware, native)))
                native.assert_not_called()
                self.assertEqual({}, runtime._native_threads)

    def test_native_denial_is_returned_unchanged_not_claimed_as_effect(self):
        with self.active_turn() as (_, runtime, trace, middleware):
            denied = {"approved": False, "message": "native policy refused"}
            native = mock.Mock(return_value=denied)
            self.assertIs(denied, self.invoke(middleware, native))
            native.assert_called_once()
            self.assertEqual("unknown", runtime.native_invocations.records()[0]["effect"])

    def test_exception_is_durably_reserved_across_ledger_reopen(self):
        with self.active_turn() as (_, runtime, trace, middleware):
            native = mock.Mock(side_effect=RuntimeError("native failed"))
            with self.assertRaisesRegex(RuntimeError, "native failed"):
                self.invoke(middleware, native)
            runtime.native_invocations = hermes_tools.NativeInvocationJournal(runtime.native_invocations.path)
            self.assertIn("error", json.loads(self.invoke(middleware, native)))
            native.assert_called_once()
            self.assertEqual("raised", runtime.native_invocations.records()[0]["invocation"])
            self.assertEqual({}, runtime._native_threads)

    def test_arguments_are_snapshotted_and_not_stored_in_cleartext(self):
        with self.active_turn() as (_, runtime, trace, middleware):
            args = {"path": "sensitive-private-path"}
            def native(payload):
                self.assertIsNot(args, payload)
                self.assertEqual(args, payload)
                payload["path"] = "mutated"
                return "ok"
            middleware.run_tool_execution_middleware(
                "read_file", args, native, session_id="session", turn_id="turn", tool_call_id="call"
            )
            self.assertEqual("sensitive-private-path", args["path"])
            self.assertNotIn("sensitive-private-path", json.dumps(runtime.native_invocations.records()))

    def test_unconfigured_route_falls_through_but_orphan_configured_work_is_denied(self):
        with self.active_turn() as (_, runtime, trace, middleware):
            active = hermes_v2._ACTIVE_STOCK_TURN.set(None)
            configured = hermes_v2._CONFIGURED_ROUTE_CONTEXT.set(False)
            try:
                native = mock.Mock(return_value="stock")
                self.assertEqual("stock", self.invoke(middleware, native))
                hermes_v2._CONFIGURED_ROUTE_CONTEXT.set(True)
                self.assertIn("error", json.loads(self.invoke(middleware, native)))
                native.assert_called_once()
                self.assertEqual([], runtime.native_invocations.records())
            finally:
                hermes_v2._CONFIGURED_ROUTE_CONTEXT.reset(configured)
                hermes_v2._ACTIVE_STOCK_TURN.reset(active)

    def test_current_approval_helper_post_wait_expiry_and_rollback(self):
        with self.active_turn() as (_, runtime, trace, middleware):
            approval = types.ModuleType("tools.approval")
            gateway = types.ModuleType("tools.approval_gateway_wait")
            interrupt = types.ModuleType("tools.interrupt")
            def _await_gateway_decision():
                pass
            _await_gateway_decision.__module__ = gateway.__name__
            approval._await_gateway_decision = gateway._await_gateway_decision = _await_gateway_decision
            def is_interrupted():
                return False
            def _poll_event(event, session_key, *, interrupt_log):
                is_interrupted()
                trace.deadline = 0
                return "set"
            _poll_event.__module__ = gateway.__name__
            gateway._poll_event = _poll_event
            interrupt.set_interrupt = lambda active, thread_id=None: None
            interrupt.is_interrupted = is_interrupted
            modules = {"tools.approval": approval, "tools.approval_gateway_wait": gateway, "tools.interrupt": interrupt}
            with mock.patch.dict(sys.modules, modules):
                hermes_tools.install_approval_boundary(
                    hermes_v2._ACTIVE_STOCK_TURN.get, hermes_v2._CONFIGURED_ROUTE_CONTEXT.get,
                    hermes_v2._set_shim_attribute, [runtime],
                )
                self.assertEqual("interrupted", gateway._poll_event(None, "session", interrupt_log="test"))
            self.assertTrue(trace.token.cancel_event.is_set())

    def test_foreign_native_approval_shape_is_rejected_before_patching(self):
        approval = types.ModuleType("tools.approval")
        approval._await_gateway_decision = lambda: None
        with mock.patch.dict(sys.modules, {"tools.approval": approval, "tools.interrupt": types.ModuleType("tools.interrupt")}):
            setter = mock.Mock()
            with self.assertRaisesRegex(hermes_tools.ValidationError, "unsupported Hermes"):
                hermes_tools.install_approval_boundary(lambda: None, lambda: False, setter, [])
            setter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
