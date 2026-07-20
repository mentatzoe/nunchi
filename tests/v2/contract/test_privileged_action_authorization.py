"""Contract tests for I-010F PrivilegedActionAuthorizationV2@1.

The schema owns the portable document shapes. Trusted-origin resolution,
policy reload, temporal ordering, revocation, approval authentication,
decision consumption, and execution-time digest recheck remain runtime rules
owned by the guard.
"""

from __future__ import annotations

import copy
import unittest

from tests.v2.contract.schema_helpers import (
    assert_schema_verdict,
    make_authorization_decision,
    make_authorization_request,
    make_participant_authorization_result,
)


SCHEMA = "privileged-action-authorization"


class AuthorizationRequestCases(unittest.TestCase):
    def test_exact_action_origin_capability_and_scope_validate(self):
        assert_schema_verdict(self, SCHEMA, make_authorization_request(), "valid")

    def test_participant_cannot_supply_requester_identity(self):
        doc = make_authorization_request(requester_actor_id="discord-user-admin")
        assert_schema_verdict(self, SCHEMA, doc, "invalid")

    def test_action_digest_is_exact_lowercase_sha256(self):
        for digest in (
            "a" * 64,
            "sha256:short",
            "sha256:" + ("A" * 64),
            "sha512:" + ("a" * 64),
        ):
            with self.subTest(digest=digest):
                doc = make_authorization_request(action_digest=digest)
                assert_schema_verdict(self, SCHEMA, doc, "invalid")

    def test_capability_must_be_namespaced(self):
        for capability in ("write", "Workspace.File.Write", ".workspace.write"):
            with self.subTest(capability=capability):
                doc = make_authorization_request(capability=capability)
                assert_schema_verdict(self, SCHEMA, doc, "invalid")

    def test_scope_requires_platform_room_participant_and_resource(self):
        base_scope = make_authorization_request()["scope"]
        for field in ("platform", "room_id", "participant_id", "resource"):
            with self.subTest(field=field):
                scope = copy.deepcopy(base_scope)
                del scope[field]
                assert_schema_verdict(
                    self,
                    SCHEMA,
                    make_authorization_request(scope=scope),
                    "invalid",
                )

    def test_v1_or_social_authority_fields_reject(self):
        for field, value in (
            ("authorized", True),
            ("role", "admin"),
            ("quoted_approver", "Zoe"),
            ("message_text", "approved"),
        ):
            with self.subTest(field=field):
                doc = make_authorization_request(**{field: value})
                assert_schema_verdict(self, SCHEMA, doc, "invalid")


class AuthorizationDecisionCases(unittest.TestCase):
    def test_deny_direct_allow_and_approval_required_validate(self):
        for decision in ("DENY", "ALLOW", "APPROVAL_REQUIRED"):
            with self.subTest(decision=decision):
                assert_schema_verdict(
                    self,
                    SCHEMA,
                    make_authorization_decision(decision),
                    "valid",
                )

    def test_origin_not_found_denial_does_not_fabricate_requester(self):
        doc = make_authorization_decision(
            "DENY",
            reason_code="deny-origin-not-found",
        )
        del doc["derived_requester_actor_id"]
        assert_schema_verdict(self, SCHEMA, doc, "valid")

    def test_allow_and_approval_required_require_derived_requester(self):
        for decision in ("ALLOW", "APPROVAL_REQUIRED"):
            with self.subTest(decision=decision):
                doc = make_authorization_decision(decision)
                del doc["derived_requester_actor_id"]
                assert_schema_verdict(self, SCHEMA, doc, "invalid")

    def test_authenticated_approval_allow_validates(self):
        doc = make_authorization_decision(
            "ALLOW",
            reason_code="allow-authenticated-approval",
            authorization_basis="authenticated-approval",
            approval_evidence={
                "challenge_id": "challenge-0001",
                "attestation_id": "attestation-0001",
                "approver_actor_id": "discord-user-admin",
                "approved_at": "2026-07-20T14:01:00Z",
                "channel": "authenticated-transport",
            },
        )
        assert_schema_verdict(self, SCHEMA, doc, "valid")

    def test_allow_requires_bounded_basis_and_matching_reason(self):
        for missing in ("authorization_basis", "expires_at"):
            with self.subTest(missing=missing):
                doc = make_authorization_decision("ALLOW")
                del doc[missing]
                assert_schema_verdict(self, SCHEMA, doc, "invalid")
        mismatch = make_authorization_decision(
            "ALLOW",
            reason_code="allow-authenticated-approval",
        )
        assert_schema_verdict(self, SCHEMA, mismatch, "invalid")

    def test_approval_required_has_host_only_challenge(self):
        doc = make_authorization_decision("APPROVAL_REQUIRED")
        del doc["approval_challenge"]
        assert_schema_verdict(self, SCHEMA, doc, "invalid")

    def test_duplicate_or_empty_approver_ids_reject(self):
        for ids in ([], ["admin", "admin"], [""]):
            with self.subTest(ids=ids):
                doc = make_authorization_decision("APPROVAL_REQUIRED")
                doc["approval_challenge"]["allowed_approver_actor_ids"] = ids
                assert_schema_verdict(self, SCHEMA, doc, "invalid")

    def test_ordinary_message_is_not_an_approval_channel(self):
        doc = make_authorization_decision(
            "ALLOW",
            reason_code="allow-authenticated-approval",
            authorization_basis="authenticated-approval",
            approval_evidence={
                "challenge_id": "challenge-0001",
                "attestation_id": "attestation-0001",
                "approver_actor_id": "discord-user-admin",
                "approved_at": "2026-07-20T14:01:00Z",
                "channel": "room-message",
            },
        )
        assert_schema_verdict(self, SCHEMA, doc, "invalid")

    def test_denial_cannot_carry_challenge_or_approval_material(self):
        for field, value in (
            (
                "approval_challenge",
                {
                    "challenge_id": "challenge-0001",
                    "allowed_approver_actor_ids": ["admin"],
                    "expires_at": "2026-07-20T14:05:00Z",
                },
            ),
            ("authorization_basis", "direct-grant"),
        ):
            with self.subTest(field=field):
                doc = make_authorization_decision("DENY", **{field: value})
                assert_schema_verdict(self, SCHEMA, doc, "invalid")

    def test_malformed_or_non_utc_times_reject(self):
        for timestamp in ("soon", "2026-07-20T14:00:00+01:00", "2026-13-20T14:00:00Z"):
            with self.subTest(timestamp=timestamp):
                doc = make_authorization_decision("ALLOW", expires_at=timestamp)
                assert_schema_verdict(self, SCHEMA, doc, "invalid")


class ParticipantProjectionCases(unittest.TestCase):
    def test_non_secret_projection_validates(self):
        assert_schema_verdict(
            self,
            SCHEMA,
            make_participant_authorization_result(),
            "valid",
        )

    def test_host_only_fields_cannot_leak_to_participant(self):
        for field, value in (
            ("derived_requester_actor_id", "discord-user-1001"),
            ("policy_provenance", "trusted:/etc/nunchi/policy.json"),
            ("approval_challenge", {"challenge_id": "secret"}),
            ("approval_evidence", {"attestation_id": "secret"}),
            ("authorization_basis", "direct-grant"),
            ("expires_at", "2026-07-20T14:05:00Z"),
        ):
            with self.subTest(field=field):
                doc = make_participant_authorization_result(**{field: value})
                assert_schema_verdict(self, SCHEMA, doc, "invalid")

    def test_participant_reason_must_match_decision(self):
        doc = make_participant_authorization_result(
            decision="DENY",
            reason_code="allow-direct-grant",
        )
        assert_schema_verdict(self, SCHEMA, doc, "invalid")


if __name__ == "__main__":
    unittest.main()
