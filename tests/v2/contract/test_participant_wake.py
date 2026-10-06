"""Contract tests for ``I-010C ParticipantWakeV2@6`` (slice 010, T004).

Red cases cover the wake sources, advice-free ``PREATTENTION_BYPASS``
(010-Preattention-bypass), the FR-013 advice-source violations (advice on
any non-``WAKE`` ``source``), and non-positive participant budgets (S15).
The downstream corpus containing the wake cases is run by
``test_context_and_receipt.py``.
"""

from __future__ import annotations

import unittest

from tests.v2.contract.schema_helpers import (
    assert_schema_verdict,
    check_advice_citations,
    make_advice,
    make_wake,
)


class MemoryCases(unittest.TestCase):
    """@4: the participant's own recent moves, facts with pointers (#94 step 5)."""

    MOVES = [
        {"kind": "message", "event_id": "v1", "text": "Will do.", "at": "2026-10-06T08:00:00.000Z"},
        {"kind": "reply", "event_id": "v2", "about_event_id": "q1", "text": "It was the cert."},
        {"kind": "reaction", "event_id": "r1", "about_event_id": "s1", "reaction": "\U0001f442"},
        {"kind": "silence", "about_event_id": "q2", "at": "2026-10-06T08:05:00.000Z"},
    ]

    def wake(self, moves):
        doc = make_wake("WAKE")
        doc["memory"] = {"own_moves": moves}
        return doc

    def test_each_kind_of_move_validates(self):
        assert_schema_verdict(self, "participant-wake", self.wake(self.MOVES), "valid")
        for source in ("ACK", "DEFER", "ERROR_FALLBACK"):
            with self.subTest(source=source):
                doc = make_wake(source)
                doc["memory"] = {"own_moves": self.MOVES[:1]}
                assert_schema_verdict(self, "participant-wake", doc, "valid")

    def test_any_move_may_carry_its_reason(self):
        # @6: the participant's own reason at the time, never posted.
        moves = [dict(move, why="Castor was asked; waiting for him.") for move in self.MOVES]
        assert_schema_verdict(self, "participant-wake", self.wake(moves), "valid")
        for bad in ("", "x" * 201, 7):
            with self.subTest(why=bad):
                assert_schema_verdict(self, "participant-wake", self.wake([dict(self.MOVES[3], why=bad)]), "invalid")

    def test_malformed_memory_rejects(self):
        too_long = dict(self.MOVES[0], text="x" * 281)
        silence_with_text = dict(self.MOVES[3], text="I stayed quiet")
        reply_without_target = {k: v for k, v in self.MOVES[1].items() if k != "about_event_id"}
        for bad in (
            [],
            [{"kind": "verdict", "about_event_id": "q1"}],
            [too_long],
            [silence_with_text],
            [reply_without_target],
            [dict(self.MOVES[2], reaction="")],
        ):
            with self.subTest(bad=bad):
                assert_schema_verdict(self, "participant-wake", self.wake(bad), "invalid")
        extra = make_wake("WAKE")
        extra["memory"] = {"own_moves": self.MOVES, "todo": ["answer q2"]}
        assert_schema_verdict(self, "participant-wake", extra, "invalid")
        empty = make_wake("WAKE")
        empty["memory"] = {}
        assert_schema_verdict(self, "participant-wake", empty, "invalid")


class ThreadCases(unittest.TestCase):
    """@5: who asked what and which messages responded (#94 step 5)."""

    THREADS = [
        {
            "event_id": "q1",
            "author_id": "human:zoe",
            "text": "Does the backoff cap at 30 seconds?",
            "addressed_to": "room",
            "at": "2026-10-06T08:00:00.000Z",
            "responses": [{"event_id": "a1", "author_id": "human:castor", "text": "Yes, 30 s."}],
        },
        {
            "event_id": "v1",
            "author_id": "bot:vigil",
            "text": "Docs too?",
            "responses": [{"event_id": "z1", "author_id": "human:zoe", "text": "Yes please."}],
        },
        {"event_id": "q2", "author_id": "human:zoe", "text": "Lunch?", "addressed_to": "participant", "responses": []},
    ]

    def wake(self, threads, **memory):
        doc = make_wake("DEFER")
        doc["memory"] = {"threads": threads, **memory}
        return doc

    def test_threads_validate_alone_or_with_own_moves(self):
        assert_schema_verdict(self, "participant-wake", self.wake(self.THREADS), "valid")
        both = self.wake(self.THREADS, own_moves=MemoryCases.MOVES)
        assert_schema_verdict(self, "participant-wake", both, "valid")

    def test_malformed_threads_reject(self):
        thread = self.THREADS[0]
        response = thread["responses"][0]
        for bad in (
            [],
            [dict(thread, open=True)],
            [dict(thread, addressed_to="Castor")],
            [dict(thread, text="x" * 281)],
            [{k: v for k, v in thread.items() if k != "responses"}],
            [dict(thread, responses=[{"event_id": "a1"}])],
            [dict(thread, responses=[{k: v for k, v in response.items() if k != "text"}])],
            [dict(thread, responses=[dict(response, text="x" * 281)])],
            [dict(thread, responses=[dict(response, verdict="handled")])],
            [dict(thread, responses=[response] * 5)],
            [dict(thread, author_id="")],
        ):
            with self.subTest(bad=bad):
                assert_schema_verdict(self, "participant-wake", self.wake(bad), "invalid")


class WakeSourceCases(unittest.TestCase):
    """FR-008: explicit sources, no admission meta-answer, facts separate."""

    def test_every_source_validates_without_advice(self):
        for source in ("ACK", "WAKE", "DEFER", "ERROR_FALLBACK", "PREATTENTION_BYPASS"):
            with self.subTest(source=source):
                assert_schema_verdict(self, "participant-wake", make_wake(source), "valid")

    def test_unknown_source_rejects(self):
        assert_schema_verdict(self, "participant-wake", make_wake("BYPASS"), "invalid")

    def test_missing_source_rejects(self):
        doc = make_wake()
        del doc["attention"]["source"]
        assert_schema_verdict(self, "participant-wake", doc, "invalid")

    def test_missing_materialized_facts_reject(self):
        # The wake packet materializes self/room/actors/events/trigger/
        # coverage directly (FR-014), not a wrapped observation reference.
        doc = make_wake()
        del doc["self"]
        assert_schema_verdict(self, "participant-wake", doc, "invalid")

    def test_malformed_materialized_self_rejects(self):
        doc = make_wake()
        del doc["self"]["actor_id"]
        assert_schema_verdict(self, "participant-wake", doc, "invalid")

    def test_v1_shaped_stray_fields_reject(self):
        doc = make_wake(
            trigger={"id": "trigger-speak", "content": "please implement"},
            context=[],
            agent={"id": "turnaware-vigil"},
        )
        assert_schema_verdict(self, "participant-wake", doc, "invalid")


class WakeAdviceCases(unittest.TestCase):
    """@3: the reading appears only on ``WAKE`` and ``DEFER`` packets, the
    turns a participant takes after a model judgment."""

    def test_wake_source_with_advice_is_valid(self):
        doc = make_wake("WAKE", advice=[make_advice()])
        assert_schema_verdict(self, "participant-wake", doc, "valid")

    def test_bypass_wake_is_advice_free(self):
        # 010-Preattention-bypass: no classifier ran, so no advice exists.
        doc = make_wake("PREATTENTION_BYPASS", advice=[make_advice()])
        assert_schema_verdict(self, "participant-wake", doc, "invalid")

    def test_defer_wake_carries_the_reading(self):
        doc = make_wake("DEFER", advice=[make_advice()])
        assert_schema_verdict(self, "participant-wake", doc, "valid")

    def test_judged_through_dates_a_reading_and_needs_one(self):
        dated = make_wake("DEFER", advice=[make_advice()])
        dated["attention"]["judged_through_event_id"] = dated["trigger_event_id"]
        assert_schema_verdict(self, "participant-wake", dated, "valid")
        undated = make_wake("DEFER")
        undated["attention"]["judged_through_event_id"] = undated["trigger_event_id"]
        assert_schema_verdict(self, "participant-wake", undated, "invalid")

    def test_error_fallback_wake_is_advice_free(self):
        doc = make_wake("ERROR_FALLBACK", advice=[make_advice()])
        assert_schema_verdict(self, "participant-wake", doc, "invalid")

    def test_wake_advice_citations_are_checked_against_its_own_events(self):
        # Runtime-adapter-only: the packet is schema-valid in isolation while
        # the citation references no observed event (FR-013). The wake
        # materializes its own events, so citations are checked against
        # the packet itself.
        doc = make_wake("WAKE", advice=[make_advice(evidence_event_ids=["e-ghost"])])
        assert_schema_verdict(self, "participant-wake", doc, "valid")
        self.assertTrue(check_advice_citations(doc, doc))
        grounded = make_wake("WAKE", advice=[make_advice(evidence_event_ids=["e1"])])
        self.assertEqual([], check_advice_citations(grounded, grounded))


class WakeBudgetCases(unittest.TestCase):
    """S15: participant budgets are independent, explicit, and positive."""

    def test_zero_participant_event_budget_rejects(self):
        doc = make_wake()
        doc["coverage"]["max_events"] = 0
        assert_schema_verdict(self, "participant-wake", doc, "invalid")

    def test_negative_participant_byte_budget_rejects(self):
        doc = make_wake()
        doc["coverage"]["max_bytes"] = -5
        assert_schema_verdict(self, "participant-wake", doc, "invalid")

    def test_missing_participant_budgets_are_optional(self):
        doc = make_wake()
        del doc["coverage"]["max_events"]
        del doc["coverage"]["max_bytes"]
        assert_schema_verdict(self, "participant-wake", doc, "valid")


class WakeLedgerRejectionCases(unittest.TestCase):
    """S16: no composed reply, admission answer, or social ledger."""

    def test_reply_and_admission_fields_reject(self):
        for field, value in (
            ("reply", "sure, I can help"),
            ("admission_answer", "SPEAK"),
            ("composed_reply", {"text": "hello"}),
        ):
            with self.subTest(field=field):
                doc = make_wake(**{field: value})
                assert_schema_verdict(self, "participant-wake", doc, "invalid")

    def test_social_ledger_fields_reject(self):
        for field, value in (("handled", False), ("owed", ["reply"])):
            with self.subTest(field=field):
                doc = make_wake(**{field: value})
                assert_schema_verdict(self, "participant-wake", doc, "invalid")


if __name__ == "__main__":
    unittest.main()
