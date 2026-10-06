"""Authenticated native reaction capability, for the participant's own reactions.

Nunchi never reacts on the participant's behalf (#94 step 7): a mhm is the
participant's own move, and an adapter's attested capability decides whether
the participant may react at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .errors import ValidationError


@dataclass(frozen=True)
class ReactionCapability:
    """Authenticated native reaction facts supplied by a platform adapter."""

    supported: bool
    authenticated: bool
    operations: tuple[str, ...] = ()
    reactions: tuple[str, ...] = ()
    permissions_revision: str = "unavailable"
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.supported, bool) or not isinstance(self.authenticated, bool):
            raise ValueError("reaction capability booleans are invalid")
        if any(item not in ("add", "remove") for item in self.operations):
            raise ValueError("reaction capability operation is unsupported")
        if len(self.operations) != len(set(self.operations)):
            raise ValueError("reaction capability operations must be unique")
        if not all(isinstance(item, str) and item for item in self.reactions):
            raise ValueError("reaction capability reactions must be non-empty strings")
        if not isinstance(self.permissions_revision, str) or not self.permissions_revision:
            raise ValueError("reaction permissions revision must be non-empty")
        if not isinstance(self.detail, str):
            raise ValueError("reaction capability detail must be a string")

    def allows(self, reaction: str, operation: str = "add") -> bool:
        return self.permits(operation) and (
            "*" in self.reactions or reaction in self.reactions
        )

    def permits(self, operation: str = "add") -> bool:
        """Whether the participant may add or remove some reaction."""

        return (
            self.supported
            and self.authenticated
            and operation in self.operations
            and bool(self.reactions)
        )

    def document(self) -> dict[str, Any]:
        return {
            "supported": self.supported,
            "authenticated": self.authenticated,
            "operations": list(self.operations),
            "reactions": list(self.reactions),
            "permissions_revision": self.permissions_revision,
            **({"detail": self.detail} if self.detail else {}),
        }


UNAVAILABLE_REACTION_CAPABILITY = ReactionCapability(
    supported=False,
    authenticated=False,
    permissions_revision="unavailable",
    detail="adapter did not attest native reaction capability",
)


def reaction_capability(value: Any) -> ReactionCapability:
    if isinstance(value, ReactionCapability):
        return value
    if value is None:
        return UNAVAILABLE_REACTION_CAPABILITY
    if not isinstance(value, Mapping):
        raise ValidationError("reaction capability must be an object")
    required = {
        "supported",
        "authenticated",
        "operations",
        "reactions",
        "permissions_revision",
    }
    optional = {"detail"}
    if required - set(value) or set(value) - (required | optional):
        raise ValidationError("reaction capability has a missing or unexpected field")
    try:
        return ReactionCapability(
            supported=value["supported"],
            authenticated=value["authenticated"],
            operations=tuple(value["operations"]),
            reactions=tuple(value["reactions"]),
            permissions_revision=value["permissions_revision"],
            detail=value.get("detail", ""),
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"reaction capability is invalid: {exc}") from exc
