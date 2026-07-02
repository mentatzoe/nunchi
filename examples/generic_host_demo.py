#!/usr/bin/env python3
"""Demo: a NON-cc-connect host adopting the gate via the transport-neutral contract.

This stands in for a plain message-queue / "Slack-style" loop — no cc-connect, no
Discord, no platform glue. A worker `helpbot` pulls events off a queue and, for
each one, asks the gate whether to speak BEFORE composing anything. It acts only
on the transport-neutral decision the adapter returns:

    if result.silent:  the host posts nothing
    else:              the host would compose exactly one turn in result.run_shape

It never composes reply prose — it just shows the routing a real host would do.
To prove the contract is platform-agnostic, it also derives this host's OWN
suppression sentinel via ``result.silent_token("<<HOST_NOOP>>")`` — a made-up
magic string for a transport that suppresses sends by a final-output marker.
Nothing here references cc-connect's sentinel.

Run live (real classifier):
    export NUNCHI_CLASSIFIER_MODEL=google/gemini-3.1-flash-lite
    export OPENROUTER_API_KEY=...
    PYTHONPATH=src python3 examples/generic_host_demo.py

Run offline (pin every verdict, just to see the routing/plumbing):
    export NUNCHI_CLASSIFIER_TEST_RESULT='{"verdict":"PASS","confidences":{"PASS":1,"ACK":0,"ASK":0,"SPEAK":0},"context_checked":[],"reasons":["dev"]}'
    PYTHONPATH=src python3 examples/generic_host_demo.py

    # Or inject a different pinned verdict to watch it route a SPEAK:
    export NUNCHI_CLASSIFIER_TEST_RESULT='{"verdict":"SPEAK","confidences":{"PASS":0,"ACK":0,"ASK":0,"SPEAK":1},"context_checked":[],"reasons":["dev"]}'
"""

import os
import sys

from nunchi.adapters.channel import gate

# This host's own suppression marker. It is OUR convention, not Nunchi's — a
# transport that drops an outbound message when the worker's final output equals
# this string. (cc-connect has a different one; the gate is agnostic to both.)
HOST_NOOP_SENTINEL = "<<HOST_NOOP>>"

AGENT = {"id": "helpbot", "role": "participant", "mention_id": "U_HELPBOT"}

# A few canned events off the queue: (label, trigger, recent transcript oldest-first).
QUEUE = [
    (
        "operator asks this worker for substantive help",
        {"content": "helpbot, can you summarize today's incident timeline?",
         "author": "dana", "author_kind": "operator", "message_id": "evt-1"},
        [],
    ),
    (
        "two peers chatting, nobody addressed this worker",
        {"content": "yeah I'll grab lunch after the deploy", "author": "sam",
         "author_kind": "peer", "message_id": "evt-2"},
        [{"content": "deploy's green, merging now", "author": "lee",
          "author_kind": "peer", "message_id": "evt-1b"}],
    ),
    (
        "trigger just echoes what this worker already said (duplicate)",
        {"content": "someone should note the cache TTL changed", "author": "lee",
         "author_kind": "peer", "message_id": "evt-3"},
        [{"content": "Heads up: cache TTL changed to 60s in this release.",
          "author": "helpbot", "author_kind": "self", "message_id": "evt-2b"}],
    ),
]


def main() -> int:
    if not (os.environ.get("NUNCHI_CLASSIFIER_MODEL")
            or os.environ.get("NUNCHI_CLASSIFIER_TEST_RESULT")):
        print("Set NUNCHI_CLASSIFIER_MODEL (+OPENROUTER_API_KEY) for a live run, "
              "or NUNCHI_CLASSIFIER_TEST_RESULT to see routing offline.",
              file=sys.stderr)
        return 2

    print(f"[host] generic message-queue worker: {AGENT['id']}")
    print("[host] asking the gate per event; acting only on result.silent / verdict.\n")

    posted = suppressed = 0
    for label, trigger, history in QUEUE:
        result = gate(
            trigger, history,
            agent_id=AGENT["id"], agent_role=AGENT["role"],
            agent_mention_id=AGENT["mention_id"],
            surface={"type": "generic-queue"}, fail_policy="open",
        )

        print(f"• {label}")
        print(f"    trigger : {trigger['content']}")
        print(f"    verdict : {result.verdict}")
        if result.silent:
            suppressed += 1
            # Transport-neutral branch: just don't post. We ALSO show this host's
            # own sentinel, to demonstrate the generic suppression-token helper.
            print("    [host] suppressed (posted nothing)")
            print(f"    [host] (our suppression marker would be: "
                  f"{result.silent_token(HOST_NOOP_SENTINEL)!r})")
        else:
            posted += 1
            # Admission only — we route, we do NOT compose the reply here.
            print(f"    [host] would compose one turn — run_shape: {result.run_shape}")
            # On a non-PASS verdict the host's sentinel helper yields "" (no suppression).
            assert result.silent_token(HOST_NOOP_SENTINEL) == ""
        if result.reasons:
            print(f"    reason  : {result.reasons[0]}")
        print()

    print(f"[host] {suppressed} suppressed, {posted} routed for composition "
          f"— classifier model: {result.classifier_model}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
