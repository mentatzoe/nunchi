"""Shared outbound HTTP safety primitives for credential-bearing clients."""

from __future__ import annotations

import urllib.request


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Turn every HTTP redirect into an ordinary HTTP error response."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(NoRedirectHandler())


def open_no_redirect(request: urllib.request.Request, *, timeout: float):
    """Open one exact request without forwarding credentials to a new URL."""

    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)


__all__ = ["NoRedirectHandler", "open_no_redirect"]
