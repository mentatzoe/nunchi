# V1 test retirement and V2 replacement

The top-level `tests/test_*.py` corpus records the retired V1 verdict, hook,
send-gate, installer, and adapter behavior. It is preserved for historical
comparison but is not a supported or executable product contract after the
atomic V2 cutover.

`python3 -m unittest` loads only `tests/v2/`:

| Retired V1 concern | V2 replacement |
|---|---|
| PASS/ACK/ASK/SPEAK classifier and `admit` CLI | attention request/decision contract corpus; `test_shared_foundation.py`; V2 CLI tests |
| inferred self/peer and responder suppression | exact canonical identity, self retention, alias adversaries, participant wake/silence tests |
| FIFO history buffer | bounded observation, relation closure, continuation, coalescing, restart and gap tests |
| prompt/send hooks and second judgment | host-owned Codex room runner and single output commit tests |
| per-adapter V1 gates | canonical Discord, Matrix, Telegram, and generic normalization/conformance tests |
| transport send backstop only | exact one-use HMAC, durable replay journal, bounded queue gap, and native result tests |
| Hermes and Claude Code integration tests | outside this candidate by explicit product scope; no V2 implementation or arming claim |
| repository-copy installer | clean-wheel install, stable V2 state initialization, permission and no-fallback tests |

The portable schema corpus in `tests/v2/contract/` remains the oracle for the
published platform interface. The adversarial runtime suite adds relational,
lifecycle, persistence, authorization, transport, and installed-entry-point
checks that JSON Schema cannot express.
