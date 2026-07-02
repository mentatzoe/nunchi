# Loader snippet: shell out to the admission gate before replying

Paste the block below into your agent's loader file (`CLAUDE.md`, `AGENTS.md`,
`GEMINI.md`, or whatever your runtime loads as standing instruction). It
implements **Path A** from [`docs/integration.md`](../docs/integration.md): the
agent calls Nunchi first and obeys the verdict, instead of improvising the
"should I speak?" decision inline.

It is transport-neutral — nothing below assumes cc-connect, Discord, Slack, or
any particular platform. The agent posts a normal turn or stays silent; the gate
decides which.

## Operator setup (one-time, outside the loader)

The host process must have the classifier configured in its environment before
the agent runs. Set **one** of:

- **Live:** `NUNCHI_CLASSIFIER_MODEL` (e.g. `google/gemini-3.1-flash-lite`)
  plus an API key (`OPENROUTER_API_KEY` or `NUNCHI_CLASSIFIER_API_KEY`).
- **Dev / offline (no provider call):** `NUNCHI_CLASSIFIER_TEST_RESULT` set to
  a pinned decision JSON, e.g.
  `{"verdict":"PASS","confidences":{"PASS":1,"ACK":0,"ASK":0,"SPEAK":0},"context_checked":[],"reasons":["dev"]}`.

Install once with `pip install .` (gives you the `nunchi-channel` console
script), or run from a checkout with `PYTHONPATH=src python3 -m nunchi.adapters`.

---

## Paste this into your loader file

```markdown
## Before any channel output

You do NOT decide on your own whether to speak. Before composing anything that
would appear in the channel, run the admission gate and obey its verdict.

1. Build a JSON payload from what you're reacting to:
   - `trigger`: the message that woke you — at least `content`; include
     `message_id`, `author`, and `author_kind` when you have them.
   - `history`: the recent transcript (about the last 10 messages), **oldest
     first**. Tag each line's `author_kind` as one of:
       - `operator` — a human / the person you serve,
       - `peer` — another agent or participant,
       - `self` — a message you yourself wrote earlier
         (lets the gate suppress duplicating or echoing your own turn).
   - `agent`: your own identity — `{"id": "<YOUR_AGENT_ID>"}`. If this surface
     uses @mentions, also add `"mention_id": "<YOUR_MENTION_HANDLE>"` so the gate
     can tell a mention aimed at someone else apart from one aimed at you.
   - (optional) `surface`: `{"type": "<YOUR_PLATFORM>"}` for context/logging.
   - (optional) `pinned_rules`: your channel's governance text, as a string.
   - (optional) `fail_policy`: `"open"` (default; gate-unavailable -> SPEAK),
     `"closed"` (gate-unavailable -> PASS), or `"raise"`.

   Example payload:

       {
         "trigger": {
           "content": "<THE_MESSAGE_THAT_TRIGGERED_YOU>",
           "author": "<SENDER>",
           "author_kind": "operator",
           "message_id": "<TRIGGER_ID>"
         },
         "history": [
           {"content": "<EARLIER_MESSAGE>", "author": "<SOMEONE>",
            "author_kind": "peer", "message_id": "<ID_1>"},
           {"content": "<SOMETHING_YOU_SAID>", "author": "<YOUR_AGENT_ID>",
            "author_kind": "self", "message_id": "<ID_2>"}
         ],
         "agent": {"id": "<YOUR_AGENT_ID>", "mention_id": "<YOUR_MENTION_HANDLE>"},
         "fail_policy": "open"
       }

2. Pipe that payload to the gate and read the JSON it prints:

       echo "$PAYLOAD" | nunchi-channel
       # or, from a checkout without installing:
       echo "$PAYLOAD" | PYTHONPATH=src python3 -m nunchi.adapters

3. Act on the directive:
   - If the JSON has `"silent": true` -> **post nothing this turn. Stop.**
   - Otherwise read `verdict` and `run_shape`, and compose **exactly one** turn
     in that shape. Do not exceed the run-shape:
       - `SPEAK` — one normal participant turn.
       - `ASK`   — one blocking clarifying question, nothing else.
       - `ACK`   — one short presence signal (an emoji or a single sentence).

The gate decides admission only. It never writes your reply — you compose the
turn yourself once it admits you.
```

---

## Optional: suppression-by-magic-string transports

Most hosts just branch on `"silent": true` and post nothing. But some transports
suppress an outbound message when the agent's *final output* is a specific magic
string. If yours is one of those, add `--silent-token` so the CLI prints **your**
token (and nothing else) on PASS, instead of JSON:

```sh
echo "$PAYLOAD" | nunchi-channel --silent-token "<YOUR_TRANSPORTS_SENTINEL>"
# PASS  -> prints exactly: <YOUR_TRANSPORTS_SENTINEL>   (emit it verbatim to stay silent)
# other -> prints the normal JSON directive             (compose one turn)
```

The token is **your platform's convention, not Nunchi's** — supply your own.

cc-connect is one such transport, provided as a named preset of this same
mechanism (no special status):

```sh
echo "$PAYLOAD" | nunchi-channel --format cc-connect
# equivalent to: --silent-token CC_CONNECT_SILENT_PASS
```

With a token configured, the loader's step 3 becomes: if the gate prints your
sentinel, emit it verbatim and stop; otherwise compose one turn per the JSON.
