"""Contract tests for ``I-010A AttentionRequestV2@1`` (slice 010, T002).

Red cases cover exact identity (S01), actor mentions versus
``mentions_room`` (S02), the runtime-adapter-only relational classes
(duplicate event IDs, timestamp-versus-order disagreement, trigger
membership), the classifier-safe continuation projection and bounded tail
(S03), non-positive budgets (S15), and V1-envelope / reply-bearing /
social-ledger rejection (S16, 010-V1). The corpus suite runs the
``evals/v2/contract/attention-request`` corpus through both validators.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.v2.contract import schema_helpers as helpers
from tests.v2.contract.schema_helpers import (
    ContractCorpusMixin,
    CorpusError,
    EvidenceError,
    NumberToken,
    assert_corpus_inventory,
    assert_schema_verdict,
    check_id_uniqueness,
    check_timestamp_order,
    check_trigger_membership,
    enforce_evidence_record,
    make_request,
    preservation_failure,
    scan_control_plane_references,
    semantic_equal,
    token_parse,
    validate_attention_request,
)


class AttentionRequestCorpusSuite(ContractCorpusMixin, unittest.TestCase):
    CORPUS = "attention-request"
    REQUIRED_SCENES = frozenset({"S01", "S02", "S03", "S15", "S16", "010-V1"})


class ExactIdentityRedCases(unittest.TestCase):
    """S01: exact self binding is decisive; aliases never prove authorship."""

    def test_valid_request_with_alias_collision_stays_valid(self):
        # Another observed actor displays the same loose name as self; the
        # contract keeps authorship bound to exact actor IDs, so the
        # collision is representable without becoming an identity claim.
        doc = make_request()
        self.assertEqual("Vigil", doc["actors"]["discord:2002"]["display_name"])
        self.assertIn("Vigil", doc["self"]["names"])
        self.assertNotIn(doc["self"]["actor_id"], doc["actors"])
        assert_schema_verdict(self, "attention-request", doc, "valid")

    def test_missing_exact_actor_binding_rejects(self):
        doc = make_request()
        del doc["self"]["actor_id"]
        assert_schema_verdict(self, "attention-request", doc, "invalid")

    def test_empty_actor_binding_rejects(self):
        doc = make_request()
        doc["self"]["actor_id"] = ""
        assert_schema_verdict(self, "attention-request", doc, "invalid")

    def test_loose_descriptors_cannot_substitute_for_exact_binding(self):
        doc = make_request()
        del doc["self"]["actor_id"]
        doc["self"]["names"] = ["Vigil", "turnaware-vigil"]
        assert_schema_verdict(self, "attention-request", doc, "invalid")


class MentionRelationRedCases(unittest.TestCase):
    """S02: actor-targeted mention IDs stay distinct from ``mentions_room``."""

    def test_actor_mentions_and_room_mention_are_distinct_fields(self):
        doc = make_request()
        self.assertEqual(["discord:9001"], doc["events"][0]["mentioned_actor_ids"])
        self.assertFalse(doc["events"][0]["mentions_room"])
        self.assertTrue(doc["events"][2]["mentions_room"])
        assert_schema_verdict(self, "attention-request", doc, "valid")

    def test_mentions_room_must_be_boolean(self):
        doc = make_request()
        doc["events"][2]["mentions_room"] = "yes"
        assert_schema_verdict(self, "attention-request", doc, "invalid")

    def test_mentions_must_be_actor_id_array(self):
        doc = make_request()
        doc["events"][0]["mentioned_actor_ids"] = "everyone"
        assert_schema_verdict(self, "attention-request", doc, "invalid")

    def test_missing_mentions_room_rejects(self):
        doc = make_request()
        del doc["events"][2]["mentions_room"]
        assert_schema_verdict(self, "attention-request", doc, "invalid")

    def test_reply_to_event_id_is_a_literal_relation(self):
        doc = make_request()
        doc["events"][1]["reply_to_event_id"] = "e1"
        assert_schema_verdict(self, "attention-request", doc, "valid")

    def test_unresolved_relation_target_is_representable(self):
        # A reply relation whose target is outside the bounded projection
        # stays schema-valid with honest gap coverage (spec US1 scenario 2);
        # resolving it against the included events is runtime-adapter-only.
        doc = make_request()
        doc["events"][2]["reply_to_event_id"] = "e-outside"
        doc["coverage"]["has_gaps"] = True
        assert_schema_verdict(self, "attention-request", doc, "valid")

    def test_thread_root_event_id_is_a_literal_relation(self):
        doc = make_request()
        doc["events"][1]["thread_root_event_id"] = "e1"
        assert_schema_verdict(self, "attention-request", doc, "valid")


class RelationalRuntimeOnlyCases(unittest.TestCase):
    """FR-012 document-shaped relational classes: the document stays
    schema-valid in isolation while the runtime adapter rejects."""

    def test_duplicate_event_ids_reject_in_runtime_adapter_only(self):
        doc = make_request()
        doc["events"][1]["id"] = "e1"
        assert_schema_verdict(self, "attention-request", doc, "valid")
        self.assertTrue(check_id_uniqueness(doc))

    def test_identical_text_with_distinct_ids_is_valid(self):
        doc = make_request()
        doc["events"][1]["text"] = doc["events"][0]["text"]
        assert_schema_verdict(self, "attention-request", doc, "valid")
        self.assertEqual([], check_id_uniqueness(doc))

    def test_timestamp_disagreeing_with_array_order_rejects(self):
        doc = make_request()
        doc["events"][1]["timestamp"] = "2026-07-17T00:59:59Z"
        assert_schema_verdict(self, "attention-request", doc, "valid")
        self.assertTrue(check_timestamp_order(doc))

    def test_explicitly_unknown_timestamp_is_exempt_from_order_rule(self):
        doc = make_request()
        doc["events"][1]["timestamp"] = None
        assert_schema_verdict(self, "attention-request", doc, "valid")
        self.assertEqual([], check_timestamp_order(doc))

    def test_trigger_absent_from_events_rejects(self):
        doc = make_request(trigger_event_id="e99")
        assert_schema_verdict(self, "attention-request", doc, "valid")
        self.assertTrue(check_trigger_membership(doc))

    def test_trigger_present_in_events_passes(self):
        self.assertEqual([], check_trigger_membership(make_request()))


class ClassifierProjectionRedCases(unittest.TestCase):
    """S03: honest coverage and the full continuation capability are
    representable on the wire document (FR-014); the classifier-facing
    redaction of host secrets happens at runtime, not in this schema."""

    def test_bounded_tail_with_honest_coverage_is_valid(self):
        doc = make_request()
        doc["coverage"] = {
            "has_more_before": True,
            "has_more_after": False,
            "has_gaps": True,
            "truncated_by": ["events"],
            "continuity": "session-only",
            "has_restart_gap": False,
        }
        assert_schema_verdict(self, "attention-request", doc, "valid")

    def test_continuation_object_is_representable(self):
        # The design's own example embeds the full continuation capability
        # in the request; a schema forbidding it would reject a document
        # the selected design declares valid (FR-014).
        doc = make_request()
        doc["continuation"] = {
            "handle_id": "ctx:discord:42:e3",
            "bound_to": {
                "participant_id": "vigil",
                "room_id": "42",
                "continuity_scope_id": "discord:room:42#2026-07",
                "trigger_event_id": "e3",
            },
            "can_fetch_before": True,
            "can_fetch_after": False,
            "can_fetch_around_event": True,
            "max_events_per_fetch": 20,
            "max_bytes_per_fetch": 32768,
        }
        assert_schema_verdict(self, "attention-request", doc, "valid")

    def test_stray_top_level_handle_field_rejects(self):
        doc = make_request()
        doc["handle_id"] = "cont-7f3a"
        assert_schema_verdict(self, "attention-request", doc, "invalid")

    def test_host_secret_inside_coverage_rejects(self):
        doc = make_request()
        doc["coverage"]["handle_id"] = "cont-7f3a"
        assert_schema_verdict(self, "attention-request", doc, "invalid")

    def test_incomplete_continuation_rejects(self):
        doc = make_request()
        doc["continuation"] = {"handle_id": "cont-7f3a"}
        assert_schema_verdict(self, "attention-request", doc, "invalid")


class BudgetRedCases(unittest.TestCase):
    """S15: independent event/byte budgets are explicit and positive."""

    def test_zero_event_budget_rejects(self):
        doc = make_request()
        doc["coverage"]["max_events"] = 0
        assert_schema_verdict(self, "attention-request", doc, "invalid")

    def test_negative_byte_budget_rejects(self):
        doc = make_request()
        doc["coverage"]["max_bytes"] = -1
        assert_schema_verdict(self, "attention-request", doc, "invalid")

    def test_missing_budgets_are_optional(self):
        # max_events/max_bytes/max_age_seconds are optional coverage facts
        # (FR-014); their absence is honest, not invalid.
        doc = make_request()
        del doc["coverage"]["max_events"]
        del doc["coverage"]["max_bytes"]
        assert_schema_verdict(self, "attention-request", doc, "valid")


class LedgerAndV1RejectionCases(unittest.TestCase):
    """S16 / 010-V1: no social ledger, no reply prose, no V1 bridge."""

    V1_ENVELOPE = {
        "request_id": "fixture-speak",
        "trigger": {"id": "trigger-speak", "author": "zoe", "content": "please implement"},
        "context": [{"id": "ctx-1", "author": "zoe", "content": "assignment"}],
        "agent": {"id": "turnaware-vigil", "role": "developer"},
        "surface": {"type": "issue-thread"},
    }

    def test_v1_envelope_rejects_without_translation(self):
        assert_schema_verdict(self, "attention-request", dict(self.V1_ENVELOPE), "invalid")

    def test_social_ledger_fields_reject(self):
        for field, value in (
            ("handled", True),
            ("open", ["e1"]),
            ("owed", {"discord:1001": "reply"}),
            ("permission", "granted"),
        ):
            with self.subTest(field=field):
                doc = make_request(**{field: value})
                assert_schema_verdict(self, "attention-request", doc, "invalid")

    def test_reply_bearing_fields_reject(self):
        for field in ("reply", "reply_text", "composed_reply"):
            with self.subTest(field=field):
                doc = make_request(**{field: "sure, on it"})
                assert_schema_verdict(self, "attention-request", doc, "invalid")

    def test_inferred_roster_rejects(self):
        doc = make_request(roster=["discord:1001", "discord:2002", "discord:9001"])
        assert_schema_verdict(self, "attention-request", doc, "invalid")

    def test_event_level_social_state_rejects(self):
        doc = make_request()
        doc["events"][0]["handled"] = True
        assert_schema_verdict(self, "attention-request", doc, "invalid")


class PreservationHelperCases(unittest.TestCase):
    """SC-002 comparator semantics: exact tokens, exact order."""

    def test_int_and_float_tokens_are_distinct(self):
        self.assertFalse(semantic_equal(token_parse("1"), token_parse("1.0")))
        self.assertTrue(semantic_equal(token_parse("1.0"), token_parse("1.0")))

    def test_number_token_never_equals_plain_string(self):
        self.assertFalse(semantic_equal(NumberToken("1"), "1"))

    def test_array_order_is_semantic(self):
        self.assertFalse(semantic_equal(token_parse('["a","b"]'), token_parse('["b","a"]')))

    def test_key_order_and_whitespace_are_out_of_scope(self):
        left = token_parse('{"a": 1, "b": 2}')
        right = token_parse('{ "b":2,"a":1 }')
        self.assertTrue(semantic_equal(left, right))

    def test_pipeline_preservation_detects_reordering(self):
        doc = make_request()
        raw_tokens = token_parse(json.dumps(doc))
        reordered = make_request()
        reordered["events"].reverse()
        self.assertIsNotNone(preservation_failure(raw_tokens, reordered))
        self.assertIsNone(preservation_failure(raw_tokens, doc))

    def test_non_canonical_number_token_is_detected(self):
        raw_tokens = token_parse('{"latency": 1.50}')
        loaded = json.loads('{"latency": 1.50}')
        self.assertIsNotNone(preservation_failure(raw_tokens, loaded))


class SentinelDecodeCases(unittest.TestCase):
    """The reserved non-finite sentinel vocabulary decodes exactly once."""

    def test_all_three_sentinels_decode(self):
        decoded = helpers.decode_non_finite({"values": ["NaN", "Infinity", "-Infinity", "text"]})
        values = decoded["values"]
        self.assertTrue(values[0] != values[0])  # NaN
        self.assertEqual(float("inf"), values[1])
        self.assertEqual(float("-inf"), values[2])
        self.assertEqual("text", values[3])


class CorpusInventoryCases(unittest.TestCase):
    """T020/CHK067: the on-disk corpus inventory is closed and asserted at
    load time, so a wholly missing or unregistered corpus directory fails
    loudly rather than passing vacuously."""

    @staticmethod
    def _stage_registered_corpora(root: Path) -> None:
        for name in helpers.CORPUS_NAMES:
            directory = root / name
            directory.mkdir()
            (directory / "cases.jsonl").write_text("", encoding="utf-8")
            (directory / "expected-counts.json").write_text("{}", encoding="utf-8")

    def test_real_inventory_is_exactly_the_registered_set(self):
        assert_corpus_inventory()

    def test_wholly_missing_corpus_directory_fails_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._stage_registered_corpora(root)
            downstream = root / "downstream"
            for child in downstream.iterdir():
                child.unlink()
            downstream.rmdir()
            with self.assertRaisesRegex(CorpusError, "missing: \\['downstream'\\]"):
                assert_corpus_inventory(root)

    def test_unregistered_corpus_directory_fails_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._stage_registered_corpora(root)
            (root / "orphan-corpus").mkdir()
            with self.assertRaisesRegex(CorpusError, "unregistered: \\['orphan-corpus'\\]"):
                assert_corpus_inventory(root)

    def test_registered_corpus_missing_counts_file_fails_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._stage_registered_corpora(root)
            (root / "attention-decision" / "expected-counts.json").unlink()
            with self.assertRaisesRegex(CorpusError, "expected-counts.json"):
                assert_corpus_inventory(root)


class EvidenceRecordShapeCases(unittest.TestCase):
    """T021/CHK070: the shared evidence writer refuses any aggregate record
    missing one of the five mandatory fields."""

    COMPLETE = {
        "scene_id": "S01",
        "case_id": "REQ-S01-001",
        "validator": helpers.ADAPTER_VALIDATOR_ID,
        "expected": "valid",
        "observed": "valid",
    }

    def test_complete_record_is_accepted(self):
        enforce_evidence_record(dict(self.COMPLETE), "test")

    def test_each_missing_mandatory_field_is_refused(self):
        for field in helpers.MANDATORY_EVIDENCE_FIELDS:
            with self.subTest(field=field):
                record = dict(self.COMPLETE)
                del record[field]
                with self.assertRaisesRegex(EvidenceError, field):
                    enforce_evidence_record(record, "test")

    def test_empty_mandatory_field_is_refused(self):
        record = dict(self.COMPLETE)
        record["scene_id"] = ""
        with self.assertRaises(EvidenceError):
            enforce_evidence_record(record, "test")

    def test_landed_evidence_files_carry_all_mandatory_fields(self):
        for filename in helpers.EVIDENCE_FILES.values():
            path = helpers.EVIDENCE_DIR / filename
            if not path.is_file():
                continue
            with self.subTest(evidence=filename):
                self.assertGreater(helpers.verify_evidence_file(path), 0)


class ControlPlaneReadBoundaryCases(unittest.TestCase):
    """T023/CHK076: no file under the test or corpus trees references a
    SpecKit-managed control-plane path; the suite embeds its own copy of the
    FR-012 class vocabulary and no build or test path reads a SpecKit file."""

    # The forbidden prefixes are owned here, joined at compile time so this
    # declaration is never itself a contiguous control-plane token (the
    # repository governance scan and this suite's own scanner must flag real
    # references, not this list): the slice-specification tree and the
    # SpecKit configuration tree.
    FORBIDDEN_PREFIXES = ("spec" "s/", ".spec" "ify/")

    def test_no_test_or_corpus_file_reads_a_control_plane_path(self):
        hits = scan_control_plane_references(self.FORBIDDEN_PREFIXES)
        self.assertEqual(
            [],
            hits,
            "tests/v2/contract/ and evals/v2/contract/ must not reference "
            "SpecKit-managed control-plane paths",
        )

    def test_partition_vocabulary_is_embedded_not_read(self):
        # The closed FR-012 vocabulary lives in the harness itself.
        self.assertEqual(
            ("schema-expressible", "id-uniqueness", "timestamp-order",
             "advice-citation", "trigger-membership", "binding-expiry",
             "receipt-sequence"),
            helpers.ALL_CLASSES,
        )


if __name__ == "__main__":
    unittest.main()
