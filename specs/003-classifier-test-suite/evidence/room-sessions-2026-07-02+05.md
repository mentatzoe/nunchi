# Room sessions — live multi-agent gate receipts (2026-07-02 and 2026-07-05)

Receipt-level evidence for the first two organic sessions of `#nunchi-room`:
the 2026-07-02 first live in-room deployment and the 2026-07-05 evening
session that produced the findings ledger behind the history-depth work (see
`history-depth-2026-07-07.md`, which analyzes a slice of the same receipts).

This file follows the redaction convention of `history-depth-2026-07-07.md`:
**stats only — zero message content.** The room held organic personal
conversation; no message text, reply text, or gate `reasons` prose is
reproduced here. Participants are identified by role and agent identity (no
human content; the operator's Discord handle is not repeated in prose).
The un-redacted record lives in the operator's private vault
(`2026-07-05-room-retrospective.md`), which this file corroborates — and, in
a few counts, corrects.

## Sources and method

All sources were read read-only on 2026-07-09 from the operator's machine.

1. **Station-side (Claude Code integration) receipts** —
   `~/.claude/nunchi-gate-receipts.jsonl`, the enforcement-hook receipt log.
   **Contamination caveat:** at read time the file held 770 rows, of which
   729 (95%) are test artifacts carrying fixture chat_ids (`c1` ×723,
   `chat-123` ×4, `999` ×2) — an earlier test run wrote receipts to the real
   log path instead of a temp dir. All analysis below filters **strictly** to
   the room's Discord channel id (`1522258711047831653`, the same channel
   already named in `integrations/hermes/nunchi-gate/docs/core-patch/`),
   which leaves 39 rows: 3 on Jul 2, 24 on Jul 5, 12 later (Jul 7–8, out of
   scope here).
2. **Aleph hermes-side receipts** — `~/.hermes/logs/nunchi-gate.jsonl`, the
   plugin's default `log_path` under `HERMES_HOME=~/.hermes` (instance
   confirmed via the `ai.hermes.gateway` launchd plist). 121 in-room rows;
   1 non-room row (an earlier hook-smoke channel) excluded.
3. **Writer-profile hermes-side receipts** —
   `~/.hermes/profiles/writer/logs/nunchi-gate.jsonl`, same plugin under
   `HERMES_HOME=~/.hermes/profiles/writer` (via `ai.hermes.gateway-writer`).
   142 rows, all in-room, none before Jul 5 (the profile was gated that day).
4. **Operator vault record** (private) — the 2026-07-05 room retrospective;
   used for expected values and for claims receipts cannot carry (rendering,
   conversation phases).

Counts are lower bounds: the receipt logs are append-only JSONL with no
gap/rotation detection, so a receipt lost to a gateway restart would be
invisible.

## Session 1 — 2026-07-02 (first live in-room deployment)

- **UTC bounds:** 15:17:34 – 15:44:16 (first row is a Station pipe-test
  untriggered allow; gated verdicts run 15:36:17 – 15:44:16).
- **Participants and integration paths:**
  - Operator (human) — ungated.
  - Aleph (hermes default profile) — `nunchi-gate` plugin at
    `pre_gateway_dispatch`. 4 gated calls.
  - Station (Claude Code) — enforcement hook writing the Station receipts
    log. 3 receipts.
  - Writer profile — **not yet gated** (zero receipts this day).
- **Verdicts:**

  | participant | calls | SPEAK | PASS | ACK | ASK | denials | fastpath |
  |---|---|---|---|---|---|---|---|
  | Aleph (hermes) | 4 | 3 | 0 | 1 | 0 | n/a (advisory allow) | 0 |
  | Station (hook) | 3 | 1 | 0 | 0 | 0 | 0 | 0 |

  The first live in-room verdict ever was Aleph's **ACK** on the operator's
  greeting (15:36:17). Aleph's triggers: operator ×2, Station ×2. Station's
  other two receipts: one `allow-untriggered` (pipe test) and one
  `allow-gate-error` at 15:37:04 — the hook failed open because the
  classifier model env var was missing (misconfiguration, fixed in-session;
  the 15:44 receipt is a clean model-backed SPEAK).
- **history_len:** hermes-side 4/4 at `0` (blind); Station rows 0, 0, 2.
- **Latency (model calls):** Aleph three calls at 1.2–1.4 s and one outlier
  at 12.2 s (the last call of the session); Station's clean call 1.05 s.
- **Classifier:** `google/gemini-3.1-flash-lite` on both paths.

## Session 2 — 2026-07-05 (organic multi-agent evening session)

- **UTC bounds:** 21:26:09 – 23:31:00 (hermes side); Station receipts
  21:27:15 – 23:30:58. Matches the vault record's "~21:26–23:30 UTC".
- **Participants and integration paths:**
  - Operator (human) — ungated.
  - Aleph (hermes default profile) — `nunchi-gate` plugin,
    `HERMES_HOME=~/.hermes`.
  - Writer profile, surfacing as the **Aether** bot identity — same plugin,
    separate instance (`HERMES_HOME=~/.hermes/profiles/writer`).
  - Station (Claude Code) — advisory gate harness plus enforcement hook; the
    receipts log records the enforcement decisions.
- **Verdicts:**

  | participant | calls | SPEAK | PASS | ACK | ASK | enforced denials | fastpath |
  |---|---|---|---|---|---|---|---|
  | Aleph (hermes) | 73 | 38 | 34 | 1 | 0 | n/a | 3 |
  | Writer/Aether (hermes) | 80 | 34 | 44 | 2 | 0 | n/a | 0 |
  | Station (hook) | 24 | 21 | 3 | 0 | 0 | **3** | 0 |

- **Enforced denials:** Station's hook denied 3 of its 24 composed sends
  (`deny-pass` at 22:30:31, 22:47:44, 23:02:09 UTC), each on an
  operator-authored trigger, each judged with `history_len: 10`. Matches the
  vault record's "three enforced denials" exactly.
- **Fastpath hits:** 3, all Aleph-side deterministic mention-fastpath PASSes
  (`classifier_model: null`, PASS confidence 1.0, 62/94/101 ms — no model
  call), each on an operator message that @mentioned other participants
  only.
- **history_len:** hermes-side **153/153 at `0`** (Aleph 73/73, writer
  80/80) — every hermes verdict this night was trigger-only (the F1
  regression; root cause and fix are documented in the retrospective and the
  history-depth branch). Station-side history was **nonzero**: 1 row at 4,
  2 at 6, 21 at 10 (the hook maintains its own rolling history, capped at 10
  at the time) — confirming the retrospective's correction that the nonzero
  values seen mid-session came from the hook's log, not hermes.
- **Trigger authors** (per gate log; each gate skips its own messages):
  - Aleph's 73: operator 23, Aether (peer bot) 29, Station (peer bot) 21.
  - Writer's 80: operator 22, Aleph (peer bot) 37, Station (peer bot) 21.
  - Station's 24: operator 24 — **all** of Station's triggers were
    human-authored, consistent with the retrospective's F7 (Claude Code
    cannot receive bot-authored messages).
- **ACK:** 3 hermes-side ACKs this session (Aleph 1, writer 2); Aleph and
  the writer independently ACKed the same Station-authored meta-commentary
  trigger. With the Jul-2 ACK that makes 4 ACK verdicts across the two
  sessions — matching the retrospective's "ACK fired 4× across agents". One
  ACK was executed as an emoji reaction (operator-record-derived; receipts
  log verdicts, not rendering). **ASK: zero fires** on any path in either
  session, consistent with F4.
- **Identity corroboration:** the vault marked the writer↔Aether mapping
  "inferred, not confirmed". The receipts corroborate it: the writer's log
  contains no Aether-authored triggers (a gate never sees its own identity),
  both hermes logs agree Station authored exactly 21 triggers, and the
  author sets are otherwise complementary (Aleph sees Aether; the writer
  sees Aleph).
- **Latency:** medians ~1.2 s on all three model-call paths (Aleph max
  2.5 s, writer max 4.4 s, Station max 2.2 s); fastpath 62–101 ms.
- **Classifier:** `google/gemini-3.1-flash-lite` everywhere a model was
  called.

## Discrepancies vs the operator's vault record

| Vault claim (Jul 5) | Receipt logs | Assessment |
|---|---|---|
| Aleph 76 calls = 41 SPEAK / 33 PASS / 2 ACK | Jul-5-only: 73 = 38/34/1. Both sessions: 77 = 41/34/2 | SPEAK 41 and ACK 2 match the **two-session cumulative** exactly; the vault figure is evidently cumulative, off by exactly one PASS (34 in logs vs 33) |
| Writer profile 79 | 80 (all Jul 5; no Jul-2 writer receipts exist) | off by one in the other direction |
| 155/155 hermes-side `history_len: 0` | 153/153 (Jul 5 only); 157/157 (both sessions) | the substantive claim — 100% blind — holds exactly; the denominator inherits the two count errors above (155 = 76 + 79) |
| Station ~15 advisory + hook enforcement | 24 enforcement receipts (21 allow / 3 deny) | the advisory-call count is not recorded in any located log; **unverifiable** |
| 3 enforced denials | 3 `deny-pass` | exact match |
| 1 deterministic-fastpath PASS | 3 fastpath PASSes (all Aleph-side) | logs show three, not one |
| 1 ACK executed as a reaction | 4 ACK verdicts across sessions; rendering not logged | consistent; the rendering claim rests on the operator record |

## Provenance, and what the staged smoke will add

Both sessions were **organic and unstaged**: real conversation, no scripted
addressing matrix, no injection checks, no fixed cast. Items in this file
that are **operator-record-derived** rather than receipt-verifiable: the
ACK-as-reaction rendering, the advisory-call estimate, and the session's
conversational phases (category level only: creative performance → personal
support → collaborative fiction → in-room product retrospective).

The staged n-agent smoke (integration plan §A) remains owed and is distinct
from this evidence: it will add a scripted addressing/suppression matrix,
injection-resistance checks, receipts committed to the repo and produced by
a reproducible script — and, unlike these sessions, it will run with the
rolling-history fix live (hermes-side receipts first show nonzero
`history_len` on 2026-07-08).

## Known gaps

- No log of Station's advisory (non-enforcement) gate calls was found; the
  "~15 advisory" figure cannot be checked.
- One stray Station receipt on Jul 5 (21:31:54 UTC) carries a near-miss
  channel id (`…831456` vs the room's `…831653`): an untriggered allow with
  no verdict, excluded by the strict filter; likely a sibling channel.
- The Station receipts file remains contaminated with fixture-chat_id test
  rows (see Sources); this file's counts are unaffected by construction, but
  the log itself should be cleaned or the test path isolated.
- Append-only logs carry no gap detection; all counts are lower bounds.
