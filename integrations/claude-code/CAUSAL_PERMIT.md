# Causal reply-authorization — Claude Code implementation

**The contract is meant to be standard; this file is the Claude *implementation*
of it.** Blocker-fixed per Aleph's review; honest soft spots at the bottom.

## The standard contract (should live in nunchi core, not here)

> An admitted `ACK`/`ASK`/`SPEAK` authorizes **one** response from that same
> live turn, causally bound to its triggering message A. A later `PASS` on B may
> classify B but cannot revise A's authorization. The authorization is consumed
> on send, or expires silently when the turn ends. It never survives a
> turn/session/restart to revive an old answer.

This is what "admission" has to mean everywhere. Hermes carries it in
process/session state (and is only *accidentally* safe today); Codex has its own
runner surface; Claude Code needs a small shared store because its inbound and
outbound gates are **separate processes**. Promoting this to a core primitive
(`reply_authorization` on every non-PASS decision) + a shared contract test each
adapter must pass is the deliberate follow-on.

## The bug this fixes (live, 2026-07-10 03:09)

Claude's outbound gate (`PreToolUse`) reverse-scanned the transcript for the
**newest inbound** line and judged that. Zoe posts invitation A → I compose a
reply for A → a peer posts B → the outbound gate picks B, judges "not addressed
to me," and kills the composed reply as a false `PASS`.

## Implementation (`nunchi_causal_permit.py`)

- **Inbound admit → write authorization** (`write_permit`), *before composition*,
  keyed by `(session, chat)`. A `PASS` writes nothing and never mutates one.
- **Outbound → honor it** (`read_permit`): bind `trigger` to the origin message,
  not newest-inbound; include the **post-origin tail** with timestamps so a
  drifted thread can still correctly `PASS`. No permit → legacy scan.
- **Send decision → consume it** (`clear_permit`, one-shot): so an unrelated
  later send cannot inherit it.

**Not a service queue:** session-scoped, newest-wins (not FIFO), TTL-silent, and
consumed on first decision.

## Blockers from review — fixed

1. **Installer ships the modules.** `nunchi_causal_permit.py` + `nunchi_defer.py`
   added to `CLAUDE_HOOK_FILES`; `test_install.py::ClaudeInstalledCausalPath`
   runs the *installed* hook end-to-end and asserts it binds A. (Previously a
   normal `nunchi-install` silently shipped the old bug.)
2. **One-shot.** The outbound hook now calls `clear_permit` on the first
   decision. A transport retry of *that* send degrades to legacy (documented
   trade — TTL is not a turn boundary, so we don't pretend it distinguishes a
   retry from an unrelated later send).
3. **Concurrency.** One file **per (session, chat)** — atomic rename per key.
   Concurrent admits for different keys can't clobber each other (fixes the
   shared read-modify-write lost-permit race).

## Tests

`tests/test_causal_permit.py`: fixture-zero (binds A, B in post-tail), legacy
contrast (binds B), no cross-session bind, one-shot consume, per-key isolation,
+ permit units. `tests/test_install.py`: installed-path bind. See
`nunchi_defer.py` / `tests/test_defer.py` for the DEFER arm and `DEFER_EVAL.md`
for its evaluation plan.

## Honest soft spots (not solved)

- **Concurrent same-key admits** (A and C admitted for the same session+chat,
  overlapping replies): resolution is last-*write*-wins on the rename, **not**
  newest-by-timestamp, so a concurrent *older* admit that renames last would win.
  Characterized by `test_same_key_is_last_write_wins_not_newest_timestamp`.
  Closing it needs one file per admission selected by an immutable sequence, not
  per-key overwrite.
- **Retry causality is unsupported** — the permit is one-shot (consumed on the
  first outbound decision), so a transport *retry* of that same send falls back to
  legacy newest-inbound binding. Made legible as an `expectedFailure`
  (`test_retry_after_consume_rebinds_origin_UNSUPPORTED`) so "documented" cannot
  read as "solved"; closing it needs a retry correlation token distinct from the
  one-shot permit.
- **No `PostToolUse` delivery-confirmed fulfilment** — consume is on the
  *decision*, not a recorded Discord receipt. Vigil's durable send-intent +
  receipt finalize is the robustness upgrade, deferred.
- **DEFER is v1 mechanism, uncalibrated** — the uncertainty threshold's value
  (does it improve room behaviour?) is unproven pending the eval arm; disabled
  unless `NUNCHI_DEFER` is set. DEFER is *abstention*, not model routing: an
  uncertain PASS returns the turn to the participant's own judgment, with no
  second classifier in the live path (`DEFER_EVAL.md`).
- **Full suite status (re-verified 2026-07-10)** — on this machine (Python 3.14,
  classifier API env scrubbed) both `main` (957 tests, 8 skipped) and this branch
  (983 tests, 8 skipped, 1 expected failure — the retry-causality gap above) run
  fully green. An earlier note of "~4 baseline failures" did **not** reproduce
  here and appears to have been transient/env-specific; it is retracted rather
  than left standing. CI's offline 3.11–3.13 matrix remains the authoritative
  gate — I have not personally run that matrix.
