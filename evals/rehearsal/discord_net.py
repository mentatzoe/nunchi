"""The launcher: Discord's names lead to the stand-in, in a private namespace, for one rehearsal (step 9f, PR 3b).

    sudo -E <python> -m evals.rehearsal.discord_net [--offline] [--require-bwrap] -- <python> -m evals.rehearsal.probe ...

Run it from the repository's root, as the probe is. ``sudo -E`` keeps the
environment and resets ``PATH``, so name each Python by its full path. In
order:

1. **Certificates.** A per-run CA, limited by name constraints to Discord's
   domains, signs one leaf for the five names the stand-in answers. The
   CA's key is deleted before anything else runs, so nothing more can be
   signed.
2. **A private namespace:** ``unshare --mount --propagation private``, plus
   ``--net`` with ``--offline``, which leaves only loopback. Inside, a
   private ``/etc/hosts`` maps the names to 127.0.0.1 (IPv4 only; any other
   entry for them is dropped), and a private ``/etc/ssl/certs`` adds the CA
   to the system's trust store, in the bundle and in the hashed directory,
   so each Python finds it with its default context. Loopback is brought up.
3. **Port 443.** ``net.ipv4.ip_unprivileged_port_start=443``, so the
   stand-in can bind it as the invoking user. The setting belongs to the
   network namespace: with ``--offline`` it stays private. Without, it would
   change this machine's, so the launcher refuses to run without
   ``--offline`` unless ``CI=true`` (a runner is discarded after its job),
   and puts the old value back afterwards.
4. **Checks.** No proxy variable is set and each name resolves to 127.0.0.1
   alone (`preflight.py`). With ``--require-bwrap``, for a harness whose
   sandbox uses bubblewrap, ``bwrap --ro-bind / / true`` runs as the
   invoking user, so the sandbox fails here, not in the middle of a run; it
   cannot be skipped. Without the flag the check does not run, and the
   record says so.
5. **The command** runs as the invoking user (``SUDO_UID``, ``SUDO_GID`` and
   that user's groups), with ``NUNCHI_DISCORD_NET`` naming the run's record
   (`net.json`): the names, the stand-in's certificate and key, and what the
   launcher did. When it ends, the run's files, the key included, are
   removed, and its exit status is the launcher's.

Root writes and changes owner only inside directories only root can write:
the run directory and ``tls/`` stay root's, and the invoking user owns the
leaf key alone. SIGTERM and SIGHUP end the launcher the same way, so the
files are removed and the port setting restored.

The TLS check of the run's nonce needs the stand-in, which the probe
starts; the probe runs `preflight.py` with the nonce in each Discord
process's own environment.

Exit status: the command's, which can be any number; 2 bad arguments or a
refusal; 3 the namespace could not be set up or a check failed.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator, Mapping, Sequence
import contextlib
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import signal
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
from typing import Any

from . import preflight

ENV = "NUNCHI_DISCORD_NET"
NAMES = preflight.NAMES
ADDRESS = preflight.ADDRESS
# The CA may vouch only for these domains and names under them.
DOMAINS = ("discord.com", "discord.gg", "discordapp.com", "discordapp.net")
HOSTS = Path("/etc/hosts")
CERTS = Path("/etc/ssl/certs")
BUNDLE = "ca-certificates.crt"
PORT_START = Path("/proc/sys/net/ipv4/ip_unprivileged_port_start")
BWRAP_CHECK = ("bwrap", "--ro-bind", "/", "/", "true")
EXIT_USAGE, EXIT_SETUP = 2, 3
TERMINATION = (signal.SIGTERM, signal.SIGHUP)


class Refused(Exception):
    """The launcher will not run as asked (exit 2)."""


class SetupFailed(Exception):
    """The namespace could not be set up, or a check failed (exit 3)."""


# -- what can be prepared and checked without root ---------------------------------------------


def refusal(offline: bool, command: Sequence[str], env: Mapping[str, str], euid: int) -> str | None:
    """Why the launcher must not run as asked, before it changes anything; None when it may."""
    ci = env.get("CI") == "true"
    if not command:
        return "no command: give it after --, as in: -- <python> -m evals.rehearsal.probe ..."
    if not offline and not ci:
        return ("without --offline the port setting would change this machine's network namespace: "
                "pass --offline, or run on a CI runner (CI=true), which is discarded after the job")
    found = preflight.proxies(env)
    if found:
        return (f"proxy variables are set: {', '.join(found)}. A Discord client would follow them past the stand-in; "
                f"unset them (env -u NAME ...)")
    if euid != 0:
        return "it must run as root, with sudo -E, to make the namespace; it drops back to you for the command"
    if not env.get("SUDO_UID", "").isdigit() or not env.get("SUDO_GID", "").isdigit():
        return "SUDO_UID and SUDO_GID are not set: run it with sudo -E, so it knows whom to drop back to"
    return None


def _openssl(*args: str) -> str:
    try:
        done = subprocess.run(["openssl", *args], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise SetupFailed("the openssl command is not installed") from None
    if done.returncode != 0:
        raise SetupFailed(f"openssl {args[0]} failed: {done.stderr.strip()}")
    return done.stdout


def _config(path: Path, common_name: str, extensions: Sequence[str]) -> Path:
    """An openssl config of our own, so the system's openssl.cnf adds nothing."""
    lines = ["[req]", "distinguished_name = dn", "prompt = no", "x509_extensions = v3", "[dn]", f"CN = {common_name}", "[v3]", *extensions]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def make_ca(directory: Path) -> tuple[Path, Path]:
    """A per-run CA that may vouch only for Discord's domains: (certificate, key)."""
    permitted = ", ".join(f"permitted;DNS:{domain}" for domain in DOMAINS)
    config = _config(directory / "ca.cnf", f"Nunchi rehearsal CA {secrets.token_hex(4)}", [
        "basicConstraints = critical, CA:TRUE, pathlen:0",
        "keyUsage = critical, keyCertSign, cRLSign",
        "subjectKeyIdentifier = hash",
        f"nameConstraints = critical, {permitted}",
    ])
    cert, key = directory / "ca.crt", directory / "ca.key"
    _openssl("req", "-x509", "-config", str(config), "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
             "-days", "2", "-keyout", str(key), "-out", str(cert))
    return cert, key


def make_leaf(directory: Path, ca: Path, ca_key: Path, names: Sequence[str] = NAMES) -> tuple[Path, Path]:
    """A server certificate for ``names``, signed by the CA: (chain of leaf and CA, key)."""
    config = _config(directory / "leaf.cnf", names[0], [
        "basicConstraints = critical, CA:FALSE",
        "keyUsage = critical, digitalSignature",
        "extendedKeyUsage = serverAuth",
        "subjectAltName = " + ", ".join(f"DNS:{name}" for name in names),
        "subjectKeyIdentifier = hash",
        "authorityKeyIdentifier = keyid:always",
    ])
    key, request, leaf = directory / "leaf.key", directory / "leaf.csr", directory / "leaf.crt"
    _openssl("req", "-new", "-config", str(config), "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
             "-keyout", str(key), "-out", str(request))
    _openssl("x509", "-req", "-in", str(request), "-CA", str(ca), "-CAkey", str(ca_key), "-set_serial", "0x" + secrets.token_hex(15),
             "-days", "2", "-extfile", str(config), "-extensions", "v3", "-out", str(leaf))
    chain = directory / "chain.crt"
    chain.write_text(leaf.read_text(encoding="ascii") + ca.read_text(encoding="ascii"), encoding="ascii")
    for path in (request, leaf, config):
        path.unlink()
    return chain, key


def make_certificates(ca_dir: Path, tls_dir: Path) -> dict[str, Any]:
    """The CA in ``ca_dir`` and the stand-in's chain and key in ``tls_dir``; the CA's key is deleted."""
    ca, ca_key = make_ca(ca_dir)
    try:
        chain, key = make_leaf(tls_dir, ca, ca_key)
    finally:
        ca_key.unlink(missing_ok=True)
        (ca_dir / "ca.cnf").unlink(missing_ok=True)
    return {"ca": ca, "chain": chain, "key": key, "ca_sha256": _fingerprint(ca), "leaf_sha256": _fingerprint(chain)}


def _fingerprint(pem_file: Path) -> str:
    """The SHA-256 of the first certificate in a PEM file, as a TLS peer shows it."""
    text = pem_file.read_text(encoding="ascii")
    end = "-----END CERTIFICATE-----"
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(text[: text.index(end) + len(end)])).hexdigest()


def hosts_text(original: str, names: Sequence[str] = NAMES, address: str = ADDRESS) -> str:
    """``/etc/hosts`` with every other entry for ``names`` dropped and each mapped to ``address`` alone."""
    lines = []
    wanted = {name.lower() for name in names}
    for line in original.splitlines():
        entry, hash_mark, comment = line.partition("#")
        fields = entry.split()
        if len(fields) < 2 or not wanted.intersection(f.lower() for f in fields[1:]):
            lines.append(line)
            continue
        kept = [f for f in fields[1:] if f.lower() not in wanted]
        if kept:
            lines.append(" ".join([fields[0], *kept]) + (f" {hash_mark}{comment}" if hash_mark else ""))
    lines.append("# Nunchi rehearsal: Discord's names lead to the stand-in (evals/rehearsal/discord_net.py)")
    lines += [f"{address} {name}" for name in names]
    return "\n".join(lines) + "\n"


def trust_store(source: Path, target: Path, ca: Path) -> Path:
    """A copy of the system's ``/etc/ssl/certs`` that also trusts ``ca``: in the bundle, and by subject hash.

    This is what ``update-ca-certificates`` would write, without its hooks,
    which could write outside the copy.
    """
    shutil.copytree(source, target, symlinks=True)
    pem = ca.read_text(encoding="ascii")
    bundle = target / BUNDLE
    existing = bundle.read_text(encoding="ascii") if bundle.exists() else ""
    if bundle.is_symlink():
        bundle.unlink()
    bundle.write_text(existing.rstrip("\n") + "\n" + pem if existing else pem, encoding="ascii")
    name = "nunchi-rehearsal-ca.pem"
    (target / name).write_text(pem, encoding="ascii")
    subject_hash = _openssl("x509", "-noout", "-subject_hash", "-in", str(ca)).strip()
    n = 0
    while (target / f"{subject_hash}.{n}").exists() or (target / f"{subject_hash}.{n}").is_symlink():
        n += 1
    (target / f"{subject_hash}.{n}").symlink_to(name)
    return target


def prepare(run: Path, uid: int, gid: int, *, hosts: Path = HOSTS, certs: Path = CERTS) -> dict[str, Any]:
    """Everything the namespace needs, under ``run``; the stand-in's key belongs to ``uid``.

    ``run`` and ``tls/`` stay root's (0711): the invoking user reaches the
    chain (0644) and its own key (0600) by their paths and can create or
    replace nothing there, so nothing root writes or changes owner in them is
    reached through a path the user can swap.
    """
    run.chmod(0o711)  # the invoking user reaches tls/, and nothing else here
    ca_dir, tls_dir = run / "ca", run / "tls"
    ca_dir.mkdir()
    tls_dir.mkdir()
    tls_dir.chmod(0o711)
    made = make_certificates(ca_dir, tls_dir)
    (run / "hosts").write_text(hosts_text(hosts.read_text(encoding="utf-8")), encoding="utf-8")
    (run / "hosts").chmod(0o644)
    trust_store(certs, run / "certs", made["ca"])
    made["chain"].chmod(0o644)
    os.chown(made["key"], uid, gid, follow_symlinks=False)
    made["key"].chmod(0o600)
    return {
        "names": list(NAMES),
        "address": ADDRESS,
        "domains": list(DOMAINS),
        "tls": {"cert": str(made["chain"]), "key": str(made["key"])},
        "ca_sha256": made["ca_sha256"],
        "leaf_sha256": made["leaf_sha256"],
        "ca_key": "deleted",
    }


def _write_record(path: Path, document: Mapping[str, Any]) -> None:
    """Root writes a new record, 0644, into the run directory (root's alone); it never follows a link at ``path``."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o644)
        handle.write(json.dumps(document, indent=2) + "\n")


@contextlib.contextmanager
def _unwind_on_signals() -> Iterator[None]:
    """SIGTERM and SIGHUP raise SystemExit (128 plus the signal), once, so every ``finally`` runs.

    The launcher's files, the keys included, are then removed and the port
    setting restored, whenever the signal comes. Signal handlers can be set
    in the main thread only.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    armed = [True]

    def unwind(signum: int, _frame: Any) -> None:
        try:
            armed.pop()  # atomic; a second signal must not cut the clean-up short
        except IndexError:
            return
        raise SystemExit(128 + signum)

    previous = {number: signal.signal(number, unwind) for number in TERMINATION}
    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def _ignore_signals() -> None:
    """At the start of a clean-up: a signal now must not interrupt it."""
    if threading.current_thread() is threading.main_thread():
        for number in TERMINATION:
            signal.signal(number, signal.SIG_IGN)


# -- inside the namespace, as root -------------------------------------------------------------------


def _namespace(kind: str, pid: int | str = "self") -> str:
    return os.readlink(f"/proc/{pid}/ns/{kind}")


def _mount(source: Path, target: Path) -> None:
    done = subprocess.run(["mount", "--bind", str(source), str(target)], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise SetupFailed(f"could not mount {source} on {target}: {done.stderr.strip()}")


def _loopback_up() -> None:
    """Bring ``lo`` up (``ip`` may not be installed): SIOCGIFFLAGS, then SIOCSIFFLAGS with IFF_UP."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        flags = struct.unpack("16sH22x", fcntl.ioctl(sock, 0x8913, struct.pack("16sH22x", b"lo", 0)))[1]
        fcntl.ioctl(sock, 0x8914, struct.pack("16sH22x", b"lo", flags | 0x1))


def _user(env: Mapping[str, str]) -> dict[str, Any]:
    """Whom the command runs as: the user sudo was run by, with that user's groups."""
    uid, gid = int(env["SUDO_UID"]), int(env["SUDO_GID"])
    try:
        name = pwd.getpwuid(uid).pw_name
        groups = os.getgrouplist(name, gid)
    except KeyError:
        name, groups = None, [gid]
    return {"uid": uid, "gid": gid, "name": name, "groups": groups}


def _as_user(user: Mapping[str, Any]) -> dict[str, Any]:
    """subprocess arguments that drop to ``user`` (setgroups, setresgid, setresuid), or none when already them."""
    if user["uid"] == os.geteuid() and user["gid"] == os.getegid():
        return {}
    return {"user": user["uid"], "group": user["gid"], "extra_groups": user["groups"]}


def _bwrap(user: Mapping[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    try:
        done = subprocess.run(BWRAP_CHECK, capture_output=True, text=True, timeout=60, env=dict(env), check=False, **_as_user(user))
    except FileNotFoundError:
        raise SetupFailed("bubblewrap (bwrap) is not installed, and --require-bwrap says this run's sandbox needs it") from None
    except subprocess.TimeoutExpired:
        raise SetupFailed(f"{' '.join(BWRAP_CHECK)} did not finish in 60 s") from None
    if done.returncode != 0:
        raise SetupFailed(f"{' '.join(BWRAP_CHECK)} failed in the launcher's namespace (exit {done.returncode}): {done.stderr.strip()}")
    return {"checked": True, "command": list(BWRAP_CHECK), "result": "ran"}


def _run(command: Sequence[str], user: Mapping[str, Any], env: Mapping[str, str]) -> int:
    """Run ``command`` and pass SIGTERM and SIGHUP on to it; SIGINT reaches it from the terminal on its own."""
    child: subprocess.Popen | None = None
    early: list[int] = []

    def forward(signum: int, _frame: Any) -> None:
        # One that comes before the command exists is passed on as soon as it does.
        if child is None:
            early.append(signum)
        else:
            child.send_signal(signum)

    previous = {signum: signal.signal(signum, forward) for signum in TERMINATION}
    try:
        try:
            child = subprocess.Popen(list(command), env=dict(env), **_as_user(user))
        except OSError as error:
            raise SetupFailed(f"could not start {command[0]}: {error}") from None
        # After the command exists: an ignored signal would be inherited, and Ctrl-C must reach it.
        previous[signal.SIGINT] = signal.signal(signal.SIGINT, signal.SIG_IGN)
        for signum in early:
            child.send_signal(signum)
        code = child.wait()
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    return 128 - code if code < 0 else code


def inside(run: Path, offline: bool, require_bwrap: bool, command: Sequence[str], launcher: Sequence[str]) -> int:
    """In the private namespace, as root: the mounts, loopback, the port, the checks, then the command as the user."""
    parent = os.getppid()
    try:
        private = _namespace("mnt") != _namespace("mnt", parent) and (not offline or _namespace("net") != _namespace("net", parent))
    except OSError:
        private = False
    if not private:
        raise SetupFailed("--inside runs only in the namespace the launcher makes; it would change this machine's /etc/hosts")
    (run / "entered").touch()  # `outside` tells a namespace that was never made from a command that failed
    env = dict(os.environ)
    user = _user(env)
    _mount(run / "hosts", HOSTS)
    _mount(run / "certs", CERTS)
    if offline:
        _loopback_up()
    before = PORT_START.read_text().strip()
    try:
        PORT_START.write_text("443\n")
        failures = preflight.unmapped()
        if failures:
            raise SetupFailed("; ".join(failures))
        record = json.loads((run / "prepared.json").read_text(encoding="utf-8"))
        tls = record["tls"]
        if subprocess.run(["test", "-r", tls["cert"], "-a", "-r", tls["key"]], env=env, check=False, **_as_user(user)).returncode != 0:
            raise SetupFailed(f"user {user['uid']} cannot read the stand-in's certificate and key under {run}: "
                              "is TMPDIR a directory only root can enter?")
        bwrap = _bwrap(user, env) if require_bwrap else {"checked": False, "skipped": "not required"}
        record.update({
            "launcher": list(launcher),
            "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "offline": offline,
            "ci": env.get("CI") == "true",
            "namespace": {"mount": "private", "net": "private, loopback only" if offline else "the host's"},
            "port_start": {"before": int(before), "set": 443,
                           "scope": "this run's network namespace" if offline else "the host's, restored afterwards"},
            "user": user,
            "bwrap": bwrap,
            "preflight": {"names": "each resolves to 127.0.0.1 alone", "proxies": "none set"},
            "command": list(command),
        })
        path = run / "net.json"
        _write_record(path, record)
        return _run(command, user, {**env, ENV: str(path)})
    finally:
        _ignore_signals()
        if not offline:
            PORT_START.write_text(before + "\n")


# -- outside, as root ----------------------------------------------------------------------------------


def outside(offline: bool, require_bwrap: bool, command: Sequence[str], launcher: Sequence[str]) -> int:
    """Prepare the run's files, enter the namespace through ``unshare``, and remove the files afterwards."""
    for tool in ("unshare", "mount"):
        if shutil.which(tool) is None:
            raise SetupFailed(f"the {tool} command is not installed")
    user = _user(os.environ)
    run = Path(tempfile.mkdtemp(prefix="nunchi-discord-net-"))
    try:
        _write_record(run / "prepared.json", prepare(run, user["uid"], user["gid"]))
        flags = [*(["--offline"] if offline else []), *(["--require-bwrap"] if require_bwrap else [])]
        inner = ["unshare", "--mount", "--propagation", "private", *(["--net"] if offline else []), "--",
                 sys.executable, "-m", "evals.rehearsal.discord_net",
                 "--inside", str(run), "--launcher", json.dumps(list(launcher)), *flags, "--", *command]
        code = _run(inner, {"uid": os.geteuid(), "gid": os.getegid()}, os.environ)
        if 0 < code < 128 and not (run / "entered").exists():
            raise SetupFailed(f"the launcher could not enter its namespace (unshare, then its inner step, ended with {code}; "
                              "does this process hold CAP_SYS_ADMIN?)")
        return code
    finally:
        _ignore_signals()
        shutil.rmtree(run, ignore_errors=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m evals.rehearsal.discord_net", description=__doc__.split("\n\n")[0])
    parser.add_argument("--offline", action="store_true", help="a private network namespace with only loopback (unshare --net)")
    parser.add_argument("--require-bwrap", action="store_true",
                        help="check that bubblewrap runs here, as the invoking user, for a harness whose sandbox uses it; "
                        "without it the check is not run, and the record says so")
    parser.add_argument("--inside", help=argparse.SUPPRESS)
    parser.add_argument("--launcher", help=argparse.SUPPRESS)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- then the command, as in: -- <python> -m evals.rehearsal.probe ...")
    return parser


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    args = _parser().parse_args(arguments)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        with _unwind_on_signals():
            if args.inside:
                return inside(Path(args.inside), args.offline, args.require_bwrap, command, json.loads(args.launcher))
            reason = refusal(args.offline, command, os.environ if env is None else env, os.geteuid())
            if reason:
                raise Refused(reason)
            return outside(args.offline, args.require_bwrap, command, ["python", "-m", "evals.rehearsal.discord_net", *arguments])
    except Refused as error:
        print(f"discord_net: refused: {error}", file=sys.stderr)
        return EXIT_USAGE
    except (SetupFailed, OSError) as error:
        print(f"discord_net: {error}", file=sys.stderr)
        return EXIT_SETUP


if __name__ == "__main__":
    raise SystemExit(main())
