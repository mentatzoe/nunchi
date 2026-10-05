"""Attention failures follow the error policy; they never silently suppress.

Only the engine's own cancel signal may produce the one error that never
wakes (`cancelled`). Provider or model text, exception types raised by a
model, and malformed judgments are provider failures, which wake under the
default error policy.
"""

from __future__ import annotations

import threading
import unittest

from nunchi.attention import (
    ATTENTION_JUDGMENT_SCHEMA,
    AttentionCancelled,
    AttentionDeadlineExceeded,
    AttentionError,
)
from tests.v2.test_shared_foundation import FixtureModel, foundation, message


def _deliver(pipeline, event_id="e1"):
    return pipeline.handle_delivery(
        delivery_id=f"d-{event_id}",
        event=message(event_id, text="@Vigil can you check this?"),
        actors={"human:zoe": {"kind": "human"}},
    )


class _RaisingModel(FixtureModel):
    def __init__(self, exc: BaseException) -> None:
        super().__init__()
        self.exc = exc

    def judge(self, **kwargs):
        super().judge(**kwargs)
        raise self.exc


class _JudgmentModel(FixtureModel):
    def __init__(self, judgment) -> None:
        super().__init__()
        self.judgment = judgment

    def judge(self, **kwargs):
        super().judge(**kwargs)
        return self.judgment(kwargs["projection"])


class ProviderTextNeverSuppressesTests(unittest.TestCase):
    def assert_wakes_on_provider_failure(self, model) -> None:
        wakes = []
        pipeline, _, _, receipts = foundation(
            model=model,
            participant=lambda **kwargs: wakes.append(kwargs["wake"]) or None,
        )
        outcome = _deliver(pipeline)
        opportunity = outcome.opportunities[0]
        self.assertEqual("error", opportunity.decision_status)
        self.assertEqual("ERROR_FALLBACK", opportunity.effective_disposition)
        self.assertEqual(1, len(wakes), "the participant must be woken")
        error = receipts.records(opportunity.request_id)[1]["body"]["error"]
        self.assertEqual("provider-failure", error["code"])

    def test_provider_text_mentioning_cancelled_still_wakes(self) -> None:
        self.assert_wakes_on_provider_failure(
            _RaisingModel(RuntimeError("stream cancelled by upstream proxy"))
        )

    def test_attention_error_text_mentioning_cancelled_still_wakes(self) -> None:
        self.assert_wakes_on_provider_failure(
            _RaisingModel(AttentionError("upstream request was cancelled"))
        )

    def test_model_cannot_raise_the_engine_cancellation_type(self) -> None:
        self.assert_wakes_on_provider_failure(
            _RaisingModel(AttentionCancelled("spoofed cancellation"))
        )

    def test_model_raised_deadline_is_a_provider_failure(self) -> None:
        self.assert_wakes_on_provider_failure(
            _RaisingModel(AttentionDeadlineExceeded("provider's own timeout"))
        )

    def test_duplicate_evidence_is_a_provider_failure_not_a_crash(self) -> None:
        def duplicated(projection):
            trigger = projection["trigger_event_id"]
            return {
                "disposition": "SUPPRESS",
                "reasons": ["duplicated citation"],
                "evidence_event_ids": [trigger, trigger],
                "legacy_verdict_confidences": {
                    "PASS": 0.9, "ACK": 0.03, "ASK": 0.03, "SPEAK": 0.04
                },
            }

        self.assert_wakes_on_provider_failure(_JudgmentModel(duplicated))


class EngineOwnedErrorsTests(unittest.TestCase):
    def test_engine_cancellation_still_does_not_wake(self) -> None:
        release = threading.Event()
        model = FixtureModel(block=release)
        wakes = []
        pipeline, _, _, receipts = foundation(
            model=model,
            participant=lambda **kwargs: wakes.append(kwargs["wake"]) or None,
        )
        request_ids = []

        def deliver() -> None:
            outcome = _deliver(pipeline)
            request_ids.extend(o.request_id for o in outcome.opportunities)

        worker = threading.Thread(target=deliver)
        worker.start()
        self.assertTrue(model.started.wait(5))
        pipeline.scheduler.cancel()
        release.set()
        worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertEqual([], wakes)


class JudgmentSchemaMatchesValidatorTests(unittest.TestCase):
    def test_schema_requires_the_non_empty_values_the_validator_requires(self) -> None:
        props = ATTENTION_JUDGMENT_SCHEMA["properties"]
        self.assertEqual(1, props["reasons"]["items"]["minLength"])
        self.assertEqual(1, props["evidence_event_ids"]["items"]["minLength"])
        advice = props["attention_advice"]["items"]["properties"]
        self.assertEqual(1, advice["note"]["minLength"])
        self.assertEqual(1, advice["evidence_event_ids"]["minItems"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
