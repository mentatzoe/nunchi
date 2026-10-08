"""The Nunchi Hermes plugin (#94 step 9e).

This directory is both a Python package and a Hermes directory plugin
(`plugin.yaml` beside this file). Hermes loads it under its own module name
and calls `register(ctx)`; the code always comes from the installed `nunchi`
package, so a plugin directory installed with `hermes plugins install` and the
library never disagree. See `integrations/hermes-plugin/README.md`.
"""

from nunchi.integrations.hermes_plugin.plugin import (
    HERMES_SILENT_ANSWERS,
    PLUGIN_NAME,
    SILENCE_MARKER,
    WAKE_MARKER,
    HermesPluginError,
    HermesReactions,
    HermesRoomPlugin,
    HermesRoute,
    build_plugin,
    register,
)

__all__ = [
    "HERMES_SILENT_ANSWERS",
    "PLUGIN_NAME",
    "SILENCE_MARKER",
    "WAKE_MARKER",
    "HermesPluginError",
    "HermesReactions",
    "HermesRoomPlugin",
    "HermesRoute",
    "build_plugin",
    "register",
]
