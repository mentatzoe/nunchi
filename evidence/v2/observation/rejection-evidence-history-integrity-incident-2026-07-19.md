# Rejection-evidence history integrity incident

**Date recorded**: 2026-07-19
**Affected path**: `evidence/v2/observation/review-2026-07-19-80c1de2-late-rejection.md`
**Classification**: semantic verdict preserved; exact bytes rewritten
**Recovery baseline**: `abad8d85e8150bfd2716ab77ebb3791827591bf1`
**Recovery blob**: `79c43c56acdb3151967f37788af7aa44b5c0b7cb`
**Recovery SHA-256**: `6062ce5a1937314d5e74b4460cdf69985966953da58844fed2b309ca918b5015`

## Incident

Phase 27 removed Markdown hard-break trailing spaces from lines 3, 4, and 6 of
the historical `80c1de2` rejection while fixing activation-range whitespace.
That cleanup changed exact historical bytes. It did not alter the target,
REJECT verdict, findings, or authority disclaimer, but it was still a rewrite
and therefore contradicts any claim of byte-identical preservation.

Exact transition:

```text
pre-rewrite commit: a49313a5354259346e1089e759184b9f08735b37
pre-rewrite blob:   63f586542ea43f9eac4d4048ca8ae3188a13d536
pre-rewrite SHA256: 4495507ac0e6665567e56b343df517469e33f03c9a3cc7f730469ccd4c7f9f2c

recovery commit:    abad8d85e8150bfd2716ab77ebb3791827591bf1
recovery blob:      79c43c56acdb3151967f37788af7aa44b5c0b7cb
recovery SHA256:    6062ce5a1937314d5e74b4460cdf69985966953da58844fed2b309ca918b5015
```

Git history records only the introduction commit and the Phase 27 rewrite. The
violation cannot be made absent retroactively. Shared governance therefore pins
the recovery bytes at `abad8d85` and rejects deletion or any later change.

All other registered `review-*-rejection.md` records replay byte-identically
from introduction and are immutable from first use. New rejection records must
be added to the explicit registry in the same commit that introduces them.

This incident record discloses a provenance fault. It does not weaken or reverse
the preserved REJECT verdict and grants no candidate, handoff, acceptance,
integration, deployment, release, promotion, or cutover authority.
