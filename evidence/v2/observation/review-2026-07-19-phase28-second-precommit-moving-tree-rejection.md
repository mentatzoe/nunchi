## Verdict: **FAIL**

### Blocking findings

1. **The review object moved and is no longer the requested frozen tree**
   - Started at requested `HEAD=upstream=6c3b89ef030cfa8bebdc5f206f899569e4e7c813`.
   - During review, files changed repeatedly; then `901aaed47e8d7173df4a0a8788ed69e3cecdb44f` was committed.
   - Final state:
     - `HEAD=901aaed…`
     - upstream remains `6c3b89e…`
     - branch is ahead by one
     - four files are newly dirty again.
   - Reproduction:
     ```sh
     git rev-parse HEAD
     git rev-parse '@{u}'
     git status --short --branch --untracked-files=all
     ```
   - No single immutable tree is bound to all completed inspection and verification.

2. **T159 was closed contrary to the required lifecycle state**
   - `specs/020-v2-observation/tasks.md:1225` now marks T159 `[X]`.
   - The required state was `ACTIVE` with `T103/T159/T160` open.
   - Current diagnostic reports:
     ```text
     checked=158 ... open=T103,T160
     ```
   - The task itself requires freeze **and push**; the branch remains ahead of upstream and the metadata successor is dirty. `evidence/v2/observation/handoff.md:1427-1430` nevertheless says T159 is closed.
   - Restore T159 to open until its complete immutable freeze/push/scan contract is actually satisfied.

3. **“All top-level checkbox rows” parsing remains bypassable**
   - `scripts/check_governance.py:1411-1415` recognizes only `- [...]` rows.
   - Standard top-level Markdown task bullets using `*` or `+` are silently omitted.
   - Public-manifest reproduction with a complete graph plus:
     ```text
     * [X] T161 hidden top-level checkbox
     ```
     returned success with exactly 160 parsed IDs:
     ```text
     public_manifest_hidden_checkbox=ACCEPTED 160 True
     ```
   - This violates strict all-top-level-checkbox canonical parsing and lets a hidden extra task coexist with an apparently exact T001–T160 graph.

4. **Supersession semantics are still regex-bypassable**
   - `scripts/check_governance.py:1614-1628`
   - The new checks reject one reported negation phrase, but still accept contradictory equivalents:
     ```text
     exact object never remains rejected and is now authorized
     exact object remains rejected only in name; acceptance is valid
     ```
   - Both returned `[]` from the attempt-2 policy check.
   - Enforce an exact canonical rejection statement or structured disposition rather than attempting open-ended semantic validation with keyword regexes.

5. **Current diff hygiene and its evidence claim are false**
   - `git diff --check HEAD` exits `2`.
   - Trailing-whitespace findings:
     - `evidence/v2/observation/convergence-phase28-task-rejection-authority-2026-07-19.md:130-132`
     - `evidence/v2/observation/handoff.md:1421-1422`
   - This conflicts with the recorded clean diff-check claim, including `convergence-phase28-task-rejection-authority-2026-07-19.md:154`.

### Passing controls observed

Before subsequent tree movement invalidated exact-object binding:

- Full unittest: **1,467 OK, 4 skips**
- Observation: **207 OK**
- Standard eval: **53 rows, 0 FAIL**
- Adversarial eval: **39 rows, 0 FAIL**, freshly reproduced byte-for-byte
- Docs + corpus: **14 + 6 tests OK**, corpus **202/202**
- Ruff `--no-cache`: clean
- Working-tree secret scan: 0 findings
- Donor review artifacts matched `3e38a70` byte-for-byte; donor candidate/handoff files were not imported
- Product mechanisms inspected—returned-event/page relation gaps, restart-gap wire truth, final-page validation, deterministic relation priority, private-issued receipt authority, and permanent handle non-reuse—were present

These controls do not overcome the lifecycle, parser, semantic-policy, diff-integrity, and moving-object blockers.

### Review hygiene

- **Files created or modified by me:** none.
- **Issue encountered:** concurrent writes and a commit occurred inside the supposedly frozen review worktree.