#!/usr/bin/env python3
"""End-to-end demo: route a real multi-turn channel scenario through the gate.

Agent `dalgos` sits in a shared Discord-style channel and must decide, for each
incoming trigger, whether to speak. This runs each turn through the live
admission classifier via the channel adapter and prints the verdict and what the
agent's transport would actually emit (the silent-pass sentinel, or nothing —
leaving the agent to compose its own turn).

Run live:
    export TURNAWARE_CLASSIFIER_MODEL=google/gemini-2.5-flash
    export OPENROUTER_API_KEY=...
    PYTHONPATH=src python3 examples/read_the_room_demo.py

Run offline (pin every verdict, just to see the routing/plumbing):
    export TURNAWARE_CLASSIFIER_TEST_RESULT='{"verdict":"PASS","confidences":{"PASS":1,"ACK":0,"ASK":0,"SPEAK":0},"context_checked":[],"reasons":["pinned"]}'
    PYTHONPATH=src python3 examples/read_the_room_demo.py
"""

import os
import sys

from turnaware.adapters.channel import gate

AGENT = {"id": "dalgos", "role": "participant", "mention_id": "1494822747856967683"}

# Each turn: (label, trigger, recent transcript, expected-ish verdict for the demo narrative)
# A realistic burst of channel traffic the agent `dalgos` is woken on. Each entry
# is (label, trigger, recent transcript). The demo prints the gate's verdict,
# reason, and what the agent's transport would emit — it asserts nothing, it
# shows the gate reading the room.
TURNS = [
    (
        "operator addresses a different agent",
        {"content": "vigil, can you rebase the classifier branch onto main?", "author": "zoe",
         "author_kind": "human", "message_id": "m-1"},
        [],
    ),
    (
        "operator asks me directly for substantive work",
        {"content": "dalgos, summarize the tradeoffs of the in-process cache for the channel.",
         "author": "zoe", "author_kind": "human", "message_id": "m-2"},
        [],
    ),
    (
        "a peer nudges me about work my earlier turn already covered",
        {"content": "dalgos should double-check the rate-limit path.", "author": "castor",
         "author_kind": "peer_bot", "message_id": "m-3"},
        [{"content": "Rate-limit path looks correct to me after the last fix.",
          "author": "dalgos", "author_kind": "self", "message_id": "m-2b"}],
    ),
    (
        "an @mention aimed at someone else",
        {"content": "Hey <@1494822530643398827>, could you post a recap when you get a sec?",
         "author": "zoe", "author_kind": "human", "message_id": "m-4"},
        [],
    ),
    (
        "operator hands me a genuinely new task",
        {"content": "dalgos, draft the migration note for the cache change and share it here.",
         "author": "zoe", "author_kind": "human", "message_id": "m-5"},
        [],
    ),
]


def main() -> int:
    if not (os.environ.get("TURNAWARE_CLASSIFIER_MODEL") or os.environ.get("TURNAWARE_CLASSIFIER_TEST_RESULT")):
        print("Set TURNAWARE_CLASSIFIER_MODEL (+OPENROUTER_API_KEY) for a live run, "
              "or TURNAWARE_CLASSIFIER_TEST_RESULT to see routing offline.", file=sys.stderr)
        return 2

    print(f"agent: {AGENT['id']}  (mention_id {AGENT['mention_id']})")
    print("The gate decides whether dalgos speaks; PASS emits the sentinel "
          "cc-connect suppresses.\n")
    model_seen = None
    spoke = silent = 0
    for label, trigger, history in TURNS:
        result = gate(trigger, history, agent_id=AGENT["id"],
                      agent_role=AGENT["role"], agent_mention_id=AGENT["mention_id"],
                      surface={"type": "discord"}, fail_policy="open")
        model_seen = result.classifier_model or model_seen
        if result.silent:
            silent += 1
            action = "stay silent (host posts nothing)"
        else:
            spoke += 1
            action = "agent composes its turn"
        print(f"• {label}")
        print(f"    trigger : {trigger['content']}")
        print(f"    verdict : {result.verdict:5s} -> {action}")
        if result.reasons:
            print(f"    reason  : {result.reasons[0]}")
        print()
    print(f"{silent} suppressed, {spoke} spoke — classifier model: {model_seen}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
