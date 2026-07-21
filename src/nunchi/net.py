"""Shared outbound HTTP safety primitives for credential-bearing clients."""

from __future__ import annotations

import ipaddress
import urllib.request


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Turn every HTTP redirect into an ordinary HTTP error response."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(NoRedirectHandler())


def open_no_redirect(request: urllib.request.Request, *, timeout: float):
    """Open one exact request without forwarding credentials to a new URL."""

    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)


def is_loopback_hostname(value: object) -> bool:
    """Return whether *value* is one exact local hostname or IP literal.

    Credential-bearing clients use this only to admit an explicitly selected
    plaintext development endpoint.  It deliberately does not resolve DNS:
    names that merely happen to resolve to loopback can later be rebound.
    """

    if not isinstance(value, str) or not value:
        return False
    if value.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def is_bounded_ascii_credential(value: object, *, maximum: int = 4096) -> bool:
    """Return whether *value* is safe to place in an HTTP header or URL path."""

    return (
        isinstance(value, str)
        and 0 < len(value) <= maximum
        and value.isascii()
        and all(33 <= ord(character) <= 126 for character in value)
    )


__all__ = [
    "NoRedirectHandler",
    "is_bounded_ascii_credential",
    "is_loopback_hostname",
    "open_no_redirect",
]
