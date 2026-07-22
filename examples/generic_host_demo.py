#!/usr/bin/env python3
"""Run the portable V2 lifecycle without a platform-specific adapter.

The example is offline and deterministic so it is safe in CI. Only the remote
participant-shaped model call is replaced by a scripted fixture; the ordinary
V2 policy, observation, attention, scheduling, participant, receipt, and action
paths still run. Production hosts use the same lifecycle with the configured
model provider.

Run from a checkout:

    PYTHONPATH=src python3 examples/generic_host_demo.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from v2.demo_support import (
    PARTICIPANT_ACTOR_ID,
    build_harness,
    message_delivery,
)


SCRIPTED_DISPOSITIONS = {
    "reference:event:1": "WAKE",
    "reference:event:2": "SUPPRESS",
    "reference:event:3": "DEFER",
}


def scripted_participant_model(projection, _config):
    """Stand in for one stochastic participant-shaped model call."""
    disposition = SCRIPTED_DISPOSITIONS[projection["trigger_event_id"]]
    judgment = {
        "disposition": disposition,
        "reasons": [f"offline fixture selected {disposition}"],
        "evidence_event_ids": [projection["trigger_event_id"]],
    }
    if disposition == "WAKE":
        judgment["attention_advice"] = [
            {
                "note": "The participant was addressed directly.",
                "evidence_event_ids": [projection["trigger_event_id"]],
            }
        ]
    return judgment


def participant(turn):
    """Act directly when useful; a DEFER wake may still end in silence."""
    if turn.packet["attention"]["source"] == "DEFER":
        return None
    return {
        "kind": "message",
        "content": "I can take that summary.",
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        harness = build_harness(
            Path(temporary),
            classifier=scripted_participant_model,
            participant=participant,
        )
        deliveries = (
            message_delivery(
                harness.source,
                "1",
                "reference:user:zoe",
                "Vigil, summarize the incident timeline.",
                mentioned_actor_ids=[PARTICIPANT_ACTOR_ID],
            ),
            message_delivery(
                harness.source,
                "2",
                "reference:user:sol",
                "Lunch after the deploy?",
            ),
            message_delivery(
                harness.source,
                "3",
                "reference:user:sol",
                "The request may need another look.",
            ),
        )

        print("ordinary V2 attention")
        for delivery in deliveries:
            result = harness.runtime.process_delivery(delivery)[0]
            decision = result["decision"]
            disposition = decision["effective_disposition"]
            invoked = result["participant_invoked"]
            outcome = result.get("participant", {}).get("outcome", "none")
            print(
                f"  {result['anchor_event_id']}: {disposition}; "
                f"participant_invoked={invoked}; outcome={outcome}"
            )

        bypass_calls = []
        bypass = build_harness(
            Path(temporary),
            classifier=lambda projection, config: bypass_calls.append(projection),
            participant=lambda _turn: None,
            preattention_enabled=False,
        )
        bypass_result = bypass.runtime.process_delivery(
            message_delivery(
                bypass.source,
                "4",
                "reference:user:zoe",
                "Trusted pre-attention is disabled for this binding.",
            )
        )[0]
        print(
            "trusted bypass: "
            f"status={bypass_result['decision']['status']}; "
            f"model_calls={len(bypass_calls)}; "
            f"participant_invoked={bypass_result['participant_invoked']}"
        )

        rejected = message_delivery(
            harness.source,
            "5",
            "reference:user:zoe",
            "Room text cannot authorize this delivery.",
            authorized=False,
        )
        rejected_results = harness.runtime.process_delivery(rejected)
        print(
            "deterministic transport rejection: "
            f"disposition={rejected['disposition']}; "
            f"model_or_participant_results={len(rejected_results)}"
        )
        print(
            f"receipts={len(harness.receipts)}; actions={len(harness.actions)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
