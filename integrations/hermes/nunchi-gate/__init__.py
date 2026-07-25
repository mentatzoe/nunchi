"""Hermes user-plugin loader for the Nunchi V2 package.

The wheel entry point imports :mod:`nunchi_hermes_v2` directly. Hermes user
plugin discovery imports this file, so both installation shapes execute the
same implementation with no compatibility branch.
"""

from .nunchi_hermes_v2 import register

__all__ = ["register"]
