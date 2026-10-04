"""The shared core is agent- and provider-agnostic (issue #85).

The core names no agent host, chat platform, or model vendor. Attention
models are chosen by configuration; integrations plug in their own kinds and
their own operator text.
"""

from __future__ import annotations

from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

from nunchi import cli
from nunchi.attention import (
    AttentionEngine,
    AttentionModelSelection,
    HostAttentionPermissionError,
    HostStructuredAttentionModel,
    HostTextAttentionModel,
    OpenAICompatibleAttentionModel,
    attention_model_from_config,
    decode_judgment_text,
)
from nunchi.errors import ValidationError
from nunchi.operator import OperatorStore, build_operator_config, validate_operator_config
from tests.v2.test_shared_foundation import FixtureModel, foundation, message

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "src" / "nunchi"
HOSTS_AND_VENDORS = re.compile(
    r"hermes|codex|claude|openrouter|anthropic|deepseek|\bgpt-|\bnous\b",
    re.IGNORECASE,
)
CHAT_PLATFORMS = re.compile(r"discord|telegram|matrix|slack", re.IGNORECASE)
# Conformance scenarios use canonical example IDs from one reference adapter.
CHAT_PLATFORM_LABEL_FILES = {"conformance.py"}


def _judgment(trigger: str, disposition: str = "WAKE") -> dict:
    return {
        "disposition": disposition,
        "reasons": ["asked directly"],
        "evidence_event_ids": [trigger],
        "legacy_verdict_confidences": {
            "PASS": 0.02, "ACK": 0.03, "ASK": 0.05, "SPEAK": 0.9
        },
    }


class CoreNamesNoHostVendorOrPlatformTests(unittest.TestCase):
    def test_core_modules_name_no_agent_host_or_model_vendor(self) -> None:
        for path in sorted(CORE.glob("*.py")):
            with self.subTest(module=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(
                    HOSTS_AND_VENDORS.search(text),
                    f"{path.name} names a specific agent host or model vendor",
                )

    def test_core_modules_name_no_chat_platform(self) -> None:
        for path in sorted(CORE.glob("*.py")):
            if path.name in CHAT_PLATFORM_LABEL_FILES:
                continue
            with self.subTest(module=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(
                    CHAT_PLATFORMS.search(text),
                    f"{path.name} names a specific chat platform",
                )


class AttentionModelSelectionTests(unittest.TestCase):
    def test_default_kind_is_openai_compatible_and_requires_an_explicit_endpoint(self) -> None:
        with mock.patch.dict(os.environ, {"KEY": "secret"}):
            with self.assertRaises(ValidationError) as raised:
                attention_model_from_config({"model": "m", "api_key_env": "KEY"})
            self.assertIn("base_url", str(raised.exception))
            model = attention_model_from_config(
                {"model": "m", "api_key_env": "KEY", "base_url": "http://127.0.0.1:1/v1"}
            )
        self.assertIsInstance(model, OpenAICompatibleAttentionModel)

    def test_integrations_supply_their_own_kinds(self) -> None:
        built = []

        def factory(config):
            built.append(config)
            return HostTextAttentionModel(lambda **_: "{}")

        model = attention_model_from_config(
            {"kind": "host-text", "model": "x"}, host_kinds={"host-text": factory}
        )
        self.assertIsInstance(model, HostTextAttentionModel)
        self.assertEqual([{"model": "x"}], built)

    def test_unknown_kind_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            attention_model_from_config({"kind": "mystery", "model": "x"})


class OpenAICompatibleWireTests(unittest.TestCase):
    def _serve(self, reply: dict) -> tuple[str, list]:
        seen: list = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers["Content-Length"])
                seen.append(
                    (self.path, dict(self.headers), json.loads(self.rfile.read(length)))
                )
                payload = json.dumps(reply).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}/v1", seen

    def test_request_shape_and_fenced_reply(self) -> None:
        judgment = _judgment("e1")
        base_url, seen = self._serve(
            {"choices": [{"message": {"content": "```json\n" + json.dumps(judgment) + "\n```"}}]}
        )
        model = OpenAICompatibleAttentionModel(
            model="any-model",
            api_key="secret",
            base_url=base_url,
            temperature=None,
            extra_body={"seed": 7},
        )
        result = model.judge(
            instructions="judge", projection={"trigger_event_id": "e1"}, timeout_seconds=5
        )
        self.assertEqual(judgment, result)
        path, headers, body = seen[0]
        self.assertEqual("/v1/chat/completions", path)
        self.assertEqual("Bearer secret", headers["Authorization"])
        self.assertEqual("any-model", body["model"])
        self.assertEqual({"type": "json_object"}, body["response_format"])
        self.assertNotIn("temperature", body)
        self.assertEqual(7, body["seed"])
        self.assertEqual("system", body["messages"][0]["role"])

    def test_a_reply_without_choices_is_a_provider_failure(self) -> None:
        base_url, _ = self._serve(_judgment("e1"))
        model = OpenAICompatibleAttentionModel(model="m", api_key="k", base_url=base_url)
        with self.assertRaises(Exception) as raised:
            model.judge(instructions="judge", projection={}, timeout_seconds=5)
        self.assertIn("no message content", str(raised.exception))

    def test_extra_body_cannot_override_the_core_request(self) -> None:
        with self.assertRaises(ValidationError):
            OpenAICompatibleAttentionModel(
                model="m", api_key="k", base_url="http://x/v1", extra_body={"messages": []}
            )


class HostTextAttentionTests(unittest.TestCase):
    def test_text_only_host_reads_the_room_without_reporting_its_model(self) -> None:
        calls = []

        def complete(*, system, prompt, timeout_seconds):
            calls.append((system, prompt))
            trigger = json.loads(prompt)["observation"]["trigger_event_id"]
            return SimpleNamespace(text=json.dumps(_judgment(trigger)))

        wakes = []
        pipeline, _, _, receipts = foundation(
            model=HostTextAttentionModel(complete),
            participant=lambda **kwargs: wakes.append(kwargs["wake"]) or None,
        )
        outcome = pipeline.handle_delivery(
            delivery_id="d1",
            event=message("e1"),
            actors={"human:zoe": {"kind": "human"}},
        )
        self.assertEqual("ok", outcome.opportunities[0].decision_status)
        self.assertEqual(1, len(wakes))
        audit = receipts.records(outcome.opportunities[0].request_id)[1]["body"]["classifier"]
        self.assertEqual({"name": "participant-attention"}, audit)
        self.assertEqual(1, len(calls))

    def test_decode_rejects_anything_but_one_object(self) -> None:
        for text in ("[]", "not json", "```json\n{}", 7):
            with self.subTest(text=text):
                with self.assertRaises(Exception):
                    decode_judgment_text(text)


class HostDenialTests(unittest.TestCase):
    def _engine_result(self, model):
        pipeline, _, _, receipts = foundation(model=model)
        outcome = pipeline.handle_delivery(
            delivery_id="d1",
            event=message("e1"),
            actors={"human:zoe": {"kind": "human"}},
        )
        request_id = outcome.opportunities[0].request_id
        return outcome.opportunities[0], receipts.records(request_id)[1]["body"]

    def test_without_a_denial_rule_a_permission_error_is_a_provider_failure(self) -> None:
        def denied(**_):
            raise PermissionError(13, "Permission denied", "/tmp/token")

        model = HostStructuredAttentionModel(
            SimpleNamespace(complete_structured=denied),
            AttentionModelSelection(provider="p", model="m"),
        )
        opportunity, body = self._engine_result(model)
        self.assertEqual("ERROR_FALLBACK", opportunity.effective_disposition)
        self.assertEqual("provider-failure", body["error"]["code"])

    def test_a_host_denial_wakes_with_neutral_text_and_no_classifier_audit(self) -> None:
        def denied(**_):
            raise RuntimeError("host refused")

        model = HostStructuredAttentionModel(
            SimpleNamespace(complete_structured=denied),
            AttentionModelSelection(provider="p", model="m"),
            is_denial=lambda exc: isinstance(exc, RuntimeError),
        )
        opportunity, body = self._engine_result(model)
        self.assertEqual("ERROR_FALLBACK", opportunity.effective_disposition)
        self.assertEqual("host-permission-denied", body["error"]["code"])
        self.assertEqual(HostAttentionPermissionError.detail, body["error"]["detail"])
        self.assertIsNone(HOSTS_AND_VENDORS.search(body["error"]["detail"]))

    def test_attestation_can_be_opted_out_for_hosts_that_cannot_report_it(self) -> None:
        def complete(**kwargs):
            trigger = json.loads(kwargs["input"][0]["text"])["observation"]["trigger_event_id"]
            return SimpleNamespace(parsed=_judgment(trigger), provider=None, model=None)

        strict = HostStructuredAttentionModel(
            SimpleNamespace(complete_structured=complete),
            AttentionModelSelection(provider="p", model="m"),
        )
        relaxed = HostStructuredAttentionModel(
            SimpleNamespace(complete_structured=complete),
            AttentionModelSelection(provider="p", model="m"),
            require_attestation=False,
        )
        _, strict_body = self._engine_result(strict)
        self.assertEqual("provider-failure", strict_body["error"]["code"])
        opportunity, _ = self._engine_result(relaxed)
        self.assertEqual("ok", opportunity.decision_status)


class OperatorPlatformNeutralityTests(unittest.TestCase):
    def test_any_safe_platform_name_and_host_served_models_validate(self) -> None:
        config = build_operator_config(
            profile_id="vigil",
            participant_id="vigil",
            actor_id="acme:bot:9",
            display_name="Vigil",
            instructions="Contribute carefully.",
            platform="acme-chat",
            room_id="42",
            room_name="delivery",
            continuity_scope_id="acme:channel:42",
            attention_model="attention-model",
            participant_model="participant-model",
        )
        for model in config["models"].values():
            model.pop("credential_env")
            model["kind"] = "host-served"
        validate_operator_config(config)

    def test_unregistered_platform_reports_unknown_capabilities_as_a_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with redirect_stdout(io.StringIO()):
                code = cli.main(
                    [
                        "setup", "--profile", "vigil",
                        "--config-root", str(root / "config"),
                        "--state-root", str(root / "state"),
                        "--participant-id", "vigil",
                        "--actor-id", "acme:bot:9",
                        "--display-name", "Vigil",
                        "--instructions", "Contribute carefully.",
                        "--platform", "acme-chat",
                        "--room-id", "42",
                        "--room-name", "delivery",
                        "--continuity-scope-id", "acme:channel:42",
                        "--attention-model", "attention-model",
                        "--participant-model", "participant-model",
                    ]
                )
            self.assertEqual(0, code)
            snapshot = OperatorStore(root / "config", root / "state", "vigil").snapshot()
            self.assertEqual("unregistered", snapshot["compatibility"]["acme-chat:42"]["status"])
            self.assertTrue(
                any(w.get("feature") == "platform" for w in snapshot["health"]["warnings"])
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
