"""Capabilities of the chat platforms the in-tree reference adapters serve.

The operator registry in core is platform-neutral; these registrations are
reference-adapter data. A room on any other platform is still valid, with
capabilities unknown until measured at runtime.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..operator import PlatformRegistration, register_platform

_REACTION_ALL: dict[str, Any] = {
    "reaction": {"supported": True, "operations": ["add", "remove"], "reactions": ["*"]},
    "message": True,
    "reply": True,
}

REFERENCE_PLATFORM_CAPABILITIES: dict[str, dict[str, Any]] = {
    "channel": _REACTION_ALL,
    "discord": _REACTION_ALL,
    "matrix": {
        "reaction": {"supported": True, "operations": ["add"], "reactions": ["*"]},
        "message": True,
        "reply": True,
    },
    "telegram": {
        "reaction": {"supported": False, "operations": [], "reactions": []},
        "message": True,
        "reply": True,
    },
}


def register_reference_platforms() -> None:
    for name, capabilities in REFERENCE_PLATFORM_CAPABILITIES.items():
        register_platform(
            PlatformRegistration(
                name=name,
                capabilities=deepcopy(capabilities),
                compatibility={"status": "reference", "operator_managed": True},
            )
        )
