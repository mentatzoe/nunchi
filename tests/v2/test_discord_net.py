"""The Discord launcher and its preflight check (step 9f, PR 3b).

Without root: the refusals, made before anything changes; the per-run CA,
its name constraints and its leaf; the private ``/etc/hosts`` and trust
store, built as copies; the proxy and name checks, on a fake resolver so no
test looks up a Discord name; and the TLS check of the stand-in's nonce, on
loopback with the run's CA and strict X.509 checks. With root, where
namespaces are permitted: the launcher itself, offline, around the stand-in
at port 443, reached by name on the default SSL context by Nunchi's own
clients. CI runs this suite without root, so that test skips there; the
scripted lanes run the launcher itself.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from evals.rehearsal import discord_net, preflight
from evals.rehearsal.fake_discord import server
from evals.rehearsal.fake_discord.control import FakeDiscord

ROOT = Path(__file__).resolve().parents[2]
WORLD = {"people": ["zoe"], "bots": {"vigil": {}}, "channels": {"room": {}}}
OPENSSL = shutil.which("openssl")


def loopback(*_args, **_kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]


def scratch(test: unittest.TestCase) -> Path:
    path = Path(tempfile.mkdtemp(prefix="discord-net-test-"))
    test.addCleanup(shutil.rmtree, path, True)
    return path


class RefusalTest(unittest.TestCase):
    """Every refusal comes before the launcher makes or changes anything."""

    def refused(self, argv: list[str], env: dict[str, str], euid: int = 0) -> str:
        stderr = io.StringIO()
        nothing = mock.Mock(side_effect=AssertionError("the launcher started work it had refused"))
        with mock.patch.object(discord_net.os, "geteuid", return_value=euid), \
                mock.patch.object(discord_net.tempfile, "mkdtemp", nothing), \
                mock.patch.object(discord_net.subprocess, "run", nothing), \
                mock.patch.object(discord_net.subprocess, "Popen", nothing), \
                contextlib.redirect_stderr(stderr):
            self.assertEqual(discord_net.main(argv, env), discord_net.EXIT_USAGE)
        return stderr.getvalue()

    def test_no_network_namespace_unless_on_ci(self):
        message = self.refused(["--", "true"], {"SUDO_UID": "1000", "SUDO_GID": "1000"})
        self.assertIn("without --offline the port setting would change this machine's network namespace", message)
        self.assertIsNone(discord_net.refusal(False, False, ["true"], {"CI": "true", "SUDO_UID": "1000", "SUDO_GID": "1000"}, 0),
                          "a CI runner is discarded after the job")

    def test_no_proxy_variable_in_any_case(self):
        message = self.refused(["--offline", "--", "true"], {"Https_Proxy": "http://127.0.0.1:9", "DISCORD_PROXY": "x", "NO_PROXY": "*",
                                                              "SUDO_UID": "0", "SUDO_GID": "0"})
        self.assertIn("proxy variables are set: DISCORD_PROXY, Https_Proxy.", message)

    def test_the_bwrap_check_is_skipped_only_off_ci(self):
        self.assertIn("CI never passes it", self.refused(["--offline", "--no-bwrap-check", "--", "true"], {"CI": "true"}))
        self.assertIsNone(discord_net.refusal(True, True, ["true"], {"SUDO_UID": "1000", "SUDO_GID": "1000"}, 0))

    def test_root_through_sudo_and_a_command(self):
        self.assertIn("must run as root, with sudo -E", self.refused(["--offline", "--", "true"], {}, euid=1000))
        self.assertIn("SUDO_UID and SUDO_GID are not set", self.refused(["--offline", "--", "true"], {}))
        self.assertIn("no command", self.refused(["--offline"], {"SUDO_UID": "0", "SUDO_GID": "0"}))

    def test_inside_only_in_its_own_namespace(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = discord_net.main(["--inside", "/nonexistent", "--launcher", "[]", "--offline", "--", "true"])
        self.assertEqual(code, discord_net.EXIT_SETUP)
        self.assertIn("--inside runs only in the namespace the launcher makes", stderr.getvalue())


class PreflightTest(unittest.TestCase):
    def test_proxy_variables_in_any_case(self):
        env = {"HTTP_PROXY": "a", "https_proxy": "b", "All_Proxy": "c", "WSS_PROXY": "d", "DISCORD_PROXY": "e",
               "NO_PROXY": "f", "no_proxy": "g", "YARN_HTTPS_PROXY": "h", "PATH": "/bin"}
        self.assertEqual(preflight.proxies(env), ["All_Proxy", "DISCORD_PROXY", "HTTP_PROXY", "WSS_PROXY", "https_proxy"])

    def test_each_name_resolves_to_loopback_alone(self):
        self.assertEqual(preflight.unmapped(resolve=loopback), [])

        def resolve(name, *_args, **_kwargs):
            if name == "gateway.discord.gg":
                raise socket.gaierror(-2, "Name or service not known")
            if name == "cdn.discordapp.com":
                return [*loopback(), (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 443, 0, 0))]
            if name == "discordapp.com":
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("162.159.128.233", 443))]
            return loopback()

        failures = preflight.unmapped(resolve=resolve)
        self.assertEqual(len(failures), 3)
        self.assertIn("gateway.discord.gg does not resolve", failures[0])
        self.assertIn("cdn.discordapp.com resolves to 127.0.0.1, ::1, not 127.0.0.1 alone", failures[1])
        self.assertIn("discordapp.com resolves to 162.159.128.233", failures[2])

    def test_the_names_are_the_stand_ins(self):
        self.assertEqual(preflight.NAMES, server.HOSTS)
        self.assertEqual(preflight.REST_HOST, server.REST_HOST)

    def test_the_command_line_fails_on_a_proxy(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:9"}), \
                mock.patch.object(preflight.socket, "getaddrinfo", loopback), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(preflight.main([]), 1)
        result = json.loads(stdout.getvalue())
        self.assertFalse(result["ok"])
        self.assertIn("HTTPS_PROXY", result["failures"][0])
        self.assertIn("preflight: proxy variables are set", stderr.getvalue())


@unittest.skipUnless(OPENSSL, "needs the openssl command")
class CertificatesTest(unittest.TestCase):
    def verify(self, ca: Path, leaf: Path) -> subprocess.CompletedProcess:
        return subprocess.run(["openssl", "verify", "-x509_strict", "-CAfile", str(ca), str(leaf)], capture_output=True, text=True)

    def test_the_ca_vouches_only_for_discords_domains(self):
        directory = scratch(self)
        ca, key = discord_net.make_ca(directory)
        for names, good in ((discord_net.NAMES, True), (["openrouter.ai"], False), (["evil-discord.com"], False),
                            (["discord.com.evil.example"], False), (["api.discord.com"], True)):
            leaf_dir = directory / names[0]
            leaf_dir.mkdir()
            chain, _ = discord_net.make_leaf(leaf_dir, ca, key, names)
            done = self.verify(ca, chain)
            with self.subTest(names=names):
                self.assertEqual(done.returncode == 0, good, done.stdout + done.stderr)
                if not good:
                    self.assertIn("permitted subtree violation", done.stdout + done.stderr)

    def test_the_ca_key_is_gone_and_the_leaf_names_every_host(self):
        directory = scratch(self)
        (directory / "ca").mkdir()
        (directory / "tls").mkdir()
        made = discord_net.make_certificates(directory / "ca", directory / "tls")
        self.assertEqual(sorted(p.name for p in (directory / "ca").iterdir()), ["ca.crt"])
        self.assertEqual(sorted(p.name for p in (directory / "tls").iterdir()), ["chain.crt", "leaf.key"])
        text = subprocess.run(["openssl", "x509", "-noout", "-text", "-in", str(made["chain"])], capture_output=True, text=True).stdout
        self.assertEqual(tuple(re.findall(r"DNS:([\w.-]+)", text)), discord_net.NAMES)
        self.assertEqual(made["leaf_sha256"], discord_net._fingerprint(made["chain"]))


class FilesTest(unittest.TestCase):
    """The private /etc/hosts and trust store are copies; the originals are only read."""

    def test_hosts_maps_the_names_to_loopback_alone(self):
        original = ("127.0.0.1 localhost\n# 1.2.3.4 discord.com stays a comment\n::1 localhost discord.com\n"
                    "162.159.128.233 Discord.com gateway.discord.gg # cached\n10.0.0.1 example.internal\n")
        text = discord_net.hosts_text(original)
        lines = text.splitlines()
        self.assertEqual(lines[:4], ["127.0.0.1 localhost", "# 1.2.3.4 discord.com stays a comment", "::1 localhost",
                                     "10.0.0.1 example.internal"])
        self.assertEqual(lines[-5:], [f"127.0.0.1 {name}" for name in discord_net.NAMES])
        mapped = [line for line in lines if not line.startswith("#") and set(line.split()[1:]) & set(discord_net.NAMES)]
        self.assertEqual(len(mapped), 5, "no other entry for a Discord name is left, IPv6 included")

    @unittest.skipUnless(OPENSSL, "needs the openssl command")
    def test_the_trust_store_adds_the_ca_to_a_copy(self):
        directory = scratch(self)
        source = directory / "source"
        source.mkdir()
        (directory / "elsewhere.crt").write_text("system bundle\n")
        (source / discord_net.BUNDLE).symlink_to(directory / "elsewhere.crt")
        (source / "abcd1234.0").symlink_to("other.pem")
        (directory / "ca").mkdir()
        (directory / "tls").mkdir()
        made = discord_net.make_certificates(directory / "ca", directory / "tls")
        store = discord_net.trust_store(source, directory / "certs", made["ca"])
        self.assertEqual((directory / "elsewhere.crt").read_text(), "system bundle\n", "the original is only read")
        self.assertEqual(sorted(p.name for p in source.iterdir()), ["abcd1234.0", discord_net.BUNDLE])
        bundle = store / discord_net.BUNDLE
        self.assertFalse(bundle.is_symlink())
        self.assertEqual(bundle.read_text(), "system bundle\n" + made["ca"].read_text())
        links = [p for p in store.iterdir() if p.is_symlink() and p.name != "abcd1234.0"]
        self.assertEqual([os.readlink(p) for p in links], ["nunchi-rehearsal-ca.pem"])
        fd = FakeDiscord(WORLD, tls=(str(made["chain"]), str(made["key"]))).start()
        self.addCleanup(fd.stop)
        for context in (ssl.create_default_context(capath=str(store)), ssl.create_default_context(cafile=str(bundle))):
            context.verify_flags |= ssl.VERIFY_X509_STRICT
            result = preflight.check({}, fd.preflight_nonce, resolve=loopback, port=fd.port, context=context, address="127.0.0.1")
            self.assertEqual(result["failures"], [])

    @unittest.skipUnless(OPENSSL, "needs the openssl command")
    def test_prepare_leaves_no_ca_key_and_keeps_the_leaf_key_private(self):
        directory = scratch(self)
        hosts, certs = directory / "hosts", directory / "certs"
        hosts.write_text("127.0.0.1 localhost\n")
        certs.mkdir()
        (certs / discord_net.BUNDLE).write_text("system bundle\n")
        run = directory / "run"
        run.mkdir()
        record = discord_net.prepare(run, os.getuid(), os.getgid(), hosts=hosts, certs=certs)
        self.assertEqual(record["ca_key"], "deleted")
        self.assertEqual([p for p in run.rglob("*") if p.name in ("ca.key", "ca.cnf", "leaf.csr")], [])
        self.assertEqual(run.stat().st_mode & 0o777, 0o711)
        self.assertEqual((run / "tls").stat().st_mode & 0o777, 0o700)
        self.assertEqual(Path(record["tls"]["key"]).stat().st_mode & 0o777, 0o600)
        self.assertIn("127.0.0.1 gateway.discord.gg", (run / "hosts").read_text())
        self.assertEqual(hosts.read_text(), "127.0.0.1 localhost\n")


@unittest.skipUnless(OPENSSL, "needs the openssl command")
class ReachTest(unittest.TestCase):
    """The TLS check of the run's nonce, on loopback: the names cannot be mapped without root."""

    def setUp(self) -> None:
        directory = scratch(self)
        (directory / "ca").mkdir()
        (directory / "tls").mkdir()
        self.made = discord_net.make_certificates(directory / "ca", directory / "tls")
        self.fd = FakeDiscord(WORLD, tls=(str(self.made["chain"]), str(self.made["key"]))).start()
        self.addCleanup(self.fd.stop)
        self.context = ssl.create_default_context(cafile=str(self.made["ca"]))
        self.context.verify_flags |= ssl.VERIFY_X509_STRICT

    def check(self, nonce: str, context: ssl.SSLContext | None = None) -> dict:
        return preflight.check({}, nonce, resolve=loopback, port=self.fd.port, context=context or self.context, address="127.0.0.1")

    def test_this_runs_stand_in_passes(self):
        result = self.check(self.fd.preflight_nonce)
        self.assertEqual((result["ok"], result["failures"]), (True, []))
        self.assertEqual(result["certificate_sha256"], self.made["leaf_sha256"])
        self.fd.wait_for(lambda r: r["kind"] == "tls" and r["server_name"] == preflight.NAMES[-1], 5)  # the server logs after the client returns
        names = [r["server_name"] for r in self.fd.wire.records if r["kind"] == "tls"]
        self.assertEqual(sorted(names), sorted(preflight.NAMES), "one handshake for each name")
        self.assertTrue(self.fd.verdict()["clean"])

    def test_another_nonce_or_an_untrusted_certificate_fails(self):
        result = self.check("another-run")
        self.assertIn("not the run's nonce", result["failures"][0])
        result = self.check(self.fd.preflight_nonce, ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))  # trusts no CA
        self.assertIn("certificate verify failed", result["failures"][0])


def _launcher_permitted() -> str | None:
    """Why the launcher cannot run here, or None."""
    if os.geteuid() != 0:
        return "needs root"
    for tool in ("unshare", "mount", "openssl"):
        if shutil.which(tool) is None:
            return f"needs {tool}"
    if os.environ.get("CI") == "true" and shutil.which("bwrap") is None:
        return "on CI the bubblewrap check is never skipped, and bwrap is not installed"
    done = subprocess.run(["unshare", "--mount", "--propagation", "private", "--net", "true"], capture_output=True)
    return None if done.returncode == 0 else "namespaces are not permitted here"


CHECK = """
import asyncio, json, os, socket
from pathlib import Path
from nunchi.mcp_discord.gateway import DEFAULT_GATEWAY_URL
from nunchi.mcp_discord.rest import DiscordRestClient
from nunchi.mcp_discord.ws import WSClient
from evals.rehearsal import preflight
from evals.rehearsal.fake_discord.control import FakeDiscord

net = json.loads(Path(os.environ["NUNCHI_DISCORD_NET"]).read_text())
fd = FakeDiscord({"people": ["zoe"], "bots": {"vigil": {}}, "channels": {"room": {}}}, port=443,
                 tls=(net["tls"]["cert"], net["tls"]["key"])).start()

async def hello():
    ws = await WSClient.connect(DEFAULT_GATEWAY_URL)
    try:
        return json.loads(await ws.receive_text())
    finally:
        await ws.close()

try:
    result = {
        "net": net,
        "port_start": Path("/proc/sys/net/ipv4/ip_unprivileged_port_start").read_text().strip(),
        "interfaces": [name for _, name in socket.if_nameindex()],
        "preflight": preflight.check(os.environ, fd.preflight_nonce),
        "capability": DiscordRestClient(fd.token("vigil")).reaction_capability(fd.world.channel("room").id, fd.world.member("vigil").id),
        "hello": asyncio.run(hello())["op"],
    }
finally:
    result["clean"] = fd.stop()["clean"]
print(json.dumps(result))
"""


@unittest.skipIf(_launcher_permitted(), _launcher_permitted() or "")
class LauncherTest(unittest.TestCase):
    """The launcher itself, offline: Discord's names lead Nunchi's own clients to the stand-in, on the default SSL context."""

    def setUp(self) -> None:
        home, tmp = scratch(self), scratch(self)
        home.chmod(0o755)
        tmp.chmod(0o755)
        self.tmp = tmp
        env = {k: v for k, v in os.environ.items() if k.lower() not in (*preflight.PROXY_VARIABLES, "no_proxy")}
        env.update(HOME=str(home), TMPDIR=str(tmp), PYTHONPATH=os.pathsep.join([str(ROOT / "src"), str(ROOT)]))
        env.setdefault("SUDO_UID", str(os.getuid()))
        env.setdefault("SUDO_GID", str(os.getgid()))
        self.env = env
        self.flags = ["--offline", *([] if shutil.which("bwrap") else ["--no-bwrap-check"])]

    def launch(self, command: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "evals.rehearsal.discord_net", *self.flags, "--", *command],
                              cwd=ROOT, env=env or self.env, capture_output=True, text=True, timeout=120)

    def test_the_stand_in_answers_as_discord_and_the_host_is_untouched(self):
        hosts, port_start = Path("/etc/hosts").read_bytes(), discord_net.PORT_START.read_text()
        done = self.launch([sys.executable, "-c", CHECK])
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        self.assertEqual(result["preflight"]["failures"], [])
        self.assertTrue(result["preflight"]["nonce_checked"])
        self.assertEqual(result["capability"]["capability"]["operations"], ["add", "remove"])
        self.assertEqual((result["hello"], result["clean"]), (10, True))
        self.assertEqual((result["port_start"], result["interfaces"]), ("443", ["lo"]))
        net = result["net"]
        self.assertEqual((net["offline"], net["ca_key"], net["names"]), (True, "deleted", list(discord_net.NAMES)))
        self.assertEqual(net["bwrap"]["checked"], bool(shutil.which("bwrap")))
        self.assertEqual(result["preflight"]["certificate_sha256"], net["leaf_sha256"])
        self.assertEqual((Path("/etc/hosts").read_bytes(), discord_net.PORT_START.read_text()), (hosts, port_start))
        self.assertEqual(list(self.tmp.iterdir()), [], "the run's files, the key included, are removed")

    def test_a_proxy_variable_is_refused(self):
        done = self.launch(["true"], {**self.env, "https_proxy": "http://127.0.0.1:9"})
        self.assertEqual(done.returncode, discord_net.EXIT_USAGE)
        self.assertIn("proxy variables are set: https_proxy", done.stderr)


if __name__ == "__main__":
    unittest.main()
