"""Run the attention setup probes outside the checkout with an installed wheel.

Example:
  python scripts/verify_hermes_attention_setup.py --python /venv/bin/python \
    --harness-source /normal-turn-checkout/tests/v2 --output /scratch/probe \
    --wheel /dist/nunchi-2.0.0-py3-none-any.whl

The harness source is the unchanged t_44229f49 normal-turn test artifact.
Only fixtures are copied. The child has an allowlisted environment, isolated
HOME, -I, no PYTHONPATH, no real credentials, and loopback network doubles.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def integrity():
    distribution = importlib.metadata.distribution("hermes-agent")
    paths = [Path(str(distribution.locate_file(p))) for p in distribution.files or []]
    import gateway.run
    host_root = Path(gateway.run.__file__).resolve().parents[1]
    if "site-packages" not in str(host_root):
        paths.extend(p for p in host_root.rglob("*") if p.suffix in {".py", ".json", ".toml", ".lock"})
    return {str(p.resolve()): digest(p) for p in sorted(set(paths))
            if p.is_file() and p.suffix != ".pyc" and "__pycache__" not in p.parts}


def child(output, service_only):
    sys.path.insert(0, str(output / "harness"))
    import nunchi
    import gateway.run
    origin = str(Path(nunchi.__file__).resolve())
    assert "site-packages" in origin, origin
    installed = importlib.metadata.distribution("nunchi")
    direct = json.loads(installed.read_text("direct_url.json") or "{}")
    assert not direct.get("dir_info", {}).get("editable"), direct
    before = integrity()
    # Stock editable-host imports prepend their own checkout. Restore the
    # copied fixture package first; the Nunchi implementation stays installed.
    sys.path.insert(0, str(output / "harness"))
    test_class = "InstalledAttentionServiceTests" if service_only else "InstalledAttentionSetupTests"
    suite = unittest.defaultTestLoader.loadTestsFromName(
        "tests.v2.test_hermes_attention_setup_installed." + test_class
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    after = integrity()
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    receipt = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.executable, "python_version": sys.version,
        "hermes_version": importlib.metadata.version("hermes-agent"),
        "host_gateway_origin": str(Path(gateway.run.__file__).resolve()),
        "nunchi_origin": origin, "nunchi_direct_url": direct,
        "tests_run": result.testsRun, "failures": len(result.failures),
        "test_class": test_class,
        "errors": len(result.errors), "skipped": len(result.skipped),
        "host_files_checked": len(before), "host_changed_files": changed,
        "host_before_sha256": hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
        "host_after_sha256": hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest(),
        "environment": "allowlisted; isolated HOME/HERMES_HOME; no PYTHONPATH; -I",
        "network": "loopback model double and fake Discord client; NOT live-provider acceptance",
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if result.wasSuccessful() and not changed and not result.skipped else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", type=Path)
    parser.add_argument("--python", type=Path)
    parser.add_argument("--harness-source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--service-only", action="store_true")
    args = parser.parse_args()
    if args.child:
        return child(args.child, args.service_only)
    if not all((args.python, args.harness_source, args.output, args.wheel)):
        parser.error("--python, --harness-source, --output and --wheel are required")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    harness = output / "harness" / "tests" / "v2"
    harness.mkdir(parents=True)
    (harness.parent / "__init__.py").write_text("")
    (harness / "__init__.py").write_text("")
    for name in ("hermes_normal_turn_support.py", "test_hermes_normal_turn.py"):
        shutil.copyfile(args.harness_source / name, harness / name)
    root = Path(__file__).resolve().parents[1]
    shutil.copyfile(root / "tests/v2/test_hermes_attention_setup_installed.py", harness / "test_hermes_attention_setup_installed.py")
    runner = output / "runner.py"
    shutil.copyfile(__file__, runner)
    for directory in ("home", "hermes-home", "tmp"):
        (output / directory).mkdir(mode=0o700)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(output / "home"), "HERMES_HOME": str(output / "hermes-home"),
        "TMPDIR": str(output / "tmp"), "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1", "NUNCHI_REQUIRE_HERMES_NORMAL_TURN": "1",
        "NUNCHI_PROBE_KEEP_HOME": str(output / "retained-home"),
    }
    command = [str(args.python.absolute()), "-I", str(runner), "--child", str(output)]
    if args.service_only:
        command.append("--service-only")
    with (output / "run.log").open("w") as log:
        result = subprocess.run(command, cwd=output, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300)
    provenance = {"command": command, "exit_code": result.returncode,
                  "wheel_sha256": digest(args.wheel),
                  "fixture_sha256": {p.name: digest(p) for p in harness.glob("*.py")}}
    (output / "invocation.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(json.dumps(provenance, indent=2))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
