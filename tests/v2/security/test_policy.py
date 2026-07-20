from __future__ import annotations

import dataclasses
import os
import tempfile
import unittest
from pathlib import Path

from nunchi.policy import PolicyLoadError, load_operator_policy

from tests.v2.security.helpers import clone_policy, write_policy


class StrictPolicySourceCases(unittest.TestCase):
    def test_valid_policy_loads_as_immutable_typed_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_policy(directory)
            policy = load_operator_policy(path)
        self.assertEqual(policy.schema_version, 2)
        self.assertEqual(policy.attention.participant_id, "vigil")
        self.assertEqual(policy.authorization.grants[0].capability, "workspace.file.write")
        self.assertTrue(policy.provenance.startswith("operator:local-v2@sha256:"))
        self.assertNotIn(str(path), policy.provenance)
        self.assertNotIn("do-not-project-this-secret", repr(policy))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            policy.attention.preattention_enabled = False  # type: ignore[misc]

    def test_relative_path_is_rejected(self):
        with self.assertRaises(PolicyLoadError) as caught:
            load_operator_policy("policy.json")
        self.assertEqual(caught.exception.code, "policy-path-invalid")

    def test_symlink_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = write_policy(directory)
            link = Path(directory) / "linked-policy.json"
            link.symlink_to(target)
            with self.assertRaises(PolicyLoadError):
                load_operator_policy(link)

    def test_group_or_other_readable_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_policy(directory)
            path.chmod(0o640)
            with self.assertRaises(PolicyLoadError) as caught:
                load_operator_policy(path)
        self.assertEqual(caught.exception.code, "policy-source-unsafe")

    def test_duplicate_json_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(
                '{"schema_version":2,"schema_version":2,"source":"x",'
                '"attention":{},"recoverability":{},"classifier":{},'
                '"authorization":{}}',
                encoding="utf-8",
            )
            path.chmod(0o600)
            with self.assertRaises(PolicyLoadError) as caught:
                load_operator_policy(path)
        self.assertEqual(caught.exception.code, "policy-duplicate-key")

    def test_non_finite_json_constant_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text('{"schema_version":NaN}', encoding="utf-8")
            path.chmod(0o600)
            with self.assertRaises(PolicyLoadError):
                load_operator_policy(path)


class ClosedTypedPolicyCases(unittest.TestCase):
    def assert_policy_rejects(self, document):
        with tempfile.TemporaryDirectory() as directory:
            path = write_policy(directory, document)
            with self.assertRaises(PolicyLoadError):
                load_operator_policy(path)

    def test_unknown_field_rejects_at_every_policy_layer(self):
        mutations = []
        root = clone_policy()
        root["room_override"] = True
        mutations.append(root)
        for section in (
            "attention",
            "recoverability",
            "classifier",
            "authorization",
            "receipt_sink",
        ):
            document = clone_policy()
            document[section]["room_override"] = True
            mutations.append(document)
        grant = clone_policy()
        grant["authorization"]["grants"][0]["display_name"] = "Admin"
        mutations.append(grant)
        for document in mutations:
            with self.subTest(document=document):
                self.assert_policy_rejects(document)

    def test_boolean_and_integer_types_are_strict(self):
        for section, field, value in (
            ("attention", "preattention_enabled", 1),
            ("attention", "attention_max_events", True),
            ("attention", "participant_max_bytes", 0),
            ("recoverability", "eligible", "yes"),
            ("classifier", "max_retries", 3),
            ("classifier", "timeout_seconds", float("inf")),
        ):
            with self.subTest(section=section, field=field, value=value):
                document = clone_policy()
                document[section][field] = value
                self.assert_policy_rejects(document)

    def test_classifier_provider_and_endpoint_are_closed_and_transport_safe(self):
        for provider, endpoint in (
            ("mystery-provider", "https://provider.example/v1/chat/completions"),
            ("openai-compatible", "http://provider.example/v1/chat/completions"),
            ("openai-compatible", "https://user:secret@provider.example/v1"),
            ("openai-compatible", "https://provider.example/v1?token=secret"),
        ):
            with self.subTest(provider=provider, endpoint=endpoint):
                document = clone_policy()
                document["classifier"]["provider"] = provider
                document["classifier"]["endpoint"] = endpoint
                self.assert_policy_rejects(document)

        document = clone_policy()
        document["classifier"]["endpoint"] = (
            "http://127.0.0.1:11434/v1/chat/completions"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = write_policy(directory, document)
            self.assertEqual(
                load_operator_policy(path).classifier.endpoint,
                document["classifier"]["endpoint"],
            )

    def test_margin_fields_are_present_or_absent_together(self):
        for missing in ("transition_defer_margin", "transition_defer_margin_source"):
            with self.subTest(missing=missing):
                document = clone_policy()
                del document["attention"][missing]
                self.assert_policy_rejects(document)

    def test_direct_grant_cannot_carry_approvers(self):
        document = clone_policy()
        document["authorization"]["grants"][0]["allowed_approver_actor_ids"] = ["admin"]
        self.assert_policy_rejects(document)

    def test_approval_grant_requires_unique_exact_approvers(self):
        for approvers in ([], ["admin", "admin"], [""]):
            with self.subTest(approvers=approvers):
                document = clone_policy()
                document["authorization"]["grants"][1][
                    "allowed_approver_actor_ids"
                ] = approvers
                self.assert_policy_rejects(document)

    def test_duplicate_grant_binding_is_rejected(self):
        document = clone_policy()
        duplicate = dict(document["authorization"]["grants"][0])
        duplicate["grant_id"] = "another-id"
        document["authorization"]["grants"].append(duplicate)
        self.assert_policy_rejects(document)

    def test_unrecognized_capability_impact_status_or_execution_rejects(self):
        for field, value in (
            ("capability", "write"),
            ("impact", "safe"),
            ("status", "disabled"),
            ("execution", "model-decides"),
        ):
            with self.subTest(field=field):
                document = clone_policy()
                document["authorization"]["grants"][0][field] = value
                self.assert_policy_rejects(document)


if __name__ == "__main__":
    unittest.main()
