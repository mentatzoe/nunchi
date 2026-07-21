# Hermes V2 successor verification — 2026-07-21

## Candidate identity and scope

- Canonical base: `a03eeb95c7d569895e1171993c7a5748fc250bd8`
- Successor branch: `codex/v2-hermes-successor-08`
- Final candidate commit: assigned by Git after this record is frozen; the exact
  commit is reported with the manifest digest in the external review request.
- Installed Hermes source: `/Users/zmll/.hermes/hermes-agent`
- Installed Hermes commit: `f657840e06e03b9552cf2d28175a1e4e4af0210b`
- Installed Hermes version: `0.19.0`

The candidate is an independent complete successor from the canonical base.
The rejected 23-entry manifest is historical REWORK evidence only and is not a
parent or reconstruction dependency.

## Remediation coverage

The successor closes the original HIGH classes and follow-up lifecycle gaps:

1. Plaintext and native Discord control output serialize against admission and
   close owned participant tickets before direct output.
2. Raw Discord retention and pre-gateway dispatch require canonical literal
   `True` authorization before lookup, scheduling, retention, or receipts.
3. Pre-participant and executor cancellation close exact-generation staged
   state without masking `CancelledError`.
4. Deferred cleanup cannot finish or abort a promoted generation.
5. Reserved wake context stays invisible until the exact native dispatch is
   consumed.
6. Observation, participant-host, and transport receipt persistence accepts
   only exact `None` acknowledgements.
7. `NO_WAKE` closes the participant-host stage canonically without invocation.
8. Discord and Telegram wrappers rebind to current module globals after reload.
9. Non-privileged and privileged tools execute only after participant-host
   receipt persistence; privileged effects use the shared I-040B guard and
   coordinator with canonical room scope.
10. Discord and Telegram adapters expose the pinned native reaction protocol;
    Telegram topic/message correlation preserves exact chat and native message
    identity, and its optional factory is statically resolved before closure.
11. The retired executable Hermes V1 command, verdict, state, resolver, and
    dashboard surface and its obsolete tests are removed; history is archived.

## Fresh command results

- Receipt/identity/reload group: `Ran 14 tests` — `OK`.
- Tool/authorization group: `Ran 5 tests` — `OK`.
- Focused reaction regressions: `Ran 2 tests in 0.003s` — `OK`.
- Complete Hermes lifecycle module: `Ran 87 tests in 0.976s` — `OK`.
- Hermes implementation plus eval: `Ran 94 tests in 2.479s` — `OK`.
- Repository-wide unittest discovery: `Ran 1014 tests in 47.547s` —
  `OK (skipped=7)`.
- Telegram reaction-factory Pyright diagnostic: cleared by binding one
  definitely-callable `resolved_factory` before the nested reaction method.
- Governance boundary and CLI:
  `governance boundary + CLI: OK (SpecKit 0.12.11)`.
- Hermes executable V1-residue audit: `OK`.
- `git diff --check` against the canonical base: `OK`.

## HM-01 through HM-06

All six installed-source scenes returned `PASS`:

- HM-01 exact identity
- HM-02 disposition routing
- HM-03 later-hearing restart
- HM-04 shared Discord
- HM-05 Telegram capability
- HM-06 installed provenance

Regenerated HM evidence SHA-256:
`7914643bfed7fea164a501eec312a389cefcc7b9c0b2e9e9319de8f19b084761`.

## Installed Hermes seams

All installed-source tests used the production interpreter only as an
executable, disposable pytest site `/tmp/nunchi-hermes-py311-pytest.Vroaus/site`,
`PYTHONDONTWRITEBYTECODE=1`, and `-p no:cacheprovider`. No package was installed
and no production source/configuration was changed.

- `tests/e2e/test_platform_commands.py`: `50 passed, 4 skipped in 6.03s`.
- `tests/gateway/test_session_race_guard.py` plus
  `tests/gateway/test_discord_slash_auth.py`: `60 passed in 5.91s`.
- `tests/gateway/test_pending_drain_race.py` plus
  `tests/gateway/test_pending_drain_no_recursion.py`: `8 passed in 4.97s`.
- `tests/gateway/test_discord_roles_dm_scope.py`, with only
  `DISCORD_ALLOWED_CHANNELS` and `DISCORD_IGNORED_CHANNELS` unset:
  `15 passed in 0.18s`. The earlier positive-control failure was inherited
  channel-scope environment contamination, not an installed-Hermes limitation.

The installed checkout remained clean at
`f657840e06e03b9552cf2d28175a1e4e4af0210b`.

## Disposition and limitations

This is a source/evidence review candidate, not an installed-runtime cutover.
No plugin was armed, gateway restarted, profile mutated, or live-delivery claim
made. Canonical lifecycle activation/candidate/handoff records remain absent,
so the packet verifier runs in candidate-internal mode rather than
`--require-complete`. External integration review must accept or reject the
exact final commit; this packet owner does not self-accept it.
