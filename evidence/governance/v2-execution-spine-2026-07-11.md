# V2 execution-spine verification — 2026-07-11

## Claim boundary

This record proves the Goal 1 governance, planning, relocation, and tooling
candidate. It does **not** claim that any V2 product contract or behavior is
implemented. The ordinary runtime remains V1.

## Upstream authority

- Aleph Vault selected-design PR
  [#67](https://github.com/mentatzoe/aleph-vault/pull/67) is merged at
  `bdd1ebb97012b3eaa67c1c5b21af6e7118b7294a`.
- Contract-clarification PR
  [#68](https://github.com/mentatzoe/aleph-vault/pull/68) is merged at
  `c834e8c5a56b81cf2f8f400d056f8f007eeab4ac`.
- Both commits were verified as ancestors of Aleph Vault `origin/main`.

## SpecKit installation and workflow

- Repository pin: SpecKit `0.12.11`, upstream commit
  `e802a7dd52a6eceba9403cbbf40e60dced043238`.
- `python3 scripts/check_governance.py --check-cli` passed. The CLI check
  verified both `specify --version` and uv's PEP 610 source/commit metadata.
- `specify self check` reported `Up to date: 0.12.11`.
- `specify integration list` reported exactly Claude and Codex installed, with
  Codex as default.
- `specify workflow info nunchi-plan` parsed nine planning-only steps and no
  implementation step.
- `specify workflow info speckit` parsed thirteen steps with explicit Goal 2
  authorization before implementation, followed by convergence and handoff.
- `.specify/scripts/bash/check-prerequisites.sh --json` resolved the active
  umbrella at `specs/001-nunchi-v2-program` successfully.

## Repository boundary and relocation

- Governance validation found no product artifact under `.specify/`, `specs/`,
  or either SpecKit skill surface, and no executable/build/test/eval/runtime
  dependency on a managed path.
- All 120 relocated historical verdict-fixture files compare byte-for-byte with
  their versions at the Goal 1 base commit.
- `python3 -m evals.verdict_suite.runner --list` discovered 60 fixtures from the
  ordinary `evals/` tree.
- Historical evidence path changes are recorded through dated addenda; captured
  run observations were not rewritten.
- `git diff --check` passed and the local Markdown-link audit embedded in the
  governance validator found no missing target.

## Disposable control-plane proof

A disposable repository copy was tested with `.specify/`, `specs/`, and both
SpecKit skill surfaces removed. At that proof point, `python3 -m unittest`
discovered all 968 pre-existing product tests: 960 passed and the existing 8
remained skipped; the then-present 9 governance tests were additionally skipped
only because the control plane was intentionally absent. The ordinary verdict
runner still discovered all 60 fixtures.

The copy was then initialized from the exact pinned SpecKit commit for Codex,
Claude was installed, Codex was restored as default, and the reviewed Nunchi
governance overlay was reapplied. Product baseline and corpus discovery remained
unchanged, and the governance/CLI check passed. Later additions in this branch
only expand governance tests; they do not alter the product proof.

## Final candidate baseline

```text
python3 -m unittest
Ran 980 tests in 27.231s
OK (skipped=8)
```

The total consists of the unchanged 968-test product baseline plus 12 governance
tests. No existing test was deleted or weakened.

Independent foundation and surface red-team passes ended with zero unresolved
CRITICAL, HIGH, MEDIUM, or LOW findings. In particular, they closed the
preattention-bypass representation, classifier-safe continuation projection,
immutable staged-receipt ownership, core/surface evidence dependency cycle,
exact CLI process contract, surface-producing tasks, stochastic repetition
floor, S14 ladder, assurance-base provenance, and atomic-main-merge ambiguities.
