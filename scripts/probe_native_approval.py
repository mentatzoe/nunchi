"""Installed-host native guard reachability probe, no command execution/network.

Run with a disposable stock interpreter and Nunchi wheel installed, using -I.
Only the opportunity state and human answer are controlled; command guards,
approval queues/waits and interrupt functions are the actual host implementation.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace


def main() -> None:
    # Run in a child process: host modules bind their home at import time.
    for name in list(os.environ):
        if name.startswith(("HERMES_", "GATEWAY_", "DISCORD_", "OPENAI_", "OPENROUTER_", "ANTHROPIC_")):
            os.environ.pop(name, None)
    with tempfile.TemporaryDirectory(prefix="nunchi-approval-") as directory:
        os.environ["HERMES_HOME"] = directory
        os.environ["HERMES_SESSION_PLATFORM"] = "discord"
        Path(directory, "config.yaml").write_text("approvals:\n  mode: manual\n  timeout: 5\nplugins:\n  enabled: []\n")
        from tools import approval, interrupt
        from nunchi.integrations.hermes_tools import install_approval_boundary

        local = threading.local()
        patches = []
        def setter(target, name, value):
            patches.append((target, name, getattr(target, name)))
            setattr(target, name, value)
        install_approval_boundary(lambda: getattr(local, "trace", None), lambda: False, setter, [])
        report = {"host": importlib.metadata.version("hermes-agent"),
                  "approval_origin": approval.__file__, "cases": {}}
        try:
            for case in ("approve", "deny", "expired_approve", "interrupt", "fallthrough"):
                session = "nunchi-probe-" + case
                parked = threading.Event()
                token = SimpleNamespace(cancel_event=threading.Event())
                runtime = SimpleNamespace(_lock=threading.RLock(), scheduler=SimpleNamespace(is_current=lambda _: True))
                trace = SimpleNamespace(runtime=runtime, token=token, deadline=time.monotonic() + 30)
                runtime._active_trace = trace
                runtime.expire_stock_turn = lambda _: token.cancel_event.set()
                outcome = {}
                approval.register_gateway_notify(session, lambda _: parked.set())
                def worker():
                    local.trace = None if case == "fallthrough" else trace
                    session_token = approval.set_current_session_key(session)
                    try:
                        outcome.update(approval.check_all_command_guards("rm -rf /tmp/nunchi-probe-never-executed", "local"))
                    finally:
                        approval.reset_current_session_key(session_token)
                        interrupt.set_interrupt(False)
                thread = threading.Thread(target=worker)
                thread.start()
                try:
                    assert parked.wait(10), (case, outcome)
                    if case == "expired_approve":
                        trace.deadline = 0
                    if case == "interrupt":
                        interrupt.set_interrupt(True, thread.ident)
                    else:
                        approval.resolve_gateway_approval(session, "deny" if case == "deny" else "once")
                    thread.join(10)
                    assert not thread.is_alive(), case
                    expected = case in {"approve", "fallthrough"}
                    assert outcome.get("approved") is expected, (case, outcome)
                    assert not approval._gateway_queues.get(session), case
                    report["cases"][case] = {"approved": outcome["approved"], "queue_clean": True}
                finally:
                    interrupt.set_interrupt(True, thread.ident)
                    thread.join(10)
                    interrupt.set_interrupt(False, thread.ident)
                    approval.clear_session(session)
            print(json.dumps(report, indent=2))
        finally:
            for target, name, original in reversed(patches):
                setattr(target, name, original)
            assert all(getattr(target, name) is original for target, name, original in patches)


if __name__ == "__main__":
    main()
