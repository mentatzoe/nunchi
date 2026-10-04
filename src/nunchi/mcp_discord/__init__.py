"""Shared Discord V2 transport.

The gateway emits closed canonical V2 message, reaction, membership, and gap
notifications, including exact self. Native tools require exact short-lived
host authorization and contain no social judgment.
"""

from __future__ import annotations
