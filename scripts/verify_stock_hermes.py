#!/usr/bin/env python3
"""Exercise installed packages outside Nunchi's checkout, with disposable homes.

Run with the host environment's Python after installing a Nunchi wheel. New
Hermes releases intentionally require a source-installed runtime; --host-mode
records that distinction instead of calling an editable host a wheel proof.
No provider or platform credentials are inherited. This checks discovery and
the installed contract, not authenticated normal-turn or live-room behaviour.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone


def source_identity(root):
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    names = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"]).split(b"\0")
    digest = hashlib.sha256()
    for name in sorted(filter(None, names)):
        path = root / os.fsdecode(name)
        digest.update(name + b"\0" + path.read_bytes() + b"\0")
    clean = all(subprocess.run(["git", "-C", str(root), *args], check=False).returncode == 0
                for args in (("diff", "--exit-code"), ("diff", "--cached", "--exit-code")))
    return {"commit": commit, "source_sha256": digest.hexdigest(), "tracked_clean": clean}


def distribution_identity(name):
    dist = importlib.metadata.distribution(name)
    digest = hashlib.sha256()
    for relative in sorted(dist.files or (), key=str):
        path = Path(str(dist.locate_file(relative)))
        if path.is_file():
            digest.update(str(relative).encode() + b"\0" + path.read_bytes() + b"\0")
    return {"version": dist.version, "sha256": digest.hexdigest()}


def probe(args):
    # This process has no checkout on its import path. Test-only fixtures are
    # copied alongside it; implementation is loaded solely from the installation.
    nunchi = importlib.import_module("nunchi")
    hermes_cli = importlib.import_module("hermes_cli")
    from nunchi.integrations.hermes_version import hermes_version

    prefix = Path(sys.prefix).resolve()
    assert nunchi.__file__ and hermes_cli.__file__
    plugin = Path(nunchi.__file__).resolve()
    host = Path(hermes_cli.__file__).resolve()
    assert plugin.is_relative_to(prefix), f"Nunchi not installed: {plugin}"
    direct = json.loads(importlib.metadata.distribution("nunchi").read_text("direct_url.json") or "{}")
    assert not direct.get("dir_info", {}).get("editable"), "editable Nunchi is not an artifact proof"
    assert "PYTHONPATH" not in os.environ
    if args.host_mode == "wheel":
        assert host.is_relative_to(prefix), f"Hermes not installed from wheel: {host}"
        host_direct = json.loads(importlib.metadata.distribution("hermes-agent").read_text("direct_url.json") or "{}")
        assert not host_direct.get("dir_info", {}).get("editable")
    else:
        assert host.is_relative_to(args.hermes_source), f"wrong stock runtime: {host}"
    print(json.dumps({"nunchi_origin": str(plugin), "hermes_origin": str(host),
                      "host_mode": args.host_mode, "hermes_version": hermes_version()}, sort_keys=True), flush=True)
    import unittest
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.v2.test_hermes_installed_contract")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() and result.testsRun >= 4 and not result.skipped else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-source", type=Path, required=True)
    parser.add_argument("--host-mode", choices=("wheel", "source"), required=True)
    parser.add_argument("--platform", choices=("discord", "telegram"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--probe", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.hermes_source = args.hermes_source.resolve()
    if args.probe:
        return probe(args)

    repo = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    before = {"host": source_identity(args.hermes_source),
              "distribution": distribution_identity("hermes-agent")}
    receipt = {"started_at": datetime.now(timezone.utc).isoformat(),
               "platform": args.platform, "host_mode": args.host_mode,
               "python": sys.version, "before": before,
               "nunchi": distribution_identity("nunchi"),
               "normal_authenticated_turn": "not exercised by this contract probe"}
    with tempfile.TemporaryDirectory(prefix="nunchi-stock-") as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir()
        hermes_home = home / ".hermes"
        hermes_home.mkdir()
        shutil.copytree(repo / "tests", root / "tests", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        script = root / "verify_stock_hermes.py"
        shutil.copyfile(__file__, script)
        # Allowlist, not a credential-name blacklist. Do not inherit profile,
        # model keys, PYTHONPATH, install-root overrides or Git worktree settings.
        env = {"PATH": os.environ.get("PATH", os.defpath), "HOME": str(home),
               "HERMES_HOME": str(hermes_home), "PYTHONNOUSERSITE": "1",
               "PYTHONDONTWRITEBYTECODE": "1", "NUNCHI_REQUIRE_HERMES_CONTRACT": "1",
               "NUNCHI_HERMES_PLATFORM": args.platform, "TMPDIR": str(root),
               "LANG": "en_US.UTF-8"}
        command = [sys.executable, str(script), "--probe", "--hermes-source", str(args.hermes_source),
                   "--host-mode", args.host_mode, "--platform", args.platform, "--output", str(output)]
        receipt["command"] = command
        with (output / "contract.log").open("w") as log:
            try:
                run = subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180)
                receipt["exit_code"] = run.returncode
            except subprocess.TimeoutExpired:
                receipt["exit_code"] = 124
        receipt["after"] = {"host": source_identity(args.hermes_source),
                            "distribution": distribution_identity("hermes-agent")}
        receipt["integrity_unchanged"] = before == receipt["after"]
    receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print((output / "contract.log").read_text())
    print(json.dumps(receipt, indent=2))
    return 0 if (receipt["exit_code"] == 0 and receipt["integrity_unchanged"]
                 and before["host"]["tracked_clean"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
