#!/usr/bin/env python3
"""Minimal offline V2 host showing contribution and silence ownership."""

from __future__ import annotations

from nunchi.attention import AttentionEngine, AttentionPolicy, ParticipantProfile
from nunchi.observation import ObservationProvider, ParticipantBinding
from nunchi.participant import (
    ConversationOpportunityScheduler,
    ParticipantTurnHost,
    TransportResult,
)
from nunchi.pipeline import NunchiV2Pipeline
from nunchi.receipts import ReceiptJournal


class DemoAttention:
    name = "demo-attention"
    provider = "offline"
    model_id = "fixed"

    def judge(self, *, projection, **_):
        # The typed answers a chat model returns: conversation, addressed to
        # the participant, nothing answered yet, and speaking fits best.
        return {
            "conversation": 0.98,
            "addressee": {"participant": 0.9, "room": 0.1, "someone_else": 0.0, "nobody": 0.0},
            "answered": 0.02,
            "answered_by": None,
            "mid_thought": 0.05,
            "adds_something": 0.9,
            "move": {"speak": 0.95, "mhm": 0.02, "wait": 0.02, "stay_quiet": 0.01},
            "notes": [
                {
                    "note": "The demo message asks Helpbot directly.",
                    "evidence_event_ids": [projection["trigger_event_id"]],
                }
            ],
        }


class DemoTransport:
    def dispatch(self, *, action, wake):
        print({"room": wake["room"]["id"], "action": action})
        return TransportResult("sent", "demo")


def main() -> int:
    binding = ParticipantBinding(
        "helpbot",
        "generic:actor:helpbot",
        "generic",
        "room-1",
        "generic:room-1",
        names=("Helpbot",),
    )
    profile = ParticipantProfile(
        "helpbot-profile",
        binding.participant_id,
        binding.actor_id,
        "Answer directly and briefly.",
        "example:trusted",
        "0" * 64,
    )
    receipts = ReceiptJournal()
    observation = ObservationProvider(binding, receipts=receipts)
    scheduler = ConversationOpportunityScheduler("helpbot:room-1")
    host = ParticipantTurnHost(
        observation=observation,
        participant=lambda **kwargs: {
            "kind": "message",
            "origin_event_id": kwargs["wake"]["trigger_event_id"],
            "text": "Here is the concise answer.",
        },
        transport=DemoTransport(),
        scheduler=scheduler,
        receipts=receipts,
    )
    pipeline = NunchiV2Pipeline(
        observation=observation,
        attention=AttentionEngine(
            profile=profile,
            model=DemoAttention(),
            policy=AttentionPolicy(),
            receipts=receipts,
        ),
        host=host,
        scheduler=scheduler,
    )
    outcome = pipeline.handle_delivery(
        delivery_id="delivery-1",
        event={
            "id": "message-1",
            "type": "message",
            "author_id": "generic:actor:zoe",
            "text": "Helpbot, summarize the result.",
            "mentioned_actor_ids": [binding.actor_id],
            "mentions_room": False,
        },
        actors={
            "generic:actor:zoe": {"display_name": "Zoe", "kind": "human"},
        },
    )
    print([record["stage"] for record in receipts.all_records()])
    return 0 if outcome.opportunities[0].transport.delivery == "sent" else 1


if __name__ == "__main__":
    raise SystemExit(main())
