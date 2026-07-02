"""Nunchi adapter tier.

Adapters translate a host surface's message shape into a Nunchi admission
request, call the callable core, and route the verdict back into the host's
action model. They depend on the core; the core never depends on them.

Currently shipped:

- `channel` — channel-local transcript surface: trigger + recent transcript +
  agent identity -> verdict -> run-shape action. The contract is
  transport-neutral (branch on `silent`/`verdict`); cc-connect is supported as
  one transport via an opt-in sentinel, not a dependency.
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
