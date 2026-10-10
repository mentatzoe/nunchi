"""The preflight check: do Discord's names lead this process to the stand-in, and only to it? (step 9f, PR 3b)

    python -m evals.rehearsal.preflight [--nonce NONCE]

Run it in a Discord process's own environment, before the process starts.
It fails when:

- a proxy variable is set: ``HTTP_PROXY``, ``HTTPS_PROXY``, ``ALL_PROXY``,
  ``WS_PROXY``, ``WSS_PROXY`` or ``DISCORD_PROXY``, in any case. The
  transport's REST calls follow one, and so does Hermes's discord.py, and
  the proxy resolves Discord's names itself, past the private ``/etc/hosts``;
- one of Discord's names does not resolve to 127.0.0.1 alone;
- with ``--nonce``: a TLS GET of ``https://discord.com/api/v10/_preflight/<nonce>``
  on the default SSL context (the system's trust store, no CA argument) does
  not answer that nonce, or a TLS handshake with each other name, on the same
  context, does not show the same certificate. The nonce is the run's own
  (`FakeDiscord.preflight_nonce`), so a stale stand-in or the real Discord
  fails it.

The launcher (`discord_net.py`) runs the first two before its command
starts; the nonce needs the stand-in, which the probe starts. It prints one
JSON object and exits 1 on any failure. Standard library only, and nothing
imported from this repository, so any Python 3.11+ can run it.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
import hashlib
import http.client
import json
import os
import socket
import ssl
import sys
from typing import Any

# Every name a Discord client in a rehearsal may reach; the stand-in answers all five (fake_discord/server.py HOSTS).
NAMES = ("discord.com", "gateway.discord.gg", "cdn.discordapp.com", "media.discordapp.net", "discordapp.com")
ADDRESS = "127.0.0.1"
REST_HOST = "discord.com"
ROUTE = "/api/v10/_preflight/"
# The proxy variables a Discord client may follow, compared in lower case.
PROXY_VARIABLES = ("http_proxy", "https_proxy", "all_proxy", "ws_proxy", "wss_proxy", "discord_proxy")

Resolve = Callable[..., Sequence[tuple[Any, ...]]]


def proxies(env: Mapping[str, str]) -> list[str]:
    """The proxy variables set in ``env``, as spelled there."""
    return sorted(name for name in env if name.lower() in PROXY_VARIABLES)


def unmapped(names: Sequence[str] = NAMES, resolve: Resolve | None = None) -> list[str]:
    """A failure for each name that does not resolve to 127.0.0.1 alone (``resolve`` is the system's unless given)."""
    resolve = resolve or socket.getaddrinfo
    failures = []
    for name in names:
        try:
            found = {info[4][0] for info in resolve(name, 443, type=socket.SOCK_STREAM)}
        except OSError as error:
            failures.append(f"{name} does not resolve ({error}); the launcher maps it to {ADDRESS}")
            continue
        if found != {ADDRESS}:
            failures.append(f"{name} resolves to {', '.join(sorted(found))}, not {ADDRESS} alone")
    return failures


def _connect(name: str, port: int, context: ssl.SSLContext, address: str | None, timeout: float) -> ssl.SSLSocket:
    raw = socket.create_connection((address or name, port), timeout=timeout)
    try:
        return context.wrap_socket(raw, server_hostname=name)
    except BaseException:
        raw.close()
        raise


def reach(nonce: str, *, port: int = 443, context: ssl.SSLContext | None = None, address: str | None = None,
          timeout: float = 10.0) -> tuple[list[str], str | None]:
    """The failures of the TLS checks, and the certificate's SHA-256 that discord.com showed.

    ``address`` connects there instead of resolving each name (for tests,
    which cannot map the names); the name is still the SNI and ``Host``.
    """
    context = context or ssl.create_default_context()
    url = f"https://{REST_HOST}{ROUTE}{nonce}"
    try:
        with _connect(REST_HOST, port, context, address, timeout) as tls:
            certificate = hashlib.sha256(tls.getpeercert(binary_form=True) or b"").hexdigest()
            connection = http.client.HTTPSConnection(REST_HOST, port, timeout=timeout)
            connection.sock = tls  # already connected, through the name
            connection.request("GET", ROUTE + nonce, headers={"User-Agent": "nunchi-rehearsal-preflight", "Connection": "close"})
            response = connection.getresponse()
            status, body = response.status, response.read()
    except (OSError, http.client.HTTPException) as error:
        return [f"GET {url} failed: {error}"], None
    try:
        answer = json.loads(body).get("nonce")
    except (ValueError, AttributeError):
        answer = None
    if status != 200 or answer != nonce:
        return [f"GET {url} answered {status} {body[:200]!r}, not the run's nonce: something other than this run's stand-in answered"], certificate
    failures = []
    for name in NAMES:
        if name == REST_HOST:
            continue
        try:
            with _connect(name, port, context, address, timeout) as tls:
                seen = hashlib.sha256(tls.getpeercert(binary_form=True) or b"").hexdigest()
        except OSError as error:
            failures.append(f"TLS to {name}:{port} failed: {error}")
            continue
        if seen != certificate:
            failures.append(f"{name} showed another certificate than {REST_HOST}: it is not this run's stand-in")
    return failures, certificate


def check(env: Mapping[str, str], nonce: str | None = None, *, resolve: Resolve | None = None, port: int = 443,
          context: ssl.SSLContext | None = None, address: str | None = None) -> dict[str, Any]:
    """Every check for a process with ``env``; ``ok`` only when none failed."""
    failures = []
    found = proxies(env)
    if found:
        failures.append(f"proxy variables are set: {', '.join(found)}. A Discord client would follow them past the stand-in")
    failures += unmapped(resolve=resolve)
    certificate = None
    if nonce is not None:
        more, certificate = reach(nonce, port=port, context=context, address=address)
        failures += more
    return {"ok": not failures, "failures": failures, "names": list(NAMES), "address": ADDRESS,
            "nonce_checked": nonce is not None, "certificate_sha256": certificate}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.rehearsal.preflight", description=__doc__.split("\n\n")[0])
    parser.add_argument("--nonce", help="the stand-in's preflight nonce; without it, only the names and the proxy variables are checked")
    args = parser.parse_args(argv)
    result = check(os.environ, args.nonce)
    print(json.dumps(result, indent=2))
    for failure in result["failures"]:
        print(f"preflight: {failure}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
