"""Model routes and isolated process environments for the reference rehearsal."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any

from nunchi.attention import DEFAULT_API_KEY_ENV
from nunchi.participant_model import DEFAULT_API_KEY_ENV as PARTICIPANT_API_KEY_ENV
from evals.behavior.run import is_typed_decision_model, model_route, model_spec

HARNESSES = ("reference",)
OPENROUTER = "https://openrouter.ai/api/v1"
KEY_URL = f"{OPENROUTER}/key"
DEFAULT_AGENT_MODEL = "anthropic/claude-haiku-4.5"
DEFAULT_ATTENTION_MODEL = "openai/gpt-6-luna@low"
ATTENTION_KEY_ENV = DEFAULT_API_KEY_ENV
PARTICIPANT_KEY_ENV = PARTICIPANT_API_KEY_ENV
CANARY_ENV = "REHEARSAL_CANARY"
OUTPUT_KEY_ENV = "NUNCHI_REHEARSAL_OUTPUT_KEY"
LIVE_SCENE_KEYS = {"reference": (ATTENTION_KEY_ENV, PARTICIPANT_KEY_ENV)}
PASSTHROUGH_ENV = (
    "PATH", "LANG", "LC_ALL", "TZ", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY",
    "https_proxy", "http_proxy", "no_proxy", "SSL_CERT_FILE", "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "NODE_EXTRA_CA_CERTS",
)


def harness_key_env(harness: str) -> str:
    if harness != "reference":
        raise ValueError(f"unsupported participant {harness!r}")
    return PARTICIPANT_KEY_ENV


def attention_key_env(harness: str) -> str:
    return ATTENTION_KEY_ENV


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

@dataclass(frozen=True)
class Homes:
    """Fresh HOME, TMPDIR and XDG directories for the reference process."""

    base: Path

    @property
    def home(self) -> Path:
        return self.base / "home"

    def env(self) -> dict[str, str]:
        home = self.home
        return {
            "HOME": str(home),
            "TMPDIR": str(self.base / "tmp"),
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
