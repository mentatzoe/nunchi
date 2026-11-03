"""Contract tests for ``I-010A AttentionRequestV2@9`` (slice 010, T002; #94 step 6: @2 adds the pace, @3 the pause occasion, @4 the outcome one, @5 the memory, @6 the unattended messages; #94 step 9d: @7 a message the harness posted; agreed, 2026-10-10: @8 the gaps a window reaches; @9 a message points at the message it answered).

Red cases cover exact identity (S01), actor mentions versus
``mentions_room`` (S02), the runtime-adapter-only relational classes
(duplicate event IDs, timestamp-versus-order disagreement, trigger
membership), the classifier-safe continuation projection and bounded tail
(S03), non-positive budgets (S15), and V1-envelope / reply-bearing /
social-ledger rejection (S16, 010-V1).
"""

from __future__ import annotations

import unittest

from tests.v2.contract.schema_helpers import (
    assert_schema_verdict,
    check_actor_reference_integrity,
    check_id_uniqueness,
    check_timestamp_order,
    check_trigger_membership,
    make_request,
    scan_control_plane_references,
    validate_attention_request,
)


class PaceCases(unittest.TestCase):
    """@2 (#94 step 6): the room's pace, plain facts in whole seconds."""

    PACE = {
        "now": "2026-10-06T09:00:00.000Z",
        "window_messages": 5,
        "own_messages": 1,
        "judged_seconds_ago": 2,
        "quiet_before_seconds": 25200,
        "author_run_messages": 3,
        "author_run_seconds": 40,
        "own_last_seconds_ago": 25300,
    }

    def test_pace_validates_with_or_without_its_optional_facts(self):
        for pace in (self.PACE, {key: self.PACE[key] for key in ("now", "window_messages", "own_messages")}):
            with self.subTest(keys=sorted(pace)):
                assert_schema_verdict(self, "attention-request", dict(make_request(), pace=pace), "valid")

    def test_malformed_pace_rejects(self):
        for bad in (
            {k: v for k, v in self.PACE.items() if k != "now"},
            dict(self.PACE, quiet_before_seconds=-1),
            dict(self.PACE, judged_seconds_ago=2.5),
            dict(self.PACE, author_run_messages=0),
            dict(self.PACE, own_messages=True),
            dict(self.PACE, mood="tense"),
        ):
            with self.subTest(bad=bad):
                assert_schema_verdict(self, "attention-request", dict(make_request(), pace=bad), "invalid")


class OccasionCases(unittest.TestCase):
    """@3 and @4 (#94 step 6): a look again or an outcome turn says so."""

    def test_a_pause_or_an_outcome_validates_and_nothing_else_does(self):
        for occasion in ("pause", "outcome"):
            with self.subTest(occasion=occasion):
                assert_schema_verdict(self, "attention-request", dict(make_request(), occasion=occasion), "valid")
        for bad in ("later", "", None, ["pause"]):
            with self.subTest(bad=bad):
                assert_schema_verdict(self, "attention-request", dict(make_request(), occasion=bad), "invalid")


class MemoryCases(unittest.TestCase):
    """@5 (#94 step 6): the judgment may carry the participant's memory."""

    MEMORY = {
        "own_moves": [
            {"kind": "reply", "event_id": "v1", "about_event_id": "e1", "text": "I'll tell you when it finishes.",
             "at": "2026-10-06T09:00:00.000Z", "why": "Alice asked me to watch the nightly."},
        ],
        "threads": [
            {"event_id": "e1", "author_id": "human:alice", "text": "Tell me when the nightly finishes?",
             "addressed_to": "participant", "responses": [
                 {"event_id": "v1", "author_id": "discord:bot:9", "text": "I'll tell you when it finishes."}]},
        ],
    }

    def test_memory_validates_like_the_turns(self):
        assert_schema_verdict(self, "attention-request", dict(make_request(), memory=self.MEMORY), "valid")
        for bad in ({}, {"own_moves": [{"kind": "verdict"}]}, {"notes": []}):
            with self.subTest(bad=bad):
                assert_schema_verdict(self, "attention-request", dict(make_request(), memory=bad), "invalid")


    def test_a_message_may_point_at_the_message_it_answered(self):
        # @9: the same memory as the turn's (I-010C@16), so the judgment can cite the ask beside the promise.
        posted = {"kind": "message", "event_id": "v1", "text": "I'll tell you when it finishes.",
                  "about_event_id": "e1", "about_author_id": "human:alice", "about_text": "Tell me when the nightly finishes?"}
        assert_schema_verdict(self, "attention-request", dict(make_request(), memory={"own_moves": [posted]}), "valid")
        alone = {k: v for k, v in posted.items() if k != "about_event_id"}
        assert_schema_verdict(self, "attention-request", dict(make_request(), memory={"own_moves": [alone]}), "invalid")


class UnattendedCases(unittest.TestCase):
    """@6 (#94 step 6; agreed, 2026-10-06): the newest is judged with what it replaced."""

    def test_one_to_three_unique_ids_validate(self):
        assert_schema_verdict(self, "attention-request", dict(make_request(), unattended_event_ids=["e1"]), "valid")
        for bad in ([], ["e1", "e1"], ["e1", "e2", "e3", "e4"], [""], None):
            with self.subTest(bad=bad):
                assert_schema_verdict(self, "attention-request", dict(make_request(), unattended_event_ids=bad), "invalid")


class GapCases(unittest.TestCase):
    """@8 (agreed, 2026-10-10): coverage names the gaps in view that are still news, by when each was declared."""

    def request(self, gaps):
        doc = make_request()
        doc["coverage"].update(has_gaps=True, has_restart_gap=True, continuity="unknown", gaps=gaps)
        return doc

    def test_gaps_validate_and_are_optional(self):
        assert_schema_verdict(self, "attention-request", make_request(), "valid")
        assert_schema_verdict(self, "attention-request", self.request([{"at": "2026-10-10T14:02:00.000Z"}]), "valid")
        assert_schema_verdict(
            self,
            "attention-request",
            self.request([{"at": "2026-10-10T13:10:00.000Z"}, {"at": "2026-10-10T14:02:00.000Z"}]),
            "valid",
        )

    def test_a_malformed_gap_rejects(self):
        for bad in ([], {}, "2026-10-10T14:02:00.000Z", [{}], [{"at": ""}], [{"at": 7}], [{"at": "x", "why": "restart"}], [None]):
            with self.subTest(bad=bad):
                assert_schema_verdict(self, "attention-request", self.request(bad), "invalid")


class ExactIdentityRedCases(unittest.TestCase):
    """S01: exact self binding is decisive; aliases never prove authorship."""

    def test_valid_request_with_alias_collision_stays_valid(self):
        # Another observed actor displays the same loose name as self; the
        # contract keeps authorship bound to exact actor IDs, so the
        # collision is representable without becoming an identity claim.
        # self's own exact actor_id is present in actors (rejection R8) and
        # distinct from the colliding actor's ID.
        doc = make_request()
        self.assertEqual("Vigil", doc["actors"]["discord:2002"]["display_name"])
        self.assertIn("Vigil", doc["self"]["names"])
        self.assertIn(doc["self"]["actor_id"], doc["actors"])
        self.assertNotEqual(doc["self"]["actor_id"], "discord:2002")
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

    def test_omitted_timestamp_is_exempt_from_order_rule(self):
        # Unknown timestamp is represented by omission, not `null`
        # (rejection R7); the authority's event union has no null variant.
        doc = make_request()
        del doc["events"][1]["timestamp"]
        assert_schema_verdict(self, "attention-request", doc, "valid")
        self.assertEqual([], check_timestamp_order(doc))

    def test_trigger_absent_from_events_rejects(self):
        doc = make_request(trigger_event_id="e99")
        assert_schema_verdict(self, "attention-request", doc, "valid")
        self.assertTrue(check_trigger_membership(doc))

    def test_trigger_present_in_events_passes(self):
        self.assertEqual([], check_trigger_membership(make_request()))

    def test_self_actor_id_present_in_actors_passes(self):
        self.assertEqual([], check_actor_reference_integrity(make_request()))

    def test_self_actor_id_absent_from_actors_rejects_in_runtime_adapter_only(self):
        # Rejection R8: a dangling self reference is schema-valid in
        # isolation (Draft 2020-12 cannot express dynamic key membership)
        # but the runtime adapter's relational rule rejects it.
        doc = make_request()
        del doc["actors"][doc["self"]["actor_id"]]
        assert_schema_verdict(self, "attention-request", doc, "valid")
        self.assertTrue(check_actor_reference_integrity(doc))

    def test_mentioned_actor_absent_from_actors_rejects_in_runtime_adapter_only(self):
        doc = make_request()
        doc["events"][0]["mentioned_actor_ids"] = ["discord:ghost"]
        assert_schema_verdict(self, "attention-request", doc, "valid")
        self.assertTrue(check_actor_reference_integrity(doc))

    def test_message_author_absent_from_actors_rejects_in_runtime_adapter_only(self):
        doc = make_request()
        doc["events"][0]["author_id"] = "discord:ghost"
        assert_schema_verdict(self, "attention-request", doc, "valid")
        self.assertTrue(check_actor_reference_integrity(doc))

    def test_reaction_author_absent_from_actors_rejects_in_runtime_adapter_only(self):
        doc = make_request()
        doc["events"][1] = {
            "id": "e2",
            "type": "reaction",
            "author_id": "discord:ghost",
            "target_event_id": "e1",
            "reaction": "🚀",
            "operation": "add",
        }
        assert_schema_verdict(self, "attention-request", doc, "valid")
        self.assertTrue(check_actor_reference_integrity(doc))

    def test_membership_subject_absent_from_actors_rejects_in_runtime_adapter_only(self):
        doc = make_request()
        doc["events"][1] = {
            "id": "e2",
            "type": "membership",
            "scope": {"kind": "room", "id": "42"},
            "subject_actor_id": "discord:ghost",
            "change": "join",
        }
        assert_schema_verdict(self, "attention-request", doc, "valid")
        self.assertTrue(check_actor_reference_integrity(doc))

    def test_membership_causal_actor_absent_from_actors_rejects_in_runtime_adapter_only(self):
        doc = make_request()
        doc["events"][1] = {
            "id": "e2",
            "type": "membership",
            "scope": {"kind": "room", "id": "42"},
            "subject_actor_id": doc["self"]["actor_id"],
            "caused_by_actor_id": "discord:ghost",
            "change": "join",
        }
        assert_schema_verdict(self, "attention-request", doc, "valid")
        self.assertTrue(check_actor_reference_integrity(doc))

    def test_empty_actor_map_key_rejects(self):
        doc = make_request()
        doc["actors"][""] = {"display_name": "ghost", "kind": "unknown"}
        assert_schema_verdict(self, "attention-request", doc, "invalid")


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
        "trigger": {"id": "trigger-speak", "author": "alice", "content": "please implement"},
        "context": [{"id": "ctx-1", "author": "alice", "content": "assignment"}],
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


class ControlPlaneReadBoundaryCases(unittest.TestCase):
    """T023/CHK076: no file under the contract test tree references a
    SpecKit-managed control-plane path."""

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
            "tests/v2/contract/ must not reference "
            "SpecKit-managed control-plane paths",
        )


if __name__ == "__main__":
    unittest.main()
