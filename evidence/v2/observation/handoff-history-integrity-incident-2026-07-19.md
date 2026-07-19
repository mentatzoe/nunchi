# Slice 020 ordinary handoff packet — history integrity incident

**Date recorded**: 2026-07-19
**Affected path**: `evidence/v2/observation/handoff.md`
**Classification**: historical append-only claim false; lifecycle ledgers unaffected
**Recovery baseline commit**: `a49313a5354259346e1089e759184b9f08735b37`
**Recovery baseline blob**: `ae91264cb67aa5fca1e05d4de7a5b09bf1a712cc`
**Recovery baseline SHA-256**: `4fdfec86798c941e8c7ad2b7da0957fb913099108a6c5b2167dcb0b085f3cc3d`

## Incident

The ordinary documentation-disposition/handoff packet declared itself
append-only after first use. A complete Git-object replay proves that claim was
false. Four historical transitions changed prior bytes instead of retaining the
old content as a prefix:

```text
418432a50815 -> 77a94cf1f56e
cd61dfd649b8 -> 75ff65fa98a3
75ff65fa98a3 -> 247e28202399
ff3c5a2e71bb -> cd8917c56f0d
```

The first rewrite changed original documentation dispositions, interface/owner
language, packet completion, and limitation text before adding a supersession.
Later tasks simultaneously demanded preserving the historical wrong owner lane
and eliminating every occurrence from the packet; tests enforced elimination.
That was contradictory and made the rewrite look green.

The violation cannot be repaired by rewriting Git history or editing the
historical packet again. The correct repair is disclosure and a new forward
integrity boundary.

## Authority disposition

- `handoff.md` is not proof that its complete pre-baseline history was
  append-only. Historical sections are dated implementation evidence only.
- The lifecycle streams remained structurally sound:
  `slice-candidate.md` did not change after attempt 1 and `slice-handoff.md`
  extended append-only through rejection.
- Current truth is the final superseding section of `handoff.md`, the exact Git
  objects it cites, this incident record, and the strict lifecycle streams.
- Shared governance now requires every version after recovery baseline
  `a49313a5354259346e1089e759184b9f08735b37`, including the working tree, to
  preserve the baseline/current prefix exactly and append only.

## Verification

The baseline object and digest were independently reproduced with:

```text
git rev-parse a49313a5354259346e1089e759184b9f08735b37:evidence/v2/observation/handoff.md
ae91264cb67aa5fca1e05d4de7a5b09bf1a712cc

git show a49313a5354259346e1089e759184b9f08735b37:evidence/v2/observation/handoff.md | shasum -a 256
4fdfec86798c941e8c7ad2b7da0957fb913099108a6c5b2167dcb0b085f3cc3d
```

A regression creates an explicit recovery baseline, proves an appended working
copy passes, then proves replacing the prefix fails. This record does not make
pre-baseline history append-only; it prevents another rewrite from being
laundered as one.
