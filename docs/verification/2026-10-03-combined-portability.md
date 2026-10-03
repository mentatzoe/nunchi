# Combined Hermes portability repair — 3 October 2026

PR83 landed at `19ba1398a3619bd077edc3bdc03fb5088f3a8fd3`. PR84 combines
installed-host verification, attention Save parser portability and the stopped
profile lifecycle. The parser/provenance repair below addressed `a0dc5a6`;
the next repair also addresses review's real Save→retire failure at `78f60e7`.
Neither is a whole-V2, release or live-adoption claim.

## Dashboard Save and lifecycle interoperability

Dashboard Save intentionally emits JSON. The lifecycle now recognises strict
JSON objects as a separate rendering path rather than treating them as block
YAML. It changes only activation-list values and inserts absent activation keys;
all other JSON bytes, including nested trust entries, remain unchanged. Existing
saved JSON needs no migration. Both formats still undergo the real host parser,
recursive duplicate/alias checks and rendered semantic comparison. General flow
YAML and malformed/non-finite JSON constants still refuse read-only.

The regression first reproduced the public Save→retire failure for default and
named profiles. A separate RED case caught trust-byte reformatting before the
narrower splice was applied. Repository lifecycle tests now cover those paths,
existing compact/pretty/escaped-key JSON, absent nodes, unsafe JSON, byte-exact
restore and publication races for both YAML and JSON. The installed package
runner includes real Save→retire→verify→uninstall/reinstall→restore in default
and named profiles, followed by named-profile reactivation and fresh discovery.

The new canary resolved for this repair is stock main
`eaecc99c7ec5b6f37e880a0b69d16871cd3e4f57`, not the earlier snapshots below.
The frozen successor manifest and raw logs carry its exact wheel and final
matrix/source/eval outcomes. Modern host dependencies remain separate from the
source-only test extra; no PyYAML is added to modern hosts.

## Repair and reproduced failures

- Lifecycle manifest/config/predecessor readers now use the real host parser:
  modern `hermes_yaml` load/dump with ruamel YAML 1.1 token/node marks;
  released-host PyYAML only when `hermes_yaml` itself is absent. Broken
  transitive imports never trigger fallback. Alias/anchor, duplicate mapping,
  unsupported layout and rendered-mapping checks run before staging. Config
  outside the activation node retains its bytes.
- The no-Hermes source suite declares PyYAML in `.[test]` alongside jsonschema.
  Modern installed-host proofs deliberately do not install that extra.
- Verifier source identity rejects a nested archive under another Git root,
  empty/wrong project inventories and tracked paths escaping the selected root
  before reading tracked bytes. Clean/dirty enclosing-root regressions verify
  that it never reads unrelated contents.

The original combined wheel reproduced the missing `yaml` failure on current
main; the original test extra reproduced the source lifecycle errors. Negative
YAML tests also reproduced nested duplicate keys accepted by released PyYAML;
the lifecycle now rejects those explicitly. All failed logs are retained with
the task evidence rather than replaced by successful reruns.

## Verification and provenance

Fresh task-owned environments for the prior parser/provenance repair used these
stock targets (historical evidence, not the Save→retire successor's final run):

| Target | Exact stock identity | Installation |
|---|---|---|
| Minimum 0.19.0 | `3ef6bbd201263d354fd83ec55b3c306ded2eb72a` | published `hermes-agent[messaging]==0.19.0` wheel |
| Release 0.21.5 | `f97608f178d1ffeca59860195ab7da295f7c8e5f` | supported source install with declared messaging dependencies |
| Moving main, resolved this run | `46904a3b467f62616f5b3ee247adce30b1b277a0` | supported source install, Python 3.14, no PyYAML |

The development repair passes 805 source tests on clean Python 3.11/3.12/3.13
with the normal test extra (30 explicit installed-host-only skips), and 11/11
offline eval scenes per interpreter. Each stock target passes 24 lifecycle tests
without skips, the exact historical 648-case V1 path matrix, and the full real
package/profile sequence: historical installation, cutover, fresh discovery,
archived predecessor wheel restoration, retirement, actual uninstall/reinstall,
guarded restoration and named-profile isolation. Host sources and other
installed RECORD files remain unchanged. The modern production parser probe
asserts PyYAML is absent; no parser mocks or JSON-only replacement mask that path.

The frozen deliverable's task attachment manifest binds commit/tree, exact wheel,
source/wheel/installed equality, commands, raw logs and before/after integrity.
Final verification uses `scripts/verify_stock_hermes.py` for normal-attention32,
Discord/Telegram contract4+4 and startup1+1 per host, plus the lifecycle runner
and unchanged safety/race probes against that same wheel. Consult the retained
final receipts for outcomes; development results above do not stand in for the
frozen run. Independent review covers the entire combined delta from `19ba139`,
not just this repair. Author runtime is `openai-codex/gpt-6-astra`; profile naming
is not evidence of a different model family.

## What this does not claim

Normal-turn tests use a loopback model and captured platform transport. Fresh
registration and filesystem verification are not authenticated provider/platform
acceptance or adoption by a running gateway. Auto-title, typing, voice/media,
thread/detached-command and other missing event/platform surfaces remain open
requirements. Native Hermes tools and approval authority are unchanged.

The lifecycle archives actual attributed predecessor bytes; it does not convert
V1 social policy/history, erase unrelated user data or purge retained archives.
All live activity remains separately authorised and operator-owned. PR84's exact
review, remote CI consumption, canonical merge and post-merge verification belong
to the delivery owner; this local record is not a remote CI or release verdict.
