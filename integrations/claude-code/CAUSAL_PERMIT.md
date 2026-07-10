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

- **Concurrent distinct admits** (A and C both admitted, overlapping replies):
  newest-wins binds the current composition correctly, but a reply still in
  flight for A binds to C. Needs a correlation token threaded through
  composition; this does not do that.
- **No `PostToolUse` delivery-confirmed fulfilment** — consume is on the
  *decision*, not a recorded Discord receipt. Vigil's durable send-intent +
  receipt finalize is the robustness upgrade, deferred.
- **DEFER is v1 mechanism, uncalibrated** — the uncertainty threshold's value
  (does it improve room behaviour?) is unproven pending the eval arm; disabled
  unless `NUNCHI_DEFER_MODEL` is set.
- **Full suite is not clean-green here** — targeted suites (causal/defer/install/
  hooks) pass, but a clean-env full run has ~4 pre-existing baseline failures
  reproducible on `main` (not introduced by this branch).
