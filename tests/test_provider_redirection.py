"""Cross-layer provider-redirection enforcement tests.

Threat model: an attacker who controls request-envelope content (a chat
message, a channel event, a dashboard/slash state patch) tries to smuggle
plumbing overrides — redirecting the classifier provider (``endpoint`` /
``base_url``), naming which env var to exfiltrate as the bearer token
(``api_key_env``), swapping the gate executable (``binary``), impersonating
another agent (``agent_id`` / ``mention_id``), or moving the receipt log
(``log_path``).

These tests assert that NO hostile envelope field can set any of those, at
BOTH enforcement layers:

1. The classifier-config whitelist in ``src/nunchi/classifiers.py``
   (``ProductAdmissionClassifier`` rejects every non-whitelisted
   ``classifier_config`` key with a ``ValidationError``), plus the request
   validator, which never copies unknown top-level envelope fields onto the
   validated request.
2. The hermes state whitelist in ``integrations/hermes/nunchi-gate/state.py``
   (``OVERRIDABLE_KEYS`` filtering at ingestion AND at merge time, so even a
   hand-tampered state file cannot redirect operator-only plumbing).

All tests are stdlib-only, offline, and deterministic: the classifier is
always injected via NUNCHI_CLASSIFIER_TEST_RESULT so no code path can reach
a network even if an assertion fails.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

_WORKTREE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_WORKTREE_ROOT / "src"))

from nunchi import classifiers  # noqa: E402
from nunchi.core import evaluate  # noqa: E402
from nunchi.errors import ValidationError  # noqa: E402
from nunchi.schema import validate_request  # noqa: E402

from tests.provider_helpers import provider_env  # noqa: E402

_STATE_PATH = _WORKTREE_ROOT / "integrations" / "hermes" / "nunchi-gate" / "state.py"
_PLUGIN_PATH = _WORKTREE_ROOT / "integrations" / "hermes" / "nunchi-gate" / "__init__.py"

# Every plumbing field a hostile envelope may try to set, with an obviously
# attacker-shaped value. Parametrized over BOTH layers below: each layer must
# refuse the whole set, not just the keys it happens to know about.
HOSTILE_FIELDS: dict[str, str] = {
    "endpoint": "https://attacker.example/api",
    "base_url": "https://attacker.example/v1",
    "api_key_env": "AWS_SECRET_ACCESS_KEY",
    "binary": "/tmp/evil-nunchi-channel",
    "agent_id": "impersonated-operator-bot",
    "mention_id": "999999999999999999",
    "log_path": "/tmp/evil-receipts.jsonl",
}


def _load_state_module() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "nunchi_gate_state_redirection_test", _STATE_PATH
    )
    assert spec is not None and spec.loader is not None, f"missing {_STATE_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _load_plugin_module() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "nunchi_gate_plugin_redirection_test", _PLUGIN_PATH
    )
    assert spec is not None and spec.loader is not None, f"missing {_PLUGIN_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _envelope(classifier_config: dict | None = None, **top_level) -> dict:
    request: dict = {
        "request_id": "redirect-attempt-1",
        "trigger": {
            "id": "msg-hostile",
            "author": "mallory",
            "content": "hello there",
        },
        "context": [],
        "agent": {"id": "dalgos", "role": "participant"},
        "surface": {"type": "discord-channel"},
    }
    if classifier_config is not None:
        request["classifier_config"] = classifier_config
    request.update(top_level)
    return request


class ClassifierConfigWhitelistTests(unittest.TestCase):
    """Layer 1: classifier_config in the admission envelope is a closed set."""

    def setUp(self):
        patcher = mock.patch.dict(
            os.environ, provider_env("SPEAK", checked=["trigger:msg-hostile"])
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_every_hostile_key_is_rejected_by_evaluate(self):
        for key, value in HOSTILE_FIELDS.items():
            with self.subTest(hostile_key=key):
                with self.assertRaises(ValidationError) as caught:
                    evaluate(_envelope(classifier_config={key: value}))
                self.assertIn(key, str(caught.exception))

    def test_every_hostile_key_is_rejected_at_classifier_construction(self):
        for key, value in HOSTILE_FIELDS.items():
            with self.subTest(hostile_key=key):
                with self.assertRaises(ValidationError):
                    classifiers.get_classifier("product", {key: value})

    def test_hostile_key_hidden_among_supported_keys_still_rejected(self):
        # A whitelisted key must not smuggle a hostile sibling through.
        for key, value in HOSTILE_FIELDS.items():
            with self.subTest(hostile_key=key):
                with self.assertRaises(ValidationError):
                    evaluate(
                        _envelope(classifier_config={"timeout": 5, key: value})
                    )

    def test_supported_whitelist_is_disjoint_from_hostile_fields(self):
        # The accepted set (mirrors ProductAdmissionClassifier.__init__): all
        # keys tuning judgment/resilience only — none with host/credential
        # influence. Every key must construct cleanly on its own.
        supported = {
            "model": "test-model",
            "provider": "openai-compatible",
            "timeout": 5,
            "max_retries": 1,
            "retry_base_delay": 0.1,
            "require_pass_corroboration": True,
        }
        self.assertEqual(set(supported).intersection(HOSTILE_FIELDS), set())
        for key, value in supported.items():
            with self.subTest(supported_key=key):
                engine = classifiers.get_classifier("product", {key: value})
                self.assertEqual(engine.provider, "test-fixture")

    def test_top_level_hostile_envelope_fields_do_not_survive_validation(self):
        # FR-009 forward compatibility: unknown top-level fields must not fail
        # validation — and must not land anywhere on the validated request.
        raw = _envelope(**HOSTILE_FIELDS)
        validated = validate_request(raw)
        for key in HOSTILE_FIELDS:
            with self.subTest(hostile_key=key):
                self.assertFalse(
                    hasattr(validated, key),
                    f"validated AdmissionRequest exposes hostile field {key!r}",
                )
        # The envelope still evaluates to the injected verdict, untouched.
        result = evaluate(raw)
        self.assertEqual(result["verdict"], "SPEAK")

    def test_base_url_and_api_key_resolve_from_operator_env_only(self):
        # With no test injection, the provider client is built exclusively
        # from operator environment variables; classifier_config cannot name
        # a host or an env var. (No network call happens — construction only.)
        env = {
            "NUNCHI_CLASSIFIER_MODEL": "operator/model",
            "NUNCHI_CLASSIFIER_API_KEY": "operator-key",
            "NUNCHI_CLASSIFIER_BASE_URL": "https://operator.example/v1",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            engine = classifiers.ProductAdmissionClassifier(
                config={"model": "operator/model"}
            )
            self.assertEqual(engine.client.base_url, "https://operator.example/v1")
            self.assertEqual(engine.client.api_key, "operator-key")


class HermesStateWhitelistTests(unittest.TestCase):
    """Layer 2: hermes runtime state can never carry plumbing overrides."""

    def setUp(self):
        self.m = _load_state_module()

    def test_overridable_keys_disjoint_from_hostile_fields(self):
        self.assertEqual(
            set(self.m.OVERRIDABLE_KEYS).intersection(HOSTILE_FIELDS), set()
        )

    def test_filter_overridable_drops_every_hostile_key(self):
        for key, value in HOSTILE_FIELDS.items():
            with self.subTest(hostile_key=key):
                result = self.m.filter_overridable({key: value, "enabled": True})
                self.assertNotIn(key, result)
                self.assertIn("enabled", result)

    def test_apply_state_patch_never_stores_hostile_keys(self):
        baseline = {"enabled": True, "channels": "c1"}
        for key, value in HOSTILE_FIELDS.items():
            with self.subTest(hostile_key=key):
                patch = {
                    "global": {key: value, "verbosity": "debug"},
                    "channels": {"c1": {key: value, "senders": "humans"}},
                }
                new_state = self.m.apply_state_patch({}, patch, baseline)
                self.assertNotIn(key, new_state.get("global", {}))
                self.assertNotIn(key, new_state.get("channels", {}).get("c1", {}))
                # The legitimate sibling keys still land.
                self.assertEqual(new_state["global"]["verbosity"], "debug")
                self.assertEqual(new_state["channels"]["c1"]["senders"], "humans")

    def test_audit_patch_reports_every_hostile_key_as_rejected(self):
        patch = {
            "global": dict(HOSTILE_FIELDS),
            "channels": {"c1": dict(HOSTILE_FIELDS)},
        }
        audit = self.m.audit_patch(patch)
        self.assertEqual(audit["applied"], {})
        self.assertEqual(sorted(audit["rejected"]), sorted(HOSTILE_FIELDS))

    def test_merge_effective_ignores_hostile_keys_in_tampered_state(self):
        # Even a state FILE containing hostile keys (written outside the
        # whitelisted ingestion path) must not override operator plumbing:
        # merge_effective re-filters at merge time.
        baseline = {
            "enabled": True,
            "channels": "c1",
            "binary": "/usr/local/bin/nunchi-channel",
            "agent_id": "aleph",
            "mention_id": "1496355876234199040",
            "log_path": "~/.hermes/logs/nunchi-gate.jsonl",
        }
        tampered_state = {
            "global": {**HOSTILE_FIELDS, "verbosity": "debug"},
            "channels": {"c1": {**HOSTILE_FIELDS, "senders": "humans"}},
        }
        effective = self.m.merge_effective(baseline, tampered_state, {"c1"})
        self.assertIsNotNone(effective)
        for key in HOSTILE_FIELDS:
            with self.subTest(hostile_key=key):
                self.assertEqual(
                    effective.get(key),
                    baseline.get(key),
                    f"tampered state overrode operator-only key {key!r}",
                )
        # Whitelisted overrides still apply.
        self.assertEqual(effective["verbosity"], "debug")
        self.assertEqual(effective["senders"], "humans")


class HermesPerChannelConfigWhitelistTests(unittest.TestCase):
    """The config.yaml map form is operator-owned, but its per-channel merge
    is also a closed whitelist: a per-channel entry cannot rebind plumbing."""

    def setUp(self):
        self.p = _load_plugin_module()

    def test_per_channel_keys_disjoint_from_hostile_fields(self):
        self.assertEqual(
            set(self.p._PER_CHANNEL_KEYS).intersection(HOSTILE_FIELDS), set()
        )

    def test_resolve_channel_config_never_merges_hostile_per_channel_keys(self):
        cfg = {
            "enabled": True,
            "binary": "/usr/local/bin/nunchi-channel",
            "agent_id": "aleph",
            "mention_id": "1496355876234199040",
            "log_path": "~/.hermes/logs/nunchi-gate.jsonl",
            "channels": {"c1": {**HOSTILE_FIELDS, "verbosity": "debug"}},
        }
        resolved = self.p.resolve_channel_config(cfg, {"c1"})
        self.assertIsNotNone(resolved)
        for key in HOSTILE_FIELDS:
            with self.subTest(hostile_key=key):
                self.assertEqual(
                    resolved.get(key),
                    cfg.get(key),
                    f"per-channel entry overrode operator-only key {key!r}",
                )
        self.assertEqual(resolved["verbosity"], "debug")


if __name__ == "__main__":
    unittest.main()
