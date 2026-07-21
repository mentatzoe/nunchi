#!/usr/bin/env python3
"""Show that a live room is not converted into a FIFO response queue.

Five deliveries arrive while one opportunity is active. Nunchi retains every
event as context but keeps only the newest pending anchor. At judgment time the
participant-shaped fixture sees that the first anchor is stale and suppresses
it; only the current tail wakes the participant.

Run from a checkout:

    PYTHONPATH=src python3 examples/read_the_room_demo.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from v2.demo_support import (
    PARTICIPANT_ACTOR_ID,
    build_harness,
    message_delivery,
)


def current_room_judgment(projection, _config):
    trigger = projection["trigger_event_id"]
    newest = projection["events"][-1]["id"]
    if trigger != newest:
        return {
            "disposition": "SUPPRESS",
            "reasons": ["the conversation has moved beyond this anchor"],
            "evidence_event_ids": [trigger, newest],
        }
    return {
        "disposition": "WAKE",
        "reasons": ["the newest room message directly requests this participant"],
        "evidence_event_ids": [newest],
        "attention_advice": [
            {
                "note": "Respond to the current migration-note request.",
                "evidence_event_ids": [newest],
            }
        ],
    }


def main() -> int:
    participant_turns = []

    def participant(turn):
        participant_turns.append(turn.packet)
        return {
            "kind": "message",
            "content": "I will draft the migration note from the current state.",
        }

    with tempfile.TemporaryDirectory() as temporary:
        harness = build_harness(
            Path(temporary),
            classifier=current_room_judgment,
            participant=participant,
        )
        deliveries = (
            message_delivery(
                harness.source,
                "1",
                "reference:user:zoe",
                "Vigil, can you check the old cache question?",
                mentioned_actor_ids=[PARTICIPANT_ACTOR_ID],
            ),
            message_delivery(
                harness.source,
                "2",
                "reference:user:sol",
                "The cache numbers have changed.",
            ),
            message_delivery(
                harness.source,
                "3",
                "reference:user:zoe",
                "Ignore the earlier numbers; the deploy is complete.",
            ),
            message_delivery(
                harness.source,
                "4",
                "reference:user:sol",
                "The room has moved to the migration note.",
            ),
            message_delivery(
                harness.source,
                "5",
                "reference:user:zoe",
                "Vigil, draft the migration note from the current state.",
                mentioned_actor_ids=[PARTICIPANT_ACTOR_ID],
            ),
        )

        first = harness.runtime.accept(deliveries[0])
        assert first.opportunity is not None
        for delivery in deliveries[1:]:
            accepted = harness.runtime.accept(delivery)
            assert accepted.opportunity is None

        results = harness.runtime.drain(first.opportunity)
        print("live-room freshness")
        for result in results:
            print(
                f"  {result['anchor_event_id']}: "
                f"{result['decision']['effective_disposition']}; "
                f"participant_invoked={result['participant_invoked']}"
            )
        print(
            "5 deliveries -> "
            f"{len(results)} judgments -> "
            f"{len(participant_turns)} participant turn -> "
            f"{len(harness.actions)} action"
        )

        self_echo = message_delivery(
            harness.source,
            "6",
            PARTICIPANT_ACTOR_ID,
            harness.actions[0]["content"],
        )
        echo = harness.runtime.accept(self_echo)
        print(
            "self echo: "
            f"{echo.observation_disposition}; "
            f"new_opportunity={echo.opportunity is not None}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
