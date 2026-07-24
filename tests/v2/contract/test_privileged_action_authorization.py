"""Contract tests for ``I-010F PrivilegedActionAuthorizationV2@1`` (A3).

The contract carries only non-secret, exact-bound authorization facts. It does
not execute an action or turn a decision into a bearer token: slice 040 must
still persist, recheck, and consume a valid allow at its effect-commit point.
These tests prove the portable schema and the deterministic correlation rules
that prevent a supplied flow from substituting an origin, requester, digest,
scope, approval, or prior decision.
"""

from __future__ import annotations

from copy import deepcopy
import unittest

from tests.v2.contract.schema_helpers import (
    ContractCorpusMixin,
    assert_schema_verdict,
    make_approval_challenge,
    make_approval_completion,
    make_authenticated_approval_flow,
    make_authorization_decision,
    make_authorization_request,
    validate_privileged_action_authorization_flow,
)


class PrivilegedActionAuthorizationCorpusSuite(ContractCorpusMixin, unittest.TestCase):
    CORPUS = "privileged-action-authorization"
    REQUIRED_SCENES = frozenset({"S18"})


class AuthorizationShapeCases(unittest.TestCase):
    def test_each_union_member_has_a_valid_closed_shape(self):
        for document in (
            make_authorization_request(),
            make_authorization_decision(),
            make_approval_challenge(),
            make_approval_completion(),
        ):
            with self.subTest(kind=document["kind"]):
                assert_schema_verdict(
                    self, "privileged-action-authorization", document, "valid"
                )

    def test_digest_requires_sha256_lower_hex_and_a_profile(self):
        for digest in (
            {"algorithm": "sha512", "value": "0" * 64, "canonicalization_profile": "v1"},
            {"algorithm": "sha256", "value": "A" * 64, "canonicalization_profile": "v1"},
            {"algorithm": "sha256", "value": "0" * 63, "canonicalization_profile": "v1"},
            {"algorithm": "sha256", "value": "0" * 64},
        ):
            with self.subTest(digest=digest):
                document = make_authorization_request()
                document["binding"]["action_digest"] = digest
                assert_schema_verdict(
                    self, "privileged-action-authorization", document, "invalid"
                )

    def test_room_model_and_operation_body_cannot_claim_authority(self):
        for field, value in (
            ("operation", {"shell": "rm -rf /"}),
            ("room_approval", "approved in chat"),
            ("model_assertion", "the admin asked for this"),
            ("bearer_token", "copied-decision"),
        ):
            with self.subTest(field=field):
                document = make_authorization_decision()
                document[field] = value
                assert_schema_verdict(
                    self, "privileged-action-authorization", document, "invalid"
                )

    def test_approval_members_are_explicit_and_host_only(self):
        challenge = make_approval_challenge(host_only=False)
        assert_schema_verdict(self, "privileged-action-authorization", challenge, "invalid")
        challenge = make_approval_challenge(approver_ids=["operator:zoe", "operator:zoe"])
        assert_schema_verdict(self, "privileged-action-authorization", challenge, "invalid")


class AuthorizationFlowCases(unittest.TestCase):
    def test_valid_direct_allow_is_bound_to_one_request(self):
        flow = [make_authorization_request(), make_authorization_decision()]
        self.assertEqual([], validate_privileged_action_authorization_flow(flow))

    def test_valid_authenticated_approval_rechecks_before_new_allow(self):
        self.assertEqual([], validate_privileged_action_authorization_flow(make_authenticated_approval_flow()))

    def test_changed_digest_or_requester_cannot_reuse_allow(self):
        for field, value in (
            ("action_digest", {"algorithm": "sha256", "value": "f" * 64, "canonicalization_profile": "nunchi.operation-json.v1"}),
            ("derived_requester", {"actor_id": "discord:9999", "origin_event_id": "discord:event:1001", "source": "transport-attested-origin-event"}),
        ):
            with self.subTest(field=field):
                flow = [make_authorization_request(), make_authorization_decision()]
                flow[1]["binding"][field] = value
                errors = validate_privileged_action_authorization_flow(flow)
                self.assertTrue(any("substituted" in error for error in errors), errors)

    def test_unknown_persistence_revocation_or_expiry_never_allows(self):
        for field, value in (
            ("persistence_status", "unknown"),
            ("revocation_status", "revoked"),
            ("expires_at", "2026-07-24T01:01:00Z"),
        ):
            with self.subTest(field=field):
                flow = [make_authorization_request(), make_authorization_decision()]
                flow[1][field] = value
                self.assertTrue(validate_privileged_action_authorization_flow(flow))

    def test_wrong_approver_and_replayed_challenge_reject(self):
        wrong_approver = make_authenticated_approval_flow()
        wrong_approver[3]["authenticated_approver_id"] = "operator:mallory"
        self.assertTrue(validate_privileged_action_authorization_flow(wrong_approver))

        replay = make_authenticated_approval_flow()
        second_completion = deepcopy(replay[3])
        second_completion["approval_completion_id"] = "approval-completion-0002"
        second_completion["completed_at"] = "2026-07-24T01:06:00Z"
        second_completion["recheck"]["evaluated_at"] = "2026-07-24T01:07:00Z"
        second_completion["recheck"]["revocation_checked_at"] = "2026-07-24T01:07:00Z"
        replay.insert(4, second_completion)
        errors = validate_privileged_action_authorization_flow(replay)
        self.assertTrue(any("challenge replayed" in error for error in errors), errors)

    def test_completion_cannot_authorize_more_than_one_decision(self):
        flow = make_authenticated_approval_flow()
        second_allow = deepcopy(flow[-1])
        second_allow["decision_id"] = "authorization-decision-0003"
        second_allow["evaluated_at"] = "2026-07-24T01:08:00Z"
        second_allow["revocation_checked_at"] = "2026-07-24T01:08:00Z"
        flow.append(second_allow)
        errors = validate_privileged_action_authorization_flow(flow)
        self.assertTrue(any("reused by multiple decisions" in error for error in errors), errors)
