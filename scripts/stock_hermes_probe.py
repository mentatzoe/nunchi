"""Private child of verify_stock_hermes.py; never a live-profile launcher."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import traceback
import unittest
from unittest import mock

LANES = {
    "contract": (["tests.v2.test_hermes_installed_contract"], 4),
    "normal-attention": (["tests.v2.test_hermes_normal_turn",
                          "tests.v2.test_hermes_attention_setup_installed"], 28),
    "startup-single": (["tests.v2.test_hermes_startup_installed"], 1),
    "startup-multiplex": (["tests.v2.test_hermes_startup_installed"], 1),
}


def network_guard(attempts):
    """Audit socket operations, including DNS/UDP and calls caught by the host.

    This is an in-process deterministic-test fence, not an OS sandbox for
    adversarial subprocesses. Only numeric loopback endpoints and Unix sockets
    are permitted. Every denied attempt also makes the whole lane fail.
    """
    def audit(event, args):
        address = None
        if event in {"socket.connect", "socket.sendto"}:
            address = args[-1]
            if not isinstance(address, tuple):  # local Unix socket
                return
            host = address[0]
        elif event == "socket.getaddrinfo":
            host = args[0]
        elif event in {"socket.gethostbyname", "socket.gethostbyaddr"}:
            host = args[0]
        else:
            return
        if host not in {"127.0.0.1", "::1", b"127.0.0.1", b"::1"}:
            detail = {"event": event, "host": str(host)}
            attempts.append(detail)
            print("BLOCKED_NETWORK", json.dumps(detail), flush=True)
            traceback.print_stack()
            raise AssertionError("external network forbidden in stock verification")
    return audit


def assert_origins(host_source, host_mode):
    import nunchi
    import hermes_cli
    prefix = Path(sys.prefix).resolve()
    plugin = Path(nunchi.__file__).resolve()
    host = Path(hermes_cli.__file__).resolve()
    assert plugin.is_relative_to(prefix), f"Nunchi not installed: {plugin}"
    direct = json.loads(importlib.metadata.distribution("nunchi").read_text("direct_url.json") or "{}")
    assert not direct.get("dir_info", {}).get("editable"), "editable Nunchi forbidden"
    assert "PYTHONPATH" not in os.environ and sys.flags.isolated
    expected = prefix if host_mode == "wheel" else host_source
    assert host.is_relative_to(expected), f"wrong stock runtime: {host}"
    host_direct = json.loads(importlib.metadata.distribution("hermes-agent").read_text("direct_url.json") or "{}")
    if host_mode == "wheel":
        assert not host_direct.get("dir_info", {}).get("editable")
    from nunchi.integrations.hermes_version import hermes_version
    return {"nunchi": str(plugin), "hermes_cli": str(host), "hermes_version": hermes_version()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=LANES, required=True)
    parser.add_argument("--host-mode", choices=("wheel", "source"), required=True)
    parser.add_argument("--hermes-source", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    attempts = []
    result = {"lane": args.lane, "external_attempts": attempts, "success": False}
    sys.addaudithook(network_guard(attempts))
    try:
        result["origins"] = assert_origins(args.hermes_source.resolve(), args.host_mode)
        print("ORIGINS", json.dumps(result["origins"]), flush=True)
        root = Path(__file__).resolve().parent
        # Explicit tests-only path, never Nunchi implementation/PYTHONPATH.
        sys.path.insert(0, str(root))
        with ExitStack() as stack:
            # Reviewed optional security-download/remote-metadata doubles.
            # Stock native participant, tool dispatch and approval are untouched.
            stack.enter_context(mock.patch("tools.tirith_security.ensure_installed", return_value=None))
            security = importlib.import_module("tools.tirith_security")
            # Moving main moved acquisition into PM. Double its optional
            # acquisition boundary, never scan_command or native approval.
            download = "_download_file" if hasattr(security, "_download_file") else "_background_install"
            stack.enter_context(mock.patch.object(security, download,
                                                  side_effect=OSError("offline: optional download unavailable")))
            result["doubles"] = ["tools.tirith_security.ensure_installed",
                                 f"tools.tirith_security.{download}",
                                 "agent.model_metadata.fetch_model_metadata"]
            stack.enter_context(mock.patch("agent.model_metadata.fetch_model_metadata", return_value={}))
            # Stock runtime imports can prepend the host tree (and its tests).
            sys.path.remove(str(root))
            sys.path.insert(0, str(root))
            tests = importlib.import_module("tests")
            assert Path(tests.__file__).resolve() == root / "tests" / "__init__.py"
            modules, expected = LANES[args.lane]
            suite = unittest.defaultTestLoader.loadTestsFromNames(modules)

            class Result(unittest.TextTestResult):
                def addFailure(self, test, err):
                    super().addFailure(test, err)
                    server = getattr(test, "server", None)
                    if server:
                        print("FAILED_REQUEST_BODIES", test.id(), json.dumps(server.bodies()), flush=True)

            run = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(suite)
            # Check after dispatch too: imports must not migrate to either
            # checkout while stock runtime bootstrap changes sys.path.
            plugin_root = Path(sys.prefix).resolve()
            for name, module in tuple(sys.modules.items()):
                if name == "nunchi" or name.startswith("nunchi."):
                    origin = getattr(module, "__file__", None)
                    if origin:
                        assert Path(origin).resolve().is_relative_to(plugin_root), (name, origin)
            result.update(tests_run=run.testsRun, expected_tests=expected,
                          failures=len(run.failures), errors=len(run.errors),
                          skipped=[(str(test), reason) for test, reason in run.skipped])
            result["success"] = (run.wasSuccessful() and run.testsRun == expected
                                 and not run.skipped and not attempts)
    except Exception:
        result["error"] = traceback.format_exc()
        traceback.print_exc()
    finally:
        if attempts:
            result["success"] = False
        print("EXTERNAL_ATTEMPTS", json.dumps(attempts), flush=True)
        args.result.write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
