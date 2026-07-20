from __future__ import annotations

import json
import tempfile
import unittest

from evals.v2.social import runner
from nunchi.policy import load_operator_policy
from tests.v2.security.helpers import clone_policy, write_policy


def wake(projection, _config):
    return {
        "disposition": "WAKE",
        "reasons": ["the current moment may warrant a contribution"],
        "evidence_event_ids": [projection["trigger_event_id"]],
    }


def suppress(projection, _config):
    return {
        "disposition": "SUPPRESS",
        "reasons": ["the participant need not be woken"],
        "evidence_event_ids": [projection["trigger_event_id"]],
        "legacy_verdict_confidences": {
            "PASS": 0.99,
            "ACK": 0.0,
            "ASK": 0.0,
            "SPEAK": 0.01,
        },
    }


class SocialEvaluationCases(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.document = clone_policy()
        self.path = write_policy(self.temporary.name, self.document)
        self.policy = load_operator_policy(self.path)

    def test_catalog_is_closed_and_contains_false_suppression_and_no_necro_scenes(self):
        catalog = runner.load_catalog()
        case_ids = [case["case_id"] for case in catalog["cases"]]
        self.assertEqual(len(case_ids), len(set(case_ids)))
        tags = {tag for case in catalog["cases"] for tag in case["tags"]}
        self.assertIn("false-suppression-scar", tags)
        self.assertIn("no-necro", tags)
        self.assertIn("coverage-gap", tags)

    def test_repeated_run_records_raw_and_effective_distributions_without_claiming_completion(self):
        record = runner.run(
            self.policy,
            trials=5,
            classifier_transport=wake,
            deterministic_time=True,
        )
        self.assertTrue(record["summary"]["machine_constraints_passed"])
        self.assertTrue(record["summary"]["post_hoc_review_required"])
        self.assertFalse(record["summary"]["product_completion_claimed"])
        first = record["cases"][0]
        self.assertEqual(first["observed"]["classifier_distribution"]["counts"], {"WAKE": 5})
        self.assertEqual(first["observed"]["effective_distribution"]["counts"], {"WAKE": 5})
        self.assertEqual(len(first["trials"]), 5)
        self.assertEqual(first["trials"][0]["raw_judgment"]["disposition"], "WAKE")
        self.assertEqual(first["trials"][0]["attention_receipt"]["stage"], "attention")
        self.assertRegex(first["projection_digest"], r"^sha256:[0-9a-f]{64}$")

    def test_direct_request_classifier_suppression_fails_even_if_policy_widens_it(self):
        self.document["recoverability"]["eligible"] = False
        write_policy(self.temporary.name, self.document)
        policy = load_operator_policy(self.path)
        record = runner.run(
            policy,
            trials=5,
            selected_ids=("C01-exact-direct-request",),
            classifier_transport=suppress,
            deterministic_time=True,
        )
        case = record["cases"][0]
        self.assertEqual(
            case["observed"]["classifier_distribution"]["counts"],
            {"SUPPRESS": 5},
        )
        self.assertEqual(
            case["observed"]["effective_distribution"]["counts"],
            {"DEFER": 5},
        )
        self.assertIn(
            "classifier-false-suppression-rate", case["constraint_failures"]
        )
        self.assertNotIn(
            "effective-false-suppression-rate", case["constraint_failures"]
        )

    def test_flicker_is_measured_in_trial_order(self):
        calls = 0

        def alternating(projection, config):
            nonlocal calls
            calls += 1
            return wake(projection, config) if calls % 2 else suppress(projection, config)

        record = runner.run(
            self.policy,
            trials=5,
            selected_ids=("C07-ordinary-flow",),
            classifier_transport=alternating,
            deterministic_time=True,
        )
        distribution = record["cases"][0]["observed"]["classifier_distribution"]
        self.assertTrue(distribution["flickered"])
        self.assertEqual(distribution["consecutive_transitions"], 4)
        self.assertEqual(distribution["counts"], {"SUPPRESS": 2, "WAKE": 3})

    def test_output_has_provenance_but_no_raw_endpoint_key_or_policy_path(self):
        record = runner.run(
            self.policy,
            trials=5,
            selected_ids=("C04-exact-peer-request",),
            classifier_transport=wake,
            deterministic_time=True,
        )
        serialized = json.dumps(record, sort_keys=True)
        self.assertIn(self.policy.classifier.model, serialized)
        self.assertNotIn(self.policy.classifier.endpoint, serialized)
        self.assertNotIn(self.policy.classifier.api_key, serialized)
        self.assertNotIn(str(self.path), serialized)
        self.assertRegex(
            record["classifier"]["prompt_digest"], r"^sha256:[0-9a-f]{64}$"
        )

    def test_too_few_trials_and_bypass_policy_are_rejected(self):
        with self.assertRaises(runner.SocialEvaluationError):
            runner.run(self.policy, trials=4, classifier_transport=wake)
        self.document["attention"]["preattention_enabled"] = False
        write_policy(self.temporary.name, self.document)
        with self.assertRaises(runner.SocialEvaluationError):
            runner.run(
                load_operator_policy(self.path),
                trials=5,
                classifier_transport=wake,
            )

    def test_deterministic_mode_is_byte_stable(self):
        first = runner.run(
            self.policy,
            trials=5,
            selected_ids=("C04-exact-peer-request",),
            classifier_transport=wake,
            deterministic_time=True,
        )
        second = runner.run(
            self.policy,
            trials=5,
            selected_ids=("C04-exact-peer-request",),
            classifier_transport=wake,
            deterministic_time=True,
        )
        self.assertEqual(
            json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True)
        )


if __name__ == "__main__":
    unittest.main()
