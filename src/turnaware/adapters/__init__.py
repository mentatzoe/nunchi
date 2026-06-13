"""TurnAware adapter tier.

Adapters translate a host surface's message shape into a TurnAware admission
request, call the callable core, and route the verdict back into the host's
action model. They depend on the core; the core never depends on them.

Currently shipped:

- `channel` — channel-local transcript surface (cc-connect / pilot-bot shape):
  trigger + recent transcript + agent identity -> verdict -> run-shape action,
  with `CC_CONNECT_SILENT_PASS` emission on PASS.
"""

from .channel import (
    SILENT_PASS_SENTINEL,
    ChannelGateResult,
    ChannelMessage,
    FailPolicy,
    build_request,
    gate,
)

__all__ = [
    "SILENT_PASS_SENTINEL",
    "ChannelGateResult",
    "ChannelMessage",
    "FailPolicy",
    "build_request",
    "gate",
]
