"""Each harness's model route and keys, by variable name (step 9f, PR 1).

One secret, the OpenRouter key, goes in under the name each process reads:

- ``NUNCHI_ATTENTION_API_KEY`` for attention beside Claude Code and Codex, in
  Nunchi's own process. Their integrations strip every ``NUNCHI_*`` variable
  from the harness's environment, then add back only the room tools' socket
  path and per-launch secret (``NUNCHI_CLAUDE_CODE_GATE_*`` for the Claude
  Code session, ``NUNCHI_CODEX_TURN_*`` for the room's MCP server that Codex
  starts).
- ``OPENROUTER_API_KEY`` for attention beside Hermes (`attention_key_env`).
  The plugin runs in Hermes's own process, so whatever attention reads is
  there too; Hermes strips this name, its own provider key, from the
  environment of the agent's terminal and code tools, and would not strip a
  ``NUNCHI_*`` name. No ``NUNCHI_*`` key enters Hermes's process.
- ``ANTHROPIC_AUTH_TOKEN`` for Claude Code, with ``ANTHROPIC_BASE_URL`` at
  OpenRouter's Anthropic endpoint and ``ANTHROPIC_API_KEY`` set empty, as
  OpenRouter's Claude Code guide says.
- ``OPENROUTER_API_KEY`` for Codex (its provider's ``env_key``) and Hermes
  (its ``openrouter`` provider), named in the Hermes plugin's
  ``withheld_env``.

A canary, ``REHEARSAL_CANARY``, holds a random value in each harness's
environment. No ``*_env`` key names it, as with any key a user keeps there,
so the room's guard does not know it: if it shows up in any output, only the
scan catches it (`scan.py`). With one shared secret, the guard already holds
the key's value under attention's name, so a check that asks only for the key
would pass whether or not a harness's own key is guarded.

Nothing here holds a value of a secret. Configs name variables; the probe
fills the environment.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any

from nunchi.attention import DEFAULT_API_KEY_ENV

from evals.behavior.run import is_typed_decision_model, model_route, model_spec

HARNESSES = ("claude-code", "codex", "hermes")

OPENROUTER = "https://openrouter.ai/api/v1"
# Claude Code adds /v1/messages itself (OpenRouter's Claude Code guide).
OPENROUTER_ANTHROPIC = "https://openrouter.ai/api"
KEY_URL = f"{OPENROUTER}/key"

DEFAULT_AGENT_MODEL = "anthropic/claude-haiku-4.5"
# The behavior eval's attention baseline, on the chat route at low effort.
DEFAULT_ATTENTION_MODEL = "openai/gpt-6-luna@low"

ATTENTION_KEY_ENV = DEFAULT_API_KEY_ENV
CANARY_ENV = "REHEARSAL_CANARY"
# The stand-in transport's output key, for Claude Code's and Codex's legs only:
# a NUNCHI_* name, which their integrations strip from the harness.
OUTPUT_KEY_ENV = "NUNCHI_REHEARSAL_OUTPUT_KEY"
HARNESS_KEY_ENV = {
    "claude-code": "ANTHROPIC_AUTH_TOKEN",
    "codex": "OPENROUTER_API_KEY",
    "hermes": "OPENROUTER_API_KEY",
}


def attention_key_env(harness: str) -> str:
    """The variable attention reads its key from, beside ``harness``.

    Hermes runs the plugin, and so attention, in its own process: there the
    key goes under Hermes's own ``OPENROUTER_API_KEY``, which Hermes strips
    from its children, and not under a ``NUNCHI_*`` name, which it would pass
    to the agent's terminal. Elsewhere it is Nunchi's own
    ``NUNCHI_ATTENTION_API_KEY``, in Nunchi's process only.
    """

    return HARNESS_KEY_ENV["hermes"] if harness == "hermes" else ATTENTION_KEY_ENV

# The pinned installs every lane uses (.github/workflows/ci.yml).
PINS = {
    "claude-code": "2.1.289",
    "codex": "0.160.1",
    "hermes": "a50406d9b7474b060450d2dcaff8743c977d296a",
}

# What a clean user's environment keeps from the job's: the path, the locale,
# and how to reach the network (proxies, certificate bundles). Nothing else of
# the runner's environment reaches a harness.
PASSTHROUGH_ENV = (
    "PATH",
    "LANG",
    "LC_ALL",
    "TZ",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "NO_PROXY",
    "https_proxy",
    "http_proxy",
    "no_proxy",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "NODE_EXTRA_CA_CERTS",
)

# Claude Code's background-model variables, all on the agent's model, so no
# call goes to a model the run did not ask for.
CLAUDE_BACKGROUND_MODEL_ENV = (
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
)
# The user settings integrations/claude-code/README.md recommends: Bash in
# Claude Code's sandbox, and no session at all where the sandbox cannot run.
CLAUDE_SETTINGS = {
    "sandbox": {
        "enabled": True,
        "failIfUnavailable": True,
        "allowUnsandboxedCommands": False,
        "enableWeakerNestedSandbox": False,
    }
}


@dataclass(frozen=True)
class ClaudeModel:
    """A Claude model the probe runs Claude Code on, as the pinned Claude Code knows it."""

    # The Anthropic model id the pinned Claude Code recognizes.
    anthropic_id: str
    # The permission mode `claude -p` starts in on it through a gateway: ``auto``
    # where the model supports auto mode, ``default`` where it does not.
    permission_mode: str


# The OpenRouter slugs the probe runs Claude Code on. Behind a gateway, Claude
# Code knows a model only by its Anthropic id: given an unknown slug, it logs
# ``[claude-code:unrecognized_model]``, starts in auto mode and sends what its
# newest model takes (adaptive thinking, effort, a safeguards block), which an
# older model rejects. The probe writes ``modelOverrides`` {Anthropic id: slug}
# into the clean user's settings, so Claude Code treats the slug as that model
# and still sends the slug upstream (Claude Code's model configuration docs,
# "Override model IDs per version"). Each row was checked offline against
# Claude Code 2.1.289 and a local Messages endpoint: no diagnostic, and the
# permission mode it says (docs/rehearsal.md). The slugs follow OpenRouter's
# naming; only the default has been used against OpenRouter.
CLAUDE_CODE_MODELS = {
    "anthropic/claude-haiku-4.5": ClaudeModel("claude-haiku-4-5", "default"),
    "anthropic/claude-sonnet-4.5": ClaudeModel("claude-sonnet-4-5", "default"),
    "anthropic/claude-sonnet-4.6": ClaudeModel("claude-sonnet-4-6", "auto"),
    "anthropic/claude-sonnet-5": ClaudeModel("claude-sonnet-5", "auto"),
    "anthropic/claude-sonnet-5.5": ClaudeModel("claude-sonnet-5-5", "auto"),
    "anthropic/claude-opus-4.6": ClaudeModel("claude-opus-4-6", "auto"),
    "anthropic/claude-opus-4.7": ClaudeModel("claude-opus-4-7", "auto"),
    "anthropic/claude-opus-4.8": ClaudeModel("claude-opus-4-8", "auto"),
    "anthropic/claude-opus-5": ClaudeModel("claude-opus-5", "auto"),
    "anthropic/claude-opus-5.5": ClaudeModel("claude-opus-5-5", "auto"),
}


def claude_code_model(agent_model: str) -> ClaudeModel:
    """How the pinned Claude Code knows ``agent_model``; a slug with no row is refused."""

    try:
        return CLAUDE_CODE_MODELS[agent_model]
    except KeyError:
        raise ValueError(
            f"model {agent_model!r}: the probe runs Claude Code only on a slug it maps to Claude Code's own "
            f"model id ({', '.join(CLAUDE_CODE_MODELS)}); add a row to routes.CLAUDE_CODE_MODELS"
        ) from None


# The Hermes chat the plugin is bound to, and the identity its injected turns
# run as: the kit's Discord lane (`nunchi.integrations.hermes_plugin_conformance`).
HERMES_TURN_USER = "nunchi-turns"


def attention_config(
    label: str, *, base_url: str = OPENROUTER, provider: str = "openrouter", api_key_env: str = ATTENTION_KEY_ENV
) -> dict[str, Any]:
    """Attention on OpenRouter's chat route, as the behavior eval configures it.

    ``label`` is the eval's model label (`evals.behavior.run.model_spec`):
    ``id`` or ``id@effort``. The probe builds the chat route only, so a label
    naming another route (``messages:``, ``responses:``) or a typed decision
    model is refused. The key is read from ``api_key_env``
    (`attention_key_env`). OpenRouter reports each call's cost and serving
    provider only when asked (``usage.include``).
    """

    route, _ = model_route(label)
    model, effort = model_spec(label)
    if route is not None or is_typed_decision_model(model):
        raise ValueError(f"model {label!r}: the probe runs attention on the chat route only")
    extra: dict[str, Any] = {"usage": {"include": True}}
    if effort is not None:
        extra["reasoning"] = {"enabled": False} if effort == "off" else {"effort": effort}
    return {
        "model": model,
        "base_url": base_url,
        "provider": provider,
        "api_key_env": api_key_env,
        "temperature": 0,
        "extra_body": extra,
    }


@dataclass(frozen=True)
class Route:
    """How one harness reaches its model: settings, and the variables that carry the key."""

    harness: str
    model: str
    # Plain settings for the harness's environment (no secret among them).
    env: Mapping[str, str] = field(default_factory=dict)
    # The variables the secret goes in, for this harness.
    secret_env: tuple[str, ...] = ()
    # Where the model calls go.
    base_url: str = OPENROUTER

    def describe(self) -> dict[str, Any]:
        return {
            "harness": self.harness,
            "model": self.model,
            "base_url": self.base_url,
            "env": dict(self.env),
            "secret_env": list(self.secret_env),
        }


def claude_code_route(agent_model: str, *, base_url: str = OPENROUTER_ANTHROPIC) -> Route:
    """Claude Code through OpenRouter's Anthropic endpoint.

    The runner's ``model`` setting passes the slug as ``--model``; the
    background-model variables point at the same slug, and the clean user's
    settings map it to Claude Code's own id (`CLAUDE_CODE_MODELS`).
    """

    env = {"ANTHROPIC_BASE_URL": base_url, "ANTHROPIC_API_KEY": ""}
    env.update({name: agent_model for name in CLAUDE_BACKGROUND_MODEL_ENV})
    return Route("claude-code", agent_model, env=env, secret_env=(HARNESS_KEY_ENV["claude-code"],), base_url=base_url)


def _toml(value: str) -> str:
    # A TOML basic string; JSON's escapes are TOML's for these characters.
    return json.dumps(value, ensure_ascii=True)


def codex_config(agent_model: str, *, base_url: str = OPENROUTER, scripted: bool = False) -> str:
    """The throwaway user's ``$CODEX_HOME/config.toml``.

    OpenRouter as a custom Responses provider (``wire_api = "responses"`` is
    the only value Codex 0.160.1 accepts), its key from ``OPENROUTER_API_KEY``,
    and the sandbox integrations/codex-app-server/README.md recommends. A
    scripted run points the same provider at the local scripted endpoint and
    turns retries off, as the conformance kit does.
    """

    retries = "request_max_retries = 0\nstream_max_retries = 0\n" if scripted else ""
    return (
        f"model = {_toml(agent_model)}\n"
        'model_provider = "openrouter"\n'
        'sandbox_mode = "workspace-write"\n'
        "\n"
        "[sandbox_workspace_write]\n"
        "network_access = false\n"
        "\n"
        "[model_providers.openrouter]\n"
        'name = "OpenRouter"\n'
        f"base_url = {_toml(base_url)}\n"
        'wire_api = "responses"\n'
        f"env_key = {_toml(HARNESS_KEY_ENV['codex'])}\n"
        "supports_websockets = false\n"
        f"{retries}"
    )


def codex_route(agent_model: str, *, base_url: str = OPENROUTER) -> Route:
    return Route("codex", agent_model, secret_env=(HARNESS_KEY_ENV["codex"],), base_url=base_url)


# The literal the conformance kit's scripted Hermes endpoint takes; not a key.
HERMES_SCRIPTED_API_KEY = "sk-local-conformance"


def hermes_auxiliary_tasks() -> list[str]:
    """The installed Hermes's auxiliary tasks that pick a provider and model.

    Call only once ``HERMES_HOME`` points at a throwaway home: importing
    Hermes's config reads it.
    """

    from hermes_cli.config import DEFAULT_CONFIG  # type: ignore[import-not-found]

    tasks = DEFAULT_CONFIG.get("auxiliary", {})
    return sorted(name for name, block in tasks.items() if isinstance(block, Mapping) and "provider" in block)


def hermes_model_config(
    agent_model: str, aux_tasks: Iterable[str], *, scripted_base_url: str | None = None
) -> dict[str, Any]:
    """Hermes's ``model`` and ``auxiliary`` blocks: every call on the agent's model.

    Live, ``model.provider: openrouter`` reads ``OPENROUTER_API_KEY``. The
    kit's gateway writes a literal key for its scripted endpoint; ``api_key``
    is set empty here so that only the environment's key is used. Scripted,
    the same blocks point at the scripted endpoint.
    """

    if scripted_base_url is None:
        model = {"default": agent_model, "provider": "openrouter", "base_url": OPENROUTER, "api_key": ""}
        aux = {"provider": "openrouter", "model": agent_model}
    else:
        model = {
            "default": agent_model,
            "provider": "custom",
            "base_url": scripted_base_url,
            "api_key": HERMES_SCRIPTED_API_KEY,
        }
        aux = {
            "provider": "custom",
            "model": agent_model,
            "base_url": scripted_base_url,
            "api_key": HERMES_SCRIPTED_API_KEY,
        }
    return {"model": model, "auxiliary": {task: dict(aux) for task in aux_tasks}}


def hermes_section(chat_id: str) -> dict[str, Any]:
    """The Nunchi config's ``hermes`` section for a Discord channel (integrations/hermes-plugin/README.md).

    ``OPENROUTER_API_KEY`` lives in Hermes's process, where the plugin runs,
    and attention reads it there too: it is named here so the room's guard
    withholds its value.
    """

    return {
        "platform": "discord",
        "chat_id": chat_id,
        "thread_id": None,
        "turn_user_id": HERMES_TURN_USER,
        "turn_user_name": "Nunchi",
        "withheld_env": ["DISCORD_BOT_TOKEN", HARNESS_KEY_ENV["hermes"]],
        "start_timeout_seconds": 120,
    }


def hermes_route(agent_model: str) -> Route:
    return Route("hermes", agent_model, secret_env=(HARNESS_KEY_ENV["hermes"],))


def route_for(harness: str, agent_model: str) -> Route:
    if harness == "claude-code":
        return claude_code_route(agent_model)
    if harness == "codex":
        return codex_route(agent_model)
    if harness == "hermes":
        return hermes_route(agent_model)
    raise ValueError(f"unknown harness {harness!r}")


@dataclass(frozen=True)
class Homes:
    """A clean user: fresh HOME, CODEX_HOME, HERMES_HOME, CLAUDE_CONFIG_DIR and TMPDIR."""

    base: Path

    @property
    def home(self) -> Path:
        return self.base / "home"

    def env(self) -> dict[str, str]:
        home = self.home
        return {
            "HOME": str(home),
            "TMPDIR": str(self.base / "tmp"),
            "CODEX_HOME": str(self.base / "codex-home"),
            "HERMES_HOME": str(self.base / "hermes-home"),
            "CLAUDE_CONFIG_DIR": str(self.base / "claude-config"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "XDG_STATE_HOME": str(home / ".local" / "state"),
        }

    def create(self) -> dict[str, str]:
        env = self.env()
        for value in env.values():
            Path(value).mkdir(parents=True, exist_ok=True, mode=0o700)
        return env


def clean_environment(
    homes: Mapping[str, str], route: Route, *, inherited: Mapping[str, str] | None = None
) -> dict[str, str]:
    """A clean user's environment: the pass-through variables, the homes, and the route's settings."""

    inherited = os.environ if inherited is None else inherited
    env = {name: inherited[name] for name in PASSTHROUGH_ENV if name in inherited}
    env.update(homes)
    env.update(route.env)
    return env
