"""Nunchi step 9b spike: does Codex app-server's thread/start write trust into the user's config?

Each scenario uses a fresh, throwaway CODEX_HOME and HOME (never anyone's own setup) and a git
working directory. No model is called: thread/start alone.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(sys.argv[1]).resolve()
CODEX = BASE / "npm" / "node_modules" / ".bin" / "codex"


def run(name, params_for):
    root = BASE / "runs" / name
    shutil.rmtree(root, ignore_errors=True)
    home, codex_home, work = root / "home", root / "codex-home", root / "work"
    for d in (home, codex_home, work):
        d.mkdir(parents=True)
    (codex_home / "config.toml").write_text('model = "stand-in"\n')
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "CODEX_HOME": str(codex_home)}
    proc = subprocess.Popen([str(CODEX), "app-server", "--listen", "stdio://"], cwd=str(work), env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def send(msg):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def wait_for(id_):
        while True:
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError("app-server exited: " + proc.stderr.read()[-2000:])
            msg = json.loads(line)
            if msg.get("id") == id_:
                return msg

    try:
        send({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "nunchi-spike", "version": "0"}, "capabilities": {"experimentalApi": True}}})
        init = wait_for(1)
        send({"method": "initialized"})
        send({"id": 2, "method": "thread/start", "params": params_for(work)})
        started = wait_for(2)
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=10)
    config = (codex_home / "config.toml").read_text()
    result = started.get("result") or {}
    print(f"== {name}")
    print("   initialize:", "ok" if "result" in init else init.get("error"))
    print("   thread/start:", "ok" if "result" in started else started.get("error"))
    if result:
        print("   sandbox:", json.dumps(result.get("sandbox"))[:120], "| cwd:", result.get("cwd"))
    print("   config.toml changed:", config != 'model = "stand-in"\n')
    if config != 'model = "stand-in"\n':
        print("   " + config.replace("\n", "\n   "))


run("cwd-workspace-write", lambda w: {"cwd": str(w), "sandbox": "workspace-write"})
run("cwd-read-only", lambda w: {"cwd": str(w), "sandbox": "read-only"})
run("no-cwd-workspace-write", lambda w: {"sandbox": "workspace-write"})
run("cwd-trust-in-thread-config", lambda w: {
    "cwd": str(w), "sandbox": "workspace-write",
    "config": {"projects": {str(w): {"trust_level": "trusted"}}}})
run("cwd-untrusted-in-thread-config", lambda w: {
    "cwd": str(w), "sandbox": "workspace-write",
    "config": {"projects": {str(w): {"trust_level": "untrusted"}}}})
