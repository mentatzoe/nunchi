# V1 test retirement and V2 replacement

The V1 test corpus (top-level `tests/test_*.py`, its helpers, and
`tests/fixtures/`) covered the retired V1 verdict, hook, send-gate, installer,
and adapter behavior. It never ran after the V2 cutover and was removed on
2026-10-04; it is recoverable from git history (`git show v0.2.0:tests/`).

`python3 -m unittest` loads `tests/v2/`. Each retired concern maps to V2
coverage:

| Retired V1 concern | V2 replacement |
|---|---|
| PASS/ACK/ASK/SPEAK classifier and `admit` CLI | attention request/decision contract corpus; `test_shared_foundation.py`; V2 CLI tests |
| inferred self/peer and responder suppression | exact canonical identity, self retention, alias adversaries, participant wake/silence tests |
| FIFO history buffer | bounded observation, relation closure, continuation, coalescing, restart and gap tests |
| prompt/send hooks and second judgment | host-owned Codex room runner and single output commit tests |
| per-adapter V1 gates | canonical Discord, Matrix, Telegram, and generic normalization/conformance tests |
| transport send backstop only | exact one-use HMAC, durable replay journal, bounded queue gap, and native result tests |
| Discord token hygiene | `tests/v2/test_mcp_discord_token_hygiene.py` |
| Hermes and Claude Code integration tests | `tests/v2/test_hermes_*.py` and `tests/v2/test_claude_code*.py` |
| repository-copy installer | clean-wheel install, stable V2 state initialization, permission and no-fallback tests |

The portable schema corpus in `tests/v2/contract/` remains the oracle for the
published platform interface. The adversarial runtime suite adds relational,
lifecycle, persistence, authorization, transport, and installed-entry-point
checks that JSON Schema cannot express.

Documentation truthfulness is active V2 coverage at
`tests/v2/test_docs_truthfulness.py`. The retired top-level V1 documentation
test was removed when the live integration guard was ported; its V1 adapter
defaults, release-state claims, and source-only installation assertions are
recoverable from git history but are not executable V2 expectations.
